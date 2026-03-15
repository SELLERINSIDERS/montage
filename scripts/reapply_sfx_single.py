#!/usr/bin/env python3
"""
Re-apply SFX to a single clip. Strips existing audio first,
then overlays new SFX layers from the project's audio_design.json.

Usage:
    python scripts/reapply_sfx_single.py --project vsl/nightcap --scene scene_V2_32
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
        project_dir: Project directory path (e.g. "vsl/nightcap").

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
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(video_path)],
            capture_output=True, text=True, timeout=10
        )
    except subprocess.TimeoutExpired:
        logger.error("ffprobe timed out for %s", video_path, exc_info=True)
        raise
    return float(json.loads(result.stdout)["format"]["duration"])


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


def strip_audio(clip_path):
    """Remove audio track, return path to silent video."""
    silent = clip_path.with_suffix(".silent.mp4")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(clip_path), "-c:v", "copy", "-an", str(silent)],
            capture_output=True, text=True, timeout=300
        )
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg strip_audio timed out for %s", clip_path, exc_info=True)
        raise
    return silent


def apply_sfx(scene_id, layers, clip_path, sfx_dir=None):
    """Overlay SFX layers onto a video clip using ffmpeg."""
    if sfx_dir is None:
        sfx_dir = SFX_DIR
    duration = get_duration(clip_path)
    print(f"  [{scene_id}] Duration: {duration:.1f}s, {len(layers)} SFX layer(s)", flush=True)

    inputs = ["-i", str(clip_path)]
    filter_parts = []
    amix_inputs = []

    for i, layer in enumerate(layers):
        sfx_path = sfx_dir / layer["file"]
        if not sfx_path.exists():
            print(f"  WARNING: {layer['file']} not found", flush=True)
            continue

        input_idx = i + 1
        if layer.get("loop", False):
            inputs.extend(["-stream_loop", "-1", "-i", str(sfx_path)])
        else:
            inputs.extend(["-i", str(sfx_path)])

        filters = []
        filters.append(f"volume={layer.get('volume', 0.5)}")
        if layer.get("delay_ms", 0) > 0:
            filters.append(f"adelay={layer['delay_ms']}|{layer['delay_ms']}")
        if layer.get("fadeIn_ms", 0) > 0:
            filters.append(f"afade=t=in:st=0:d={layer['fadeIn_ms'] / 1000.0}")
        filters.append(f"atrim=0:{duration}")
        filters.append("asetpts=PTS-STARTPTS")

        label = f"sfx{i}"
        filter_parts.append(f"[{input_idx}:a]{','.join(filters)}[{label}]")
        amix_inputs.append(f"[{label}]")

    if not amix_inputs:
        return False

    if len(amix_inputs) == 1:
        mix_label = amix_inputs[0]
    else:
        mix_str = "".join(amix_inputs)
        filter_parts.append(f"{mix_str}amix=inputs={len(amix_inputs)}:duration=first:dropout_transition=0[mixed]")
        mix_label = "[mixed]"

    filter_complex = ";".join(filter_parts)
    tmp_path = clip_path.with_suffix(".tmp.mp4")

    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", mix_label,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", str(tmp_path)
    ]

    print(f"  [{scene_id}] Mixing new SFX...", flush=True)
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

    shutil.move(str(tmp_path), str(clip_path))
    new_size = clip_path.stat().st_size / (1024 * 1024)
    print(f"  [{scene_id}] OK — {new_size:.1f} MB", flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(description="Re-apply SFX to a single clip")
    parser.add_argument("--project", required=True,
                        help="Project directory e.g. vsl/nightcap")
    parser.add_argument("--scene", required=True,
                        help="Scene ID e.g. scene_V2_32")
    args = parser.parse_args()

    paths = build_paths(args.project)
    clips_dir = paths["clips_dir"]
    audio_design_path = paths["audio_design"]

    with open(audio_design_path) as f:
        design = json.load(f)

    scene_id = args.scene

    if scene_id not in design["scenes"]:
        print(f"Scene {scene_id} not in audio design")
        return 1

    scene_data = design["scenes"][scene_id]
    name = scene_data["name"]
    clip_path = clips_dir / f"{scene_id}_{name}.mp4"

    if not clip_path.exists():
        print(f"Clip not found: {clip_path}")
        return 1

    print(f"\nRe-applying SFX to {scene_id} ({name})", flush=True)

    # Step 1: Strip existing audio
    print(f"  Stripping old audio...", flush=True)
    silent = strip_audio(clip_path)

    # Step 2: Apply new SFX to the silent version
    if scene_data["layers"]:
        success = apply_sfx(scene_id, scene_data["layers"], silent)
        if success:
            # Move the result back to original name
            shutil.move(str(silent), str(clip_path))
        else:
            silent.unlink()
            return 1
    else:
        # No layers — just keep the silent version
        shutil.move(str(silent), str(clip_path))
        print(f"  No SFX layers — clip is now silent", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
