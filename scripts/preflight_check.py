"""Pre-flight asset validation for Remotion rendering.

Validates all assets referenced by an EDL exist and have correct dimensions
before invoking a Remotion render. Reports ALL issues at once.

Usage:
    from scripts.preflight_check import preflight_check

    result = preflight_check(edl, production_dir)
    if result.errors:
        print("BLOCKED:", result.errors)
    if result.warnings:
        print("WARNINGS:", result.warnings)
"""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Minimum playback rate threshold
MIN_PLAYBACK_RATE = 0.5


@dataclass
class PreflightResult:
    """Result of pre-flight validation."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True if no blocking errors found."""
        return len(self.errors) == 0


def _ffprobe_clip(clip_path: Path) -> dict | None:
    """Run ffprobe on a clip and return stream info.

    Returns dict with width, height, duration or None on failure.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "stream=width,height,duration",
                "-of", "json",
                str(clip_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if not streams:
            return None
        stream = streams[0]
        return {
            "width": stream.get("width"),
            "height": stream.get("height"),
            "duration": float(stream.get("duration", 0)),
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        return None


def preflight_check(edl: dict, production_dir: str) -> PreflightResult:
    """Validate all assets referenced by an EDL before rendering.

    Checks:
    - All scene clip_src files exist
    - Voiceover file exists (if voiceover not null)
    - Whisper data file exists (if voiceover not null)
    - Clip dimensions match target format (warning only)
    - Playback rate won't drop below 0.5 (warning only)

    Args:
        edl: EDL dictionary (matching edlSchema).
        production_dir: Root directory of the production.

    Returns:
        PreflightResult with errors and warnings lists.
    """
    result = PreflightResult()
    prod_path = Path(production_dir)

    target_width = edl.get("meta", {}).get("width", 1080)
    target_height = edl.get("meta", {}).get("height", 1920)

    # Check each scene clip
    for scene in edl.get("scenes", []):
        scene_id = scene.get("id", "unknown")
        clip_src = scene.get("clip_src", "")
        clip_path = prod_path / clip_src

        if not clip_path.exists():
            result.errors.append(f"Missing clip: {scene_id} -> {clip_path}")
            continue

        # ffprobe dimension and duration check
        probe = _ffprobe_clip(clip_path)
        if probe:
            # Dimension mismatch warning (report-only, not error)
            if probe["width"] and probe["height"]:
                if (probe["width"] != target_width or
                        probe["height"] != target_height):
                    result.warnings.append(
                        f"Dimension mismatch for {scene_id}: "
                        f"clip is {probe['width']}x{probe['height']}, "
                        f"target is {target_width}x{target_height}"
                    )

            # Playback rate warning
            clip_duration = probe.get("duration", 0)
            scene_duration = scene.get("duration_s", 0)
            if clip_duration > 0 and scene_duration > 0:
                rate = clip_duration / scene_duration
                if rate < MIN_PLAYBACK_RATE:
                    result.warnings.append(
                        f"Playback rate for {scene_id} would be {rate:.2f} "
                        f"(below {MIN_PLAYBACK_RATE}): clip={clip_duration:.1f}s, "
                        f"scene={scene_duration:.1f}s — consider regenerating clip"
                    )

    # Check voiceover
    voiceover = edl.get("voiceover")
    if voiceover:
        vo_src = voiceover.get("src", "")
        vo_path = prod_path / vo_src
        if not vo_path.exists():
            result.errors.append(f"Missing voiceover: {vo_path}")

        # Check whisper data
        whisper_src = voiceover.get("whisper_data", "")
        whisper_path = prod_path / whisper_src
        if not whisper_path.exists():
            result.errors.append(f"Missing Whisper data: {whisper_path}")

    return result
