"""Tests for add_sound() integration in batch_generate.py with SFX fallback."""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from video.kling.batch_generate import _apply_kling_audio


class TestApplyKlingAudio:
    """Test _apply_kling_audio() helper in batch_generate.py."""

    def _make_client(self, use_proxy=True):
        client = MagicMock()
        client.use_proxy = use_proxy
        client.add_sound.return_value = "/output/scene_01_harbor_with_audio.mp4"
        return client

    def _make_manifest(self):
        manifest = MagicMock()
        return manifest

    def _make_audio_design(self, scene_key="scene_01", classification="ambient"):
        return {
            scene_key: {
                "type": classification,
                "layers": [],
            }
        }

    def test_add_sound_called_for_non_silent_scene(self):
        """add_sound is called for scenes classified as non-silent."""
        client = self._make_client()
        manifest = self._make_manifest()
        audio_design = self._make_audio_design("scene_01", "ambient")

        _apply_kling_audio(
            client=client,
            scene_num="01",
            video_url="https://cdn.example.com/video.mp4",
            output_path="/output/scene_01_with_audio.mp4",
            manifest=manifest,
            audio_design=audio_design,
        )

        client.add_sound.assert_called_once_with(
            "https://cdn.example.com/video.mp4",
            "/output/scene_01_with_audio.mp4",
        )

    def test_add_sound_skipped_for_silent_scene(self):
        """add_sound is NOT called for silent scenes."""
        client = self._make_client()
        manifest = self._make_manifest()
        audio_design = self._make_audio_design("scene_01", "silent")

        _apply_kling_audio(
            client=client,
            scene_num="01",
            video_url="https://cdn.example.com/video.mp4",
            output_path="/output/scene_01_with_audio.mp4",
            manifest=manifest,
            audio_design=audio_design,
        )

        client.add_sound.assert_not_called()

    def test_add_sound_skipped_when_not_proxy(self):
        """add_sound is NOT called when using direct backend."""
        client = self._make_client(use_proxy=False)
        manifest = self._make_manifest()
        audio_design = self._make_audio_design("scene_01", "ambient")

        _apply_kling_audio(
            client=client,
            scene_num="01",
            video_url="https://cdn.example.com/video.mp4",
            output_path="/output/scene_01_with_audio.mp4",
            manifest=manifest,
            audio_design=audio_design,
        )

        client.add_sound.assert_not_called()

    @patch("video.kling.batch_generate.apply_sfx_to_clip")
    def test_add_sound_failure_logs_warning_and_records_fallback(self, mock_apply_sfx, caplog):
        """add_sound failure triggers warning log, manifest records fallback, and apply_sfx is called."""
        client = self._make_client()
        client.add_sound.side_effect = RuntimeError("API timeout")
        manifest = self._make_manifest()
        audio_design = self._make_audio_design("scene_01", "ambient")

        with caplog.at_level(logging.WARNING):
            _apply_kling_audio(
                client=client,
                scene_num="01",
                video_url="https://cdn.example.com/video.mp4",
                output_path="/output/scene_01_harbor_with_audio.mp4",
                manifest=manifest,
                audio_design=audio_design,
            )

        # Check warning was logged
        assert any("add_sound failed" in r.message for r in caplog.records)

        # Check manifest records fallback
        call_kwargs = manifest.update_clip.call_args[1]
        assert call_kwargs["kling_audio_fallback"] == "sfx"
        assert "API timeout" in call_kwargs["kling_audio_error"]

        # Check apply_sfx was called with correct args
        mock_apply_sfx.assert_called_once_with(
            "scene_01",
            audio_design["scene_01"],
            Path("/output/scene_01_harbor.mp4"),
        )

    @patch("video.kling.batch_generate.apply_sfx_to_clip")
    def test_sfx_fallback_double_fault_is_caught(self, mock_apply_sfx, caplog):
        """If apply_sfx itself raises inside the fallback, exception is caught and logged."""
        client = self._make_client()
        client.add_sound.side_effect = RuntimeError("API timeout")
        mock_apply_sfx.side_effect = OSError("ffmpeg not found")
        manifest = self._make_manifest()
        audio_design = self._make_audio_design("scene_01", "ambient")

        with caplog.at_level(logging.WARNING):
            # Should NOT raise despite double fault
            _apply_kling_audio(
                client=client,
                scene_num="01",
                video_url="https://cdn.example.com/video.mp4",
                output_path="/output/scene_01_harbor_with_audio.mp4",
                manifest=manifest,
                audio_design=audio_design,
            )

        # apply_sfx was called (and raised)
        mock_apply_sfx.assert_called_once()

        # Double-fault was logged
        assert any("SFX fallback also failed" in r.message for r in caplog.records)

    def test_manifest_increment_api_usage_on_success(self):
        """manifest.increment_api_usage called on add_sound success."""
        client = self._make_client()
        manifest = self._make_manifest()
        audio_design = self._make_audio_design("scene_01", "ambient")

        _apply_kling_audio(
            client=client,
            scene_num="01",
            video_url="https://cdn.example.com/video.mp4",
            output_path="/output/scene_01_with_audio.mp4",
            manifest=manifest,
            audio_design=audio_design,
        )

        manifest.increment_api_usage.assert_called_once_with("kling_audio", 1)

    def test_manifest_records_audio_path_on_success(self):
        """manifest.update_clip records kling_audio_path on success."""
        client = self._make_client()
        client.add_sound.return_value = "/output/scene_01_with_audio.mp4"
        manifest = self._make_manifest()
        audio_design = self._make_audio_design("scene_01", "ambient")

        _apply_kling_audio(
            client=client,
            scene_num="01",
            video_url="https://cdn.example.com/video.mp4",
            output_path="/output/scene_01_with_audio.mp4",
            manifest=manifest,
            audio_design=audio_design,
        )

        manifest.update_clip.assert_called_once_with(
            "01", kling_audio_path="/output/scene_01_with_audio.mp4"
        )

    def test_graceful_handling_no_audio_design(self):
        """When audio_design is None, add_sound is skipped entirely."""
        client = self._make_client()
        manifest = self._make_manifest()

        _apply_kling_audio(
            client=client,
            scene_num="01",
            video_url="https://cdn.example.com/video.mp4",
            output_path="/output/scene_01_with_audio.mp4",
            manifest=manifest,
            audio_design=None,
        )

        client.add_sound.assert_not_called()

    def test_scene_not_in_audio_design_skips(self):
        """When scene is not in audio_design, it is skipped."""
        client = self._make_client()
        manifest = self._make_manifest()
        audio_design = self._make_audio_design("scene_99", "ambient")

        _apply_kling_audio(
            client=client,
            scene_num="01",
            video_url="https://cdn.example.com/video.mp4",
            output_path="/output/scene_01_with_audio.mp4",
            manifest=manifest,
            audio_design=audio_design,
        )

        client.add_sound.assert_not_called()


class TestVideoUrlInManifest:
    """Test that video_url is stored in manifest after successful generation."""

    def test_last_video_url_stored_after_poll(self):
        """KlingClient stores last_video_url after successful _poll_until_done."""
        from video.kling.api_client import KlingClient

        client = KlingClient.__new__(KlingClient)
        client.use_proxy = True
        client.base_url = "https://api.useapi.net/v1/kling"
        client.api_key = "test"
        client._semaphore = MagicMock()
        client._jwt_lock = MagicMock()

        poll_response = {
            "status_name": "succeed",
            "works": [{"url": "https://cdn.example.com/video.mp4"}],
        }

        with patch.object(client, "_poll_once", return_value=poll_response), \
             patch.object(client, "_download"), \
             patch("time.sleep"):
            result = client._poll_until_done("task-123", "/tmp/out.mp4")

        assert client.last_video_url == "https://cdn.example.com/video.mp4"
