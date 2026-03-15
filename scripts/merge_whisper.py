#!/usr/bin/env python3
"""Merge per-scene Whisper JSON segments into a single whisper.json.

Combines per-scene transcription JSONs with cumulative time offsets
calculated from ffprobe audio durations. Adds scene_id annotation
to each segment for downstream EDL generation.

Usage:
    python scripts/merge_whisper.py --project vsl/nightcap
"""

import argparse
import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_audio_duration(mp3_path: str) -> float:
    """Get audio duration in seconds via ffprobe.

    Args:
        mp3_path: Path to the MP3 file.

    Returns:
        Duration in seconds.

    Raises:
        RuntimeError: If ffprobe fails.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(mp3_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        logger.error("ffprobe timed out for %s", mp3_path, exc_info=True)
        raise RuntimeError(f"ffprobe timed out for {mp3_path}")
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {mp3_path}: {result.stderr}")

    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def merge_whisper(project_dir: str) -> dict:
    """Merge per-scene Whisper JSONs into a single whisper.json.

    Each segment gets:
    - scene_id derived from filename (scene_01_vo.json -> scene_01)
    - Timestamps shifted by cumulative offset from prior scene durations
    - Word-level timestamps shifted when present

    Duration for offset calculation comes from ffprobe on the matching
    MP3 file. Falls back to last segment end time if MP3 is missing.

    Args:
        project_dir: Path to the production root directory.

    Returns:
        Merged dict with {"segments": [...]}.

    Raises:
        FileNotFoundError: If no *_vo.json segments exist.
    """
    proj = Path(project_dir)
    segments_dir = proj / "audio" / "segments"

    # Find and sort JSON segments
    json_files = sorted(segments_dir.glob("*_vo.json")) if segments_dir.is_dir() else []
    if not json_files:
        raise FileNotFoundError(
            f"No Whisper JSON segments found in {segments_dir}. "
            "Run transcription first."
        )

    merged_segments = []
    cumulative_offset = 0.0

    for json_path in json_files:
        # Derive scene_id from filename: scene_01_vo.json -> scene_01
        stem = json_path.stem  # scene_01_vo
        scene_id = stem.replace("_vo", "")

        # Load segments
        with open(json_path) as f:
            data = json.load(f)

        scene_segments = data.get("segments", [])

        # Shift timestamps for each segment
        for seg in scene_segments:
            shifted = {
                "start": round(seg["start"] + cumulative_offset, 3),
                "end": round(seg["end"] + cumulative_offset, 3),
                "text": seg["text"],
                "scene_id": scene_id,
            }

            # Shift word-level timestamps if present
            if "words" in seg:
                shifted["words"] = [
                    {
                        **w,
                        "start": round(w["start"] + cumulative_offset, 3),
                        "end": round(w["end"] + cumulative_offset, 3),
                    }
                    for w in seg["words"]
                ]

            merged_segments.append(shifted)

        # Calculate offset for next scene using ffprobe duration
        mp3_path = json_path.with_suffix(".mp3")
        if mp3_path.exists():
            try:
                duration = _get_audio_duration(str(mp3_path))
            except (RuntimeError, KeyError, json.JSONDecodeError):
                # Fallback to last segment end time
                duration = scene_segments[-1]["end"] if scene_segments else 0.0
                logger.warning(
                    "ffprobe failed for %s, using segment end time %.3f",
                    mp3_path, duration,
                )
        else:
            # Fallback: use last segment end time
            duration = scene_segments[-1]["end"] if scene_segments else 0.0
            logger.warning(
                "MP3 not found for %s, using segment end time %.3f as duration",
                scene_id, duration,
            )

        cumulative_offset = round(cumulative_offset + duration, 3)

    # Write merged output
    merged = {"segments": merged_segments}
    output_path = proj / "audio" / "whisper.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(merged, f, indent=2)

    logger.info(
        "Merged %d segments from %d scenes into %s",
        len(merged_segments), len(json_files), output_path,
    )
    return merged


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Merge per-scene Whisper JSONs into a single file"
    )
    parser.add_argument(
        "--project", required=True, help="Path to production directory"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = merge_whisper(args.project)
    print(f"Merged {len(result['segments'])} segments into whisper.json")


if __name__ == "__main__":
    main()
