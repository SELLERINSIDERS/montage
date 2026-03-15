"""Tests for Kling audio compliance test runner (SC-5 gap closure)."""

import json
import os
import tempfile

import pytest

from scripts.kling_audio_compliance import (
    CHECKLIST,
    COMPLIANCE_PROMPTS,
    evaluate_clip,
    generate_compliance_report,
    save_compliance_result,
    update_manifest_compliance,
)


class TestEvaluateClip:
    """Test evaluate_clip() returns dict with 5 checklist booleans and pass/fail."""

    def test_all_pass(self):
        scene = {
            "scene_id": "scene_01",
            "no_artifacts": True,
            "matches_visual": True,
            "dialogue_intelligible": True,
            "volume_appropriate": True,
            "no_abrupt_cuts": True,
        }
        result = evaluate_clip(scene)
        assert result["scene_id"] == "scene_01"
        assert result["passed"] is True
        assert all(result["checks"].values())
        assert len(result["checks"]) == 5

    def test_one_fails(self):
        scene = {
            "scene_id": "scene_02",
            "no_artifacts": True,
            "matches_visual": False,
            "dialogue_intelligible": True,
            "volume_appropriate": True,
            "no_abrupt_cuts": True,
        }
        result = evaluate_clip(scene)
        assert result["passed"] is False
        assert result["checks"]["matches_visual"] is False

    def test_all_fail(self):
        scene = {
            "scene_id": "scene_03",
            "no_artifacts": False,
            "matches_visual": False,
            "dialogue_intelligible": False,
            "volume_appropriate": False,
            "no_abrupt_cuts": False,
        }
        result = evaluate_clip(scene)
        assert result["passed"] is False
        assert not any(result["checks"].values())


class TestGenerateComplianceReport:
    """Test generate_compliance_report() aggregates 10 clip evaluations."""

    def _make_evaluation(self, scene_id, passed):
        return {
            "scene_id": scene_id,
            "checks": {k: passed for k in CHECKLIST},
            "passed": passed,
        }

    def test_all_pass(self):
        evals = [self._make_evaluation(f"scene_{i:02d}", True) for i in range(1, 11)]
        report = generate_compliance_report(evals)
        assert report["overall_status"] == "passed"
        assert report["passed_count"] == 10
        assert report["failed_count"] == 0
        assert "evaluated_at" in report
        assert len(report["clips"]) == 10

    def test_some_fail(self):
        evals = [self._make_evaluation(f"scene_{i:02d}", i <= 7) for i in range(1, 11)]
        report = generate_compliance_report(evals)
        assert report["overall_status"] == "failed"
        assert report["passed_count"] == 7
        assert report["failed_count"] == 3


class TestSaveComplianceResult:
    """Test save_compliance_result() writes JSON with history."""

    def test_writes_initial(self, tmp_path):
        config_path = str(tmp_path / "compliance.json")
        # Write initial empty structure
        with open(config_path, "w") as f:
            json.dump({"latest": None, "history": []}, f)

        report = {
            "overall_status": "passed",
            "passed_count": 10,
            "failed_count": 0,
            "evaluated_at": "2026-03-11T19:00:00Z",
            "clips": [],
        }
        save_compliance_result(report, config_path)

        with open(config_path) as f:
            data = json.load(f)
        assert data["latest"]["overall_status"] == "passed"
        assert len(data["history"]) == 1

    def test_appends_to_history(self, tmp_path):
        config_path = str(tmp_path / "compliance.json")
        existing = {
            "latest": {"overall_status": "failed", "evaluated_at": "2026-03-10T00:00:00Z"},
            "history": [{"overall_status": "failed", "evaluated_at": "2026-03-10T00:00:00Z"}],
        }
        with open(config_path, "w") as f:
            json.dump(existing, f)

        report = {
            "overall_status": "passed",
            "passed_count": 10,
            "failed_count": 0,
            "evaluated_at": "2026-03-11T19:00:00Z",
            "clips": [],
        }
        save_compliance_result(report, config_path)

        with open(config_path) as f:
            data = json.load(f)
        assert data["latest"]["overall_status"] == "passed"
        assert len(data["history"]) == 2


class TestUpdateManifestCompliance:
    """Test update_manifest_compliance() sets kling_compliance fields."""

    def test_sets_fields(self, tmp_path):
        manifest_path = str(tmp_path / "manifest.json")
        manifest_data = {
            "schema_version": "workflow-manifest-v2",
            "format": "vsl",
            "slug": "test",
            "created_at": "2026-03-11T00:00:00Z",
            "skills_invoked": [],
            "gates": {},
            "audio_config": {
                "preset": "narrated",
                "layers_active": {},
                "fallback_applied": False,
                "kling_compliance_status": None,
                "kling_compliance_date": None,
            },
            "phase_timing": {},
            "retry_counts": {},
            "api_usage": {},
            "scenes": [],
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        update_manifest_compliance(manifest_path, "passed", "2026-03-11T19:00:00Z")

        with open(manifest_path) as f:
            data = json.load(f)
        assert data["audio_config"]["kling_compliance_status"] == "passed"
        assert data["audio_config"]["kling_compliance_date"] == "2026-03-11T19:00:00Z"


class TestCompliancePrompts:
    """Test COMPLIANCE_PROMPTS has 10 entries with correct type distribution."""

    def test_count(self):
        assert len(COMPLIANCE_PROMPTS) == 10

    def test_type_distribution(self):
        types = [p["type"] for p in COMPLIANCE_PROMPTS]
        assert types.count("dialogue") >= 3
        assert types.count("ambient") >= 5
        assert types.count("silent") >= 2

    def test_required_fields(self):
        for p in COMPLIANCE_PROMPTS:
            assert "scene_id" in p
            assert "type" in p
            assert "prompt" in p


class TestChecklist:
    """Test CHECKLIST has exactly 5 entries."""

    def test_count(self):
        assert len(CHECKLIST) == 5

    def test_expected_keys(self):
        expected = {
            "no_artifacts",
            "matches_visual",
            "dialogue_intelligible",
            "volume_appropriate",
            "no_abrupt_cuts",
        }
        assert set(CHECKLIST.keys()) == expected
