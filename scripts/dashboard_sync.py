"""Dashboard sync module: bridges local pipeline to Supabase for dashboard consumption.

Pushes manifest data, scene updates, and media assets to Supabase.
Pulls review decisions from the dashboard back to the pipeline.
All operations are non-blocking: failures log warnings but never crash the pipeline.

Usage:
    sync = DashboardSync()
    if sync.enabled:
        sync.push_manifest("vsl/my-project/state/workflow-manifest.json")
        sync.push_heartbeat(production_id)
        decisions = sync.pull_review_decisions(production_id)
"""

import json
import logging
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from supabase import create_client
except ImportError:
    create_client = None  # type: ignore[assignment]

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Map pipeline phases to grouped Kanban stages
STAGE_MAP: dict[str, str] = {
    "script": "Script & Design",
    "storyboard": "Script & Design",
    "scene_design": "Script & Design",
    "camera_plan": "Script & Design",
    "compliance": "Script & Design",
    "image_generation": "Image Gen",
    "image_1k": "Image Gen",
    "image_2k": "Image Gen",
    "image_review": "Image Gen",
    "video_generation": "Video Gen",
    "video_review": "Video Gen",
    "voiceover": "Audio & Post",
    "sound_design": "Audio & Post",
    "post_production": "Audio & Post",
    "remotion_render": "Audio & Post",
    "complete": "Complete",
    "delivered": "Complete",
}

# Retry config
_MAX_RETRIES = 3
_BACKOFF_SECONDS = [1, 2, 4]


def _retry(func, *args, **kwargs):
    """Execute func with retry logic. Returns result on success, None on failure."""
    for attempt in range(_MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if attempt < _MAX_RETRIES - 1:
                wait = _BACKOFF_SECONDS[attempt]
                logger.warning(
                    "DashboardSync retry %d/%d after %ds: %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    wait,
                    exc,
                )
                time.sleep(wait)
            else:
                logger.warning(
                    "DashboardSync failed after %d attempts: %s",
                    _MAX_RETRIES,
                    exc,
                )
    return None


class DashboardSync:
    """Sync pipeline state to Supabase for dashboard consumption.

    All public methods check self.enabled first and return gracefully if False.
    All operations are wrapped in retry logic (3 attempts, 1s/2s/4s backoff).
    No exceptions are raised to the caller.
    """

    def __init__(self) -> None:
        """Initialize Supabase client from environment variables.

        If SUPABASE_URL or SUPABASE_SERVICE_KEY are missing, sets enabled=False
        and logs a warning instead of raising.
        """
        self.enabled = False
        self.client = None
        self.bucket = "production-assets"

        if load_dotenv is not None:
            load_dotenv()
            # Also load additional .env if configured (e.g. for Supabase creds)
            _extra_env = os.environ.get("EXTRA_ENV_FILE", "")
            if _extra_env and Path(_extra_env).exists():
                load_dotenv(Path(_extra_env), override=False)

        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")

        if not url or not key:
            logger.warning(
                "DashboardSync disabled: SUPABASE_URL and/or SUPABASE_SERVICE_KEY not set"
            )
            return

        if create_client is None:
            logger.warning("DashboardSync disabled: supabase package not installed")
            return

        try:
            self.client = create_client(url, key)
            self.enabled = True
        except Exception as exc:
            logger.warning("DashboardSync disabled: failed to create client: %s", exc)

    @staticmethod
    def _load_cost_rates() -> dict:
        """Load API cost rates from config/api_costs.json.

        Returns:
            Dict of rate configs keyed by service name, or empty dict if file missing.
        """
        try:
            config_path = (
                Path(__file__).resolve().parent.parent / "config" / "api_costs.json"
            )
            with open(config_path, "r") as f:
                data = json.load(f)
            return data.get("rates", {})
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.warning("Could not load api_costs.json: %s", exc)
            return {}

    @staticmethod
    def _calculate_analytics(manifest_data: dict) -> dict:
        """Compute production analytics from manifest data.

        Extracts phase_timing, retry_counts, and api_usage from the manifest
        and computes aggregate metrics: total cost, total duration, retry rate,
        and per-phase breakdown.

        Args:
            manifest_data: Full workflow manifest dict.

        Returns:
            Dict with keys: total_cost_estimate, total_duration_minutes,
            retry_rate_percent, phases (list of phase detail dicts).
        """
        phase_timing = manifest_data.get("phase_timing", {})
        retry_counts = manifest_data.get("retry_counts", {})
        api_usage = manifest_data.get("api_usage", {})
        scenes = manifest_data.get("scenes", [])
        scene_count = len(scenes)

        # --- Retry rate ---
        total_retries = 0
        for scene_retries in retry_counts.values():
            total_retries += sum(scene_retries.values())
        retry_rate_percent = (
            (total_retries / scene_count * 100) if scene_count > 0 else 0.0
        )

        # --- Cost estimation ---
        rates = DashboardSync._load_cost_rates()
        total_cost = 0.0

        elevenlabs_chars = api_usage.get("elevenlabs_chars", 0)
        if elevenlabs_chars > 0 and "elevenlabs" in rates:
            cost_per_1000 = rates["elevenlabs"].get("cost_per_1000", 0)
            total_cost += elevenlabs_chars / 1000 * cost_per_1000

        gemini_images = api_usage.get("gemini_images", 0)
        if gemini_images > 0 and "gemini" in rates:
            cost_per_image = rates["gemini"].get("cost_per_image", 0)
            total_cost += gemini_images * cost_per_image

        kling_clips = api_usage.get("kling_clips", 0)
        if kling_clips > 0 and "kling" in rates:
            # Kling is subscription-based, flat monthly cost
            monthly_cost = rates["kling"].get("monthly_cost", 0)
            total_cost += monthly_cost

        total_cost = round(total_cost, 2)

        # --- Phase durations ---
        total_duration_minutes = 0.0
        phases = []
        for phase_name, timing in phase_timing.items():
            started = timing.get("started_at")
            completed = timing.get("completed_at")
            duration_minutes = 0.0
            if started and completed:
                try:
                    start_dt = datetime.fromisoformat(started)
                    end_dt = datetime.fromisoformat(completed)
                    duration_minutes = (end_dt - start_dt).total_seconds() / 60
                except (ValueError, TypeError):
                    pass
            total_duration_minutes += duration_minutes
            phases.append({
                "phase_name": phase_name,
                "duration_minutes": round(duration_minutes, 2),
            })

        return {
            "total_cost_estimate": total_cost,
            "total_duration_minutes": round(total_duration_minutes, 2),
            "retry_rate_percent": round(retry_rate_percent, 1),
            "phases": phases,
            "scene_count": scene_count,
            "total_retries": total_retries,
        }

    def push_manifest(self, manifest_path: str, user_id: Optional[str] = None) -> None:
        """Read workflow manifest from disk and sync to Supabase.

        Upserts the production row with aggregate counts, then upserts each scene.

        Args:
            manifest_path: Path to workflow-manifest.json on disk.
            user_id: Optional Supabase auth user ID to associate with this production.
        """
        if not self.enabled:
            return

        def _do_push():
            with open(manifest_path, "r") as f:
                manifest_data = json.load(f)

            schema_ver = manifest_data.get("schema_version")
            if schema_ver != "workflow-manifest-v2":
                logger.error(
                    "push_manifest requires workflow-manifest-v2, got %r. "
                    "Pass a WorkflowManifest path, not a raw scene array.",
                    schema_ver,
                )
                return  # Fail early, don't push invalid data

            fmt = manifest_data.get("format", "vsl")
            slug = manifest_data.get("slug", "unknown")
            production_id = self._production_id(fmt, slug)

            scenes = manifest_data.get("scenes", [])
            approved = sum(1 for s in scenes if self._scene_status(s) == "approved")
            flagged = sum(1 for s in scenes if self._scene_status(s) == "flagged")
            pending = len(scenes) - approved - flagged

            current_phase = manifest_data.get("current_phase", "script")
            current_stage = STAGE_MAP.get(current_phase, "Script & Design")

            # Compute analytics from manifest data
            analytics = self._calculate_analytics(manifest_data)

            # Extract post_production data for dashboard scene grid
            post_prod = manifest_data.get("post_production", {})
            post_prod_status = post_prod.get("status")
            edl_scenes = []
            if post_prod:
                # Extract scene list from EDL data for dashboard scene grid
                edl_path = post_prod.get("edl_path")
                if edl_path:
                    try:
                        edl_file = Path(manifest_path).parent.parent / Path(edl_path).name
                        if not edl_file.exists():
                            edl_file = Path(edl_path)
                        if edl_file.exists():
                            with open(edl_file, "r") as ef:
                                edl_data = json.load(ef)
                            edl_scenes = [
                                {
                                    "id": s.get("scene_id", s.get("id")),
                                    "label": s.get("label", ""),
                                    "duration_s": s.get("duration_s", 0),
                                    "start_s": s.get("start_s", 0),
                                    "audio_type": s.get("audio_type", ""),
                                }
                                for s in edl_data.get("scenes", [])
                            ]
                    except (json.JSONDecodeError, OSError) as exc:
                        logger.warning("Could not read EDL for dashboard: %s", exc)

            production_row = {
                "id": production_id,
                "format": fmt,
                "slug": slug,
                "display_name": manifest_data.get("display_name", slug),
                "current_phase": current_phase,
                "current_stage": current_stage,
                "scene_count": len(scenes),
                "approved_count": approved,
                "flagged_count": flagged,
                "pending_count": pending,
                "manifest_data": manifest_data,
                "analytics": analytics,
                "updated_at": "now()",
            }

            # Include post_production data for dashboard
            if post_prod_status:
                production_row["post_production"] = {
                    "status": post_prod_status,
                    "edl_scenes": edl_scenes,
                    "preview_versions": post_prod.get("preview_versions", []),
                    "final_version": post_prod.get("final_version"),
                    "final_approved": post_prod.get("final_approved", False),
                }
            if user_id:
                production_row["user_id"] = user_id

            self.client.table("productions").upsert(
                production_row, on_conflict="format,slug"
            ).execute()

            # Upsert each scene
            for idx, scene in enumerate(scenes):
                scene_row = {
                    "production_id": production_id,
                    "scene_id": scene.get("scene_id", f"scene_{idx + 1:02d}"),
                    "scene_index": idx,
                    "prompt_text": scene.get("prompt_text"),
                    "image_1k_status": self._gate_status(scene, "image_1k"),
                    "image_2k_status": self._gate_status(scene, "image_2k"),
                    "video_status": self._gate_status(scene, "video"),
                    "updated_at": "now()",
                }
                self.client.table("scenes").upsert(
                    scene_row, on_conflict="production_id,scene_id"
                ).execute()

        _retry(_do_push)

    def push_scene_update(
        self, production_id: str, scene_id: str, data: dict
    ) -> None:
        """Update a single scene row in Supabase.

        Args:
            production_id: UUID of the production.
            scene_id: Scene identifier (e.g. "scene_01").
            data: Dict of column values to update.
        """
        if not self.enabled:
            return

        def _do_update():
            data["updated_at"] = "now()"
            self.client.table("scenes").update(data).eq(
                "production_id", production_id
            ).eq("scene_id", scene_id).execute()

        _retry(_do_update)

    def push_generation_event(
        self,
        production_id: str,
        scene_id: Optional[str],
        event_type: str,
        event_data: Optional[dict] = None,
    ) -> None:
        """Insert a generation event for the real-time activity feed.

        Args:
            production_id: UUID of the production.
            scene_id: Scene identifier, or None for production-level events.
            event_type: Event type string (e.g. "image_completed", "video_batch_started").
            event_data: Optional dict of event-specific data.
        """
        if not self.enabled:
            return

        def _do_insert():
            self.client.table("generation_events").insert(
                {
                    "production_id": production_id,
                    "scene_id": scene_id,
                    "event_type": event_type,
                    "event_data": event_data or {},
                }
            ).execute()

        _retry(_do_insert)

    def claim_regeneration_job(self, worker_id: str) -> Optional[dict]:
        """Claim the oldest pending regeneration job using optimistic locking.

        Finds the oldest job with status='pending', then attempts to atomically
        update it to 'claimed'. If another worker claims it first, returns None.

        Args:
            worker_id: Identifier for the claiming worker process.

        Returns:
            The claimed job dict on success, None if no jobs or claim lost.
        """
        if not self.enabled:
            return None

        def _do_claim():
            # Find oldest pending job
            result = (
                self.client.table("regeneration_queue")
                .select("*")
                .eq("status", "pending")
                .order("created_at")
                .limit(1)
                .execute()
            )
            if not result.data:
                return None
            job = result.data[0]
            # Attempt to claim it (optimistic lock via status check)
            update_result = (
                self.client.table("regeneration_queue")
                .update(
                    {
                        "status": "claimed",
                        "claimed_by": worker_id,
                        "claimed_at": "now()",
                    }
                )
                .eq("id", job["id"])
                .eq("status", "pending")
                .execute()
            )
            if update_result.data:
                return update_result.data[0]
            return None  # Someone else claimed it

        return _retry(_do_claim)

    def complete_regeneration_job(
        self,
        job_id: str,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """Mark a regeneration job as completed or failed.

        Args:
            job_id: UUID of the regeneration job.
            success: True if the regeneration succeeded, False if it failed.
            error_message: Optional error message when success is False.
        """
        if not self.enabled:
            return

        def _do_complete():
            status = "completed" if success else "failed"
            update: dict = {"status": status, "completed_at": "now()"}
            if error_message:
                update["error_message"] = error_message
            self.client.table("regeneration_queue").update(update).eq(
                "id", job_id
            ).execute()

        _retry(_do_complete)

    def upload_asset(self, local_path: str, storage_path: str) -> Optional[str]:
        """Upload a file to Supabase Storage.

        Args:
            local_path: Path to local file.
            storage_path: Destination path in the storage bucket.

        Returns:
            The storage path on success, None on failure.
        """
        if not self.enabled:
            return None

        def _do_upload():
            with open(local_path, "rb") as f:
                self.client.storage.from_(self.bucket).upload(
                    path=storage_path,
                    file=f,
                    file_options={"upsert": "true"},
                )
            return storage_path

        return _retry(_do_upload)

    def upload_scene_image(
        self,
        production_id: str,
        scene_id: str,
        local_path: str,
        base_storage_path: str,
        clear_flags: bool = True,
        gate_type: str = "image_1k",
    ) -> Optional[str]:
        """Upload a regenerated scene image with CDN cache-busting.

        The storage bucket is public with CDN caching — uploading a new file to
        the same path serves the old cached version. This method avoids that by:
          1. Computing the next revision suffix (_r1, _r2, ...) from the current
             image_storage_path in the database.
          2. Uploading the new image to the versioned path.
          3. Updating image_storage_path in the scenes table atomically.
          4. Optionally clearing flag_reasons and resetting current_gate.

        Args:
            production_id: UUID of the production.
            scene_id: Scene identifier as stored in the scenes table (e.g. "S07").
            local_path: Path to the new image file on disk.
            base_storage_path: Base storage path without revision suffix
                (e.g. "my-project/images/v1/scene_07.png").
            clear_flags: If True, clears flag_reasons and sets current_gate to
                "{gate_type}:generated". Default True.
            gate_type: The gate type used for current_gate value. Default "image_1k".

        Returns:
            The new versioned storage path on success, None on failure.
        """
        if not self.enabled:
            return None

        def _do_upload():
            # Determine next revision number from current DB value
            result = (
                self.client.table("scenes")
                .select("image_storage_path")
                .eq("production_id", production_id)
                .eq("scene_id", scene_id)
                .single()
                .execute()
            )
            current_path: str = (result.data or {}).get(
                "image_storage_path", base_storage_path
            ) or base_storage_path

            # Parse existing revision suffix, e.g. "scene_07_r2.png" → revision=2
            stem, ext = current_path.rsplit(".", 1) if "." in current_path else (current_path, "png")
            # Strip existing _rN suffix if present
            import re as _re
            stem_base = _re.sub(r"_r\d+$", "", stem)
            # Check all existing revisions by counting _rN matches
            rev_match = _re.search(r"_r(\d+)$", stem)
            next_rev = int(rev_match.group(1)) + 1 if rev_match else 1
            versioned_path = f"{stem_base}_r{next_rev}.{ext}"

            # Upload to versioned path
            with open(local_path, "rb") as f:
                self.client.storage.from_(self.bucket).upload(
                    path=versioned_path,
                    file=f,
                    file_options={"upsert": "true"},
                )

            # Update DB to point to new versioned path (image + thumbnail)
            update_data: dict = {
                "image_storage_path": versioned_path,
                "thumbnail_storage_path": versioned_path,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if clear_flags:
                update_data["flag_reasons"] = []
                update_data["current_gate"] = f"{gate_type}:generated"
                update_data["feedback_image"] = None

            self.client.table("scenes").update(update_data).eq(
                "production_id", production_id
            ).eq("scene_id", scene_id).execute()

            logger.info(
                "Uploaded scene image with version bust: %s → %s",
                base_storage_path,
                versioned_path,
            )
            return versioned_path

        return _retry(_do_upload)

    def generate_thumbnail(
        self, video_path: str, thumb_path: str
    ) -> Optional[str]:
        """Extract first frame from video as JPEG thumbnail using ffmpeg.

        Args:
            video_path: Path to source video file.
            thumb_path: Path to write the thumbnail JPEG.

        Returns:
            The thumb_path on success, None on failure.
        """
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    video_path,
                    "-vframes",
                    "1",
                    "-q:v",
                    "5",
                    "-y",
                    thumb_path,
                ],
                capture_output=True,
                check=True,
                timeout=60,
            )
            return thumb_path
        except subprocess.TimeoutExpired:
            logger.error("Thumbnail generation timed out for %s", video_path, exc_info=True)
            return None
        except Exception as exc:
            logger.warning("Thumbnail generation failed: %s", exc, exc_info=True)
            return None

    def pull_review_decisions(self, production_id: str) -> list[dict]:
        """Pull unsynced review decisions from the dashboard.

        Fetches decisions where synced_to_pipeline is False, then marks them synced.
        Deduplicates to keep only the latest decision per (scene_id, gate_type).

        Args:
            production_id: UUID of the production.

        Returns:
            List of decision dicts. Empty list on failure.
        """
        if not self.enabled:
            return []

        def _do_pull():
            result = (
                self.client.table("review_decisions")
                .select("*")
                .eq("production_id", production_id)
                .eq("synced_to_pipeline", False)
                .execute()
            )

            if result.data:
                ids = [d["id"] for d in result.data]
                self.client.table("review_decisions").update(
                    {"synced_to_pipeline": True}
                ).in_("id", ids).execute()

            raw = result.data or []

            # Keep only the latest decision per (scene_id, gate_type)
            latest: dict[tuple, dict] = {}
            for d in sorted(raw, key=lambda x: x.get("decided_at", "")):
                latest[(d.get("scene_id"), d.get("gate_type"))] = d
            return list(latest.values())

        result = _retry(_do_pull)
        return result if result is not None else []

    def pull_flagged_scenes(self, production_id: str) -> list[dict]:
        """Pull scenes that have been flagged in the dashboard with per-gate feedback.

        Checks feedback_image, feedback_video, feedback_final columns on the scenes
        table. Values that are not null, not 'approved', and not 'deferred' are
        treated as flagged feedback text.

        Args:
            production_id: UUID of the production.

        Returns:
            List of dicts with keys: scene_id, gate_type, feedback_text, flag_reasons.
            Empty list on failure or if disabled.
        """
        if not self.enabled:
            return []

        # Map per-gate feedback columns to pipeline gate types
        _FEEDBACK_COL_TO_GATE: dict[str, str] = {
            "feedback_image": "image_1k",
            "feedback_video": "video_clip",
            "feedback_final": "final_video",
        }

        def _do_pull():
            result = (
                self.client.table("scenes")
                .select("scene_id, feedback_image, feedback_video, feedback_final, flag_reasons")
                .eq("production_id", production_id)
                .execute()
            )

            flagged: list[dict] = []
            for scene in (result.data or []):
                for col, gate_type in _FEEDBACK_COL_TO_GATE.items():
                    feedback_value = scene.get(col)
                    if (
                        feedback_value
                        and feedback_value not in ("approved", "deferred")
                    ):
                        flagged.append({
                            "scene_id": scene["scene_id"],
                            "gate_type": gate_type,
                            "feedback_text": feedback_value,
                            "flag_reasons": scene.get("flag_reasons") or [],
                        })
            return flagged

        result = _retry(_do_pull)
        return result if result is not None else []

    def _ensure_video_bucket(self) -> None:
        """Create production-videos bucket if it doesn't exist.

        Called lazily on first upload attempt. Public read, authenticated write.
        """
        if not self.enabled or getattr(self, "_video_bucket_checked", False):
            return

        try:
            self.client.storage.get_bucket("production-videos")
        except Exception:
            try:
                self.client.storage.create_bucket(
                    "production-videos",
                    options={"public": True},
                )
                logger.info("Created storage bucket: production-videos")
            except Exception as exc:
                logger.warning("Could not create production-videos bucket: %s", exc)

        self._video_bucket_checked = True

    def upload_final_video(
        self, production_id: str, video_path: str, version: int,
        quality: str = "final",
    ) -> Optional[str]:
        """Upload rendered video to Supabase Storage production-videos bucket.

        Args:
            production_id: UUID of the production.
            video_path: Local path to the rendered MP4 file.
            version: Version number of the render.
            quality: "preview" or "final".

        Returns:
            Public URL on success, None on failure or if disabled.
        """
        if not self.enabled:
            return None

        self._ensure_video_bucket()

        prefix = "preview" if quality == "preview" else "final"
        storage_path = f"{production_id}/{prefix}_v{version}.mp4"

        def _do_upload():
            with open(video_path, "rb") as f:
                self.client.storage.from_("production-videos").upload(
                    path=storage_path,
                    file=f,
                    file_options={
                        "upsert": "true",
                        "content-type": "video/mp4",
                    },
                )
            # Get public URL
            url_resp = (
                self.client.storage.from_("production-videos")
                .get_public_url(storage_path)
            )
            return url_resp

        result = _retry(_do_upload)
        if result:
            logger.info("Uploaded video (%s v%d): %s", quality, version, result)
        return result

    def push_video_version(
        self, production_id: str, version_data: dict
    ) -> None:
        """Upsert video version record to production_videos table.

        Args:
            production_id: UUID of the production.
            version_data: Dict with keys: version, quality ("preview"/"final"),
                storage_url, rendered_at, render_duration_s, is_approved.
        """
        if not self.enabled:
            return

        def _do_push():
            row = {
                "production_id": production_id,
                "version": version_data.get("version", 1),
                "quality": version_data.get("quality", "preview"),
                "storage_url": version_data.get("storage_url"),
                "rendered_at": version_data.get("rendered_at"),
                "render_duration_s": version_data.get("render_duration_s"),
                "is_approved": version_data.get("is_approved", False),
                "file_size_bytes": version_data.get("file_size_bytes"),
                "updated_at": "now()",
            }
            self.client.table("production_videos").upsert(
                row, on_conflict="production_id,version,quality"
            ).execute()

        _retry(_do_push)

    def mark_final_approved(
        self, production_id: str, version: int
    ) -> None:
        """Mark a video version as approved and update production status.

        Args:
            production_id: UUID of the production.
            version: Version number to approve.
        """
        if not self.enabled:
            return

        def _do_approve():
            # Mark version approved
            self.client.table("production_videos").update(
                {"is_approved": True, "updated_at": "now()"}
            ).eq("production_id", production_id).eq(
                "version", version
            ).execute()

            # Update production status to Complete
            self.client.table("productions").update(
                {
                    "current_stage": "Complete",
                    "current_phase": "complete",
                    "status": "completed",
                    "completed_at": "now()",
                    "updated_at": "now()",
                }
            ).eq("id", production_id).execute()

        _retry(_do_approve)

    def get_video_versions(self, production_id: str) -> list[dict]:
        """Fetch all video version records for a production.

        Args:
            production_id: UUID of the production.

        Returns:
            List of version dicts ordered by version number. Empty on failure.
        """
        if not self.enabled:
            return []

        def _do_fetch():
            result = (
                self.client.table("production_videos")
                .select("*")
                .eq("production_id", production_id)
                .order("version", desc=False)
                .execute()
            )
            return result.data or []

        result = _retry(_do_fetch)
        return result if result is not None else []

    def push_heartbeat(self, production_id: str) -> None:
        """Update heartbeat_at timestamp for stale detection.

        Args:
            production_id: UUID of the production.
        """
        if not self.enabled:
            return

        def _do_heartbeat():
            self.client.table("productions").update(
                {"heartbeat_at": "now()"}
            ).eq("id", production_id).execute()

        _retry(_do_heartbeat)

    @staticmethod
    def _scene_status(scene: dict) -> str:
        """Derive overall scene status from gate data.

        Returns 'approved' if all gates approved, 'flagged' if any flagged
        or needs_manual_intervention, otherwise 'pending'.
        """
        gates = scene.get("gates", {})
        if not gates:
            return "pending"
        statuses = [g.get("status", "pending") for g in gates.values()]
        if "flagged" in statuses or "needs_manual_intervention" in statuses:
            return "flagged"
        if all(s == "approved" for s in statuses):
            return "approved"
        return "pending"

    @staticmethod
    def _production_id(format: str, slug: str) -> str:
        """Generate deterministic UUID5 from format and slug.

        Args:
            format: Production type (vsl, ad, ugc).
            slug: Project slug.

        Returns:
            Deterministic UUID string.
        """
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{format}/{slug}"))

    @staticmethod
    def _gate_status(scene: dict, gate_type: str) -> str:
        """Get the status of a specific gate for a scene."""
        gates = scene.get("gates", {})
        gate = gates.get(gate_type, {})
        return gate.get("status", "pending") if gate else "pending"

    @staticmethod
    def _current_gate(scene: dict) -> Optional[str]:
        """Determine the current active gate for a scene."""
        gate_order = ["image_1k", "image_2k", "video"]
        gates = scene.get("gates", {})
        for gate_type in gate_order:
            gate = gates.get(gate_type, {})
            status = gate.get("status", "pending") if gate else "pending"
            if status != "approved":
                return gate_type
        return None

    @staticmethod
    def _total_attempts(scene: dict) -> int:
        """Sum all gate attempts for a scene."""
        gates = scene.get("gates", {})
        return sum(g.get("attempts", 0) for g in gates.values())
