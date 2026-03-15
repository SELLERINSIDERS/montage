#!/usr/bin/env python3
"""
Test: Does kling-v3-omni work on the direct Kling API (api.klingai.com)?
Also tests generate_audio parameter.

Tests multiple model_name variants to find what works.
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
from PIL import Image
import io

load_dotenv(Path(__file__).parent.parent.parent / ".env")

ACCESS_KEY = os.environ["KLING_ACCESS_KEY"]
SECRET_KEY = os.environ["KLING_SECRET_KEY"]
BASE_URL = "https://api.klingai.com/v1"

IMAGE_PATH = Path(__file__).parent.parent.parent / "images/vsl_cleopatra_v3/scene_01_cleopatra_portrait.png"
OUTPUT_DIR = Path(__file__).parent.parent / "output" / "kling" / "vsl_cleopatra"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PROMPT = (
    "Slow dolly in toward the woman's face. Torchlight flickering warmly on her "
    "features and the golden table surface. Dust particles floating through warm "
    "light beams. Her eyes shift subtly — composed, calculating. Scrolls and maps "
    "catching ambient torch glow in the soft background. "
    "Keep subject identity stable. Cinematic realism. 5s. Smooth, cinematic movement."
)

NEGATIVE_PROMPT = (
    "text, words, letters, logos, watermarks, UI elements, buttons, overlays, "
    "modern clothing in historical scenes, anachronistic objects, "
    "cartoonish, illustrated style, blurry, distorted, morphing faces, identity shift"
)


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
    result = resp.json()
    print(f"  <- Code: {result.get('code')}, Message: {result.get('message')}", flush=True)
    return result


def encode_image(image_path):
    img = Image.open(image_path)
    if img.mode == "RGBA":
        img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw_bytes = buf.getvalue()
    else:
        raw_bytes = image_path.read_bytes()
    return base64.b64encode(raw_bytes).decode("utf-8")


def test_model(model_name, with_audio=False, label=""):
    print(f"\n{'='*60}", flush=True)
    print(f"TEST: {label}", flush=True)
    print(f"  model_name: {model_name}", flush=True)
    print(f"  generate_audio: {with_audio}", flush=True)
    print(f"{'='*60}", flush=True)

    image_base64 = encode_image(IMAGE_PATH)
    print(f"  Image encoded: {len(image_base64)} chars", flush=True)

    data = {
        "model_name": model_name,
        "image": image_base64,
        "prompt": PROMPT,
        "negative_prompt": NEGATIVE_PROMPT,
        "duration": "5",
        "aspect_ratio": "9:16",
        "mode": "std",
        "cfg_scale": 0.4,
    }

    if with_audio:
        data["generate_audio"] = True

    result = api_request("POST", "/videos/image2video", data)

    code = result.get("code")
    task_id = result.get("data", {}).get("task_id") if result.get("data") else None

    if code == 0 and task_id:
        print(f"  ✅ ACCEPTED! Task ID: {task_id}", flush=True)
        return {"status": "accepted", "task_id": task_id, "model": model_name, "audio": with_audio}
    else:
        print(f"  ❌ REJECTED. Code: {code}, Message: {result.get('message')}", flush=True)
        return {"status": "rejected", "code": code, "message": result.get("message"), "model": model_name, "audio": with_audio}


def poll_and_download(task_id, filename):
    print(f"\n  Polling task {task_id}...", flush=True)
    start = time.time()
    while time.time() - start < 600:
        res = api_request("GET", f"/videos/image2video/{task_id}")
        d = res.get("data", {})
        status = d.get("task_status", "unknown")
        elapsed = int(time.time() - start)
        print(f"  [{elapsed}s] Status: {status}", flush=True)

        if status == "succeed":
            videos = d.get("task_result", {}).get("videos", [])
            if not videos:
                print("  ❌ No videos in result.", flush=True)
                return None

            video_url = videos[0].get("url")
            out = OUTPUT_DIR / filename
            print(f"  Downloading to {out}...", flush=True)

            r = requests.get(video_url, stream=True, timeout=120)
            r.raise_for_status()
            total = 0
            with open(out, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    total += len(chunk)

            print(f"  ✅ Downloaded: {total / (1024*1024):.1f} MB -> {out}", flush=True)
            return out

        elif status == "failed":
            print(f"  ❌ Failed: {d.get('task_status_msg')}", flush=True)
            return None

        time.sleep(10)

    print("  ⏰ Timed out.", flush=True)
    return None


def main():
    print("=" * 60, flush=True)
    print("KLING V3-OMNI DIRECT API TEST", flush=True)
    print(f"API: {BASE_URL}", flush=True)
    print(f"Image: {IMAGE_PATH}", flush=True)
    print("=" * 60, flush=True)

    # Test 1: kling-v3-omni (the name we think it should be)
    r1 = test_model("kling-v3-omni", with_audio=False, label="v3-omni WITHOUT audio")
    time.sleep(3)

    # Test 2: kling-v3-omni WITH audio
    r2 = test_model("kling-v3-omni", with_audio=True, label="v3-omni WITH audio")
    time.sleep(3)

    # Test 3: Try alternate naming — maybe "kling-v3.0-omni"
    r3 = test_model("kling-v3.0-omni", with_audio=False, label="v3.0-omni (alternate naming)")
    time.sleep(3)

    # Test 4: Try "kling-v3" with generate_audio (maybe audio works on v3 too?)
    r4 = test_model("kling-v3", with_audio=True, label="v3 WITH audio")

    # Summary
    results = [r1, r2, r3, r4]
    print(f"\n{'='*60}", flush=True)
    print("RESULTS SUMMARY", flush=True)
    print(f"{'='*60}", flush=True)

    accepted = []
    for r in results:
        icon = "✅" if r["status"] == "accepted" else "❌"
        audio_str = "+audio" if r.get("audio") else ""
        print(f"  {icon} {r['model']}{audio_str}: {r['status']} — {r.get('message', r.get('task_id', ''))}", flush=True)
        if r["status"] == "accepted":
            accepted.append(r)

    # If any accepted, poll the first one to download
    if accepted:
        best = accepted[0]
        print(f"\n  Polling best result: {best['model']} (audio={best['audio']})...", flush=True)
        audio_tag = "_with_audio" if best["audio"] else ""
        filename = f"scene_01_test_{best['model'].replace('.', '_')}{audio_tag}.mp4"
        poll_and_download(best["task_id"], filename)

    # Save all results
    results_path = OUTPUT_DIR / "v3_omni_test_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved to {results_path}", flush=True)


if __name__ == "__main__":
    main()
