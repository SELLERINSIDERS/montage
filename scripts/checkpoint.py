"""Checkpoint system for compaction-safe pipeline resume.

Writes checkpoint files every 3 completed phases with full state needed
to resume from that point. Each checkpoint includes a pre-written prompt
for the next phase so that on context compaction, the pipeline resumes
without any reconstruction overhead.

Uses atomic_write_json from video.kling.manifest for crash safety.

Usage:
    mgr = CheckpointManager("vsl/nightcap/state")
    if mgr.should_checkpoint(len(phases_completed)):
        mgr.write_checkpoint(
            phases_completed=phases_completed,
            current_phase="image_gen_2k",
            manifest_path="state/manifest.json",
            accumulated_decisions=["Used X for Y"],
            next_phase_prompt="Run image_gen_2k with ...",
            skill_paths={"cinematic_director": "skills/cinematic-director/SKILL.md"},
            gate_summary={...},
        )

    # On resume after compaction
    state = mgr.get_resume_state()
    if state:
        prompt = state["next_phase_prompt"]
"""

import glob
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from video.kling.manifest import atomic_write_json


@dataclass
class Checkpoint:
    """Immutable snapshot of pipeline state at a checkpoint boundary."""

    checkpoint_number: int
    written_at: str
    phases_completed: list[str]
    current_phase: str
    manifest_path: str
    accumulated_decisions: list[str]
    next_phase_prompt: str
    skill_paths: dict[str, str]
    gate_summary: dict


class CheckpointManager:
    """Manages checkpoint files in a project's state/ directory.

    Checkpoints are written every 3 completed phases. Each checkpoint
    contains the full state needed to resume the pipeline, including
    a pre-written prompt for the next phase.

    Args:
        state_dir: Path to the state directory (e.g., vsl/nightcap/state/).
    """

    def __init__(self, state_dir: str) -> None:
        self.state_dir = state_dir

    def should_checkpoint(self, phases_completed_count: int) -> bool:
        """Return True when a checkpoint should be written.

        Checkpoints occur every 3 phases: at 3, 6, 9, etc.
        """
        return phases_completed_count > 0 and phases_completed_count % 3 == 0

    def write_checkpoint(
        self,
        phases_completed: list[str],
        current_phase: str,
        manifest_path: str,
        accumulated_decisions: list[str],
        next_phase_prompt: str,
        skill_paths: dict[str, str],
        gate_summary: dict,
    ) -> str:
        """Write a checkpoint file with full pipeline state.

        Args:
            phases_completed: List of completed phase names.
            current_phase: The phase to resume from.
            manifest_path: Path to the workflow manifest.
            accumulated_decisions: Decisions made so far.
            next_phase_prompt: Pre-written prompt for resuming the next phase.
            skill_paths: Map of skill name to SKILL.md path.
            gate_summary: Gate state (approvals, flagged, feedback, timestamps).

        Returns:
            Path to the written checkpoint file.
        """
        checkpoint_number = len(phases_completed) // 3
        data = {
            "checkpoint_number": checkpoint_number,
            "written_at": datetime.now(timezone.utc).isoformat(),
            "phases_completed": phases_completed,
            "current_phase": current_phase,
            "manifest_path": manifest_path,
            "accumulated_decisions": accumulated_decisions,
            "next_phase_prompt": next_phase_prompt,
            "skill_paths": skill_paths,
            "gate_summary": gate_summary,
        }
        filename = f"checkpoint-phase-{checkpoint_number}.json"
        path = os.path.join(self.state_dir, filename)
        atomic_write_json(path, data)
        return path

    def load_latest(self) -> Optional[Checkpoint]:
        """Load the most recent checkpoint from the state directory.

        Returns:
            Checkpoint object, or None if no checkpoints exist.
        """
        pattern = os.path.join(self.state_dir, "checkpoint-phase-*.json")
        files = glob.glob(pattern)
        if not files:
            return None

        # Sort by checkpoint number extracted from filename
        def _number(path):
            base = os.path.basename(path)
            # checkpoint-phase-{N}.json
            return int(base.replace("checkpoint-phase-", "").replace(".json", ""))

        files.sort(key=_number)
        latest_path = files[-1]

        with open(latest_path, "r") as f:
            data = json.load(f)

        return Checkpoint(
            checkpoint_number=data["checkpoint_number"],
            written_at=data["written_at"],
            phases_completed=data["phases_completed"],
            current_phase=data["current_phase"],
            manifest_path=data["manifest_path"],
            accumulated_decisions=data["accumulated_decisions"],
            next_phase_prompt=data["next_phase_prompt"],
            skill_paths=data["skill_paths"],
            gate_summary=data["gate_summary"],
        )

    def get_resume_state(self) -> Optional[dict]:
        """Get the minimal state needed to resume from the latest checkpoint.

        Returns:
            Dict with current_phase, next_phase_prompt, manifest_path,
            gate_summary, or None if no checkpoints exist.
        """
        checkpoint = self.load_latest()
        if checkpoint is None:
            return None

        return {
            "current_phase": checkpoint.current_phase,
            "next_phase_prompt": checkpoint.next_phase_prompt,
            "manifest_path": checkpoint.manifest_path,
            "gate_summary": checkpoint.gate_summary,
        }
