#!/usr/bin/env python3
"""
DEPRECATED: Use scripts/post_production.py for full composition rendering.
This per-scene batch renderer is legacy.

Original description:
Batch render all VSL scenes with audio using Remotion.
Reads scene_manifest.json for clip specs, renders each composition
sequentially via `npx remotion render`, with resume capability.

Usage:
    python3 scripts/batch_render_audio.py
    python3 scripts/batch_render_audio.py --dry-run   # Preview only
"""

import json
import os
import subprocess
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path


def emit_deprecation_warning():
    """Emit a DeprecationWarning for this module."""
    warnings.warn(
        "batch_render_audio.py is deprecated. Use scripts/post_production.py "
        "for full composition rendering.",
        DeprecationWarning,
        stacklevel=2,
    )

PROJECT_ROOT = Path(__file__).parent.parent
REMOTION_DIR = PROJECT_ROOT / "video" / "remotion-video"
MANIFEST_PATH = PROJECT_ROOT / "state" / "scene_manifest.json"
STATE_PATH = PROJECT_ROOT / "state" / "batch_render_audio_state.json"
OUTPUT_DIR = PROJECT_ROOT / "video" / "output" / "kling" / "vsl_with_audio"  # TODO: Set your output dir
AUDIO_DESIGNS_PATH = REMOTION_DIR / "src" / "audioDesigns.ts"
SOURCE_DIR = REMOTION_DIR / "public" / "vsl"  # symlink to original clips
RENDER_TIMEOUT = 180  # seconds per render


def get_silent_scenes() -> set[str]:
    """Parse audioDesigns.ts and return set of scene IDs with empty layers ([])."""
    import re
    silent = set()
    if not AUDIO_DESIGNS_PATH.exists():
        return silent
    content = AUDIO_DESIGNS_PATH.read_text()
    # Match lines like: scene_01: [], or scene_26: [],
    for match in re.finditer(r'(scene_\d+):\s*\[\]', content):
        silent.add(match.group(1))
    return silent


def copy_silent_scene(source: str, dest: str) -> tuple[bool, str]:
    """Copy original clip unchanged for SILENT scenes (no re-encoding)."""
    import shutil
    try:
        shutil.copy2(source, dest)
        return True, "COPIED (silent)"
    except Exception as e:
        return False, str(e)


def load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"started_at": datetime.now().isoformat(), "completed_at": None, "scenes": {}}


def save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def verify_output(filepath: str) -> bool:
    """Check that output has both h264 video and aac audio streams."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name",
             "-of", "csv=p=0", filepath],
            capture_output=True, text=True, timeout=10
        )
        codecs = result.stdout.strip().split("\n")
        has_video = any("h264" in c for c in codecs)
        has_audio = any("aac" in c for c in codecs)
        return has_video and has_audio
    except Exception:
        return False


def render_scene(comp_id: str, output_path: str) -> tuple[bool, str]:
    """Render a single composition. Returns (success, message)."""
    try:
        result = subprocess.run(
            ["npx", "remotion", "render", "src/index.ts", comp_id,
             output_path, "--codec", "h264"],
            capture_output=True, text=True, timeout=RENDER_TIMEOUT,
            cwd=str(REMOTION_DIR)
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip()[-500:] if result.stderr else "Unknown error"
            return False, error_msg
        return True, "OK"
    except subprocess.TimeoutExpired:
        return False, f"Timed out after {RENDER_TIMEOUT}s"
    except Exception as e:
        return False, str(e)


def main():
    emit_deprecation_warning()
    dry_run = "--dry-run" in sys.argv

    # Load manifest
    if not MANIFEST_PATH.exists():
        print(f"ERROR: Manifest not found at {MANIFEST_PATH}")
        print("Run: python3 scripts/generate_scene_manifest.py")
        sys.exit(1)

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    print(f"Loaded manifest: {len(manifest)} scenes")
    print(f"Output directory: {OUTPUT_DIR}")

    if dry_run:
        print("\n[DRY RUN] Would render:")
        for entry in manifest:
            output_file = OUTPUT_DIR / entry["sourceFile"]
            print(f"  {entry['compId']} -> {output_file}")
        print(f"\nTotal: {len(manifest)} renders")
        return

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Detect SILENT scenes from audioDesigns.ts
    silent_scenes = get_silent_scenes()
    print(f"SILENT scenes (copy unchanged): {len(silent_scenes)} — {sorted(silent_scenes)}")

    # Load state for resume
    state = load_state()
    if not state.get("started_at"):
        state["started_at"] = datetime.now().isoformat()

    succeeded = 0
    copied = 0
    failed = 0
    skipped = 0
    total = len(manifest)
    start_time = time.time()

    print(f"\nStarting batch render of {total} scenes...")
    print("=" * 60)

    for i, entry in enumerate(manifest, 1):
        comp_id = entry["compId"]
        state_key = comp_id  # unique per clip (including variants)
        output_file = OUTPUT_DIR / entry["sourceFile"]
        output_path = str(output_file)

        # Check if already completed
        scene_state = state["scenes"].get(state_key, {})
        if scene_state.get("status") == "success" and output_file.exists():
            print(f"[{i}/{total}] {comp_id} — SKIPPED (already done)")
            skipped += 1
            continue

        # Extract scene number from PascalCase compId and normalize to snake_case
        import re
        from video.kling.schema_validation import normalize_scene_id
        pascal_match = re.match(r'Scene(\d+)', comp_id)
        scene_id = normalize_scene_id(comp_id) if pascal_match else None

        # SILENT scenes: copy original unchanged (no re-encoding)
        if scene_id and scene_id in silent_scenes:
            source_file = SOURCE_DIR / entry["sourceFile"]
            print(f"[{i}/{total}] {comp_id} SILENT — copying...", end=" ", flush=True)
            copy_start = time.time()
            success, message = copy_silent_scene(str(source_file), output_path)
            copy_time = time.time() - copy_start
            if success:
                print(f"OK ({copy_time:.1f}s)")
                state["scenes"][state_key] = {
                    "status": "success",
                    "output": entry["sourceFile"],
                    "duration_s": round(copy_time, 1),
                    "method": "copy_silent",
                }
                copied += 1
            else:
                print(f"FAILED — {message[:100]}")
                state["scenes"][state_key] = {
                    "status": "failed",
                    "error": message[:200],
                    "output": None,
                    "method": "copy_silent",
                }
                failed += 1
            save_state(state)
            continue

        # Audio scenes: render through Remotion
        print(f"[{i}/{total}] Rendering {comp_id}...", end=" ", flush=True)
        render_start = time.time()

        success, message = render_scene(comp_id, output_path)
        render_time = time.time() - render_start

        if success and verify_output(output_path):
            print(f"OK ({render_time:.1f}s)")
            state["scenes"][state_key] = {
                "status": "success",
                "output": entry["sourceFile"],
                "duration_s": round(render_time, 1),
                "method": "remotion_render",
            }
            succeeded += 1
        else:
            print(f"FAILED ({render_time:.1f}s) — {message[:100]}")
            state["scenes"][state_key] = {
                "status": "failed",
                "error": message[:200],
                "output": None,
                "duration_s": round(render_time, 1),
                "method": "remotion_render",
            }
            failed += 1

        save_state(state)

    # Final summary
    total_time = time.time() - start_time
    state["completed_at"] = datetime.now().isoformat()
    save_state(state)

    print("\n" + "=" * 60)
    print(f"BATCH RENDER COMPLETE")
    print(f"  Rendered:  {succeeded}")
    print(f"  Copied:    {copied} (SILENT — unchanged)")
    print(f"  Failed:    {failed}")
    print(f"  Skipped:   {skipped}")
    print(f"  Total:     {succeeded + copied + failed + skipped}")
    print(f"  Total time: {total_time:.0f}s ({total_time/60:.1f} min)")
    print(f"  Output:    {OUTPUT_DIR}")
    print(f"  State:     {STATE_PATH}")

    if failed > 0:
        print(f"\n{failed} scenes failed. Re-run to retry them.")
        sys.exit(1)


if __name__ == "__main__":
    main()
