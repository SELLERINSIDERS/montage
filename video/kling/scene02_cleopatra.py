#!/usr/bin/env python3
"""
Scene 02 — Cleopatra in Palace (Image-to-Video)

Animates Scene_2.png using Kling 3.0 image-to-video.
Motion: Slow dolly in, torch flames flickering, fabric shifting subtly.
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

IMAGE_PATH = Path(os.path.expanduser("~/Downloads/Scene_2.png"))
OUTPUT_DIR = Path(__file__).parent.parent / "output" / "kling" / "clips"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_jwt_token():
    now = int(time.time())
    headers = {"alg": "HS256", "typ": "JWT"}
    payload = {"iss": ACCESS_KEY, "exp": now + 1800, "nbf": now - 5}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256", headers=headers)


def api_request(method, endpoint, json_data=None):
    token = generate_jwt_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
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


def main():
    if not IMAGE_PATH.exists():
        print(f"❌ Image not found: {IMAGE_PATH}", flush=True)
        sys.exit(1)

    print(f"📸 Image: {IMAGE_PATH}", flush=True)
    image_base64 = encode_image(IMAGE_PATH)

    motion_prompt = (
        "Slow dolly in toward the woman. Torch flames flickering gently on the walls. "
        "Subtle fabric movement on her white gown. Warm amber light dancing across "
        "hieroglyphic carvings. Dust particles floating in the air. "
        "Smooth, cinematic movement. 5 seconds."
    )

    print(f"\n🎬 Creating image-to-video task...", flush=True)
    print(f"   Prompt: {motion_prompt}", flush=True)

    data = {
        "model_name": "kling-v3",
        "image": image_base64,
        "prompt": motion_prompt,
        "duration": "5",
        "aspect_ratio": "9:16",
        "mode": "std",
        "cfg_scale": 0.4,
    }

    result = api_request("POST", "/videos/image2video", data)
    print(f"  Response: {json.dumps(result, indent=2)}", flush=True)

    task_id = result.get("data", {}).get("task_id")
    if not task_id:
        print(f"❌ No task_id. Response: {json.dumps(result, indent=2)}", flush=True)
        sys.exit(1)

    print(f"\n📋 Task ID: {task_id}", flush=True)
    print(f"\n⏳ Polling...", flush=True)

    start = time.time()
    while time.time() - start < 600:
        res = api_request("GET", f"/videos/image2video/{task_id}")
        d = res.get("data", {})
        status = d.get("task_status", "unknown")
        elapsed = int(time.time() - start)
        print(f"   [{elapsed}s] Status: {status}", flush=True)

        if status == "succeed":
            videos = d.get("task_result", {}).get("videos", [])
            if not videos:
                print("❌ No videos in result.", flush=True)
                sys.exit(1)
            video_url = videos[0].get("url")
            print(f"\n🎥 Video URL: {video_url}", flush=True)

            out = OUTPUT_DIR / "scene_02_cleopatra_palace.mp4"
            print(f"📥 Downloading to {out}...", flush=True)
            r = requests.get(video_url, stream=True, timeout=120)
            r.raise_for_status()
            total = 0
            with open(out, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    total += len(chunk)
            print(f"   Downloaded: {total / (1024*1024):.1f} MB", flush=True)
            print(f"\n🎉 Done! Video saved to: {out}", flush=True)
            return

        elif status == "failed":
            print(f"❌ Failed: {d.get('task_status_msg')}", flush=True)
            sys.exit(1)

        time.sleep(10)

    print("⏰ Timed out.", flush=True)
    sys.exit(1)


if __name__ == "__main__":
    main()
