"""Tests for audio preset selection and manifest audio/analytics fields."""

import json
import os
import pytest
from datetime import datetime
from unittest.mock import patch

from scripts.workflow_manifest import WorkflowManifest


class TestAudioPresetSelection:
    """create() derives audio_config preset from format."""

    def test_vsl_format_uses_narrated_preset(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("vsl", "test", 4, path=path)
        assert data["audio_config"]["preset"] == "narrated"

    def test_vsl_layers_active(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("vsl", "test", 4, path=path)
        layers = data["audio_config"]["layers_active"]
        assert layers["elevenlabs_voiceover"] is True
        assert layers["kling_audio"] is True
        assert layers["kling_dialogue"] is False

    def test_ugc_format_uses_full_mix_preset(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("ugc", "test", 4, path=path)
        assert data["audio_config"]["preset"] == "full_mix"

    def test_ugc_layers_active(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("ugc", "test", 4, path=path)
        layers = data["audio_config"]["layers_active"]
        assert layers["kling_dialogue"] is True

    def test_ad_format_uses_narrated_preset(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("ad", "test", 4, path=path)
        assert data["audio_config"]["preset"] == "narrated"

    def test_unknown_format_defaults_to_narrated(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("unknown", "test", 4, path=path)
        assert data["audio_config"]["preset"] == "narrated"

    def test_audio_config_has_fallback_fields(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("vsl", "test", 4, path=path)
        ac = data["audio_config"]
        assert ac["fallback_applied"] is False
        assert ac["kling_compliance_status"] is None
        assert ac["kling_compliance_date"] is None


class TestAnalyticsFields:
    """create() includes phase_timing, retry_counts, api_usage."""

    def test_phase_timing_empty_dict(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("vsl", "test", 4, path=path)
        assert data["phase_timing"] == {}

    def test_retry_counts_empty_dict(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("vsl", "test", 4, path=path)
        assert data["retry_counts"] == {}

    def test_api_usage_all_zero_counters(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("vsl", "test", 4, path=path)
        expected_keys = [
            "kling_video", "kling_audio", "kling_tts", "kling_lipsync",
            "elevenlabs_chars", "elevenlabs_calls", "gemini_images",
            "whisper_segments",
        ]
        for key in expected_keys:
            assert data["api_usage"][key] == 0, f"api_usage[{key}] should be 0"

    def test_schema_version_unchanged(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("vsl", "test", 4, path=path)
        assert data["schema_version"] == "workflow-manifest-v2"


class TestSceneAudioField:
    """Each scene includes audio field with null defaults."""

    def test_scene_has_audio_field(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("vsl", "test", 3, path=path)
        for scene in data["scenes"]:
            assert "audio" in scene, f"{scene['scene_id']} missing audio field"
            assert scene["audio"]["type"] is None
            assert scene["audio"]["audio_prompt"] is None
            assert scene["audio"]["audio_path"] is None


class TestHelperMethods:
    """Helper methods for incrementing usage, timing, retries."""

    def _make_manifest(self, tmp_path, format="vsl", scenes=4):
        path = str(tmp_path / "manifest.json")
        WorkflowManifest.create(format, "test", scenes, path=path)
        return WorkflowManifest(path)

    def test_increment_api_usage(self, tmp_path):
        m = self._make_manifest(tmp_path)
        m.increment_api_usage("kling_video", 3)
        assert m.data["api_usage"]["kling_video"] == 3
        m.increment_api_usage("kling_video")
        assert m.data["api_usage"]["kling_video"] == 4

    def test_increment_api_usage_default_count(self, tmp_path):
        m = self._make_manifest(tmp_path)
        m.increment_api_usage("elevenlabs_calls")
        assert m.data["api_usage"]["elevenlabs_calls"] == 1

    def test_record_phase_timing_start(self, tmp_path):
        m = self._make_manifest(tmp_path)
        m.record_phase_timing("voiceover", started_at="2026-03-11T10:00:00Z")
        assert m.data["phase_timing"]["voiceover"]["started_at"] == "2026-03-11T10:00:00Z"

    def test_record_phase_timing_complete(self, tmp_path):
        m = self._make_manifest(tmp_path)
        m.record_phase_timing("voiceover", started_at="2026-03-11T10:00:00Z")
        m.record_phase_timing("voiceover", completed_at="2026-03-11T10:30:00Z")
        timing = m.data["phase_timing"]["voiceover"]
        assert timing["started_at"] == "2026-03-11T10:00:00Z"
        assert timing["completed_at"] == "2026-03-11T10:30:00Z"

    def test_increment_retry(self, tmp_path):
        m = self._make_manifest(tmp_path)
        m.increment_retry("scene_01", "video")
        assert m.data["retry_counts"]["scene_01"]["video"] == 1
        m.increment_retry("scene_01", "video")
        assert m.data["retry_counts"]["scene_01"]["video"] == 2

    def test_increment_retry_different_types(self, tmp_path):
        m = self._make_manifest(tmp_path)
        m.increment_retry("scene_01", "video")
        m.increment_retry("scene_01", "audio")
        assert m.data["retry_counts"]["scene_01"]["video"] == 1
        assert m.data["retry_counts"]["scene_01"]["audio"] == 1
