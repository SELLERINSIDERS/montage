"""Tests for bookend sync pattern in batch_generate.py.

Verifies that sync_from_dashboard() is called before and after batch processing,
push_manifest() receives the workflow manifest path (not the batch manifest),
and all sync failures are caught without blocking the pipeline.
"""

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal project directory with workflow manifest."""
    project_dir = tmp_path / "vsl" / "test-proj"
    state_dir = project_dir / "state"
    state_dir.mkdir(parents=True)
    wf_manifest = state_dir / "workflow-manifest.json"
    wf_manifest.write_text(json.dumps({
        "schema_version": "workflow-manifest-v2",
        "format": "vsl",
        "slug": "test-proj",
        "scenes": [],
    }))
    # Parity check fixtures: manifest + matching image
    manifest_dir = project_dir / "manifest"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "kling_manifest.json").write_text(json.dumps([
        {"scene": "01", "name": "test_scene", "image": "images/final/scene_01.png", "prompt": "test"}
    ]))
    images_dir = project_dir / "images" / "final"
    images_dir.mkdir(parents=True)
    (images_dir / "scene_01.png").write_bytes(b"\x89PNG fake")
    return project_dir, wf_manifest


@pytest.fixture
def tmp_batch_manifest(tmp_path):
    """Create a minimal batch manifest (scene array JSON)."""
    manifest = tmp_path / "vsl" / "test-proj" / "prompts" / "scene_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps([
        {"scene": "01", "name": "test_scene", "image": "/tmp/fake.png", "prompt": "test"}
    ]))
    return manifest


@pytest.fixture
def mock_kling_client():
    """Mock KlingClient that doesn't need API keys."""
    with patch("video.kling.batch_generate.KlingClient") as MockClient:
        instance = MockClient.return_value
        instance.use_proxy = False
        yield instance


@pytest.fixture
def mock_dashboard_sync():
    """Mock DashboardSync."""
    with patch("video.kling.batch_generate.DashboardSync") as MockSync:
        instance = MockSync.return_value
        instance.enabled = False
        MockSync._production_id = MagicMock(return_value="test-id")
        yield instance


@pytest.fixture
def mock_workflow_manifest():
    """Mock WorkflowManifest class."""
    with patch("video.kling.batch_generate.WorkflowManifest") as MockWF:
        instance = MockWF.return_value
        instance.sync_from_dashboard = MagicMock()
        yield MockWF, instance


class TestPreBatchSync:
    """Tests for sync_from_dashboard before batch processing."""

    def test_sync_called_with_project_and_manifest(
        self, tmp_project, tmp_batch_manifest, mock_kling_client,
        mock_dashboard_sync, mock_workflow_manifest
    ):
        """When --project is provided and workflow-manifest.json exists,
        sync_from_dashboard() is called before batch."""
        project_dir, wf_manifest = tmp_project
        MockWF, wf_instance = mock_workflow_manifest

        with patch("sys.argv", ["batch_generate.py", str(tmp_batch_manifest),
                                "--project", str(project_dir)]):
            from video.kling.batch_generate import main
            main()

        # WorkflowManifest should have been instantiated with the workflow manifest path
        MockWF.assert_any_call(str(wf_manifest))
        # sync_from_dashboard should have been called (at least once for pre-batch)
        assert wf_instance.sync_from_dashboard.call_count >= 1

    def test_sync_skipped_without_project(
        self, tmp_batch_manifest, mock_kling_client,
        mock_dashboard_sync, mock_workflow_manifest
    ):
        """When --project not provided, bookend sync is skipped entirely."""
        MockWF, wf_instance = mock_workflow_manifest

        with patch("sys.argv", ["batch_generate.py", str(tmp_batch_manifest)]):
            from video.kling.batch_generate import main
            main()

        MockWF.assert_not_called()
        wf_instance.sync_from_dashboard.assert_not_called()

    def test_sync_skipped_no_workflow_manifest_file(
        self, tmp_path, tmp_batch_manifest, mock_kling_client,
        mock_dashboard_sync, mock_workflow_manifest
    ):
        """When --project is provided but no workflow-manifest.json exists, skip sync."""
        project_dir = tmp_path / "vsl" / "empty-proj"
        project_dir.mkdir(parents=True)
        # Parity check fixtures so batch_generate doesn't fail on parity
        manifest_dir = project_dir / "manifest"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "kling_manifest.json").write_text(json.dumps([
            {"scene": "01", "name": "test", "image": "images/final/s01.png", "prompt": "t"}
        ]))
        images_dir = project_dir / "images" / "final"
        images_dir.mkdir(parents=True)
        (images_dir / "s01.png").write_bytes(b"\x89PNG")
        MockWF, wf_instance = mock_workflow_manifest

        with patch("sys.argv", ["batch_generate.py", str(tmp_batch_manifest),
                                "--project", str(project_dir)]):
            from video.kling.batch_generate import main
            main()

        MockWF.assert_not_called()

    def test_sync_error_does_not_block_pipeline(
        self, tmp_project, tmp_batch_manifest, mock_kling_client,
        mock_dashboard_sync, mock_workflow_manifest
    ):
        """If sync_from_dashboard raises, batch still continues (no crash)."""
        project_dir, wf_manifest = tmp_project
        MockWF, wf_instance = mock_workflow_manifest
        wf_instance.sync_from_dashboard.side_effect = RuntimeError("Network down")

        with patch("sys.argv", ["batch_generate.py", str(tmp_batch_manifest),
                                "--project", str(project_dir)]):
            from video.kling.batch_generate import main
            # Should NOT raise
            main()


class TestPostBatchSync:
    """Tests for push_manifest and sync_from_dashboard after batch processing."""

    def test_push_manifest_uses_workflow_path(
        self, tmp_project, tmp_batch_manifest, mock_kling_client,
        mock_dashboard_sync, mock_workflow_manifest
    ):
        """push_manifest receives workflow manifest path, NOT the batch manifest path."""
        project_dir, wf_manifest = tmp_project
        MockWF, wf_instance = mock_workflow_manifest
        mock_dashboard_sync.enabled = True

        with patch("sys.argv", ["batch_generate.py", str(tmp_batch_manifest),
                                "--project", str(project_dir)]):
            from video.kling.batch_generate import main
            main()

        # push_manifest should be called with the workflow manifest path
        mock_dashboard_sync.push_manifest.assert_called_once_with(str(wf_manifest))
        # Should NOT have been called with the batch manifest
        for call_args in mock_dashboard_sync.push_manifest.call_args_list:
            assert str(tmp_batch_manifest) not in str(call_args)

    def test_sync_from_dashboard_called_after_push(
        self, tmp_project, tmp_batch_manifest, mock_kling_client,
        mock_dashboard_sync, mock_workflow_manifest
    ):
        """sync_from_dashboard is called after push_manifest (bookend pattern)."""
        project_dir, wf_manifest = tmp_project
        MockWF, wf_instance = mock_workflow_manifest
        mock_dashboard_sync.enabled = True

        with patch("sys.argv", ["batch_generate.py", str(tmp_batch_manifest),
                                "--project", str(project_dir)]):
            from video.kling.batch_generate import main
            main()

        # Should be called at least twice: once before batch, once after push_manifest
        assert wf_instance.sync_from_dashboard.call_count >= 2

    def test_push_manifest_error_does_not_crash(
        self, tmp_project, tmp_batch_manifest, mock_kling_client,
        mock_dashboard_sync, mock_workflow_manifest
    ):
        """If push_manifest raises, batch still considered successful."""
        project_dir, wf_manifest = tmp_project
        MockWF, wf_instance = mock_workflow_manifest
        mock_dashboard_sync.enabled = True
        mock_dashboard_sync.push_manifest.side_effect = RuntimeError("Supabase down")

        with patch("sys.argv", ["batch_generate.py", str(tmp_batch_manifest),
                                "--project", str(project_dir)]):
            from video.kling.batch_generate import main
            # Should NOT raise
            main()
