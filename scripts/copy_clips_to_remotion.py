#!/usr/bin/env python3
"""
Copy/rename Kling clips to populate Remotion public/vsl/ directory.

The Remotion manifest may use composite scene numbering (master script),
while Kling clips use flat numbering from scene_prompts.

This script:
1. Maps each manifest filename to the correct Kling clip
2. For scenes with multiple takes, picks the best version (latest mod time for versioned clips)
3. Copies clips to video/remotion-video/public/vsl/
4. Skips clips that already exist
5. Reports results
"""

import logging
import os
import shutil
import glob
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
V4_DIR = PROJECT_ROOT / "video/output/kling/vsl_example"  # TODO: Set your Kling output dir
DEST_DIR = PROJECT_ROOT / "video/remotion-video/public/vsl"

# ============================================================================
# MAPPING: manifest_filename -> kling_clip_base_name
#
# The manifest uses composite master-script scene IDs.
# Kling clips use flat scene_prompts numbering.
#
# TEMPLATE: Replace these example entries with your actual scene mappings.
# Format: "manifest_filename.mp4": "kling_clip_base_name"
# ============================================================================

MAPPING = {
    # --- EXAMPLE ENTRIES (replace with your production's actual mappings) ---
    "scene_01_opening.mp4": "scene_01_opening_shot",
    "scene_02_establishing.mp4": "scene_02_establishing_wide",
    "scene_03_subject_intro.mp4": "scene_03_subject_introduction",
    "scene_04_detail.mp4": "scene_04_detail_close_up",
    # ... add one entry per scene in your manifest
}


def find_best_clip(base_name: str) -> str | None:
    """
    Find the best clip for a given base name in the v4 directory.

    For version selection:
    - If only the original exists, use it
    - If versioned clips exist (v2, v3, etc.), compare modification times
    - Use the ORIGINAL unless a newer version has a MORE RECENT modification time
      (indicating a quality refinement)
    """
    # Find all matching clips (base + versioned)
    pattern = f"{base_name}*.mp4"
    matches = list(V4_DIR.glob(pattern))

    if not matches:
        return None

    if len(matches) == 1:
        return matches[0].name

    # Separate original from versions
    original = None
    versions = []

    for m in matches:
        name = m.stem  # without .mp4
        # Check if it's a versioned file (ends with _v2, _v3, _v_2, etc.)
        if re.search(r'_v_?\d+$', name):
            versions.append(m)
        elif name == base_name:
            original = m
        else:
            # Edge case: might be a different scene entirely (e.g., scene_01 matching scene_010)
            # Only include exact base name matches
            if m.stem == base_name:
                original = m

    if not original and not versions:
        return None

    if not versions:
        return original.name if original else None

    if not original:
        # Only versions exist, pick the latest mod time
        best = max(versions, key=lambda p: p.stat().st_mtime)
        return best.name

    # Compare: prefer original UNLESS a version has a more recent modification time
    original_mtime = original.stat().st_mtime

    # Find the latest version
    latest_version = max(versions, key=lambda p: p.stat().st_mtime)
    latest_version_mtime = latest_version.stat().st_mtime

    if latest_version_mtime > original_mtime:
        # A newer version exists with a more recent mod time — it's a quality refinement
        return latest_version.name
    else:
        # Original is newer or same age — prefer original
        return original.name


def main():
    print("=" * 70)
    print("KLING V4 -> REMOTION PUBLIC/VSL CLIP COPY")
    print("=" * 70)
    print(f"\nSource:      {V4_DIR}")
    print(f"Destination: {DEST_DIR}")
    print(f"Manifest scenes: {len(MAPPING)}")
    print()

    # Ensure destination exists
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    copied = []
    skipped = []
    missing = []
    errors = []

    for manifest_file, v4_base in MAPPING.items():
        dest_path = DEST_DIR / manifest_file

        # Skip if already exists
        if dest_path.exists():
            skipped.append(manifest_file)
            continue

        # Find best clip
        best_clip = find_best_clip(v4_base)

        if best_clip is None:
            missing.append((manifest_file, v4_base))
            continue

        src_path = V4_DIR / best_clip

        try:
            shutil.copy2(str(src_path), str(dest_path))
            size_mb = src_path.stat().st_size / (1024 * 1024)
            copied.append((manifest_file, best_clip, size_mb))
        except Exception as e:
            logger.error("Error copying %s: %s", manifest_file, e, exc_info=True)
            errors.append((manifest_file, best_clip, str(e)))

    # Report
    print("-" * 70)
    print(f"COPIED: {len(copied)} clips")
    print("-" * 70)
    for mf, v4f, size in copied:
        print(f"  {v4f}")
        print(f"    -> {mf}  ({size:.1f} MB)")

    print()
    print("-" * 70)
    print(f"SKIPPED (already exist): {len(skipped)} clips")
    print("-" * 70)
    for mf in skipped:
        print(f"  {mf}")

    if missing:
        print()
        print("-" * 70)
        print(f"MISSING (no v4 clip found): {len(missing)} clips")
        print("-" * 70)
        for mf, v4b in missing:
            print(f"  {mf}  (looked for: {v4b}*)")

    if errors:
        print()
        print("-" * 70)
        print(f"ERRORS: {len(errors)} clips")
        print("-" * 70)
        for mf, v4f, err in errors:
            print(f"  {mf} <- {v4f}: {err}")

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    total_size = sum(s for _, _, s in copied)
    print(f"  Copied:  {len(copied)} clips ({total_size:.0f} MB)")
    print(f"  Skipped: {len(skipped)} clips (already existed)")
    print(f"  Missing: {len(missing)} clips")
    print(f"  Errors:  {len(errors)} clips")
    print(f"  Total manifest scenes: {len(MAPPING)}")
    print(f"  Coverage: {len(copied) + len(skipped)}/{len(MAPPING)} ({100*(len(copied)+len(skipped))/len(MAPPING):.0f}%)")


if __name__ == "__main__":
    main()
