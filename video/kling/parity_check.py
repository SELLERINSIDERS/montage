"""Pre-flight parity validation before Kling batch generation.

Validates that the number of images matches the number of scenes in the
manifest before any API calls are made. Prevents wasted credits on
mismatched batches.

Usage:
    from video.kling.parity_check import check_parity, ParityError

    try:
        check_parity(Path("vsl/my-project"))
    except ParityError as e:
        print(f"Parity mismatch: {e}")
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ParityError(Exception):
    """Raised when pre-flight parity check fails."""
    pass


def check_parity(project_dir) -> bool:
    """Validate image count matches expected scene count from manifest.

    Checks:
    1. kling_manifest.json exists and is parseable
    2. Image count in images/final/ (or images/v1/ fallback) matches scene count

    Args:
        project_dir: Path to production directory (e.g., vsl/my-project/).

    Returns:
        True if all counts match.

    Raises:
        ParityError: If counts mismatch or manifest is missing.
    """
    project_dir = Path(project_dir)

    # --- Load manifest for expected scene count ---
    manifest_path = project_dir / "manifest" / "kling_manifest.json"
    if not manifest_path.exists():
        raise ParityError(
            f"kling_manifest.json not found at {manifest_path}. "
            "Generate manifest before running batch generation."
        )

    with open(manifest_path) as f:
        scenes = json.load(f)

    expected_count = len(scenes)

    # --- Count images (final/ preferred, v1/ fallback) ---
    final_dir = project_dir / "images" / "final"
    v1_dir = project_dir / "images" / "v1"

    image_extensions = {".png", ".jpg", ".jpeg", ".webp"}

    if final_dir.exists():
        images = [f for f in final_dir.iterdir() if f.suffix.lower() in image_extensions]
    elif v1_dir.exists():
        images = [f for f in v1_dir.iterdir() if f.suffix.lower() in image_extensions]
    else:
        images = []

    image_count = len(images)

    # --- Compare counts ---
    if image_count != expected_count:
        raise ParityError(
            f"Parity mismatch: expected {expected_count} scenes from manifest, "
            f"found {image_count} images. "
            f"Resolve image count before batch generation."
        )

    logger.info(
        "Parity check passed: %d scenes, %d images",
        expected_count,
        image_count,
    )
    return True
