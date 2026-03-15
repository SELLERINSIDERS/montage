#!/usr/bin/env python3
"""Convert a video manifest JSON to batch_generate_concurrent.py-compatible format."""

import json
import os
import re
import sys

INPUT = "vsl/example/video_manifest.json"  # TODO: Set your input manifest
OUTPUT = "video/kling/manifests/batch_manifest.json"  # TODO: Set your output path
IMAGE_DIR = "images/vsl_example"  # TODO: Set your images directory

# Scenes to skip (no images exist)
SKIP_SCENES = {"scene_87", "scene_88"}

PROMPT_SUFFIX = " Keep subject identity stable. Cinematic realism. 5s."


def to_snake(name: str) -> str:
    """Convert scene name to snake_case for filenames."""
    name = name.strip().strip('"').strip("'")
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name.lower()


def convert():
    with open(INPUT) as f:
        data = json.load(f)

    scenes = data["scenes"]
    batch = []

    for s in scenes:
        if s["scene_id"] in SKIP_SCENES:
            continue

        scene_num = s["scene_id"].replace("scene_", "")
        name = to_snake(s["scene_name"])
        image_path = os.path.join(IMAGE_DIR, s["image_file"])

        # Flatten multiline prompt and add suffix
        prompt = " ".join(s["video_prompt"].split())
        if not prompt.rstrip().endswith("5s."):
            prompt = prompt.rstrip() + PROMPT_SUFFIX

        negative = " ".join(s["negative_prompt"].split())

        batch.append({
            "scene": scene_num,
            "name": name,
            "image": image_path,
            "prompt": prompt,
            "negative_prompt": negative,
            "duration": str(s["duration"]),
            "aspect_ratio": "9:16",
            "mode": s.get("mode", "pro"),
            "cfg_scale": s.get("cfg_scale", 0.4),
            "model_name": "kling-v3",
        })

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(batch, f, indent=2)

    print(f"Converted {len(batch)} scenes → {OUTPUT}")

    # Verify images exist
    missing = [e for e in batch if not os.path.exists(e["image"])]
    if missing:
        print(f"\nWARNING: {len(missing)} missing images:")
        for m in missing:
            print(f"  {m['scene']}: {m['image']}")
    else:
        print("All images verified.")


if __name__ == "__main__":
    convert()
