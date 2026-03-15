#!/usr/bin/env python3
"""
Kling AI API Model & Audio Support Tester

Tests which model versions are accepted by the text-to-video endpoint
and whether generate_audio is supported.
"""

import jwt
import time
import json
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

ACCESS_KEY = os.environ["KLING_ACCESS_KEY"]
SECRET_KEY = os.environ["KLING_SECRET_KEY"]
BASE_URL = "https://api.klingai.com/v1"

DELAY = 3  # seconds between API calls


def generate_jwt_token():
    now = int(time.time())
    headers = {"alg": "HS256", "typ": "JWT"}
    payload = {"iss": ACCESS_KEY, "exp": now + 1800, "nbf": now - 5}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256", headers=headers)


def api_call(method, endpoint, json_data=None):
    """Make an API call and return (status_code, response_json_or_text)."""
    token = generate_jwt_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{BASE_URL}{endpoint}"

    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=30)
        else:
            resp = requests.post(url, headers=headers, json=json_data, timeout=30)

        try:
            body = resp.json()
        except Exception:
            body = resp.text

        return resp.status_code, body
    except Exception as e:
        return None, str(e)


def print_result(label, status_code, body):
    print(f"\n{'─'*60}", flush=True)
    print(f"  {label}", flush=True)
    print(f"  HTTP Status: {status_code}", flush=True)
    if isinstance(body, dict):
        print(f"  Response:", flush=True)
        print(f"  {json.dumps(body, indent=2)}", flush=True)
    else:
        print(f"  Response: {str(body)[:500]}", flush=True)


# ══════════════════════════════════════════════════════════
# PART 1: Probe discovery endpoints
# ══════════════════════════════════════════════════════════
print("=" * 60, flush=True)
print("PART 1: PROBING DISCOVERY ENDPOINTS", flush=True)
print("=" * 60, flush=True)

discovery_endpoints = [
    ("GET", "/models", "List models"),
    ("GET", "/videos/text2video", "GET text2video (might return docs)"),
    ("GET", "/account/info", "Account info"),
    ("GET", "/account/credits", "Account credits"),
    ("GET", "/", "API root"),
]

for method, endpoint, label in discovery_endpoints:
    status_code, body = api_call(method, endpoint)
    print_result(f"{label} — {method} {endpoint}", status_code, body)
    time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
# PART 2: Test model versions on text-to-video
# ══════════════════════════════════════════════════════════
print(f"\n\n{'='*60}", flush=True)
print("PART 2: TEXT-TO-VIDEO MODEL VERSION TESTS", flush=True)
print("=" * 60, flush=True)

models_to_test = [
    "kling-v1",
    "kling-v1-5",
    "kling-v1-6",
    "kling-v2",
    "kling-v2-master",
    "kling-v2-1",
    "kling-v2.5",
    "kling-v2-6",
    "kling-v2.6",
    "kling-v3",
    "kling-v3-omni",
]

base_payload = {
    "prompt": "A calm ocean wave gently washing onto a sandy beach at sunset, golden light reflecting on the water",
    "duration": "5",
    "mode": "std",
    "cfg_scale": 0.4,
    "aspect_ratio": "16:9",
    "negative_prompt": "text, watermarks, logos, blurry, distorted"
}

accepted_models = []

for model in models_to_test:
    payload = {**base_payload, "model_name": model}
    print(f"\n  Testing model: {model}...", flush=True)
    status_code, body = api_call("POST", "/videos/text2video", payload)
    print_result(f"Model: {model}", status_code, body)

    # Check if accepted
    if isinstance(body, dict):
        code = body.get("code", -1)
        task_id = body.get("data", {}).get("task_id") if body.get("data") else None
        if code == 0 and task_id:
            accepted_models.append(model)
            print(f"  >>> ACCEPTED — task_id: {task_id}", flush=True)
        else:
            msg = body.get("message", "")
            print(f"  >>> REJECTED — code: {code}, message: {msg}", flush=True)

    time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
# PART 3: Test generate_audio on accepted models
# ══════════════════════════════════════════════════════════
print(f"\n\n{'='*60}", flush=True)
print("PART 3: AUDIO GENERATION TESTS (generate_audio: true)", flush=True)
print(f"Accepted models to test: {accepted_models}", flush=True)
print("=" * 60, flush=True)

for model in accepted_models:
    payload = {**base_payload, "model_name": model, "generate_audio": True}
    print(f"\n  Testing {model} + generate_audio: true...", flush=True)
    status_code, body = api_call("POST", "/videos/text2video", payload)
    print_result(f"Model: {model} + audio", status_code, body)

    if isinstance(body, dict):
        code = body.get("code", -1)
        task_id = body.get("data", {}).get("task_id") if body.get("data") else None
        if code == 0 and task_id:
            print(f"  >>> ACCEPTED WITH AUDIO — task_id: {task_id}", flush=True)
        else:
            msg = body.get("message", "")
            print(f"  >>> REJECTED WITH AUDIO — code: {code}, message: {msg}", flush=True)

    time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
# PART 4: Test image-to-video endpoint model support
# ══════════════════════════════════════════════════════════
print(f"\n\n{'='*60}", flush=True)
print("PART 4: IMAGE-TO-VIDEO MODEL TESTS (no image — just checking model acceptance)", flush=True)
print("=" * 60, flush=True)

# Try a few models on image2video to see error messages (we won't provide an image)
for model in ["kling-v2", "kling-v2-master", "kling-v3"]:
    payload = {
        "model_name": model,
        "prompt": "A calm ocean wave",
        "duration": "5",
        "mode": "std",
        "cfg_scale": 0.4,
        "aspect_ratio": "16:9",
    }
    print(f"\n  Testing i2v model: {model} (no image)...", flush=True)
    status_code, body = api_call("POST", "/videos/image2video", payload)
    print_result(f"I2V Model: {model} (no image)", status_code, body)

    time.sleep(DELAY)


# ══════════════════════════════════════════════════════════
# PART 5: Check task status of first accepted model (text2video)
# to see if response contains audio fields
# ══════════════════════════════════════════════════════════
if accepted_models:
    print(f"\n\n{'='*60}", flush=True)
    print("PART 5: CHECK TASK STATUS STRUCTURE (for audio fields)", flush=True)
    print("=" * 60, flush=True)

    # Use the first accepted model's task to check status structure
    # Re-submit a quick one
    test_model = accepted_models[0]
    payload = {**base_payload, "model_name": test_model}
    status_code, body = api_call("POST", "/videos/text2video", payload)
    task_id = None
    if isinstance(body, dict) and body.get("data"):
        task_id = body["data"].get("task_id")

    if task_id:
        print(f"\n  Checking status of task {task_id} ({test_model})...", flush=True)
        time.sleep(5)  # Wait a bit
        status_code, body = api_call("GET", f"/videos/text2video/{task_id}")
        print_result(f"Task status ({test_model})", status_code, body)

        # Check for audio-related fields in the response
        if isinstance(body, dict) and body.get("data"):
            data = body["data"]
            result = data.get("task_result", {})
            print(f"\n  Task result keys: {list(result.keys()) if result else 'N/A'}", flush=True)
            if result.get("videos"):
                for i, video in enumerate(result["videos"]):
                    print(f"  Video {i} keys: {list(video.keys())}", flush=True)


# ══════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════
print(f"\n\n{'='*60}", flush=True)
print("SUMMARY", flush=True)
print("=" * 60, flush=True)
print(f"  Models tested: {models_to_test}", flush=True)
print(f"  Models accepted (text2video): {accepted_models}", flush=True)
print(f"  Models rejected: {[m for m in models_to_test if m not in accepted_models]}", flush=True)
print(f"\nDone.", flush=True)
