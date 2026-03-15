#!/usr/bin/env python3
"""
Kling AI Concurrent Batch Image-to-Video Generator

Generates multiple Kling video clips concurrently using ThreadPoolExecutor.
Uses KlingClient for API calls and BatchManifest for crash-resume tracking.

Usage:
    python video/kling/batch_generate_concurrent.py <manifest.json> --output <dir> --workers 3
    python video/kling/batch_generate_concurrent.py <manifest.json> --output <dir> --mode pro
    python video/kling/batch_generate_concurrent.py <manifest.json> --output <dir> --dry-run
    python video/kling/batch_generate_concurrent.py <manifest.json> --output <dir> --resume
"""

import time
import json
import os
import sys
import base64
import argparse
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from PIL import Image
import io

from video.kling.api_client import KlingClient
from video.kling.manifest import BatchManifest, HeartbeatWriter, ClipStatus
from video.kling.schema_validation import validate_manifest
from scripts.dashboard_sync import DashboardSync

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# ── Config ──────────────────────────────────────────────
DEFAULT_NEGATIVE_PROMPT = (
    "text, words, letters, logos, watermarks, UI elements, buttons, overlays, "
    "modern clothing in historical scenes, anachronistic objects, "
    "cartoonish, illustrated style, blurry, distorted, morphing faces, identity shift"
)

MIN_VIDEO_SIZE = 500_000  # 500KB — valid videos are typically 2-10MB
SUBMISSION_DELAY = 3  # seconds between submitting scenes to API


def _derive_format_slug(manifest_path: str) -> tuple[str, str]:
    """Derive production format and slug from manifest path."""
    parts = Path(manifest_path).resolve().parts
    for i, part in enumerate(parts):
        if part in ('vsl', 'ads', 'ugc'):
            return part, parts[i + 1] if i + 1 < len(parts) else 'unknown'
    return 'unknown', 'unknown'

# Thread-safe print lock
print_lock = threading.Lock()


def tprint(msg):
    """Thread-safe print with flush."""
    with print_lock:
        print(msg, flush=True)


def encode_image(image_path):
    """Encode image as raw base64 PNG (no JPEG compression)."""
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
                    sync=None, format_type=None, slug=None):
    """Generate a single scene video via KlingClient. Thread-safe, self-contained."""
    scene_num = scene["scene"]
    name = scene["name"]
    label = f"Scene {scene_num}"
    image_path = Path(os.path.expanduser(scene["image"]))
    prompt = scene["prompt"]
    duration = scene.get("duration", "5")
    mode = mode_override or scene.get("mode", "std")
    cfg_scale = scene.get("cfg_scale", 0.4)
    negative_prompt = scene.get("negative_prompt", DEFAULT_NEGATIVE_PROMPT)

    out_path = output_dir / f"scene_{scene_num}_{name}.mp4"
    start_time = time.time()

    # Validate image
    if not image_path.exists():
        tprint(f"  [{label}] FAIL -- image not found: {image_path}")
        manifest.update_clip(scene_num, status=ClipStatus.FAILED.value,
                             error_reason=f"Image not found: {image_path}")
        return {
            "scene": scene_num, "name": name, "status": "failed",
            "error": f"Image not found: {image_path}", "elapsed": 0
        }

    size_mb = image_path.stat().st_size / (1024 * 1024)
    if size_mb > 10:
        tprint(f"  [{label}] FAIL -- image too large: {size_mb:.1f} MB")
        manifest.update_clip(scene_num, status=ClipStatus.FAILED.value,
                             error_reason=f"Image too large: {size_mb:.1f} MB")
        return {
            "scene": scene_num, "name": name, "status": "failed",
            "error": f"Image too large: {size_mb:.1f} MB", "elapsed": 0
        }

    # Encode
    tprint(f"  [{label}] Encoding {image_path.name} ({size_mb:.1f} MB)...")
    image_bytes = encode_image(image_path)

    # Update manifest to SUBMITTED
    manifest.update_clip(scene_num, status=ClipStatus.SUBMITTED.value,
                         submit_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    # Submit + poll + download via KlingClient
    tprint(f"  [{label}] Submitting: {duration}s, {mode}, prompt: {prompt[:80]}...")

    try:
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
        tprint(f"  [{label}] OK -- {total_mb:.1f} MB ({elapsed}s)")

        manifest.update_clip(scene_num, status=ClipStatus.SUCCEEDED.value,
                             output_path=str(result_path),
                             complete_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                             elapsed_seconds=elapsed)

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

        return {
            "scene": scene_num, "name": name, "status": "success",
            "output": str(result_path), "elapsed": elapsed, "size_mb": round(total_mb, 1)
        }
    except Exception as e:
        elapsed = int(time.time() - start_time)
        tprint(f"  [{label}] FAIL -- {e} ({elapsed}s)")
        manifest.update_clip(scene_num, status=ClipStatus.FAILED.value,
                             error_reason=str(e),
                             complete_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                             elapsed_seconds=elapsed)
        return {
            "scene": scene_num, "name": name, "status": "failed",
            "error": str(e), "elapsed": elapsed
        }


def _load_or_create_manifest(scenes, output_dir, batch_manifest_path):
    """Load existing manifest for resume, or create a new one."""
    if batch_manifest_path.exists():
        tprint(f"  Resuming from manifest: {batch_manifest_path}")
        return BatchManifest.load(str(batch_manifest_path))

    # Create a new manifest
    batch_id = f"batch-{int(time.time())}"
    config = {"generator": "batch_generate_concurrent", "output_dir": str(output_dir)}
    return BatchManifest.create(
        batch_id=batch_id,
        format="vsl",
        clips=scenes,
        config=config,
        path=str(batch_manifest_path),
    )


def main():
    parser = argparse.ArgumentParser(description="Kling concurrent batch image-to-video generator")
    parser.add_argument("manifest", help="Path to JSON manifest file")
    parser.add_argument("--output", type=str, default="video/output/kling/clips",
                        help="Output directory for generated videos")
    parser.add_argument("--workers", type=int, default=3, help="Max concurrent workers (default: 3)")
    parser.add_argument("--mode", choices=["std", "pro"], help="Override mode for all scenes")
    parser.add_argument("--dry-run", action="store_true", help="List scenes without generating")
    parser.add_argument("--batch-manifest", type=str, default=None,
                        help="Path to batch manifest file (default: {output_dir}/batch_manifest.json)")
    args = parser.parse_args()

    output_dir = Path(args.output)
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

    # Parity gate -- block batch if image/prompt counts mismatch
    # Derive project_dir from manifest path (look for vsl/ads/ugc parent)
    manifest_parts = manifest_path.resolve().parts
    project_dir = None
    for i, part in enumerate(manifest_parts):
        if part in ('vsl', 'ads', 'ugc') and i + 1 < len(manifest_parts):
            project_dir = Path(*manifest_parts[:i + 2])
            break
    if project_dir and project_dir.exists():
        from video.kling.parity_check import check_parity, ParityError
        try:
            check_parity(project_dir)
            print("  Parity check passed", flush=True)
        except ParityError as e:
            print(f"  Parity check FAILED: {e}", flush=True)
            raise

    print(f"{'='*60}", flush=True)
    print(f"KLING CONCURRENT BATCH GENERATOR", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  Manifest: {manifest_path} ({len(scenes)} scenes)", flush=True)
    print(f"  Output:   {output_dir}", flush=True)
    print(f"  Workers:  {args.workers}", flush=True)
    print(f"  Mode:     {args.mode or 'per-scene (from manifest)'}", flush=True)
    print(f"  Backend:  {'UseAPI.net proxy' if client.use_proxy else 'Direct Kling API'}", flush=True)

    # Load or create batch manifest
    batch_manifest = _load_or_create_manifest(scenes, output_dir, batch_manifest_path)

    # Determine what needs work
    resumable = batch_manifest.get_resumable_clips()
    pending = batch_manifest.get_pending_clips()

    # Pre-scan for already-succeeded clips
    succeeded = [c for c in batch_manifest.clips if c["status"] == ClipStatus.SUCCEEDED.value]

    print(f"\n  Already succeeded: {len(succeeded)}", flush=True)
    print(f"  Resumable (re-poll): {len(resumable)}", flush=True)
    print(f"  Pending (submit):    {len(pending)}", flush=True)
    print(f"  Total:               {len(scenes)}", flush=True)

    # Dashboard heartbeat at batch start
    production_id = DashboardSync._production_id(format_type, slug) if sync.enabled else None
    if sync.enabled:
        sync.push_heartbeat(production_id)

    if args.dry_run:
        print(f"\n  DRY RUN -- would generate {len(pending)} scenes:", flush=True)
        for clip in pending:
            scene_data = next((s for s in scenes if s["scene"] == clip["scene"]), None)
            if scene_data:
                dur = scene_data.get("duration", "5")
                mode = args.mode or scene_data.get("mode", "std")
                img = Path(scene_data["image"]).name
                print(f"    Scene {clip['scene']:>3s}: {clip['name']:<35s} {dur}s {mode} <- {img}", flush=True)
        if resumable:
            print(f"\n  Would re-poll {len(resumable)} in-flight scenes", flush=True)
        if succeeded:
            print(f"\n  Would skip {len(succeeded)} already-succeeded scenes", flush=True)
        return

    to_process = pending
    if not to_process and not resumable:
        print(f"\n  All {len(scenes)} scenes already completed. Nothing to do.", flush=True)
        return

    all_results = []
    batch_start = time.time()

    # Dashboard event: batch started
    if sync.enabled:
        try:
            sync.push_generation_event(
                production_id, None, "video_batch_started",
                {"scene_count": len(to_process)},
            )
        except Exception as exc:
            tprint(f"  [DashboardSync] batch_started event failed: {exc}")

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

        # Generate with heartbeat
        print(f"\n{'='*60}", flush=True)
        print(f"GENERATING {len(to_process)} SCENES ({args.workers} concurrent)", flush=True)
        print(f"{'='*60}\n", flush=True)

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {}
            for clip in to_process:
                scene_data = next((s for s in scenes if s["scene"] == clip["scene"]), None)
                if scene_data:
                    future = executor.submit(generate_scene, client, scene_data,
                                             output_dir, batch_manifest, args.mode,
                                             sync=sync, format_type=format_type,
                                             slug=slug)
                    futures[future] = scene_data
                    time.sleep(SUBMISSION_DELAY)

            for future in as_completed(futures):
                scene_data = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = {
                        "scene": scene_data["scene"], "name": scene_data["name"],
                        "status": "failed", "error": str(e), "elapsed": 0
                    }

                all_results.append(result)

                # Progress
                done = len(all_results)
                total = len(to_process)
                elapsed_total = time.time() - batch_start
                avg = elapsed_total / done if done else 0
                remaining = total - done
                eta = (avg * remaining) / 60

                icon = {"success": "OK", "skipped": "SKIP", "failed": "FAIL"}.get(result["status"], "??")
                tprint(f"\n  [{done}/{total}] Scene {result['scene']}: {icon} ({result.get('elapsed', 0)}s) -- ETA: ~{eta:.0f}m")

    # Summary
    elapsed_total = time.time() - batch_start
    success = sum(1 for r in all_results if r["status"] == "success")
    failed = sum(1 for r in all_results if r["status"] == "failed")

    print(f"\n{'='*60}", flush=True)
    print(f"BATCH COMPLETE ({elapsed_total/60:.1f} minutes)", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  OK:      {success}", flush=True)
    print(f"  Skipped: {len(succeeded)}", flush=True)
    print(f"  Failed:  {failed}", flush=True)

    if failed:
        print(f"\n  Failed scenes:", flush=True)
        for r in all_results:
            if r["status"] == "failed":
                print(f"    Scene {r['scene']}: {r.get('error', 'unknown')}", flush=True)

    print(f"\n  Batch manifest: {batch_manifest_path}", flush=True)
    print(f"  Complete: {batch_manifest.is_complete()}", flush=True)

    # Dashboard sync -- push workflow manifest (not the kling scene manifest) and final heartbeat
    if sync.enabled:
        try:
            # Find the workflow manifest (not the kling scene manifest)
            workflow_manifest = None
            if project_dir and project_dir.exists():
                wm_path = project_dir / "state" / "workflow-manifest.json"
                if wm_path.exists():
                    workflow_manifest = str(wm_path)
            if workflow_manifest:
                sync.push_manifest(workflow_manifest)
            sync.push_heartbeat(production_id)
            sync.push_generation_event(
                production_id, None, "video_batch_completed",
                {
                    "success": success,
                    "failed": failed,
                    "elapsed_minutes": round(elapsed_total / 60, 1),
                },
            )
        except Exception as exc:
            tprint(f"  [DashboardSync] batch completion sync failed: {exc}")


if __name__ == "__main__":
    main()
