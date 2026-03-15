---
name: cinematic-director
description: Professional Hollywood-level scene design for AI video/image generation. Use when designing scenes from a VSL master script, writing image or video generation prompts, applying the Epic Scale Doctrine, or when the user asks to "direct" scenes, run cinematic design, or prepare prompts before image/video generation. Always invoke for Phase 4 of VSL production (after Master Script approval, before Scene Breakdown). Invoke any time someone asks you to write generation prompts without explicitly running this first — cinematic quality depends on it.
---

# Cinematic Director — VSL Wrapper

Load the Cinematic Director skill from your configured skills directory before doing anything else.

> **Note:** Skills are not bundled in this repo. Configure your own skills directory and place the `cinematic-director/SKILL.md` skill there. See the project README for details.

Execute the complete cinematic-director workflow exactly as the skill describes.

## VSL Project Context

**Pipeline position**: Phase 4 — runs after Master Script is approved (Phase 3), before Scene Breakdown writes generation prompts (Phase 6).

**Trigger condition**: The Director's master script exists at `vsl/{project_slug}/copy/master_script.md` and is marked approved in the workflow manifest.

**Inputs**:
- `vsl/{project_slug}/copy/master_script.md` — the BINDING source of truth

**Output**:
- Scene design specifications fed directly into `vsl/{project_slug}/prompts/scene_prompts.md`

## If Invoked Standalone (outside orchestrator)

Ask: "Which VSL project are we working on?" to get the `project_slug`, then read:
- `vsl/{project_slug}/copy/master_script.md`

Apply the full cinematic-director framework to every scene in the script.

## How Skills Are Accessed in This Project

Skills are loaded from a configurable skills directory. Set your skills path in your project configuration or environment. Each skill is a self-contained folder with a `SKILL.md` file.
