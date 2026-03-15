"""Pure dispatcher orchestrator for multi-format video production.

Context Budget Constraint (REL-05):
    The orchestrator reads ONLY manifest state, checkpoint paths, and phase status.
    It NEVER reads skill files, scripts, images, or large outputs.
    All skill files are read by subagents in their own fresh context windows.
    All handoffs between phases happen through files in the state/ folder.

This design keeps the main orchestration agent lean enough to survive context
compaction in long productions (80+ scenes). Checkpoints enable resume from
any point without losing progress.

Usage:
    orch = Orchestrator("vsl/my-project", "vsl")
    state = orch.resume()
    # ... run phase via subagent ...
    next_info = orch.advance_phase("intake", "Completed intake analysis")
"""

import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from scripts.checkpoint import CheckpointManager
from scripts.gate_runner import GateRunner
from scripts.manifest_sync import sync_phase
from scripts.validate_skills import validate_skills
from scripts.workflow_manifest import WorkflowManifest


class GateError(Exception):
    """Raised when a quality gate blocks the pipeline.

    Attributes:
        gate_type: Which gate blocked (e.g., 'compliance', 'image_1k').
        reason: Human-readable explanation of why the gate blocked.
        resume_command: Command to resume after fixing the issue.
    """

    def __init__(self, gate_type: str, reason: str, resume_command: str):
        self.gate_type = gate_type
        self.reason = reason
        self.resume_command = resume_command
        super().__init__(f"[{gate_type}] BLOCKED: {reason}\nResume: {resume_command}")


class Orchestrator:
    """Pure dispatcher: reads manifest, spawns agents, validates outputs, presents gates.

    Context Budget Constraint:
    - Orchestrator reads ONLY: manifest, checkpoint paths, phase status
    - NEVER reads: skill files, scripts, images, large outputs
    - All skill files read by subagents in their own fresh context
    - All handoffs through files in state/ folder
    """

    PRODUCTION_PHASES = [
        "intake",
        "research",
        "scriptwriting",
        "compliance",
        "scene_design",
        "camera_plan",
        "image_gen_1k",
        "image_review",
        "image_gen_2k",
        "video_prompts",
        "realignment",
        "voiceover",
        "video_gen",
        "clip_review",
        "final_stitch",
        "final_review",
    ]

    # Stale heartbeat threshold
    _HEARTBEAT_STALE_MINUTES = 30
    _MAX_AUTO_RESTARTS = 2

    # Gate-to-phase mapping: gates run BEFORE the consuming phase.
    # Key = phase that requires a gate check before it can start.
    # Value = (gate_name, callable(gate_runner, orchestrator) -> result).
    GATE_MAP: dict[str, tuple[str, "callable"]] = {
        # GATE-01: Compliance must pass before any visual work
        "scene_design": (
            "compliance",
            lambda gr, orch: gr.run_compliance_gate(orch.format_type),
        ),
        # Script review before camera planning (informational)
        "camera_plan": (
            "script_review",
            lambda gr, orch: gr.run_script_review_gate(),
        ),
        # GATE-02: 1K image review before 2K generation
        "image_gen_2k": (
            "image_1k",
            lambda gr, orch: gr.run_image_review_gate(
                [s["scene_id"] for s in orch.manifest.data["scenes"]]
            ),
        ),
        # GATE-03: Realignment before video prompts (informational)
        "video_prompts": (
            "realignment",
            lambda gr, orch: gr.run_realignment_gate(),
        ),
        # GATE-04: Clip review before final stitching
        "final_stitch": (
            "clip_review",
            lambda gr, orch: gr.run_clip_review_gate(
                [s["scene_id"] for s in orch.manifest.data["scenes"]]
            ),
        ),
        # GATE-05: Final review at end of pipeline
        "final_review": (
            "final_video",
            lambda gr, orch: gr.run_final_review_gate(),
        ),
    }

    # Scene-level gates that check needs_review / manual_intervention
    _SCENE_LEVEL_GATES = {"image_1k", "clip_review"}

    # Non-blocking informational gates (log only, never raise GateError)
    _INFORMATIONAL_GATES = {"script_review", "realignment"}

    def __init__(
        self,
        project_dir: str,
        format_type: str,
        quick_approve: bool = False,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            project_dir: Path to the project folder (e.g., vsl/my-project/).
            format_type: Production type ("vsl", "ad", "ugc").
            quick_approve: If True, auto-approve gates without human review.

        Raises:
            RuntimeError: If required skills are missing.
        """
        self.project_dir = project_dir
        self.format_type = format_type
        self.quick_approve = quick_approve
        self.state_dir = os.path.join(project_dir, "state")
        self.phases_completed: list[str] = []

        # Initialize checkpoint manager
        self.checkpoint_mgr = CheckpointManager(self.state_dir)

        # Load manifest if it exists
        manifest_path = os.path.join(self.state_dir, "manifest.json")
        self.manifest: Optional[WorkflowManifest] = None
        self.gate_runner: Optional[GateRunner] = None
        if os.path.exists(manifest_path):
            self.manifest = WorkflowManifest(manifest_path)
            self.gate_runner = GateRunner(
                manifest_path,
                quick_approve=quick_approve,
                lessons_learned_path=os.path.join(
                    project_dir, "config", "lessons_learned.json"
                ),
            )

        # Fail fast if skills missing
        validate_skills()

    def resume(self) -> dict:
        """Resume from last checkpoint or beginning.

        Also syncs Ralph Loop workflow-manifest.json to catch up on any
        phases that completed but weren't recorded (e.g., after a crash).

        Returns:
            Dict with current_phase and optional next_phase_prompt.
        """
        # Sync all phases on resume to catch missed updates
        try:
            from scripts.manifest_sync import sync_all_phases
            sync_all_phases(self.project_dir)
        except (FileNotFoundError, ImportError):
            pass

        state = self.checkpoint_mgr.get_resume_state()
        if state is not None:
            return {
                "current_phase": state["current_phase"],
                "next_phase_prompt": state["next_phase_prompt"],
            }
        return {
            "current_phase": self.PRODUCTION_PHASES[0],
            "next_phase_prompt": None,
        }

    def advance_phase(self, completed_phase: str, output_summary: str) -> dict:
        """Record phase completion, write checkpoint if due, return next phase info.

        Args:
            completed_phase: Name of the phase that just finished.
            output_summary: Brief summary of what the phase produced.

        Returns:
            Dict with next_phase, next_phase_prompt, and checkpoint_written flag.
        """
        self.phases_completed.append(completed_phase)

        # Sync Ralph Loop workflow-manifest.json so phase shows "completed"
        try:
            sync_phase(self.project_dir, completed_phase)
        except FileNotFoundError:
            pass  # No Ralph Loop manifest — using v2 manifest only

        # Push phase completion to Supabase dashboard
        try:
            from scripts.dashboard_sync import DashboardSync

            dashboard_sync = DashboardSync()
            if dashboard_sync.enabled:
                manifest_path = os.path.join(self.state_dir, "manifest.json")
                if os.path.exists(manifest_path):
                    dashboard_sync.push_manifest(manifest_path)
                    production_id = DashboardSync._production_id(
                        self.format_type,
                        os.path.basename(self.project_dir),
                    )
                    dashboard_sync.push_generation_event(
                        production_id,
                        None,
                        "phase_completed",
                        {
                            "phase": completed_phase,
                            "summary": output_summary,
                        },
                    )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "DashboardSync push failed in advance_phase: %s", exc
            )

        checkpoint_written = False
        next_phase_prompt = None

        # Determine next phase
        try:
            idx = self.PRODUCTION_PHASES.index(completed_phase)
            next_phase = (
                self.PRODUCTION_PHASES[idx + 1]
                if idx + 1 < len(self.PRODUCTION_PHASES)
                else None
            )
        except ValueError:
            next_phase = None

        # Check gate before proceeding to next phase
        if next_phase and self.gate_runner:
            self._check_gate(next_phase)

        # Build next-phase prompt if there is a next phase
        if next_phase:
            prompt_info = self.build_subagent_prompt(next_phase)
            next_phase_prompt = (
                f"Execute phase '{next_phase}' for {self.format_type} project "
                f"at {self.project_dir}. "
                f"Read skill at {prompt_info['skill_path']}. "
                f"Input files: {prompt_info['input_files']}. "
                f"Write output to {prompt_info['output_path']}."
            )

        # Write checkpoint if due
        if self.checkpoint_mgr.should_checkpoint(len(self.phases_completed)):
            manifest_path = (
                self.manifest.path if self.manifest else "state/manifest.json"
            )
            self.checkpoint_mgr.write_checkpoint(
                phases_completed=self.phases_completed,
                current_phase=next_phase or "complete",
                manifest_path=manifest_path,
                accumulated_decisions=[],
                next_phase_prompt=next_phase_prompt or "",
                skill_paths=self.get_skill_paths(),
                gate_summary=self._build_gate_summary(),
            )
            checkpoint_written = True

        return {
            "next_phase": next_phase,
            "next_phase_prompt": next_phase_prompt,
            "checkpoint_written": checkpoint_written,
        }

    def build_subagent_prompt(self, phase: str) -> dict:
        """Build prompt for subagent execution of a phase.

        Context Budget Constraint: Returns file paths and instructions only.
        Subagent reads files in its own context. NEVER include file contents.

        Args:
            phase: The phase name to build a prompt for.

        Returns:
            Dict with phase, skill_path, input_files, output_path,
            format_type, and character_anchor_path. Paths only -- not contents.
        """
        skill_map = self.get_skill_paths()

        # Map phases to their primary skill
        phase_skill_map = {
            "scene_design": "cinematic_director",
            "camera_plan": "cinematographer",
            "compliance": "compliance_checker",
            "scriptwriting": "expert_panel",
        }

        skill_key = phase_skill_map.get(phase)
        skill_path = skill_map.get(skill_key, "") if skill_key else ""

        return {
            "phase": phase,
            "skill_path": skill_path,
            "input_files": [os.path.join(self.state_dir, "manifest.json")],
            "output_path": os.path.join(self.state_dir, f"{phase}_output.json"),
            "format_type": self.format_type,
            "character_anchor_path": os.path.join(
                self.project_dir, "prompts", "character_anchor.md"
            ),
        }

    def get_phase_status(self) -> dict:
        """Read manifest for current phase status.

        Returns:
            Dict with phases_completed, current_phase, gate_states,
            and stalled_agents list.
        """
        current = (
            self.PRODUCTION_PHASES[len(self.phases_completed)]
            if len(self.phases_completed) < len(self.PRODUCTION_PHASES)
            else "complete"
        )

        return {
            "phases_completed": list(self.phases_completed),
            "current_phase": current,
            "gate_states": self._build_gate_summary(),
            "stalled_agents": self.check_agent_health(),
        }

    def check_agent_health(self) -> list[dict]:
        """Check heartbeat timestamps for stalled agents.

        Reads manifest heartbeat fields and flags any agent with heartbeat
        more than 30 minutes stale. Max 2 auto-restarts per agent before
        escalating to user.

        Returns:
            List of stalled agent dicts with phase, last_heartbeat,
            minutes_stale, restarts, and action recommendation.
        """
        if self.manifest is None:
            return []

        stalled = []
        now = datetime.now(timezone.utc)

        # Check for heartbeat data in manifest
        heartbeats = self.manifest.data.get("heartbeats", {})
        for phase, info in heartbeats.items():
            last_beat = info.get("last_heartbeat")
            restarts = info.get("restarts", 0)
            if last_beat:
                beat_time = datetime.fromisoformat(last_beat)
                delta = now - beat_time
                minutes_stale = delta.total_seconds() / 60

                if minutes_stale > self._HEARTBEAT_STALE_MINUTES:
                    action = (
                        "auto_restart"
                        if restarts < self._MAX_AUTO_RESTARTS
                        else "escalate_to_user"
                    )
                    stalled.append({
                        "phase": phase,
                        "last_heartbeat": last_beat,
                        "minutes_stale": round(minutes_stale, 1),
                        "restarts": restarts,
                        "action": action,
                    })

        return stalled

    def get_skill_paths(self) -> dict[str, str]:
        """Return paths to all required skills. Paths only -- not contents.

        Context Budget Constraint: This method returns string paths.
        It does NOT open or read any files.
        """
        skills_dir = os.environ.get("SKILLS_DIR", "skills")
        return {
            "cinematic_director": f"{skills_dir}/cinematic-director/SKILL.md",
            "cinematographer": f"{skills_dir}/cinematographer/SKILL.md",
            "compliance_checker": f"{skills_dir}/compliance-checker/SKILL.md",
            "expert_panel": f"{skills_dir}/meta-ad-copy/SKILL.md",
        }

    def _check_gate(self, next_phase: str) -> None:
        """Check if a quality gate blocks entry to next_phase.

        Looks up next_phase in GATE_MAP. If a gate exists, runs it and
        evaluates the result. Writes a checkpoint before raising GateError
        to ensure no work is lost.

        Args:
            next_phase: The phase about to start.

        Raises:
            GateError: If the gate blocks the pipeline.
        """
        if next_phase not in self.GATE_MAP:
            return
        if self.gate_runner is None:
            return

        gate_name, gate_fn = self.GATE_MAP[next_phase]
        result = gate_fn(self.gate_runner, self)
        self._log_gate_result(gate_name, result)

        # Informational gates: log only, never block
        if gate_name in self._INFORMATIONAL_GATES:
            return

        # Final_video gate: NEVER auto-approve, even in quick_approve mode
        # This is the last checkpoint before delivery and requires human sign-off
        if gate_name == "final_video":
            if result.get("auto_approved"):
                self._write_pre_gate_checkpoint(next_phase)
                raise GateError(
                    gate_type="final_video",
                    reason="Final review requires human evaluation even in quick_approve mode",
                    resume_command=f"orch.resume() after completing final review",
                )
            # Non-auto-approved final review: check scene data
            scenes = result.get("scenes", [])
            if scenes:
                self._write_pre_gate_checkpoint(next_phase)
                raise GateError(
                    gate_type="final_video",
                    reason=f"Final review pending for {len(scenes)} scenes",
                    resume_command=f"orch.resume() after completing final review",
                )
            return

        # Global gates (compliance): check blocked flag
        if "blocked" in result:
            if result["blocked"]:
                self._write_pre_gate_checkpoint(next_phase)
                raise GateError(
                    gate_type=gate_name,
                    reason=result.get("reason", "Gate blocked"),
                    resume_command=f"orch.resume() after fixing {gate_name}",
                )
            return

        # Scene-level gates (image_1k, clip_review): check categories
        if result.get("auto_approved"):
            return  # quick_approve auto-approved this optional gate

        needs_review = result.get("needs_review", [])
        manual_intervention = result.get("manual_intervention", [])

        if manual_intervention:
            self._write_pre_gate_checkpoint(next_phase)
            raise GateError(
                gate_type=gate_name,
                reason=(
                    f"{len(manual_intervention)} scene(s) need manual intervention: "
                    f"{', '.join(manual_intervention[:5])}"
                ),
                resume_command=f"orch.resume() after resolving manual intervention for {gate_name}",
            )

        if needs_review:
            self._write_pre_gate_checkpoint(next_phase)
            raise GateError(
                gate_type=gate_name,
                reason=(
                    f"{len(needs_review)} scene(s) need review: "
                    f"{', '.join(needs_review[:5])}"
                ),
                resume_command=f"orch.resume() after reviewing {gate_name}",
            )

        # Flagged but no needs_review: log warning, continue (batch-first pattern)

    def _write_pre_gate_checkpoint(self, next_phase: str) -> None:
        """Write a checkpoint before raising GateError so no work is lost."""
        manifest_path = (
            self.manifest.path if self.manifest else "state/manifest.json"
        )
        self.checkpoint_mgr.write_checkpoint(
            phases_completed=self.phases_completed,
            current_phase=next_phase,
            manifest_path=manifest_path,
            accumulated_decisions=[],
            next_phase_prompt="",
            skill_paths=self.get_skill_paths(),
            gate_summary=self._build_gate_summary(),
        )

    def _log_gate_result(self, gate_name: str, result: dict) -> None:
        """Log gate result with summary counts. Uses print(flush=True).

        Optimized for 80+ scene VSLs: summary-first, detail only for
        flagged and manual_intervention scenes.
        """
        if result.get("auto_approved"):
            print(f"[{gate_name}] Auto-approved (quick_approve mode)", flush=True)
            return

        if result.get("blocked"):
            reason = result.get("reason", "unknown")
            print(f"[{gate_name}] BLOCKED: {reason}", flush=True)
            return

        # Scene-level results: summary counts
        counts = []
        for category in ("approved", "flagged", "needs_review", "manual_intervention", "deferred"):
            items = result.get(category, [])
            if items:
                counts.append(f"{category}={len(items)}")

        if counts:
            print(f"[{gate_name}] {', '.join(counts)}", flush=True)

            # Detail for flagged and manual_intervention only
            for category in ("flagged", "manual_intervention"):
                items = result.get(category, [])
                if items:
                    print(f"  {category}: {', '.join(items)}", flush=True)
        else:
            # Non-scene gates (realignment, script_review)
            if "changed_scenes" in result:
                print(
                    f"[{gate_name}] {len(result['changed_scenes'])} scenes with changes",
                    flush=True,
                )
            elif "scene_count" in result:
                print(
                    f"[{gate_name}] {result['scene_count']} scenes, "
                    f"compliance: {result.get('compliance_status', 'unknown')}",
                    flush=True,
                )
            else:
                print(f"[{gate_name}] Gate checked", flush=True)

    def _build_gate_summary(self) -> dict:
        """Build gate summary from manifest for checkpoint persistence.

        Delegates to GateRunner.get_gate_summary() when available for
        richer aggregation (includes counts instead of lists).
        """
        if self.gate_runner is not None:
            return self.gate_runner.get_gate_summary()

        if self.manifest is None:
            return {}

        summary = {}
        for scene in self.manifest.data.get("scenes", []):
            for gate_type, gate_data in scene.get("gates", {}).items():
                if gate_type not in summary:
                    summary[gate_type] = {
                        "approved": [],
                        "flagged": [],
                        "deferred": [],
                    }
                status = gate_data.get("status")
                scene_id = scene["scene_id"]
                if status == "approved":
                    summary[gate_type]["approved"].append(scene_id)
                elif status == "flagged":
                    summary[gate_type]["flagged"].append(scene_id)
                elif status == "deferred":
                    summary[gate_type]["deferred"].append(scene_id)

        return summary
