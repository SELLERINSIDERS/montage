"""Human review gate infrastructure for the VSL production pipeline.

Provides 6 gate types: compliance, script review, image 1K review,
realignment, video clip review, and final video review. Each gate
tracks decisions in the workflow manifest and enforces the
approve/flag/defer workflow.

Gates prevent wasted API calls by catching issues early (1K before 2K,
compliance before generation). They also create a feedback loop that
feeds the lessons-learned log.

Usage:
    runner = GateRunner("state/manifest.json")
    result = runner.run_compliance_gate("vsl")
    if result["blocked"]:
        print("Compliance must pass first")
    else:
        runner.run_script_review_gate()
"""

import json
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from scripts.workflow_manifest import (
    WorkflowManifest,
    SceneStatus,
    GateDecision,
)


class GateType(Enum):
    """All gate types in the production pipeline."""

    COMPLIANCE = "compliance"
    SCRIPT_REVIEW = "script_review"
    IMAGE_1K = "image_1k"
    REALIGNMENT = "realignment"
    VIDEO_CLIP = "video_clip"
    FINAL_VIDEO = "final_video"


# Default path for lessons-learned log
_DEFAULT_LESSONS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "lessons_learned.json",
)


class GateRunner:
    """Orchestrates human review gates across the production pipeline.

    Each gate reads/writes state via WorkflowManifest. Compliance gate
    blocks ALL downstream work for ALL formats. Quick-approve mode
    skips optional gates but never compliance.

    Attributes:
        manifest: The WorkflowManifest instance.
        quick_approve: Whether optional gates auto-approve.
        lessons_learned_path: Path to the lessons-learned JSON log.
    """

    # Gates that ALWAYS run, even in quick_approve mode
    ALWAYS_GATES = {GateType.COMPLIANCE}

    # Gates that can be skipped in quick_approve mode
    OPTIONAL_GATES = {GateType.IMAGE_1K, GateType.VIDEO_CLIP, GateType.FINAL_VIDEO}

    def __init__(
        self,
        manifest_path: str,
        quick_approve: bool = False,
        lessons_learned_path: Optional[str] = None,
    ) -> None:
        """Load manifest and configure gate runner.

        Args:
            manifest_path: Path to the workflow manifest JSON.
            quick_approve: If True, optional gates return auto-approved.
            lessons_learned_path: Override path for lessons_learned.json.
        """
        self.manifest = WorkflowManifest(manifest_path)
        self.quick_approve = quick_approve
        self.lessons_learned_path = lessons_learned_path or _DEFAULT_LESSONS_PATH

    def _now_iso(self) -> str:
        """Return current UTC time as ISO string."""
        return datetime.now(timezone.utc).isoformat()

    def _record_global_gate_timing(self, gate_type: str, event: str) -> None:
        """Record timing for a global (non-scene) gate."""
        if "gate_timing" not in self.manifest.data:
            self.manifest.data["gate_timing"] = {}
        if gate_type not in self.manifest.data["gate_timing"]:
            self.manifest.data["gate_timing"][gate_type] = {}
        self.manifest.data["gate_timing"][gate_type][event] = self._now_iso()
        self.manifest.save()

    def run_compliance_gate(self, format: str) -> dict:
        """Check compliance status. Blocks ALL downstream if not passed.

        Args:
            format: Production format ("vsl", "ad", "ugc").

        Returns:
            Dict with blocked (bool) and reason (str if blocked).
        """
        self._record_global_gate_timing("compliance", "checked")

        compliance = self.manifest.data.get("gates", {}).get("compliance", {})
        status = compliance.get("status")

        if status == "passed":
            return {"blocked": False, "format": format}

        return {
            "blocked": True,
            "reason": "Compliance must pass before generation",
            "format": format,
        }

    def run_script_review_gate(self) -> dict:
        """Return formatted summary for human script review.

        Returns:
            Dict with scene_count, format, compliance_status, and file_paths.
        """
        self._record_global_gate_timing("script_review", "presented")

        data = self.manifest.data
        compliance = data.get("gates", {}).get("compliance", {})

        return {
            "scene_count": len(data["scenes"]),
            "format": data["format"],
            "compliance_status": compliance.get("status", "not_run"),
            "file_paths": {
                "script": f"{data['slug']}/copy/script.md",
                "master_script": f"{data['slug']}/copy/master_script.md",
                "compliance_report": f"{data['slug']}/copy/compliance_report.md",
            },
        }

    def run_image_review_gate(self, scene_ids: list[str]) -> dict:
        """Categorize scenes by their image 1K review status.

        Args:
            scene_ids: List of scene IDs to check.

        Returns:
            Dict with needs_review, approved, flagged, deferred,
            manual_intervention lists, and auto_approved flag.
        """
        if self.quick_approve and GateType.IMAGE_1K in self.OPTIONAL_GATES:
            return {
                "auto_approved": True,
                "needs_review": [],
                "approved": scene_ids,
                "flagged": [],
                "deferred": [],
                "manual_intervention": [],
            }

        self._record_global_gate_timing("image_1k", "presented")

        result = {
            "auto_approved": False,
            "needs_review": [],
            "approved": [],
            "flagged": [],
            "deferred": [],
            "manual_intervention": [],
        }

        for scene_id in scene_ids:
            scene = self.manifest._find_scene(scene_id)
            gate = scene["gates"].get("image_1k", {})
            status = gate.get("status")

            if status == SceneStatus.APPROVED.value:
                result["approved"].append(scene_id)
            elif status == SceneStatus.FLAGGED.value:
                result["flagged"].append(scene_id)
            elif status == SceneStatus.DEFERRED.value:
                result["deferred"].append(scene_id)
            elif status == SceneStatus.NEEDS_MANUAL_INTERVENTION.value:
                result["manual_intervention"].append(scene_id)
            else:
                result["needs_review"].append(scene_id)

        return result

    def promote_to_2k(self, scene_ids: list[str]) -> dict:
        """Promote approved 1K scenes to 2K generation.

        Args:
            scene_ids: List of scene IDs to promote.

        Returns:
            Dict with promoted list.

        Raises:
            ValueError: If any scene is not approved at 1K.
        """
        promoted = []

        for scene_id in scene_ids:
            scene = self.manifest._find_scene(scene_id)
            gate = scene["gates"].get("image_1k", {})
            status = gate.get("status")

            if status != SceneStatus.APPROVED.value:
                raise ValueError(
                    f"Scene {scene_id} not approved at 1K (status: {status})"
                )

            # Mark 2K as pending
            if "image_2k" not in scene["gates"]:
                scene["gates"]["image_2k"] = {
                    "status": "pending",
                    "feedback": None,
                    "attempts": 0,
                }
            else:
                scene["gates"]["image_2k"]["status"] = "pending"

            promoted.append(scene_id)

        self.manifest.save()
        return {"promoted": promoted}

    def run_realignment_gate(self) -> dict:
        """Return diff summary of video prompt changes after image approval.

        Returns:
            Dict with changed_scenes list.
        """
        self._record_global_gate_timing("realignment", "presented")

        changed = []
        for scene in self.manifest.data["scenes"]:
            # Check if scene has approved images that might need prompt realignment
            gate = scene["gates"].get("image_1k", {})
            if gate.get("status") == SceneStatus.APPROVED.value:
                changed.append({
                    "scene_id": scene["scene_id"],
                    "original_prompt": None,
                    "revised_prompt": None,
                })

        return {"changed_scenes": changed}

    def run_clip_review_gate(self, scene_ids: list[str]) -> dict:
        """Categorize clips by review status.

        Args:
            scene_ids: List of scene IDs to review.

        Returns:
            Dict with needs_review, approved, flagged, deferred lists.
        """
        if self.quick_approve and GateType.VIDEO_CLIP in self.OPTIONAL_GATES:
            return {
                "auto_approved": True,
                "needs_review": [],
                "approved": scene_ids,
                "flagged": [],
                "deferred": [],
            }

        self._record_global_gate_timing("video_clip", "presented")

        result = {
            "needs_review": [],
            "approved": [],
            "flagged": [],
            "deferred": [],
        }

        for scene_id in scene_ids:
            scene = self.manifest._find_scene(scene_id)
            gate = scene["gates"].get("video_clip", {})
            status = gate.get("status")

            if status == SceneStatus.APPROVED.value:
                result["approved"].append(scene_id)
            elif status == SceneStatus.FLAGGED.value:
                result["flagged"].append(scene_id)
            elif status == SceneStatus.DEFERRED.value:
                result["deferred"].append(scene_id)
            else:
                result["needs_review"].append(scene_id)

        return result

    def run_final_review_gate(self) -> dict:
        """Return full production summary with scene-level re-edit options.

        Returns:
            Dict with scenes list, total_duration, and re_edit_options.
        """
        if self.quick_approve and GateType.FINAL_VIDEO in self.OPTIONAL_GATES:
            return {
                "auto_approved": True,
                "scenes": [s["scene_id"] for s in self.manifest.data["scenes"]],
                "re_edit_options": [],
            }

        self._record_global_gate_timing("final_video", "presented")

        scenes = []
        for scene in self.manifest.data["scenes"]:
            scenes.append({
                "scene_id": scene["scene_id"],
                "gates": scene["gates"],
            })

        return {
            "scenes": scenes,
            "re_edit_options": [],
        }

    def record_feedback(
        self,
        scene_id: str,
        gate_type: GateType,
        decision: GateDecision,
        feedback_text: Optional[str] = None,
    ) -> None:
        """Record a gate decision and optionally log to lessons-learned.

        If decision is APPROVED and there was prior flagged feedback,
        logs the successful revision pattern to lessons_learned.json.

        Args:
            scene_id: Scene identifier.
            gate_type: Which gate this decision applies to.
            decision: APPROVED, FLAGGED, or DEFERRED.
            feedback_text: Optional human feedback text.
        """
        gate_key = gate_type.value

        # Check for prior feedback before recording new decision
        scene = self.manifest._find_scene(scene_id)
        prior_gate = scene["gates"].get(gate_key, {})
        had_prior_feedback = (
            prior_gate.get("status") == SceneStatus.FLAGGED.value
            and prior_gate.get("feedback") is not None
        )
        prior_feedback_text = prior_gate.get("feedback")

        # Record the decision via manifest
        self.manifest.record_gate_decision(
            scene_id, gate_key, decision.value, feedback=feedback_text
        )

        # Log to lessons-learned if this is a successful revision
        if (
            decision == GateDecision.APPROVED
            and had_prior_feedback
            and prior_feedback_text
        ):
            self._log_lesson(
                scene_id=scene_id,
                gate_type=gate_key,
                original_issue=prior_feedback_text,
                resolution=feedback_text,
            )

    def _log_lesson(
        self,
        scene_id: str,
        gate_type: str,
        original_issue: str,
        resolution: Optional[str],
    ) -> None:
        """Append a successful revision pattern to lessons_learned.json."""
        entry = {
            "scene_id": scene_id,
            "scene_type": gate_type,
            "original_issue": original_issue,
            "prompt_change": resolution,
            "outcome": "success",
            "timestamp": self._now_iso(),
        }

        try:
            with open(self.lessons_learned_path, "r") as f:
                lessons = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            lessons = []

        lessons.append(entry)

        with open(self.lessons_learned_path, "w") as f:
            json.dump(lessons, f, indent=2)

    def get_gate_summary(self) -> dict:
        """Aggregate all gate statuses across scenes.

        Returns:
            Dict keyed by gate_type, each with counts of approved,
            flagged, deferred, pending, needs_manual_intervention.
        """
        summary: dict[str, dict[str, int]] = {}

        for scene in self.manifest.data["scenes"]:
            for gate_key, gate_data in scene["gates"].items():
                if gate_key not in summary:
                    summary[gate_key] = {
                        "approved": 0,
                        "flagged": 0,
                        "deferred": 0,
                        "pending": 0,
                        "needs_manual_intervention": 0,
                    }

                status = gate_data.get("status", "pending")
                if status in summary[gate_key]:
                    summary[gate_key][status] += 1
                else:
                    summary[gate_key]["pending"] += 1

        return summary
