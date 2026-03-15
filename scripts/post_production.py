"""Post-production orchestrator for Remotion rendering pipeline.

Single entry point that drives the full post-production flow:
EDL generation -> pre-flight validation -> asset symlinks -> render preview/final.

Supports version tracking, feedback loops with re-rendering, and regen-clip
detection that pauses post-production instead of re-rendering.

Usage:
    # Full pipeline (preview render)
    python scripts/post_production.py vsl/nightcap

    # Final quality render
    python scripts/post_production.py vsl/nightcap --final

    # Re-render preview from existing EDL
    python scripts/post_production.py vsl/nightcap --rerender
"""

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from video.kling.schema_validation import validate_edl as validate_edl_schema
from scripts.edl_generator import generate_edl, modify_edl
from scripts.merge_voiceover import merge_voiceover
from scripts.merge_whisper import merge_whisper
from scripts.preflight_check import preflight_check
from scripts.workflow_manifest import WorkflowManifest
from scripts.dashboard_sync import DashboardSync

logger = logging.getLogger(__name__)

# Remotion public directory for asset symlinks
REMOTION_PUBLIC = Path("video/remotion-video/public/productions")


def check_post_render_dimensions(output_path: str, expected_width: int, expected_height: int) -> None:
    """Compare rendered video dimensions against expected. Report-only (no auto-fix).

    Logs a WARNING with scene ID, expected vs actual dimensions if mismatch found.

    Args:
        output_path: Path to the rendered video file.
        expected_width: Expected video width in pixels.
        expected_height: Expected video height in pixels.
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0",
             str(output_path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            logger.warning(
                "Could not probe dimensions for %s: %s",
                output_path, result.stderr.strip(),
            )
            return
        parts = result.stdout.strip().split(",")
        actual_w, actual_h = int(parts[0]), int(parts[1])
        if actual_w != expected_width or actual_h != expected_height:
            logger.warning(
                "Post-render dimension mismatch for %s: "
                "expected %dx%d, actual %dx%d",
                output_path, expected_width, expected_height,
                actual_w, actual_h,
            )
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe timed out checking dimensions for %s", output_path)
    except (ValueError, IndexError) as exc:
        logger.warning("Could not parse dimensions for %s: %s", output_path, exc)


# ---------------------------------------------------------------------------
# Symlink management
# ---------------------------------------------------------------------------

def setup_symlinks(format: str, slug: str, production_dir: str) -> str:
    """Create symlinks from production assets into Remotion public directory.

    Creates:
      - public/productions/{format}_{slug}/clips -> {production_dir}/video/clips
      - public/productions/{format}_{slug}/audio -> {production_dir}/audio

    Args:
        format: Production format (vsl, ad, ugc).
        slug: Project slug.
        production_dir: Path to the production root.

    Returns:
        Path string to the created symlink directory.

    Raises:
        FileNotFoundError: If source directories don't exist.
    """
    prod_path = Path(production_dir).resolve()
    clips_src = prod_path / "video" / "clips"
    audio_src = prod_path / "audio"

    if not clips_src.is_dir():
        raise FileNotFoundError(f"Clips directory not found: {clips_src}")
    if not audio_src.is_dir():
        raise FileNotFoundError(f"Audio directory not found: {audio_src}")

    link_dir = REMOTION_PUBLIC / f"{format}_{slug}"
    link_dir.mkdir(parents=True, exist_ok=True)

    clips_link = link_dir / "clips"
    if not clips_link.exists():
        clips_link.symlink_to(clips_src)
        logger.info("Symlinked clips: %s -> %s", clips_link, clips_src)

    audio_link = link_dir / "audio"
    if not audio_link.exists():
        audio_link.symlink_to(audio_src)
        logger.info("Symlinked audio: %s -> %s", audio_link, audio_src)

    return str(link_dir)


def cleanup_symlinks(format: str, slug: str) -> None:
    """Remove the symlink directory for a production.

    Args:
        format: Production format.
        slug: Project slug.
    """
    link_dir = REMOTION_PUBLIC / f"{format}_{slug}"
    if link_dir.exists():
        shutil.rmtree(link_dir)
        logger.info("Cleaned up symlinks: %s", link_dir)


# ---------------------------------------------------------------------------
# Version management
# ---------------------------------------------------------------------------

def get_next_version(production_dir: str, quality: str) -> int:
    """Determine the next version number for a render.

    Scans video/final/ for existing files matching the pattern.

    Args:
        production_dir: Path to production root.
        quality: "preview" or "final".

    Returns:
        Next version number (1-based).
    """
    final_dir = Path(production_dir) / "video" / "final"
    if not final_dir.exists():
        return 1

    if quality == "preview":
        pattern = re.compile(r"preview_v(\d+)\.mp4$")
    else:
        pattern = re.compile(r"_v(\d+)\.mp4$")

    max_version = 0
    for f in final_dir.iterdir():
        match = pattern.search(f.name)
        if match:
            v = int(match.group(1))
            if v > max_version:
                max_version = v

    return max_version + 1


# ---------------------------------------------------------------------------
# Render function
# ---------------------------------------------------------------------------

def render_composition(edl_path: str, output_path: str, quality: str = "preview") -> bool:
    """Invoke Remotion render via subprocess.

    Args:
        edl_path: Path to EDL JSON file (passed as --props).
        output_path: Path for the rendered output MP4.
        quality: "preview" (CRF 28, jpeg-quality 60) or "final" (CRF 18).

    Returns:
        True if render succeeded, False otherwise.
    """
    cmd = [
        "npx", "remotion", "render",
        "src/index.ts", "UniversalVSL",
        output_path,
        "--codec", "h264",
        "--props", edl_path,
    ]

    if quality == "preview":
        cmd.extend(["--crf", "28", "--jpeg-quality", "60"])
    else:
        cmd.extend(["--crf", "18"])

    remotion_dir = Path("video/remotion-video")

    logger.info("Starting %s render: %s", quality, output_path)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(remotion_dir),
    )

    # Parse progress from stdout
    try:
        for line in proc.stdout:
            text = line.decode("utf-8", errors="replace").strip()
            # Look for percentage in output
            pct_match = re.search(r"(\d+)%", text)
            if pct_match:
                pct = int(pct_match.group(1))
                bar_len = 30
                filled = int(bar_len * pct / 100)
                bar = "=" * filled + "-" * (bar_len - filled)
                print(f"\rRendering: {pct}% [{bar}]", end="", flush=True)

        proc.wait(timeout=600)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        logger.error("Remotion render timed out after 600s for %s", output_path, exc_info=True)
        print("\nERROR: Render timed out after 600s (see logs for full trace)", flush=True)
        return False
    print()  # Newline after progress bar

    if proc.returncode != 0:
        logger.error("Render failed with exit code %d", proc.returncode)
        return False

    logger.info("Render complete: %s", output_path)
    return True


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_post_production(
    production_dir: str,
    manifest_path: Optional[str] = None,
    audio_design_path: Optional[str] = None,
    whisper_path: Optional[str] = None,
) -> bool:
    """Run the full post-production pipeline.

    Steps: generate_edl -> preflight -> symlink -> render preview.

    Args:
        production_dir: Path to production root.
        manifest_path: Override path to manifest JSON.
        audio_design_path: Override path to audio_design JSON.
        whisper_path: Override path to Whisper JSON.

    Returns:
        True if pipeline completed successfully.
    """
    prod_path = Path(production_dir)

    # Resolve default paths
    _manifest_path = manifest_path or str(prod_path / "state" / "manifest.json")
    _audio_design_path = audio_design_path or str(prod_path / "state" / "audio_design.json")
    _whisper_path = whisper_path or str(prod_path / "audio" / "whisper.json")

    # Load manifest
    manifest = WorkflowManifest(_manifest_path)
    fmt = manifest.data.get("format", "vsl")
    slug = manifest.data.get("slug", "untitled")

    # Record phase start
    now = datetime.now(timezone.utc).isoformat()
    manifest.record_phase_timing("post_production", started_at=now)

    # Step 0: Merge per-scene audio segments if needed
    segments_dir = prod_path / "audio" / "segments"
    merged_vo = prod_path / "audio" / "voiceover.mp3"
    merged_whisper = prod_path / "audio" / "whisper.json"

    has_segments = (
        segments_dir.is_dir()
        and any(segments_dir.glob("*_vo.mp3"))
    )

    if has_segments and not merged_vo.exists():
        manifest.update_post_production(status="merging_audio")
        logger.info("Merging per-scene audio segments...")
        merge_voiceover(production_dir)
        result_whisper = merge_whisper(production_dir)
        seg_count = len(list(segments_dir.glob("*_vo.mp3")))
        logger.info("Merged %d voiceover segments into audio/voiceover.mp3", seg_count)
    elif not has_segments and not merged_vo.exists():
        logger.warning(
            "No voiceover segments or merged file found in %s — "
            "voiceover may not be needed for this format",
            prod_path / "audio",
        )
    else:
        logger.info("Merged voiceover already exists, skipping merge step")

    # Step 1: Generate EDL
    manifest.update_post_production(status="generating_edl")
    logger.info("Generating EDL...")
    edl = generate_edl(_manifest_path, _audio_design_path, _whisper_path)
    # Validate EDL schema before writing
    validate_edl_schema(edl)

    edl_path = str(prod_path / "state" / "edl.json")
    with open(edl_path, "w") as f:
        json.dump(edl, f, indent=2)
    manifest.update_post_production(edl_path="state/edl.json", edl_version=edl["meta"]["version"])
    logger.info("EDL written to %s", edl_path)

    # Step 2: Preflight check
    manifest.update_post_production(status="preflight")
    logger.info("Running pre-flight check...")
    result = preflight_check(edl, production_dir)

    if result.errors:
        logger.error("Pre-flight FAILED with %d errors:", len(result.errors))
        for err in result.errors:
            logger.error("  - %s", err)
        manifest.update_post_production(status="preflight_failed")
        return False

    if result.warnings:
        logger.warning("Pre-flight passed with %d warnings:", len(result.warnings))
        for warn in result.warnings:
            logger.warning("  - %s", warn)

    # Step 3: Setup symlinks
    link_dir = setup_symlinks(fmt, slug, production_dir)

    # Step 4: Render preview
    manifest.update_post_production(status="rendering_preview")
    version = get_next_version(production_dir, "preview")
    output_filename = f"preview_v{version}.mp4"
    output_path = str(prod_path / "video" / "final" / output_filename)

    render_start = time.time()
    success = render_composition(edl_path, output_path, quality="preview")
    render_duration = time.time() - render_start

    # Post-render dimension check (report-only per user decision)
    if success:
        target_w = edl.get("meta", {}).get("width", 1080)
        target_h = edl.get("meta", {}).get("height", 1920)
        check_post_render_dimensions(output_path, target_w, target_h)

    # Record timing
    manifest.update_post_production(
        render_timing={
            "started_at": datetime.fromtimestamp(render_start, tz=timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s": round(render_duration, 2),
        }
    )

    # Record preview version
    manifest.record_preview_version(
        version=version,
        path=f"video/final/{output_filename}",
        render_duration_s=round(render_duration, 2),
    )

    # Update status
    manifest.update_post_production(status="review")
    logger.info("Preview ready at %s. Review and provide feedback.", output_path)

    # Cleanup symlinks
    cleanup_symlinks(fmt, slug)

    return True


# ---------------------------------------------------------------------------
# Feedback + re-render
# ---------------------------------------------------------------------------

def apply_feedback_and_rerender(
    production_dir: str,
    feedback_text: str,
    changes: list[dict],
) -> str:
    """Apply feedback and optionally re-render.

    If any change has type "regen_clip", flags those scenes and pauses
    post-production without re-rendering.

    Args:
        production_dir: Path to production root.
        feedback_text: Human feedback text.
        changes: List of change dicts with 'type' and type-specific fields.

    Returns:
        Status message string.
    """
    prod_path = Path(production_dir)
    manifest_path = str(prod_path / "state" / "manifest.json")
    manifest = WorkflowManifest(manifest_path)

    # Check for regen_clip changes
    regen_scenes = [
        c["scene_id"] for c in changes if c.get("type") == "regen_clip"
    ]

    if regen_scenes:
        # Flag scenes for regeneration
        manifest.update_post_production(
            status="paused_for_regen",
            flagged_scenes=regen_scenes,
        )

        # Record feedback
        current_version = len(manifest.data.get("post_production", {}).get("preview_versions", []))
        manifest.record_feedback(
            version=current_version,
            feedback=feedback_text,
            changes_applied=[f"flagged_for_regen: {sid}" for sid in regen_scenes],
        )

        scene_list = ", ".join(regen_scenes)
        msg = f"Paused -- regenerate scenes {{{scene_list}}} then resume post-production"
        logger.info(msg)
        return msg

    # Non-regen changes: modify EDL and re-render
    edl_path = str(prod_path / "state" / "edl.json")
    non_regen_changes = [c for c in changes if c.get("type") != "regen_clip"]
    modify_edl(edl_path, non_regen_changes)

    fmt = manifest.data.get("format", "vsl")
    slug = manifest.data.get("slug", "untitled")

    # Record feedback
    current_version = len(manifest.data.get("post_production", {}).get("preview_versions", []))
    manifest.record_feedback(
        version=current_version,
        feedback=feedback_text,
        changes_applied=[f"{c['type']}" for c in non_regen_changes],
    )

    # Setup symlinks and re-render
    link_dir = setup_symlinks(fmt, slug, production_dir)

    version = get_next_version(production_dir, "preview")
    output_filename = f"preview_v{version}.mp4"
    output_path = str(prod_path / "video" / "final" / output_filename)

    manifest.update_post_production(status="rendering_preview")
    render_start = time.time()
    success = render_composition(edl_path, output_path, quality="preview")
    render_duration = time.time() - render_start

    manifest.record_preview_version(
        version=version,
        path=f"video/final/{output_filename}",
        render_duration_s=round(render_duration, 2),
    )
    manifest.update_post_production(status="review")

    cleanup_symlinks(fmt, slug)

    msg = f"Re-rendered preview v{version} at {output_path}"
    logger.info(msg)
    return msg


# ---------------------------------------------------------------------------
# Final render
# ---------------------------------------------------------------------------

def render_final(production_dir: str) -> bool:
    """Render at final quality and upload to Supabase Storage.

    Args:
        production_dir: Path to production root.

    Returns:
        True if render and upload succeeded.
    """
    prod_path = Path(production_dir)
    manifest_path = str(prod_path / "state" / "manifest.json")
    manifest = WorkflowManifest(manifest_path)

    fmt = manifest.data.get("format", "vsl")
    slug = manifest.data.get("slug", "untitled")

    edl_path = str(prod_path / "state" / "edl.json")

    # Setup symlinks
    link_dir = setup_symlinks(fmt, slug, production_dir)

    # Determine output filename
    version = get_next_version(production_dir, "final")
    output_filename = f"{slug}_{fmt}_v{version}.mp4"
    output_path = str(prod_path / "video" / "final" / output_filename)

    # Render
    manifest.update_post_production(status="rendering_final")
    render_start = time.time()
    success = render_composition(edl_path, output_path, quality="final")
    render_duration = time.time() - render_start

    # Mark final approved
    manifest.mark_final_approved(
        version=version,
        path=f"video/final/{output_filename}",
        render_duration_s=round(render_duration, 2),
    )

    # Cleanup symlinks
    cleanup_symlinks(fmt, slug)

    # Upload via DashboardSync
    sync = DashboardSync()
    uploaded = False

    if sync.enabled:
        production_id = DashboardSync._production_id(fmt, slug)
        upload_url = sync.upload_final_video(production_id, output_path, version)
        if upload_url:
            sync.push_video_version(production_id, {
                "version": version,
                "quality": "final",
                "is_approved": True,
                "path": output_path,
            })
            uploaded = True
            logger.info("Final video uploaded: %s", upload_url)
        else:
            logger.warning("Final video upload failed or returned None")
    else:
        logger.info("Dashboard sync disabled, skipping upload")

    manifest.update_post_production(final_uploaded=uploaded)

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point for post-production orchestrator."""
    parser = argparse.ArgumentParser(description="Post-production orchestrator")
    parser.add_argument("production_dir", help="Path to production directory")
    parser.add_argument("--final", action="store_true", help="Render at final quality")
    parser.add_argument("--rerender", action="store_true", help="Re-render from existing EDL")
    parser.add_argument("--manifest", help="Override manifest path")
    parser.add_argument("--audio-design", help="Override audio_design path")
    parser.add_argument("--whisper", help="Override whisper path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.final:
        success = render_final(args.production_dir)
    elif args.rerender:
        # Re-render from existing EDL (skip EDL generation)
        prod_path = Path(args.production_dir)
        edl_path = str(prod_path / "state" / "edl.json")
        version = get_next_version(args.production_dir, "preview")
        output_path = str(prod_path / "video" / "final" / f"preview_v{version}.mp4")
        success = render_composition(edl_path, output_path, quality="preview")
    else:
        success = run_post_production(
            args.production_dir,
            manifest_path=args.manifest,
            audio_design_path=args.audio_design,
            whisper_path=args.whisper,
        )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
