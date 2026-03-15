"""Tests for BatchManifest: schema, resume logic, staleness detection, atomic writes."""

import json
import os
import time
from datetime import datetime, timezone, timedelta

import pytest

from video.kling.manifest import BatchManifest, ClipStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_clips(count=5):
    """Return a list of clip config dicts for testing."""
    return [
        {"scene": f"{i:02d}", "name": f"clip_{i:02d}"}
        for i in range(1, count + 1)
    ]


def _sample_config():
    return {
        "model_name": "kling-v3",
        "mode": "std",
        "workers": 3,
        "proxy": True,
    }


# ---------------------------------------------------------------------------
# Test: create manifest
# ---------------------------------------------------------------------------

class TestCreateManifest:
    def test_create_manifest(self, tmp_path):
        """New manifest has all clips as PENDING, summary counts correct."""
        path = tmp_path / "manifest.json"
        m = BatchManifest.create(
            batch_id="test-batch-001",
            format="vsl",
            clips=_sample_clips(5),
            config=_sample_config(),
            path=str(path),
        )

        assert len(m.clips) == 5
        for clip in m.clips:
            assert clip["status"] == ClipStatus.PENDING.value

        assert m.data["summary"]["total"] == 5
        assert m.data["summary"]["pending"] == 5
        assert m.data["summary"]["succeeded"] == 0
        assert m.data["summary"]["failed"] == 0

    def test_schema_fields_present(self, tmp_path):
        """Manifest contains all required top-level schema fields."""
        path = tmp_path / "manifest.json"
        m = BatchManifest.create(
            batch_id="test-batch-002",
            format="vsl",
            clips=_sample_clips(2),
            config=_sample_config(),
            path=str(path),
        )

        required_keys = [
            "schema_version", "batch_id", "format", "created_at",
            "last_heartbeat", "config", "skills_invoked", "summary", "clips",
        ]
        for key in required_keys:
            assert key in m.data, f"Missing key: {key}"

        assert m.data["schema_version"] == "batch-manifest-v1"
        assert m.data["batch_id"] == "test-batch-002"
        assert m.data["format"] == "vsl"


# ---------------------------------------------------------------------------
# Test: load manifest (round-trip)
# ---------------------------------------------------------------------------

class TestLoadManifest:
    def test_load_manifest(self, tmp_path):
        """Round-trip create -> save -> load preserves all fields."""
        path = tmp_path / "manifest.json"
        original = BatchManifest.create(
            batch_id="roundtrip-001",
            format="ads",
            clips=_sample_clips(3),
            config=_sample_config(),
            path=str(path),
        )

        loaded = BatchManifest.load(str(path))

        assert loaded.data["batch_id"] == original.data["batch_id"]
        assert loaded.data["format"] == original.data["format"]
        assert len(loaded.clips) == len(original.clips)
        for orig_clip, load_clip in zip(original.clips, loaded.clips):
            assert orig_clip == load_clip


# ---------------------------------------------------------------------------
# Test: update clip
# ---------------------------------------------------------------------------

class TestUpdateClip:
    def test_update_clip(self, tmp_path):
        """Updating status changes clip and recomputes summary."""
        path = tmp_path / "manifest.json"
        m = BatchManifest.create(
            batch_id="update-001",
            format="vsl",
            clips=_sample_clips(3),
            config=_sample_config(),
            path=str(path),
        )

        m.update_clip("01", status=ClipStatus.SUCCEEDED.value, task_id="abc123",
                       output_path="/some/path.mp4")

        clip = next(c for c in m.clips if c["scene"] == "01")
        assert clip["status"] == ClipStatus.SUCCEEDED.value
        assert clip["task_id"] == "abc123"
        assert clip["output_path"] == "/some/path.mp4"

        assert m.data["summary"]["succeeded"] == 1
        assert m.data["summary"]["pending"] == 2


# ---------------------------------------------------------------------------
# Test: schema consistency across formats
# ---------------------------------------------------------------------------

class TestSchemaConsistency:
    def test_schema_consistency(self, tmp_path):
        """VSL, ads, UGC all produce same core schema structure."""
        core_keys = {
            "schema_version", "batch_id", "format", "created_at",
            "last_heartbeat", "config", "skills_invoked", "summary", "clips",
        }
        clip_keys = {
            "scene", "name", "status", "task_id", "submit_time",
            "complete_time", "error_reason", "output_path", "retry_count",
            "elapsed_seconds",
        }

        for fmt in ("vsl", "ads", "ugc"):
            path = tmp_path / f"manifest_{fmt}.json"
            m = BatchManifest.create(
                batch_id=f"schema-{fmt}",
                format=fmt,
                clips=_sample_clips(2),
                config=_sample_config(),
                path=str(path),
            )
            assert set(m.data.keys()) == core_keys, f"Schema mismatch for format={fmt}"
            for clip in m.clips:
                assert set(clip.keys()) == clip_keys, f"Clip schema mismatch for format={fmt}"


# ---------------------------------------------------------------------------
# Test: resume logic
# ---------------------------------------------------------------------------

class TestResumeLogic:
    def test_resume_skips_completed(self, tmp_path):
        """get_pending_clips() excludes SUCCEEDED clips."""
        path = tmp_path / "manifest.json"
        m = BatchManifest.create(
            batch_id="resume-001",
            format="vsl",
            clips=_sample_clips(4),
            config=_sample_config(),
            path=str(path),
        )

        m.update_clip("01", status=ClipStatus.SUCCEEDED.value)
        m.update_clip("02", status=ClipStatus.SUCCEEDED.value)

        pending = m.get_pending_clips()
        scenes = [c["scene"] for c in pending]
        assert "01" not in scenes
        assert "02" not in scenes
        assert "03" in scenes
        assert "04" in scenes

    def test_resume_retries_failed(self, tmp_path):
        """get_pending_clips() includes FAILED clips."""
        path = tmp_path / "manifest.json"
        m = BatchManifest.create(
            batch_id="resume-002",
            format="vsl",
            clips=_sample_clips(3),
            config=_sample_config(),
            path=str(path),
        )

        m.update_clip("02", status=ClipStatus.FAILED.value, error_reason="moderation")

        pending = m.get_pending_clips()
        scenes = [c["scene"] for c in pending]
        assert "02" in scenes  # Failed clips are retried

    def test_resumable_clips(self, tmp_path):
        """get_resumable_clips() returns SUBMITTED/POLLING clips with task_id."""
        path = tmp_path / "manifest.json"
        m = BatchManifest.create(
            batch_id="resume-003",
            format="vsl",
            clips=_sample_clips(5),
            config=_sample_config(),
            path=str(path),
        )

        m.update_clip("01", status=ClipStatus.SUCCEEDED.value, task_id="t1")
        m.update_clip("02", status=ClipStatus.SUBMITTED.value, task_id="t2")
        m.update_clip("03", status=ClipStatus.POLLING.value, task_id="t3")
        m.update_clip("04", status=ClipStatus.FAILED.value, task_id="t4")
        # 05 stays PENDING (no task_id)

        resumable = m.get_resumable_clips()
        scenes = [c["scene"] for c in resumable]
        assert "02" in scenes
        assert "03" in scenes
        assert "01" not in scenes  # succeeded
        assert "04" not in scenes  # failed
        assert "05" not in scenes  # pending, no task_id

    def test_skip_completed(self, tmp_path):
        """Only SUCCEEDED clips are skipped; all other statuses are candidates."""
        path = tmp_path / "manifest.json"
        m = BatchManifest.create(
            batch_id="skip-001",
            format="vsl",
            clips=_sample_clips(5),
            config=_sample_config(),
            path=str(path),
        )

        m.update_clip("01", status=ClipStatus.SUCCEEDED.value)
        m.update_clip("02", status=ClipStatus.FAILED.value)
        m.update_clip("03", status=ClipStatus.SUBMITTED.value, task_id="t3")
        m.update_clip("04", status=ClipStatus.POLLING.value, task_id="t4")
        # 05 stays PENDING

        pending = m.get_pending_clips()
        resumable = m.get_resumable_clips()

        # Only SUCCEEDED is truly skipped from all work
        all_work_scenes = {c["scene"] for c in pending} | {c["scene"] for c in resumable}
        assert "01" not in all_work_scenes
        assert "02" in all_work_scenes  # failed -> retry
        assert "03" in all_work_scenes  # submitted -> re-poll
        assert "04" in all_work_scenes  # polling -> re-poll
        assert "05" in all_work_scenes  # pending -> submit


# ---------------------------------------------------------------------------
# Test: staleness detection
# ---------------------------------------------------------------------------

class TestStalenessDetection:
    def test_staleness_detection(self, tmp_path):
        """last_heartbeat >30min ago with incomplete batch = stale."""
        path = tmp_path / "manifest.json"
        m = BatchManifest.create(
            batch_id="stale-001",
            format="vsl",
            clips=_sample_clips(2),
            config=_sample_config(),
            path=str(path),
        )

        # Set heartbeat to 31 minutes ago
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()
        m.data["last_heartbeat"] = old_time
        m.save()

        assert m.is_stale() is True

    def test_not_stale_when_complete(self, tmp_path):
        """Completed batch is never stale regardless of heartbeat age."""
        path = tmp_path / "manifest.json"
        m = BatchManifest.create(
            batch_id="stale-002",
            format="vsl",
            clips=_sample_clips(2),
            config=_sample_config(),
            path=str(path),
        )

        m.update_clip("01", status=ClipStatus.SUCCEEDED.value)
        m.update_clip("02", status=ClipStatus.SUCCEEDED.value)

        # Set heartbeat to 60 minutes ago
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        m.data["last_heartbeat"] = old_time
        m.save()

        assert m.is_stale() is False

    def test_not_stale_when_recent(self, tmp_path):
        """Heartbeat <30min ago is not stale."""
        path = tmp_path / "manifest.json"
        m = BatchManifest.create(
            batch_id="stale-003",
            format="vsl",
            clips=_sample_clips(2),
            config=_sample_config(),
            path=str(path),
        )

        # Heartbeat is set to now on create, so should not be stale
        assert m.is_stale() is False


# ---------------------------------------------------------------------------
# Test: atomic write
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_atomic_write(self, tmp_path):
        """Manifest file is valid JSON after write (no corruption)."""
        path = tmp_path / "manifest.json"
        m = BatchManifest.create(
            batch_id="atomic-001",
            format="vsl",
            clips=_sample_clips(10),
            config=_sample_config(),
            path=str(path),
        )

        # Update several clips to trigger multiple writes
        for i in range(1, 11):
            m.update_clip(f"{i:02d}", status=ClipStatus.SUCCEEDED.value, task_id=f"t{i}")

        # Read back and verify valid JSON
        with open(str(path)) as f:
            data = json.load(f)

        assert data["batch_id"] == "atomic-001"
        assert data["summary"]["succeeded"] == 10


# ---------------------------------------------------------------------------
# Test: skills_invoked field
# ---------------------------------------------------------------------------

class TestSkillsInvoked:
    def test_skills_invoked_field(self, tmp_path):
        """skills_invoked present in schema with default value."""
        path = tmp_path / "manifest.json"
        m = BatchManifest.create(
            batch_id="skills-001",
            format="vsl",
            clips=_sample_clips(1),
            config=_sample_config(),
            path=str(path),
        )

        assert "skills_invoked" in m.data
        assert isinstance(m.data["skills_invoked"], list)
        assert "kling-video-workflow" in m.data["skills_invoked"]
