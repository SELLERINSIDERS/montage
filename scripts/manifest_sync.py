"""Sync Ralph Loop workflow-manifest.json phase statuses from checkpoint/handoff files.

The vsl-production orchestrator skill uses workflow-manifest.json (Ralph Loop format)
to track phase-level status (pending/completed/skipped). This module ensures phase
statuses stay in sync with actual checkpoint and handoff file state on disk.

Problem solved: Previously, agents completed phases and wrote checkpoint/handoff
files, but workflow-manifest.json was never updated — leaving phases stuck as
"pending" even though all deliverables existed. On resume, the orchestrator would
try to re-run completed work.

Usage:
    # Sync a single phase after agent completion
    sync_phase("ads/my-project-v1", "scriptwriting")

    # Sync all phases (on resume or after crash recovery)
    report = sync_all_phases("ads/my-project-v1")

    # CLI usage
    python -m scripts.manifest_sync ads/my-project-v1
    python -m scripts.manifest_sync ads/my-project-v1 --phase scriptwriting
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from video.kling.manifest import atomic_write_json


# Map phase IDs to the files that prove completion.
# Each phase lists (checkpoint_path, handoff_path, deliverable_paths).
# A phase is "completed" if its handoff file exists and is valid JSON,
# OR if its primary deliverable exists.
PHASE_EVIDENCE = {
    "intake": {
        "checkpoint": "state/intake-checkpoint.json",
        "handoff": None,
        "deliverables": ["copy/brief.md"],
    },
    "research": {
        "checkpoint": "state/research-checkpoint.json",
        "handoff": "state/handoff-research.json",
        "deliverables": ["copy/research.md"],
    },
    "scriptwriting": {
        "checkpoint": "state/script-checkpoint.json",
        "handoff": "state/handoff-script.json",
        "deliverables": ["copy/script.md", "copy/script_narrated.md"],
    },
    "master-script": {
        "checkpoint": "state/master-script-checkpoint.json",
        "handoff": "state/handoff-master-script.json",
        "deliverables": ["copy/master_script.md"],
    },
    "camera-plan": {
        "checkpoint": "state/camera-plan-checkpoint.json",
        "handoff": None,
        "deliverables": ["prompts/camera_plan.json"],
    },
    "scene-breakdown": {
        "checkpoint": "state/scenes-checkpoint.json",
        "handoff": "state/handoff-scenes.json",
        "deliverables": ["prompts/scene_prompts.md"],
    },
    "voiceover": {
        "checkpoint": "state/voiceover-checkpoint.json",
        "handoff": "state/handoff-voiceover.json",
        "deliverables": ["audio/voiceover.mp3"],
    },
    "imagegen-v1": {
        "checkpoint": "state/imagegen-v1-checkpoint.json",
        "handoff": "state/handoff-images-v1.json",
        "deliverables": [],  # images checked via handoff
    },
    "imagegen-v2": {
        "checkpoint": "state/imagegen-v2-checkpoint.json",
        "handoff": "state/handoff-images-v2.json",
        "deliverables": [],
    },
    "video-realignment": {
        "checkpoint": "state/video-realign-checkpoint.json",
        "handoff": None,
        "deliverables": ["prompts/scene_prompts_final.md"],
    },
    "kling-video": {
        "checkpoint": "state/kling-checkpoint.json",
        "handoff": "state/handoff-kling.json",
        "deliverables": [],
    },
    "sound-design": {
        "checkpoint": "state/sound-design-checkpoint.json",
        "handoff": "state/handoff-sound-design.json",
        "deliverables": ["manifest/audio_design.json"],
    },
    "post-production": {
        "checkpoint": "state/postprod-checkpoint.json",
        "handoff": "state/handoff-postprod.json",
        "deliverables": [],
    },
    "final-edit": {
        "checkpoint": "state/final-edit-checkpoint.json",
        "handoff": "state/handoff-final-edit.json",
        "deliverables": [],
    },
    "final-gate": {
        "checkpoint": "state/final-gate-checkpoint.json",
        "handoff": None,
        "deliverables": ["copy/final-gate-report.md"],
    },
}


def _is_valid_json(path: str) -> bool:
    """Check if a file exists and contains valid JSON."""
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r") as f:
            json.load(f)
        return True
    except (json.JSONDecodeError, OSError):
        return False


def _check_phase_completed(project_root: str, phase_id: str) -> bool:
    """Determine if a phase is completed by checking evidence files.

    A phase is considered completed if:
    1. Its handoff file exists and is valid JSON, OR
    2. ALL of its deliverable files exist (non-empty)

    Args:
        project_root: Path to the project directory.
        phase_id: Phase identifier (e.g., "scriptwriting").

    Returns:
        True if the phase appears to be completed.
    """
    evidence = PHASE_EVIDENCE.get(phase_id)
    if evidence is None:
        return False

    # Check handoff file first (strongest signal)
    handoff = evidence["handoff"]
    if handoff:
        handoff_path = os.path.join(project_root, handoff)
        if _is_valid_json(handoff_path):
            return True

    # Check deliverables
    deliverables = evidence["deliverables"]
    if deliverables:
        all_exist = all(
            os.path.exists(os.path.join(project_root, d))
            and os.path.getsize(os.path.join(project_root, d)) > 0
            for d in deliverables
        )
        if all_exist:
            return True

    return False


def _load_manifest(project_root: str) -> tuple[dict, str]:
    """Load workflow-manifest.json from a project.

    Returns:
        Tuple of (manifest_data, manifest_path).

    Raises:
        FileNotFoundError: If workflow-manifest.json doesn't exist.
    """
    manifest_path = os.path.join(project_root, "state", "workflow-manifest.json")
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(
            f"No workflow-manifest.json found at {manifest_path}"
        )

    with open(manifest_path, "r") as f:
        data = json.load(f)

    return data, manifest_path


def sync_phase(project_root: str, phase_id: str) -> dict:
    """Sync a single phase's status in workflow-manifest.json.

    Checks if the phase is completed on disk and updates the manifest
    if the status was previously "pending" or "running".

    Args:
        project_root: Path to the project directory.
        phase_id: Phase identifier to sync.

    Returns:
        Dict with phase_id, old_status, new_status, and changed flag.
    """
    data, manifest_path = _load_manifest(project_root)

    result = {
        "phase_id": phase_id,
        "old_status": None,
        "new_status": None,
        "changed": False,
    }

    for phase in data.get("phases", []):
        if phase["id"] == phase_id:
            old_status = phase["status"]
            result["old_status"] = old_status

            # Only upgrade from pending/running → completed
            if old_status in ("pending", "running"):
                if _check_phase_completed(project_root, phase_id):
                    phase["status"] = "completed"
                    phase["active_session_id"] = None
                    data["last_progress_at"] = datetime.now(
                        timezone.utc
                    ).isoformat()
                    result["new_status"] = "completed"
                    result["changed"] = True
                    atomic_write_json(manifest_path, data)
                else:
                    result["new_status"] = old_status
            else:
                result["new_status"] = old_status

            break

    return result


def sync_all_phases(project_root: str) -> dict:
    """Sync all phase statuses in workflow-manifest.json.

    Scans every phase in the manifest. For phases marked "pending" or
    "running", checks if evidence files on disk indicate completion.
    Updates the manifest atomically with all changes at once.

    Args:
        project_root: Path to the project directory.

    Returns:
        Dict with total_phases, synced (list of changed phases),
        already_correct count, and skipped count.
    """
    data, manifest_path = _load_manifest(project_root)

    report = {
        "total_phases": 0,
        "synced": [],
        "already_correct": 0,
        "skipped": 0,
    }

    changed = False

    for phase in data.get("phases", []):
        report["total_phases"] += 1
        phase_id = phase["id"]
        status = phase["status"]

        # Skip already-completed or explicitly-skipped phases
        if status in ("completed", "skipped"):
            report["already_correct"] += 1
            continue

        # Check if this phase is actually done
        if status in ("pending", "running"):
            if _check_phase_completed(project_root, phase_id):
                old = status
                phase["status"] = "completed"
                phase["active_session_id"] = None
                report["synced"].append({
                    "phase_id": phase_id,
                    "old_status": old,
                    "new_status": "completed",
                })
                changed = True
            else:
                report["skipped"] += 1

    if changed:
        data["last_progress_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(manifest_path, data)

    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync workflow-manifest.json phase statuses from disk evidence"
    )
    parser.add_argument(
        "project_root",
        help="Path to project directory (e.g., ads/my-project-v1)",
    )
    parser.add_argument(
        "--phase",
        help="Sync a single phase only (e.g., scriptwriting)",
        default=None,
    )
    args = parser.parse_args()

    if args.phase:
        result = sync_phase(args.project_root, args.phase)
        if result["changed"]:
            print(
                f"Synced {result['phase_id']}: "
                f"{result['old_status']} → {result['new_status']}"
            )
        else:
            print(
                f"Phase {result['phase_id']} already "
                f"{result['new_status'] or 'unknown'}"
            )
    else:
        report = sync_all_phases(args.project_root)
        print(f"Phases: {report['total_phases']}")
        print(f"Already correct: {report['already_correct']}")
        print(f"Still pending: {report['skipped']}")
        if report["synced"]:
            print(f"Synced {len(report['synced'])} phases:")
            for s in report["synced"]:
                print(f"  {s['phase_id']}: {s['old_status']} → {s['new_status']}")
        else:
            print("No changes needed.")
