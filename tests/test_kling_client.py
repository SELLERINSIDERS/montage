"""Tests for KlingClient with dual-backend routing."""

import os
import time
import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

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


@pytest.fixture
def unset_env(monkeypatch):
    """Unset KLING_USE_PROXY to test default behavior."""
    monkeypatch.delenv("KLING_USE_PROXY", raising=False)
    monkeypatch.setenv("KLING_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("KLING_SECRET_KEY", "test-secret-key-at-least-32chars!!")


# --- Backend Routing Tests ---


class TestProxyRouting:
    """Test that KLING_USE_PROXY=true routes to UseAPI.net."""

    def test_proxy_base_url(self, proxy_env):
        client = KlingClient()
        assert "useapi.net" in client.base_url

    def test_proxy_uses_useapi_key(self, proxy_env):
        client = KlingClient()
        assert client.api_key == "test-useapi-key-123"


class TestDirectRouting:
    """Test that KLING_USE_PROXY=false routes to direct Kling."""

    def test_direct_base_url(self, direct_env):
        client = KlingClient()
        assert "klingai.com" in client.base_url

    def test_direct_uses_access_key(self, direct_env):
        client = KlingClient()
        assert client.access_key == "test-access-key"


class TestEnvToggle:
    """Test env var toggle behavior."""

    def test_default_is_direct(self, unset_env):
        """KLING_USE_PROXY unset should default to direct Kling."""
        client = KlingClient()
        assert client.use_proxy is False
        assert "klingai.com" in client.base_url

    def test_toggle_changes_backend(self, monkeypatch):
        """Changing env var should change backend."""
        monkeypatch.setenv("KLING_USE_PROXY", "true")
        monkeypatch.setenv("USEAPI_KEY", "key1")
        client_proxy = KlingClient()

        monkeypatch.setenv("KLING_USE_PROXY", "false")
        monkeypatch.setenv("KLING_ACCESS_KEY", "ak")
        monkeypatch.setenv("KLING_SECRET_KEY", "sk-long-enough-for-jwt-signing!!")
        client_direct = KlingClient()

        assert client_proxy.use_proxy is True
        assert client_direct.use_proxy is False


# --- JWT Tests ---


class TestJwtGeneration:
    """Test JWT generation for direct Kling API."""

    def test_jwt_has_correct_fields(self, direct_env):
        import jwt as pyjwt
        client = KlingClient()
        token = client._generate_jwt()
        decoded = pyjwt.decode(token, "test-secret-key-at-least-32chars!!",
                               algorithms=["HS256"])
        assert "iss" in decoded
        assert "exp" in decoded
        assert "nbf" in decoded
        assert decoded["iss"] == "test-access-key"

    def test_jwt_expiry_is_30_minutes(self, direct_env):
        import jwt as pyjwt
        client = KlingClient()
        token = client._generate_jwt()
        decoded = pyjwt.decode(token, "test-secret-key-at-least-32chars!!",
                               algorithms=["HS256"])
        # exp should be ~30 min from now
        assert decoded["exp"] - decoded["nbf"] <= 1810  # 1800 + 5s buffer

    def test_jwt_caching_reuses_token(self, direct_env):
        """Second call within validity period should reuse the JWT."""
        client = KlingClient()
        token1 = client._get_jwt()
        token2 = client._get_jwt()
        assert token1 == token2

    def test_jwt_regenerates_when_expired(self, direct_env):
        """JWT should regenerate when < 5 minutes remaining."""
        client = KlingClient()
        token1 = client._get_jwt()
        # Simulate near-expiry by setting expiry to now
        client._jwt_expiry = time.time() - 10
        token2 = client._get_jwt()
        assert token1 != token2


# --- Headers Tests ---


class TestHeaders:
    """Test auth headers per backend."""

    def test_headers_proxy_bearer_token(self, proxy_env):
        client = KlingClient()
        headers = client._get_headers()
        assert headers["Authorization"] == "Bearer test-useapi-key-123"
        assert headers["Content-Type"] == "application/json"

    def test_headers_direct_jwt_bearer(self, direct_env):
        client = KlingClient()
        headers = client._get_headers()
        assert headers["Authorization"].startswith("Bearer ")
        assert headers["Content-Type"] == "application/json"
        # Should be a JWT (3 dot-separated parts)
        token = headers["Authorization"].split(" ")[1]
        assert len(token.split(".")) == 3


# --- Model Name Mapping Tests ---


class TestModelNameMapping:
    """Test model name mapping between backends."""

    def test_proxy_maps_to_kling_v3_0(self, proxy_env):
        client = KlingClient()
        assert client._get_model_name() == "kling-v3-0"

    def test_direct_uses_kling_v3(self, direct_env):
        client = KlingClient()
        assert client._get_model_name() == "kling-v3"


# --- Image Upload Tests ---


class TestImageUploadUseapi:
    """Test base64-to-URL conversion for UseAPI.net."""

    @patch("video.kling.api_client.requests.post")
    def test_upload_returns_url(self, mock_post, proxy_env):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"url": "https://cdn.useapi.net/image123.png"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = KlingClient()
        url = client._upload_image_useapi(b"fake-image-bytes")
        assert url == "https://cdn.useapi.net/image123.png"
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "/assets" in call_url


# --- Submit Tests ---


class TestSubmit:
    """Test submit methods per backend."""

    @patch("video.kling.api_client.requests.post")
    def test_submit_proxy_endpoint(self, mock_post, proxy_env):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"task": {"id": 12345}}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = KlingClient()
        result = client._submit("/videos/image2video-frames", {"prompt": "test"})
        call_url = mock_post.call_args[0][0]
        assert "useapi.net" in call_url

    @patch("video.kling.api_client.requests.post")
    def test_submit_direct_endpoint(self, mock_post, direct_env):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"task_id": "abc123"}}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = KlingClient()
        result = client._submit("/videos/image2video", {"prompt": "test"})
        call_url = mock_post.call_args[0][0]
        assert "klingai.com" in call_url


# --- Poll Tests ---


class TestPoll:
    """Test polling behavior."""

    def test_poll_normalizes_string_task_id(self, proxy_env):
        """String task IDs should be handled correctly."""
        client = KlingClient()
        endpoint = client._get_poll_endpoint("abc-123")
        assert "abc-123" in endpoint

    def test_poll_normalizes_integer_task_id(self, proxy_env):
        """Integer task IDs should be converted to string."""
        client = KlingClient()
        endpoint = client._get_poll_endpoint(12345)
        assert "12345" in endpoint


# --- Dual-Frame Tests ---


class TestDualFrameDirect:
    """Test dual-frame (start+end image) payload for direct Kling backend."""

    @patch("video.kling.api_client.requests.get")
    @patch("video.kling.api_client.requests.post")
    def test_dual_frame_payload_direct(self, mock_post, mock_get, direct_env):
        """Direct backend: payload should contain 'image_tail' with base64 string."""
        import base64

        # Mock submit response
        submit_resp = MagicMock()
        submit_resp.json.return_value = {"data": {"task_id": "task-dual-1"}}
        submit_resp.raise_for_status = MagicMock()

        # Mock poll response (immediate success)
        poll_resp = MagicMock()
        poll_resp.json.return_value = {
            "data": {
                "task_status": "succeed",
                "task_result": {"videos": [{"url": "https://example.com/video.mp4"}]},
            }
        }
        poll_resp.raise_for_status = MagicMock()

        # Mock download response
        download_resp = MagicMock()
        download_resp.raise_for_status = MagicMock()
        download_resp.iter_content.return_value = [b"video-data"]

        mock_post.return_value = submit_resp
        mock_get.side_effect = [poll_resp, download_resp]

        client = KlingClient()
        start_image = b"start-frame-bytes"
        end_image = b"end-frame-bytes"

        client.image_to_video(
            start_image, "transition prompt", "/tmp/test_dual.mp4",
            image_tail_bytes=end_image,
        )

        # Check the payload sent to submit
        submit_call = mock_post.call_args
        payload = submit_call[1]["json"] if "json" in submit_call[1] else submit_call[0][1] if len(submit_call[0]) > 1 else submit_call[1].get("json")
        # The submit is called via _submit which uses requests.post(url, headers=..., json=...)
        # So payload is in kwargs['json']
        payload = mock_post.call_args[1]["json"]
        assert "image_tail" in payload
        expected_tail = base64.b64encode(end_image).decode("utf-8")
        assert payload["image_tail"] == expected_tail

    @patch("video.kling.api_client.requests.get")
    @patch("video.kling.api_client.requests.post")
    def test_dual_frame_auto_10s_duration_direct(self, mock_post, mock_get, direct_env):
        """Dual-frame should auto-set duration to 10 for transition scenes."""
        submit_resp = MagicMock()
        submit_resp.json.return_value = {"data": {"task_id": "task-dur-1"}}
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
        client.image_to_video(
            b"start", "prompt", "/tmp/test.mp4",
            image_tail_bytes=b"end", duration=5,
        )

        payload = mock_post.call_args[1]["json"]
        # Direct backend sends duration as string
        assert payload["duration"] == "10"


class TestDualFrameProxy:
    """Test dual-frame payload for UseAPI.net proxy backend."""

    @patch("video.kling.api_client.requests.get")
    @patch("video.kling.api_client.requests.post")
    def test_dual_frame_payload_proxy(self, mock_post, mock_get, proxy_env):
        """Proxy backend: payload should contain 'image_tail' URL and use image2video-frames endpoint."""
        # First post call: upload start image -> URL
        upload_start_resp = MagicMock()
        upload_start_resp.json.return_value = {"url": "https://cdn.useapi.net/start.png"}
        upload_start_resp.raise_for_status = MagicMock()

        # Second post call: upload end image -> URL
        upload_end_resp = MagicMock()
        upload_end_resp.json.return_value = {"url": "https://cdn.useapi.net/end.png"}
        upload_end_resp.raise_for_status = MagicMock()

        # Third post call: submit generation
        submit_resp = MagicMock()
        submit_resp.json.return_value = {"task": {"id": "proxy-task-1"}}
        submit_resp.raise_for_status = MagicMock()

        mock_post.side_effect = [upload_start_resp, upload_end_resp, submit_resp]

        # Poll response
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
            b"start-bytes", "transition prompt", "/tmp/test_proxy_dual.mp4",
            image_tail_bytes=b"end-bytes",
        )

        # The third post call should be the submit with image_tail URL
        submit_call = mock_post.call_args_list[2]
        submit_url = submit_call[0][0]
        payload = submit_call[1]["json"]

        assert "/videos/image2video-frames" in submit_url
        assert "image_tail" in payload
        assert payload["image_tail"] == "https://cdn.useapi.net/end.png"

    @patch("video.kling.api_client.requests.get")
    @patch("video.kling.api_client.requests.post")
    def test_dual_frame_auto_10s_duration_proxy(self, mock_post, mock_get, proxy_env):
        """Proxy backend dual-frame should also auto-set duration to 10."""
        upload_start_resp = MagicMock()
        upload_start_resp.json.return_value = {"url": "https://cdn.useapi.net/s.png"}
        upload_start_resp.raise_for_status = MagicMock()

        upload_end_resp = MagicMock()
        upload_end_resp.json.return_value = {"url": "https://cdn.useapi.net/e.png"}
        upload_end_resp.raise_for_status = MagicMock()

        submit_resp = MagicMock()
        submit_resp.json.return_value = {"task": {"id": "proxy-dur-1"}}
        submit_resp.raise_for_status = MagicMock()

        mock_post.side_effect = [upload_start_resp, upload_end_resp, submit_resp]

        poll_resp = MagicMock()
        poll_resp.json.return_value = {
            "status_name": "succeed",
            "works": [{"url": "https://cdn.useapi.net/v.mp4"}],
        }
        poll_resp.raise_for_status = MagicMock()

        download_resp = MagicMock()
        download_resp.raise_for_status = MagicMock()
        download_resp.iter_content.return_value = [b"v"]

        mock_get.side_effect = [poll_resp, download_resp]

        client = KlingClient()
        client.image_to_video(
            b"s", "p", "/tmp/t.mp4",
            image_tail_bytes=b"e", duration=5,
        )

        payload = mock_post.call_args_list[2][1]["json"]
        # Proxy sends duration as int
        assert payload["duration"] == 10


class TestSingleFrameUnchanged:
    """Test that single-frame (no image_tail_bytes) behavior is completely unchanged."""

    @patch("video.kling.api_client.requests.get")
    @patch("video.kling.api_client.requests.post")
    def test_single_frame_no_image_tail_key(self, mock_post, mock_get, direct_env):
        """Without image_tail_bytes, payload should have no 'image_tail' key."""
        submit_resp = MagicMock()
        submit_resp.json.return_value = {"data": {"task_id": "single-1"}}
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
        download_resp.iter_content.return_value = [b"v"]

        mock_post.return_value = submit_resp
        mock_get.side_effect = [poll_resp, download_resp]

        client = KlingClient()
        client.image_to_video(b"image", "prompt", "/tmp/single.mp4")

        payload = mock_post.call_args[1]["json"]
        assert "image_tail" not in payload
        assert payload["duration"] == "5"  # default 5, direct backend uses string

    @patch("video.kling.api_client.requests.get")
    @patch("video.kling.api_client.requests.post")
    def test_single_frame_custom_duration_preserved(self, mock_post, mock_get, direct_env):
        """Without image_tail_bytes, custom duration should be preserved (not overridden)."""
        submit_resp = MagicMock()
        submit_resp.json.return_value = {"data": {"task_id": "single-2"}}
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
        download_resp.iter_content.return_value = [b"v"]

        mock_post.return_value = submit_resp
        mock_get.side_effect = [poll_resp, download_resp]

        client = KlingClient()
        client.image_to_video(b"image", "prompt", "/tmp/single10.mp4", duration=10)

        payload = mock_post.call_args[1]["json"]
        assert "image_tail" not in payload
        assert payload["duration"] == "10"  # custom 10 preserved


# --- poll_existing_task Tests ---


class TestPollExistingTask:
    """Test poll_existing_task: re-poll a known task_id to completion."""

    @patch("video.kling.api_client.requests.get")
    def test_already_succeeded_downloads_and_returns_path(self, mock_get, direct_env):
        """A task that already succeeded should download and return output_path."""
        poll_resp = MagicMock()
        poll_resp.json.return_value = {
            "data": {
                "task_status": "succeed",
                "task_result": {"videos": [{"url": "https://example.com/video.mp4"}]},
            }
        }
        poll_resp.raise_for_status = MagicMock()

        download_resp = MagicMock()
        download_resp.raise_for_status = MagicMock()
        download_resp.iter_content.return_value = [b"video-data"]

        mock_get.side_effect = [poll_resp, download_resp]

        client = KlingClient()
        result = client.poll_existing_task("task-123", "/tmp/test_repoll.mp4")

        assert result == "/tmp/test_repoll.mp4"
        # Should have polled once, then downloaded
        assert mock_get.call_count == 2

    @patch("video.kling.api_client.time.sleep")
    @patch("video.kling.api_client.requests.get")
    def test_processing_then_succeeded_polls_until_done(self, mock_get, mock_sleep, direct_env):
        """A task still processing should poll multiple times until terminal."""
        processing_resp = MagicMock()
        processing_resp.json.return_value = {
            "data": {"task_status": "processing"}
        }
        processing_resp.raise_for_status = MagicMock()

        succeed_resp = MagicMock()
        succeed_resp.json.return_value = {
            "data": {
                "task_status": "succeed",
                "task_result": {"videos": [{"url": "https://example.com/v.mp4"}]},
            }
        }
        succeed_resp.raise_for_status = MagicMock()

        download_resp = MagicMock()
        download_resp.raise_for_status = MagicMock()
        download_resp.iter_content.return_value = [b"video"]

        mock_get.side_effect = [processing_resp, succeed_resp, download_resp]

        client = KlingClient()
        result = client.poll_existing_task("task-456", "/tmp/test_poll_wait.mp4")

        assert result == "/tmp/test_poll_wait.mp4"
        # 2 polls + 1 download = 3 GET calls
        assert mock_get.call_count == 3
        # Should have slept between polls
        assert mock_sleep.call_count >= 1

    @patch("video.kling.api_client.time.sleep")
    @patch("video.kling.api_client.requests.get")
    def test_failed_task_raises_runtime_error(self, mock_get, mock_sleep, direct_env):
        """A task that failed on Kling's side should raise RuntimeError."""
        failed_resp = MagicMock()
        failed_resp.json.return_value = {
            "data": {"task_status": "failed"}
        }
        failed_resp.raise_for_status = MagicMock()

        mock_get.return_value = failed_resp

        client = KlingClient()
        with pytest.raises(RuntimeError, match="failed"):
            client.poll_existing_task("task-789", "/tmp/test_failed.mp4")

    @patch("video.kling.api_client.time.time")
    @patch("video.kling.api_client.time.sleep")
    @patch("video.kling.api_client.requests.get")
    def test_timeout_raises_runtime_error(self, mock_get, mock_sleep, mock_time, direct_env):
        """A task that never reaches terminal should raise RuntimeError after timeout."""
        processing_resp = MagicMock()
        processing_resp.json.return_value = {
            "data": {"task_status": "processing"}
        }
        processing_resp.raise_for_status = MagicMock()

        mock_get.return_value = processing_resp

        # Simulate time progression past POLL_TIMEOUT (600s)
        # First call is start time, subsequent calls increment past timeout
        mock_time.side_effect = [0, 0, 100, 200, 300, 400, 500, 601, 700]

        client = KlingClient()
        with pytest.raises(RuntimeError, match="timeout"):
            client.poll_existing_task("task-timeout", "/tmp/test_timeout.mp4")
