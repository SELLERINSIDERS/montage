"""Unit tests for DashboardSync with mocked Supabase client.

All tests use mocked Supabase to avoid real API calls.
Tests verify sync behavior: manifest pushing, scene updates, review decisions,
asset uploads, heartbeat, and graceful degradation when disabled.
"""

import os
import uuid
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_mock_supabase():
    """Create a mock Supabase client with chainable table/storage methods."""
    mock_client = MagicMock()

    # Chainable table methods: .table("x").upsert({}).execute()
    mock_table = MagicMock()
    mock_table.upsert.return_value = mock_table
    mock_table.update.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.in_.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[])
    mock_client.table.return_value = mock_table

    # Storage: .storage.from_("bucket").upload(...)
    mock_storage_bucket = MagicMock()
    mock_client.storage.from_.return_value = mock_storage_bucket

    return mock_client, mock_table, mock_storage_bucket


def _make_sample_manifest(
    approved=3, flagged=1, pending=2, fmt="vsl", slug="test-prod"
):
    """Build a sample manifest dict matching WorkflowManifest.create() format."""
    scenes = []
    idx = 0
    for _ in range(approved):
        idx += 1
        scenes.append({
            "scene_id": f"scene_{idx:02d}",
            "gates": {
                "image_1k": {"status": "approved", "attempts": 0},
                "image_2k": {"status": "approved", "attempts": 0},
                "video": {"status": "approved", "attempts": 0},
            },
            "gate_timing": {},
        })
    for _ in range(flagged):
        idx += 1
        scenes.append({
            "scene_id": f"scene_{idx:02d}",
            "gates": {
                "image_1k": {"status": "approved", "attempts": 0},
                "image_2k": {"status": "flagged", "attempts": 2},
            },
            "gate_timing": {},
        })
    for _ in range(pending):
        idx += 1
        scenes.append({
            "scene_id": f"scene_{idx:02d}",
            "gates": {},
            "gate_timing": {},
        })

    return {
        "schema_version": "workflow-manifest-v2",
        "format": fmt,
        "slug": slug,
        "current_phase": "image_2k",
        "scenes": scenes,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase.co", "SUPABASE_SERVICE_KEY": "test-key"})
@patch("scripts.dashboard_sync.create_client")
class TestPushManifestComputesCounts:
    """push_manifest computes correct approved/flagged/pending counts."""

    def test_push_manifest_computes_counts(self, mock_create_client):
        mock_client, mock_table, _ = _make_mock_supabase()
        mock_create_client.return_value = mock_client

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()
        assert sync.enabled is True

        manifest = _make_sample_manifest(approved=3, flagged=1, pending=2)
        manifest_path = "/tmp/test_manifest.json"
        import json
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        sync.push_manifest(manifest_path)

        # Find the productions upsert call
        upsert_calls = mock_table.upsert.call_args_list
        assert len(upsert_calls) > 0

        prod_row = upsert_calls[0][0][0]
        assert prod_row["approved_count"] == 3
        assert prod_row["flagged_count"] == 1
        assert prod_row["pending_count"] == 2
        assert prod_row["scene_count"] == 6


@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase.co", "SUPABASE_SERVICE_KEY": "test-key"})
@patch("scripts.dashboard_sync.create_client")
class TestPushManifestUpsertsScenes:
    """push_manifest upserts each scene to scenes table."""

    def test_push_manifest_upserts_scenes(self, mock_create_client):
        mock_client, mock_table, _ = _make_mock_supabase()
        mock_create_client.return_value = mock_client

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()
        manifest = _make_sample_manifest(approved=2, flagged=0, pending=1)
        manifest_path = "/tmp/test_manifest_scenes.json"
        import json
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        sync.push_manifest(manifest_path)

        # 1 production upsert + 3 scene upserts = 4 total
        upsert_calls = mock_table.upsert.call_args_list
        assert len(upsert_calls) == 4  # 1 production + 3 scenes

        # Check scene rows have scene_id and production_id
        scene_rows = [c[0][0] for c in upsert_calls[1:]]
        scene_ids = [r["scene_id"] for r in scene_rows]
        assert "scene_01" in scene_ids
        assert "scene_02" in scene_ids
        assert "scene_03" in scene_ids


@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase.co", "SUPABASE_SERVICE_KEY": "test-key"})
@patch("scripts.dashboard_sync.create_client")
class TestPullReviewDecisions:
    """pull_review_decisions returns unsynced decisions and marks them synced."""

    def test_pull_review_decisions_returns_unsynced(self, mock_create_client):
        mock_client, mock_table, _ = _make_mock_supabase()
        mock_create_client.return_value = mock_client

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()

        # Mock select returning unsynced decisions
        decision_data = [
            {"id": "dec-1", "scene_id": "scene_01", "decision": "flagged"},
            {"id": "dec-2", "scene_id": "scene_02", "decision": "approved"},
        ]
        mock_table.execute.return_value = MagicMock(data=decision_data)

        prod_id = DashboardSync._production_id("vsl", "test")
        decisions = sync.pull_review_decisions(prod_id)

        assert len(decisions) == 2
        assert decisions[0]["decision"] == "flagged"

        # Verify mark-as-synced was called
        mock_table.update.assert_called_with({"synced_to_pipeline": True})
        mock_table.in_.assert_called_with("id", ["dec-1", "dec-2"])


@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase.co", "SUPABASE_SERVICE_KEY": "test-key"})
@patch("scripts.dashboard_sync.create_client")
class TestPullReviewDecisionsEmptyOnFailure:
    """pull_review_decisions returns empty list on Supabase failure."""

    def test_pull_review_decisions_empty_on_failure(self, mock_create_client):
        mock_client, mock_table, _ = _make_mock_supabase()
        mock_create_client.return_value = mock_client

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()

        # Make select().eq().eq().execute() raise
        mock_table.execute.side_effect = Exception("Connection failed")

        prod_id = DashboardSync._production_id("vsl", "test")
        decisions = sync.pull_review_decisions(prod_id)

        assert decisions == []


@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase.co", "SUPABASE_SERVICE_KEY": "test-key"})
@patch("scripts.dashboard_sync.create_client")
class TestUploadAssetRetriesOnFailure:
    """upload_asset retries up to 3 times, returns None on final failure."""

    @patch("scripts.dashboard_sync.time.sleep")
    def test_upload_asset_retries_on_failure(self, mock_sleep, mock_create_client):
        mock_client, _, mock_storage = _make_mock_supabase()
        mock_create_client.return_value = mock_client

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()

        # Make upload always fail
        mock_storage.upload.side_effect = Exception("Upload failed")

        # Create a test file
        test_file = "/tmp/test_upload.png"
        with open(test_file, "wb") as f:
            f.write(b"fake image data")

        result = sync.upload_asset(test_file, "images/test.png")

        assert result is None
        assert mock_storage.upload.call_count == 3
        # Verify backoff sleeps
        assert mock_sleep.call_count == 2  # 2 sleeps between 3 attempts


class TestDisabledWhenNoEnvVars:
    """All methods return gracefully when SUPABASE_URL/KEY not set."""

    @patch.dict(os.environ, {}, clear=True)
    @patch("scripts.dashboard_sync.create_client", side_effect=Exception("should not be called"))
    def test_disabled_when_no_env_vars(self, mock_create_client):
        # Remove env vars if they exist
        os.environ.pop("SUPABASE_URL", None)
        os.environ.pop("SUPABASE_SERVICE_KEY", None)

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()
        assert sync.enabled is False

        # All methods should return gracefully
        sync.push_manifest("/nonexistent/path")
        sync.push_scene_update("fake-id", "scene_01", {"status": "approved"})
        result = sync.upload_asset("/nonexistent", "path")
        assert result is None
        decisions = sync.pull_review_decisions("fake-id")
        assert decisions == []
        sync.push_heartbeat("fake-id")

        # create_client should NOT have been called
        mock_create_client.assert_not_called()


class TestProductionIdDeterministic:
    """Same format+slug always produces same UUID."""

    def test_production_id_deterministic(self):
        from scripts.dashboard_sync import DashboardSync

        id1 = DashboardSync._production_id("vsl", "example-project")
        id2 = DashboardSync._production_id("vsl", "example-project")
        id3 = DashboardSync._production_id("ad", "example-project")

        assert id1 == id2
        assert id1 != id3
        # Should be a valid UUID
        uuid.UUID(id1)


class TestSceneStatusDerivation:
    """_scene_status correctly derives pending/approved/flagged from gate data."""

    def test_empty_gates_is_pending(self):
        from scripts.dashboard_sync import DashboardSync

        assert DashboardSync._scene_status({"gates": {}}) == "pending"

    def test_no_gates_key_is_pending(self):
        from scripts.dashboard_sync import DashboardSync

        assert DashboardSync._scene_status({}) == "pending"

    def test_all_approved_is_approved(self):
        from scripts.dashboard_sync import DashboardSync

        scene = {
            "gates": {
                "image_1k": {"status": "approved"},
                "image_2k": {"status": "approved"},
                "video": {"status": "approved"},
            }
        }
        assert DashboardSync._scene_status(scene) == "approved"

    def test_any_flagged_is_flagged(self):
        from scripts.dashboard_sync import DashboardSync

        scene = {
            "gates": {
                "image_1k": {"status": "approved"},
                "image_2k": {"status": "flagged"},
            }
        }
        assert DashboardSync._scene_status(scene) == "flagged"

    def test_needs_manual_intervention_is_flagged(self):
        from scripts.dashboard_sync import DashboardSync

        scene = {
            "gates": {
                "image_1k": {"status": "needs_manual_intervention"},
            }
        }
        assert DashboardSync._scene_status(scene) == "flagged"

    def test_mixed_approved_pending_is_pending(self):
        from scripts.dashboard_sync import DashboardSync

        scene = {
            "gates": {
                "image_1k": {"status": "approved"},
                "image_2k": {"status": "pending"},
            }
        }
        assert DashboardSync._scene_status(scene) == "pending"


@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase.co", "SUPABASE_SERVICE_KEY": "test-key"})
@patch("scripts.dashboard_sync.create_client")
class TestPushHeartbeat:
    """push_heartbeat updates heartbeat_at for given production_id."""

    def test_push_heartbeat(self, mock_create_client):
        mock_client, mock_table, _ = _make_mock_supabase()
        mock_create_client.return_value = mock_client

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()
        prod_id = "test-production-id"
        sync.push_heartbeat(prod_id)

        mock_table.update.assert_called_with({"heartbeat_at": "now()"})
        mock_table.eq.assert_called_with("id", prod_id)
        mock_table.execute.assert_called()


@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase.co", "SUPABASE_SERVICE_KEY": "test-key"})
@patch("scripts.dashboard_sync.create_client")
class TestUploadFinalVideo:
    """upload_final_video uploads to production-videos bucket and returns URL."""

    def test_upload_final_video_returns_url(self, mock_create_client):
        mock_client, _, mock_storage = _make_mock_supabase()
        mock_create_client.return_value = mock_client
        mock_storage.get_public_url.return_value = "https://storage.test/production-videos/pid/final_v1.mp4"

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()

        # Create test file
        test_file = "/tmp/test_final_video.mp4"
        with open(test_file, "wb") as f:
            f.write(b"fake video data")

        result = sync.upload_final_video("pid", test_file, 1)

        assert result is not None
        assert "final_v1" in result
        mock_storage.upload.assert_called_once()

    def test_upload_preview_video_uses_preview_prefix(self, mock_create_client):
        mock_client, _, mock_storage = _make_mock_supabase()
        mock_create_client.return_value = mock_client
        mock_storage.get_public_url.return_value = "https://storage.test/production-videos/pid/preview_v2.mp4"

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()

        test_file = "/tmp/test_preview_video.mp4"
        with open(test_file, "wb") as f:
            f.write(b"fake video data")

        result = sync.upload_final_video("pid", test_file, 2, quality="preview")

        assert result is not None
        assert "preview_v2" in result

    def test_upload_returns_none_when_disabled(self, mock_create_client):
        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync.__new__(DashboardSync)
        sync.enabled = False
        sync.client = None

        result = sync.upload_final_video("pid", "/fake/path.mp4", 1)
        assert result is None


@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase.co", "SUPABASE_SERVICE_KEY": "test-key"})
@patch("scripts.dashboard_sync.create_client")
class TestPushVideoVersion:
    """push_video_version upserts to production_videos table."""

    def test_push_video_version_upserts(self, mock_create_client):
        mock_client, mock_table, _ = _make_mock_supabase()
        mock_create_client.return_value = mock_client

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()

        version_data = {
            "version": 1,
            "quality": "preview",
            "storage_url": "https://storage.test/video.mp4",
            "rendered_at": "2026-03-11T12:00:00Z",
            "render_duration_s": 120,
            "is_approved": False,
        }

        sync.push_video_version("pid", version_data)

        upsert_calls = mock_table.upsert.call_args_list
        assert len(upsert_calls) > 0
        row = upsert_calls[0][0][0]
        assert row["production_id"] == "pid"
        assert row["version"] == 1
        assert row["quality"] == "preview"


@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase.co", "SUPABASE_SERVICE_KEY": "test-key"})
@patch("scripts.dashboard_sync.create_client")
class TestGetVideoVersions:
    """get_video_versions fetches all versions ordered by version number."""

    def test_get_video_versions_returns_list(self, mock_create_client):
        mock_client, mock_table, _ = _make_mock_supabase()
        mock_create_client.return_value = mock_client

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()

        mock_table.execute.return_value = MagicMock(data=[
            {"version": 1, "quality": "preview", "is_approved": False},
            {"version": 2, "quality": "final", "is_approved": True},
        ])

        # Need to also mock .order() for chaining
        mock_table.order.return_value = mock_table

        versions = sync.get_video_versions("pid")

        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[1]["is_approved"] is True

    def test_get_video_versions_empty_when_disabled(self, mock_create_client):
        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync.__new__(DashboardSync)
        sync.enabled = False
        sync.client = None

        assert sync.get_video_versions("pid") == []


@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase.co", "SUPABASE_SERVICE_KEY": "test-key"})
@patch("scripts.dashboard_sync.create_client")
class TestMarkFinalApproved:
    """mark_final_approved updates version and production status."""

    def test_mark_final_approved(self, mock_create_client):
        mock_client, mock_table, _ = _make_mock_supabase()
        mock_create_client.return_value = mock_client

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()
        sync.mark_final_approved("pid", 3)

        # Should have two update calls: one for version, one for production
        update_calls = mock_table.update.call_args_list
        assert len(update_calls) >= 2

        # First update: mark version approved
        first_update = update_calls[0][0][0]
        assert first_update["is_approved"] is True

        # Second update: production status
        second_update = update_calls[1][0][0]
        assert second_update["current_stage"] == "Complete"
        assert second_update["status"] == "completed"


class TestStageMapping:
    """current_phase maps to correct grouped stage."""

    def test_image_phases_map_to_image_gen(self):
        from scripts.dashboard_sync import STAGE_MAP

        assert STAGE_MAP["image_1k"] == "Image Gen"
        assert STAGE_MAP["image_2k"] == "Image Gen"
        assert STAGE_MAP["image_generation"] == "Image Gen"
        assert STAGE_MAP["image_review"] == "Image Gen"

    def test_script_phases_map_to_script_design(self):
        from scripts.dashboard_sync import STAGE_MAP

        assert STAGE_MAP["script"] == "Script & Design"
        assert STAGE_MAP["storyboard"] == "Script & Design"
        assert STAGE_MAP["compliance"] == "Script & Design"

    def test_video_phases_map_to_video_gen(self):
        from scripts.dashboard_sync import STAGE_MAP

        assert STAGE_MAP["video_generation"] == "Video Gen"
        assert STAGE_MAP["video_review"] == "Video Gen"

    def test_audio_phases_map_to_audio_post(self):
        from scripts.dashboard_sync import STAGE_MAP

        assert STAGE_MAP["voiceover"] == "Audio & Post"
        assert STAGE_MAP["sound_design"] == "Audio & Post"
        assert STAGE_MAP["post_production"] == "Audio & Post"
        assert STAGE_MAP["remotion_render"] == "Audio & Post"

    def test_complete_phases_map_to_complete(self):
        from scripts.dashboard_sync import STAGE_MAP

        assert STAGE_MAP["complete"] == "Complete"
        assert STAGE_MAP["delivered"] == "Complete"
