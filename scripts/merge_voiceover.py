#!/usr/bin/env python3
"""Merge per-scene voiceover MP3 segments into a single voiceover.mp3.

Uses ffmpeg concat demuxer with -c copy (no re-encode) for lossless
concatenation. Segments are sorted by filename for deterministic order.

Usage:
    python scripts/merge_voiceover.py --project vsl/nightcap
"""

import argparse
import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def merge_voiceover(project_dir: str) -> str:
    """Concatenate per-scene voiceover MP3s into a single audio/voiceover.mp3.

    Args:
        project_dir: Path to the production root directory.

    Returns:
        Path string to the merged output file.

    Raises:
        ComplianceError: If compliance gate fails.
        FileNotFoundError: If no *_vo.mp3 segments exist.
        RuntimeError: If ffmpeg fails.
    """
    from video.kling.compliance_gate import check_compliance, ComplianceError

    # Compliance gate -- block voiceover if compliance failed
    try:
        check_compliance(project_dir)
    except ComplianceError as e:
        logger.error("Compliance gate blocked voiceover merge: %s", e)
        raise

    proj = Path(project_dir)
    segments_dir = proj / "audio" / "segments"

    # Find and sort segments
    segments = sorted(segments_dir.glob("*_vo.mp3")) if segments_dir.is_dir() else []
    if not segments:
        raise FileNotFoundError(
            f"No voiceover segments found in {segments_dir}. "
            "Run voiceover generation first."
        )

    output_path = proj / "audio" / "voiceover.mp3"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Create temp concat list file
    concat_file = None
    try:
        concat_file = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            prefix="ffmpeg_concat_",
            delete=False,
        )
        for seg in segments:
            concat_file.write(f"file '{seg.resolve()}'\n")
        concat_file.close()

        # Run ffmpeg concat demuxer
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file.name,
            "-c", "copy",
            str(output_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg concat timed out after 300s", exc_info=True)
            raise RuntimeError("ffmpeg concat timed out after 300s")

        if result.returncode != 0:
            stderr_tail = result.stderr[-500:] if result.stderr else "(no stderr)"
            raise RuntimeError(
                f"ffmpeg concat failed (exit {result.returncode}): {stderr_tail}"
            )

        logger.info(
            "Merged %d voiceover segments into %s", len(segments), output_path
        )
        return str(output_path)

    finally:
        # Always clean up the temp concat file
        if concat_file is not None:
            try:
                Path(concat_file.name).unlink(missing_ok=True)
            except OSError:
                pass


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Merge per-scene voiceover MP3s into a single file"
    )
    parser.add_argument(
        "--project", required=True, help="Path to production directory"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    output = merge_voiceover(args.project)
    print(f"Merged voiceover written to: {output}")


if __name__ == "__main__":
    main()
