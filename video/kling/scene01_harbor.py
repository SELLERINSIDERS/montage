#!/usr/bin/env python3
"""
Scene 01 — Alexandria Harbor (Image-to-Video)

Animates Scene_1.png using Kling 3.0 image-to-video.
Motion: Slow aerial dolly forward over the harbor, ships rocking, golden light.
"""

import jwt
import time
import json
import os
import sys
import base64
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# ── Config ──────────────────────────────────────────────
ACCESS_KEY = os.environ["KLING_ACCESS_KEY"]
SECRET_KEY = os.environ["KLING_SECRET_KEY"]
BASE_URL = "https://api.klingai.com/v1"

IMAGE_PATH = Path(os.path.expanduser("~/Downloads/Scene_1.png"))
OUTPUT_DIR = Path(__file__).parent.parent / "output" / "kling" / "clips"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_jwt_token():
    """Generate a short-lived JWT token from access key + secret key."""
    now = int(time.time())
    headers = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": ACCESS_KEY,
        "exp": now + 1800,
        "nbf": now - 5,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256", headers=headers)


def api_request(method, endpoint, json_data=None):
    """Make an authenticated API request."""
    token = generate_jwt_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = f"{BASE_URL}{endpoint}"
    print(f"  -> {method} {url}", flush=True)

    if method == "GET":
        resp = requests.get(url, headers=headers, timeout=60)
    else:
        resp = requests.post(url, headers=headers, json=json_data, timeout=120)

    print(f"  <- Status: {resp.status_code}", flush=True)

    if resp.status_code != 200:
        print(f"  <- Error: {resp.text}", flush=True)
        resp.raise_for_status()

    return resp.json()


def encode_image(image_path):
    """Encode image as raw base64 string (no compression — preserves full quality)."""
    from PIL import Image
    import io

    size_mb = image_path.stat().st_size / (1024 * 1024)
    print(f"  Original: {image_path.name} ({size_mb:.1f} MB)", flush=True)

    img = Image.open(image_path)
    if img.mode == "RGBA":
        img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw_bytes = buf.getvalue()
    else:
        raw_bytes = image_path.read_bytes()

    raw_mb = len(raw_bytes) / (1024 * 1024)
    print(f"  Sending raw PNG: {raw_mb:.1f} MB (no compression)", flush=True)

    data = base64.b64encode(raw_bytes).decode("utf-8")
    print(f"  Base64 length: {len(data)} chars", flush=True)
    return data


def create_image_to_video(image_base64, prompt, duration="5", aspect_ratio="9:16",
                          model="kling-v3", mode="std"):
    """Create an image-to-video generation task."""
    print(f"\n🎬 Creating image-to-video task...", flush=True)
    print(f"   Prompt: {prompt}", flush=True)
    print(f"   Duration: {duration}s, Aspect: {aspect_ratio}, Model: {model}, Mode: {mode}", flush=True)

    data = {
        "model_name": model,
        "image": image_base64,
        "prompt": prompt,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "mode": mode,
        "cfg_scale": 0.4,
    }

    result = api_request("POST", "/videos/image2video", data)
    print(f"  Response: {json.dumps(result, indent=2)}", flush=True)
    return result


def poll_until_complete(task_id, max_wait=600, interval=10):
    """Poll task status until complete or timeout."""
    print(f"\n⏳ Polling task {task_id}...", flush=True)
    start = time.time()

    while time.time() - start < max_wait:
        result = api_request("GET", f"/videos/image2video/{task_id}")
        data = result.get("data", {})
        status = data.get("task_status", "unknown")
        elapsed = int(time.time() - start)

        print(f"   [{elapsed}s] Status: {status}", flush=True)

        if status == "succeed":
            print(f"\n✅ Task completed!", flush=True)
            return data
        elif status == "failed":
            error = data.get("task_status_msg", "Unknown error")
            print(f"\n❌ Task failed: {error}", flush=True)
            return data

        time.sleep(interval)

    print(f"\n⏰ Timed out after {max_wait}s", flush=True)
    return None


def download_video(video_url, filename):
    """Download the generated video."""
    output_path = OUTPUT_DIR / filename
    print(f"\n📥 Downloading to {output_path}...", flush=True)

    resp = requests.get(video_url, stream=True, timeout=120)
    resp.raise_for_status()

    total = 0
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            total += len(chunk)

    size_mb = total / (1024 * 1024)
    print(f"   Downloaded: {size_mb:.1f} MB", flush=True)
    return output_path


def main():
    # ── Validate image ──────────────────────────────────
    if not IMAGE_PATH.exists():
        print(f"❌ Image not found: {IMAGE_PATH}", flush=True)
        sys.exit(1)

    size_mb = IMAGE_PATH.stat().st_size / (1024 * 1024)
    if size_mb > 10:
        print(f"❌ Image too large: {size_mb:.1f} MB (max 10MB)", flush=True)
        sys.exit(1)

    print(f"📸 Image: {IMAGE_PATH} ({size_mb:.1f} MB)", flush=True)

    # ── Encode image ────────────────────────────────────
    image_base64 = encode_image(IMAGE_PATH)

    # ── Motion prompt (from VSL scene doc) ──────────────
    motion_prompt = (
        "Slow aerial dolly forward over the harbor. Ships gently rocking on water. "
        "Seagulls in the distance. Atmospheric haze drifting. "
        "Golden light shimmering on water surface. "
        "3.5 seconds. Smooth, cinematic movement."
    )

    # ── Step 1: Create task ─────────────────────────────
    result = create_image_to_video(
        image_base64=image_base64,
        prompt=motion_prompt,
        duration="5",
        aspect_ratio="9:16",
        model="kling-v3",
        mode="std",
    )

    # Extract task ID
    data = result.get("data", {})
    task_id = data.get("task_id")

    if not task_id:
        print(f"\n❌ No task_id in response. Full response:", flush=True)
        print(json.dumps(result, indent=2), flush=True)
        sys.exit(1)

    print(f"\n📋 Task ID: {task_id}", flush=True)

    # ── Step 2: Poll until complete ─────────────────────
    completed = poll_until_complete(task_id, max_wait=600, interval=10)

    if not completed or completed.get("task_status") != "succeed":
        print("\n❌ Video generation did not succeed.", flush=True)
        sys.exit(1)

    # ── Step 3: Download video ──────────────────────────
    videos = completed.get("task_result", {}).get("videos", [])
    if not videos:
        print("\n❌ No videos in result.", flush=True)
        print(json.dumps(completed, indent=2), flush=True)
        sys.exit(1)

    video_url = videos[0].get("url")
    if not video_url:
        print("\n❌ No URL in video result.", flush=True)
        sys.exit(1)

    print(f"\n🎥 Video URL: {video_url}", flush=True)
    output_path = download_video(video_url, "scene_01_alexandria_harbor.mp4")
    print(f"\n🎉 Done! Video saved to: {output_path}", flush=True)


if __name__ == "__main__":
    main()
