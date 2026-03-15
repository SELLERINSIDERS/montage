"""Event-driven regeneration listener using Supabase Realtime.

Subscribes to INSERT and UPDATE events on the ``regeneration_queue`` table.
When a new pending job appears (insert or status reset to 'pending'),
it immediately claims and processes it — no polling delay.

Also runs a periodic stale-job reaper (every 60 s) to recover stuck jobs.

Usage:
    python -m scripts.job_listener          # Start listener (foreground)
    python -m scripts.job_listener --once   # Process pending jobs then wait for 1 event
"""

import argparse
import asyncio
import logging
import os
import signal
import socket
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load project .env first, then optional EXTRA_ENV_FILE (e.g. for Supabase creds)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
_extra_env = os.environ.get("EXTRA_ENV_FILE", "")
if _extra_env and Path(_extra_env).exists():
    load_dotenv(Path(_extra_env), override=False)

from realtime import AsyncRealtimeClient, RealtimeSubscribeStates
from scripts.dashboard_sync import DashboardSync

logger = logging.getLogger(__name__)

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"

# Graceful shutdown
_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    _shutdown = True
    logger.info("Shutdown signal received...")


def _process_job(sync: DashboardSync, job: dict) -> None:
    """Claim and process a single regeneration job (sync, runs in thread)."""
    job_id = job["id"]
    scene_id = job["scene_id"]
    gate_type = job["gate_type"]

    logger.info("Processing job %s: scene=%s gate=%s", job_id, scene_id, gate_type)

    try:
        from scripts.regenerate_scene import regenerate
        regenerate(job, sync)
    except Exception as exc:
        logger.error("Job %s failed: %s", job_id, exc, exc_info=True)
        sync.complete_regeneration_job(
            job_id, success=False, error_message=str(exc)
        )


def _drain_pending(sync: DashboardSync) -> int:
    """Claim and process all pending jobs. Returns count processed."""
    count = 0
    while not _shutdown:
        job = sync.claim_regeneration_job(WORKER_ID)
        if job is None:
            break
        _process_job(sync, job)
        count += 1
    return count


def _reap_stale_jobs(sync: DashboardSync, stale_minutes: int = 15) -> None:
    """Reset jobs stuck in claimed/processing state."""
    # Reuse the reaper from job_poller
    from scripts.job_poller import _reap_stale_jobs as reap
    reap(sync, stale_minutes)


async def run_listener(sync: DashboardSync, once: bool = False) -> None:
    """Main async loop: subscribe to Realtime and process jobs."""

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")

    if not url or not key:
        logger.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
        return

    # Realtime URL: replace https:// with wss:// and add /realtime/v1
    realtime_url = url.replace("https://", "wss://").replace("http://", "ws://")
    realtime_url = f"{realtime_url}/realtime/v1"

    # --- Drain any existing pending jobs first ---
    logger.info("Draining existing pending jobs...")
    drained = await asyncio.get_event_loop().run_in_executor(
        None, _drain_pending, sync
    )
    if drained:
        logger.info("Drained %d pending job(s)", drained)
    else:
        logger.info("No pending jobs in queue")

    if once and drained:
        logger.info("--once mode: processed %d job(s), exiting", drained)
        return

    # --- Connect to Supabase Realtime ---
    logger.info("Connecting to Supabase Realtime...")
    client = AsyncRealtimeClient(realtime_url, key)

    # Event to signal when a new job arrives
    job_event = asyncio.Event()

    def _on_insert(payload: dict) -> None:
        """Callback for INSERT on regeneration_queue."""
        record = payload.get("data", {}).get("record", {})
        status = record.get("status", "")
        scene_id = record.get("scene_id", "?")
        gate_type = record.get("gate_type", "?")

        if status == "pending":
            logger.info(
                "Realtime: new pending job detected — scene=%s gate=%s",
                scene_id, gate_type,
            )
            job_event.set()

    def _on_update(payload: dict) -> None:
        """Callback for UPDATE on regeneration_queue (e.g. reset to pending)."""
        record = payload.get("data", {}).get("record", {})
        status = record.get("status", "")
        scene_id = record.get("scene_id", "?")

        if status == "pending":
            logger.info(
                "Realtime: job reset to pending — scene=%s", scene_id,
            )
            job_event.set()

    def _on_subscribe(
        status: RealtimeSubscribeStates, err: Optional[Exception]
    ) -> None:
        if status == RealtimeSubscribeStates.SUBSCRIBED:
            logger.info("Subscribed to regeneration_queue changes — listening...")
        elif status == RealtimeSubscribeStates.CHANNEL_ERROR:
            logger.error("Realtime channel error: %s", err)
        elif status == RealtimeSubscribeStates.TIMED_OUT:
            logger.error("Realtime subscription timed out")
        elif status == RealtimeSubscribeStates.CLOSED:
            logger.warning("Realtime channel closed")

    channel = client.channel("regen-queue-listener")

    channel.on_postgres_changes(
        "INSERT",
        schema="public",
        table="regeneration_queue",
        callback=_on_insert,
    )

    channel.on_postgres_changes(
        "UPDATE",
        schema="public",
        table="regeneration_queue",
        callback=_on_update,
    )

    await channel.subscribe(_on_subscribe)

    # --- Main event loop ---
    logger.info("Listener running (worker=%s). Ctrl+C to stop.", WORKER_ID)
    last_reap = asyncio.get_event_loop().time()
    reap_interval = 60.0

    while not _shutdown:
        # Wait for a Realtime event or periodic reap timeout
        try:
            await asyncio.wait_for(job_event.wait(), timeout=reap_interval)
        except asyncio.TimeoutError:
            pass

        if _shutdown:
            break

        # Clear the event and process
        job_event.clear()

        # Drain all pending jobs (there may be multiple)
        processed = await asyncio.get_event_loop().run_in_executor(
            None, _drain_pending, sync
        )
        if processed:
            logger.info("Processed %d job(s)", processed)

        # Periodic stale job reaper
        now = asyncio.get_event_loop().time()
        if now - last_reap >= reap_interval:
            await asyncio.get_event_loop().run_in_executor(
                None, _reap_stale_jobs, sync
            )
            last_reap = now

        if once and processed:
            logger.info("--once mode: done after processing %d job(s)", processed)
            break

    # Cleanup
    await client.remove_channel(channel)
    logger.info("Listener shut down cleanly")


def main():
    parser = argparse.ArgumentParser(
        description="Event-driven regeneration listener (Supabase Realtime)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process pending jobs + wait for one event, then exit",
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

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    asyncio.run(run_listener(sync, once=args.once))


if __name__ == "__main__":
    main()
