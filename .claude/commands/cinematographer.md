---
name: cinematographer
description: Camera plan extraction and validation for Kling AI video generation. Use when extracting camera directions from a VSL master script, producing camera_plan.json, validating camera movement feasibility, or auditing camera distribution. Always invoke for Phase 5 of VSL production (after Master Script, before Scene Breakdown). If anyone asks about camera planning, camera motions for Kling, or which camera type to use for a scene — invoke this skill.
---

# Cinematographer — VSL Wrapper

Load the Cinematographer skill from your configured skills directory before doing anything else.

> **Note:** Skills are not bundled in this repo. Configure your own skills directory and place the `cinematographer/SKILL.md` skill there. See the project README for details.

Execute the complete cinematographer workflow exactly as the skill describes.

## VSL Project Context

**Pipeline position**: Phase 5 — runs after Master Script is complete (Phase 4), before Scene Breakdown (Phase 6). The Cinematographer reads the Director's script and produces the camera plan that ALL downstream agents consume. No agent downstream invents camera movements — they all read `camera_plan.json`.

**Inputs**:
- `vsl/{project_slug}/copy/master_script.md` — the BINDING source of truth
- `vsl/{project_slug}/state/handoff-master-script.json` — confirms audit_status = PASS

**Output**:
- `vsl/{project_slug}/prompts/camera_plan.json` — validated camera plan for every scene

**Distribution targets** (enforced by this skill):
- static ≤ 25%
- No 3+ consecutive identical camera types
- At least 4 different camera types in any 10-scene window

## If Invoked Standalone (outside orchestrator)

Ask: "Which VSL project are we working on?" to get the `project_slug`, then read:
- `vsl/{project_slug}/copy/master_script.md`

Produce `vsl/{project_slug}/prompts/camera_plan.json` following the full cinematographer protocol.

## How Skills Are Accessed in This Project

Skills are loaded from a configurable skills directory. Set your skills path in your project configuration or environment. Each skill is a self-contained folder with a `SKILL.md` file.
