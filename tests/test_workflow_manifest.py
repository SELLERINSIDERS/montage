"""Tests for WorkflowManifest v2: gate state, transitions, approvals, timing."""

import json
import os
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from scripts.workflow_manifest import (
    WorkflowManifest,
    SceneStatus,
    GateDecision,
)


class TestCreateSchema:
    """WorkflowManifest.create produces v2 schema."""

    def test_schema_version(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("ad", "test-slug", 4, path=path)
        assert data["schema_version"] == "workflow-manifest-v2"

    def test_format_field(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("vsl", "example-project", 10, path=path)
        assert data["format"] == "vsl"

    def test_scene_count(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("ad", "test", 8, path=path)
        assert len(data["scenes"]) == 8

    def test_scene_structure(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("ad", "test", 3, path=path)
        scene = data["scenes"][0]
        assert "scene_id" in scene
        assert "gates" in scene
        assert "transition" in scene
        assert scene["transition"]["type"] is None
        assert scene["transition"]["end_frame_source"] is None
        assert scene["transition"]["approved"] is False

    def test_gates_dict_exists(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("ad", "test", 2, path=path)
        assert "gates" in data
        assert isinstance(data["gates"], dict)

    def test_skills_invoked_empty(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("ugc", "test", 2, path=path)
        assert data["skills_invoked"] == []

    def test_file_written_to_disk(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        WorkflowManifest.create("ad", "test", 2, path=path)
        assert os.path.exists(path)
        with open(path) as f:
            loaded = json.load(f)
        assert loaded["schema_version"] == "workflow-manifest-v2"


class TestGateDecisions:
    """record_gate_decision tracks approve/flag/defer per scene per gate."""

    def _make_manifest(self, tmp_path, scene_count=4):
        path = str(tmp_path / "manifest.json")
        WorkflowManifest.create("vsl", "test", scene_count, path=path)
        return WorkflowManifest(path)

    def test_approve_scene(self, tmp_path):
        m = self._make_manifest(tmp_path)
        m.record_gate_decision("scene_01", "image_1k", "approved")
        scene = m.data["scenes"][0]
        assert scene["gates"]["image_1k"]["status"] == "approved"

    def test_flag_scene_with_feedback(self, tmp_path):
        m = self._make_manifest(tmp_path)
        m.record_gate_decision("scene_01", "image_1k", "flagged", feedback="too dark")
        scene = m.data["scenes"][0]
        gate = scene["gates"]["image_1k"]
        assert gate["status"] == "flagged"
        assert gate["feedback"] == "too dark"
        assert gate["attempts"] == 1

    def test_flag_increments_attempts(self, tmp_path):
        m = self._make_manifest(tmp_path)
        m.record_gate_decision("scene_01", "image_1k", "flagged", feedback="too dark")
        m.record_gate_decision("scene_01", "image_1k", "flagged", feedback="still dark")
        scene = m.data["scenes"][0]
        assert scene["gates"]["image_1k"]["attempts"] == 2

    def test_three_flags_triggers_manual_intervention(self, tmp_path):
        m = self._make_manifest(tmp_path)
        m.record_gate_decision("scene_01", "image_1k", "flagged", feedback="issue 1")
        m.record_gate_decision("scene_01", "image_1k", "flagged", feedback="issue 2")
        m.record_gate_decision("scene_01", "image_1k", "flagged", feedback="issue 3")
        scene = m.data["scenes"][0]
        assert scene["gates"]["image_1k"]["status"] == "needs_manual_intervention"

    def test_defer_scene(self, tmp_path):
        m = self._make_manifest(tmp_path)
        m.record_gate_decision("scene_02", "video", "deferred")
        scene = m.data["scenes"][1]
        assert scene["gates"]["video"]["status"] == "deferred"


class TestGetApprovedScenes:
    """get_approved_scenes filters by gate type and approved status."""

    def test_returns_only_approved(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        WorkflowManifest.create("vsl", "test", 4, path=path)
        m = WorkflowManifest(path)
        m.record_gate_decision("scene_01", "image_1k", "approved")
        m.record_gate_decision("scene_02", "image_1k", "flagged", feedback="bad")
        m.record_gate_decision("scene_03", "image_1k", "approved")
        m.record_gate_decision("scene_04", "image_1k", "deferred")

        approved = m.get_approved_scenes("image_1k")
        ids = [s["scene_id"] for s in approved]
        assert ids == ["scene_01", "scene_03"]

    def test_empty_when_none_approved(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        WorkflowManifest.create("ad", "test", 2, path=path)
        m = WorkflowManifest(path)
        assert m.get_approved_scenes("image_1k") == []


class TestGateTiming:
    """record_gate_timing tracks ISO timestamps for presented/decided events."""

    def test_records_presented_timestamp(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        WorkflowManifest.create("ad", "test", 2, path=path)
        m = WorkflowManifest(path)
        m.record_gate_timing("scene_01", "image_1k", "presented")
        scene = m.data["scenes"][0]
        ts = scene["gate_timing"]["image_1k"]["presented"]
        # Should be valid ISO timestamp
        datetime.fromisoformat(ts)

    def test_records_decided_timestamp(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        WorkflowManifest.create("ad", "test", 2, path=path)
        m = WorkflowManifest(path)
        m.record_gate_timing("scene_01", "image_1k", "decided")
        scene = m.data["scenes"][0]
        ts = scene["gate_timing"]["image_1k"]["decided"]
        datetime.fromisoformat(ts)


class TestAtomicWrite:
    """WorkflowManifest uses atomic_write_json from video.kling.manifest."""

    def test_save_uses_atomic_write(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        WorkflowManifest.create("ad", "test", 2, path=path)
        m = WorkflowManifest(path)

        with patch("scripts.workflow_manifest.atomic_write_json") as mock_write:
            m.save()
            mock_write.assert_called_once_with(path, m.data)


class TestLessonsLearnedSeed:
    """config/lessons_learned.json exists as empty array."""

    def test_seed_file_exists(self):
        seed_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config",
            "lessons_learned.json",
        )
        assert os.path.exists(seed_path), f"Seed file missing at {seed_path}"

    def test_seed_file_is_empty_array(self):
        seed_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config",
            "lessons_learned.json",
        )
        with open(seed_path) as f:
            data = json.load(f)
        assert data == []
