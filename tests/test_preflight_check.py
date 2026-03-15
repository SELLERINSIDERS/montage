"""Tests for pre-flight asset validation before Remotion rendering.

Tests cover:
- Returns empty errors when all assets exist and dimensions match
- Returns error for each missing clip file
- Returns error for missing voiceover file
- Returns error for missing Whisper JSON
- Returns warning for clip dimensions not matching target format
- Returns warning when clip duration would require playback_rate below 0.5
- WorkflowManifest.create includes post_production section
- post_production status transitions
"""

import json
import os
import pytest
from unittest.mock import patch, MagicMock

from scripts.preflight_check import preflight_check, PreflightResult
from scripts.workflow_manifest import WorkflowManifest, CAPTION_PRESETS


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def production_dir(tmp_path):
    """Create a production directory with all expected assets."""
    clips_dir = tmp_path / "video" / "clips"
    clips_dir.mkdir(parents=True)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    return tmp_path


@pytest.fixture
def valid_edl(production_dir):
    """Create a valid EDL with 2 scenes and all asset files present."""
    # Create clip files
    (production_dir / "video" / "clips" / "scene_01.mp4").write_bytes(b"\x00")
    (production_dir / "video" / "clips" / "scene_02.mp4").write_bytes(b"\x00")
    # Create voiceover and whisper
    (production_dir / "audio" / "voiceover.mp3").write_bytes(b"\x00")
    (production_dir / "audio" / "whisper.json").write_text('{"segments": []}')

    edl = {
        "meta": {
            "fps": 24,
            "width": 1080,
            "height": 1920,
            "title": "test",
            "format": "vsl",
            "caption_preset": "tiktok_bold",
            "platform_target": "generic",
            "render_quality": "preview",
            "version": 1,
        },
        "voiceover": {
            "src": "audio/voiceover.mp3",
            "volume": 1.0,
            "whisper_data": "audio/whisper.json",
        },
        "scenes": [
            {
                "id": "scene_01",
                "clip_src": "video/clips/scene_01.mp4",
                "duration_s": 4.5,
                "trim_start_s": 0,
                "trim_end_s": 4.5,
                "audio_type": "voiceover_only",
                "ambient_audio": [],
                "transition_in": "hard_cut",
                "label": "Scene 01",
                "playback_rate_override": None,
            },
            {
                "id": "scene_02",
                "clip_src": "video/clips/scene_02.mp4",
                "duration_s": 5.0,
                "trim_start_s": 0,
                "trim_end_s": 5.0,
                "audio_type": "mixed",
                "ambient_audio": [],
                "transition_in": "hard_cut",
                "label": "Scene 02",
                "playback_rate_override": None,
            },
        ],
        "changelog": [],
    }
    return edl


def _mock_ffprobe_success(width=1080, height=1920, duration=5.0):
    """Create a mock for subprocess.run that returns ffprobe results."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = json.dumps({
        "streams": [{
            "width": width,
            "height": height,
            "duration": str(duration),
        }]
    })
    return result


# ── Test: Empty errors when all assets valid ─────────────────────────


class TestPreflightAllValid:
    """preflight_check returns empty errors when all assets exist."""

    @patch("subprocess.run")
    def test_no_errors_when_all_present(self, mock_run, valid_edl, production_dir):
        mock_run.return_value = _mock_ffprobe_success()
        result = preflight_check(valid_edl, str(production_dir))
        assert isinstance(result, PreflightResult)
        assert result.errors == []

    @patch("subprocess.run")
    def test_result_has_warnings_list(self, mock_run, valid_edl, production_dir):
        mock_run.return_value = _mock_ffprobe_success()
        result = preflight_check(valid_edl, str(production_dir))
        assert isinstance(result.warnings, list)


# ── Test: Missing clip files ─────────────────────────────────────────


class TestMissingClips:
    """preflight_check returns error for each missing clip file."""

    def test_error_for_missing_clip(self, valid_edl, production_dir):
        # Remove one clip
        os.remove(production_dir / "video" / "clips" / "scene_01.mp4")
        result = preflight_check(valid_edl, str(production_dir))
        assert len(result.errors) >= 1
        assert any("scene_01" in e for e in result.errors)

    def test_error_for_all_missing_clips(self, production_dir):
        # No clips exist
        edl = {
            "meta": {"width": 1080, "height": 1920},
            "voiceover": None,
            "scenes": [
                {
                    "id": "scene_01",
                    "clip_src": "video/clips/missing1.mp4",
                    "duration_s": 5.0,
                },
                {
                    "id": "scene_02",
                    "clip_src": "video/clips/missing2.mp4",
                    "duration_s": 5.0,
                },
            ],
        }
        result = preflight_check(edl, str(production_dir))
        assert len(result.errors) >= 2


# ── Test: Missing voiceover ──────────────────────────────────────────


class TestMissingVoiceover:
    """preflight_check returns error for missing voiceover file."""

    def test_error_for_missing_voiceover(self, valid_edl, production_dir):
        os.remove(production_dir / "audio" / "voiceover.mp3")
        result = preflight_check(valid_edl, str(production_dir))
        assert any("voiceover" in e.lower() for e in result.errors)


# ── Test: Missing Whisper JSON ───────────────────────────────────────


class TestMissingWhisper:
    """preflight_check returns error for missing Whisper JSON."""

    def test_error_for_missing_whisper(self, valid_edl, production_dir):
        os.remove(production_dir / "audio" / "whisper.json")
        result = preflight_check(valid_edl, str(production_dir))
        assert any("whisper" in e.lower() for e in result.errors)


# ── Test: Dimension mismatch warnings ────────────────────────────────


class TestDimensionMismatch:
    """preflight_check returns warning for dimension mismatch."""

    @patch("subprocess.run")
    def test_warning_for_wrong_dimensions(self, mock_run, valid_edl, production_dir):
        # Return wrong dimensions from ffprobe
        mock_run.return_value = _mock_ffprobe_success(width=1920, height=1080)
        result = preflight_check(valid_edl, str(production_dir))
        # Dimension mismatches are warnings, not errors (report-only per user decision)
        assert len(result.warnings) >= 1
        assert any("dimension" in w.lower() for w in result.warnings)


# ── Test: Playback rate warning ──────────────────────────────────────


class TestPlaybackRateWarning:
    """preflight_check returns warning for playback_rate below 0.5."""

    @patch("subprocess.run")
    def test_warning_for_slow_playback(self, mock_run, valid_edl, production_dir):
        # Clip is 2s but scene needs 10s => rate = 0.2 (below 0.5)
        mock_run.return_value = _mock_ffprobe_success(duration=2.0)
        # Set scene duration to 10s
        valid_edl["scenes"][0]["duration_s"] = 10.0
        result = preflight_check(valid_edl, str(production_dir))
        assert any("playback" in w.lower() for w in result.warnings)


# ── Test: Manifest post_production section ───────────────────────────


class TestManifestPostProduction:
    """WorkflowManifest.create includes post_production section."""

    def test_create_includes_post_production(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("vsl", "test", 3, path=path)
        assert "post_production" in data

    def test_post_production_initial_status(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("vsl", "test", 3, path=path)
        pp = data["post_production"]
        assert pp["status"] == "pending"
        assert pp["edl_version"] == 0
        assert pp["preview_versions"] == []
        assert pp["feedback_log"] == []
        assert pp["final_approved"] is False

    def test_post_production_has_caption_preset(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("vsl", "test", 3, path=path)
        pp = data["post_production"]
        assert pp["caption_preset"] == "tiktok_bold"

    def test_post_production_has_platform_target(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        data = WorkflowManifest.create("vsl", "test", 3, path=path)
        pp = data["post_production"]
        assert pp["platform_target"] == "generic"


# ── Test: Status transitions ─────────────────────────────────────────


class TestPostProductionStatusTransitions:
    """post_production status transitions correctly."""

    def test_update_status(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        WorkflowManifest.create("vsl", "test", 3, path=path)
        m = WorkflowManifest(path)
        m.update_post_production(status="generating_edl")
        assert m.data["post_production"]["status"] == "generating_edl"

    def test_record_preview_version(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        WorkflowManifest.create("vsl", "test", 3, path=path)
        m = WorkflowManifest(path)
        m.record_preview_version(1, "video/final/preview_v1.mp4", 120)
        pp = m.data["post_production"]
        assert len(pp["preview_versions"]) == 1
        assert pp["preview_versions"][0]["version"] == 1
        assert pp["preview_versions"][0]["path"] == "video/final/preview_v1.mp4"
        assert pp["preview_versions"][0]["render_duration_s"] == 120

    def test_record_feedback(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        WorkflowManifest.create("vsl", "test", 3, path=path)
        m = WorkflowManifest(path)
        m.record_feedback(1, "Scene 3 too dark", ["adjusted_brightness"])
        pp = m.data["post_production"]
        assert len(pp["feedback_log"]) == 1
        assert pp["feedback_log"][0]["version"] == 1
        assert pp["feedback_log"][0]["feedback"] == "Scene 3 too dark"

    def test_mark_final_approved(self, tmp_path):
        path = str(tmp_path / "manifest.json")
        WorkflowManifest.create("vsl", "test", 3, path=path)
        m = WorkflowManifest(path)
        m.mark_final_approved(3, "video/final/cadence_vsl_v3.mp4", 300)
        pp = m.data["post_production"]
        assert pp["final_approved"] is True
        assert pp["final_version"]["version"] == 3
        assert pp["status"] == "complete"

    def test_full_status_lifecycle(self, tmp_path):
        """Test all status transitions in order."""
        path = str(tmp_path / "manifest.json")
        WorkflowManifest.create("vsl", "test", 3, path=path)
        m = WorkflowManifest(path)

        statuses = [
            "generating_edl",
            "preflight",
            "rendering_preview",
            "review",
            "rendering_final",
            "complete",
        ]
        for status in statuses:
            m.update_post_production(status=status)
            assert m.data["post_production"]["status"] == status


# ── Test: Caption presets constant ───────────────────────────────────


class TestCaptionPresets:
    """CAPTION_PRESETS list is defined and correct."""

    def test_has_three_presets(self):
        assert len(CAPTION_PRESETS) == 3

    def test_contains_tiktok_bold(self):
        assert "tiktok_bold" in CAPTION_PRESETS

    def test_contains_clean_minimal(self):
        assert "clean_minimal" in CAPTION_PRESETS

    def test_contains_cinematic_subtle(self):
        assert "cinematic_subtle" in CAPTION_PRESETS
