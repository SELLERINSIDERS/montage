#!/usr/bin/env python3
"""Per-segment Whisper transcription with word-level timestamps.

Transcribes each voiceover segment (.mp3) in a project's audio/segments/
directory, producing a JSON file with word-level timestamps alongside
each audio file.

Usage:
    python scripts/transcribe_segments.py \\
        --project vsl/my-project [--model base]
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import whisper
except ImportError:
    whisper = None  # type: ignore[assignment]


def transcribe_segment(audio_path: str, model=None) -> dict:
    """Transcribe a single audio segment with word-level timestamps.

    Args:
        audio_path: Path to the audio file (.mp3).
        model: Pre-loaded whisper model (injectable for testing/reuse).

    Returns:
        Dict with text, segments, and words (word-level timestamps).
    """
    if model is None:
        model = whisper.load_model("base")

    result = model.transcribe(audio_path, word_timestamps=True, language="en")

    # Extract word-level timestamps from all segments
    words = []
    for segment in result.get("segments", []):
        for word_info in segment.get("words", []):
            words.append({
                "word": word_info["word"],
                "start": word_info["start"],
                "end": word_info["end"],
            })

    return {
        "text": result["text"],
        "segments": result["segments"],
        "words": words,
    }


def transcribe_all_segments(
    segments_dir: str,
    model_size: str = "base",
) -> list[dict]:
    """Transcribe all voiceover segments in a directory.

    Finds all *_vo.mp3 files, transcribes each with word-level timestamps,
    and saves the result as a JSON file alongside the mp3.

    Args:
        segments_dir: Directory containing *_vo.mp3 files.
        model_size: Whisper model size ("base", "medium", etc.).

    Returns:
        List of result dicts with scene_id, path, word_count, duration.
    """
    segments_path = Path(segments_dir)
    mp3_files = sorted(segments_path.glob("*_vo.mp3"))

    if not mp3_files:
        logger.warning("No *_vo.mp3 files found in %s", segments_dir)
        return []

    # Load model once for all segments
    model = whisper.load_model(model_size)

    results = []
    for mp3_path in mp3_files:
        scene_id = mp3_path.stem.replace("_vo", "")

        logger.info("Transcribing: %s", mp3_path.name)
        transcription = transcribe_segment(str(mp3_path), model=model)

        # Save JSON alongside mp3
        json_path = mp3_path.with_suffix(".json")
        with open(json_path, "w") as f:
            json.dump(transcription, f, indent=2)

        # Calculate duration from last word end time
        duration = 0.0
        if transcription["words"]:
            duration = transcription["words"][-1]["end"]

        results.append({
            "scene_id": scene_id,
            "path": str(json_path),
            "word_count": len(transcription["words"]),
            "duration": duration,
        })

        logger.info(
            "  %s: %d words, %.1fs",
            scene_id,
            len(transcription["words"]),
            duration,
        )

    return results


def main():
    """CLI entry point for segment transcription."""
    parser = argparse.ArgumentParser(
        description="Transcribe voiceover segments with word-level timestamps"
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Project directory (e.g. vsl/my-project)",
    )
    parser.add_argument(
        "--model",
        default="base",
        choices=["base", "small", "medium", "large"],
        help="Whisper model size (default: base)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    segments_dir = os.path.join(args.project, "audio", "segments")
    if not os.path.isdir(segments_dir):
        logger.error("Segments directory not found: %s", segments_dir)
        sys.exit(1)

    results = transcribe_all_segments(segments_dir, model_size=args.model)

    # Print summary table
    print(f"\n{'Scene':<15} {'Words':>6} {'Duration':>10} {'Path'}")
    print("-" * 60)
    for r in results:
        print(f"{r['scene_id']:<15} {r['word_count']:>6} {r['duration']:>8.1f}s  {r['path']}")

    print(f"\nTotal: {len(results)} segments transcribed")


if __name__ == "__main__":
    main()
