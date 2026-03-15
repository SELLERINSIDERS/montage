"""Batch manifest system for crash-resume, staleness detection, and per-clip status tracking.

Provides BatchManifest class with atomic writes, heartbeat-based staleness detection,
and resume logic that correctly handles in-flight tasks without duplicate API calls.

Schema is consistent across VSL, ads, and UGC formats.
"""

import json
import os
import tempfile
import threading
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any


class ClipStatus(Enum):
    """Per-clip lifecycle status. String values match JSON output."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    POLLING = "polling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def atomic_write_json(path: str, data: dict) -> None:
    """Write JSON atomically -- no partial files on crash.

    Writes to a temp file in the same directory, then renames (POSIX atomic).
    """
    dir_path = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class BatchManifest:
    """Rich batch manifest with per-clip tracking, heartbeat, crash-resume, atomic writes.

    Usage:
        # Create new manifest
        m = BatchManifest.create("batch-001", "vsl", clips, config, path="manifest.json")

        # Load existing manifest
        m = BatchManifest.load("manifest.json")

        # Update a clip
        m.update_clip("01", status="succeeded", task_id="abc123", output_path="out.mp4")

        # Get clips needing work
        pending = m.get_pending_clips()      # PENDING or FAILED
        resumable = m.get_resumable_clips()  # SUBMITTED/POLLING with task_id

        # Staleness check
        if m.is_stale():
            print("Pipeline appears crashed")
    """

    def __init__(self, data: dict, path: str) -> None:
        self.data = data
        self.path = path
        self._lock = threading.Lock()

    @property
    def clips(self) -> list[dict]:
        return self.data["clips"]

    @classmethod
    def create(
        cls,
        batch_id: str,
        format: str,
        clips: list[dict],
        config: dict,
        path: str,
    ) -> "BatchManifest":
        """Create a new manifest with all clips in PENDING status."""
        now = datetime.now(timezone.utc).isoformat()

        manifest_clips = []
        for clip_cfg in clips:
            manifest_clips.append({
                "scene": clip_cfg["scene"],
                "name": clip_cfg["name"],
                "status": ClipStatus.PENDING.value,
                "task_id": None,
                "submit_time": None,
                "complete_time": None,
                "error_reason": None,
                "output_path": None,
                "retry_count": 0,
                "elapsed_seconds": None,
            })

        data = {
            "schema_version": "batch-manifest-v1",
            "batch_id": batch_id,
            "format": format,
            "created_at": now,
            "last_heartbeat": now,
            "config": config,
            "skills_invoked": ["kling-video-workflow"],
            "summary": cls._compute_summary(manifest_clips),
            "clips": manifest_clips,
        }

        instance = cls(data, path)
        instance.save()
        return instance

    @classmethod
    def load(cls, path: str) -> "BatchManifest":
        """Load an existing manifest from JSON."""
        with open(path, "r") as f:
            data = json.load(f)
        return cls(data, path)

    def save(self) -> None:
        """Save manifest atomically. Auto-recomputes summary counts."""
        with self._lock:
            self.data["summary"] = self._compute_summary(self.clips)
            atomic_write_json(self.path, self.data)

    def update_clip(self, scene: str, **kwargs: Any) -> None:
        """Find clip by scene id, update fields, save atomically."""
        with self._lock:
            for clip in self.clips:
                if clip["scene"] == scene:
                    for key, value in kwargs.items():
                        clip[key] = value
                    break
            else:
                raise ValueError(f"No clip with scene={scene!r}")
            self.data["summary"] = self._compute_summary(self.clips)
            atomic_write_json(self.path, self.data)

    def get_pending_clips(self) -> list[dict]:
        """Return clips needing submission: PENDING or FAILED (for retry)."""
        return [
            c for c in self.clips
            if c["status"] in (ClipStatus.PENDING.value, ClipStatus.FAILED.value)
        ]

    def get_resumable_clips(self) -> list[dict]:
        """Return clips with task_id but non-terminal status (need re-polling, not re-submitting)."""
        return [
            c for c in self.clips
            if c["status"] in (ClipStatus.SUBMITTED.value, ClipStatus.POLLING.value)
            and c["task_id"] is not None
        ]

    def is_complete(self) -> bool:
        """Return True if all clips are in a terminal state (SUCCEEDED or FAILED)."""
        terminal = {ClipStatus.SUCCEEDED.value, ClipStatus.FAILED.value}
        return all(c["status"] in terminal for c in self.clips)

    def is_stale(self, threshold_minutes: int = 30) -> bool:
        """Return True when last_heartbeat is older than threshold and batch is not complete."""
        if self.is_complete():
            return False

        heartbeat_str = self.data.get("last_heartbeat")
        if not heartbeat_str:
            return True

        heartbeat = datetime.fromisoformat(heartbeat_str)
        # Ensure timezone-aware comparison
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=timezone.utc)

        threshold = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
        return heartbeat < threshold

    def update_heartbeat(self) -> None:
        """Update last_heartbeat to current UTC time and save."""
        self.data["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
        self.save()

    @staticmethod
    def _compute_summary(clips: list[dict]) -> dict:
        """Compute summary counts from clip statuses."""
        total = len(clips)
        succeeded = sum(1 for c in clips if c["status"] == ClipStatus.SUCCEEDED.value)
        failed = sum(1 for c in clips if c["status"] == ClipStatus.FAILED.value)
        submitted = sum(1 for c in clips if c["status"] == ClipStatus.SUBMITTED.value)
        polling = sum(1 for c in clips if c["status"] == ClipStatus.POLLING.value)
        pending = total - succeeded - failed - submitted - polling

        return {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "submitted": submitted,
            "polling": polling,
            "pending": pending,
        }


class HeartbeatWriter:
    """Context manager that starts a background thread updating heartbeat every N seconds.

    Usage:
        manifest = BatchManifest.load("manifest.json")
        with HeartbeatWriter(manifest, interval=30):
            # ... run batch processing ...
            pass
        # Heartbeat thread stops cleanly on exit
    """

    def __init__(self, manifest: BatchManifest, interval: int = 30) -> None:
        self.manifest = manifest
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "HeartbeatWriter":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    def start(self) -> None:
        """Start the heartbeat daemon thread."""
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        """Background loop: update heartbeat at interval until stopped."""
        while not self._stop.wait(self.interval):
            try:
                self.manifest.update_heartbeat()
            except Exception:
                pass  # Heartbeat failure should not crash the pipeline

    def stop(self) -> None:
        """Signal the heartbeat thread to stop and wait for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
