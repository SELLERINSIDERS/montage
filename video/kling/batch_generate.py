#!/usr/bin/env python3
"""
Kling AI Batch Image-to-Video Generator (Sequential)

Reads a JSON manifest of scenes and generates videos for each one sequentially.
Uses KlingClient for API calls and BatchManifest for crash-resume tracking.

Usage:
    python video/kling/batch_generate.py <manifest.json>
    python video/kling/batch_generate.py <manifest.json> --start 3   # resume from scene 3
    python video/kling/batch_generate.py <manifest.json> --mode pro  # use pro mode
    python video/kling/batch_generate.py <manifest.json> --output <dir>

Manifest format (JSON array):
[
    {
        "scene": "01",
        "name": "alexandria_harbor",
        "image": "~/Downloads/Scene_1.png",
        "prompt": "Slow aerial dolly forward over the harbor...",
        "duration": "5",
        "negative_prompt": "text, words, logos, watermarks, blurry, distorted"
    },
    ...
]

Optional fields per scene (with defaults):
    "duration": "5"
    "aspect_ratio": "9:16"
    "mode": "std"
    "cfg_scale": 0.4
    "negative_prompt": (uses DEFAULT_NEGATIVE_PROMPT if omitted)
"""

import time
import json
import logging
import os
import sys
import base64
import argparse
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image
import io

from video.kling.api_client import KlingClient
from video.kling.manifest import BatchManifest, HeartbeatWriter, ClipStatus
from video.kling.schema_validation import validate_manifest
from scripts.apply_sfx_to_clips import apply_sfx as apply_sfx_to_clip
from scripts.dashboard_sync import DashboardSync
from scripts.workflow_manifest import WorkflowManifest

load_dotenv(Path(__file__).parent.parent.parent / ".env")

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────
DEFAULT_NEGATIVE_PROMPT = (
    "text, words, letters, logos, watermarks, UI elements, buttons, overlays, "
    "modern clothing in historical scenes, anachronistic objects, "
    "cartoonish, illustrated style, blurry, distorted"
)

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "kling" / "clips"


def _derive_format_slug(manifest_path: str) -> tuple[str, str]:
    """Derive production format and slug from manifest path."""
    parts = Path(manifest_path).resolve().parts
    for i, part in enumerate(parts):
        if part in ('vsl', 'ads', 'ugc'):
            return part, parts[i + 1] if i + 1 < len(parts) else 'unknown'
    return 'unknown', 'unknown'


def _load_audio_design(project_dir: str) -> dict | None:
    """Load audio_design.json from project manifest directory.

    Returns None if not found (graceful degradation -- audio will be skipped).
    """
    if not project_dir:
        return None
    path = Path(project_dir) / "manifest" / "audio_design.json"
    if not path.exists():
        logger.warning("audio_design.json not found at %s -- skipping Kling audio", path)
        return None
    with open(path) as f:
        data = json.load(f)
    # Normalize: audio_design may have top-level "scenes" dict or be flat
    if "scenes" in data:
        return data["scenes"]
    return data


def _apply_kling_audio(client, scene_num, video_url, output_path, manifest, audio_design):
    """Attempt Kling add_sound() for a scene, fallback to SFX on failure.

    Args:
        client: KlingClient instance.
        scene_num: Scene number string (e.g. "01").
        video_url: CDN URL of the generated video.
        output_path: Where to save the audio-enhanced video.
        manifest: BatchManifest for tracking.
        audio_design: Dict of scene audio classifications, or None to skip.
    """
    if audio_design is None:
        return

    scene_key = f"scene_{int(scene_num):02d}"
    scene_info = audio_design.get(scene_key)
    if scene_info is None:
        return

    classification = scene_info.get("type", "silent")
    if classification == "silent":
        return

    if not client.use_proxy:
        return  # add_sound is proxy-only

    try:
        audio_path = client.add_sound(video_url, output_path)
        manifest.increment_api_usage("kling_audio", 1)
        manifest.update_clip(scene_num, kling_audio_path=str(audio_path))
    except Exception as e:
        logger.warning("add_sound failed for scene %s: %s -- falling back to SFX", scene_num, e)
        manifest.update_clip(scene_num, kling_audio_fallback="sfx", kling_audio_error=str(e))
        # Invoke SFX library as fallback — derive original clip path from audio output path
        original_clip = Path(str(output_path).replace("_with_audio.mp4", ".mp4"))
        try:
            apply_sfx_to_clip(scene_key, scene_info, original_clip)
        except Exception as sfx_err:
            logger.warning("SFX fallback also failed for scene %s: %s", scene_num, sfx_err)


def _get_review_feedback(scene: dict) -> str | None:
    """Extract review feedback for a scene from any flagged gate.

    Checks all gates in the scene and returns the first review_feedback
    string found on a flagged gate.

    Args:
        scene: Scene dict from the workflow manifest.

    Returns:
        Review feedback string or None if no feedback found.
    """
    for gate_type, gate_data in scene.get("gates", {}).items():
        fb = gate_data.get("review_feedback")
        if fb and gate_data.get("status") == "flagged":
            return fb
    return None


def encode_image(image_path):
    """Encode image as raw bytes (no JPEG compression -- preserves full quality)."""
    img = Image.open(image_path)
    if img.mode == "RGBA":
        img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw_bytes = buf.getvalue()
    else:
        raw_bytes = image_path.read_bytes()

    return raw_bytes


def generate_scene(client, scene, output_dir, manifest, mode_override=None,
                    sync=None, format_type=None, slug=None, audio_design=None):
    """Generate a single scene video via KlingClient. Returns output path or None."""
    scene_num = scene["scene"]
    name = scene["name"]
    image_path = Path(os.path.expanduser(scene["image"]))
    prompt = scene["prompt"]
    duration = scene.get("duration", "5")
    mode = mode_override or scene.get("mode", "std")
    cfg_scale = scene.get("cfg_scale", 0.4)
    negative_prompt = scene.get("negative_prompt", DEFAULT_NEGATIVE_PROMPT)

    print(f"\n{'='*60}", flush=True)
    print(f"SCENE {scene_num}: {name}", flush=True)
    print(f"{'='*60}", flush=True)

    # Validate
    if not image_path.exists():
        print(f"  Image not found: {image_path}", flush=True)
        manifest.update_clip(scene_num, status=ClipStatus.FAILED.value,
                             error_reason=f"Image not found: {image_path}")
        return None

    size_mb = image_path.stat().st_size / (1024 * 1024)
    if size_mb > 10:
        print(f"  Image too large: {size_mb:.1f} MB", flush=True)
        manifest.update_clip(scene_num, status=ClipStatus.FAILED.value,
                             error_reason=f"Image too large: {size_mb:.1f} MB")
        return None

    # Encode
    image_bytes = encode_image(image_path)
    print(f"  Image: {image_path.name} ({size_mb:.1f} MB)", flush=True)

    # Incorporate review feedback into prompt for flagged scenes
    review_feedback = _get_review_feedback(scene)
    if review_feedback:
        prompt = f"{prompt}\n\n{review_feedback}"
        logger.info("Incorporating review feedback for scene %s", scene_num)

    # Update manifest to SUBMITTED
    manifest.update_clip(scene_num, status=ClipStatus.SUBMITTED.value,
                         submit_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    # Submit + poll + download via KlingClient
    print(f"\n  Prompt: {prompt[:100]}...", flush=True)
    print(f"  Duration: {duration}s, Mode: {mode}", flush=True)

    start_time = time.time()
    try:
        out_path = output_dir / f"scene_{scene_num}_{name}.mp4"
        result_path = client.image_to_video(
            image_bytes=image_bytes,
            prompt=prompt,
            output_path=str(out_path),
            negative_prompt=negative_prompt,
            cfg_scale=cfg_scale,
            duration=int(duration) if isinstance(duration, str) else duration,
            mode=mode,
        )
        elapsed = int(time.time() - start_time)
        total_mb = out_path.stat().st_size / (1024 * 1024)
        print(f"  Downloaded: {total_mb:.1f} MB ({elapsed}s) -> {result_path}", flush=True)

        # Capture video URL from client for add_sound() consumption
        video_url = getattr(client, "last_video_url", None)

        manifest.update_clip(scene_num, status=ClipStatus.SUCCEEDED.value,
                             output_path=str(result_path),
                             video_url=video_url,
                             complete_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                             elapsed_seconds=elapsed)

        # Apply Kling AI audio (add_sound) for non-silent scenes
        if audio_design and video_url:
            audio_out = output_dir / f"scene_{scene_num}_{name}_with_audio.mp4"
            _apply_kling_audio(client, scene_num, video_url, str(audio_out),
                               manifest, audio_design)

        # Dashboard sync -- upload completed clip and push scene update
        if sync and sync.enabled:
            storage_path = f"{format_type}/{slug}/video/clips/{os.path.basename(str(result_path))}"
            sync.upload_asset(str(result_path), storage_path)
            # Generate and upload thumbnail
            thumb_local = str(result_path).replace('.mp4', '_thumb.jpg')
            thumb_storage = None
            if sync.generate_thumbnail(str(result_path), thumb_local):
                thumb_storage = storage_path.replace('.mp4', '_thumb.jpg')
                sync.upload_asset(thumb_local, thumb_storage)
            # Push scene status update
            production_id = DashboardSync._production_id(format_type, slug)
            sync.push_scene_update(production_id, scene_num, {
                'video_status': 'completed',
                'video_storage_path': storage_path,
                'thumbnail_storage_path': thumb_storage,
            })

        return result_path
    except Exception as e:
        elapsed = int(time.time() - start_time)
        print(f"  Failed: {e} ({elapsed}s)", flush=True)
        manifest.update_clip(scene_num, status=ClipStatus.FAILED.value,
                             error_reason=str(e),
                             complete_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                             elapsed_seconds=elapsed)
        return None


def _load_or_create_manifest(scenes, output_dir, batch_manifest_path, start_from=1):
    """Load existing manifest for resume, or create a new one.

    If --start is specified and no manifest exists, create manifest
    with clips before start_from pre-marked as SUCCEEDED.
    """
    if batch_manifest_path.exists():
        print(f"  Resuming from manifest: {batch_manifest_path}", flush=True)
        return BatchManifest.load(str(batch_manifest_path))

    # Create a new manifest
    batch_id = f"batch-{int(time.time())}"
    config = {"generator": "batch_generate", "output_dir": str(output_dir)}
    manifest = BatchManifest.create(
        batch_id=batch_id,
        format="vsl",
        clips=scenes,
        config=config,
        path=str(batch_manifest_path),
    )

    # If --start > 1, mark earlier clips as succeeded (assumed done)
    if start_from > 1:
        for i, clip in enumerate(manifest.clips, 1):
            if i < start_from:
                manifest.update_clip(clip["scene"], status=ClipStatus.SUCCEEDED.value,
                                     output_path="(pre-existing)")

    return manifest


def main():
    parser = argparse.ArgumentParser(description="Kling batch image-to-video generator")
    parser.add_argument("manifest", help="Path to JSON manifest file")
    parser.add_argument("--start", type=int, default=1, help="Start from scene N (1-indexed)")
    parser.add_argument("--mode", choices=["std", "pro"], help="Override mode for all scenes")
    parser.add_argument("--output", type=str, help="Custom output directory (default: video/output/kling/clips)")
    parser.add_argument("--batch-manifest", type=str, default=None,
                        help="Path to batch manifest file (default: {output_dir}/batch_manifest.json)")
    parser.add_argument("--project", type=str, default=None,
                        help="Project directory for audio_design.json (e.g. vsl/nightcap)")
    args = parser.parse_args()

    # Output directory
    output_dir = Path(args.output) if args.output else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}", flush=True)
        sys.exit(1)

    with open(manifest_path) as f:
        scenes = json.load(f)

    # Validate manifest schema
    validate_manifest(scenes)

    # Batch manifest path
    batch_manifest_path = Path(args.batch_manifest) if args.batch_manifest else output_dir / "batch_manifest.json"

    # Initialize KlingClient and DashboardSync
    client = KlingClient()
    sync = DashboardSync()
    format_type, slug = _derive_format_slug(args.manifest)

    # Bookend sync: pull dashboard decisions before batch
    wf_manifest_path = None
    if args.project:
        wf_manifest_path = Path(args.project) / "state" / "workflow-manifest.json"
        if wf_manifest_path.exists():
            try:
                wf = WorkflowManifest(str(wf_manifest_path))
                wf.sync_from_dashboard()
                print(f"  Synced dashboard decisions from {wf_manifest_path}", flush=True)
            except Exception as exc:
                print(f"  WARNING: sync_from_dashboard failed (continuing): {exc}", flush=True)
        else:
            print(f"  No workflow manifest at {wf_manifest_path} -- skipping dashboard sync", flush=True)

    # Parity gate -- block batch if image/prompt counts mismatch
    if args.project:
        from video.kling.parity_check import check_parity, ParityError
        try:
            check_parity(args.project)
            print("  Parity check passed", flush=True)
        except ParityError as e:
            logger.error("Parity check failed: %s", e)
            raise

    # Load audio design for Kling audio integration (once at batch start)
    audio_design = _load_audio_design(args.project)

    print(f"Loaded {len(scenes)} scenes from {manifest_path}", flush=True)
    print(f"  Output: {output_dir}", flush=True)
    print(f"  Backend: {'UseAPI.net proxy' if client.use_proxy else 'Direct Kling API'}", flush=True)
    if args.start > 1:
        print(f"  Starting from scene {args.start}", flush=True)
    if args.mode:
        print(f"  Mode override: {args.mode}", flush=True)

    # Load or create batch manifest
    batch_manifest = _load_or_create_manifest(scenes, output_dir, batch_manifest_path, args.start)

    # Get clips to process
    pending = batch_manifest.get_pending_clips()
    resumable = batch_manifest.get_resumable_clips()
    succeeded = [c for c in batch_manifest.clips if c["status"] == ClipStatus.SUCCEEDED.value]
    print(f"\n  Already succeeded: {len(succeeded)}", flush=True)
    print(f"  Resumable (re-poll): {len(resumable)}", flush=True)
    print(f"  Pending: {len(pending)}", flush=True)

    # Dashboard heartbeat at batch start
    if sync.enabled:
        production_id = DashboardSync._production_id(format_type, slug)
        sync.push_heartbeat(production_id)

    if not pending and not resumable:
        print(f"\n  All {len(scenes)} scenes already completed. Nothing to do.", flush=True)
        return

    results = []
    with HeartbeatWriter(batch_manifest, interval=30):
        # Re-poll in-flight clips from prior crash
        if resumable:
            print(f"\n{'='*60}", flush=True)
            print(f"RE-POLLING {len(resumable)} IN-FLIGHT CLIPS", flush=True)
            print(f"{'='*60}\n", flush=True)
            for clip in resumable:
                scene_data = next((s for s in scenes if s["scene"] == clip["scene"]), None)
                if not scene_data:
                    continue
                out_path = output_dir / f"scene_{clip['scene']}_{clip['name']}.mp4"
                try:
                    result_path = client.poll_existing_task(clip["task_id"], str(out_path))
                    batch_manifest.update_clip(clip["scene"],
                        status=ClipStatus.SUCCEEDED.value,
                        output_path=str(result_path),
                        complete_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                    print(f"  Re-polled scene {clip['scene']}: {clip['name']} -> {result_path}", flush=True)
                except Exception as e:
                    batch_manifest.update_clip(clip["scene"],
                        status=ClipStatus.FAILED.value,
                        error_reason=f"Re-poll failed: {e}",
                        complete_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                    print(f"  Re-poll failed scene {clip['scene']}: {clip['name']} -> {e}", flush=True)

        for clip in pending:
            scene_data = next((s for s in scenes if s["scene"] == clip["scene"]), None)
            if not scene_data:
                continue

            output = generate_scene(client, scene_data, output_dir, batch_manifest,
                                    mode_override=args.mode, sync=sync,
                                    format_type=format_type, slug=slug,
                                    audio_design=audio_design)
            results.append({
                "scene": scene_data["scene"],
                "name": scene_data["name"],
                "status": "success" if output else "failed",
                "output": str(output) if output else None,
            })

            # Rate limit between scenes
            if clip != pending[-1]:
                print(f"\n  Waiting 5s before next scene...", flush=True)
                time.sleep(5)

    # Summary
    print(f"\n{'='*60}", flush=True)
    print(f"BATCH COMPLETE", flush=True)
    print(f"{'='*60}", flush=True)
    success = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failed")
    print(f"  Success: {success}", flush=True)
    print(f"  Failed: {failed}", flush=True)
    for r in results:
        icon = "OK" if r["status"] == "success" else "FAIL"
        print(f"  {icon} Scene {r['scene']}: {r['name']} -> {r['output'] or 'FAILED'}", flush=True)

    print(f"\n  Batch manifest: {batch_manifest_path}", flush=True)
    print(f"  Complete: {batch_manifest.is_complete()}", flush=True)

    # Dashboard sync -- push workflow manifest (not batch manifest) and bookend sync
    if sync.enabled:
        if wf_manifest_path and wf_manifest_path.exists():
            try:
                sync.push_manifest(str(wf_manifest_path))
            except Exception as exc:
                print(f"  WARNING: push_manifest failed (continuing): {exc}", flush=True)
            try:
                wf = WorkflowManifest(str(wf_manifest_path))
                wf.sync_from_dashboard()
            except Exception as exc:
                print(f"  WARNING: post-batch sync_from_dashboard failed (continuing): {exc}", flush=True)
        else:
            print(f"  WARNING: No workflow manifest -- skipping push_manifest", flush=True)
        sync.push_heartbeat(DashboardSync._production_id(format_type, slug))


if __name__ == "__main__":
    main()
