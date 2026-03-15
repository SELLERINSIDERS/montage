#!/usr/bin/env python3
"""
Regenerate ONLY V2-34 (bathroom scene) via Kling V3.
New prompt: digestive discomfort instead of foot tapping.
"""

import json
import os
import sys
import time
import base64
import jwt
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.klingai.com/v1"
OUTPUT_DIR = Path("video/output/kling/vsl_example")  # TODO: Set your output dir
MANIFEST = Path("vsl/example/state/kling_manifest.json")  # TODO: Set your manifest path


def get_token():
    ak = os.environ["KLING_ACCESS_KEY"]
    sk = os.environ["KLING_SECRET_KEY"]
    now = int(time.time())
    payload = {"iss": ak, "exp": now + 1800, "nbf": now - 5}
    return jwt.encode(payload, sk, algorithm="HS256",
                      headers={"alg": "HS256", "typ": "JWT"})


def main():
    with open(MANIFEST) as f:
        scenes = json.load(f)

    scene = next(s for s in scenes if s["scene"] == "V2_34")
    image_path = Path(scene["image"])

    print(f"Regenerating V2-34 via Kling V3...", flush=True)
    print(f"  Prompt: {scene['prompt'][:80]}...", flush=True)

    # Encode image
    image_data = image_path.read_bytes()
    b64 = base64.b64encode(image_data).decode()
    print(f"  Image: {len(image_data) / 1024 / 1024:.1f} MB", flush=True)

    token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Delete old clip
    clip_path = OUTPUT_DIR / f"scene_V2_34_bathroom_scene.mp4"
    if clip_path.exists():
        clip_path.unlink()
        print(f"  Deleted old clip", flush=True)

    # Submit
    payload = {
        "model_name": "kling-v3",
        "mode": "pro",
        "duration": "5",
        "aspect_ratio": "9:16",
        "cfg_scale": 0.4,
        "image": b64,
        "prompt": scene["prompt"],
        "negative_prompt": scene["negative_prompt"],
        "camera": {"type": scene.get("camera", "tilt_down"),
                    "config": {"intensity": scene.get("intensity", 0.2)}}
    }

    resp = requests.post(f"{API_BASE}/videos/image2video", headers=headers, json=payload)
    data = resp.json()

    if data.get("code") != 0:
        print(f"  ERROR: {data}", flush=True)
        return 1

    task_id = data["data"]["task_id"]
    print(f"  Task: {task_id}", flush=True)

    # Poll
    start = time.time()
    while time.time() - start < 600:
        time.sleep(10)
        elapsed = int(time.time() - start)

        # Refresh token if needed
        if elapsed > 0 and elapsed % 300 == 0:
            token = get_token()
            headers["Authorization"] = f"Bearer {token}"

        resp = requests.get(f"{API_BASE}/videos/image2video/{task_id}", headers=headers)
        result = resp.json()
        status = result["data"]["task_status"]
        print(f"  {status}... ({elapsed}s)", flush=True)

        if status == "succeed":
            video_url = result["data"]["task_result"]["videos"][0]["url"]
            video_resp = requests.get(video_url)
            clip_path.write_bytes(video_resp.content)
            size_mb = len(video_resp.content) / 1024 / 1024
            print(f"  OK — {size_mb:.1f} MB", flush=True)
            return 0
        elif status == "failed":
            print(f"  FAILED: {result}", flush=True)
            return 1

    print(f"  TIMEOUT after 600s", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
