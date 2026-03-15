"""Regeneration queue poller daemon.

Polls the regeneration_queue table for pending jobs and dispatches them
to regenerate_scene.py for processing. Runs as a long-lived daemon with
configurable poll interval.

Uses DashboardSync.claim_regeneration_job() for optimistic locking --
safe to run multiple instances (only one will claim each job).

Usage:
    python scripts/job_poller.py                    # Poll every 10s (default)
    python scripts/job_poller.py --interval 5       # Poll every 5s
    python scripts/job_poller.py --once             # Single poll (for cron/testing)
    python scripts/job_poller.py --dry-run          # Show what would be claimed
"""

import argparse
import logging
import os
import signal
import socket
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Load project .env first, then optional EXTRA_ENV_FILE (e.g. for Supabase creds)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
_extra_env = os.environ.get("EXTRA_ENV_FILE", "")
if _extra_env and Path(_extra_env).exists():
    load_dotenv(Path(_extra_env), override=False)

from scripts.dashboard_sync import DashboardSync

logger = logging.getLogger(__name__)

# Worker ID = hostname:PID (unique per process, safe for multi-instance)
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"

# Graceful shutdown flag
_shutdown = False


def _handle_signal(signum, frame):
    """Set shutdown flag on SIGINT/SIGTERM for graceful exit."""
    global _shutdown
    _shutdown = True
    logger.info("Shutdown signal received, finishing current job...")


def _peek_pending(sync: DashboardSync, limit: int = 5) -> list[dict]:
    """Peek at pending jobs without claiming (for dry-run mode).

    Returns:
        List of pending job dicts, up to ``limit``.
    """
    result = (
        sync.client.table("regeneration_queue")
        .select("id, scene_id, gate_type, feedback_text, flag_reasons, created_at")
        .eq("status", "pending")
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return result.data or []


def _reap_stale_jobs(sync: DashboardSync, stale_minutes: int = 15) -> None:
    """Find and reset jobs stuck in 'claimed' or 'processing' state.

    Jobs older than ``stale_minutes`` are either reset to 'pending' (if under
    max_attempts) or marked 'failed' (if at or above max_attempts). The
    corresponding scene's asset_state is reset from 'regenerating' to 'flagged'.

    Args:
        sync: Active DashboardSync instance.
        stale_minutes: Minutes after which a claimed/processing job is stale.
    """
    if not sync.enabled:
        return

    try:
        from datetime import datetime, timedelta, timezone

        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
        ).isoformat()

        result = (
            sync.client.table("regeneration_queue")
            .select("id, scene_id, production_id, attempt_count, max_attempts, status")
            .in_("status", ["claimed", "processing"])
            .lt("updated_at", cutoff)
            .execute()
        )

        stale_jobs = result.data or []
        if not stale_jobs:
            return

        for job in stale_jobs:
            job_id = job["id"]
            scene_id = job["scene_id"]
            production_id = job["production_id"]
            attempt_count = job.get("attempt_count", 0)
            max_attempts = job.get("max_attempts", 3)

            if attempt_count >= max_attempts:
                # Exhausted retries -- mark as failed
                sync.client.table("regeneration_queue").update(
                    {"status": "failed", "error_message": "Stale job reaped: max attempts exceeded"}
                ).eq("id", job_id).execute()

                sync.push_scene_update(
                    production_id, scene_id, {"asset_state": "failed"}
                )
                logger.warning(
                    "Reaped stale job %s (scene=%s) -> failed (attempts=%d/%d)",
                    job_id, scene_id, attempt_count, max_attempts,
                )
            else:
                # Reset to pending for retry
                sync.client.table("regeneration_queue").update(
                    {"status": "pending", "claimed_by": None, "claimed_at": None}
                ).eq("id", job_id).execute()

                sync.push_scene_update(
                    production_id, scene_id, {"asset_state": "flagged"}
                )
                logger.warning(
                    "Reaped stale job %s (scene=%s) -> pending (attempts=%d/%d)",
                    job_id, scene_id, attempt_count, max_attempts,
                )

    except Exception as exc:
        logger.error("Stale job reaper error: %s", exc, exc_info=True)


def poll_once(sync: DashboardSync, dry_run: bool = False) -> bool:
    """Claim and process one regeneration job.

    In dry-run mode, prints pending jobs without claiming or processing.

    Args:
        sync: Active DashboardSync instance.
        dry_run: If True, peek only -- do not claim or dispatch.

    Returns:
        True if a job was found (and processed in normal mode), False if queue empty.
    """
    if dry_run:
        jobs = _peek_pending(sync)
        if jobs:
            for job in jobs:
                feedback_preview = (job.get("feedback_text") or "")[:60]
                print(
                    f"  [DRY RUN] Would claim: scene={job['scene_id']} "
                    f"gate={job['gate_type']} feedback={feedback_preview}"
                )
            return True
        print("  [DRY RUN] No pending jobs")
        return False

    # Normal mode: claim and dispatch
    job = sync.claim_regeneration_job(WORKER_ID)
    if job is None:
        return False

    logger.info(
        "Claimed job %s: scene=%s gate=%s",
        job["id"],
        job["scene_id"],
        job["gate_type"],
    )

    try:
        from scripts.regenerate_scene import regenerate

        regenerate(job, sync)
    except Exception as exc:
        logger.error("Job %s failed: %s", job["id"], exc, exc_info=True)
        sync.complete_regeneration_job(
            job["id"], success=False, error_message=str(exc)
        )

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Regeneration queue poller daemon"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Poll interval in seconds (default: 10)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Single poll then exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show pending jobs without claiming",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    sync = DashboardSync()
    if not sync.enabled:
        logger.error(
            "DashboardSync is disabled. Set SUPABASE_URL and SUPABASE_SERVICE_KEY."
        )
        sys.exit(1)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info(
        "Job poller started (worker=%s, interval=%ds)", WORKER_ID, args.interval
    )

    if args.once or args.dry_run:
        poll_once(sync, dry_run=args.dry_run)
        return

    # Daemon loop
    last_reap = 0.0
    reap_interval = 60  # seconds between stale job reaper runs
    while not _shutdown:
        try:
            # Run stale job reaper every 60 seconds
            now = time.time()
            if now - last_reap >= reap_interval:
                _reap_stale_jobs(sync)
                last_reap = now

            found = poll_once(sync)
            if not found:
                # No jobs -- back off before next poll
                time.sleep(args.interval)
            # If we found a job, immediately check for more (no sleep)
        except Exception as exc:
            logger.error("Poll cycle error: %s", exc, exc_info=True)
            time.sleep(args.interval)  # Back off on unexpected errors

    logger.info("Job poller shut down cleanly")


if __name__ == "__main__":
    main()
