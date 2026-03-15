#!/usr/bin/env python3
"""
Kling API Rate Limit Calibration Script

Discovers UseAPI.net/Kling rate limit thresholds by running batches at increasing
concurrency levels and recording success rates, response times, and 429 error counts.

Usage:
    python scripts/calibrate_kling.py --dry-run --clips 4 --output-dir /tmp/calibration
    python scripts/calibrate_kling.py --clips 20 --output-dir /tmp/calibration

Concurrency levels tested: 1, 2, 3, 5 workers.
Default: 5 clips per level (20 total).
Results written to config/rate_limits.json.
"""

import argparse
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from video.kling.api_client import KlingClient
from video.kling.manifest import BatchManifest, HeartbeatWriter, ClipStatus

# Calibration config
CONCURRENCY_LEVELS = [1, 2, 3, 5]
CONFIG_PATH = PROJECT_ROOT / "config" / "rate_limits.json"

# Minimal test image: 64x64 solid blue PNG (base64-decoded at runtime)
# This keeps calibration cost minimal
CALIBRATION_PROMPT = "Gentle camera push forward, subtle ambient light shift, minimal motion"
CALIBRATION_NEGATIVE = "text, watermarks, logos, fast motion, dramatic changes"


def _create_test_image():
    """Create a minimal test PNG image (64x64 blue) for calibration."""
    try:
        from PIL import Image
        import io
        img = Image.new("RGB", (64, 64), color=(40, 60, 120))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        # Fallback: minimal valid 1x1 PNG
        import base64
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQAB"
            "Nl7BcQAAAABJRU5ErkJggg=="
        )


def _generate_calibration_clip(client, clip_id, output_dir):
    """Submit a single calibration clip and measure timing.

    Returns dict with success, elapsed_seconds, error_429, error_other.
    """
    output_path = output_dir / f"calibration_{clip_id}.mp4"
    image_bytes = _create_test_image()
    start = time.time()
    result = {
        "clip_id": clip_id,
        "success": False,
        "elapsed_seconds": 0,
        "error_429": False,
        "error_other": None,
    }

    try:
        client.image_to_video(
            image_bytes=image_bytes,
            prompt=CALIBRATION_PROMPT,
            output_path=str(output_path),
            negative_prompt=CALIBRATION_NEGATIVE,
            cfg_scale=0.4,
            duration=5,
            mode="std",
        )
        result["success"] = True
        result["elapsed_seconds"] = int(time.time() - start)
    except Exception as e:
        result["elapsed_seconds"] = int(time.time() - start)
        error_str = str(e).lower()
        if "429" in error_str or "too many" in error_str or "rate limit" in error_str:
            result["error_429"] = True
        else:
            result["error_other"] = str(e)

    return result


def _run_level(client, concurrency, clips_per_level, output_dir, level_num):
    """Run calibration at a specific concurrency level."""
    print(f"\n  Level {level_num}: {concurrency} concurrent workers, {clips_per_level} clips", flush=True)
    level_dir = output_dir / f"level_{concurrency}"
    level_dir.mkdir(parents=True, exist_ok=True)

    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {}
        for i in range(clips_per_level):
            clip_id = f"L{concurrency}_C{i+1:02d}"
            future = executor.submit(_generate_calibration_clip, client, clip_id, level_dir)
            futures[future] = clip_id
            time.sleep(1)  # Stagger submissions slightly

        for future in as_completed(futures):
            clip_id = futures[future]
            try:
                result = future.result()
            except Exception as e:
                result = {
                    "clip_id": clip_id, "success": False,
                    "elapsed_seconds": 0, "error_429": False, "error_other": str(e)
                }
            results.append(result)
            status = "OK" if result["success"] else ("429" if result["error_429"] else "FAIL")
            print(f"    {clip_id}: {status} ({result['elapsed_seconds']}s)", flush=True)

    # Compute level stats
    successes = sum(1 for r in results if r["success"])
    errors_429 = sum(1 for r in results if r["error_429"])
    elapsed_values = [r["elapsed_seconds"] for r in results if r["success"]]
    avg_time = sum(elapsed_values) / len(elapsed_values) if elapsed_values else 0
    success_rate = successes / len(results) if results else 0

    stats = {
        "success_rate": round(success_rate, 2),
        "avg_time_seconds": round(avg_time),
        "errors_429": errors_429,
        "total_clips": len(results),
        "successes": successes,
    }

    print(f"    Result: {success_rate:.0%} success, {errors_429} x 429, avg {avg_time:.0f}s", flush=True)
    return stats


def _select_optimal(results):
    """Select optimal concurrency: highest level with >= 95% success and <= 1 429 errors."""
    optimal = 1
    for level_str, stats in sorted(results.items(), key=lambda x: int(x[0])):
        if stats["success_rate"] >= 0.95 and stats["errors_429"] <= 1:
            optimal = int(level_str)
    return optimal


def _write_config(results, optimal_concurrent):
    """Write calibration results to config/rate_limits.json."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "calibrated": True,
        "calibrated_at": datetime.now(timezone.utc).isoformat(),
        "max_concurrent": optimal_concurrent,
        "submission_delay_seconds": 3,
        "results": results,
    }
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
    print(f"\n  Config written: {CONFIG_PATH}", flush=True)
    print(f"  Optimal concurrency: {optimal_concurrent}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Kling API rate limit calibration")
    parser.add_argument("--clips", type=int, default=20,
                        help="Total clips to generate (split across concurrency levels, default: 20)")
    parser.add_argument("--output-dir", type=str, default="/tmp/kling_calibration",
                        help="Directory for calibration outputs")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate setup without calling APIs")
    parser.add_argument("--keep-files", action="store_true",
                        help="Keep calibration video files (default: clean up)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    clips_per_level = max(1, args.clips // len(CONCURRENCY_LEVELS))
    total_clips = clips_per_level * len(CONCURRENCY_LEVELS)

    print(f"{'='*60}", flush=True)
    print(f"KLING RATE LIMIT CALIBRATION", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  Total clips:      {total_clips}", flush=True)
    print(f"  Clips per level:  {clips_per_level}", flush=True)
    print(f"  Concurrency levels: {CONCURRENCY_LEVELS}", flush=True)
    print(f"  Output dir:       {output_dir}", flush=True)
    print(f"  Config path:      {CONFIG_PATH}", flush=True)

    # Initialize client (validates credentials)
    try:
        client = KlingClient()
        print(f"  Backend:          {'UseAPI.net proxy' if client.use_proxy else 'Direct Kling API'}", flush=True)
    except Exception as e:
        print(f"\n  ERROR: Failed to initialize KlingClient: {e}", flush=True)
        print(f"  Set KLING_USE_PROXY=true and USEAPI_KEY in .env for proxy mode", flush=True)
        print(f"  Or set KLING_ACCESS_KEY and KLING_SECRET_KEY for direct mode", flush=True)
        sys.exit(1)

    # Create batch manifest for tracking
    scenes = [
        {"scene": f"cal_{i+1:02d}", "name": f"calibration_{i+1:02d}"}
        for i in range(total_clips)
    ]
    manifest_path = output_dir / "calibration_manifest.json"
    manifest = BatchManifest.create(
        batch_id=f"calibration-{int(time.time())}",
        format="calibration",
        clips=scenes,
        config={"type": "rate_limit_calibration", "levels": CONCURRENCY_LEVELS},
        path=str(manifest_path),
    )
    print(f"  Manifest:         {manifest_path}", flush=True)

    if args.dry_run:
        print(f"\n  DRY RUN -- setup validated successfully", flush=True)
        print(f"\n  Would run calibration:", flush=True)
        for level in CONCURRENCY_LEVELS:
            print(f"    Level {level}: {clips_per_level} clips at {level} concurrent workers", flush=True)
        print(f"\n  KlingClient initialized: OK", flush=True)
        print(f"  BatchManifest created: OK ({len(scenes)} clips)", flush=True)
        print(f"  Config will be written to: {CONFIG_PATH}", flush=True)

        # Clean up dry-run manifest
        if manifest_path.exists():
            manifest_path.unlink()
        return

    # Run calibration levels
    print(f"\n{'='*60}", flush=True)
    print(f"RUNNING CALIBRATION", flush=True)
    print(f"{'='*60}", flush=True)

    all_results = {}
    with HeartbeatWriter(manifest, interval=30):
        for i, concurrency in enumerate(CONCURRENCY_LEVELS, 1):
            stats = _run_level(client, concurrency, clips_per_level, output_dir, i)
            all_results[str(concurrency)] = stats

    # Select optimal and write config
    optimal = _select_optimal(all_results)
    _write_config(all_results, optimal)

    # Clean up calibration files
    if not args.keep_files:
        for level in CONCURRENCY_LEVELS:
            level_dir = output_dir / f"level_{level}"
            if level_dir.exists():
                shutil.rmtree(level_dir)
        print(f"  Calibration files cleaned up", flush=True)

    # Summary
    print(f"\n{'='*60}", flush=True)
    print(f"CALIBRATION COMPLETE", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  Optimal concurrency: {optimal} workers", flush=True)
    print(f"  Config: {CONFIG_PATH}", flush=True)
    for level_str, stats in sorted(all_results.items(), key=lambda x: int(x[0])):
        print(f"    {level_str} workers: {stats['success_rate']:.0%} success, "
              f"{stats['errors_429']} x 429, avg {stats['avg_time_seconds']}s", flush=True)


if __name__ == "__main__":
    main()
