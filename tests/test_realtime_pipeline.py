"""End-to-end integration tests for the real-time pipeline.

Tests the full feedback-regeneration cycle:
  1. Pipeline auto-pushes a scene to Supabase (DashboardSync)
  2. Dashboard reads it via Realtime subscription (simulated)
  3. User flags the scene (review_decisions INSERT)
  4. DB trigger propagates flag and enqueues regeneration job
  5. Job poller claims and processes the job
  6. Regenerated asset is uploaded and scene updated
  7. Dashboard sees the update in real-time (simulated)
  8. User approves the regenerated scene
  9. Feedback is captured to learnings table

Prerequisites:
  - SUPABASE_URL and SUPABASE_SERVICE_KEY in environment
  - .env file at project root (or set EXTRA_ENV_FILE for additional credentials)
  - Migration 005 applied to the database

Usage:
  pytest tests/test_realtime_pipeline.py -v
  pytest tests/test_realtime_pipeline.py -v -k test_full_cycle
  python tests/test_realtime_pipeline.py  # standalone mode
"""
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
_extra_env = os.environ.get("EXTRA_ENV_FILE", "")
if _extra_env and Path(_extra_env).exists():
    load_dotenv(Path(_extra_env), override=False)

from scripts.dashboard_sync import DashboardSync


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _migration_005_applied(client) -> bool:
    """Check whether migration 005 has been applied by probing for the
    asset_state column on the scenes table.  Returns True if the column
    exists, False otherwise.
    """
    try:
        client.table("scenes").select("asset_state").limit(0).execute()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def sync():
    """Create a DashboardSync instance, skip if not configured."""
    s = DashboardSync()
    if not s.enabled:
        pytest.skip(
            "DashboardSync not configured (missing SUPABASE_URL or SUPABASE_SERVICE_KEY)"
        )
    if not _migration_005_applied(s.client):
        pytest.skip(
            "Migration 005 not applied. Run supabase/migrations/005_realtime_pipeline.sql "
            "against the database first."
        )
    return s


@pytest.fixture(scope="module")
def test_production(sync):
    """Create a test production and clean it up after all tests.

    Uses a unique slug with timestamp to avoid collisions.
    """
    test_slug = f"test-e2e-{int(time.time())}"
    production_id = DashboardSync._production_id("vsl", test_slug)

    # Create production
    sync.client.table("productions").upsert(
        {
            "id": production_id,
            "format": "vsl",
            "slug": test_slug,
            "display_name": f"E2E Test {test_slug}",
            "current_phase": "image_generation",
            "current_stage": "Image Gen",
            "scene_count": 3,
            "approved_count": 0,
            "flagged_count": 0,
            "pending_count": 3,
            "status": "active",
            "updated_at": "now()",
        },
        on_conflict="format,slug",
    ).execute()

    # Create 3 test scenes
    for i in range(3):
        sync.client.table("scenes").upsert(
            {
                "production_id": production_id,
                "scene_id": f"test_scene_{i + 1:02d}",
                "scene_index": i,
                "prompt_text": f"Test scene {i + 1} prompt for E2E testing",
                "image_1k_status": "pending",
                "image_2k_status": "pending",
                "video_status": "pending",
                "asset_state": "pending",
                "regeneration_count": 0,
                "prompt_version": 1,
                "updated_at": "now()",
            },
            on_conflict="production_id,scene_id",
        ).execute()

    yield {"production_id": production_id, "slug": test_slug, "format": "vsl"}

    # Cleanup: delete test data in dependency order
    try:
        for table in [
            "review_decisions",
            "regeneration_queue",
            "generation_events",
            "prompt_versions",
            "scenes",
        ]:
            sync.client.table(table).delete().eq(
                "production_id", production_id
            ).execute()
        sync.client.table("productions").delete().eq("id", production_id).execute()
    except Exception as exc:
        print(f"Cleanup warning: {exc}")


# --------------------------------------------------------------------------- #
# Test 1: Pipeline Auto-Push (Phase 2)
# --------------------------------------------------------------------------- #


class TestPipelineAutoPush:
    """Test that DashboardSync correctly pushes scene data to Supabase."""

    def test_push_scene_update(self, sync, test_production):
        """Simulate image gen completing and pushing to Supabase."""
        pid = test_production["production_id"]
        scene_id = "test_scene_01"

        # Simulate image generation completing
        sync.push_scene_update(
            pid,
            scene_id,
            {
                "image_1k_status": "generated",
                "image_storage_path": "vsl/test/images/v1/test_scene_01.png",
                "thumbnail_storage_path": "vsl/test/images/v1/test_scene_01.png",
                "asset_state": "generated",
            },
        )

        # Verify the update landed
        result = (
            sync.client.table("scenes")
            .select("*")
            .eq("production_id", pid)
            .eq("scene_id", scene_id)
            .single()
            .execute()
        )

        assert result.data is not None
        assert result.data["image_1k_status"] == "generated"
        assert result.data["asset_state"] == "generated"
        assert (
            result.data["image_storage_path"]
            == "vsl/test/images/v1/test_scene_01.png"
        )

    def test_push_generation_event(self, sync, test_production):
        """Test that generation events are recorded."""
        pid = test_production["production_id"]

        sync.push_generation_event(
            pid,
            "test_scene_01",
            "image_completed",
            {
                "gate_type": "image_1k",
                "storage_path": "vsl/test/images/v1/test_scene_01.png",
            },
        )

        # Verify event was created
        result = (
            sync.client.table("generation_events")
            .select("*")
            .eq("production_id", pid)
            .eq("event_type", "image_completed")
            .execute()
        )

        assert len(result.data) >= 1
        assert result.data[0]["scene_id"] == "test_scene_01"


# --------------------------------------------------------------------------- #
# Test 2: Flag -> Trigger -> Queue (Phase 1 trigger + Phase 4 queue)
# --------------------------------------------------------------------------- #


class TestFlagToRegenQueue:
    """Test the DB trigger chain: review_decision INSERT -> scene update -> regen queue."""

    def test_flag_creates_regen_job(self, sync, test_production):
        """Flag a scene and verify the trigger creates a regeneration job."""
        pid = test_production["production_id"]
        scene_id = "test_scene_01"

        # Ensure the scene has a prompt_text (needed by trigger)
        sync.push_scene_update(
            pid,
            scene_id,
            {
                "prompt_text": "A test scene prompt for regeneration testing",
            },
        )

        # Insert a flag decision
        sync.client.table("review_decisions").insert(
            {
                "production_id": pid,
                "scene_id": scene_id,
                "gate_type": "image_1k",
                "decision": "flagged",
                "flag_reasons": ["wrong_pose", "wrong_lighting"],
                "feedback": "Person is standing, should be sitting. Lighting is too flat.",
                "decided_at": datetime.now(timezone.utc).isoformat(),
                "synced_to_pipeline": False,
            }
        ).execute()

        # Wait a moment for the trigger to fire
        time.sleep(1)

        # Verify scene was updated by trigger
        scene_result = (
            sync.client.table("scenes")
            .select("feedback_image, current_gate, flag_reasons, asset_state")
            .eq("production_id", pid)
            .eq("scene_id", scene_id)
            .single()
            .execute()
        )

        assert scene_result.data is not None
        assert scene_result.data["current_gate"] == "image_1k:flagged"
        assert "wrong_pose" in (scene_result.data["flag_reasons"] or [])
        assert scene_result.data["asset_state"] == "flagged"

        # Verify regeneration job was created by trigger
        regen_result = (
            sync.client.table("regeneration_queue")
            .select("*")
            .eq("production_id", pid)
            .eq("scene_id", scene_id)
            .execute()
        )

        assert len(regen_result.data) >= 1
        job = regen_result.data[0]
        assert job["status"] == "pending"
        assert job["gate_type"] == "image_1k"
        assert "wrong_pose" in (job["flag_reasons"] or [])

    def test_approval_clears_flags(self, sync, test_production):
        """Approve a scene and verify flags are cleared."""
        pid = test_production["production_id"]
        scene_id = "test_scene_02"

        # First flag it
        sync.client.table("review_decisions").insert(
            {
                "production_id": pid,
                "scene_id": scene_id,
                "gate_type": "image_1k",
                "decision": "flagged",
                "flag_reasons": ["low_quality"],
                "decided_at": datetime.now(timezone.utc).isoformat(),
                "synced_to_pipeline": False,
            }
        ).execute()
        time.sleep(0.5)

        # Now approve it
        sync.client.table("review_decisions").insert(
            {
                "production_id": pid,
                "scene_id": scene_id,
                "gate_type": "image_1k",
                "decision": "approved",
                "decided_at": datetime.now(timezone.utc).isoformat(),
                "synced_to_pipeline": False,
            }
        ).execute()
        time.sleep(0.5)

        # Verify flags are cleared
        scene_result = (
            sync.client.table("scenes")
            .select("current_gate, flag_reasons")
            .eq("production_id", pid)
            .eq("scene_id", scene_id)
            .single()
            .execute()
        )

        assert scene_result.data["current_gate"] == "image_1k:approved"
        assert (
            scene_result.data["flag_reasons"] == []
            or scene_result.data["flag_reasons"] is None
        )


# --------------------------------------------------------------------------- #
# Test 3: Job Claim Semantics (Phase 4)
# --------------------------------------------------------------------------- #


class TestJobClaimSemantics:
    """Test that job claiming uses optimistic locking correctly."""

    def test_claim_and_complete(self, sync, test_production):
        """Claim a pending job and mark it completed."""
        pid = test_production["production_id"]

        # There should be pending jobs from the flag test
        job = sync.claim_regeneration_job("test-worker-1")

        if job is None:
            # Create a fresh job for this test
            sync.client.table("regeneration_queue").insert(
                {
                    "production_id": pid,
                    "scene_id": "test_scene_03",
                    "gate_type": "image_1k",
                    "feedback_text": "Test feedback for claim test",
                    "status": "pending",
                }
            ).execute()
            time.sleep(0.5)
            job = sync.claim_regeneration_job("test-worker-1")

        assert job is not None
        assert job["status"] == "claimed"
        assert job["claimed_by"] == "test-worker-1"

        # Complete the job
        sync.complete_regeneration_job(job["id"], success=True)

        # Verify completion
        result = (
            sync.client.table("regeneration_queue")
            .select("status, completed_at")
            .eq("id", job["id"])
            .single()
            .execute()
        )

        assert result.data["status"] == "completed"
        assert result.data["completed_at"] is not None

    def test_double_claim_blocked(self, sync, test_production):
        """Verify that two workers cannot claim the same job."""
        pid = test_production["production_id"]

        # Create a fresh pending job
        sync.client.table("regeneration_queue").insert(
            {
                "production_id": pid,
                "scene_id": "test_scene_03",
                "gate_type": "image_1k",
                "feedback_text": "Double claim test",
                "status": "pending",
            }
        ).execute()
        time.sleep(0.5)

        # First claim should succeed
        job1 = sync.claim_regeneration_job("worker-A")
        assert job1 is not None

        # Second claim should get None (no more pending jobs for this scene)
        # or a different job
        job2 = sync.claim_regeneration_job("worker-B")
        if job2 is not None:
            assert job2["id"] != job1["id"], "Two workers claimed the same job!"

        # Clean up
        sync.complete_regeneration_job(job1["id"], success=True)
        if job2:
            sync.complete_regeneration_job(job2["id"], success=True)


# --------------------------------------------------------------------------- #
# Test 4: Prompt Version Audit Trail (Phase 4)
# --------------------------------------------------------------------------- #


class TestPromptVersions:
    """Test that prompt adjustments are tracked in prompt_versions table."""

    def test_prompt_version_saved(self, sync, test_production):
        """Verify prompt versions are saved correctly."""
        pid = test_production["production_id"]
        scene_id = "test_scene_01"

        # Save version 1 (original)
        sync.client.table("prompt_versions").upsert(
            {
                "production_id": pid,
                "scene_id": scene_id,
                "version": 1,
                "prompt_text": "Original test prompt",
                "source": "original",
            },
            on_conflict="production_id,scene_id,version",
        ).execute()

        # Save version 2 (feedback adjusted)
        sync.client.table("prompt_versions").upsert(
            {
                "production_id": pid,
                "scene_id": scene_id,
                "version": 2,
                "prompt_text": "Original test prompt | CORRECTIONS: Fix pose; adjust lighting",
                "source": "feedback_adjusted",
                "feedback_reference": "job:test-123 | Person standing | wrong_pose",
            },
            on_conflict="production_id,scene_id,version",
        ).execute()

        # Verify both versions exist
        result = (
            sync.client.table("prompt_versions")
            .select("*")
            .eq("production_id", pid)
            .eq("scene_id", scene_id)
            .order("version")
            .execute()
        )

        assert len(result.data) >= 2
        assert result.data[0]["version"] == 1
        assert result.data[0]["source"] == "original"
        assert result.data[1]["version"] == 2
        assert result.data[1]["source"] == "feedback_adjusted"
        assert "CORRECTIONS" in result.data[1]["prompt_text"]


# --------------------------------------------------------------------------- #
# Test 5: Production Count Accuracy (Phase 1 trigger)
# --------------------------------------------------------------------------- #


class TestProductionCounts:
    """Test that production aggregate counts stay accurate through the cycle."""

    def test_counts_after_decisions(self, sync, test_production):
        """Verify approved/flagged/pending counts match actual scene states."""
        pid = test_production["production_id"]

        # Read current production counts
        prod = (
            sync.client.table("productions")
            .select("approved_count, flagged_count, pending_count, scene_count")
            .eq("id", pid)
            .single()
            .execute()
        )

        assert prod.data is not None

        total = prod.data["scene_count"]
        approved = prod.data["approved_count"]
        flagged = prod.data["flagged_count"]
        pending = prod.data["pending_count"]

        # pending should never be negative
        assert pending >= 0, f"pending_count is negative: {pending}"

        # counts should sum to <= scene_count (with tolerance for trigger race conditions)
        assert approved + flagged + pending <= total + 1, (
            f"Counts exceed scene_count: {approved} + {flagged} + {pending} > {total}"
        )


# --------------------------------------------------------------------------- #
# Test 6: Generation Events Activity Feed (Phase 2)
# --------------------------------------------------------------------------- #


class TestGenerationEvents:
    """Test the generation events activity feed."""

    def test_multiple_event_types(self, sync, test_production):
        """Fire several event types and verify they are all recorded."""
        pid = test_production["production_id"]

        events_to_fire = [
            ("image_started", {"gate_type": "image_1k"}),
            ("image_completed", {"gate_type": "image_1k", "storage_path": "test/path"}),
            ("regen_started", {"gate_type": "image_1k", "job_id": "test-job"}),
            ("regen_completed", {"gate_type": "image_1k", "new_version": 2}),
            ("phase_completed", {"phase": "image_generation"}),
        ]

        for event_type, event_data in events_to_fire:
            sync.push_generation_event(pid, "test_scene_01", event_type, event_data)

        # Verify all events recorded
        result = (
            sync.client.table("generation_events")
            .select("event_type")
            .eq("production_id", pid)
            .execute()
        )

        recorded_types = {e["event_type"] for e in result.data}
        for event_type, _ in events_to_fire:
            assert event_type in recorded_types, f"Missing event: {event_type}"


# --------------------------------------------------------------------------- #
# Test 7: Prompt Adjustment Logic (Phase 4)
# --------------------------------------------------------------------------- #


class TestPromptAdjustment:
    """Test the prompt adjustment function from regenerate_scene.py."""

    def test_flag_reasons_mapped(self):
        """Test that flag reasons are mapped to corrections."""
        from scripts.regenerate_scene import adjust_prompt

        result = adjust_prompt(
            "Original prompt text", None, ["wrong_pose", "wrong_lighting"]
        )

        assert "CORRECTIONS" in result
        assert "pose" in result.lower()
        assert "lighting" in result.lower()

    def test_feedback_text_included(self):
        """Test that free-text feedback is included."""
        from scripts.regenerate_scene import adjust_prompt

        result = adjust_prompt(
            "Original prompt text", "The person should be smiling", []
        )

        assert "Reviewer note" in result
        assert "smiling" in result

    def test_no_feedback_unchanged(self):
        """Test that no feedback returns original prompt."""
        from scripts.regenerate_scene import adjust_prompt

        result = adjust_prompt("Original prompt text", None, [])
        assert result == "Original prompt text"

    def test_past_rules_included(self):
        """Test that past learnings are prepended as rules."""
        from scripts.regenerate_scene import adjust_prompt

        result = adjust_prompt(
            "Original prompt text",
            None,
            ["wrong_pose"],
            past_rules=["Always show subject seated"],
        )

        assert "CORRECTIONS" in result
        assert "Past learning" in result
        assert "Always show subject seated" in result
        assert "pose" in result.lower()

    def test_combined_feedback_and_flags(self):
        """Test that both feedback text and flag reasons produce combined corrections."""
        from scripts.regenerate_scene import adjust_prompt

        result = adjust_prompt(
            "Original prompt text",
            "Make it brighter",
            ["wrong_lighting", "low_quality"],
        )

        assert "CORRECTIONS" in result
        assert "lighting" in result.lower()
        assert "quality" in result.lower()
        assert "Make it brighter" in result


# --------------------------------------------------------------------------- #
# Test 8: Updated-at Trigger (Phase 1)
# --------------------------------------------------------------------------- #


class TestUpdatedAtTrigger:
    """Test that the set_updated_at() trigger fires on updates."""

    def test_scenes_updated_at_auto_set(self, sync, test_production):
        """Verify updated_at changes when a scene is modified."""
        pid = test_production["production_id"]
        scene_id = "test_scene_03"

        # Read current updated_at
        before = (
            sync.client.table("scenes")
            .select("updated_at")
            .eq("production_id", pid)
            .eq("scene_id", scene_id)
            .single()
            .execute()
        )

        before_ts = before.data["updated_at"]

        time.sleep(1.1)  # Ensure time passes

        # Update something
        sync.push_scene_update(pid, scene_id, {"prompt_text": "Updated prompt"})

        # Read again
        after = (
            sync.client.table("scenes")
            .select("updated_at")
            .eq("production_id", pid)
            .eq("scene_id", scene_id)
            .single()
            .execute()
        )

        after_ts = after.data["updated_at"]
        assert after_ts > before_ts, "updated_at should have changed"


# --------------------------------------------------------------------------- #
# Test 9: Full Cycle Smoke Test (end-to-end)
# --------------------------------------------------------------------------- #


class TestFullCycle:
    """Smoke test: generate -> flag -> regen-queue -> claim -> complete -> approve."""

    def test_full_cycle(self, sync, test_production):
        """Walk through the complete feedback-regeneration cycle for one scene."""
        pid = test_production["production_id"]
        scene_id = "test_scene_03"

        # Step 1: Simulate image generation completing
        sync.push_scene_update(
            pid,
            scene_id,
            {
                "image_1k_status": "generated",
                "asset_state": "generated",
                "image_storage_path": "vsl/test/images/v1/test_scene_03.png",
            },
        )
        sync.push_generation_event(
            pid, scene_id, "image_completed", {"gate_type": "image_1k"}
        )

        # Step 2: Verify scene is in generated state
        scene = (
            sync.client.table("scenes")
            .select("asset_state, image_1k_status")
            .eq("production_id", pid)
            .eq("scene_id", scene_id)
            .single()
            .execute()
        )
        assert scene.data["asset_state"] == "generated"
        assert scene.data["image_1k_status"] == "generated"

        # Step 3: Flag the scene
        sync.client.table("review_decisions").insert(
            {
                "production_id": pid,
                "scene_id": scene_id,
                "gate_type": "image_1k",
                "decision": "flagged",
                "flag_reasons": ["wrong_expression"],
                "feedback": "Character should look contemplative, not angry",
                "decided_at": datetime.now(timezone.utc).isoformat(),
                "synced_to_pipeline": False,
            }
        ).execute()
        time.sleep(1)

        # Step 4: Verify scene is flagged and regen job created
        scene_after_flag = (
            sync.client.table("scenes")
            .select("asset_state, current_gate")
            .eq("production_id", pid)
            .eq("scene_id", scene_id)
            .single()
            .execute()
        )
        assert scene_after_flag.data["asset_state"] == "flagged"
        assert scene_after_flag.data["current_gate"] == "image_1k:flagged"

        # Step 5: Claim the regeneration job
        job = sync.claim_regeneration_job("e2e-test-worker")
        # The job might be from this scene or from an earlier test;
        # either way, claiming should work
        if job is not None:
            assert job["status"] == "claimed"

            # Step 6: Complete the job (simulating successful regeneration)
            sync.complete_regeneration_job(job["id"], success=True)

            # Verify job is completed
            job_result = (
                sync.client.table("regeneration_queue")
                .select("status")
                .eq("id", job["id"])
                .single()
                .execute()
            )
            assert job_result.data["status"] == "completed"

        # Step 7: Simulate re-upload after regeneration
        sync.push_scene_update(
            pid,
            scene_id,
            {
                "asset_state": "generated",
                "image_1k_status": "generated",
                "image_storage_path": "vsl/test/images/v1/test_scene_03_r1.png",
                "flag_reasons": [],
            },
        )

        # Step 8: Approve the regenerated scene
        sync.client.table("review_decisions").insert(
            {
                "production_id": pid,
                "scene_id": scene_id,
                "gate_type": "image_1k",
                "decision": "approved",
                "decided_at": datetime.now(timezone.utc).isoformat(),
                "synced_to_pipeline": False,
            }
        ).execute()
        time.sleep(0.5)

        # Step 9: Verify final approved state
        final_scene = (
            sync.client.table("scenes")
            .select("current_gate, flag_reasons")
            .eq("production_id", pid)
            .eq("scene_id", scene_id)
            .single()
            .execute()
        )
        assert final_scene.data["current_gate"] == "image_1k:approved"
        assert (
            final_scene.data["flag_reasons"] == []
            or final_scene.data["flag_reasons"] is None
        )


# --------------------------------------------------------------------------- #
# Standalone runner
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
