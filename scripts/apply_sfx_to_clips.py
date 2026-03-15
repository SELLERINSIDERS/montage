#!/usr/bin/env python3
"""
Apply SFX audio layers to Kling video clips using ffmpeg.
Reads audio_design.json from the project manifest directory,
overlays SFX onto clips, replaces originals.
Clips with no SFX layers are untouched.

Usage:
    python scripts/apply_sfx_to_clips.py --project vsl/my-project
"""

import argparse
import json
import logging
import os
import subprocess
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

SFX_DIR = Path("video/remotion-video/public/sfx")


def build_paths(project_dir: str) -> dict:
    """Derive clips_dir and audio_design path from a project directory.

    Args:
        project_dir: Project directory path (e.g. "vsl/my-project").

    Returns:
        Dict with clips_dir and audio_design as Path objects.

    Raises:
        FileNotFoundError: If project directory doesn't exist.
    """
    project = Path(project_dir)
    if not project.exists():
        raise FileNotFoundError(f"Project directory not found: {project}")
    return {
        "clips_dir": project / "video" / "clips",
        "audio_design": project / "manifest" / "audio_design.json",
    }


def get_duration(video_path):
    """Get video duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(video_path)],
            capture_output=True, text=True, timeout=10
        )
    except subprocess.TimeoutExpired:
        logger.error("ffprobe timed out for %s", video_path, exc_info=True)
        raise
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def _verify_with_ffprobe(file_path):
    """Verify a media file is valid using ffprobe. Returns True if valid."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(file_path)],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0 and result.stdout.strip() != ""
    except subprocess.TimeoutExpired:
        logger.error("ffprobe verification timed out for %s", file_path, exc_info=True)
        return False


def apply_sfx(scene_id, scene_data, clip_path, sfx_dir=None):
    """Overlay SFX layers onto a video clip using ffmpeg."""
    if sfx_dir is None:
        sfx_dir = SFX_DIR
    layers = scene_data["layers"]
    if not layers:
        return False

    duration = get_duration(clip_path)
    print(f"  [{scene_id}] Duration: {duration:.1f}s, {len(layers)} SFX layer(s)", flush=True)

    # Build ffmpeg command
    inputs = ["-i", str(clip_path)]
    filter_parts = []
    amix_inputs = []

    for i, layer in enumerate(layers):
        sfx_path = sfx_dir / layer["file"]
        if not sfx_path.exists():
            print(f"  [{scene_id}] WARNING: SFX not found: {layer['file']}", flush=True)
            continue

        input_idx = i + 1  # 0 is the video

        # Loop audio if needed
        if layer.get("loop", False):
            inputs.extend(["-stream_loop", "-1", "-i", str(sfx_path)])
        else:
            inputs.extend(["-i", str(sfx_path)])

        # Build filter chain for this layer
        filters = []
        vol = layer.get("volume", 0.5)
        delay_ms = layer.get("delay_ms", 0)
        fade_in_ms = layer.get("fadeIn_ms", 0)

        # Volume
        filters.append(f"volume={vol}")

        # Delay
        if delay_ms > 0:
            filters.append(f"adelay={delay_ms}|{delay_ms}")

        # Fade in
        if fade_in_ms > 0:
            fade_in_s = fade_in_ms / 1000.0
            filters.append(f"afade=t=in:st=0:d={fade_in_s}")

        # Trim to clip duration (important for looped audio)
        filters.append(f"atrim=0:{duration}")
        filters.append("asetpts=PTS-STARTPTS")

        filter_chain = ",".join(filters)
        label = f"sfx{i}"
        filter_parts.append(f"[{input_idx}:a]{filter_chain}[{label}]")
        amix_inputs.append(f"[{label}]")

    if not amix_inputs:
        return False

    # Mix all SFX layers together
    if len(amix_inputs) == 1:
        mix_label = amix_inputs[0]
    else:
        mix_str = "".join(amix_inputs)
        filter_parts.append(f"{mix_str}amix=inputs={len(amix_inputs)}:duration=first:dropout_transition=0[mixed]")
        mix_label = "[mixed]"

    # Full filter complex
    filter_complex = ";".join(filter_parts)

    # Output to temp file, then replace original
    tmp_path = clip_path.with_suffix(".tmp.mp4")

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "0:v",          # Keep original video
        "-map", mix_label,       # Use mixed SFX audio
        "-c:v", "copy",         # Don't re-encode video
        "-c:a", "aac",          # Encode audio as AAC
        "-b:a", "192k",
        "-shortest",
        str(tmp_path)
    ]

    print(f"  [{scene_id}] Mixing SFX...", flush=True)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg timed out for %s after 300s", scene_id, exc_info=True)
        print(f"  [{scene_id}] ERROR: ffmpeg timed out after 300s (see logs for full trace)", flush=True)
        if tmp_path.exists():
            tmp_path.unlink()
        return False

    if result.returncode != 0:
        logger.error("ffmpeg failed for %s: %s", scene_id, result.stderr)
        print(f"  [{scene_id}] ERROR: {result.stderr[-200:]} (see logs for full trace)", flush=True)
        if tmp_path.exists():
            tmp_path.unlink()
        return False

    # Verify output with ffprobe before replacing original (atomic operation)
    if not _verify_with_ffprobe(tmp_path):
        logger.error("ffprobe verification failed for %s temp output", scene_id)
        print(f"  [{scene_id}] ERROR: output verification failed, discarding temp file", flush=True)
        if tmp_path.exists():
            tmp_path.unlink()
        return False

    # Replace original with SFX version
    shutil.move(str(tmp_path), str(clip_path))
    new_size = clip_path.stat().st_size / (1024 * 1024)
    print(f"  [{scene_id}] OK — replaced ({new_size:.1f} MB)", flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(description="Apply SFX audio layers to Kling video clips")
    parser.add_argument("--project", required=True,
                        help="Project directory e.g. vsl/my-project")
    args = parser.parse_args()

    paths = build_paths(args.project)
    clips_dir = paths["clips_dir"]
    audio_design_path = paths["audio_design"]

    with open(audio_design_path) as f:
        design = json.load(f)

    print(f"\n{'='*60}", flush=True)
    print(f"  Apply SFX to Kling Clips", flush=True)
    print(f"  Clips: {clips_dir}", flush=True)
    print(f"  SFX:   {SFX_DIR}", flush=True)
    print(f"{'='*60}\n", flush=True)

    applied = 0
    skipped = 0
    failed = 0

    for scene_id, scene_data in design["scenes"].items():
        name = scene_data["name"]
        clip_name = f"{scene_id}_{name}.mp4"
        clip_path = clips_dir / clip_name

        if not scene_data["layers"]:
            print(f"  [{scene_id}] No SFX — skipping", flush=True)
            skipped += 1
            continue

        if not clip_path.exists():
            print(f"  [{scene_id}] Clip not found: {clip_name}", flush=True)
            failed += 1
            continue

        if apply_sfx(scene_id, scene_data, clip_path):
            applied += 1
        else:
            failed += 1

    print(f"\n{'='*60}", flush=True)
    print(f"  Done: {applied} with SFX, {skipped} skipped, {failed} failed", flush=True)
    print(f"{'='*60}\n", flush=True)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
