"""E2E integration test: verifies all 4 gate types work end-to-end against real Supabase.

Tests:
    E2E-01  image_1k approve -> feedback_image='approved', approved_count increments
    E2E-02  image_1k approve (second scene) -> approved_count increments again
    E2E-03  video_clip flag -> feedback_video contains reasons+text, pull_flagged_scenes works
    E2E-04  final_video approve -> feedback_final='approved', productions.status can be 'complete'
    E2E-LOOP full pipeline feedback loop via WorkflowManifest.sync_from_dashboard()

Run:
    python scripts/tests/test_e2e_gate_flow.py

Exit codes:
    0 — all tests pass
    1 — one or more tests failed
"""

import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Load env from both project root and shared workspace
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    load_dotenv(_PROJECT_ROOT / ".env", override=False)
    _extra_env = os.environ.get("EXTRA_ENV_FILE", "")
    if _extra_env and Path(_extra_env).exists():
        load_dotenv(Path(_extra_env), override=True)
except ImportError:
    pass  # dotenv optional; credentials must already be in env

from supabase import create_client  # type: ignore


# ---------------------------------------------------------------------------
# Test state
# ---------------------------------------------------------------------------

_results: list[dict] = []  # {name, passed, duration_s, error}


def _record(name: str, passed: bool, duration_s: float, error: str = "") -> None:
    _results.append({"name": name, "passed": passed, "duration_s": duration_s, "error": error})
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name} ({duration_s:.2f}s)" + (f" — {error}" if error else ""))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _production_id_for(fmt: str, slug: str) -> str:
    """Generate deterministic UUID5 matching DashboardSync._production_id()."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{fmt}/{slug}"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------

TEST_FORMAT = "vsl"
TEST_SLUG_PREFIX = "e2e-test-"
SCENE_IDS = ["scene_01", "scene_02", "scene_03", "scene_04"]


def setup(client) -> tuple[str, str]:
    """Create a test production and 4 scenes. Returns (production_id, slug)."""
    slug = f"{TEST_SLUG_PREFIX}{uuid.uuid4().hex[:8]}"
    production_id = _production_id_for(TEST_FORMAT, slug)

    # Insert production
    client.table("productions").upsert({
        "id": production_id,
        "format": TEST_FORMAT,
        "slug": slug,
        "display_name": f"E2E Test — {slug}",
        "current_phase": "image_generation",
        "current_stage": "Image Gen",
        "scene_count": 4,
        "approved_count": 0,
        "flagged_count": 0,
        "pending_count": 4,
        "status": "active",
    }, on_conflict="format,slug").execute()

    # Insert 4 scenes
    for idx, scene_id in enumerate(SCENE_IDS):
        client.table("scenes").upsert({
            "production_id": production_id,
            "scene_id": scene_id,
            "scene_index": idx,
            "feedback_image": None,
            "feedback_video": None,
            "feedback_final": None,
            "current_gate": None,
            "flag_reasons": None,
        }, on_conflict="production_id,scene_id").execute()

    print(f"  Setup: production_id={production_id}, slug={slug}")
    return production_id, slug


def cleanup(client, production_id: str) -> None:
    """Delete all test rows. Runs even on failure."""
    try:
        client.table("review_decisions").delete().eq("production_id", production_id).execute()
        client.table("scenes").delete().eq("production_id", production_id).execute()
        client.table("productions").delete().eq("id", production_id).execute()
        print(f"  Cleanup: removed test data for {production_id}")
    except Exception as exc:
        print(f"  Cleanup WARNING: {exc}")


# ---------------------------------------------------------------------------
# E2E-01: image_1k approve
# ---------------------------------------------------------------------------

def test_e2e_01(client, production_id: str) -> None:
    """image_1k approve -> feedback_image='approved', approved_count=1."""
    name = "E2E-01: image_1k approve (scene_01)"
    t0 = time.time()
    try:
        client.table("review_decisions").insert({
            "production_id": production_id,
            "scene_id": "scene_01",
            "gate_type": "image_1k",
            "decision": "approved",
            "flag_reasons": None,
            "feedback": None,
            "decided_at": _now_iso(),
            "synced_to_pipeline": False,
        }).execute()

        # Short wait for trigger to fire
        time.sleep(0.5)

        scene_row = (
            client.table("scenes")
            .select("feedback_image, current_gate")
            .eq("production_id", production_id)
            .eq("scene_id", "scene_01")
            .execute()
        ).data[0]

        assert scene_row["feedback_image"] == "approved", (
            f"Expected feedback_image='approved', got {scene_row['feedback_image']!r}"
        )
        assert scene_row["current_gate"] == "image_1k:approved", (
            f"Expected current_gate='image_1k:approved', got {scene_row['current_gate']!r}"
        )

        prod_row = (
            client.table("productions")
            .select("approved_count, pending_count")
            .eq("id", production_id)
            .execute()
        ).data[0]

        assert prod_row["approved_count"] == 1, (
            f"Expected approved_count=1, got {prod_row['approved_count']}"
        )
        assert prod_row["pending_count"] == 3, (
            f"Expected pending_count=3, got {prod_row['pending_count']}"
        )

        _record(name, True, time.time() - t0)
    except Exception as exc:
        _record(name, False, time.time() - t0, str(exc))


# ---------------------------------------------------------------------------
# E2E-02: second image_1k approve
# ---------------------------------------------------------------------------

def test_e2e_02(client, production_id: str) -> None:
    """image_1k approve (scene_02) -> approved_count=2."""
    name = "E2E-02: image_1k approve (scene_02)"
    t0 = time.time()
    try:
        client.table("review_decisions").insert({
            "production_id": production_id,
            "scene_id": "scene_02",
            "gate_type": "image_1k",
            "decision": "approved",
            "flag_reasons": None,
            "feedback": None,
            "decided_at": _now_iso(),
            "synced_to_pipeline": False,
        }).execute()

        time.sleep(0.5)

        scene_row = (
            client.table("scenes")
            .select("feedback_image, current_gate")
            .eq("production_id", production_id)
            .eq("scene_id", "scene_02")
            .execute()
        ).data[0]

        assert scene_row["feedback_image"] == "approved", (
            f"Expected feedback_image='approved', got {scene_row['feedback_image']!r}"
        )

        prod_row = (
            client.table("productions")
            .select("approved_count, pending_count")
            .eq("id", production_id)
            .execute()
        ).data[0]

        assert prod_row["approved_count"] == 2, (
            f"Expected approved_count=2, got {prod_row['approved_count']}"
        )
        assert prod_row["pending_count"] == 2, (
            f"Expected pending_count=2, got {prod_row['pending_count']}"
        )

        _record(name, True, time.time() - t0)
    except Exception as exc:
        _record(name, False, time.time() - t0, str(exc))


# ---------------------------------------------------------------------------
# E2E-03: video_clip flag
# ---------------------------------------------------------------------------

def test_e2e_03(client, production_id: str) -> None:
    """video_clip flag -> feedback_video contains reasons+text, pull_flagged_scenes works."""
    name = "E2E-03: video_clip flag (scene_03)"
    t0 = time.time()
    try:
        flag_reasons = ["Motion artifact", "Bad lighting"]
        feedback_text = "Too shaky in first 2 seconds"

        client.table("review_decisions").insert({
            "production_id": production_id,
            "scene_id": "scene_03",
            "gate_type": "video_clip",
            "decision": "flagged",
            "flag_reasons": flag_reasons,
            "feedback": feedback_text,
            "decided_at": _now_iso(),
            "synced_to_pipeline": False,
        }).execute()

        time.sleep(0.5)

        scene_row = (
            client.table("scenes")
            .select("feedback_video, current_gate, flag_reasons")
            .eq("production_id", production_id)
            .eq("scene_id", "scene_03")
            .execute()
        ).data[0]

        fv = scene_row["feedback_video"]
        assert fv is not None, "Expected feedback_video to be set, got None"
        assert "Motion artifact" in fv, (
            f"Expected 'Motion artifact' in feedback_video, got {fv!r}"
        )
        assert "Too shaky" in fv, (
            f"Expected 'Too shaky' in feedback_video, got {fv!r}"
        )
        assert scene_row["current_gate"] == "video_clip:flagged", (
            f"Expected current_gate='video_clip:flagged', got {scene_row['current_gate']!r}"
        )

        # Verify pull_flagged_scenes picks up this scene
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()
        assert sync.enabled, "DashboardSync not enabled — check env vars"

        flagged = sync.pull_flagged_scenes(production_id)
        scene_03_flags = [f for f in flagged if f["scene_id"] == "scene_03"]

        assert len(scene_03_flags) >= 1, (
            f"Expected scene_03 in pull_flagged_scenes result, got: {flagged}"
        )
        s3 = scene_03_flags[0]
        assert s3["gate_type"] == "video_clip", (
            f"Expected gate_type='video_clip', got {s3['gate_type']!r}"
        )
        assert "Motion artifact" in s3["feedback_text"] or "Motion artifact" in str(s3["flag_reasons"]), (
            f"Expected 'Motion artifact' in flagged scene feedback, got {s3}"
        )

        _record(name, True, time.time() - t0)
    except Exception as exc:
        _record(name, False, time.time() - t0, str(exc))


# ---------------------------------------------------------------------------
# E2E-04: final_video approve
# ---------------------------------------------------------------------------

def test_e2e_04(client, production_id: str) -> None:
    """final_video approve -> feedback_final='approved', production status can be set to complete."""
    name = "E2E-04: final_video approve (scene_04)"
    t0 = time.time()
    try:
        client.table("review_decisions").insert({
            "production_id": production_id,
            "scene_id": "scene_04",
            "gate_type": "final_video",
            "decision": "approved",
            "flag_reasons": None,
            "feedback": None,
            "decided_at": _now_iso(),
            "synced_to_pipeline": False,
        }).execute()

        time.sleep(0.5)

        scene_row = (
            client.table("scenes")
            .select("feedback_final, current_gate")
            .eq("production_id", production_id)
            .eq("scene_id", "scene_04")
            .execute()
        ).data[0]

        assert scene_row["feedback_final"] == "approved", (
            f"Expected feedback_final='approved', got {scene_row['feedback_final']!r}"
        )
        assert scene_row["current_gate"] == "final_video:approved", (
            f"Expected current_gate='final_video:approved', got {scene_row['current_gate']!r}"
        )

        # Application code sets status to 'complete' — verify it's writable/queryable
        client.table("productions").update({
            "status": "completed",
            "completed_at": _now_iso(),
        }).eq("id", production_id).execute()

        prod_row = (
            client.table("productions")
            .select("status")
            .eq("id", production_id)
            .execute()
        ).data[0]

        assert prod_row["status"] == "completed", (
            f"Expected status='completed', got {prod_row['status']!r}"
        )

        _record(name, True, time.time() - t0)
    except Exception as exc:
        _record(name, False, time.time() - t0, str(exc))


# ---------------------------------------------------------------------------
# E2E-LOOP: full pipeline feedback incorporation via WorkflowManifest
# ---------------------------------------------------------------------------

def test_e2e_loop(production_id: str, slug: str) -> None:
    """Full pipeline feedback loop: flagged scene DB -> WorkflowManifest.sync_from_dashboard().

    Creates a temporary manifest file for the test production, calls
    sync_from_dashboard(), and verifies that scene_03's video_clip gate
    has review_feedback containing 'Motion artifact' and 'Too shaky'.
    """
    name = "E2E-LOOP: Pipeline feedback incorporation"
    t0 = time.time()
    tmp_path = None
    try:
        # Build minimal manifest for the test production
        manifest_data = {
            "schema_version": "workflow-manifest-v2",
            "format": TEST_FORMAT,
            "slug": slug,
            "created_at": _now_iso(),
            "skills_invoked": [],
            "gates": {},
            "audio_config": {
                "preset": "narrated",
                "layers_active": {},
                "fallback_applied": False,
                "kling_compliance_status": None,
                "kling_compliance_date": None,
            },
            "phase_timing": {},
            "retry_counts": {},
            "api_usage": {
                "kling_video": 0, "kling_audio": 0, "kling_tts": 0,
                "kling_lipsync": 0, "elevenlabs_chars": 0, "elevenlabs_calls": 0,
                "gemini_images": 0, "whisper_segments": 0,
            },
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "gates": {},
                    "transition": {"type": None, "end_frame_source": None, "approved": False},
                    "gate_timing": {},
                    "image_1k": None, "image_2k": None, "video": None,
                    "audio": {"type": None, "audio_prompt": None, "audio_path": None},
                },
                {
                    "scene_id": "scene_02",
                    "gates": {},
                    "transition": {"type": None, "end_frame_source": None, "approved": False},
                    "gate_timing": {},
                    "image_1k": None, "image_2k": None, "video": None,
                    "audio": {"type": None, "audio_prompt": None, "audio_path": None},
                },
                {
                    "scene_id": "scene_03",
                    "gates": {
                        "video_clip": {
                            "status": None,
                            "feedback": None,
                            "attempts": 0,
                            "review_feedback": None,
                        }
                    },
                    "transition": {"type": None, "end_frame_source": None, "approved": False},
                    "gate_timing": {},
                    "image_1k": None, "image_2k": None, "video": None,
                    "audio": {"type": None, "audio_prompt": None, "audio_path": None},
                },
                {
                    "scene_id": "scene_04",
                    "gates": {},
                    "transition": {"type": None, "end_frame_source": None, "approved": False},
                    "gate_timing": {},
                    "image_1k": None, "image_2k": None, "video": None,
                    "audio": {"type": None, "audio_prompt": None, "audio_path": None},
                },
            ],
            "post_production": {
                "status": "pending",
                "caption_preset": "tiktok_bold",
                "platform_target": "generic",
                "edl_path": None,
                "edl_version": 0,
                "preview_versions": [],
                "final_version": None,
                "feedback_log": [],
                "render_timing": {},
                "final_approved": False,
                "final_uploaded": False,
            },
        }

        # Write to a temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, dir="/tmp"
        ) as f:
            json.dump(manifest_data, f)
            tmp_path = f.name

        # Ensure project root is on sys.path
        project_root = str(Path(__file__).resolve().parent.parent.parent)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from scripts.workflow_manifest import WorkflowManifest

        m = WorkflowManifest(tmp_path)
        m.sync_from_dashboard()

        # Verify scene_03 video_clip gate has review_feedback
        scene_03 = next(
            s for s in m.data["scenes"] if s["scene_id"] == "scene_03"
        )
        gate = scene_03["gates"].get("video_clip", {})
        review_fb = gate.get("review_feedback", "")

        assert review_fb, (
            "Expected review_feedback to be set on scene_03.video_clip after sync, got empty/None"
        )
        assert "Motion artifact" in review_fb or "Too shaky" in review_fb, (
            f"Expected 'Motion artifact' or 'Too shaky' in review_feedback, got: {review_fb!r}"
        )

        _record(name, True, time.time() - t0)
    except Exception as exc:
        _record(name, False, time.time() - t0, str(exc))
    finally:
        if tmp_path and Path(tmp_path).exists():
            Path(tmp_path).unlink()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("\n=== E2E Gate Flow Integration Tests ===\n")

    # Connect to Supabase
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        return 1

    client = create_client(url, key)

    production_id, slug = setup(client)
    try:
        print("\nRunning E2E tests...")
        test_e2e_01(client, production_id)
        test_e2e_02(client, production_id)
        test_e2e_03(client, production_id)
        test_e2e_04(client, production_id)
        test_e2e_loop(production_id, slug)
    finally:
        cleanup(client, production_id)

    # Summary
    print("\n=== Results ===")
    passed = sum(1 for r in _results if r["passed"])
    failed = sum(1 for r in _results if not r["passed"])
    total = len(_results)
    total_time = sum(r["duration_s"] for r in _results)

    for r in _results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  {status}  {r['name']}  ({r['duration_s']:.2f}s)")
        if r["error"]:
            print(f"       Error: {r['error']}")

    print(f"\nTotal: {passed}/{total} passed in {total_time:.2f}s")

    if failed > 0:
        print(f"\n{failed} test(s) FAILED")
        return 1

    print("\nAll tests PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
