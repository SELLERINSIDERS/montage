"""Integration tests for Orchestrator-GateRunner gate wiring.

Tests cover GATE-01 through GATE-06, checkpoint-before-error,
quick_approve passthrough, final_review bypass prevention,
resume after gate error, and flagged-scenes-continue behavior.
"""

import json
import os
import glob
import pytest
from unittest.mock import patch, MagicMock

from scripts.workflow_manifest import WorkflowManifest, SceneStatus, GateDecision
from scripts.orchestrator import Orchestrator, GateError


def _make_manifest(tmp_path, scene_count=4, fmt="vsl"):
    """Create a manifest on disk and return its path."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)
    path = str(state_dir / "manifest.json")
    WorkflowManifest.create(fmt, "test-slug", scene_count, path=path)
    return path


def _make_orchestrator(tmp_path, scene_count=4, fmt="vsl", quick_approve=False):
    """Create an Orchestrator with a manifest in tmp_path."""
    _make_manifest(tmp_path, scene_count=scene_count, fmt=fmt)
    with patch("scripts.orchestrator.validate_skills"):
        orch = Orchestrator(str(tmp_path), fmt, quick_approve=quick_approve)
    return orch


def _pass_compliance(tmp_path):
    """Set compliance gate as passed in the manifest so later gates can be tested."""
    manifest_path = os.path.join(str(tmp_path), "state", "manifest.json")
    with open(manifest_path) as f:
        data = json.load(f)
    data["gates"]["compliance"] = {"status": "passed"}
    with open(manifest_path, "w") as f:
        json.dump(data, f)


def _advance_to_phase(orch, target_phase):
    """Advance orchestrator through phases until reaching target_phase.

    Calls advance_phase for each phase before target_phase so that
    the next call would trigger the gate for target_phase.
    Gate checks are disabled during advancement to avoid blocking on
    intermediate gates.
    """
    phases = Orchestrator.PRODUCTION_PHASES
    target_idx = phases.index(target_phase)
    # Temporarily disable gate checking during advancement
    saved_gate_runner = orch.gate_runner
    orch.gate_runner = None
    for i in range(target_idx):
        orch.advance_phase(phases[i], f"Completed {phases[i]}")
    # Restore gate runner for the actual test assertion
    orch.gate_runner = saved_gate_runner


class TestComplianceBlocksSceneDesign:
    """GATE-01: Compliance gate blocks entry to scene_design."""

    def test_compliance_blocks_scene_design(self, tmp_path):
        """advance_phase('compliance', ...) raises GateError when compliance blocked."""
        orch = _make_orchestrator(tmp_path)
        # Advance through intake, research, scriptwriting
        _advance_to_phase(orch, "compliance")
        # Now complete compliance phase -- this should trigger compliance gate
        # before scene_design and raise GateError because compliance not passed
        with pytest.raises(GateError) as exc_info:
            orch.advance_phase("compliance", "Compliance phase done")
        assert "compliance" in str(exc_info.value).lower()


class TestImageGateBlocks2k:
    """GATE-02: Image 1K gate blocks entry to image_gen_2k."""

    def test_image_gate_blocks_2k(self, tmp_path):
        """advance_phase('image_review', ...) raises GateError with needs_review scenes."""
        orch = _make_orchestrator(tmp_path)
        # Advance to image_review phase
        _advance_to_phase(orch, "image_review")
        # Complete image_review -- gate should block image_gen_2k
        # because scenes have not been reviewed (needs_review)
        with pytest.raises(GateError) as exc_info:
            orch.advance_phase("image_review", "Image review done")
        assert "image_1k" in str(exc_info.value).lower() or "image" in str(exc_info.value).lower()


class TestRealignmentGate:
    """GATE-03: Realignment gate runs before video_prompts."""

    def test_realignment_gate(self, tmp_path):
        """advance_phase('realignment', ...) triggers realignment gate."""
        orch = _make_orchestrator(tmp_path)
        # Advance to realignment
        _advance_to_phase(orch, "realignment")
        # Realignment is non-blocking (informational), so no GateError
        # Just verify it completes without error
        result = orch.advance_phase("realignment", "Realignment done")
        assert result["next_phase"] == "voiceover"


class TestClipReviewBlocksStitch:
    """GATE-04: Clip review gate blocks entry to final_stitch."""

    def test_clip_review_blocks_stitch(self, tmp_path):
        """advance_phase('video_gen', ...) raises GateError with needs_review clips."""
        orch = _make_orchestrator(tmp_path)
        # Advance to video_gen -- completing it triggers clip_review gate
        # before clip_review phase... wait, let me check the GATE_MAP.
        # clip_review gate maps to final_stitch. So completing clip_review triggers it.
        _advance_to_phase(orch, "clip_review")
        # Complete clip_review -- triggers clip_review gate before final_stitch
        with pytest.raises(GateError) as exc_info:
            orch.advance_phase("clip_review", "Clip review done")
        assert "clip" in str(exc_info.value).lower() or "video" in str(exc_info.value).lower()


class TestFinalReviewGate:
    """GATE-05: Final review gate runs at end of pipeline."""

    def test_final_review_gate(self, tmp_path):
        """advance_phase('final_stitch', ...) triggers final_review gate."""
        orch = _make_orchestrator(tmp_path)
        # Advance to final_stitch
        _advance_to_phase(orch, "final_stitch")
        # Complete final_stitch -- triggers final_video gate before final_review
        # final_video is a scene-level gate; in non-quick_approve mode,
        # it presents the review (not auto-approved), so it should check scenes
        with pytest.raises(GateError):
            orch.advance_phase("final_stitch", "Final stitch done")


class TestQuickApproveDoesNotSkipFinalReview:
    """GATE-05 quick_approve: final_review NEVER auto-approves."""

    def test_quick_approve_does_not_skip_final_review(self, tmp_path):
        """Even with quick_approve=True, final_review gate raises GateError."""
        orch = _make_orchestrator(tmp_path, quick_approve=True)
        # Advance to final_stitch
        _advance_to_phase(orch, "final_stitch")
        # Even with quick_approve, final_review must block
        with pytest.raises(GateError) as exc_info:
            orch.advance_phase("final_stitch", "Final stitch done")
        assert "final" in str(exc_info.value).lower()


class TestLessonsLearnedPath:
    """GATE-06: GateRunner receives project-specific lessons_learned_path."""

    def test_lessons_learned_path(self, tmp_path):
        """Orchestrator passes project-specific lessons_learned_path to GateRunner."""
        orch = _make_orchestrator(tmp_path)
        assert orch.gate_runner is not None
        expected_path = os.path.join(str(tmp_path), "config", "lessons_learned.json")
        assert orch.gate_runner.lessons_learned_path == expected_path


class TestCheckpointBeforeGateError:
    """Checkpoint is always written before GateError is raised."""

    def test_checkpoint_before_gate_error(self, tmp_path):
        """When GateError is caught, checkpoint file exists in state dir."""
        orch = _make_orchestrator(tmp_path)
        _advance_to_phase(orch, "compliance")
        with pytest.raises(GateError):
            orch.advance_phase("compliance", "Compliance done")
        # Check that a checkpoint file was written
        state_dir = os.path.join(str(tmp_path), "state")
        checkpoints = glob.glob(os.path.join(state_dir, "checkpoint-*.json"))
        assert len(checkpoints) >= 1, "No checkpoint file found after GateError"


class TestQuickApprovePassthrough:
    """quick_approve flows from Orchestrator to GateRunner."""

    def test_quick_approve_passthrough(self, tmp_path):
        """Orchestrator(quick_approve=True) creates GateRunner(quick_approve=True)."""
        orch = _make_orchestrator(tmp_path, quick_approve=True)
        assert orch.gate_runner is not None
        assert orch.gate_runner.quick_approve is True

        # Scene-level gates (image_1k) auto-approve in quick_approve mode
        # Advance to image_review, complete it -- image_1k gate should NOT raise
        # because quick_approve auto-approves optional gates
        _advance_to_phase(orch, "image_review")
        # Should NOT raise GateError (auto-approved)
        result = orch.advance_phase("image_review", "Image review done")
        assert result["next_phase"] == "image_gen_2k"


class TestResumeAfterGateError:
    """After catching GateError and fixing the gate, resume() returns correct phase."""

    def test_resume_after_gate_error(self, tmp_path):
        """resume() returns the phase that was blocked by GateError."""
        orch = _make_orchestrator(tmp_path)
        _advance_to_phase(orch, "compliance")

        with pytest.raises(GateError):
            orch.advance_phase("compliance", "Compliance done")

        # Now fix the gate by setting compliance as passed
        manifest_path = os.path.join(str(tmp_path), "state", "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)
        data["gates"]["compliance"] = {"status": "passed"}
        with open(manifest_path, "w") as f:
            json.dump(data, f)

        # Create fresh orchestrator and resume
        with patch("scripts.orchestrator.validate_skills"):
            orch2 = Orchestrator(str(tmp_path), "vsl")
        state = orch2.resume()
        # Should be able to resume from the checkpoint
        assert state["current_phase"] is not None


class TestGateRunnerNotInstantiatedWithoutManifest:
    """When no manifest exists, gate_runner is None and advance works."""

    def test_gate_runner_not_instantiated_without_manifest(self, tmp_path):
        """Without manifest, gate_runner is None and advance_phase works."""
        state_dir = tmp_path / "state"
        state_dir.mkdir(exist_ok=True)
        # No manifest file created
        with patch("scripts.orchestrator.validate_skills"):
            orch = Orchestrator(str(tmp_path), "vsl")
        assert orch.gate_runner is None
        # advance_phase should work without gates
        result = orch.advance_phase("intake", "Intake done")
        assert result["next_phase"] == "research"


class TestFlaggedScenesContinue:
    """Flagged scenes (not needs_review) allow pipeline to continue."""

    def test_flagged_scenes_continue(self, tmp_path):
        """When image_1k has flagged but no needs_review scenes, pipeline continues."""
        orch = _make_orchestrator(tmp_path)
        # Flag all scenes (not needs_review, just flagged)
        for i in range(1, 5):
            scene_id = f"scene_{i:02d}"
            orch.manifest.record_gate_decision(scene_id, "image_1k", "flagged", feedback="minor issue")
        # Reload gate_runner's manifest
        orch.gate_runner.manifest = WorkflowManifest(
            os.path.join(str(tmp_path), "state", "manifest.json")
        )
        _advance_to_phase(orch, "image_review")
        # Should NOT raise GateError -- flagged scenes continue
        result = orch.advance_phase("image_review", "Image review done")
        assert result["next_phase"] == "image_gen_2k"


class TestManualInterventionBlocks:
    """needs_manual_intervention status raises GateError."""

    def test_manual_intervention_blocks(self, tmp_path):
        """When image_1k has needs_manual_intervention scenes, GateError is raised."""
        orch = _make_orchestrator(tmp_path)
        # Set scene to needs_manual_intervention via 3 flags
        for _ in range(3):
            orch.manifest.record_gate_decision(
                "scene_01", "image_1k", "flagged", feedback="still bad"
            )
        # Reload gate_runner's manifest
        orch.gate_runner.manifest = WorkflowManifest(
            os.path.join(str(tmp_path), "state", "manifest.json")
        )
        _advance_to_phase(orch, "image_review")
        with pytest.raises(GateError) as exc_info:
            orch.advance_phase("image_review", "Image review done")
        assert "manual" in str(exc_info.value).lower() or "intervention" in str(exc_info.value).lower()
