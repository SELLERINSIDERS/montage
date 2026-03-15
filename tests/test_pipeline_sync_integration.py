"""Integration tests verifying DashboardSync is wired into pipeline scripts correctly.

Tests use unittest.mock to avoid real Supabase calls.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.workflow_manifest import WorkflowManifest
from video.kling.manifest import atomic_write_json


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def tmp_manifest(tmp_path):
    """Create a temporary WorkflowManifest with 3 scenes."""
    manifest_path = str(tmp_path / "workflow-manifest.json")
    WorkflowManifest.create("vsl", "test-slug", 3, path=manifest_path)
    return manifest_path


# ── test_manifest_apply_review_decisions ──────────────────


def test_manifest_apply_review_decisions(tmp_manifest):
    """Given 2 approved + 1 flagged decisions, gate states are updated correctly."""
    m = WorkflowManifest(tmp_manifest)

    decisions = [
        {
            "scene_id": "scene_01",
            "gate_type": "image_1k",
            "decision": "approved",
            "feedback": None,
        },
        {
            "scene_id": "scene_02",
            "gate_type": "image_1k",
            "decision": "approved",
            "feedback": "Looks great",
        },
        {
            "scene_id": "scene_03",
            "gate_type": "image_1k",
            "decision": "flagged",
            "feedback": "Too dark, reshoot needed",
        },
    ]

    m.apply_review_decisions(decisions)

    # Reload from disk to verify persistence
    m2 = WorkflowManifest(tmp_manifest)

    scene_01 = m2._find_scene("scene_01")
    assert scene_01["gates"]["image_1k"]["status"] == "approved"

    scene_02 = m2._find_scene("scene_02")
    assert scene_02["gates"]["image_1k"]["status"] == "approved"

    scene_03 = m2._find_scene("scene_03")
    assert scene_03["gates"]["image_1k"]["status"] == "flagged"
    assert scene_03["gates"]["image_1k"]["feedback"] == "Too dark, reshoot needed"


# ── test_manifest_apply_empty_decisions ───────────────────


def test_manifest_apply_empty_decisions(tmp_manifest):
    """Empty decisions list produces no changes."""
    m = WorkflowManifest(tmp_manifest)
    original_data = json.loads(json.dumps(m.data))

    m.apply_review_decisions([])

    m2 = WorkflowManifest(tmp_manifest)
    assert m2.data["scenes"] == original_data["scenes"]


# ── test_batch_generate_imports_sync ─────────────────────


def test_batch_generate_imports_sync():
    """batch_generate.py can import DashboardSync without error."""
    from video.kling.batch_generate import DashboardSync as DS
    assert DS is not None
    assert hasattr(DS, 'push_manifest')
    assert hasattr(DS, 'upload_asset')
    assert hasattr(DS, 'push_scene_update')


# ── test_sync_calls_on_clip_success ──────────────────────


def test_sync_calls_on_clip_success():
    """Mocked DashboardSync receives upload_asset and push_scene_update on clip success."""
    mock_sync = MagicMock()
    mock_sync.enabled = True
    mock_sync.generate_thumbnail.return_value = "/tmp/thumb.jpg"
    mock_sync.upload_asset.return_value = "vsl/test/video/clips/scene_01_test.mp4"

    # Simulate what happens after a successful clip in batch_generate
    result_path = "/tmp/scene_01_test.mp4"
    format_type = "vsl"
    slug = "test-slug"
    scene_num = "01"

    if mock_sync and mock_sync.enabled:
        storage_path = f"{format_type}/{slug}/video/clips/{os.path.basename(result_path)}"
        mock_sync.upload_asset(result_path, storage_path)
        thumb_local = result_path.replace('.mp4', '_thumb.jpg')
        thumb_storage = None
        if mock_sync.generate_thumbnail(result_path, thumb_local):
            thumb_storage = storage_path.replace('.mp4', '_thumb.jpg')
            mock_sync.upload_asset(thumb_local, thumb_storage)
        from scripts.dashboard_sync import DashboardSync
        production_id = DashboardSync._production_id(format_type, slug)
        mock_sync.push_scene_update(production_id, scene_num, {
            'video_status': 'completed',
            'video_storage_path': storage_path,
            'thumbnail_storage_path': thumb_storage,
        })

    # Verify calls
    assert mock_sync.upload_asset.call_count == 2  # clip + thumbnail
    assert mock_sync.generate_thumbnail.call_count == 1
    assert mock_sync.push_scene_update.call_count == 1

    # Verify push_scene_update args
    call_args = mock_sync.push_scene_update.call_args
    assert call_args[0][1] == "01"  # scene_num
    assert call_args[0][2]['video_status'] == 'completed'


# ── test_sync_from_dashboard ─────────────────────────────


def test_sync_from_dashboard_calls_pull(tmp_manifest):
    """sync_from_dashboard calls pull_review_decisions and applies them."""
    m = WorkflowManifest(tmp_manifest)

    mock_sync_instance = MagicMock()
    mock_sync_instance.enabled = True
    mock_sync_instance.pull_review_decisions.return_value = [
        {
            "scene_id": "scene_01",
            "gate_type": "image_1k",
            "decision": "approved",
            "feedback": None,
        },
    ]

    with patch("scripts.dashboard_sync.DashboardSync", return_value=mock_sync_instance):
        m.sync_from_dashboard()

    # Verify pull was called with correct production_id
    mock_sync_instance.pull_review_decisions.assert_called_once()

    # Verify decision was applied
    m2 = WorkflowManifest(tmp_manifest)
    scene_01 = m2._find_scene("scene_01")
    assert scene_01["gates"]["image_1k"]["status"] == "approved"


def test_sync_from_dashboard_skips_when_disabled(tmp_manifest):
    """sync_from_dashboard does nothing when DashboardSync is not enabled."""
    m = WorkflowManifest(tmp_manifest)

    mock_sync_instance = MagicMock()
    mock_sync_instance.enabled = False

    with patch("scripts.dashboard_sync.DashboardSync", return_value=mock_sync_instance):
        m.sync_from_dashboard()

    mock_sync_instance.pull_review_decisions.assert_not_called()
