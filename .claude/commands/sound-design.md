---
name: sound-design
description: SFX layer mapping for VSL scenes — assigns real sound effect files with exact volume, loop, and timing settings for every scene. Use when creating audio design maps, assigning SFX to video clips, building audio_design.json for Remotion, or when the user mentions sound design, SFX, audio layers, or ambient sound for video scenes. Invoke for Phase 12 of VSL production (parallel with Kling video generation). This phase is OPTIONAL if audio is embedded during Kling generation via proxy API — ask the user which path they're using.
---

# Sound Design — VSL Wrapper

Load the Sound Design skill from your configured skills directory before doing anything else.

> **Note:** Skills are not bundled in this repo. Configure your own skills directory and place the `sound-design/SKILL.md` skill there. See the project README for details.

Execute the complete sound design workflow exactly as the skill describes.

## VSL Project Context

**Pipeline position**: Phase 12 — runs in PARALLEL with Kling video generation (Phase 11). Only needs the master script and scene prompts — does NOT need actual video clips.

**This phase is OPTIONAL** — two production paths exist:

**Path A (default — post-generation SFX)**: Run this skill → produce `audio_design.json` → apply SFX to clips via `apply_sfx_to_clips.py` and Remotion's `SceneWithAudio` component.

**Path B (future — embedded audio)**: Audio embedded during Kling generation via proxy API + Kling subscription. If this path is active, skip Phase 12 entirely — clips already contain audio.

Before starting, ask the user: "Is audio being handled via Kling proxy API (embedded during generation), or should I create an SFX design map for post-processing?"

**Inputs** (Path A only):
- `vsl/{project_slug}/copy/master_script.md` — atmosphere and sound palette per scene
- `vsl/{project_slug}/prompts/scene_prompts_final.md` — conceptual audio descriptions

**Output** (Path A only):
- `vsl/{project_slug}/manifest/audio_design.json` — SFX layers per scene, ready for `audioDesigns.ts`

## Hard Rules (from the skill)

- Maximum 3 audio layers per scene
- Volume hierarchy: Primary (0.6-0.8) > Ambient (0.3-0.5) > Detail (0.15-0.3)
- Only use APPROVED sounds from the SFX library in `remotion-audio.md`
- BANNED sounds: breathing_calm, breathing_restless, marching, war_drums, armor_clank, low_drone, electric_zap, crystal_ring, lab_glass, fluorescent_buzz, water_drip, water_splash_bath

## If Invoked Standalone (outside orchestrator)

Ask: "Which VSL project are we working on?" to get the `project_slug`, then confirm which audio path is being used before proceeding.

## How Skills Are Accessed in This Project

Skills are loaded from a configurable skills directory. Set your skills path in your project configuration or environment. Each skill is a self-contained folder with a `SKILL.md` file.
