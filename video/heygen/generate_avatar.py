#!/usr/bin/env python3
"""
HeyGen Avatar Video Generator

Generates AI avatar videos via HeyGen API V2.
Supports:
  - Custom avatars (pre-configured in HeyGen account)
  - Studio avatars (liam, harry, leonardo, etc.)
  - Green screen background (for chroma key compositing in Remotion)
  - Transparent WebM (studio avatars only)
  - Configurable dimensions, voice, speed

Usage:
  python3 generate_avatar.py --script "Your text here" --avatar-id YOUR_AVATAR_ID
  python3 generate_avatar.py --script-file path/to/script.json
  python3 generate_avatar.py --list-avatars
  python3 generate_avatar.py --list-voices
"""

import os
import sys
import json
import time
import argparse
import requests
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY")
BASE_URL = "https://api.heygen.com"
POLL_INTERVAL = 10
MAX_POLL_TIME = 600
OUTPUT_DIR = ROOT / "video" / "output" / "heygen"


def get_headers():
    if not HEYGEN_API_KEY:
        print("ERROR: HEYGEN_API_KEY not found in .env", flush=True)
        print("Add this line to your .env file:", flush=True)
        print("  HEYGEN_API_KEY=your_api_key_here", flush=True)
        sys.exit(1)
    return {
        "x-api-key": HEYGEN_API_KEY,
        "Content-Type": "application/json",
    }


def list_avatars():
    """List all available avatars in the account."""
    print("Fetching avatars...", flush=True)
    resp = requests.get(f"{BASE_URL}/v2/avatars", headers=get_headers())
    data = resp.json()

    if resp.status_code != 200:
        print(f"ERROR: {data}", flush=True)
        return

    avatars = data.get("data", {}).get("avatars", [])
    print(f"\n{'='*60}", flush=True)
    print(f"Found {len(avatars)} avatars", flush=True)
    print(f"{'='*60}\n", flush=True)

    for av in avatars:
        avatar_id = av.get("avatar_id", "N/A")
        name = av.get("avatar_name", "Unnamed")
        gender = av.get("gender", "N/A")
        print(f"  ID: {avatar_id}", flush=True)
        print(f"  Name: {name} ({gender})", flush=True)
        print(f"  ---", flush=True)

    return avatars


def list_voices():
    """List all available voices."""
    print("Fetching voices...", flush=True)
    resp = requests.get(f"{BASE_URL}/v2/voices", headers=get_headers())
    data = resp.json()

    if resp.status_code != 200:
        print(f"ERROR: {data}", flush=True)
        return

    voices = data.get("data", {}).get("voices", [])
    print(f"\n{'='*60}", flush=True)
    print(f"Found {len(voices)} voices", flush=True)
    print(f"{'='*60}\n", flush=True)

    for v in voices:
        voice_id = v.get("voice_id", "N/A")
        name = v.get("name", v.get("display_name", "Unnamed"))
        language = v.get("language", "N/A")
        gender = v.get("gender", "N/A")
        print(f"  ID: {voice_id}", flush=True)
        print(f"  Name: {name} ({gender}, {language})", flush=True)
        print(f"  ---", flush=True)

    return voices


def load_sofia_config():
    """Load Sofia avatar config from JSON."""
    config_path = Path(__file__).parent / "sofia_avatar_config.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return None


def generate_video(
    script_text,
    avatar_id="liam",
    voice_id="rex-broadcaster",
    voice_speed=1.0,
    voice_emotion=None,
    width=1080,
    height=1920,
    background_type="color",
    background_value="#00FF00",
    title="Video Ad",
    talking_photo=False,
    use_avatar_iv=False,
    motion_prompt=None,
):
    """
    Generate avatar video via HeyGen V2 API.

    Args:
        script_text: The text for the avatar to speak
        avatar_id: HeyGen avatar ID (studio) or talking_photo_id (custom)
        voice_id: HeyGen voice ID
        voice_speed: Speech speed (0.5-1.5)
        voice_emotion: Voice emotion (Excited, Friendly, Serious, Soothing, Broadcaster)
        width: Video width in pixels
        height: Video height in pixels
        background_type: "color" for solid, "image" for bg image
        background_value: Hex color or image URL
        title: Video title for HeyGen dashboard
        talking_photo: If True, use talking_photo character type
        use_avatar_iv: If True, enable Avatar IV model for natural motion
        motion_prompt: Text description of desired gestures/expressions (Avatar IV only)
    """
    char_type = "talking_photo" if talking_photo else "avatar"
    print(f"Generating video...", flush=True)
    print(f"  Type: {char_type} {'(Avatar IV)' if use_avatar_iv else ''}", flush=True)
    print(f"  Avatar: {avatar_id}", flush=True)
    print(f"  Voice: {voice_id} (speed: {voice_speed}, emotion: {voice_emotion})", flush=True)
    print(f"  Dimensions: {width}x{height}", flush=True)
    print(f"  Background: {background_type} = {background_value}", flush=True)
    if motion_prompt:
        print(f"  Motion: {motion_prompt}", flush=True)
    print(f"  Script length: {len(script_text)} chars", flush=True)

    if len(script_text) > 5000:
        print("WARNING: Script exceeds 5000 chars, may be truncated by HeyGen", flush=True)

    if talking_photo:
        character = {
            "type": "talking_photo",
            "talking_photo_id": avatar_id,
        }
        if use_avatar_iv:
            character["use_avatar_iv_model"] = True
    else:
        character = {
            "type": "avatar",
            "avatar_id": avatar_id,
        }

    voice = {
        "type": "text",
        "voice_id": voice_id,
        "input_text": script_text,
        "speed": voice_speed,
    }
    if voice_emotion:
        voice["emotion"] = voice_emotion

    video_input = {
        "character": character,
        "voice": voice,
        "background": {
            "type": background_type,
            "value": background_value,
        },
    }

    payload = {
        "video_inputs": [video_input],
        "dimension": {"width": width, "height": height},
        "title": title,
    }

    resp = requests.post(
        f"{BASE_URL}/v2/video/generate",
        json=payload,
        headers=get_headers(),
    )
    result = resp.json()

    if resp.status_code != 200 or result.get("error"):
        print(f"ERROR generating video: {json.dumps(result, indent=2)}", flush=True)
        sys.exit(1)

    video_id = result["data"]["video_id"]
    print(f"Video generation started: {video_id}", flush=True)
    return video_id


def poll_and_download(video_id, output_filename=None):
    """Poll for completion and download the video."""
    if not output_filename:
        output_filename = f"avatar_{video_id}.mp4"

    headers = get_headers()
    start = time.time()
    attempt = 0

    print(f"Polling for completion (max {MAX_POLL_TIME}s)...", flush=True)

    while time.time() - start < MAX_POLL_TIME:
        attempt += 1
        try:
            resp = requests.get(
                f"{BASE_URL}/v1/video_status.get",
                params={"video_id": video_id},
                headers=headers,
            )
            result = resp.json()
        except Exception as e:
            print(f"  Poll attempt {attempt}: network error ({e}), retrying...", flush=True)
            time.sleep(POLL_INTERVAL)
            continue

        if result.get("code") == 100 or resp.status_code == 200:
            status = result.get("data", {}).get("status", "unknown")
        else:
            print(f"  Poll attempt {attempt}: API error: {result}", flush=True)
            time.sleep(POLL_INTERVAL)
            continue

        elapsed = int(time.time() - start)
        print(f"  [{elapsed}s] Status: {status}", flush=True)

        if status == "completed":
            video_url = result["data"]["video_url"]
            output_path = OUTPUT_DIR / output_filename
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            print(f"Downloading video...", flush=True)
            video_resp = requests.get(video_url, stream=True)
            total_size = int(video_resp.headers.get("content-length", 0))

            with open(output_path, "wb") as f:
                downloaded = 0
                for chunk in video_resp.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)

            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"Downloaded: {output_path} ({size_mb:.1f} MB)", flush=True)

            # Save metadata alongside video
            meta_path = output_path.with_suffix(".json")
            meta = {
                "video_id": video_id,
                "video_url": video_url,
                "output_path": str(output_path),
                "status": "completed",
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)
            print(f"Metadata saved: {meta_path}", flush=True)

            return str(output_path)

        if status == "failed":
            error = result.get("data", {}).get("error", "Unknown error")
            print(f"ERROR: Video generation failed: {error}", flush=True)
            sys.exit(1)

        # Exponential backoff: 10s, 10s, 15s, 20s, 30s...
        delay = min(POLL_INTERVAL * (1.2 ** max(0, attempt - 5)), 60)
        time.sleep(delay)

    print(f"ERROR: Timed out after {MAX_POLL_TIME}s", flush=True)
    sys.exit(1)


def generate_from_script_json(script_path):
    """Generate video from a script JSON file."""
    with open(script_path) as f:
        script_data = json.load(f)

    meta = script_data.get("meta", {})
    avatar = script_data.get("avatar", {})
    segments = script_data.get("segments", [])

    # Concatenate all spoken text
    full_script = " ".join(seg["spoken_text"] for seg in segments if seg.get("spoken_text"))

    if not full_script:
        print("ERROR: No spoken_text found in script segments", flush=True)
        sys.exit(1)

    resolution = meta.get("resolution", {"width": 1080, "height": 1920})
    render_mode = avatar.get("render_mode", "green_screen")

    bg_type = "color"
    bg_value = "#00FF00"  # Green screen default
    if render_mode == "dark_background":
        bg_value = script_data.get("style_config", {}).get("background_color", "#0A0A0A")

    is_talking_photo = avatar.get("type", "avatar") == "talking_photo"
    avatar_id_key = "talking_photo_id" if is_talking_photo else "avatar_id"

    video_id = generate_video(
        script_text=full_script,
        avatar_id=avatar.get(avatar_id_key, avatar.get("avatar_id", "liam")),
        voice_id=avatar.get("voice_id", "rex-broadcaster"),
        voice_speed=avatar.get("voice_speed", 1.0),
        voice_emotion=avatar.get("voice_emotion"),
        width=resolution.get("width", 1080),
        height=resolution.get("height", 1920),
        background_type=bg_type,
        background_value=bg_value,
        title=meta.get("title", "Video Ad"),
        talking_photo=is_talking_photo,
        use_avatar_iv=avatar.get("use_avatar_iv", False),
        motion_prompt=avatar.get("motion_prompt"),
    )

    version = Path(script_path).stem
    output_filename = f"{version}_avatar.mp4"

    output_path = poll_and_download(video_id, output_filename)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="HeyGen Avatar Video Generator")
    parser.add_argument("--list-avatars", action="store_true", help="List available avatars")
    parser.add_argument("--list-voices", action="store_true", help="List available voices")
    parser.add_argument("--script", type=str, help="Script text for the avatar to speak")
    parser.add_argument("--script-file", type=str, help="Path to script JSON file")
    parser.add_argument("--avatar-id", type=str, default="liam", help="Avatar ID or talking_photo_id")
    parser.add_argument("--voice-id", type=str, default="rex-broadcaster", help="Voice ID")
    parser.add_argument("--voice-speed", type=float, default=1.0, help="Voice speed (0.5-1.5)")
    parser.add_argument("--width", type=int, default=1080, help="Video width")
    parser.add_argument("--height", type=int, default=1920, help="Video height")
    parser.add_argument("--background", type=str, default="#00FF00", help="Background color (hex)")
    parser.add_argument("--output", type=str, help="Output filename")
    parser.add_argument("--talking-photo", action="store_true", help="Use talking_photo type (for custom avatars)")
    parser.add_argument("--sofia", action="store_true", help="Use Sofia avatar (first look, default voice)")
    parser.add_argument("--sofia-look", type=int, default=0, help="Sofia look index (0-18)")
    args = parser.parse_args()

    if args.list_avatars:
        list_avatars()
        return

    if args.list_voices:
        list_voices()
        return

    if args.script_file:
        output = generate_from_script_json(args.script_file)
        print(f"\nDone! Video saved to: {output}", flush=True)
        return

    if args.script:
        avatar_id = args.avatar_id
        voice_id = args.voice_id
        is_talking_photo = args.talking_photo

        # --sofia shortcut: load Sofia config automatically
        if args.sofia:
            sofia = load_sofia_config()
            if not sofia:
                print("ERROR: sofia_avatar_config.json not found", flush=True)
                sys.exit(1)
            look_idx = args.sofia_look
            if look_idx < 0 or look_idx >= len(sofia["looks"]):
                print(f"ERROR: Sofia look index {look_idx} out of range (0-{len(sofia['looks'])-1})", flush=True)
                sys.exit(1)
            avatar_id = sofia["looks"][look_idx]["talking_photo_id"]
            voice_id = sofia["default_voice_id"]
            is_talking_photo = True
            print(f"  Using Sofia look #{look_idx}: {sofia['looks'][look_idx]['name']}", flush=True)

        video_id = generate_video(
            script_text=args.script,
            avatar_id=avatar_id,
            voice_id=voice_id,
            voice_speed=args.voice_speed,
            width=args.width,
            height=args.height,
            background_value=args.background,
            talking_photo=is_talking_photo,
        )
        output = poll_and_download(video_id, args.output)
        print(f"\nDone! Video saved to: {output}", flush=True)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
