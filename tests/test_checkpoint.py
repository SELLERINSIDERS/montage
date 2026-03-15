"""Tests for checkpoint write/read, resume logic, pre-written prompt, gate state persistence."""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from scripts.checkpoint import Checkpoint, CheckpointManager


@pytest.fixture
def state_dir(tmp_path):
    """Temporary state directory for checkpoint tests."""
    d = tmp_path / "state"
    d.mkdir()
    return str(d)


def _sample_gate_summary():
    return {
        "image_1k": {
            "approved": ["scene_01", "scene_02"],
            "flagged": ["scene_03"],
            "deferred": [],
            "feedback": {"scene_03": "Too dark, needs re-render"},
            "decided_at": "2026-03-10T12:00:00+00:00",
        }
    }


def _write_sample_checkpoint(mgr, phases_count=3, gate_summary=None):
    """Helper to write a checkpoint with sensible defaults."""
    phases = [f"phase_{i}" for i in range(1, phases_count + 1)]
    return mgr.write_checkpoint(
        phases_completed=phases,
        current_phase=f"phase_{phases_count + 1}",
        manifest_path="state/manifest.json",
        accumulated_decisions=["Used X for Y"],
        next_phase_prompt="Run phase_4 with file state/manifest.json",
        skill_paths={"cinematic_director": "skills/cinematic-director/SKILL.md"},
        gate_summary=gate_summary or {},
    )


class TestCheckpointWrite:
    def test_write_checkpoint_creates_file(self, state_dir):
        mgr = CheckpointManager(state_dir)
        _write_sample_checkpoint(mgr, phases_count=3)
        files = os.listdir(state_dir)
        checkpoint_files = [f for f in files if f.startswith("checkpoint-phase-")]
        assert len(checkpoint_files) == 1
        assert "checkpoint-phase-1.json" in checkpoint_files

    def test_checkpoint_contains_all_fields(self, state_dir):
        mgr = CheckpointManager(state_dir)
        _write_sample_checkpoint(mgr, phases_count=3)
        with open(os.path.join(state_dir, "checkpoint-phase-1.json")) as f:
            data = json.load(f)
        expected_fields = {
            "checkpoint_number",
            "written_at",
            "phases_completed",
            "current_phase",
            "manifest_path",
            "accumulated_decisions",
            "next_phase_prompt",
            "skill_paths",
            "gate_summary",
        }
        assert expected_fields.issubset(set(data.keys()))

    def test_checkpoint_human_readable(self, state_dir):
        mgr = CheckpointManager(state_dir)
        _write_sample_checkpoint(mgr, phases_count=3)
        path = os.path.join(state_dir, "checkpoint-phase-1.json")
        with open(path) as f:
            raw = f.read()
        # Pretty-printed JSON has newlines and indentation
        assert "\n" in raw
        assert "  " in raw


class TestShouldCheckpoint:
    @pytest.mark.parametrize("count,expected", [
        (0, False),
        (1, False),
        (2, False),
        (3, True),
        (4, False),
        (5, False),
        (6, True),
        (9, True),
    ])
    def test_should_checkpoint_every_3(self, state_dir, count, expected):
        mgr = CheckpointManager(state_dir)
        assert mgr.should_checkpoint(count) == expected


class TestLoadLatest:
    def test_load_latest_returns_most_recent(self, state_dir):
        mgr = CheckpointManager(state_dir)
        _write_sample_checkpoint(mgr, phases_count=3)
        _write_sample_checkpoint(mgr, phases_count=6)
        latest = mgr.load_latest()
        assert latest is not None
        assert latest.checkpoint_number == 2
        assert len(latest.phases_completed) == 6

    def test_load_latest_no_checkpoints(self, state_dir):
        mgr = CheckpointManager(state_dir)
        assert mgr.load_latest() is None


class TestResumeState:
    def test_resume_state_has_next_prompt(self, state_dir):
        mgr = CheckpointManager(state_dir)
        _write_sample_checkpoint(mgr, phases_count=3)
        state = mgr.get_resume_state()
        assert state is not None
        assert state["next_phase_prompt"] == "Run phase_4 with file state/manifest.json"
        assert state["current_phase"] == "phase_4"
        assert state["manifest_path"] == "state/manifest.json"

    def test_gate_state_persisted(self, state_dir):
        mgr = CheckpointManager(state_dir)
        gs = _sample_gate_summary()
        _write_sample_checkpoint(mgr, phases_count=3, gate_summary=gs)
        state = mgr.get_resume_state()
        assert state["gate_summary"] == gs
        assert "scene_03" in state["gate_summary"]["image_1k"]["flagged"]


class TestAtomicWrite:
    def test_atomic_write_used(self, state_dir):
        mgr = CheckpointManager(state_dir)
        with patch("scripts.checkpoint.atomic_write_json") as mock_write:
            _write_sample_checkpoint(mgr, phases_count=3)
            mock_write.assert_called_once()
