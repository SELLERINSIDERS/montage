"""KlingClient with dual-backend support: UseAPI.net proxy and direct Kling API.

Routes all Kling API calls through a single client. Backend selection is controlled
by the KLING_USE_PROXY env var (default: false = direct Kling).

Usage:
    from video.kling.api_client import KlingClient

    client = KlingClient()
    output = client.image_to_video(image_bytes, prompt, output_path)
"""

import base64
import json
import logging
import os
import threading
import time

import jwt as pyjwt
import requests

from shared.utils.retry import transient_retry

logger = logging.getLogger(__name__)

# Defaults per CLAUDE.md hard rules
DEFAULT_CFG_SCALE = 0.4
DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low quality, distorted, deformed, watermark, text overlay, "
    "static, frozen, glitch, artifacts"
)
POLL_INTERVAL = 10  # seconds between poll requests
POLL_TIMEOUT = 600  # 10 minutes max poll time

# Backend URLs
USEAPI_BASE_URL = "https://api.useapi.net/v1/kling"
DIRECT_BASE_URL = "https://api.klingai.com/v1"

# Model name mapping: canonical -> per-backend
MODEL_MAP_PROXY = {"kling-v3": "kling-v3-0"}
MODEL_MAP_DIRECT = {"kling-v3": "kling-v3"}


class KlingClient:
    """Unified client for Kling video generation with dual-backend routing."""

    def __init__(self):
        self.use_proxy = os.environ.get("KLING_USE_PROXY", "false").lower() == "true"

        if self.use_proxy:
            self.base_url = USEAPI_BASE_URL
            self.api_key = os.environ.get("USEAPI_KEY", "")
        else:
            self.base_url = DIRECT_BASE_URL
            self.access_key = os.environ.get("KLING_ACCESS_KEY", "")
            self._secret_key = os.environ.get("KLING_SECRET_KEY", "")

        # JWT cache (direct mode only)
        self._jwt_token = None
        self._jwt_expiry = 0
        self._jwt_lock = threading.Lock()

        # Last successful video URL (set by _poll_until_done for callers)
        self.last_video_url = None

        # Adaptive rate limiting state
        self._rate_limited = False
        self._backoff_seconds = 1  # initial backoff
        self._max_backoff = 60
        self._original_semaphore_value = None  # to restore later

        # Rate limit semaphore
        self._semaphore = self._load_rate_limit()

    def _load_rate_limit(self):
        """Load rate limits from config/rate_limits.json if available.

        Reads max_concurrent and submission_delay_seconds from the calibration config.
        Falls back to conservative defaults (3 concurrent, 3s delay) if not calibrated.
        """
        self.submission_delay = 3  # default
        config_paths = [
            "config/rate_limits.json",
            os.path.join(os.path.dirname(__file__), "..", "..", "config", "rate_limits.json"),
        ]
        for path in config_paths:
            try:
                with open(path) as f:
                    limits = json.load(f)
                max_concurrent = limits.get("max_concurrent", 3)
                self.submission_delay = limits.get("submission_delay_seconds", 3)
                return threading.Semaphore(max_concurrent)
            except (FileNotFoundError, json.JSONDecodeError):
                continue
        return threading.Semaphore(3)

    # --- Auth ---

    def _generate_jwt(self):
        """Generate a new HS256 JWT for direct Kling API auth."""
        now = time.time()
        KlingClient._jwt_seq += 1
        payload = {
            "iss": self.access_key,
            "exp": int(now + 1800),  # 30 minutes
            "nbf": int(now),
            "iat": KlingClient._jwt_seq,
        }
        return pyjwt.encode(payload, self._secret_key, algorithm="HS256")

    _jwt_seq = 0  # monotonic counter to guarantee unique JWTs per generation

    def _get_jwt(self):
        """Get cached JWT or generate a new one if expired/near-expiry."""
        with self._jwt_lock:
            if self._jwt_token and time.time() < self._jwt_expiry - 300:
                return self._jwt_token
            self._jwt_token = self._generate_jwt()
            self._jwt_expiry = time.time() + 1800
            return self._jwt_token

    def _get_headers(self):
        """Build auth headers for the active backend."""
        if self.use_proxy:
            token = self.api_key
        else:
            token = self._get_jwt()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    # --- Model mapping ---

    def _get_model_name(self):
        """Return the correct model name for the active backend."""
        if self.use_proxy:
            return MODEL_MAP_PROXY.get("kling-v3", "kling-v3-0")
        return MODEL_MAP_DIRECT.get("kling-v3", "kling-v3")

    # --- Image upload (UseAPI.net) ---

    def _upload_image_useapi(self, image_bytes):
        """Upload image to UseAPI.net /assets endpoint, return CDN URL.

        Uses raw binary upload with Content-Type: image/png as required
        by the current UseAPI assets API.
        """
        resp = requests.post(
            f"{self.base_url}/assets",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "image/png",
            },
            data=image_bytes,
        )
        resp.raise_for_status()
        return resp.json()["url"]

    # --- Submit / Poll ---

    @transient_retry
    def _submit(self, endpoint, payload):
        """Submit a generation request to the active backend."""
        url = f"{self.base_url}{endpoint}"
        resp = requests.post(url, headers=self._get_headers(), json=payload)

        if resp.status_code == 429:
            self._handle_rate_limit()
            raise requests.exceptions.HTTPError("429 Too Many Requests", response=resp)

        resp.raise_for_status()
        result = resp.json()

        # Reset backoff on success (keep 1-worker mode for rest of batch)
        if self._rate_limited:
            self._backoff_seconds = 1

        return result

    def _handle_rate_limit(self):
        """Auto-detect 429, reduce to 1 worker, exponential backoff."""
        if not self._rate_limited:
            logger.warning("429 detected -- switching to 1 concurrent worker")
            self._original_semaphore_value = self._semaphore._value
            self._semaphore = threading.Semaphore(1)
            self._rate_limited = True

        logger.warning("Rate limited -- backing off %ds", self._backoff_seconds)
        time.sleep(self._backoff_seconds)
        self._backoff_seconds = min(self._backoff_seconds * 2, self._max_backoff)

    def _get_poll_endpoint(self, task_id):
        """Build the poll endpoint URL for the given task ID."""
        task_id_str = str(task_id)
        if self.use_proxy:
            return f"/tasks/{task_id_str}"
        return f"/videos/image2video/{task_id_str}"

    @transient_retry
    def _poll_once(self, task_id):
        """Single poll request with retry."""
        endpoint = self._get_poll_endpoint(task_id)
        url = f"{self.base_url}{endpoint}"
        resp = requests.get(url, headers=self._get_headers())
        resp.raise_for_status()
        return resp.json()

    def _extract_task_id(self, submit_response):
        """Extract task ID from submit response (format differs per backend)."""
        if self.use_proxy:
            return submit_response.get("task", {}).get("id")
        return submit_response.get("data", {}).get("task_id")

    def _is_terminal(self, poll_response):
        """Check if task has reached a terminal state."""
        if self.use_proxy:
            status = poll_response.get("status_name", "")
        else:
            status = poll_response.get("data", {}).get("task_status", "")
        return status in ("succeed", "failed")

    def _is_success(self, poll_response):
        """Check if task completed successfully."""
        if self.use_proxy:
            return poll_response.get("status_name") == "succeed"
        return poll_response.get("data", {}).get("task_status") == "succeed"

    def _extract_video_url(self, poll_response):
        """Extract video download URL from successful poll response."""
        if self.use_proxy:
            works = poll_response.get("works", [])
            if works:
                work = works[0]
                # Current API: URL is at works[].resource.resource
                resource = work.get("resource")
                if isinstance(resource, dict):
                    url = resource.get("resource")
                    if url:
                        return url
                # Legacy fallback: URL was at works[].url
                return work.get("url")
        else:
            videos = poll_response.get("data", {}).get("task_result", {}).get("videos", [])
            if videos:
                return videos[0].get("url")
        return None

    # --- High-level API ---

    def poll_existing_task(self, task_id, output_path):
        """Poll a known task_id to completion and download the result.

        Used for crash-resume: when a batch run crashes, clips in SUBMITTED/POLLING
        state have valid task_ids on Kling's servers. This method re-polls them to
        completion without re-submitting.

        Args:
            task_id: A known Kling task ID from a prior run.
            output_path: Where to save the resulting video file.

        Returns:
            output_path on success.

        Raises:
            RuntimeError: If task failed or poll timed out.
        """
        with self._semaphore:
            return self._poll_until_done(task_id, output_path)

    def _poll_until_done(self, task_id, output_path):
        """Internal poll loop: sleep → poll → check terminal → download or raise.

        Shared by image_to_video (after submit) and poll_existing_task (re-poll).
        """
        start = time.time()
        while time.time() - start < POLL_TIMEOUT:
            time.sleep(POLL_INTERVAL)
            poll_resp = self._poll_once(task_id)

            if self._is_terminal(poll_resp):
                if self._is_success(poll_resp):
                    video_url = self._extract_video_url(poll_resp)
                    if not video_url:
                        raise RuntimeError(f"No video URL in response: {poll_resp}")
                    self.last_video_url = video_url
                    self._download(video_url, output_path)
                    logger.info("Video saved: %s", output_path)
                    return output_path
                else:
                    raise RuntimeError(f"Generation failed: {poll_resp}")

        raise RuntimeError(f"Poll timeout after {POLL_TIMEOUT}s for task {task_id}")

    @staticmethod
    def _build_prompt(prompt, audio_prompt=None):
        """Append audio context to video prompt for V3 audio generation.

        Kling V3 has no separate audio prompt field — audio is derived from
        the main prompt. This helper appends audio descriptions so V3's audio
        generation is influenced by the desired ambient sounds.

        Args:
            prompt: The base video/motion prompt.
            audio_prompt: Optional audio description from audio_design.json.

        Returns:
            Combined prompt string.
        """
        if not audio_prompt:
            return prompt
        return f"{prompt} [Audio: {audio_prompt}]"

    def image_to_video(self, image_bytes, prompt, output_path,
                       negative_prompt=None, cfg_scale=None,
                       duration=5, mode="std",
                       image_tail_bytes=None,
                       enable_audio=True):
        """Full lifecycle: submit image-to-video → poll → download.

        Args:
            image_bytes: Raw PNG image bytes (start frame).
            prompt: Motion/scene description.
            output_path: Where to save the resulting video file.
            negative_prompt: What to avoid (default: standard negatives).
            cfg_scale: Creativity vs fidelity (default: 0.4 per CLAUDE.md).
            duration: Video duration in seconds (default: 5).
            mode: Generation mode (default: "std").
            image_tail_bytes: Optional raw PNG bytes for the end frame
                (dual-frame transition). When provided, Kling V3 interpolates
                between start and end images. Duration auto-set to 10s.
            enable_audio: Whether to enable V3 inline audio generation
                (default: True). Set to False for silent scenes. Only
                applies to proxy backend (UseAPI.net).

        Returns:
            output_path on success.

        Raises:
            RuntimeError: If generation fails or times out.
        """
        if negative_prompt is None:
            negative_prompt = DEFAULT_NEGATIVE_PROMPT
        if cfg_scale is None:
            cfg_scale = DEFAULT_CFG_SCALE

        if not enable_audio:
            logger.info("Audio disabled for this clip (silent scene)")

        # Dual-frame transitions auto-override duration to 10s
        if image_tail_bytes is not None:
            duration = 10
            logger.info("Dual-frame transition: using 10s duration for smooth interpolation")

        with self._semaphore:
            # Prepare image
            if self.use_proxy:
                image_url = self._upload_image_useapi(image_bytes)
                # Kling V3 via UseAPI: does NOT support cfg_scale or negative_prompt.
                # Parameter name is "image" (not "input_image").
                payload = {
                    "model_name": self._get_model_name(),
                    "image": image_url,
                    "prompt": prompt,
                    "duration": duration,
                    "mode": mode,
                    "enable_audio": enable_audio,
                }
                endpoint = "/videos/image2video-frames"

                # Dual-frame: upload end image and add to payload
                if image_tail_bytes is not None:
                    tail_url = self._upload_image_useapi(image_tail_bytes)
                    payload["image_tail"] = tail_url
            else:
                b64 = base64.b64encode(image_bytes).decode("utf-8")
                payload = {
                    "model_name": self._get_model_name(),
                    "image": b64,
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "cfg_scale": cfg_scale,
                    "duration": str(duration),
                    "mode": mode,
                }
                endpoint = "/videos/image2video"

                # Dual-frame: add base64-encoded end image to payload
                if image_tail_bytes is not None:
                    payload["image_tail"] = base64.b64encode(image_tail_bytes).decode("utf-8")

            # Submit
            logger.info("Submitting image-to-video: %s", prompt[:80])
            submit_resp = self._submit(endpoint, payload)
            task_id = self._extract_task_id(submit_resp)
            if not task_id:
                raise RuntimeError(f"No task_id in submit response: {submit_resp}")
            logger.info("Task submitted: %s", task_id)

            # Poll until done (shared loop)
            return self._poll_until_done(task_id, output_path)

    def add_sound(self, video_url, output_path, crop_original_sound=False):
        """Add AI-generated audio to an existing video clip (proxy-only).

        Uses UseAPI.net POST /videos/add-sound endpoint to generate ambient
        audio for a video clip. This is a post-process fallback — primary path
        is inline audio via enable_audio=True on image_to_video().

        Note: API usage tracking is caller responsibility. Batch scripts must
        call manifest.increment_api_usage('kling_audio', 1) after each
        successful add_sound() call.

        Args:
            video_url: URL of the video to add audio to (from UseAPI.net CDN
                or prior generation).
            output_path: Where to save the resulting video with audio.
            crop_original_sound: Whether to replace original audio track
                (True) or mix with it (False).

        Returns:
            output_path on success.

        Raises:
            RuntimeError: If video_url is None, or if using direct backend
                (add-sound is UseAPI.net only), or if generation fails.
        """
        if video_url is None:
            raise RuntimeError("video_url is required for add_sound()")
        if not self.use_proxy:
            raise RuntimeError("add_sound() requires proxy backend (UseAPI.net only)")

        payload = {
            "video": video_url,
            "cropVideoOriginalSound": crop_original_sound,
        }

        with self._semaphore:
            submit_resp = self._submit("/videos/add-sound", payload)
            task_id = self._extract_task_id(submit_resp)
            if not task_id:
                raise RuntimeError(f"No task_id in add-sound response: {submit_resp}")
            logger.info("Add-sound task submitted: %s", task_id)
            return self._poll_until_done(task_id, output_path)

    def download_audio(self, task_id, output_path):
        """Download the audio track (MP3) from a completed generation task (proxy-only).

        Uses UseAPI.net GET /assets/download to extract the audio track
        separately from a V3-generated clip. This enables independent volume
        control in Remotion for ducking.

        Note: API usage tracking is caller responsibility.

        Args:
            task_id: The Kling task ID from a completed video generation.
            output_path: Where to save the extracted MP3 file.

        Returns:
            output_path on success.

        Raises:
            RuntimeError: If using direct backend (proxy-only feature).
        """
        if not self.use_proxy:
            raise RuntimeError("download_audio() requires proxy backend (UseAPI.net only)")

        url = f"{self.base_url}/assets/download?workIds={task_id}&fileTypes=MP3"
        resp = requests.get(url, headers=self._get_headers())
        resp.raise_for_status()
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(resp.content)
        logger.info("Audio track saved: %s", output_path)
        return output_path

    def _download(self, url, output_path):
        """Download video file from URL to disk."""
        resp = requests.get(url, stream=True)
        resp.raise_for_status()
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
