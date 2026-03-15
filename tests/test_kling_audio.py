"""Tests for Kling audio API integration (enable_audio, add_sound, download_audio)."""

import os
import pytest
from unittest.mock import patch, MagicMock

from video.kling.api_client import KlingClient


# --- Fixtures ---


@pytest.fixture
def proxy_env(monkeypatch):
    """Set environment for UseAPI.net proxy mode."""
    monkeypatch.setenv("KLING_USE_PROXY", "true")
    monkeypatch.setenv("USEAPI_KEY", "test-useapi-key-123")


@pytest.fixture
def direct_env(monkeypatch):
    """Set environment for direct Kling API mode."""
    monkeypatch.setenv("KLING_USE_PROXY", "false")
    monkeypatch.setenv("KLING_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("KLING_SECRET_KEY", "test-secret-key-at-least-32chars!!")


# --- Task 1: enable_audio Tests ---


class TestEnableAudioDefault:
    """Test that enable_audio defaults to True in proxy payload."""

    @patch("video.kling.api_client.requests.get")
    @patch("video.kling.api_client.requests.post")
    def test_enable_audio_default(self, mock_post, mock_get, proxy_env):
        """Proxy payload should include enable_audio=True by default."""
        # Upload image response
        upload_resp = MagicMock()
        upload_resp.json.return_value = {"url": "https://cdn.useapi.net/img.png"}
        upload_resp.raise_for_status = MagicMock()

        # Submit response
        submit_resp = MagicMock()
        submit_resp.json.return_value = {"task": {"id": "audio-task-1"}}
        submit_resp.raise_for_status = MagicMock()

        mock_post.side_effect = [upload_resp, submit_resp]

        # Poll success
        poll_resp = MagicMock()
        poll_resp.json.return_value = {
            "status_name": "succeed",
            "works": [{"url": "https://cdn.useapi.net/video.mp4"}],
        }
        poll_resp.raise_for_status = MagicMock()

        download_resp = MagicMock()
        download_resp.raise_for_status = MagicMock()
        download_resp.iter_content.return_value = [b"video"]

        mock_get.side_effect = [poll_resp, download_resp]

        client = KlingClient()
        client.image_to_video(b"image-bytes", "test prompt", "/tmp/test_audio.mp4")

        # The second POST is the submit call
        submit_call = mock_post.call_args_list[1]
        payload = submit_call[1]["json"]
        assert payload["enable_audio"] is True


class TestEnableAudioDisabled:
    """Test that enable_audio=False is respected in proxy payload."""

    @patch("video.kling.api_client.requests.get")
    @patch("video.kling.api_client.requests.post")
    def test_enable_audio_disabled(self, mock_post, mock_get, proxy_env):
        """Proxy payload should include enable_audio=False when explicitly set."""
        upload_resp = MagicMock()
        upload_resp.json.return_value = {"url": "https://cdn.useapi.net/img.png"}
        upload_resp.raise_for_status = MagicMock()

        submit_resp = MagicMock()
        submit_resp.json.return_value = {"task": {"id": "silent-task-1"}}
        submit_resp.raise_for_status = MagicMock()

        mock_post.side_effect = [upload_resp, submit_resp]

        poll_resp = MagicMock()
        poll_resp.json.return_value = {
            "status_name": "succeed",
            "works": [{"url": "https://cdn.useapi.net/video.mp4"}],
        }
        poll_resp.raise_for_status = MagicMock()

        download_resp = MagicMock()
        download_resp.raise_for_status = MagicMock()
        download_resp.iter_content.return_value = [b"video"]

        mock_get.side_effect = [poll_resp, download_resp]

        client = KlingClient()
        client.image_to_video(
            b"image-bytes", "silent scene", "/tmp/test_silent.mp4",
            enable_audio=False,
        )

        submit_call = mock_post.call_args_list[1]
        payload = submit_call[1]["json"]
        assert payload["enable_audio"] is False


class TestEnableAudioDirectBackend:
    """Test that direct backend does NOT include enable_audio in payload."""

    @patch("video.kling.api_client.requests.get")
    @patch("video.kling.api_client.requests.post")
    def test_direct_no_enable_audio(self, mock_post, mock_get, direct_env):
        """Direct Kling API payload should NOT contain enable_audio."""
        submit_resp = MagicMock()
        submit_resp.json.return_value = {"data": {"task_id": "direct-task-1"}}
        submit_resp.raise_for_status = MagicMock()

        poll_resp = MagicMock()
        poll_resp.json.return_value = {
            "data": {
                "task_status": "succeed",
                "task_result": {"videos": [{"url": "https://example.com/v.mp4"}]},
            }
        }
        poll_resp.raise_for_status = MagicMock()

        download_resp = MagicMock()
        download_resp.raise_for_status = MagicMock()
        download_resp.iter_content.return_value = [b"video"]

        mock_post.return_value = submit_resp
        mock_get.side_effect = [poll_resp, download_resp]

        client = KlingClient()
        client.image_to_video(b"image", "prompt", "/tmp/test_direct.mp4")

        payload = mock_post.call_args[1]["json"]
        assert "enable_audio" not in payload


class TestBuildPrompt:
    """Test _build_prompt helper for appending audio context to video prompt."""

    def test_build_prompt_no_audio(self, proxy_env):
        """Without audio_prompt, returns original prompt unchanged."""
        client = KlingClient()
        result = KlingClient._build_prompt("camera pans across desert")
        assert result == "camera pans across desert"

    def test_build_prompt_with_audio(self, proxy_env):
        """With audio_prompt, appends in [Audio: ...] format."""
        result = KlingClient._build_prompt(
            "camera pans across desert",
            "wind howling, sand shifting",
        )
        assert result == "camera pans across desert [Audio: wind howling, sand shifting]"

    def test_build_prompt_none_audio(self, proxy_env):
        """None audio_prompt returns original prompt unchanged."""
        result = KlingClient._build_prompt("prompt text", None)
        assert result == "prompt text"

    def test_build_prompt_empty_audio(self, proxy_env):
        """Empty audio_prompt returns original prompt unchanged."""
        result = KlingClient._build_prompt("prompt text", "")
        assert result == "prompt text"


# --- Task 2: add_sound and download_audio Tests ---


class TestAddSound:
    """Test add_sound() method for post-process audio generation."""

    @patch("video.kling.api_client.requests.get")
    @patch("video.kling.api_client.requests.post")
    def test_add_sound_submits_and_polls(self, mock_post, mock_get, proxy_env):
        """add_sound should POST to /videos/add-sound and poll until done."""
        submit_resp = MagicMock()
        submit_resp.json.return_value = {"task": {"id": "sound-task-1"}}
        submit_resp.raise_for_status = MagicMock()
        mock_post.return_value = submit_resp

        poll_resp = MagicMock()
        poll_resp.json.return_value = {
            "status_name": "succeed",
            "works": [{"url": "https://cdn.useapi.net/video_with_audio.mp4"}],
        }
        poll_resp.raise_for_status = MagicMock()

        download_resp = MagicMock()
        download_resp.raise_for_status = MagicMock()
        download_resp.iter_content.return_value = [b"video-with-audio"]

        mock_get.side_effect = [poll_resp, download_resp]

        client = KlingClient()
        result = client.add_sound(
            "https://cdn.useapi.net/original.mp4",
            "/tmp/test_with_audio.mp4",
        )

        assert result == "/tmp/test_with_audio.mp4"
        # Verify submit was called with correct endpoint
        submit_url = mock_post.call_args[0][0]
        assert "/videos/add-sound" in submit_url
        payload = mock_post.call_args[1]["json"]
        assert payload["video"] == "https://cdn.useapi.net/original.mp4"

    @patch("video.kling.api_client.requests.get")
    @patch("video.kling.api_client.requests.post")
    def test_add_sound_crop_original(self, mock_post, mock_get, proxy_env):
        """add_sound with crop_original_sound=True should include in payload."""
        submit_resp = MagicMock()
        submit_resp.json.return_value = {"task": {"id": "crop-task-1"}}
        submit_resp.raise_for_status = MagicMock()
        mock_post.return_value = submit_resp

        poll_resp = MagicMock()
        poll_resp.json.return_value = {
            "status_name": "succeed",
            "works": [{"url": "https://cdn.useapi.net/cropped.mp4"}],
        }
        poll_resp.raise_for_status = MagicMock()

        download_resp = MagicMock()
        download_resp.raise_for_status = MagicMock()
        download_resp.iter_content.return_value = [b"video"]

        mock_get.side_effect = [poll_resp, download_resp]

        client = KlingClient()
        client.add_sound(
            "https://cdn.useapi.net/clip.mp4",
            "/tmp/test_crop.mp4",
            crop_original_sound=True,
        )

        payload = mock_post.call_args[1]["json"]
        assert payload["cropVideoOriginalSound"] is True

    def test_add_sound_none_url_raises(self, proxy_env):
        """add_sound should raise RuntimeError if video_url is None."""
        client = KlingClient()
        with pytest.raises(RuntimeError, match="video_url"):
            client.add_sound(None, "/tmp/test.mp4")

    def test_add_sound_direct_backend_raises(self, direct_env):
        """add_sound should raise RuntimeError on direct backend (proxy-only)."""
        client = KlingClient()
        with pytest.raises(RuntimeError, match="proxy"):
            client.add_sound("https://example.com/v.mp4", "/tmp/test.mp4")


class TestDownloadAudio:
    """Test download_audio() method for extracting MP3 audio tracks."""

    @patch("video.kling.api_client.requests.get")
    def test_download_audio_calls_assets_endpoint(self, mock_get, proxy_env):
        """download_audio should GET /assets/download with fileTypes=MP3."""
        audio_resp = MagicMock()
        audio_resp.content = b"mp3-audio-data"
        audio_resp.raise_for_status = MagicMock()
        mock_get.return_value = audio_resp

        client = KlingClient()
        result = client.download_audio("task-123", "/tmp/test_audio.mp3")

        assert result == "/tmp/test_audio.mp3"
        call_url = mock_get.call_args[0][0]
        assert "/assets/download" in call_url
        assert "fileTypes=MP3" in call_url
        assert "task-123" in call_url

    def test_download_audio_direct_backend_raises(self, direct_env):
        """download_audio should raise RuntimeError on direct backend."""
        client = KlingClient()
        with pytest.raises(RuntimeError, match="proxy"):
            client.download_audio("task-123", "/tmp/test.mp3")
