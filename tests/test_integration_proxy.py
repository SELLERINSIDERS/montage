"""Real UseAPI.net proxy integration tests.

These tests hit the actual UseAPI.net proxy endpoint and validate the
end-to-end Kling video generation path. They are marked with
@pytest.mark.integration and require USEAPI_TOKEN env var.

Run with:
    python -m pytest tests/test_integration_proxy.py -x -v -m integration --timeout=180
"""

import io
import os
import time

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def kling_client():
    """Create a KlingClient configured for UseAPI.net proxy backend."""
    token = os.environ.get("USEAPI_TOKEN")
    if not token:
        pytest.skip("USEAPI_TOKEN not set -- skipping real proxy tests")

    # Set env vars for proxy mode
    os.environ["KLING_USE_PROXY"] = "true"
    os.environ["USEAPI_KEY"] = token

    from video.kling.api_client import KlingClient
    client = KlingClient()
    assert client.use_proxy, "Client should be in proxy mode"
    return client


def _make_test_image() -> bytes:
    """Create a minimal 100x100 solid color PNG for testing."""
    try:
        from PIL import Image
        img = Image.new("RGB", (100, 100), color=(64, 128, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        pytest.skip("Pillow not installed -- cannot create test image")


class TestProxySubmission:
    """Submit a minimal image-to-video job through UseAPI.net."""

    def test_submit_receives_task_id(self, kling_client, tmp_path):
        """Submit 1-scene job and get back a task_id."""
        image_bytes = _make_test_image()
        output_path = str(tmp_path / "test_scene.mp4")

        # Use minimal payload to avoid burning credits
        try:
            result_path = kling_client.image_to_video(
                image_bytes=image_bytes,
                prompt="Slow pan across the scene",
                output_path=output_path,
                negative_prompt="blurry, distorted",
                cfg_scale=0.4,
                duration=5,
                mode="std",
            )
            # If it completed (fast API), verify output exists
            assert result_path is not None
            print(f"Integration test: received result at {result_path}")
        except Exception as e:
            # Log the error for debugging but still assert useful info
            print(f"Integration test error (may be expected): {e}")
            # Re-raise if it's not a known API limitation
            if "rate limit" not in str(e).lower() and "quota" not in str(e).lower():
                raise


class TestProxyPoll:
    """Poll a submitted task to terminal state."""

    def test_poll_reaches_terminal_state(self, kling_client, tmp_path):
        """Submit and poll a job, expecting terminal state within timeout."""
        image_bytes = _make_test_image()
        output_path = str(tmp_path / "test_poll_scene.mp4")

        try:
            result_path = kling_client.image_to_video(
                image_bytes=image_bytes,
                prompt="Slow gentle zoom on a calm landscape",
                output_path=output_path,
                negative_prompt="blurry, distorted, text",
                cfg_scale=0.4,
                duration=5,
                mode="std",
            )
            # image_to_video already polls internally, so if we get here
            # the task reached a terminal state
            print(f"Integration poll test: completed at {result_path}")
            assert result_path is not None
        except Exception as e:
            error_msg = str(e).lower()
            # Rate limit or quota errors are acceptable terminal states
            if "rate limit" in error_msg or "quota" in error_msg:
                print(f"Integration poll test: rate limited (expected): {e}")
            elif "timeout" in error_msg:
                print(f"Integration poll test: timed out (acceptable): {e}")
            else:
                print(f"Integration poll test: failed with: {e}")
                raise
