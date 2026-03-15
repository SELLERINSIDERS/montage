# VSL Production Pipeline — Quick Reference

## Overview

The VSL (Video Sales Letter) production pipeline runs 15 phases from product intake to final delivery.
Managed by the orchestrator skill (`/project:vsl-production`). Uses Ralph Loop checkpoints for crash recovery.

**Master reference**: `docs/VSL_PRODUCTION_WORKFLOW.md` — full technical details
**Orchestrator**: `.claude/commands/vsl-production.md` — executable skill with agent prompts

## Pipeline Phases

| # | Phase | Type | Key Output |
|---|-------|------|------------|
| 1 | Intake | Interactive | `brief.md` |
| 2 | Research | Agent | `research.md` |
| 3 | Scriptwriting | Agent Team (3) | `script.md` (compliance pass + panel 90+ + humanizer) |
| 4 | Master Script | Agent (Director) | `master_script.md` — BINDING source of truth |
| 5 | Camera Plan | Agent (Cinematographer) | `camera_plan.json` |
| 6 | Scene Breakdown | Agent | `scene_prompts.md` |
| — | VALIDATION GATE | Orchestrator | Alignment check |
| — | SCRIPT APPROVAL GATE | Human Review | User approves script package |
| 7 | Voiceover | Agent (parallel w/8) | `voiceover.mp3` + `whisper.json` |
| 8 | Image Gen V1 | Agent (parallel w/7) | Draft images |
| — | HUMAN GATE | User Review | Image feedback |
| 9 | Image Revisions | Agent | 2K final images |
| 10 | Video Re-alignment | Agent | `scene_prompts_final.md` |
| 11 | Kling Video Gen | Agent (parallel w/12) | Video clips |
| 12 | Sound Design | Agent (parallel w/11) | `audio_design.json` |
| — | VOICEOVER GATE | Human Review | Approve voiceover |
| 13 | Post-Production | Agent (Remotion) | Assembled draft |
| 14 | Final Edit | Agent | Final MP4 |
| 15 | Final Gate | Agent (Quality Audit) | PASS / FAIL |

## Quality Gates

1. **Compliance Check** (Phase 3) — FDA/FTC/Meta rules. MUST PASS before panel. Includes Personal Attributes trap + Net Impression Doctrine.
2. **Expert Panel** (Phase 3) — 10-expert scoring. MUST reach 90+. Max 3 iterations.
3. **Humanizer Pass** (Phase 3) — Removes AI patterns. Mandatory after panel 90+.
4. **Validation Gate** (after Phase 6) — Orchestrator checks scene prompts align with master script.
5. **Script Approval Gate** (after Validation) — Human reviews full script package before voiceover.
6. **Image Review Gate** (after Phase 8) — Human reviews V1 images, provides feedback.
7. **Voiceover Gate** (after Phase 7) — Human listens and approves voiceover.
8. **Final Gate** (Phase 15) — 3-pass audit: source-of-truth, functional, completeness.

## Film Crew Model

| Role | Phase | Skill File |
|------|-------|-----------|
| Director | Phase 4 | `.claude/skills/cinematic-director/SKILL.md` |
| Cinematographer | Phase 5 | `.claude/skills/cinematographer/SKILL.md` |
| Scene Writer | Phase 6 | `.claude/commands/video-prompting-guide.md` |
| Voiceover | Phase 7 | `.claude/skills/elevenlabs/SKILL.md` |
| Image Dept | Phase 8-9 | `.claude/commands/nanobanana.md` |
| Video Dept | Phase 11 | `docs/knowledge/video/kling.md` |
| Sound Dept | Phase 12 | `.claude/skills/sound-design/SKILL.md` |
| Editor | Phase 13-14 | `.claude/commands/remotion-audio.md` |

## Parallel Execution

- **Phase 7 + 8**: Voiceover and image gen run simultaneously
- **Phase 11 + 12**: Kling video gen and sound design run simultaneously
- **Phase 11 (optional)**: Split into 2-3 batch agents for 60+ scene projects

## Context Management

The orchestrator is a THIN DISPATCHER — it never reads skill files, workflow docs, or large content.
Every phase is executed by a spawned agent with a fresh context window.
The orchestrator reads ONLY: manifest, handoffs, checkpoints (all small JSON files).

## Project Folder

All files for a VSL project live in `vsl/{project_slug}/` with subdirectories:
`state/`, `copy/`, `prompts/`, `images/v1/`, `images/final/`, `audio/`, `video/clips/`, `video/clips_with_audio/`, `video/final/`, `manifest/`

## Pipeline Lessons

### Phase 9 (Image Revisions)
- **2K generation**: `MAX_WORKERS = 1` mandatory — concurrent 2K deadlocks. Budget 3-4 min/image
- **Multi-version selection**: User may pick images across V5/V6 — track exact source prompt per image. Use EXACT original prompt for 2K, not a rewrite
- **Pose failures**: Add explicit in-prompt negatives with body geometry. May need 2-3 regen attempts
- **Director 8-Step rewrite (V6) ≈ V5**: Minimal visual difference on well-crafted prompts. Skip rewrite for prompts that already work

### Phase 11 (Kling Video)
- **Motion intent**: "foot tapping impatiently" → looks like enjoying music. Always state WHY motion happens (emotion) not just WHAT moves
- **Rate limits by batch size**: Under 50 clips → 3 workers fine. 70+ → switch to 1 worker. 11 clips = ~10 min
- **Resume capability**: `batch_generate_concurrent.py` skips clips > 500KB. Safe to stop and restart

### Phase 12 (Sound Design) + SFX Overlay
- **ffmpeg overlay** (`scripts/apply_sfx_to_clips.py`): Apply SFX directly to Kling clips. Much faster than Remotion for review iterations
- **Re-apply workflow** (`scripts/reapply_sfx_single.py`): Strip audio (`-an`) then overlay new layers. For changing SFX on clips that already have baked-in audio
- **Review cycle**: Generate Kling clips → apply SFX → user reviews → change SFX → re-apply single clip. No Remotion needed until final assembly

## Crash Recovery

Uses Ralph Loop v3.2 checkpoint protocol from shared-company-brain.
- Every phase writes checkpoints to `vsl/{project_slug}/state/`
- Handoff JSON files pass data between phases
- Session fencing prevents zombie writes
- On crash: re-invoke `/project:vsl-production` → reads manifest → resumes from last incomplete step
