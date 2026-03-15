"""Unit tests for DashboardSync analytics: cost calculation, retry rate, and analytics push.

Tests verify that push_manifest() computes and includes analytics data
(phase_timing, api_usage, retry_counts, cost estimation) in the Supabase upsert payload.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
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
    mock_storage_bucket = MagicMock()
    mock_client.storage.from_.return_value = mock_storage_bucket
    return mock_client, mock_table


def _make_manifest_with_analytics(
    phase_timing=None, retry_counts=None, api_usage=None,
    scene_count=6, fmt="vsl", slug="analytics-test"
):
    """Build a manifest dict with analytics fields."""
    now = datetime.now(timezone.utc)
    scenes = []
    for i in range(scene_count):
        scenes.append({
            "scene_id": f"scene_{i + 1:02d}",
            "gates": {
                "image_1k": {"status": "approved", "attempts": 0},
                "image_2k": {"status": "approved", "attempts": 0},
                "video": {"status": "approved", "attempts": 0},
            },
            "gate_timing": {},
        })

    manifest = {
        "schema_version": "workflow-manifest-v2",
        "format": fmt,
        "slug": slug,
        "current_phase": "complete",
        "scenes": scenes,
    }
    if phase_timing is not None:
        manifest["phase_timing"] = phase_timing
    if retry_counts is not None:
        manifest["retry_counts"] = retry_counts
    if api_usage is not None:
        manifest["api_usage"] = api_usage
    return manifest


# ---------------------------------------------------------------------------
# Tests: _calculate_analytics
# ---------------------------------------------------------------------------


class TestCalculateRetryRate:
    """calculate retry_rate_percent from retry_counts and scene count."""

    def test_retry_rate_computes_correctly(self):
        from scripts.dashboard_sync import DashboardSync

        manifest = _make_manifest_with_analytics(
            scene_count=10,
            retry_counts={
                "scene_01": {"video": 2, "audio": 1},
                "scene_02": {"video": 1},
                "scene_05": {"video": 3},
            },
        )
        analytics = DashboardSync._calculate_analytics(manifest)
        # Total retries = (2+1) + (1) + (3) = 7, scenes = 10
        # retry_rate = 7 / 10 * 100 = 70.0
        assert analytics["retry_rate_percent"] == 70.0

    def test_retry_rate_zero_when_no_retries(self):
        from scripts.dashboard_sync import DashboardSync

        manifest = _make_manifest_with_analytics(scene_count=5)
        analytics = DashboardSync._calculate_analytics(manifest)
        assert analytics["retry_rate_percent"] == 0.0

    def test_retry_rate_zero_when_no_scenes(self):
        from scripts.dashboard_sync import DashboardSync

        manifest = _make_manifest_with_analytics(scene_count=0)
        analytics = DashboardSync._calculate_analytics(manifest)
        assert analytics["retry_rate_percent"] == 0.0


class TestCalculateCost:
    """Cost estimation reads config/api_costs.json and multiplies by api_usage."""

    @patch("scripts.dashboard_sync.DashboardSync._load_cost_rates")
    def test_cost_calculation_elevenlabs_and_gemini(self, mock_rates):
        from scripts.dashboard_sync import DashboardSync

        mock_rates.return_value = {
            "elevenlabs": {"cost_per_1000": 0.167},
            "gemini": {"cost_per_image": 0.005},
            "kling": {"type": "subscription", "monthly_cost": 145.00},
        }

        manifest = _make_manifest_with_analytics(
            api_usage={
                "elevenlabs_chars": 3000,
                "gemini_images": 20,
                "kling_clips": 10,
            },
        )
        analytics = DashboardSync._calculate_analytics(manifest)

        # elevenlabs: 3000 / 1000 * 0.167 = 0.501
        # gemini: 20 * 0.005 = 0.1
        # kling: 145.0 (flat subscription)
        expected = round(0.501 + 0.1 + 145.0, 2)
        assert analytics["total_cost_estimate"] == expected

    @patch("scripts.dashboard_sync.DashboardSync._load_cost_rates")
    def test_cost_zero_when_no_api_usage(self, mock_rates):
        from scripts.dashboard_sync import DashboardSync

        mock_rates.return_value = {
            "elevenlabs": {"cost_per_1000": 0.167},
            "gemini": {"cost_per_image": 0.005},
            "kling": {"type": "subscription", "monthly_cost": 145.00},
        }
        manifest = _make_manifest_with_analytics()
        analytics = DashboardSync._calculate_analytics(manifest)
        assert analytics["total_cost_estimate"] == 0.0

    @patch("scripts.dashboard_sync.DashboardSync._load_cost_rates")
    def test_kling_shown_as_subscription(self, mock_rates):
        from scripts.dashboard_sync import DashboardSync

        mock_rates.return_value = {
            "kling": {"type": "subscription", "monthly_cost": 145.00},
        }
        manifest = _make_manifest_with_analytics(
            api_usage={"kling_clips": 50},
        )
        analytics = DashboardSync._calculate_analytics(manifest)
        # Kling cost is flat subscription, not per-clip
        assert analytics["total_cost_estimate"] == 145.0


class TestCalculatePhaseDuration:
    """Phase duration computed from phase_timing started_at/completed_at."""

    @patch("scripts.dashboard_sync.DashboardSync._load_cost_rates")
    def test_total_duration_computed_from_phases(self, mock_rates):
        from scripts.dashboard_sync import DashboardSync

        mock_rates.return_value = {}
        now = datetime.now(timezone.utc)

        manifest = _make_manifest_with_analytics(
            phase_timing={
                "scene_design": {
                    "started_at": (now - timedelta(minutes=30)).isoformat(),
                    "completed_at": (now - timedelta(minutes=20)).isoformat(),
                },
                "image_generation": {
                    "started_at": (now - timedelta(minutes=20)).isoformat(),
                    "completed_at": now.isoformat(),
                },
            },
        )
        analytics = DashboardSync._calculate_analytics(manifest)
        # 10 min + 20 min = 30 min total
        assert analytics["total_duration_minutes"] == pytest.approx(30.0, abs=0.1)
        assert len(analytics["phases"]) == 2

    @patch("scripts.dashboard_sync.DashboardSync._load_cost_rates")
    def test_phases_array_includes_phase_details(self, mock_rates):
        from scripts.dashboard_sync import DashboardSync

        mock_rates.return_value = {}
        now = datetime.now(timezone.utc)

        manifest = _make_manifest_with_analytics(
            phase_timing={
                "scene_design": {
                    "started_at": (now - timedelta(minutes=15)).isoformat(),
                    "completed_at": now.isoformat(),
                },
            },
        )
        analytics = DashboardSync._calculate_analytics(manifest)
        phase = analytics["phases"][0]
        assert phase["phase_name"] == "scene_design"
        assert phase["duration_minutes"] == pytest.approx(15.0, abs=0.1)


# ---------------------------------------------------------------------------
# Tests: push_manifest includes analytics in upsert payload
# ---------------------------------------------------------------------------


@patch.dict(os.environ, {"SUPABASE_URL": "http://test.supabase.co", "SUPABASE_SERVICE_KEY": "test-key"})
@patch("scripts.dashboard_sync.create_client")
class TestPushManifestIncludesAnalytics:
    """push_manifest() adds analytics dict to the Supabase upsert payload."""

    @patch("scripts.dashboard_sync.DashboardSync._load_cost_rates")
    def test_analytics_included_in_upsert(self, mock_rates, mock_create_client):
        mock_rates.return_value = {
            "elevenlabs": {"cost_per_1000": 0.167},
            "gemini": {"cost_per_image": 0.005},
            "kling": {"type": "subscription", "monthly_cost": 145.00},
        }
        mock_client, mock_table = _make_mock_supabase()
        mock_create_client.return_value = mock_client

        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()
        assert sync.enabled is True

        manifest = _make_manifest_with_analytics(
            api_usage={"elevenlabs_chars": 1000, "gemini_images": 10},
            retry_counts={"scene_01": {"video": 2}},
            phase_timing={
                "image_generation": {
                    "started_at": "2026-01-01T00:00:00+00:00",
                    "completed_at": "2026-01-01T00:10:00+00:00",
                },
            },
        )
        manifest_path = "/tmp/test_analytics_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        sync.push_manifest(manifest_path)

        # Get the production row from the first upsert call
        upsert_calls = mock_table.upsert.call_args_list
        assert len(upsert_calls) > 0
        prod_row = upsert_calls[0][0][0]

        # analytics key should be present
        assert "analytics" in prod_row
        analytics = prod_row["analytics"]
        assert "total_cost_estimate" in analytics
        assert "retry_rate_percent" in analytics
        assert "total_duration_minutes" in analytics
        assert "phases" in analytics
        assert analytics["retry_rate_percent"] > 0


# ---------------------------------------------------------------------------
# Tests: _load_cost_rates
# ---------------------------------------------------------------------------


class TestLoadCostRates:
    """_load_cost_rates reads config/api_costs.json."""

    @patch("builtins.open", side_effect=FileNotFoundError("not found"))
    def test_returns_empty_dict_when_file_missing(self, mock_open):
        from scripts.dashboard_sync import DashboardSync

        rates = DashboardSync._load_cost_rates()
        assert rates == {}

    def test_loads_rates_from_config_file(self, tmp_path):
        from scripts.dashboard_sync import DashboardSync

        config = {
            "rates": {
                "elevenlabs": {"cost_per_1000": 0.167},
                "kling": {"type": "subscription", "monthly_cost": 145.0},
            }
        }
        config_file = tmp_path / "api_costs.json"
        config_file.write_text(json.dumps(config))

        with patch("scripts.dashboard_sync.Path") as mock_path:
            # Make Path(__file__).resolve().parent.parent / "config" / "api_costs.json"
            # return our temp file
            mock_path_inst = MagicMock()
            mock_path.return_value = mock_path_inst
            mock_path_inst.resolve.return_value = mock_path_inst
            mock_path_inst.parent = mock_path_inst
            mock_path_inst.__truediv__ = lambda self, other: (
                tmp_path / other if other == "api_costs.json"
                else self
            )

            rates = DashboardSync._load_cost_rates()
            assert "elevenlabs" in rates
            assert rates["elevenlabs"]["cost_per_1000"] == 0.167
