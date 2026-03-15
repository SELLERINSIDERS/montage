"""Tests for GateRunner: compliance enforcement, 1K->2K workflow, review gates, lessons-learned."""

import json
import os
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from scripts.gate_runner import GateRunner, GateType
from scripts.workflow_manifest import WorkflowManifest, SceneStatus, GateDecision


def _make_manifest(tmp_path, scene_count=4, fmt="vsl"):
    """Create a manifest on disk and return its path."""
    path = str(tmp_path / "manifest.json")
    WorkflowManifest.create(fmt, "test-slug", scene_count, path=path)
    return path


class TestComplianceBlocking:
    """Compliance gate blocks all downstream work regardless of format."""

    def test_compliance_blocks_downstream(self, tmp_path):
        """Manifest without compliance passed returns blocked=True."""
        path = _make_manifest(tmp_path)
        runner = GateRunner(path)
        result = runner.run_compliance_gate("vsl")
        assert result["blocked"] is True
        assert "compliance" in result["reason"].lower()

    @pytest.mark.parametrize("fmt", ["ad", "ugc", "vsl"])
    def test_compliance_all_formats(self, tmp_path, fmt):
        """Compliance gate blocks for all formats equally."""
        path = _make_manifest(tmp_path, fmt=fmt)
        runner = GateRunner(path)
        result = runner.run_compliance_gate(fmt)
        assert result["blocked"] is True

    def test_compliance_passes_when_set(self, tmp_path):
        """Compliance gate returns blocked=False when status is passed."""
        path = _make_manifest(tmp_path)
        # Manually set compliance as passed
        with open(path) as f:
            data = json.load(f)
        data["gates"]["compliance"] = {"status": "passed", "timestamp": "2026-01-01T00:00:00Z"}
        with open(path, "w") as f:
            json.dump(data, f)
        runner = GateRunner(path)
        result = runner.run_compliance_gate("vsl")
        assert result["blocked"] is False


class TestScriptReview:
    """Script review gate returns formatted summary."""

    def test_script_gate_returns_summary(self, tmp_path):
        """Script review gate returns scene_count, format, compliance_status."""
        path = _make_manifest(tmp_path, scene_count=8)
        runner = GateRunner(path)
        result = runner.run_script_review_gate()
        assert result["scene_count"] == 8
        assert result["format"] == "vsl"
        assert "compliance_status" in result

    def test_script_gate_approval_records(self, tmp_path):
        """After running script review, recording approval updates manifest."""
        path = _make_manifest(tmp_path)
        runner = GateRunner(path)
        runner.run_script_review_gate()
        runner.record_feedback("scene_01", GateType.SCRIPT_REVIEW, GateDecision.APPROVED)
        m = WorkflowManifest(path)
        gate = m.data["scenes"][0]["gates"].get("script_review", {})
        assert gate["status"] == "approved"


class TestImageReview:
    """Image 1K review enforces 1K-before-2K and 3-attempt limit."""

    def test_1k_before_2k_enforcement(self, tmp_path):
        """promote_to_2k raises ValueError on unapproved scene."""
        path = _make_manifest(tmp_path)
        runner = GateRunner(path)
        with pytest.raises(ValueError, match="not approved"):
            runner.promote_to_2k(["scene_01"])

    def test_1k_approved_promotes(self, tmp_path):
        """Approved 1K scene can be promoted to 2K."""
        path = _make_manifest(tmp_path)
        runner = GateRunner(path)
        # Approve scene at 1K
        runner.record_feedback("scene_01", GateType.IMAGE_1K, GateDecision.APPROVED)
        # Now promote should work
        result = runner.promote_to_2k(["scene_01"])
        assert "scene_01" in result["promoted"]

    def test_3_attempt_max(self, tmp_path):
        """Scene flagged 3 times becomes needs_manual_intervention."""
        path = _make_manifest(tmp_path)
        runner = GateRunner(path)
        for i in range(3):
            runner.record_feedback(
                "scene_01", GateType.IMAGE_1K, GateDecision.FLAGGED,
                feedback_text=f"issue {i+1}"
            )
        m = WorkflowManifest(path)
        status = m.data["scenes"][0]["gates"]["image_1k"]["status"]
        assert status == "needs_manual_intervention"

    def test_image_review_categorizes_scenes(self, tmp_path):
        """Image review gate returns categorized scene lists."""
        path = _make_manifest(tmp_path, scene_count=5)
        runner = GateRunner(path)
        # Set up various states
        runner.record_feedback("scene_01", GateType.IMAGE_1K, GateDecision.APPROVED)
        runner.record_feedback("scene_02", GateType.IMAGE_1K, GateDecision.FLAGGED, "too dark")
        runner.record_feedback("scene_03", GateType.IMAGE_1K, GateDecision.DEFERRED)
        # scene_04 and scene_05 are pending (no decision yet)

        result = runner.run_image_review_gate(
            ["scene_01", "scene_02", "scene_03", "scene_04", "scene_05"]
        )
        assert "scene_01" in result["approved"]
        assert "scene_02" in result["flagged"]
        assert "scene_03" in result["deferred"]
        assert "scene_04" in result["needs_review"]

    def test_3_attempt_in_image_review(self, tmp_path):
        """Image review gate shows scenes hitting 3-attempt limit."""
        path = _make_manifest(tmp_path, scene_count=2)
        runner = GateRunner(path)
        for _ in range(3):
            runner.record_feedback("scene_01", GateType.IMAGE_1K, GateDecision.FLAGGED, "bad")

        result = runner.run_image_review_gate(["scene_01"])
        assert "scene_01" in result["manual_intervention"]


class TestQuickApprove:
    """Quick approve mode skips optional gates but keeps compliance."""

    def test_quick_approve_skips_optional(self, tmp_path):
        """With quick_approve=True, optional gates return auto-approved."""
        path = _make_manifest(tmp_path)
        runner = GateRunner(path, quick_approve=True)
        result = runner.run_image_review_gate(["scene_01"])
        assert result.get("auto_approved") is True

    def test_quick_approve_keeps_compliance(self, tmp_path):
        """With quick_approve=True, compliance gate still runs."""
        path = _make_manifest(tmp_path)
        runner = GateRunner(path, quick_approve=True)
        result = runner.run_compliance_gate("vsl")
        assert result["blocked"] is True  # Still blocked, not auto-approved


class TestRealignment:
    """Realignment gate returns diff summary of prompt changes."""

    def test_realignment_diff_structure(self, tmp_path):
        """Realignment gate returns changed_scenes list."""
        path = _make_manifest(tmp_path)
        runner = GateRunner(path)
        result = runner.run_realignment_gate()
        assert "changed_scenes" in result
        assert isinstance(result["changed_scenes"], list)


class TestClipReview:
    """Clip review gate categorizes clips for review."""

    def test_clip_review_structure(self, tmp_path):
        """Clip review returns categorized scene lists."""
        path = _make_manifest(tmp_path, scene_count=3)
        runner = GateRunner(path)
        result = runner.run_clip_review_gate(["scene_01", "scene_02", "scene_03"])
        assert "needs_review" in result
        assert "approved" in result
        assert "flagged" in result


class TestFinalReview:
    """Final review gate returns production summary with re-edit options."""

    def test_final_review_structure(self, tmp_path):
        """Final review returns scenes list and re_edit_options."""
        path = _make_manifest(tmp_path)
        runner = GateRunner(path)
        result = runner.run_final_review_gate()
        assert "scenes" in result
        assert "re_edit_options" in result


class TestGateTiming:
    """Gate operations record timing in manifest."""

    def test_gate_timing_recorded(self, tmp_path):
        """Running any gate records gate_timing timestamps."""
        path = _make_manifest(tmp_path)
        runner = GateRunner(path)
        runner.run_compliance_gate("vsl")
        # Reload manifest and check timing
        m = WorkflowManifest(path)
        # Global gate timing should be recorded
        assert "compliance" in m.data.get("gate_timing", m.data.get("gates", {}).get("_timing", {})) or \
            any("compliance" in str(m.data.get("gates", {})))


class TestFeedbackAndLessonsLearned:
    """Feedback that leads to successful revision logs to lessons_learned.json."""

    def test_feedback_logs_to_lessons_learned(self, tmp_path):
        """Record feedback leading to success, assert entry in lessons_learned.json."""
        ll_path = str(tmp_path / "lessons_learned.json")
        with open(ll_path, "w") as f:
            json.dump([], f)

        path = _make_manifest(tmp_path)
        runner = GateRunner(path, lessons_learned_path=ll_path)

        # First flag (issue found)
        runner.record_feedback(
            "scene_01", GateType.IMAGE_1K, GateDecision.FLAGGED,
            feedback_text="too dark, needs brighter lighting"
        )
        # Then approve (successful revision)
        runner.record_feedback(
            "scene_01", GateType.IMAGE_1K, GateDecision.APPROVED,
            feedback_text="lighting fixed after adjustment"
        )

        with open(ll_path) as f:
            lessons = json.load(f)
        assert len(lessons) == 1
        assert lessons[0]["outcome"] == "success"
        assert "scene_01" in lessons[0]["scene_id"]


class TestGateSummary:
    """get_gate_summary aggregates all gate statuses."""

    def test_gate_summary_structure(self, tmp_path):
        """Gate summary returns dict of gate statuses across scenes."""
        path = _make_manifest(tmp_path, scene_count=3)
        runner = GateRunner(path)
        runner.record_feedback("scene_01", GateType.IMAGE_1K, GateDecision.APPROVED)
        runner.record_feedback("scene_02", GateType.IMAGE_1K, GateDecision.FLAGGED, "bad")

        summary = runner.get_gate_summary()
        assert "image_1k" in summary
        assert summary["image_1k"]["approved"] >= 1
        assert summary["image_1k"]["flagged"] >= 1
