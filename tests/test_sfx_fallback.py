"""Tests for SFX fallback when Kling audio fails compliance."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestApplySfxFallback:
    """Test apply_sfx_fallback() logic."""

    def _setup_project(self, tmpdir):
        """Create minimal project structure with SFX library."""
        project_dir = Path(tmpdir) / "test_project"
        clips_dir = project_dir / "video" / "clips"
        sfx_dir = project_dir / "audio" / "sfx"
        clips_dir.mkdir(parents=True)
        sfx_dir.mkdir(parents=True)

        # Create fake SFX files
        (sfx_dir / "ambient_wind.mp3").write_bytes(b"sfx_data")
        (sfx_dir / "transition_whoosh.mp3").write_bytes(b"sfx_data")

        # Create fake video clips
        (clips_dir / "scene_01.mp4").write_bytes(b"video_data")
        (clips_dir / "scene_03.mp4").write_bytes(b"video_data")

        return str(project_dir)

    def test_returns_list_of_applied_scenes(self):
        from scripts.generate_voiceover_segments import apply_sfx_fallback

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._setup_project(tmpdir)
            result = apply_sfx_fallback(
                project_dir=project_dir,
                failed_scenes=["scene_01", "scene_03"],
            )

        assert isinstance(result, list)
        # Should return scene IDs where fallback was applied
        assert "scene_01" in result
        assert "scene_03" in result

    def test_returns_empty_for_no_failed_scenes(self):
        from scripts.generate_voiceover_segments import apply_sfx_fallback

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._setup_project(tmpdir)
            result = apply_sfx_fallback(
                project_dir=project_dir,
                failed_scenes=[],
            )

        assert result == []

    def test_logs_fallback_application(self, caplog):
        from scripts.generate_voiceover_segments import apply_sfx_fallback
        import logging

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._setup_project(tmpdir)
            with caplog.at_level(logging.INFO):
                apply_sfx_fallback(
                    project_dir=project_dir,
                    failed_scenes=["scene_01"],
                )

        assert any("SFX fallback applied" in msg for msg in caplog.messages)
