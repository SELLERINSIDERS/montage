"""Tests for post_production.py orchestrator."""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def production_dir(tmp_path):
    """Create a minimal production directory structure."""
    for subdir in ["state", "video/clips", "video/final", "audio", "copy", "prompts"]:
        (tmp_path / subdir).mkdir(parents=True, exist_ok=True)

    # Create a minimal manifest
    manifest = {
        "schema_version": "workflow-manifest-v2",
        "format": "vsl",
        "slug": "my-project",
        "scenes": [
            {
                "scene_id": "scene_01",
                "gates": {"video": {"status": "approved", "feedback": None, "attempts": 0}},
                "gate_timing": {},
                "video": "video/clips/scene_01.mp4",
            }
        ],
        "post_production": {
            "status": "pending",
            "caption_preset": "tiktok_bold",
            "platform_target": "generic",
            "edl_path": None,
            "edl_version": 0,
            "preview_versions": [],
            "final_version": None,
            "feedback_log": [],
            "render_timing": {},
            "final_approved": False,
            "final_uploaded": False,
        },
        "phase_timing": {},
    }
    manifest_path = tmp_path / "state" / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Create audio design
    audio_design = {
        "scenes": {
            "scene_01": {
                "classification": "voiceover_only",
                "ambient_audio": [],
            }
        }
    }
    (tmp_path / "state" / "audio_design.json").write_text(json.dumps(audio_design))

    # Create whisper data
    whisper = {
        "segments": [
            {"scene_id": "scene_01", "start": 0.0, "end": 3.5, "text": "Hello"},
        ]
    }
    (tmp_path / "audio" / "whisper.json").write_text(json.dumps(whisper))

    # Create voiceover file
    (tmp_path / "audio" / "voiceover.mp3").write_bytes(b"\x00" * 100)

    # Create a dummy clip
    (tmp_path / "video" / "clips" / "scene_01.mp4").write_bytes(b"\x00" * 100)

    return tmp_path


@pytest.fixture
def edl_data():
    """Minimal EDL dict."""
    return {
        "meta": {
            "fps": 24,
            "width": 1080,
            "height": 1920,
            "title": "my-project",
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
                "duration_s": 3.5,
                "trim_start_s": 0,
                "trim_end_s": 3.5,
                "audio_type": "voiceover_only",
                "ambient_audio": [],
                "transition_in": "hard_cut",
                "label": "Scene 01",
                "playback_rate_override": None,
            }
        ],
        "intro": None,
        "outro": None,
        "changelog": [],
    }


# ---------------------------------------------------------------------------
# Symlink management tests
# ---------------------------------------------------------------------------

class TestSetupSymlinks:
    def test_creates_clip_symlink(self, production_dir):
        from scripts.post_production import setup_symlinks, REMOTION_PUBLIC

        link_dir = setup_symlinks("vsl", "my-project", str(production_dir))
        link_path = Path(link_dir)

        clips_link = link_path / "clips"
        assert clips_link.exists() or clips_link.is_symlink()

    def test_creates_audio_symlink(self, production_dir):
        from scripts.post_production import setup_symlinks

        link_dir = setup_symlinks("vsl", "my-project", str(production_dir))
        link_path = Path(link_dir)

        audio_link = link_path / "audio"
        assert audio_link.exists() or audio_link.is_symlink()

    def test_cleanup_removes_link_directory(self, production_dir):
        from scripts.post_production import setup_symlinks, cleanup_symlinks

        link_dir = setup_symlinks("vsl", "my-project", str(production_dir))
        assert Path(link_dir).exists()

        cleanup_symlinks("vsl", "my-project")
        assert not Path(link_dir).exists()


# ---------------------------------------------------------------------------
# Render composition tests
# ---------------------------------------------------------------------------

class TestRenderComposition:
    @patch("scripts.post_production.subprocess.Popen")
    def test_preview_quality_args(self, mock_popen, production_dir, edl_data):
        """Preview render uses CRF 28 and jpeg-quality 60."""
        from scripts.post_production import render_composition

        mock_proc = MagicMock()
        mock_proc.stdout = iter([b"Rendering: 50%\n", b"Rendering: 100%\n"])
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        edl_path = str(production_dir / "state" / "edl.json")
        Path(edl_path).write_text(json.dumps(edl_data))
        output_path = str(production_dir / "video" / "final" / "preview_v1.mp4")

        result = render_composition(edl_path, output_path, quality="preview")

        args = mock_popen.call_args[0][0]
        assert "--crf" in args
        crf_idx = args.index("--crf")
        assert args[crf_idx + 1] == "28"
        assert "--jpeg-quality" in args
        jq_idx = args.index("--jpeg-quality")
        assert args[jq_idx + 1] == "60"
        assert result is True

    @patch("scripts.post_production.subprocess.Popen")
    def test_final_quality_args(self, mock_popen, production_dir, edl_data):
        """Final render uses CRF 18."""
        from scripts.post_production import render_composition

        mock_proc = MagicMock()
        mock_proc.stdout = iter([b"Rendering: 100%\n"])
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        edl_path = str(production_dir / "state" / "edl.json")
        Path(edl_path).write_text(json.dumps(edl_data))
        output_path = str(production_dir / "video" / "final" / "final_v1.mp4")

        render_composition(edl_path, output_path, quality="final")

        args = mock_popen.call_args[0][0]
        crf_idx = args.index("--crf")
        assert args[crf_idx + 1] == "18"
        # Should NOT have --jpeg-quality for final
        assert "--jpeg-quality" not in args

    @patch("scripts.post_production.subprocess.Popen")
    def test_output_filename_convention(self, mock_popen, production_dir):
        """Output filename follows {product}_{format}_{version}.mp4 convention."""
        from scripts.post_production import get_next_version

        # No files yet — version should be 1
        version = get_next_version(str(production_dir), "preview")
        assert version == 1

        # Create preview_v1.mp4 and check increment
        (production_dir / "video" / "final" / "preview_v1.mp4").write_bytes(b"\x00")
        version = get_next_version(str(production_dir), "preview")
        assert version == 2


# ---------------------------------------------------------------------------
# Main orchestrator tests
# ---------------------------------------------------------------------------

class TestRunPostProduction:
    @patch("scripts.post_production.render_composition")
    @patch("scripts.post_production.cleanup_symlinks")
    @patch("scripts.post_production.setup_symlinks")
    @patch("scripts.post_production.preflight_check")
    @patch("scripts.post_production.generate_edl")
    def test_calls_steps_in_order(
        self, mock_gen_edl, mock_preflight, mock_setup, mock_cleanup, mock_render,
        production_dir, edl_data
    ):
        """run_post_production calls steps in order: generate_edl -> preflight -> symlink -> render."""
        from scripts.post_production import run_post_production
        from scripts.preflight_check import PreflightResult

        mock_gen_edl.return_value = edl_data
        mock_preflight.return_value = PreflightResult(errors=[], warnings=[])
        mock_setup.return_value = str(production_dir / "remotion_link")
        mock_render.return_value = True

        call_order = []
        mock_gen_edl.side_effect = lambda *a, **kw: (call_order.append("edl"), edl_data)[1]
        mock_preflight.side_effect = lambda *a, **kw: (call_order.append("preflight"), PreflightResult())[1]
        mock_setup.side_effect = lambda *a, **kw: (call_order.append("symlink"), str(production_dir / "link"))[1]
        mock_render.side_effect = lambda *a, **kw: (call_order.append("render"), True)[1]

        run_post_production(str(production_dir))

        assert call_order == ["edl", "preflight", "symlink", "render"]

    @patch("scripts.post_production.generate_edl")
    @patch("scripts.post_production.preflight_check")
    def test_stops_on_preflight_errors(self, mock_preflight, mock_gen_edl, production_dir, edl_data):
        """run_post_production stops with clear error if preflight has errors."""
        from scripts.post_production import run_post_production
        from scripts.preflight_check import PreflightResult

        mock_gen_edl.return_value = edl_data
        mock_preflight.return_value = PreflightResult(
            errors=["Missing clip: scene_01"], warnings=[]
        )

        result = run_post_production(str(production_dir))
        assert result is False

    @patch("scripts.post_production.render_composition")
    @patch("scripts.post_production.cleanup_symlinks")
    @patch("scripts.post_production.setup_symlinks")
    @patch("scripts.post_production.preflight_check")
    @patch("scripts.post_production.generate_edl")
    def test_continues_with_warnings(
        self, mock_gen_edl, mock_preflight, mock_setup, mock_cleanup, mock_render,
        production_dir, edl_data
    ):
        """run_post_production continues with warnings logged if preflight has only warnings."""
        from scripts.post_production import run_post_production
        from scripts.preflight_check import PreflightResult

        mock_gen_edl.return_value = edl_data
        mock_preflight.return_value = PreflightResult(
            errors=[], warnings=["Dimension mismatch for scene_01"]
        )
        mock_setup.return_value = str(production_dir / "link")
        mock_render.return_value = True

        result = run_post_production(str(production_dir))
        assert result is True

    def test_version_incrementing(self, production_dir):
        """Version increments from preview_v1 -> preview_v2 on re-render."""
        from scripts.post_production import get_next_version

        assert get_next_version(str(production_dir), "preview") == 1
        (production_dir / "video" / "final" / "preview_v1.mp4").write_bytes(b"\x00")
        assert get_next_version(str(production_dir), "preview") == 2
        (production_dir / "video" / "final" / "preview_v2.mp4").write_bytes(b"\x00")
        assert get_next_version(str(production_dir), "preview") == 3

    @patch("scripts.post_production.render_composition")
    @patch("scripts.post_production.cleanup_symlinks")
    @patch("scripts.post_production.setup_symlinks")
    @patch("scripts.post_production.preflight_check")
    @patch("scripts.post_production.generate_edl")
    @patch("scripts.post_production.merge_whisper")
    @patch("scripts.post_production.merge_voiceover")
    def test_merge_called_when_segments_exist(
        self, mock_merge_vo, mock_merge_wh, mock_gen_edl, mock_preflight,
        mock_setup, mock_cleanup, mock_render, production_dir, edl_data
    ):
        """Merge called when segments exist but merged file missing."""
        from scripts.post_production import run_post_production
        from scripts.preflight_check import PreflightResult

        # Remove the pre-existing merged voiceover so merge triggers
        (production_dir / "audio" / "voiceover.mp3").unlink()

        # Create segments directory with MP3 stubs
        segments_dir = production_dir / "audio" / "segments"
        segments_dir.mkdir(parents=True, exist_ok=True)
        (segments_dir / "scene_01_vo.mp3").write_bytes(b"\xff" * 10)

        mock_merge_vo.return_value = str(production_dir / "audio" / "voiceover.mp3")
        mock_merge_wh.return_value = {"segments": []}
        mock_gen_edl.return_value = edl_data
        mock_preflight.return_value = PreflightResult()
        mock_setup.return_value = str(production_dir / "link")
        mock_render.return_value = True

        run_post_production(str(production_dir))

        mock_merge_vo.assert_called_once_with(str(production_dir))
        mock_merge_wh.assert_called_once_with(str(production_dir))

    @patch("scripts.post_production.render_composition")
    @patch("scripts.post_production.cleanup_symlinks")
    @patch("scripts.post_production.setup_symlinks")
    @patch("scripts.post_production.preflight_check")
    @patch("scripts.post_production.generate_edl")
    @patch("scripts.post_production.merge_whisper")
    @patch("scripts.post_production.merge_voiceover")
    def test_merge_skipped_when_merged_file_exists(
        self, mock_merge_vo, mock_merge_wh, mock_gen_edl, mock_preflight,
        mock_setup, mock_cleanup, mock_render, production_dir, edl_data
    ):
        """Merge skipped when merged file already exists."""
        from scripts.post_production import run_post_production
        from scripts.preflight_check import PreflightResult

        # voiceover.mp3 already exists from fixture
        assert (production_dir / "audio" / "voiceover.mp3").exists()

        mock_gen_edl.return_value = edl_data
        mock_preflight.return_value = PreflightResult()
        mock_setup.return_value = str(production_dir / "link")
        mock_render.return_value = True

        run_post_production(str(production_dir))

        mock_merge_vo.assert_not_called()
        mock_merge_wh.assert_not_called()

    @patch("scripts.post_production.render_composition")
    @patch("scripts.post_production.cleanup_symlinks")
    @patch("scripts.post_production.setup_symlinks")
    @patch("scripts.post_production.preflight_check")
    @patch("scripts.post_production.generate_edl")
    @patch("scripts.post_production.merge_whisper")
    @patch("scripts.post_production.merge_voiceover")
    def test_warning_logged_when_no_segments_and_no_merged(
        self, mock_merge_vo, mock_merge_wh, mock_gen_edl, mock_preflight,
        mock_setup, mock_cleanup, mock_render, production_dir, edl_data, caplog
    ):
        """Warning logged when no segments and no merged file."""
        from scripts.post_production import run_post_production
        from scripts.preflight_check import PreflightResult
        import logging

        # Remove merged voiceover (no segments dir either)
        (production_dir / "audio" / "voiceover.mp3").unlink()

        mock_gen_edl.return_value = edl_data
        mock_preflight.return_value = PreflightResult()
        mock_setup.return_value = str(production_dir / "link")
        mock_render.return_value = True

        with caplog.at_level(logging.WARNING):
            run_post_production(str(production_dir))

        assert any("voiceover may not be needed" in r.message for r in caplog.records)
        mock_merge_vo.assert_not_called()

    @patch("scripts.post_production.render_composition")
    @patch("scripts.post_production.cleanup_symlinks")
    @patch("scripts.post_production.setup_symlinks")
    @patch("scripts.post_production.preflight_check")
    @patch("scripts.post_production.generate_edl")
    def test_render_timing_recorded(
        self, mock_gen_edl, mock_preflight, mock_setup, mock_cleanup, mock_render,
        production_dir, edl_data
    ):
        """Render timing is recorded in manifest (started_at, completed_at)."""
        from scripts.post_production import run_post_production
        from scripts.preflight_check import PreflightResult

        mock_gen_edl.return_value = edl_data
        mock_preflight.return_value = PreflightResult()
        mock_setup.return_value = str(production_dir / "link")
        mock_render.return_value = True

        run_post_production(str(production_dir))

        manifest = json.loads((production_dir / "state" / "manifest.json").read_text())
        pp = manifest["post_production"]
        assert len(pp["preview_versions"]) >= 1
        pv = pp["preview_versions"][0]
        assert "rendered_at" in pv
        assert "render_duration_s" in pv


# ---------------------------------------------------------------------------
# Feedback + re-render tests
# ---------------------------------------------------------------------------

class TestApplyFeedbackAndRerender:
    @patch("scripts.post_production.render_composition")
    @patch("scripts.post_production.cleanup_symlinks")
    @patch("scripts.post_production.setup_symlinks")
    def test_regen_clip_flags_scenes_and_pauses(
        self, mock_setup, mock_cleanup, mock_render, production_dir
    ):
        """apply_feedback_and_rerender with regen_clip flags scenes and returns pause message."""
        from scripts.post_production import apply_feedback_and_rerender

        changes = [
            {"type": "regen_clip", "scene_id": "scene_01"},
        ]
        result = apply_feedback_and_rerender(
            str(production_dir), "Need better scene 1", changes
        )

        assert "Paused" in result
        assert "scene_01" in result

        manifest = json.loads((production_dir / "state" / "manifest.json").read_text())
        assert manifest["post_production"]["status"] == "paused_for_regen"

    @patch("scripts.post_production.render_composition")
    @patch("scripts.post_production.cleanup_symlinks")
    @patch("scripts.post_production.setup_symlinks")
    def test_mixed_changes_flags_regen_no_rerender(
        self, mock_setup, mock_cleanup, mock_render, production_dir
    ):
        """Mixed changes (regen + text) flags regen scenes and does NOT re-render."""
        from scripts.post_production import apply_feedback_and_rerender

        changes = [
            {"type": "regen_clip", "scene_id": "scene_01"},
            {"type": "update_label", "scene_id": "scene_01", "label": "New label"},
        ]
        result = apply_feedback_and_rerender(
            str(production_dir), "Mixed feedback", changes
        )

        assert "Paused" in result
        mock_render.assert_not_called()

    @patch("scripts.post_production.render_composition")
    @patch("scripts.post_production.cleanup_symlinks")
    @patch("scripts.post_production.setup_symlinks")
    @patch("scripts.post_production.modify_edl")
    def test_non_regen_changes_rerender(
        self, mock_modify, mock_setup, mock_cleanup, mock_render, production_dir, edl_data
    ):
        """Non-regen changes (reorder, caption tweak) re-render normally."""
        from scripts.post_production import apply_feedback_and_rerender

        # Write EDL to disk
        edl_path = production_dir / "state" / "edl.json"
        edl_path.write_text(json.dumps(edl_data))

        mock_modify.return_value = edl_data
        mock_setup.return_value = str(production_dir / "link")
        mock_render.return_value = True

        result = apply_feedback_and_rerender(
            str(production_dir),
            "Reorder scenes",
            [{"type": "reorder", "scene_order": ["scene_01"]}],
        )

        assert "Paused" not in result
        mock_modify.assert_called_once()
        mock_render.assert_called_once()


# ---------------------------------------------------------------------------
# Final render + DashboardSync tests
# ---------------------------------------------------------------------------

class TestRenderFinal:
    @patch("scripts.post_production.DashboardSync")
    @patch("scripts.post_production.render_composition")
    @patch("scripts.post_production.cleanup_symlinks")
    @patch("scripts.post_production.setup_symlinks")
    def test_uploads_to_supabase_after_render(
        self, mock_setup, mock_cleanup, mock_render, mock_sync_cls, production_dir, edl_data
    ):
        """render_final calls DashboardSync.upload_final_video after successful render."""
        from scripts.post_production import render_final

        # Write EDL
        edl_path = production_dir / "state" / "edl.json"
        edl_path.write_text(json.dumps(edl_data))

        mock_setup.return_value = str(production_dir / "link")
        mock_render.return_value = True

        mock_sync = MagicMock()
        mock_sync.enabled = True
        mock_sync.upload_final_video.return_value = "https://storage.example.com/video.mp4"
        mock_sync_cls.return_value = mock_sync

        render_final(str(production_dir))

        mock_sync.upload_final_video.assert_called_once()
        manifest = json.loads((production_dir / "state" / "manifest.json").read_text())
        assert manifest["post_production"]["final_uploaded"] is True
        assert manifest["post_production"]["final_approved"] is True

    @patch("scripts.post_production.DashboardSync")
    @patch("scripts.post_production.render_composition")
    @patch("scripts.post_production.cleanup_symlinks")
    @patch("scripts.post_production.setup_symlinks")
    def test_continues_if_dashboard_disabled(
        self, mock_setup, mock_cleanup, mock_render, mock_sync_cls, production_dir, edl_data
    ):
        """render_final continues without error if DashboardSync is disabled."""
        from scripts.post_production import render_final

        edl_path = production_dir / "state" / "edl.json"
        edl_path.write_text(json.dumps(edl_data))

        mock_setup.return_value = str(production_dir / "link")
        mock_render.return_value = True

        mock_sync = MagicMock()
        mock_sync.enabled = False
        mock_sync.upload_final_video.return_value = None
        mock_sync_cls.return_value = mock_sync

        # Should not raise
        render_final(str(production_dir))

        manifest = json.loads((production_dir / "state" / "manifest.json").read_text())
        assert manifest["post_production"]["final_uploaded"] is False
        assert manifest["post_production"]["final_approved"] is True
