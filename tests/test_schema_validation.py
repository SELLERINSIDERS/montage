"""Tests for schema validation: manifest structure and push_manifest version checks.

Tests for video.kling.schema_validation:
- validate_manifest accepts valid scene arrays
- validate_manifest rejects missing required fields
- normalize_scene_id converts various formats to snake_case

Tests for push_manifest schema version:
- Accepts workflow-manifest-v2 manifests and pushes normally
- Rejects manifests without schema_version (no Supabase calls)
- Rejects manifests with wrong schema_version (no Supabase calls)
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
import jsonschema

from video.kling.schema_validation import validate_manifest, normalize_scene_id


# ---------------------------------------------------------------------------
# Kling manifest schema validation tests
# ---------------------------------------------------------------------------


class TestValidateManifest:
    """validate_manifest validates scene array structure."""

    def test_valid_manifest_passes(self):
        """Well-formed manifest passes validation."""
        data = [
            {
                "scene": "01",
                "name": "harbor_dawn",
                "image": "images/final/scene_01.png",
                "prompt": "A sweeping aerial shot of ancient Alexandria harbor at dawn",
            }
        ]
        validate_manifest(data)  # Should not raise

    def test_missing_required_field_raises(self):
        """Missing 'prompt' field raises ValidationError."""
        data = [
            {
                "scene": "01",
                "name": "harbor_dawn",
                "image": "images/final/scene_01.png",
                # missing "prompt"
            }
        ]
        with pytest.raises(jsonschema.ValidationError, match="prompt"):
            validate_manifest(data)

    def test_missing_scene_field_raises(self):
        """Missing 'scene' field raises ValidationError."""
        data = [
            {
                "name": "harbor_dawn",
                "image": "images/final/scene_01.png",
                "prompt": "A shot",
            }
        ]
        with pytest.raises(jsonschema.ValidationError, match="scene"):
            validate_manifest(data)

    def test_empty_array_passes(self):
        """Empty scene array is valid (no items to check)."""
        validate_manifest([])

    def test_multi_scene_manifest_passes(self):
        """Multi-scene manifest with optional fields passes."""
        data = [
            {
                "scene": "01",
                "name": "harbor",
                "image": "scene_01.png",
                "prompt": "Shot 1",
                "duration": "5",
                "mode": "std",
                "cfg_scale": 0.4,
                "negative_prompt": "blurry",
            },
            {
                "scene": "02",
                "name": "palace",
                "image": "scene_02.png",
                "prompt": "Shot 2",
            },
        ]
        validate_manifest(data)


class TestNormalizeSceneId:
    """normalize_scene_id converts various formats to scene_XX with suffix."""

    def test_scene01_to_scene_01(self):
        assert normalize_scene_id("Scene01") == "scene_01"

    def test_lowercase_scene01_to_scene_01(self):
        assert normalize_scene_id("scene01") == "scene_01"

    def test_already_normalized_unchanged(self):
        assert normalize_scene_id("scene_01") == "scene_01"

    def test_scene_with_dash(self):
        assert normalize_scene_id("Scene-01") == "scene_01"

    def test_pads_single_digit(self):
        assert normalize_scene_id("scene1") == "scene_01"

    def test_preserves_double_digit(self):
        assert normalize_scene_id("Scene88") == "scene_88"

    # Letter suffix preservation
    def test_preserves_letter_suffix_long_form(self):
        assert normalize_scene_id("scene_04c") == "scene_04c"

    def test_preserves_letter_suffix_pascal(self):
        assert normalize_scene_id("Scene04c") == "scene_04c"

    def test_preserves_letter_suffix_a(self):
        assert normalize_scene_id("scene_04a") == "scene_04a"

    # Short form (S04c) normalization
    def test_short_form_with_suffix(self):
        assert normalize_scene_id("S04c") == "scene_04c"

    def test_short_form_without_suffix(self):
        assert normalize_scene_id("S04") == "scene_04"

    def test_short_form_lowercase(self):
        assert normalize_scene_id("s12b") == "scene_12b"

    def test_short_form_pads_single_digit(self):
        assert normalize_scene_id("S1") == "scene_01"


# ---------------------------------------------------------------------------
# push_manifest schema version validation tests (existing)
# ---------------------------------------------------------------------------


def _make_mock_supabase():
    """Create a mock Supabase client with chainable table/storage methods."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_table.upsert.return_value = mock_table
    mock_table.update.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.in_.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[])
    mock_client.table.return_value = mock_table
    return mock_client, mock_table


@patch.dict(
    os.environ,
    {"SUPABASE_URL": "http://test.supabase.co", "SUPABASE_SERVICE_KEY": "test-key"},
)
@patch("scripts.dashboard_sync.create_client")
class TestPushManifestSchemaValidation:
    """push_manifest validates schema_version before pushing."""

    def test_accepts_valid_v2_manifest(self, mock_create_client, tmp_path):
        mock_client, mock_table = _make_mock_supabase()
        mock_create_client.return_value = mock_client

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()

        manifest = {
            "schema_version": "workflow-manifest-v2",
            "format": "vsl",
            "slug": "test",
            "current_phase": "script",
            "scenes": [],
        }
        manifest_file = tmp_path / "valid_manifest.json"
        manifest_file.write_text(json.dumps(manifest))

        sync.push_manifest(str(manifest_file))

        # Should have called upsert (at least for the production row)
        mock_table.upsert.assert_called()

    def test_rejects_manifest_without_schema_version(
        self, mock_create_client, tmp_path
    ):
        mock_client, mock_table = _make_mock_supabase()
        mock_create_client.return_value = mock_client

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()

        manifest = {
            "scenes": [{"scene_id": "scene_01"}],
        }
        manifest_file = tmp_path / "no_version_manifest.json"
        manifest_file.write_text(json.dumps(manifest))

        sync.push_manifest(str(manifest_file))

        # Should NOT have called upsert (rejected before Supabase ops)
        mock_table.upsert.assert_not_called()

    def test_rejects_manifest_with_wrong_schema_version(
        self, mock_create_client, tmp_path
    ):
        mock_client, mock_table = _make_mock_supabase()
        mock_create_client.return_value = mock_client

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()

        manifest = {
            "schema_version": "v1",
            "format": "vsl",
            "slug": "test",
            "scenes": [],
        }
        manifest_file = tmp_path / "wrong_version_manifest.json"
        manifest_file.write_text(json.dumps(manifest))

        sync.push_manifest(str(manifest_file))

        # Should NOT have called upsert (rejected before Supabase ops)
        mock_table.upsert.assert_not_called()


@patch.dict(
    os.environ,
    {"SUPABASE_URL": "http://test.supabase.co", "SUPABASE_SERVICE_KEY": "test-key"},
)
@patch("scripts.dashboard_sync.create_client")
class TestPushVideoVersionOnConflict:
    """push_video_version uses 3-column on_conflict matching schema constraint."""

    def test_on_conflict_uses_three_columns(self, mock_create_client):
        mock_client, mock_table = _make_mock_supabase()
        mock_create_client.return_value = mock_client

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()

        version_data = {
            "version": 1,
            "quality": "preview",
            "storage_url": "https://example.com/video.mp4",
            "rendered_at": "2026-03-11T12:00:00Z",
            "render_duration_s": 120,
            "is_approved": False,
            "file_size_bytes": 1024000,
        }

        sync.push_video_version("pid", version_data)

        upsert_calls = mock_table.upsert.call_args_list
        assert len(upsert_calls) > 0

        # Check on_conflict kwarg is 3 columns
        _, kwargs = upsert_calls[0]
        assert kwargs.get("on_conflict") == "production_id,version,quality"

        # Check file_size_bytes is included in the row
        row = upsert_calls[0][0][0]
        assert row["file_size_bytes"] == 1024000
