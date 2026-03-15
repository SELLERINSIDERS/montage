"""Workflow manifest v2 with gate state, transitions, approvals, and timing.

Extends the Phase 1 BatchManifest concept for production-wide orchestration.
Tracks per-scene gate decisions (approved/flagged/deferred), transition data,
gate timing, and uses atomic writes via video.kling.manifest.

Usage:
    # Create new manifest
    data = WorkflowManifest.create("ad", "test-slug", 8, path="state/manifest.json")

    # Load and work with existing manifest
    m = WorkflowManifest("state/manifest.json")
    m.record_gate_decision("scene_01", "image_1k", "approved")
    m.record_gate_timing("scene_01", "image_1k", "decided")
    approved = m.get_approved_scenes("image_1k")
"""

import json
import logging
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from video.kling.manifest import atomic_write_json

logger = logging.getLogger(__name__)

# Caption preset IDs for post-production
CAPTION_PRESETS = ["tiktok_bold", "clean_minimal", "cinematic_subtle"]

# Valid post-production status values
POST_PRODUCTION_STATUSES = [
    "pending",
    "generating_edl",
    "preflight",
    "rendering_preview",
    "review",
    "rendering_final",
    "complete",
]

# Audio preset defaults per production format
PRESET_DEFAULTS = {
    "vsl": "narrated",
    "ad": "narrated",
    "ugc": "full_mix",
}

# Layer configuration per preset
PRESET_LAYERS = {
    "narrated": {
        "elevenlabs_voiceover": True,
        "kling_audio": True,
        "kling_dialogue": False,
    },
    "ambient": {
        "elevenlabs_voiceover": False,
        "kling_audio": True,
        "kling_dialogue": False,
    },
    "full_mix": {
        "elevenlabs_voiceover": True,
        "kling_audio": True,
        "kling_dialogue": True,
    },
    "silent": {
        "elevenlabs_voiceover": False,
        "kling_audio": False,
        "kling_dialogue": False,
    },
}


class SceneStatus(Enum):
    """Per-scene lifecycle status across all gates."""

    PENDING = "pending"
    APPROVED = "approved"
    FLAGGED = "flagged"
    DEFERRED = "deferred"
    NEEDS_MANUAL_INTERVENTION = "needs_manual_intervention"


class GateDecision(Enum):
    """Possible decisions at any review gate."""

    APPROVED = "approved"
    FLAGGED = "flagged"
    DEFERRED = "deferred"


# Maximum flag attempts before escalating to manual intervention
_MAX_FLAG_ATTEMPTS = 3


class WorkflowManifest:
    """Production-wide workflow manifest with gate tracking and atomic writes.

    Attributes:
        path: Filesystem path to the manifest JSON.
        data: The full manifest dictionary.
    """

    def __init__(self, path: str) -> None:
        """Load an existing manifest from disk."""
        self.path = path
        self._lock = threading.Lock()
        with open(path, "r") as f:
            self.data: dict = json.load(f)

    @classmethod
    def create(
        cls,
        format: str,
        slug: str,
        scene_count: int,
        path: str,
    ) -> dict:
        """Create a new v2 workflow manifest and write to disk.

        Args:
            format: Production type ("vsl", "ad", "ugc").
            slug: Project slug identifier.
            scene_count: Number of scenes in this production.
            path: Filesystem path to write the manifest.

        Returns:
            The manifest data dictionary.
        """
        now = datetime.now(timezone.utc).isoformat()

        scenes = []
        for i in range(1, scene_count + 1):
            scene_id = f"scene_{i:02d}"
            scenes.append({
                "scene_id": scene_id,
                "gates": {},
                "transition": {
                    "type": None,
                    "end_frame_source": None,
                    "approved": False,
                },
                "gate_timing": {},
                "image_1k": None,
                "image_2k": None,
                "video": None,
                "audio": {
                    "type": None,
                    "audio_prompt": None,
                    "audio_path": None,
                },
            })

        preset = PRESET_DEFAULTS.get(format, "narrated")

        data = {
            "schema_version": "workflow-manifest-v2",
            "format": format,
            "slug": slug,
            "created_at": now,
            "skills_invoked": [],
            "gates": {},
            "audio_config": {
                "preset": preset,
                "layers_active": PRESET_LAYERS[preset],
                "fallback_applied": False,
                "kling_compliance_status": None,
                "kling_compliance_date": None,
            },
            "phase_timing": {},
            "retry_counts": {},
            "api_usage": {
                "kling_video": 0,
                "kling_audio": 0,
                "kling_tts": 0,
                "kling_lipsync": 0,
                "elevenlabs_chars": 0,
                "elevenlabs_calls": 0,
                "gemini_images": 0,
                "whisper_segments": 0,
            },
            "scenes": scenes,
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

        atomic_write_json(path, data)

        # Push to dashboard on creation so early-phase productions are visible
        try:
            from scripts.dashboard_sync import DashboardSync
            sync = DashboardSync()
            sync.push_manifest(path)
        except Exception as exc:
            logger.warning("DashboardSync push on create failed (continuing): %s", exc)

        return data

    def _find_scene(self, scene_id: str) -> dict:
        """Find a scene by ID. Raises ValueError if not found."""
        for scene in self.data["scenes"]:
            if scene["scene_id"] == scene_id:
                return scene
        raise ValueError(f"No scene with scene_id={scene_id!r}")

    def record_gate_decision(
        self,
        scene_id: str,
        gate_type: str,
        decision: str,
        feedback: Optional[str] = None,
    ) -> None:
        """Record a gate decision for a specific scene.

        Args:
            scene_id: e.g. "scene_01"
            gate_type: e.g. "image_1k", "image_2k", "video"
            decision: "approved", "flagged", or "deferred"
            feedback: Optional feedback text (typically on flagged decisions)
        """
        with self._lock:
            scene = self._find_scene(scene_id)

            # Initialize gate entry if not present
            if gate_type not in scene["gates"]:
                scene["gates"][gate_type] = {
                    "status": None,
                    "feedback": None,
                    "attempts": 0,
                }

            gate = scene["gates"][gate_type]

            if decision == GateDecision.FLAGGED.value:
                gate["attempts"] += 1
                gate["feedback"] = feedback

                if gate["attempts"] >= _MAX_FLAG_ATTEMPTS:
                    gate["status"] = SceneStatus.NEEDS_MANUAL_INTERVENTION.value
                else:
                    gate["status"] = SceneStatus.FLAGGED.value
            elif decision == GateDecision.APPROVED.value:
                gate["status"] = SceneStatus.APPROVED.value
                gate["feedback"] = feedback
            elif decision == GateDecision.DEFERRED.value:
                gate["status"] = SceneStatus.DEFERRED.value
                gate["feedback"] = feedback

            atomic_write_json(self.path, self.data)

    def record_gate_timing(
        self,
        scene_id: str,
        gate_type: str,
        event: str,
    ) -> None:
        """Record an ISO timestamp for a gate timing event.

        Args:
            scene_id: e.g. "scene_01"
            gate_type: e.g. "image_1k"
            event: "presented" or "decided"
        """
        with self._lock:
            scene = self._find_scene(scene_id)

            if gate_type not in scene["gate_timing"]:
                scene["gate_timing"][gate_type] = {}

            scene["gate_timing"][gate_type][event] = (
                datetime.now(timezone.utc).isoformat()
            )

            atomic_write_json(self.path, self.data)

    def get_approved_scenes(self, gate_type: str) -> list[dict]:
        """Return scenes where the given gate_type has status 'approved'.

        Args:
            gate_type: e.g. "image_1k", "video"

        Returns:
            List of scene dicts with approved status for this gate.
        """
        approved = []
        for scene in self.data["scenes"]:
            gate = scene["gates"].get(gate_type, {})
            if gate.get("status") == SceneStatus.APPROVED.value:
                approved.append(scene)
        return approved

    def apply_review_decisions(self, decisions: list[dict]) -> None:
        """Apply review decisions from the dashboard to scene gate states.

        Args:
            decisions: List of decision dicts with keys:
                scene_id, gate_type, decision ('approved'/'flagged'/'deferred'),
                and optional feedback.
        """
        if not decisions:
            return

        applied = 0
        with self._lock:
            for decision in decisions:
                scene_id = decision.get("scene_id")
                gate_type = decision.get("gate_type")
                verdict = decision.get("decision")
                feedback = decision.get("feedback")

                if not scene_id or not gate_type or not verdict:
                    continue

                try:
                    scene = self._find_scene(scene_id)
                except ValueError:
                    logger.warning("Review decision for unknown scene: %s", scene_id)
                    continue

                # Initialize gate entry if not present
                if gate_type not in scene["gates"]:
                    scene["gates"][gate_type] = {
                        "status": None,
                        "feedback": None,
                        "attempts": 0,
                    }

                gate = scene["gates"][gate_type]

                if verdict == "approved":
                    gate["status"] = SceneStatus.APPROVED.value
                    gate["feedback"] = feedback
                elif verdict == "flagged":
                    gate["attempts"] = gate.get("attempts", 0) + 1
                    gate["feedback"] = feedback
                    if gate["attempts"] >= _MAX_FLAG_ATTEMPTS:
                        gate["status"] = SceneStatus.NEEDS_MANUAL_INTERVENTION.value
                    else:
                        gate["status"] = SceneStatus.FLAGGED.value
                elif verdict == "deferred":
                    gate["status"] = SceneStatus.DEFERRED.value
                    gate["feedback"] = feedback

                # Format and store review feedback for regeneration prompts
                flag_reasons = decision.get("flag_reasons") or []
                reasons_str = ", ".join(flag_reasons) if isinstance(flag_reasons, list) else str(flag_reasons)
                feedback_text = feedback or ""
                if reasons_str and feedback_text:
                    review_fb = f"REVIEW FEEDBACK: [{reasons_str}] — {feedback_text}"
                elif reasons_str:
                    review_fb = f"REVIEW FEEDBACK: [{reasons_str}]"
                elif feedback_text:
                    review_fb = f"REVIEW FEEDBACK: {feedback_text}"
                else:
                    review_fb = None
                gate["review_feedback"] = review_fb

                applied += 1

            atomic_write_json(self.path, self.data)

        logger.info("Applied %d review decisions", applied)

    def sync_from_dashboard(self) -> None:
        """Pull review decisions from Supabase dashboard and apply them.

        Instantiates DashboardSync, pulls unsynced decisions for this production,
        and applies them to the manifest. Skips silently if sync is not enabled.
        """
        from scripts.dashboard_sync import DashboardSync

        sync = DashboardSync()
        if not sync.enabled:
            return

        fmt = self.data.get("format", "unknown")
        slug = self.data.get("slug", "unknown")
        production_id = DashboardSync._production_id(fmt, slug)

        decisions = sync.pull_review_decisions(production_id)
        if decisions:
            self.apply_review_decisions(decisions)
            logger.info("Applied %d review decisions from dashboard", len(decisions))
        else:
            logger.info("No new review decisions")

        # Also pull per-gate feedback from flagged scenes as secondary source
        flagged = sync.pull_flagged_scenes(production_id)
        if flagged:
            self._store_flagged_feedback(flagged)
            logger.info("Stored feedback for %d flagged scenes", len(flagged))

    def _store_flagged_feedback(self, flagged: list[dict]) -> None:
        """Store per-gate feedback from flagged scenes into manifest gate data.

        Secondary source that ensures feedback is captured even if apply_review_decisions
        missed it (e.g., decision was synced in a previous run but scene is still flagged).

        Args:
            flagged: List of dicts with scene_id, gate_type, feedback_text, flag_reasons.
        """
        with self._lock:
            for item in flagged:
                scene_id = item.get("scene_id")
                gate_type = item.get("gate_type")
                feedback_text = item.get("feedback_text", "")
                flag_reasons = item.get("flag_reasons") or []

                try:
                    scene = self._find_scene(scene_id)
                except ValueError:
                    logger.warning("Flagged feedback for unknown scene: %s", scene_id)
                    continue

                if gate_type not in scene["gates"]:
                    scene["gates"][gate_type] = {
                        "status": None,
                        "feedback": None,
                        "attempts": 0,
                    }

                gate = scene["gates"][gate_type]

                # Only store if no review_feedback already set (don't overwrite fresher data)
                if gate.get("review_feedback"):
                    continue

                reasons_str = ", ".join(flag_reasons) if isinstance(flag_reasons, list) else str(flag_reasons)
                if reasons_str and feedback_text:
                    review_fb = f"REVIEW FEEDBACK: [{reasons_str}] — {feedback_text}"
                elif reasons_str:
                    review_fb = f"REVIEW FEEDBACK: [{reasons_str}]"
                elif feedback_text:
                    review_fb = f"REVIEW FEEDBACK: {feedback_text}"
                else:
                    continue

                gate["review_feedback"] = review_fb

            atomic_write_json(self.path, self.data)

    def increment_api_usage(self, service: str, count: int = 1) -> None:
        """Thread-safe increment of api_usage counter.

        Args:
            service: Key in api_usage dict (e.g. "kling_video", "elevenlabs_chars").
            count: Amount to increment by (default 1).
        """
        with self._lock:
            self.data["api_usage"][service] = (
                self.data["api_usage"].get(service, 0) + count
            )

    def record_phase_timing(
        self,
        phase_name: str,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> None:
        """Record start/end ISO timestamps for a production phase.

        Args:
            phase_name: e.g. "voiceover", "video_generation".
            started_at: ISO timestamp for phase start.
            completed_at: ISO timestamp for phase completion.
        """
        with self._lock:
            if phase_name not in self.data["phase_timing"]:
                self.data["phase_timing"][phase_name] = {}
            if started_at is not None:
                self.data["phase_timing"][phase_name]["started_at"] = started_at
            if completed_at is not None:
                self.data["phase_timing"][phase_name]["completed_at"] = completed_at

    def increment_retry(self, scene_id: str, retry_type: str = "video") -> None:
        """Increment retry count for a scene and retry type.

        Args:
            scene_id: e.g. "scene_01".
            retry_type: e.g. "video", "audio".
        """
        with self._lock:
            if scene_id not in self.data["retry_counts"]:
                self.data["retry_counts"][scene_id] = {}
            current = self.data["retry_counts"][scene_id].get(retry_type, 0)
            self.data["retry_counts"][scene_id][retry_type] = current + 1

    def update_post_production(self, **kwargs) -> None:
        """Update post_production fields atomically.

        Args:
            **kwargs: Fields to update in the post_production section.
                Valid keys: status, caption_preset, platform_target,
                edl_path, edl_version, final_uploaded.
        """
        with self._lock:
            pp = self.data.setdefault("post_production", {})
            for key, value in kwargs.items():
                pp[key] = value
            atomic_write_json(self.path, self.data)

    def record_preview_version(
        self, version: int, path: str, render_duration_s: float
    ) -> None:
        """Record a preview render version.

        Args:
            version: Preview version number.
            path: Path to the rendered preview file.
            render_duration_s: Time taken to render in seconds.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            pp = self.data.setdefault("post_production", {})
            pp.setdefault("preview_versions", []).append({
                "version": version,
                "path": path,
                "rendered_at": now,
                "render_duration_s": render_duration_s,
            })
            atomic_write_json(self.path, self.data)

    def record_feedback(
        self, version: int, feedback: str, changes_applied: list[str]
    ) -> None:
        """Record feedback for a preview version.

        Args:
            version: Preview version this feedback applies to.
            feedback: Natural language feedback text.
            changes_applied: List of changes that were applied.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            pp = self.data.setdefault("post_production", {})
            pp.setdefault("feedback_log", []).append({
                "version": version,
                "feedback": feedback,
                "changes_applied": changes_applied,
                "timestamp": now,
            })
            atomic_write_json(self.path, self.data)

    def mark_final_approved(
        self, version: int, path: str, render_duration_s: float
    ) -> None:
        """Mark a version as the final approved render.

        Args:
            version: Final approved version number.
            path: Path to the final rendered file.
            render_duration_s: Time taken to render in seconds.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            pp = self.data.setdefault("post_production", {})
            pp["final_version"] = {
                "version": version,
                "path": path,
                "rendered_at": now,
                "render_duration_s": render_duration_s,
            }
            pp["final_approved"] = True
            pp["status"] = "complete"
            atomic_write_json(self.path, self.data)

    def save(self) -> None:
        """Save manifest to disk atomically."""
        with self._lock:
            atomic_write_json(self.path, self.data)
