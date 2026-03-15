#!/usr/bin/env python3
"""
Generate scene manifest from Kling VSL clips.
Runs ffprobe on all clips, outputs:
  - video/remotion-video/src/sceneManifest.ts (TypeScript)
  - state/scene_manifest.json (JSON for batch render script)
"""

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

SOURCE_DIR = Path(__file__).parent.parent / "video" / "output" / "kling" / "vsl_example"  # TODO: Set your Kling output dir
TS_OUTPUT = Path(__file__).parent.parent / "video" / "remotion-video" / "src" / "sceneManifest.ts"
JSON_OUTPUT = Path(__file__).parent.parent / "state" / "scene_manifest.json"


def ffprobe_specs(filepath: str) -> dict:
    """Get width, height, fps, duration from ffprobe."""
    # Width x Height
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", filepath],
            capture_output=True, text=True, timeout=10
        )
    except subprocess.TimeoutExpired:
        logger.error("ffprobe (dimensions) timed out for %s", filepath, exc_info=True)
        raise
    w, h = result.stdout.strip().split(",")

    # FPS
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", filepath],
            capture_output=True, text=True, timeout=10
        )
    except subprocess.TimeoutExpired:
        logger.error("ffprobe (fps) timed out for %s", filepath, exc_info=True)
        raise
    fps_str = result.stdout.strip()
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = int(num) / int(den)
    else:
        fps = float(fps_str)

    # Duration
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", filepath],
            capture_output=True, text=True, timeout=10
        )
    except subprocess.TimeoutExpired:
        logger.error("ffprobe (duration) timed out for %s", filepath, exc_info=True)
        raise
    duration = float(result.stdout.strip())

    return {
        "width": int(w),
        "height": int(h),
        "fps": round(fps),
        "duration": duration,
        "durationInFrames": round(duration * round(fps)),
    }


def extract_scene_id(filename: str) -> str:
    """Extract audio key like 'scene_01' from filename. Strips version suffixes."""
    match = re.match(r"(scene_\d+)", filename)
    if not match:
        raise ValueError(f"Cannot extract scene ID from: {filename}")
    return match.group(1)


def extract_version(filename: str) -> int:
    """Extract version number from filename. Returns 0 for base, 2 for _v2, etc."""
    # Match _v2, _v_2, _v3 etc. at end of stem
    stem = Path(filename).stem
    match = re.search(r"_v_?(\d+)$", stem)
    if match:
        return int(match.group(1))
    return 0


def filename_to_comp_id(filename: str) -> str:
    """Convert filename to unique Remotion composition ID.
    scene_10_survival_to_triumph.mp4 -> Scene10SurvivalToTriumph
    scene_10_survival_to_triumph_v2.mp4 -> Scene10SurvivalToTriumphV2
    """
    stem = Path(filename).stem
    parts = stem.split("_")
    return "".join(p.capitalize() for p in parts)


def file_sort_key(filename: str) -> tuple:
    """Sort by scene number, then version."""
    scene_id = extract_scene_id(filename)
    num = int(scene_id.split("_")[1])
    version = extract_version(filename)
    return (num, version)


def main():
    clips = sorted(SOURCE_DIR.glob("scene_*.mp4"))
    if not clips:
        print(f"ERROR: No scene_*.mp4 files found in {SOURCE_DIR}")
        sys.exit(1)

    print(f"Found {len(clips)} clips in {SOURCE_DIR}")
    print("Running ffprobe on each clip...")

    entries = []
    for clip in clips:
        scene_id = extract_scene_id(clip.name)  # audio key: scene_01, scene_10, etc.
        comp_id = filename_to_comp_id(clip.name)  # unique per file
        specs = ffprobe_specs(str(clip))
        entry = {
            "id": scene_id,
            "compId": comp_id,
            "videoFile": f"vsl/{clip.name}",
            "sourceFile": clip.name,
            "width": specs["width"],
            "height": specs["height"],
            "fps": specs["fps"],
            "duration": specs["duration"],
            "durationInFrames": specs["durationInFrames"],
        }
        entries.append(entry)
        print(f"  {clip.name}: {specs['width']}x{specs['height']} @ {specs['fps']}fps, "
              f"{specs['duration']:.2f}s ({specs['durationInFrames']} frames)")

    # Sort by scene number then version
    entries.sort(key=lambda e: file_sort_key(e["sourceFile"]))

    # Write JSON
    JSON_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(JSON_OUTPUT, "w") as f:
        json.dump(entries, f, indent=2)
    print(f"\nJSON manifest: {JSON_OUTPUT} ({len(entries)} entries)")

    # Write TypeScript
    ts_lines = [
        "// AUTO-GENERATED by scripts/generate_scene_manifest.py — do not edit manually",
        "",
        "export interface SceneEntry {",
        '  id: string;',
        '  compId: string;',
        '  videoFile: string;',
        '  width: number;',
        '  height: number;',
        '  fps: number;',
        '  durationInFrames: number;',
        "}",
        "",
        "export const SCENE_MANIFEST: SceneEntry[] = [",
    ]
    for entry in entries:
        ts_lines.append(
            f'  {{ id: "{entry["id"]}", compId: "{entry["compId"]}", '
            f'videoFile: "{entry["videoFile"]}", '
            f'width: {entry["width"]}, height: {entry["height"]}, '
            f'fps: {entry["fps"]}, durationInFrames: {entry["durationInFrames"]} }},'
        )
    ts_lines.append("];")
    ts_lines.append("")

    TS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(TS_OUTPUT, "w") as f:
        f.write("\n".join(ts_lines))
    print(f"TypeScript manifest: {TS_OUTPUT} ({len(entries)} entries)")

    print(f"\nDone! {len(entries)} scenes ready for audio rendering.")


if __name__ == "__main__":
    main()
