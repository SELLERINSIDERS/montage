"""Tests for SFX script parametrization (--project flag) and batch_render_audio deprecation."""

import json
import subprocess
import sys
import warnings
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ── apply_sfx_to_clips parametrization ──


class TestApplySfxToClipsParametrize:
    """Test that apply_sfx_to_clips.py derives paths from --project flag."""

    def test_project_flag_derives_clips_dir(self, tmp_path):
        """--project flag builds correct clips_dir path."""
        project = tmp_path / "vsl" / "nightcap"
        project.mkdir(parents=True)
        (project / "video" / "clips").mkdir(parents=True)
        (project / "manifest").mkdir(parents=True)
        audio_design = project / "manifest" / "audio_design.json"
        audio_design.write_text(json.dumps({"scenes": {}}))

        from scripts.apply_sfx_to_clips import build_paths

        paths = build_paths(str(project))
        assert paths["clips_dir"] == project / "video" / "clips"
        assert paths["audio_design"] == project / "manifest" / "audio_design.json"

    def test_project_flag_required(self):
        """Main raises SystemExit when --project is missing."""
        from scripts.apply_sfx_to_clips import main

        with patch("sys.argv", ["apply_sfx_to_clips.py"]):
            with pytest.raises(SystemExit):
                main()

    def test_sfx_dir_is_shared_constant(self):
        """SFX_DIR stays at shared library path regardless of --project value."""
        from scripts.apply_sfx_to_clips import SFX_DIR

        assert SFX_DIR == Path("video/remotion-video/public/sfx")

    def test_error_when_project_dir_missing(self, tmp_path):
        """Clear error when --project directory doesn't exist."""
        from scripts.apply_sfx_to_clips import build_paths

        with pytest.raises(FileNotFoundError):
            build_paths(str(tmp_path / "nonexistent" / "project"))

    def test_no_hardcoded_cleopatra_refs(self):
        """No hardcoded references to cleopatra in apply_sfx_to_clips.py."""
        source = (Path(__file__).parent.parent / "scripts" / "apply_sfx_to_clips.py").read_text()
        assert "cleopatra" not in source.lower()
        assert "vsl_cleopatra" not in source


# ── reapply_sfx_single parametrization ──


class TestReapplySfxSingleParametrize:
    """Test that reapply_sfx_single.py derives paths from --project and --scene flags."""

    def test_project_and_scene_flags_derive_paths(self, tmp_path):
        """--project and --scene flags build correct paths."""
        project = tmp_path / "vsl" / "nightcap"
        project.mkdir(parents=True)
        (project / "video" / "clips").mkdir(parents=True)
        (project / "manifest").mkdir(parents=True)
        audio_design = project / "manifest" / "audio_design.json"
        audio_design.write_text(json.dumps({"scenes": {}}))

        from scripts.reapply_sfx_single import build_paths

        paths = build_paths(str(project))
        assert paths["clips_dir"] == project / "video" / "clips"
        assert paths["audio_design"] == project / "manifest" / "audio_design.json"

    def test_project_flag_required(self):
        """Main raises SystemExit when --project is missing."""
        from scripts.reapply_sfx_single import main

        with patch("sys.argv", ["reapply_sfx_single.py"]):
            with pytest.raises(SystemExit):
                main()

    def test_scene_flag_required(self):
        """Main raises SystemExit when --scene is missing."""
        from scripts.reapply_sfx_single import main

        with patch("sys.argv", ["reapply_sfx_single.py", "--project", "vsl/nightcap"]):
            with pytest.raises(SystemExit):
                main()

    def test_sfx_dir_is_shared_constant(self):
        """SFX_DIR stays at shared library path."""
        from scripts.reapply_sfx_single import SFX_DIR

        assert SFX_DIR == Path("video/remotion-video/public/sfx")

    def test_error_when_project_dir_missing(self, tmp_path):
        """Clear error when --project directory doesn't exist."""
        from scripts.reapply_sfx_single import build_paths

        with pytest.raises(FileNotFoundError):
            build_paths(str(tmp_path / "nonexistent" / "project"))

    def test_no_hardcoded_cleopatra_refs(self):
        """No hardcoded references to cleopatra in reapply_sfx_single.py."""
        source = (Path(__file__).parent.parent / "scripts" / "reapply_sfx_single.py").read_text()
        assert "cleopatra" not in source.lower()
        assert "vsl_cleopatra" not in source


# ── batch_render_audio deprecation ──


class TestBatchRenderAudioDeprecation:
    """Test that batch_render_audio.py emits DeprecationWarning."""

    def test_deprecation_warning_in_module(self):
        """batch_render_audio.py has deprecation docstring."""
        source = (Path(__file__).parent.parent / "scripts" / "batch_render_audio.py").read_text()
        assert "DEPRECATED" in source

    def test_deprecation_warning_emitted(self):
        """main() emits DeprecationWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Import and call main with mocked dependencies to trigger the warning
            from scripts.batch_render_audio import emit_deprecation_warning
            emit_deprecation_warning()

            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) >= 1
            assert "deprecated" in str(deprecation_warnings[0].message).lower()
