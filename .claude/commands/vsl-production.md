---
name: vsl-production
description: Video Production Orchestrator — full pipeline from intake to final video. Handles VSLs (3–6 min), short ads (15–60s), and UGC clips (15–30s). Invoke when the user wants to START any new video production, RESUME an interrupted production, or RECOVER from a mid-pipeline crash (image gen, Kling, voiceover). Trigger on: "start a VSL", "make a short ad", "new Amazon video", "kick off the pipeline", "resume the [product] production", "pick up where we left off", "crashed during [phase]", "we stopped at phase N". Do NOT trigger for single-task requests like writing the script, compliance checking copy, regenerating one scene, or applying SFX — those are individual phase tasks handled by dedicated skills.
---

# VSL Production — Automated Pipeline Orchestrator

You are the VSL Production Orchestrator. You manage the full pipeline from idea to first draft images, using Ralph Loop checkpoints for crash recovery and agent teams for parallel work.

**Master reference**: `docs/VSL_PRODUCTION_WORKFLOW.md` — contains all technical details, scripts, and specifications.

---

## How This Works

This skill runs a multi-phase production pipeline. Each phase writes a Ralph Loop checkpoint to disk so work survives crashes and context exhaustion. The workflow pauses at human gates for user input/approval.

```
PHASE 1:  INTAKE ............ Interactive — gather product info, angle, references
PHASE 2:  RESEARCH .......... Agent — analyze reference VSL + audience research
PHASE 3:  SCRIPTWRITING ..... Agent team — write → compliance → expert panel (90+) → humanizer
PHASE 4:  MASTER SCRIPT ..... Agent (Director) — creates BINDING source of truth
PHASE 5:  CAMERA PLAN ....... Agent (Cinematographer) — validates camera directions
PHASE 6:  SCENE BREAKDOWN ... Agent — image/video/audio prompts (implements master script)
  ── VALIDATION GATE ── ..... Alignment check: prompts vs master script
  ── SCRIPT APPROVAL GATE ── Human reviews script + master script + scenes
PHASE 7:  VOICEOVER ......... Agent — ElevenLabs generation + Whisper transcription
PHASE 8:  IMAGE GEN V1 ...... Agent — low-quality draft images (parallel with Phase 7)
  ── HUMAN GATE ── .......... User reviews V1 images, provides feedback
PHASE 9:  IMAGE REVISIONS ... Agent — apply feedback + final 2K render
PHASE 10: VIDEO RE-ALIGNMENT  Agent — update video prompts to match ACTUAL final images
PHASE 11: KLING VIDEO GEN ... Agent — batch video generation from images (parallel with Phase 12)
PHASE 12: SOUND DESIGN ...... Agent — SFX layer assignments per scene (parallel with Phase 11)
  ── VOICEOVER GATE ── ...... User listens and approves voiceover
PHASE 13: POST-PRODUCTION ... Agent — Remotion assembly (clips + voiceover + SFX + captions)
PHASE 14: FINAL EDIT ........ Agent — subtitle styling, jump cuts, export
PHASE 15: FINAL GATE ........ Agent — 3-pass quality audit before delivery
```

---

## Context Management — MANDATORY

You are a THIN DISPATCHER. Your context window is precious. Follow these rules:

### What YOU do (orchestrator):
- Read manifest → determine next phase
- Read previous handoff JSON → extract inputs for next phase
- Spawn agent(s) with the phase prompt template
- Wait for agent completion
- Read output handoff JSON → validate
- Run gate checks (small inline validations)
- Present human gates to user
- Move to next phase

### What you NEVER do:
- Read skill files (agents read their own skills in their fresh context)
- Read the workflow doc (agents reference it if needed)
- Read scripts, research docs, images, or large files
- Process or analyze content inline
- Run compliance checks, panel reviews, or any heavy work

### Parallel Agent Opportunities:
- Phase 7 + 8: Spawn voiceover and image gen agents simultaneously
- Phase 11 + 12: Spawn Kling video gen and sound design agents simultaneously
- Phase 11: Optionally split into 2-3 batch agents for large scene counts (60+ scenes)

### Agent Prompt Size Budget:
Each agent prompt template should be under 200 lines. The agent reads its own skill files
in its fresh context. The orchestrator passes ONLY:
- Phase-specific instructions
- Paths to skills the agent must read
- Paths to input handoff/checkpoint files
- Path to write output handoff/checkpoint

---

## Working Directory — Single Project Folder

**Every VSL project gets ONE folder** with all files inside it. Nothing scatters across `docs/`, `images/`, `video/` etc. This keeps projects self-contained and easy to find.

```
vsl/{project_slug}/
│
├── state/                          — Ralph Loop orchestration
│   ├── workflow-manifest.json      — Ralph Loop manifest (phases + status)
│   ├── intake-checkpoint.json      — Phase 1 checkpoint
│   ├── research-checkpoint.json    — Phase 2 checkpoint
│   ├── script-checkpoint.json      — Phase 3 checkpoint
│   ├── master-script-checkpoint.json — Phase 4 checkpoint
│   ├── camera-plan-checkpoint.json — Phase 5 checkpoint
│   ├── scenes-checkpoint.json      — Phase 6 checkpoint
│   ├── voiceover-checkpoint.json   — Phase 7 checkpoint
│   ├── imagegen-v1-checkpoint.json — Phase 8 checkpoint
│   ├── imagegen-v2-checkpoint.json — Phase 9 checkpoint
│   ├── video-realign-checkpoint.json — Phase 10 checkpoint
│   ├── kling-checkpoint.json       — Phase 11 checkpoint
│   ├── sound-design-checkpoint.json — Phase 12 checkpoint
│   ├── postprod-checkpoint.json    — Phase 13 checkpoint
│   ├── final-edit-checkpoint.json  — Phase 14 checkpoint
│   ├── final-gate-checkpoint.json  — Phase 15 checkpoint
│   ├── handoff-research.json       — Phase 2 → 3 handoff
│   ├── handoff-script.json         — Phase 3 → 4 handoff
│   ├── handoff-master-script.json  — Phase 4 → 5 handoff
│   ├── handoff-scenes.json         — Phase 6 → 7/8 handoff
│   ├── handoff-voiceover.json      — Phase 7 → 13 handoff
│   ├── handoff-images-v1.json      — Phase 8 → 9 handoff (includes user feedback)
│   ├── handoff-kling.json          — Phase 11 → 13 handoff
│   ├── handoff-sound-design.json   — Phase 12 → 13 handoff
│   ├── handoff-postprod.json       — Phase 13 → 14 handoff
│   ├── handoff-final-edit.json     — Phase 14 → 15 handoff
│   └── events.log                  — Verbose logs
│
├── copy/                           — Scripts & written content
│   ├── brief.md                    — Product brief (Phase 1 output)
│   ├── research.md                 — Research document (Phase 2 output)
│   ├── script.md                   — Approved VSL script
│   ├── script_narrated.md          — Narrated script with ElevenLabs audio tags
│   ├── master_script.md            — Director's BINDING source of truth (Phase 4)
│   ├── compliance-report.md        — Compliance check results
│   └── panel-report.md             — Expert panel scores & feedback
│
├── prompts/                        — Generation prompts
│   ├── camera_plan.json            — Cinematographer's validated camera plan (Phase 5)
│   ├── scene_prompts.md            — Scene-by-scene image + video + audio prompts
│   ├── scene_prompts_v2.md         — Revised prompts after V1 feedback
│   └── scene_prompts_final.md      — Video prompts re-aligned to actual final images (Phase 10)
│
├── images/                         — Generated images
│   ├── v1/                         — V1 low-quality drafts (for review)
│   └── final/                      — Final 2K production images
│
├── audio/                          — Voiceover & transcription
│   ├── voiceover.mp3               — ElevenLabs voiceover
│   └── whisper.json                — Word-level timestamps (Remotion Caption[])
│
├── video/                          — Kling clips & rendered output
│   ├── clips/                      — Raw Kling I2V clips
│   ├── clips_with_audio/           — Clips with SFX applied
│   └── final/                      — Final rendered VSL MP4
│
└── manifest/                       — Kling & Remotion manifests
    ├── kling_manifest.json         — Kling batch generation manifest
    ├── vsl_manifest.json           — Remotion scene manifest (from Whisper)
    └── audio_design.json           — SFX layer assignments per scene
```

### Initialization

When Phase 1 starts, create the full folder structure:

```bash
mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}
```

### Resume / Fresh Session (Session Continuity)

All state lives on disk. If you lose context or start a new session:
1. Run `/project:vsl-production`
2. Orchestrator scans `vsl/` for existing projects
3. Reads `vsl/{project_slug}/state/workflow-manifest.json`
4. Identifies last incomplete phase → reads that checkpoint → resumes from last incomplete step
5. Reads `next_phase_skills` from the last completed checkpoint to know which skills to load
6. Validate directory structure exists (idempotent — safe to run every time):
   mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}
7. No lost work.

**Checkpoint skill tracking**: Each phase's checkpoint includes a `next_phase_skills` field listing the REQUIRED SKILLS for the next phase. This way, a new session knows exactly which skills to load without reading the entire orchestrator spec. Example:

```json
{
  "task": "vsl-scriptwriting",
  "phase_status": "completed",
  "next_phase": "master-script",
  "next_phase_skills": [
    "cinematic-director skill (Section 13 — AUTHOR mode)",
    "screenwriting-helper skill"
  ]
}
```

### Path Convention

Throughout this skill, all file paths are relative to the project folder. For example:
- `brief.md` means `vsl/{project_slug}/copy/brief.md`
- `v1/` means `vsl/{project_slug}/images/v1/`
- `voiceover.mp3` means `vsl/{project_slug}/audio/voiceover.mp3`

Agents receive the absolute project root path and construct full paths from there.

---

## PHASE 1: INTAKE (Interactive)

**You run this directly — no agent needed.**

### Step 1.1 — Gather Information

Ask the user for the following. Use `AskUserQuestion` where choices exist, and free-form conversation for open-ended inputs.

**Required inputs:**
1. **Production type** — VSL (3–6 min full narrative) / Short Ad (15–60s) / UGC Clip (15–30s raw social)
2. **Product name** — What product is this for?
3. **Product description** — Key ingredients, benefits, positioning (or reference an existing product brief)
4. **Target audience** — Who is this for? (demographics, psychographics)
5. **Angle/concept** — Historical figure, cultural story, hook, or emotional theme. If unknown, say "I need research help" and Phase 2 (if active) will explore options.
6. **Reference production** — URL or file path to a reference to analyze. If none, we use the Fabula framework from `vsl/fabula/prompts/fabula_vsl_kling_framework.md`.
7. **Destination URL** — Where does this link to? (advertorial, PDP, landing page, Amazon listing)
8. **Duration target** — Approximate length (VSL default: ~3 min / Short Ad default: 30s / UGC default: 20s)
9. **Voice preference** — ElevenLabs voice (default: Laura, speed 1.2) — skip if UGC with no voiceover
10. **Format** — 9:16 vertical (default), 16:9 horizontal, 1:1 square

**Optional inputs:**
- Specific claims or facts to include
- Competitor positioning to reference
- Visual style preferences
- Compliance notes or restrictions

### Step 1.2 — Create Brief

Determine the project root based on production type:
- VSL → `vsl/{project_slug}/`
- Short Ad → `ads/{project_slug}/`
- UGC Clip → `ugc/{project_slug}/`

Write the brief to `{project_root}/copy/brief.md`:

```markdown
# Production Brief — {Product Name}

**Created**: {date}
**Production type**: {VSL / Short Ad / UGC Clip}
**Project slug**: {project_slug}
**Project root**: {type}/{project_slug}/
**Status**: Phase 1 Complete — Intake

## Product
- **Name**: {name}
- **Description**: {description}
- **Key ingredients/features**: {list}

## Target Audience
{audience description}

## Creative Angle
{angle/concept — historical figure, cultural story, or emotional theme}

## Reference
{reference production path or "Fabula framework (default)"}

## Destination
- **URL**: {url}
- **CTA**: {Learn More / Shop Now / etc.}

## Technical Specs
- **Production type**: {VSL / Short Ad / UGC Clip}
- **Duration**: {target}
- **Format**: {aspect ratio}
- **Voice**: {voice name, speed — or "None (UGC)"}
- **Resolution**: 1080x{1920/1080/1080}

## Notes
{any additional context, restrictions, compliance notes}
```

### Step 1.2b — Narrative Arc Sketch

After writing `brief.md`, write a lightweight narrative arc to `{project_root}/copy/arc_sketch.md`.

This is NOT a script — it's 6–8 bullets capturing the emotional journey from hook to CTA. It gives the user something concrete to react to before Phase 3 scriptwriting begins, and anchors Phase 2 research around a clear creative direction.

**Scale to production type**: VSL gets all 8 beats. Short Ad gets 4 (Hook → Problem → Solution → CTA). UGC gets 3 (Hook → Proof → CTA).

```markdown
# Narrative Arc Sketch — {Product Name}

**Angle**: {one-line hook premise}

## Emotional Journey

1. **Hook** — {The historical/cultural "in": what grabs attention in the first 5 seconds}
2. **Empathy** — {The audience pain moment: what they feel at night, no product mention yet}
3. **Credibility pivot** — {The science or history connection that makes this feel discovered, not sold}
4. **Problem agitation** — {Why this specific audience suffers from this specific gap}
5. **Solution reveal** — {Product + key ingredient, first mention}
6. **Proof beat** — {Mechanism, origin story, or social proof that makes the claim land}
7. **Benefit payoff** — {What life looks like after: sleep, energy, clarity, confidence}
8. **CTA** — {The offer framing: guarantee, ease, urgency}

**Key differentiator vs. other VSLs**: {one line on what makes this angle fresh}
**Compliance flag**: {any claims in the arc that need review before scripting}
```

This file feeds directly into the Phase 2 research agent brief (which studies whether the hook premise holds up historically/scientifically) and the Phase 3 scriptwriter (who expands each bullet into narration).

### Step 1.3 — Initialize Workflow

Determine `{project_root}` from production type (set once, use everywhere):
- VSL → `vsl/{project_slug}`
- Short Ad → `ads/{project_slug}`
- UGC Clip → `ugc/{project_slug}`

Create the project directory structure:
```bash
mkdir -p {project_root}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}
```

**Phase skip map** — set `"status": "skipped"` in the manifest for phases not applicable to this production type:

| Phase | VSL | Short Ad | UGC Clip |
|-------|-----|----------|----------|
| 1 Intake | active | active | active |
| 2 Research | active | **skipped** | **skipped** |
| 3 Scriptwriting | active | active | active |
| 4 Master Script | active | active | **skipped** |
| 5 Camera Plan | active | active | **skipped** |
| 6 Scene Breakdown | active | active | active |
| 7 Voiceover | active | active | **skipped** (usually) |
| 8 Image Gen V1 | active | active | active |
| 9 Image Revisions | active | **skipped** | **skipped** |
| 10 Video Re-alignment | active | active | active |
| 11 Kling Video | active | active | active |
| 12 Sound Design | active | active | active |
| 13 Post-Production | active | active | active |
| 14 Final Edit | active | active | active |
| 15 Final Gate | active | active | active |

Skipped phases are written to the manifest as `"status": "skipped"` — the orchestrator reads this and jumps over them automatically. No manual intervention needed on resume.

Create the Ralph Loop workflow manifest at `vsl/{project_slug}/state/workflow-manifest.json`:

```json
{
  "schema": "ralph-loop-v3.1",
  "workflow_id": "vsl-{project_slug}-{date}",
  "workflow_name": "VSL Production — {Product Name}",
  "created_at": "{ISO timestamp}",
  "status": "running",
  "workflow_timeout_hours": 24,
  "last_progress_at": null,
  "working_directory": "vsl/{project_slug}/state/",
  "phases": [
    {
      "id": "intake",
      "skill": "vsl-intake",
      "checkpoint_path": "vsl/{project_slug}/state/intake-checkpoint.json",
      "input_handoff": null,
      "output_handoff": "vsl/{project_slug}/copy/brief.md",
      "depends_on": [],
      "status": "completed",
      "active_session_id": null,
      "context_recoveries": 0,
      "max_context_recoveries": 3,
      "death_timeout_minutes": 10
    },
    {
      "id": "research",
      "phase_number": 2,
      "skill": "vsl-research",
      "checkpoint_path": "vsl/{project_slug}/state/research-checkpoint.json",
      "input_handoff": "vsl/{project_slug}/copy/brief.md",
      "output_handoff": "vsl/{project_slug}/state/handoff-research.json",
      "depends_on": ["intake"],
      "status": "pending",
      "active_session_id": null,
      "context_recoveries": 0,
      "max_context_recoveries": 3,
      "death_timeout_minutes": 15
    },
    {
      "id": "scriptwriting",
      "phase_number": 3,
      "skill": "vsl-scriptwriting",
      "checkpoint_path": "vsl/{project_slug}/state/script-checkpoint.json",
      "input_handoff": ["vsl/{project_slug}/copy/brief.md", "vsl/{project_slug}/state/handoff-research.json"],
      "output_handoff": "vsl/{project_slug}/state/handoff-script.json",
      "depends_on": ["research"],
      "status": "pending",
      "active_session_id": null,
      "context_recoveries": 0,
      "max_context_recoveries": 3,
      "death_timeout_minutes": 15
    },
    {
      "id": "master-script",
      "phase_number": 4,
      "skill": "vsl-master-script",
      "checkpoint_path": "vsl/{project_slug}/state/master-script-checkpoint.json",
      "input_handoff": ["vsl/{project_slug}/copy/brief.md", "vsl/{project_slug}/state/handoff-script.json", "vsl/{project_slug}/copy/script.md"],
      "output_handoff": "vsl/{project_slug}/state/handoff-master-script.json",
      "depends_on": ["scriptwriting"],
      "status": "pending",
      "active_session_id": null,
      "context_recoveries": 0,
      "max_context_recoveries": 3,
      "death_timeout_minutes": 20
    },
    {
      "id": "camera-plan",
      "phase_number": 5,
      "skill": "vsl-camera-plan",
      "checkpoint_path": "vsl/{project_slug}/state/camera-plan-checkpoint.json",
      "input_handoff": ["vsl/{project_slug}/copy/master_script.md", "vsl/{project_slug}/state/handoff-master-script.json"],
      "output_handoff": "vsl/{project_slug}/prompts/camera_plan.json",
      "depends_on": ["master-script"],
      "status": "pending",
      "active_session_id": null,
      "context_recoveries": 0,
      "max_context_recoveries": 3,
      "death_timeout_minutes": 15
    },
    {
      "id": "scene-breakdown",
      "phase_number": 6,
      "skill": "vsl-scene-breakdown",
      "checkpoint_path": "vsl/{project_slug}/state/scenes-checkpoint.json",
      "input_handoff": ["vsl/{project_slug}/copy/brief.md", "vsl/{project_slug}/state/handoff-script.json", "vsl/{project_slug}/copy/master_script.md", "vsl/{project_slug}/prompts/camera_plan.json"],
      "output_handoff": "vsl/{project_slug}/state/handoff-scenes.json",
      "depends_on": ["camera-plan"],
      "status": "pending",
      "active_session_id": null,
      "context_recoveries": 0,
      "max_context_recoveries": 3,
      "death_timeout_minutes": 15
    },
    {
      "id": "voiceover",
      "phase_number": 7,
      "skill": "vsl-voiceover",
      "checkpoint_path": "vsl/{project_slug}/state/voiceover-checkpoint.json",
      "input_handoff": ["vsl/{project_slug}/copy/brief.md", "vsl/{project_slug}/copy/script_narrated.md"],
      "output_handoff": "vsl/{project_slug}/state/handoff-voiceover.json",
      "depends_on": ["scene-breakdown"],
      "status": "pending",
      "active_session_id": null,
      "context_recoveries": 0,
      "max_context_recoveries": 3,
      "death_timeout_minutes": 10
    },
    {
      "id": "imagegen-v1",
      "phase_number": 8,
      "skill": "vsl-imagegen-v1",
      "checkpoint_path": "vsl/{project_slug}/state/imagegen-v1-checkpoint.json",
      "input_handoff": ["vsl/{project_slug}/copy/brief.md", "vsl/{project_slug}/state/handoff-scenes.json"],
      "output_handoff": "vsl/{project_slug}/state/handoff-images-v1.json",
      "depends_on": ["scene-breakdown"],
      "status": "pending",
      "active_session_id": null,
      "context_recoveries": 0,
      "max_context_recoveries": 3,
      "death_timeout_minutes": 15
    },
    {
      "id": "imagegen-v2",
      "phase_number": 9,
      "skill": "vsl-imagegen-v2",
      "checkpoint_path": "vsl/{project_slug}/state/imagegen-v2-checkpoint.json",
      "input_handoff": "vsl/{project_slug}/state/handoff-images-v1.json",
      "output_handoff": "vsl/{project_slug}/state/handoff-images-v2.json",
      "depends_on": ["imagegen-v1"],
      "status": "pending",
      "active_session_id": null,
      "context_recoveries": 0,
      "max_context_recoveries": 3,
      "death_timeout_minutes": 15
    },
    {
      "id": "video-realignment",
      "phase_number": 10,
      "skill": "vsl-video-realignment",
      "checkpoint_path": "vsl/{project_slug}/state/video-realign-checkpoint.json",
      "input_handoff": ["vsl/{project_slug}/state/handoff-images-v2.json", "vsl/{project_slug}/prompts/camera_plan.json", "vsl/{project_slug}/copy/master_script.md"],
      "output_handoff": "vsl/{project_slug}/prompts/scene_prompts_final.md",
      "depends_on": ["imagegen-v2"],
      "status": "pending",
      "active_session_id": null,
      "context_recoveries": 0,
      "max_context_recoveries": 3,
      "death_timeout_minutes": 15
    },
    {
      "id": "kling-video",
      "phase_number": 11,
      "skill": "vsl-kling-video",
      "checkpoint_path": "vsl/{project_slug}/state/kling-checkpoint.json",
      "input_handoff": ["vsl/{project_slug}/prompts/scene_prompts_final.md", "vsl/{project_slug}/prompts/camera_plan.json"],
      "output_handoff": "vsl/{project_slug}/state/handoff-kling.json",
      "depends_on": ["video-realignment"],
      "status": "pending",
      "active_session_id": null,
      "context_recoveries": 0,
      "max_context_recoveries": 3,
      "death_timeout_minutes": 60
    },
    {
      "id": "sound-design",
      "phase_number": 12,
      "skill": "vsl-sound-design",
      "checkpoint_path": "vsl/{project_slug}/state/sound-design-checkpoint.json",
      "input_handoff": ["vsl/{project_slug}/copy/master_script.md", "vsl/{project_slug}/prompts/scene_prompts_final.md"],
      "output_handoff": "vsl/{project_slug}/state/handoff-sound-design.json",
      "depends_on": ["video-realignment"],
      "status": "pending",
      "active_session_id": null,
      "context_recoveries": 0,
      "max_context_recoveries": 3,
      "death_timeout_minutes": 30
    },
    {
      "id": "post-production",
      "phase_number": 13,
      "skill": "vsl-post-production",
      "checkpoint_path": "vsl/{project_slug}/state/postprod-checkpoint.json",
      "input_handoff": ["vsl/{project_slug}/state/handoff-kling.json", "vsl/{project_slug}/state/handoff-sound-design.json", "vsl/{project_slug}/state/handoff-voiceover.json"],
      "output_handoff": "vsl/{project_slug}/state/handoff-postprod.json",
      "depends_on": ["kling-video", "sound-design", "voiceover"],
      "status": "pending",
      "active_session_id": null,
      "context_recoveries": 0,
      "max_context_recoveries": 3,
      "death_timeout_minutes": 45
    },
    {
      "id": "final-edit",
      "phase_number": 14,
      "skill": "vsl-final-edit",
      "checkpoint_path": "vsl/{project_slug}/state/final-edit-checkpoint.json",
      "input_handoff": "vsl/{project_slug}/state/handoff-postprod.json",
      "output_handoff": "vsl/{project_slug}/state/handoff-final-edit.json",
      "depends_on": ["post-production"],
      "status": "pending",
      "active_session_id": null,
      "context_recoveries": 0,
      "max_context_recoveries": 3,
      "death_timeout_minutes": 30
    },
    {
      "id": "final-gate",
      "phase_number": 15,
      "skill": "vsl-final-gate",
      "checkpoint_path": "vsl/{project_slug}/state/final-gate-checkpoint.json",
      "input_handoff": "vsl/{project_slug}/state/handoff-final-edit.json",
      "output_handoff": "vsl/{project_slug}/copy/final-gate-report.md",
      "depends_on": ["final-edit"],
      "status": "pending",
      "active_session_id": null,
      "context_recoveries": 0,
      "max_context_recoveries": 3,
      "death_timeout_minutes": 20
    }
  ]
}
```

### Step 1.4 — Write Intake Checkpoint (complete)

Write the intake checkpoint marking it complete, then proceed to Phase 2.

---

## PHASE 2: RESEARCH (Agent)

**Spawn a single `general-purpose` agent.**

### Agent Prompt Template:

```
You are a VSL research agent. Your job is to analyze a reference VSL and research the creative angle for a new VSL.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

REQUIRED SKILLS (read these before starting):
- Screenwriting Helper: Load the `screenwriting-helper` skill from your skills directory — story structure patterns for angle selection

Read the production brief: vsl/{project_slug}/copy/brief.md
Read the master workflow: docs/VSL_PRODUCTION_WORKFLOW.md (Phase 1 — Research & Analysis)

CHECKPOINT: vsl/{project_slug}/state/research-checkpoint.json
Follow Ralph Loop checkpoint protocol on every step (load the `ralph-loop` skill from your skills directory)

STEPS:
1. analyze_reference — If a reference VSL path/URL is provided, analyze it following the Fabula method (visual map, script analysis, audio-visual synthesis). If no reference, study the Fabula framework at docs/fabula_vsl_kling_framework.md and docs/fabula_vsl_script_analysis.md.
   VERIFICATION: Research file exists with 3 analysis sections (structure, pacing, sync patterns)

2. research_angle — Research the creative angle from the brief. Look for:
   - Historical/cultural connections to the product's core benefit
   - Verifiable facts (for compliance)
   - Visual opportunities (settings, costumes, objects)
   - The natural pivot from story → modern problem → product
   VERIFICATION: Angle section has at least 5 verifiable facts and 3 visual opportunities

3. research_audience — Search Reddit (r/Supplements, r/sleep, r/Nootropics, r/stress), Amazon reviews, health forums for:
   - EXACT language customers use to describe their problems
   - Emotional triggers, objections, what they've tried and why it failed
   - 4 distinct customer personas with real quotes
   VERIFICATION: 4 personas documented with at least 2 real quotes each

4. write_research_doc — Compile everything into vsl/{project_slug}/copy/research.md
   VERIFICATION: File exists at expected path with all 3 sections

5. write_handoff — Write handoff-research.json with:
   {
     "research_path": "vsl/{project_slug}/copy/research.md",
     "angle_summary": "{one paragraph}",
     "key_facts": ["{list of verifiable facts}"],
     "personas": ["{list of 4 personas with their core pain}"],
     "visual_opportunities": ["{list}"],
     "pivot_concept": "{the bridge from story to modern problem}"
   }
   VERIFICATION: handoff-research.json exists and is valid JSON
```

### Checkpoint Template (6 steps):

```json
{
  "task": "vsl-research",
  "owner_session_id": null,
  "started_at": null,
  "last_updated_at": null,
  "phase_status": "pending",
  "context_recovery_count": 0,
  "steps_completed": 0,
  "total_steps": 5,
  "step_order": ["analyze_reference", "research_angle", "research_audience", "write_research_doc", "write_handoff"],
  "steps": {
    "analyze_reference": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" },
    "research_angle": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" },
    "research_audience": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" },
    "write_research_doc": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" },
    "write_handoff": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" }
  }
}
```

---

## PHASE 3: SCRIPTWRITING (Agent Team)

**Spawn a 3-agent team.** This follows the same pattern as `/project:copy-ad-team` but adapted for VSL scripts.

### Team Structure:

```
TeamCreate: team_name="vsl-script-{project_slug}", description="VSL script creation"

Agent 1: scriptwriter (starts immediately)
Agent 2: compliance-checker (blocked by scriptwriter)
Agent 3: panel-reviewer (blocked by compliance-checker)
```

### Agent 1: scriptwriter

```
You are a VSL scriptwriter. Write a 3-minute Video Sales Letter script.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

REQUIRED SKILLS (read ALL of these before starting):
- Titan Copy: Load the `titan-copy` skill from your skills directory — Reptilian -> Limbic -> Neocortex persuasion framework
- Screenwriting Helper: Load the `screenwriting-helper` skill from your skills directory — narrative structure, beat sheets, emotional arc
- Fabula Framework: docs/fabula_vsl_script_analysis.md — proven VSL structure (acts, pacing, pivot)

Read these files:
- vsl/{project_slug}/copy/brief.md (product brief)
- vsl/{project_slug}/state/handoff-research.json (research handoff)
- vsl/{project_slug}/copy/research.md (full research)
- docs/VSL_PRODUCTION_WORKFLOW.md (Phase 2 — Scriptwriting section)

CHECKPOINT: vsl/{project_slug}/state/script-checkpoint.json (scriptwriter steps only)

Follow the Fabula VSL structure:
| Act       | % of Runtime | Purpose                          | Pacing         |
|-----------|-------------|----------------------------------|----------------|
| Hook      | 0-5%        | Stop the scroll. Figure intro    | 3.0s/scene     |
| Legend    | 5-26%       | Build admiration. Achievements   | 1.8-2.0s/scene |
| Pivot+Problem | 26-63%  | "But here's the part..." → escalation | 2.3-2.6s/scene |
| Solution  | 63-88%      | Product mechanism + proof         | 2.9-3.0s/scene |
| Close     | 88-100%     | Bookend + CTA                   | 3.0-3.1s/scene |

Apply Titan Protocol: Reptilian (agitate) → Limbic (emotionalize) → Neocortex (rationalize)
The Pivot sentence is the MOST IMPORTANT line. Problem section: 37% of runtime, NO relief.
Product name appears no earlier than 65% in.
~500 words, ~180 WPM, ~3 minutes.

STEPS:
1. write_script — Write the full VSL script to vsl/{project_slug}/copy/script.md
2. write_narrated — Write the narrated version with ElevenLabs audio tags to vsl/{project_slug}/copy/script_narrated.md
   Voice: use the voice specified in brief.md. Audio tags: [pause], [calm], [deliberate], [building intensity], [grave, serious], [long pause]. Max 6 pauses.

Output files when done. Then notify compliance-checker that script is ready.
```

### Agent 2: compliance-checker

```
You are the compliance checker. Verify the VSL script passes FDA/FTC/Meta rules.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

REQUIRED SKILLS (read ALL of these before starting):
- Compliance Checker: Load the `compliance-checker` skill from your skills directory
- Banned Claims: Load `compliance-checker/references/banned-claims.md` from your skills directory
- Approved Claims: Load `compliance-checker/references/approved-claims.md` from your skills directory
- Disclaimer Triggers: Load `compliance-checker/references/disclaimer-triggers.md` from your skills directory

Read the script: vsl/{project_slug}/copy/script.md

Run the 6-step compliance protocol:
1. Classify content type (VSL for Meta/Instagram)
2. Scan for banned claims (disease, drug, absolute, superiority)
3. Validate structure/function claims (must have asterisk + disclaimer)
4. Check disclaimer triggers
5. Check Personal Attributes trap (YOU + NEGATIVE STATE = rejection)
6. Apply Net Impression Doctrine

Output: PASS / PASS WITH WARNINGS / FAIL per section.
If FAIL: provide specific fixes. The scriptwriter must revise before panel review.
If PASS: notify panel-reviewer that script is ready.

Write compliance report to vsl/{project_slug}/copy/compliance-report.md
```

### Agent 3: panel-reviewer

```
You are the 10-Expert Panel reviewer. Score the VSL script.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

Read the expert panel system:
- Load the `meta-ad-copy` skill from your skills directory (Section: Expert Panel)

Read the script: vsl/{project_slug}/copy/script.md
Read the compliance report: vsl/{project_slug}/copy/compliance-report.md

Run the panel:
| # | Expert | Focus |
|---|--------|-------|
| 1 | Ogilvy | Headline power, benefit clarity |
| 2 | Schwartz | Awareness levels, desire channeling |
| 3 | Halbert | Hooks, emotional triggers |
| 4 | Hopkins | Specificity, proof elements |
| 5 | Sugarman | Psychological triggers, flow |
| 6 | Cialdini | Social proof, authority, persuasion |
| 7 | Wiebe | CRO, voice-of-customer |
| 8 | Belgray | Voice, personality, tone |
| 9 | Georgi | Health copy, compliance, hooks |
| 10 | Albuquerque | Big ideas, mechanisms, story arcs |

Each expert scores 1-100 with strengths and specific improvements.

If average < 90: implement ALL fixes, revise the script, re-run the panel. Loop until 90+.
ITERATION LIMIT: Maximum 3 panel review iterations. If the script has not reached 90+ after 3 rounds of revisions, STOP and report to the orchestrator with:
- Current score after 3 rounds
- What the panel is consistently flagging
- Whether the fundamental angle/approach needs rethinking
The orchestrator will present this to the user for a decision.

If average >= 90: approve and write handoff.

Write panel report to vsl/{project_slug}/copy/panel-report.md

After scoring 90+, run the HUMANIZER pass before writing handoff.

Load the `humanizer` skill from your skills directory.

Apply humanizer to the final approved script:
- Remove AI vocabulary (furthermore, moreover, delve, harness, landscape, journey)
- Remove inflated symbolism and purple prose
- Fix em dash overuse, rule-of-three patterns, robotic parallelism
- Ensure the script reads like a real person wrote it

After humanizing, run a QUICK compliance re-check on the humanized text:
- Scan for Personal Attributes trap (YOU + NEGATIVE STATE patterns)
- Scan for any banned claim words that may have been introduced
- Verify FDA disclaimers (asterisks) are still present on all structure/function claims
If the re-check finds issues, fix them in the humanized text before writing the handoff.

Write the humanized script back to vsl/{project_slug}/copy/script.md
Update the narrated version at vsl/{project_slug}/copy/script_narrated.md

THEN write handoff-script.json:
{
  "script_path": "vsl/{project_slug}/copy/script.md",
  "narrated_path": "vsl/{project_slug}/copy/script_narrated.md",
  "panel_score": {average},
  "compliance_status": "PASS",
  "humanizer_applied": true,
  "word_count": {N},
  "estimated_duration": "{M:SS}",
  "act_breakdown": { "hook": "{%}", "legend": "{%}", "problem": "{%}", "solution": "{%}", "close": "{%}" }
}

NEVER deliver without 90+ average AND humanizer pass.
```

### Phase 3 Checkpoint (4 steps — one per agent + humanizer):

```json
{
  "task": "vsl-scriptwriting",
  "total_steps": 4,
  "step_order": ["write_script", "compliance_check", "panel_review", "humanizer_pass"],
  "steps": {
    "write_script": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" },
    "compliance_check": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" },
    "panel_review": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" },
    "humanizer_pass": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" }
  }
}
```

---

## PHASE 4: MASTER SCRIPT (Agent — Director)

**Spawn a single `general-purpose` agent.** This is the Director creating the binding source of truth.

### Agent Prompt Template:

```
You are the DIRECTOR of a $100 million Hollywood production. Your job is to create the MASTER SCRIPT — the single binding source of truth that every department follows.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

BEFORE STARTING: Read handoff-script.json and verify humanizer_applied == true, compliance_status == "PASS", panel_score >= 90. If any is false, STOP immediately and report the failure.

REQUIRED SKILLS (read ALL of these before starting):
- Cinematic Director (AUTHOR mode): Load the `cinematic-director` skill from your skills directory — Read the ENTIRE skill, especially Section 13 (AUTHOR Mode) for the master script format, and Section 12 for camera motion psychology
- Screenwriting Helper: Load the `screenwriting-helper` skill from your skills directory — story craft informs scene emotional design (beat sheets, transitions, pacing)

Read these files:
- vsl/{project_slug}/copy/brief.md (product brief)
- vsl/{project_slug}/state/handoff-script.json (approved script handoff)
- vsl/{project_slug}/copy/script.md (the approved narrative script)
- vsl/{project_slug}/copy/script_narrated.md (narrated version)

CHECKPOINT: vsl/{project_slug}/state/master-script-checkpoint.json

STEPS:
1. break_scenes — Read the approved script and break it into scenes. Each narration line or natural phrase break = one scene. Sub-scenes (rapid montage cuts) get separate entries (14a, 14b, 14c, 14d).
   VERIFICATION: Total scenes documented, duration adds up to target

2. apply_8step — For EACH scene, apply the 8-Step Scene Design Protocol (Sections 1-8):
   - Step 1: Emotional Intent (one feeling word)
   - Step 2: Show Don't Tell — at EPIC SCALE (use Scale Hierarchy)
   - Step 3: Shot Selection (size + angle matched to psychology)
   - Step 4: Staging (2+ depth layers, subject position, leading lines)
   - Step 5: Lighting (NAMED technique — Rembrandt, chiaroscuro, etc.)
   - Step 6: Color (palette from Three-Palette System)
   - Step 7: Pacing Context (where in the breathing pattern)
   - Step 8: Prompt Construction (subject-first, 30-60 words)
   VERIFICATION: All 8 steps documented for every scene

3. write_camera — For EACH scene, specify Camera Direction (BINDING):
   - Camera Motion: one of [static / pan_left / pan_right / dolly_in / dolly_out / zoom_in / zoom_out / tilt_up / tilt_down / crane_up / crane_down / orbit_left / orbit_right]
   - Motion Reason: WHY this specific motion (what it reveals, follows, emphasizes)
   - Intensity: 0.0-1.0
   VERIFICATION: Every scene has camera motion + reason

4. write_exclusions — For EACH scene, specify "What is NOT in frame":
   - Think about what AI generators would ADD by default (hands, extra people, modern objects)
   - Explicitly exclude those elements
   VERIFICATION: Every scene has at least 1 exclusion

5. write_atmosphere — For EACH scene, specify:
   - Motion Elements (what physically moves — mandatory, every scene needs motion)
   - Sound Palette (primary + ambient + detail)
   - Emotional Tone (one word)
   VERIFICATION: Every scene has motion elements

6. write_post_notes — For EACH scene, specify Post-Production Notes:
   - Edit Timing (full 5s / trim to Xs / part of montage)
   - Transition (hard cut / crossfade / contrast cut / match cut / tonal shift)
   - Callbacks (reuses Scene XX / called back in Scene YY / standalone)
   VERIFICATION: Every scene has post-production notes

7. camera_audit — Run the Camera Distribution Audit:
   - Count each camera type across all scenes
   - Verify static ≤25%
   - Verify no 3+ consecutive same camera type
   - Verify at least 4 different types in any 10-scene window
   - Write the audit table at the end of the master script
   VERIFICATION: All distribution targets met

8. write_master_script — Write the complete master script to vsl/{project_slug}/copy/master_script.md using the format from Cinematic Director Section 13.
   VERIFICATION: File exists with all scenes in the BINDING format

9. write_handoff — Write handoff-master-script.json:
   {
     "master_script_path": "vsl/{project_slug}/copy/master_script.md",
     "total_scenes": {N},
     "camera_distribution": { "static": {N}, "pan": {N}, "dolly": {N}, ... },
     "static_percentage": {X}%,
     "audit_status": "PASS"
   }
   VERIFICATION: handoff file exists and audit_status = PASS
```

---

## PHASE 5: CAMERA PLAN (Agent — Cinematographer)

**Spawn a single `general-purpose` agent.** This is the Cinematographer validating camera directions.

### Agent Prompt Template:

```
You are the CINEMATOGRAPHER (Director of Photography). Your job is to read the Director's master script and produce a validated camera_plan.json.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

REQUIRED SKILLS (read ALL of these before starting):
- Cinematographer: Load the `cinematographer` skill from your skills directory — your full protocol for camera plan extraction & validation
- Kling Knowledge: docs/knowledge/video/kling.md — Kling camera motion parameters, API reference, and model capabilities
- Seedance 2 Camera Grammar: Load the `muapi-seedance-2` skill from your skills directory — professional cinema camera terms (Dolly In/Out, Crane Shot, Whip Pan, Tracking Shot) for cross-referencing camera vocabulary

Read these files:
- vsl/{project_slug}/copy/master_script.md (the BINDING master script)
- vsl/{project_slug}/state/handoff-master-script.json

CHECKPOINT: vsl/{project_slug}/state/camera-plan-checkpoint.json

STEPS:
1. extract_directions — Read every scene's Camera Direction (BINDING) section from the master script
   VERIFICATION: Extracted camera data for every scene

2. validate_kling — Validate each camera motion against Kling V3 API capabilities:
   - Map director's language to Kling camera_type values (see skill Step 2)
   - Check physical feasibility (macro + orbit = flag, ECU + pan = flag)
   - Check motion reason alignment (zoom_in on a wide vista = flag)
   VERIFICATION: All scenes validated, flags documented

3. distribution_audit — Count camera types, verify:
   - static ≤25%
   - No 3+ consecutive identical camera types
   - At least 4 types in any 10-scene window
   VERIFICATION: Distribution report generated

4. write_camera_plan — Write camera_plan.json to vsl/{project_slug}/prompts/camera_plan.json
   Include: scene, scene_name, master_script_direction, camera_type, intensity, motion_reason, motion_elements, duration, mode, cfg_scale, validated, validation_notes
   VERIFICATION: JSON file exists, all scenes present, format matches cinematographer skill specification

5. write_flags — If any scenes have conflicts, write them in the flags array. Severity: error / warning / info.
   VERIFICATION: All flags include severity and recommended alternative
```

---

## ── VALIDATION GATE: Master Script → Scene Prompts Alignment ──

**After Phase 6 (Scene Breakdown) completes, the orchestrator runs an alignment check:**

1. Read `master_script.md` and `scene_prompts.md`
2. For each scene, verify:
   - Image prompt subject matches master script Visual Direction subject
   - Image prompt framing matches master script framing
   - Image prompt respects "What is NOT in frame" exclusions
   - Video prompt camera motion matches camera_plan.json camera_type
   - Video prompt motion elements come from master script (not invented)
3. Any failures → flag to user before proceeding to image generation

---

## PHASE 6: SCENE BREAKDOWN (Agent)

**Spawn a single `general-purpose` agent.**

### Agent Prompt Template:

```
You are a VSL scene designer. Break the approved script into a detailed scene-by-scene production document.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

**IMPORTANT**: A master script exists at vsl/{project_slug}/copy/master_script.md. This is the BINDING source of truth. Your image prompts and video prompts MUST implement (not re-interpret) the master script's directions. A camera_plan.json also exists at vsl/{project_slug}/prompts/camera_plan.json — use its camera values directly.

REQUIRED SKILLS (read ALL of these before starting):
- Cinematic Director (Sections 1-12): Load the `cinematic-director` skill from your skills directory — shot psychology, staging, lighting (Sections 1-11 for image prompts, Section 12 for video motion prompts)
- Video Prompting Guide: .claude/commands/video-prompting-guide.md — image + video prompt alignment (7-Point + 5-Point checks, Cinematic Standards)

Read these files:
- vsl/{project_slug}/copy/brief.md
- vsl/{project_slug}/state/handoff-script.json
- vsl/{project_slug}/copy/script.md (the approved script)
- vsl/{project_slug}/copy/script_narrated.md (narrated version)
- vsl/{project_slug}/copy/master_script.md (BINDING source of truth — follow this)
- vsl/{project_slug}/prompts/camera_plan.json (validated camera directions — use these)
- docs/VSL_PRODUCTION_WORKFLOW.md (Phase 3 — Master Scene File, Phase 4 — Image Generation)
- (reference — see any existing scene_prompts.md for an 80+ scene example)

CHECKPOINT: vsl/{project_slug}/state/scenes-checkpoint.json

STEPS:
1. scene_planning — Break the script into scenes. Each scene gets: scene_id, spoken_text, duration_target, color_grade, sfx_notes, transition_in, transition_out. Follow the pacing chart from the script's act breakdown.
   VERIFICATION: Scene count matches expected duration (target_duration / avg_scene_duration)

2. image_prompts — Write image generation prompts for every scene using the 7-element formula: Subject, Setting, Lighting, Camera, Style, Details, Negative constraints. Apply Cinematic Director's shot psychology. Create a character anchor block if there's a recurring character.
   VERIFICATION: Every scene has an image prompt. Character anchor block is identical across all recurring-character scenes.

3. video_prompts — Write cinematic video motion prompts for every scene.

   MANDATORY: Read Cinematic Director Section 12 (Video Motion Prompt Craft) BEFORE writing ANY video prompt.
   MANDATORY: Read Video Prompting Guide "Cinematic Video Prompt Standards" section for atmosphere library.

   For each scene, write a 30-60 word prompt that includes ALL of these:
   a. Camera motion matching the camera_type API param EXACTLY (if camera: "pan_right", prompt describes a rightward pan)
   b. Visible motion elements — something IN the scene physically moves (hair, dust, water, fire, fabric, particles — NOT just camera)
   c. Atmosphere layer — volumetric light, particles, wind, steam, reflections, or caustics (use the atmosphere library by scene type)
   d. Technical camera grammar — named lighting techniques, physics directives, lens refs (Seedance-style director brief language)
   e. Duration target (e.g., "5s")

   Camera distribution: static ≤25% of total scenes. Diversify across pan, dolly, zoom, tilt, crane, orbit.
   Speed modifiers: only when earned. "Slow" for CTA/peaks (~10%). "Quick" for hooks/montages (~10%). Natural = default (~80%).
   No keyword soup ("8k, masterpiece, trending"). No boilerplate endings. One camera movement per scene.

   Map atmosphere to the emotional arc:
   - Warm Heritage acts → torch flicker, dust motes, fabric ripple, dancing shadows
   - Problem acts → chemical mist, fluorescent flicker, sheet waves, restless motion
   - Solution acts → water ripples, steam rising, golden hour light shifting, mineral shimmer
   - CTA acts → candle sway, slow fade, warm amber receding

   VERIFICATION:
   - 1:1 parity — image prompt count = video prompt count
   - Camera params match described motion for EVERY scene (audit all 88)
   - Static scenes ≤25% of total (count and report)
   - Every prompt has visible motion + atmosphere layer
   - All prompts 30-60 words (no camera-only prompts like "Dolly in. 5s.")

4. audio_notes — Assign SFX notes for each scene. What environment sounds, foley, and mood-reinforcing sounds should play. Reference the SFX library in docs/VSL_PRODUCTION_WORKFLOW.md Phase 7.
   VERIFICATION: Every scene has at least 1 SFX note

5. write_prompts_doc — Write the full scene prompts to vsl/{project_slug}/prompts/scene_prompts.md
   VERIFICATION: File exists with all scenes

6. write_handoff — Write handoff-scenes.json:
   {
     "prompts_path": "vsl/{project_slug}/prompts/scene_prompts.md",
     "total_scenes": {N},
     "total_images": {N},
     "total_video_prompts": {N},
     "character_anchor": "{anchor block text or null}",
     "color_arc": ["warm_sepia", "cold_industrial", "golden_hour", ...],
     "estimated_duration_seconds": {N},
     "image_output_dir": "vsl/{project_slug}/images/v1/",
     "parity_check": "PASS — {N} images = {N} video prompts"
   }
   VERIFICATION: handoff-scenes.json is valid JSON, parity check = PASS
```

---

## PHASE 7: VOICEOVER (Agent)

**Spawn a single `general-purpose` agent. Runs in PARALLEL with Phase 8 (both depend on approved script/scenes, not each other).**

Note: Phase 7 depends only on `scriptwriting` (for the narrated script). Phase 8 depends only on `scene-breakdown` (for image prompts). They can run concurrently.

### Agent Prompt Template:

```
You are a voiceover production agent. Generate the VSL voiceover and extract word-level timestamps.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

REQUIRED SKILLS (read ALL of these before starting):
- ElevenLabs: Load the `elevenlabs` skill from your skills directory — eleven_v3 voiceover generation with audio tags
- Whisper: Load the `whisper` skill from your skills directory — word-level transcription for captions

Read these files:
- vsl/{project_slug}/copy/brief.md (for voice preference)
- vsl/{project_slug}/state/handoff-script.json
- vsl/{project_slug}/copy/script_narrated.md (narrated script with audio tags)

CHECKPOINT: vsl/{project_slug}/state/voiceover-checkpoint.json

STEPS:
1. generate_voiceover — Use ElevenLabs API to generate the voiceover.
   Model: eleven_v3 (ALWAYS)
   Voice: as specified in brief.md (default: Laura FGY2WhTYpPnrIDTdsKH5, speed 1.2)
   Settings: stability 0.65, similarity_boost 0.7, style 0.2
   Save to: vsl/{project_slug}/audio/voiceover.mp3
   VERIFICATION: MP3 file exists at path, duration within 20% of target

2. transcribe_whisper — Run Whisper transcription for word-level timestamps.
   Script: python video/captions/transcribe_api.py vsl/{project_slug}/audio/voiceover.mp3
   Save to: vsl/{project_slug}/audio/whisper.json
   VERIFICATION: JSON file exists, has word-level entries with startMs/endMs fields

3. write_handoff — Write handoff-voiceover.json:
   {
     "voiceover_path": "vsl/{project_slug}/audio/voiceover.mp3",
     "whisper_path": "vsl/{project_slug}/audio/whisper.json",
     "duration_seconds": {actual duration},
     "voice_id": "{voice used}",
     "word_count": {N}
   }
   VERIFICATION: handoff-voiceover.json exists and is valid JSON
```

---

## PHASE 8: IMAGE GENERATION V1 (Agent)

**Spawn a single `general-purpose` agent.**

### Agent Prompt Template:

```
You are an image generation agent. Generate V1 low-quality draft images for all VSL scenes.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

REQUIRED SKILLS (read before starting):
- Nano Banana: .claude/commands/nanobanana.md — image generation reference + technical settings (timeouts, retries, SDK patterns)

Read these files:
- vsl/{project_slug}/copy/brief.md
- vsl/{project_slug}/state/handoff-scenes.json
- vsl/{project_slug}/prompts/scene_prompts.md (all scene prompts)

CHECKPOINT: vsl/{project_slug}/state/imagegen-v1-checkpoint.json

STEPS:
1. build_script — Build a Python generation script based on existing scripts in scripts/visuals/.
   Model: gemini-3.1-flash-image-preview (Nano Banana 2 — fast draft quality)
   Resolution: 1K (low quality for V1)
   Aspect: 9:16 for VSL (or as specified in brief)
   Workers: 5 concurrent
   Timeouts: 120s signal, 5s rate limit delays, 3 retries
   Output dir: vsl/{project_slug}/images/v1/
   CRITICAL: NEVER use base64.b64decode() — SDK returns raw bytes
   VERIFICATION: Script file exists and has correct model, resolution, and output path

2. run_generation — Execute the generation script. After EACH image saves successfully, immediately update `imagegen-v1-checkpoint.json` to mark that scene as "completed". Do not wait until all images finish — write the status after each one.
   On resume: read the checkpoint, find the first scene without "completed" status, restart generation from that index. This means a crash after image 50 of 100 resumes from image 51, not image 1.
   VERIFICATION: Number of generated images >= 90% of total_scenes (some may fail)

3. verify_images — Check every generated image:
   - File exists and is non-zero size
   - List any failures for retry
   - Report generation stats
   VERIFICATION: Image count report written

4. retry_failures — Retry any failed images (up to 3 attempts each).
   VERIFICATION: All images generated or failures documented

5. write_handoff — Write handoff-images-v1.json:
   {
     "images_dir": "vsl/{project_slug}/images/v1/",
     "total_generated": {N},
     "total_expected": {N},
     "failures": ["{list of any permanently failed scenes}"],
     "generation_model": "gemini-3.1-flash-image-preview",
     "resolution": "1K",
     "status": "READY_FOR_REVIEW",
     "user_feedback": null
   }
   VERIFICATION: handoff file exists, status = READY_FOR_REVIEW

IMPORTANT: After writing the handoff, notify the orchestrator that V1 images are ready for user review. The pipeline PAUSES here until the user provides feedback.
```

---

## ── HUMAN GATE: V1 Image Review ──

**The pipeline stops after Phase 8.** The orchestrator:

1. Reads `handoff-images-v1.json`
2. Notifies the user: "V1 images are ready for review at `vsl/{project_slug}/images/v1/`"
3. Asks the user to review each image and provide feedback:
   - For each image: APPROVED / NEEDS REVISION (with specific feedback)
   - Use `AskUserQuestion` to structure the review
4. Writes user feedback into `handoff-images-v1.json` under the `user_feedback` field:
   ```json
   "user_feedback": {
     "reviewed_at": "{timestamp}",
     "approved": ["scene_01", "scene_03", "scene_05", ...],
     "revisions": {
       "scene_02": "Character face is distorted, regenerate with stronger anchor block",
       "scene_04": "Too much empty space on the right, make the subject fill the frame",
       ...
     }
   }
   ```
5. Once feedback is captured, triggers Phase 9.

---

## PHASE 9: IMAGE REVISIONS + 2K RENDER (Agent)

**Spawn a single `general-purpose` agent.**

### Agent Prompt Template:

```
You are an image revision agent. Apply user feedback and render final 2K quality images.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

REQUIRED SKILLS (read before starting):
- Nano Banana: .claude/commands/nanobanana.md — image generation reference + technical settings

Read these files:
- vsl/{project_slug}/state/handoff-images-v1.json (includes user feedback)
- vsl/{project_slug}/prompts/scene_prompts.md (original prompts)

CHECKPOINT: vsl/{project_slug}/state/imagegen-v2-checkpoint.json

STEPS:
1. update_prompts — For each scene in the "revisions" list, update the prompt based on user feedback.
   Do NOT touch approved scene prompts.
   Write updated prompts to vsl/{project_slug}/prompts/scene_prompts_v2.md
   VERIFICATION: Updated prompts file exists

2. generate_revisions — Build and run a generation script for ONLY the revised scenes at 1K quality.
   Output to: vsl/{project_slug}/images/v2_revisions/
   VERIFICATION: All revision images generated

3. verify_revisions — Check revised images match the feedback requirements.
   VERIFICATION: All revised images verified

4. generate_final_2k — Build and run a script to generate ALL scenes (approved + revised) at 2K quality.
   Model: gemini-3.1-flash-image-preview
   Resolution: 2K
   Timeout: 5 minutes per image
   Workers: 3 concurrent (2K is slower)
   Output dir: vsl/{project_slug}/images/final/
   Use the V2 prompts for revised scenes, original prompts for approved scenes.
   VERIFICATION: All images in final directory at 2K resolution

5. write_completion — Update the workflow manifest status. Write final handoff:
   {
     "final_images_dir": "vsl/{project_slug}/images/final/",
     "total_images": {N},
     "resolution": "2K",
     "prompts_path": "vsl/{project_slug}/prompts/scene_prompts_v2.md",
     "status": "IMAGES_COMPLETE"
   }
   VERIFICATION: All files exist, workflow manifest updated
```

---

## PHASE 10: VIDEO RE-ALIGNMENT (Agent)

**Spawn a single `general-purpose` agent.** This runs AFTER all image revisions are complete and BEFORE Kling video generation.

**Why this phase exists**: Images go through multiple revision rounds (V1 → feedback → V2 → more feedback → V3...). By the time you have final 2K images, many scenes look different from what the video prompts originally described. A video prompt that says "torch flickers on gold cuffs" is wrong if the revised image has silver jewelry. This phase re-aligns every video prompt to match the ACTUAL final image.

### Agent Prompt Template:

```
You are a video prompt re-alignment agent. Your job is to ensure every video prompt accurately describes motion for the ACTUAL final image — not the original script, not the V1 image, but what's IN the final 2K image.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

Read these files:
- vsl/{project_slug}/prompts/scene_prompts_v2.md (current video prompts — may be stale)
- vsl/{project_slug}/prompts/camera_plan.json (camera directions — these stay unless impossible)
- vsl/{project_slug}/copy/master_script.md (master script — for atmosphere and motion elements)
- vsl/{project_slug}/state/handoff-images-v2.json (which scenes were revised)

REQUIRED SKILLS (read ALL of these before starting):
- Video Prompting Guide: .claude/commands/video-prompting-guide.md — Cinematic Standards + Video Re-alignment Protocol
- Cinematic Director (Section 12): Load the `cinematic-director` skill from your skills directory — Video Motion Prompt Craft

CHECKPOINT: vsl/{project_slug}/state/video-realign-checkpoint.json

STEPS:
1. identify_revised — Read handoff-images-v2.json to get the list of ALL scenes that were revised across any round. These are the scenes whose video prompts may be stale.
   VERIFICATION: List of revised scene IDs documented

2. examine_images — For EACH revised scene, examine the final 2K image at vsl/{project_slug}/images/final/. Compare what's ACTUALLY in the image against what the video prompt describes.
   For each scene, document:
   - What the video prompt currently describes
   - What's actually in the final image
   - Mismatches (elements in prompt but not in image, elements in image but not in prompt)
   VERIFICATION: Comparison table for every revised scene

3. check_camera_feasibility — For each revised scene, verify the camera_plan.json camera_type still makes sense for the final image. Example: if the original was a wide landscape (pan_right) but the revision changed it to a close-up portrait, pan_right may sweep off the subject. Flag any camera changes needed.
   VERIFICATION: Camera feasibility check for every revised scene

4. rewrite_prompts — For EACH scene with mismatches, rewrite the video prompt:
   - Keep the camera_type from camera_plan.json (unless flagged in step 3)
   - Describe motion for elements ACTUALLY visible in the final image
   - Keep atmosphere and motion elements from the master script where they match the image
   - Replace references to elements that no longer exist
   - Maintain 30-60 word prompt length
   - Maintain cinematic standards (visible motion + atmosphere + technical grammar)

   RULES:
   - Unchanged scenes: copy video prompt verbatim from scene_prompts_v2.md
   - Revised scenes with minor changes (e.g., lighting adjusted): surgical update only
   - Revised scenes with major changes (e.g., completely different composition): full rewrite
   - NEVER invent elements not in the image or master script
   VERIFICATION: All rewritten prompts pass the 5-point video alignment check

5. write_final_prompts — Write the COMPLETE final prompts document to vsl/{project_slug}/prompts/scene_prompts_final.md
   This file contains ALL scenes — unchanged + updated. It's the SOLE input for Kling manifest generation.
   Include a change log at the top:

   ## Re-alignment Change Log
   | Scene | Change Type | What Changed |
   |-------|-------------|-------------|
   | 05 | Minor | Updated "gold cuffs" → "silver bracelets" to match revised image |
   | 18 | Major | Complete rewrite — image changed from crystal close-up to mineral formation |
   | 26 | Unchanged | — |

   VERIFICATION: scene_prompts_final.md exists with ALL scenes

6. parity_check — Final verification:
   - Count image files in final/ = count video prompts in scene_prompts_final.md
   - Every video prompt camera motion matches camera_plan.json
   - No video prompt references elements absent from the final image
   - Every prompt is 30-60 words with visible motion + atmosphere
   VERIFICATION: Parity check PASS with counts documented

7. write_handoff — Write handoff-video-realign.json:
   {
     "final_prompts_path": "vsl/{project_slug}/prompts/scene_prompts_final.md",
     "total_scenes": {N},
     "scenes_updated": {N},
     "scenes_unchanged": {N},
     "camera_changes": {N},
     "parity_check": "PASS — {N} images = {N} video prompts",
     "status": "READY_FOR_KLING"
   }
   VERIFICATION: handoff file exists, status = READY_FOR_KLING
```

### Phase 10 Checkpoint (7 steps):

```json
{
  "task": "vsl-video-realignment",
  "total_steps": 7,
  "step_order": ["identify_revised", "examine_images", "check_camera_feasibility", "rewrite_prompts", "write_final_prompts", "parity_check", "write_handoff"],
  "steps": {
    "identify_revised": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" },
    "examine_images": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" },
    "check_camera_feasibility": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" },
    "rewrite_prompts": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" },
    "write_final_prompts": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" },
    "parity_check": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" },
    "write_handoff": { "status": "pending", "verified_at": null, "attempts": 0, "notes": "" }
  }
}
```

---

## PHASE 11: KLING VIDEO GENERATION (Agent)

**Spawn a single `general-purpose` agent.** Can run in PARALLEL with Phase 12 (Sound Design).

### Agent Prompt Template:

```
You are the Kling video generation agent. Generate video clips from the finalized production images.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

REQUIRED SKILLS (read ALL of these before starting):
- Kling Reference: docs/knowledge/video/kling.md — API params, rate limits, hard rules
- Kling Workflow: .claude/commands/kling-video-workflow.md — full pipeline skill
- Video Prompting Guide: .claude/commands/video-prompting-guide.md — prompt craft

Read these files:
- vsl/{project_slug}/prompts/scene_prompts_final.md (video prompts — USE THIS, not scene_prompts.md)
- vsl/{project_slug}/prompts/camera_plan.json (camera directions)
- vsl/{project_slug}/copy/master_script.md (reference for intent verification)

CHECKPOINT: vsl/{project_slug}/state/kling-checkpoint.json
Follow Ralph Loop checkpoint protocol: load the `ralph-loop` skill from your skills directory

HARD RULES (non-negotiable):
- model_name: "kling-v3" ALWAYS — never use kling-v1, kling-v1.5, or kling-pro
- cfg_scale: 0.4 ALWAYS
- negative_prompt: ALWAYS include (no text, no watermark, no blurry, no distorted)
- Image input: raw base64 PNG, max 10MB per image
- Rate limits: 5s delay between API calls, retry on 429/rate limit errors
- Wait 10 minutes (not 5) before retrying after rate limit at scale (86+ clips)

TASK ID PERSISTENCE (crash recovery):
Maintain vsl/{project_slug}/state/kling_task_map.json:
{
  "scene_01": {"task_id": "abc123", "status": "processing", "submitted_at": "2026-03-06T..."},
  "scene_02": {"task_id": "def456", "status": "completed", "video_url": "https://..."}
}
Write each task_id to this file IMMEDIATELY after API submission, BEFORE polling.
On resume: read this file, poll existing "processing" task_ids instead of resubmitting.

STEPS:
1. build_manifest — Build kling_manifest.json from scene_prompts_final.md + camera_plan.json. One entry per scene with: image_path, video_prompt, camera_type, camera_params, cfg_scale, negative_prompt.
   VERIFICATION: Manifest has same scene count as scene_prompts_final.md

2. validate_manifest — Verify: every image exists and is under 10MB, every camera type is valid for kling-v3, parity check (images = prompts = manifest entries).
   VERIFICATION: Zero validation errors

3. generate_batch — Submit scenes to Kling API. Write task_id to kling_task_map.json IMMEDIATELY after each API submission (before polling). After each clip downloads successfully, also mark that scene as "completed" in kling-checkpoint.json.
   This dual-write pattern enables two kinds of recovery:
   - API crash (task submitted but not polled): read kling_task_map.json, poll existing task_ids instead of resubmitting
   - Context exhaustion mid-generation: read kling-checkpoint.json, find first scene without "completed" status, resume from there
   A crash after clip 50 of 100 resumes from clip 51, not clip 1.
   Download clips to vsl/{project_slug}/video/clips/.
   VERIFICATION: All clips downloaded, each > 500KB

4. retry_failures — Re-submit any failed scenes (max 3 attempts each). Update kling_task_map.json.
   VERIFICATION: Zero remaining failures OR documented with reasons

5. verify_clips — Verify every clip: file exists, size > 500KB, duration matches expected (5s or 10s).
   VERIFICATION: Parity count matches. Total clips = total scenes.

6. write_handoff — Write handoff-kling.json:
   {
     "clips_dir": "vsl/{project_slug}/video/clips/",
     "total_clips": N,
     "total_expected": N,
     "failures": [],
     "cost_estimate": "$X.XX",
     "task_id_map_path": "vsl/{project_slug}/state/kling_task_map.json"
   }
   VERIFICATION: handoff-kling.json exists and is valid JSON
```

### Checkpoint Template:

```json
{
  "task": "vsl-kling-video",
  "total_steps": 6,
  "step_order": ["build_manifest", "validate_manifest", "generate_batch", "retry_failures", "verify_clips", "write_handoff"],
  "steps": {
    "build_manifest": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "validate_manifest": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "generate_batch": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "retry_failures": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "verify_clips": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "write_handoff": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""}
  },
  "next_phase_skills": [
    "sound-design skill (from your skills directory)",
    ".claude/commands/remotion-audio.md"
  ]
}
```

---

## PHASE 12: SOUND DESIGN (Agent — Optional)

**This phase is OPTIONAL.** Two audio production paths exist:

- **Path A — Post-generation SFX (default)**: Spawn this agent to create `audio_design.json`, then apply SFX via `apply_sfx_to_clips.py` and Remotion's `SceneWithAudio` component.
- **Path B — Embedded audio (future)**: Audio embedded during Kling generation via proxy API + Kling subscription. If this path is active, skip Phase 12 entirely — clips already contain audio.

**Before spawning the agent, ask the user**: "Is audio being handled via Kling proxy API (embedded during generation), or should I create a sound design map for post-processing?"

If Path B → mark Phase 12 as "skipped" in the workflow manifest and proceed to Phase 13.

**If Path A → Spawn a single `general-purpose` agent.** Can run in PARALLEL with Phase 11 (Kling Video Gen) — only needs master script + scene prompts, NOT actual video clips.

### Agent Prompt Template:

```
You are the sound design agent. Create an implementable SFX layer map for every scene.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

REQUIRED SKILLS (read ALL of these before starting):
- Sound Design: Load the `sound-design` skill from your skills directory — layer rules, approved/banned sounds, volume hierarchy
- Remotion Audio: .claude/commands/remotion-audio.md — SFX library, implementation format, banned sounds list

Read these files:
- vsl/{project_slug}/copy/master_script.md (atmosphere and sound palette per scene)
- vsl/{project_slug}/prompts/scene_prompts_final.md (conceptual audio descriptions)

CHECKPOINT: vsl/{project_slug}/state/sound-design-checkpoint.json

HARD RULES:
- Maximum 3 audio layers per scene
- Volume hierarchy: Primary > Ambient > Detail — NEVER violate
- Only use sounds from the APPROVED list in remotion-audio.md
- NEVER use banned sounds (breathing_calm, breathing_restless, marching, war_drums, armor_clank, low_drone, electric_zap, crystal_ring, lab_glass, fluorescent_buzz, water_drip, water_splash_bath)
- Same Sonic World rule: all sounds in a scene must belong to the same environment

STEPS:
1. plan_audio_design — Read master script atmosphere sections. Map each scene to its sonic environment.
   VERIFICATION: Every scene has an environment assignment

2. assign_layers — For each scene, assign up to 3 SFX layers with: file, volume (0-1), loop (bool), delay_ms, fadeIn_ms. Follow the volume hierarchy.
   VERIFICATION: No scene exceeds 3 layers, no banned sounds used

3. write_audio_design — Write audio_design.json to vsl/{project_slug}/manifest/audio_design.json in the format expected by audioDesigns.ts.
   VERIFICATION: Valid JSON, every scene has an entry

4. write_handoff — Write handoff-sound-design.json:
   {
     "audio_design_path": "vsl/{project_slug}/manifest/audio_design.json",
     "total_scenes": N,
     "avg_layers_per_scene": X.X,
     "banned_sounds_used": 0
   }
   VERIFICATION: handoff exists and banned_sounds_used == 0
```

### Checkpoint Template:

```json
{
  "task": "vsl-sound-design",
  "total_steps": 4,
  "step_order": ["plan_audio_design", "assign_layers", "write_audio_design", "write_handoff"],
  "steps": {
    "plan_audio_design": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "assign_layers": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "write_audio_design": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "write_handoff": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""}
  },
  "next_phase_skills": [
    ".claude/commands/remotion-audio.md"
  ]
}
```

---

## PHASE 13: POST-PRODUCTION — REMOTION ASSEMBLY (Agent)

**Spawn a single `general-purpose` agent.** Depends on Phase 7 (voiceover), Phase 11 (Kling clips), AND Phase 12 (sound design) all being complete.

### Agent Prompt Template:

```
You are the post-production agent. Assemble the final VSL from video clips, voiceover, SFX, and captions using Remotion.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

REQUIRED SKILLS (read ALL of these before starting):
- Remotion Audio: .claude/commands/remotion-audio.md — SFX implementation, SceneWithAudio component, batch rendering
- Remotion: .claude/skills/remotion/SKILL.md (if exists) — Remotion best practices

Read these files:
- vsl/{project_slug}/state/handoff-kling.json (video clips location)
- vsl/{project_slug}/state/handoff-sound-design.json (audio design location)
- vsl/{project_slug}/state/handoff-voiceover.json (voiceover + whisper location)
- vsl/{project_slug}/manifest/audio_design.json (SFX assignments)
- vsl/{project_slug}/audio/whisper.json (word-level timestamps for captions)

CHECKPOINT: vsl/{project_slug}/state/postprod-checkpoint.json

HARD RULES:
- ALWAYS get width/height/fps from ffprobe — NEVER hardcode dimensions
- Calculate durationInFrames from actual clip duration and fps
- Volume hierarchy for SFX: Primary > Ambient > Detail
- Voiceover volume: always louder than any SFX layer

STEPS:
1. prepare_assets — Copy/verify all input files exist. Run ffprobe on every video clip to get exact dimensions, duration, fps.
   VERIFICATION: ffprobe data for every clip, no missing files

2. build_scene_manifest — Create vsl_manifest.json mapping scene → clip path + voiceover timing + trim points.
   VERIFICATION: Manifest covers all scenes, timing adds up to voiceover duration (±5%)

3. apply_sfx — Update audioDesigns.ts with the sound design map. Configure SceneWithAudio components.
   VERIFICATION: audioDesigns.ts has entries for all scenes, no banned sounds

4. build_composition — Create Root.tsx composition stitching all scenes with voiceover overlay and captions from Whisper JSON.
   VERIFICATION: Composition registered, total duration matches voiceover

5. render — Run Remotion render. Output to vsl/{project_slug}/video/final/vsl_draft.mp4
   VERIFICATION: Output file exists, ffprobe shows h264+aac, duration within 5% of expected

6. write_handoff — Write handoff-postprod.json:
   {
     "rendered_path": "vsl/{project_slug}/video/final/vsl_draft.mp4",
     "duration_seconds": N,
     "resolution": "1080x1920",
     "filesize_mb": N
   }
```

### Checkpoint Template:

```json
{
  "task": "vsl-postprod",
  "total_steps": 6,
  "step_order": ["prepare_assets", "build_scene_manifest", "apply_sfx", "build_composition", "render", "write_handoff"],
  "steps": {
    "prepare_assets": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "build_scene_manifest": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "apply_sfx": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "build_composition": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "render": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "write_handoff": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""}
  },
  "next_phase_skills": [
    ".claude/commands/video-editor.md"
  ]
}
```

---

## PHASE 14: FINAL EDIT (Agent)

**Spawn a single `general-purpose` agent.**

### Agent Prompt Template:

```
You are the final edit agent. Apply last-mile polish to the assembled VSL.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

REQUIRED SKILLS (read ALL of these before starting):
- Video Editor: .claude/commands/video-editor.md — EDL architecture, jump cuts, overlay layers

Read these files:
- vsl/{project_slug}/state/handoff-postprod.json (rendered draft path)
- vsl/{project_slug}/copy/master_script.md (reference for pacing verification)

CHECKPOINT: vsl/{project_slug}/state/final-edit-checkpoint.json

STEPS:
1. review_draft — Watch/analyze the draft. Note pacing issues, subtitle errors, audio sync problems.
   VERIFICATION: Review notes documented

2. subtitle_pass — Verify all captions are correctly timed, properly styled, no overlaps, no missing words.
   VERIFICATION: Caption coverage matches voiceover duration

3. pacing_pass — Check scene durations match the Fabula pacing targets (Hook: 3.0s, Legend: 1.8-2.0s, Problem: 2.3-2.6s, Solution: 2.9-3.0s, Close: 3.0-3.1s per scene). Flag any scenes significantly off target.
   VERIFICATION: Pacing analysis documented

4. export_final — Re-render with all fixes applied. Output to vsl/{project_slug}/video/final/vsl_final.mp4
   VERIFICATION: Final file exists, ffprobe shows h264+aac

5. write_handoff — Write handoff-final-edit.json:
   {
     "final_path": "vsl/{project_slug}/video/final/vsl_final.mp4",
     "duration_seconds": N,
     "resolution": "1080x1920",
     "filesize_mb": N,
     "fixes_applied": ["list of changes made"]
   }
```

### Checkpoint Template:

```json
{
  "task": "vsl-final-edit",
  "total_steps": 5,
  "step_order": ["review_draft", "subtitle_pass", "pacing_pass", "export_final", "write_handoff"],
  "steps": {
    "review_draft": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "subtitle_pass": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "pacing_pass": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "export_final": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "write_handoff": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""}
  },
  "next_phase_skills": [
    "quality-gate skill (from your skills directory)"
  ]
}
```

---

## PHASE 15: FINAL GATE — QUALITY AUDIT (Agent)

**Spawn a single `general-purpose` agent.** This is the last step before delivery.

### Agent Prompt Template:

```
You are the quality gate auditor. Run the 3-pass pre-delivery audit on the completed VSL.

BEFORE STARTING: mkdir -p vsl/{project_slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

REQUIRED SKILLS (read ALL of these before starting):
- Quality Gate: Load the `quality-gate` skill from your skills directory

Read these files:
- vsl/{project_slug}/state/handoff-final-edit.json (final video path)
- vsl/{project_slug}/copy/master_script.md (source of truth for content)
- vsl/{project_slug}/copy/compliance-report.md (compliance status)
- vsl/{project_slug}/prompts/camera_plan.json (camera directions)

CHECKPOINT: vsl/{project_slug}/state/final-gate-checkpoint.json

STEPS:
1. source_of_truth_check — Does the final video match the master script?
   - Every scene present? No missing scenes?
   - Visual directions followed? Camera movements match camera_plan.json?
   - Dialogue/narration matches approved script?
   VERIFICATION: Checklist with PASS/FAIL per item

2. functional_verification — Technical quality check:
   - Audio synced with video? No drift?
   - Captions aligned with voiceover? No timing errors?
   - No black frames, no frozen frames?
   - SFX at correct volumes? No clipping?
   - Final resolution and file format correct?
   VERIFICATION: Checklist with PASS/FAIL per item

3. deliverable_completeness — All project files present:
   - All checkpoints show "complete"?
   - All handoff files valid JSON?
   - Final video at expected path?
   - Compliance report shows PASS?
   - Panel report shows 90+?
   - All images in images/final/?
   - Voiceover and whisper.json present?
   VERIFICATION: Checklist with PASS/FAIL per item

4. write_report — Write final-gate-report.md to vsl/{project_slug}/copy/:
   Result: PASS → deliver to user
   Result: FAIL → list specific failing items with fix instructions

If FAIL: The orchestrator must fix the failing items (or route to appropriate phase agent) and re-run the Final Gate.
```

### Checkpoint Template:

```json
{
  "task": "vsl-final-gate",
  "total_steps": 4,
  "step_order": ["source_of_truth_check", "functional_verification", "deliverable_completeness", "write_report"],
  "steps": {
    "source_of_truth_check": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "functional_verification": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "deliverable_completeness": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""},
    "write_report": {"status": "pending", "verified_at": null, "attempts": 0, "notes": ""}
  }
}
```

---

## Orchestrator Flow (What YOU Do)

When invoked via `/project:vsl-production`, follow this sequence:

### MANDATORY: Manifest Sync After Every Phase

**After EVERY agent returns** (regardless of phase), immediately update `workflow-manifest.json`:

```bash
python -c "from scripts.manifest_sync import sync_phase; print(sync_phase('{project_root}', '{phase_id}'))"
```

Or manually: read `workflow-manifest.json`, find the phase entry, set `"status": "completed"`, set `"active_session_id": null`, update `"last_progress_at"` to now. Write atomically.

**On resume**, run `sync_all_phases` to catch up on any missed updates:
```bash
python -m scripts.manifest_sync {project_root}
```

This is NON-NEGOTIABLE. The manifest must reflect reality at all times. A completed phase with status "pending" causes duplicate work on resume.

### 1. Check for Existing Workflow

Look in vsl/, ads/, ugc/ for any existing project directories.
If found, ask user: "Resume existing workflow {project_slug}?" or "Start new?"
If resuming:
1. Run `python -m scripts.manifest_sync {project_root}` to sync all phases
2. Read the updated workflow manifest and pick up from the last incomplete phase
Always run: mkdir -p {project_root}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}

### 2. Run Phase 1 (Intake) — INTERACTIVE

Run directly (no agent). Gather info, write brief, create manifest.

### 3. Start Phase 2 (Research) — AGENT

Spawn a `general-purpose` agent with the Phase 2 prompt. Wait for completion. Read handoff-research.json.

### 4. Start Phase 3 (Scriptwriting) — AGENT TEAM

Spawn the 3-agent team. Monitor progress. Wait for panel score 90+ AND humanizer pass.

### 5. Start Phase 4 (Master Script) — AGENT

**PRE-CONDITION**: Read handoff-script.json. Verify:
- humanizer_applied == true
- compliance_status == "PASS"
- panel_score >= 90
If ANY check fails → STOP and report to user. Do NOT proceed.

Once verified, spawn the Director agent. Wait for completion. Verify master_script.md exists and camera audit passes.

### 6. Start Phase 5 (Camera Plan) — AGENT

Spawn the Cinematographer agent. Wait for completion.

Review camera_plan.json flags:
- If flags contain severity: "error" → STOP. Present each error to user with recommended alternative. Ask: "Accept alternative? Or specify different camera motion?" Update camera_plan.json. Do NOT proceed to Phase 6 with unresolved errors.
- If flags contain severity: "warning" → Log warnings, proceed. Inform user: "Camera plan has {N} warnings — review camera_plan.json."
- If flags contain severity: "info" → Proceed without interruption.

### 7. Start Phase 6 (Scene Breakdown) — AGENT

Spawn scene breakdown agent. After completion, run the **Validation Gate** — check alignment of scene_prompts.md against master_script.md. If any alignment failures → fix before proceeding.

### 8. SCRIPT APPROVAL GATE — Human Review

After the Validation Gate passes, PAUSE and present to the user:

"Your script package is ready for review before voiceover generation begins."

Present these files for review:
1. Script: `vsl/{project_slug}/copy/script.md`
2. Master Script: `vsl/{project_slug}/copy/master_script.md`
3. Scene Breakdown: `vsl/{project_slug}/prompts/scene_prompts.md`
4. Camera Plan: `vsl/{project_slug}/prompts/camera_plan.json`
5. Compliance Report: `vsl/{project_slug}/copy/compliance-report.md`
6. Panel Report: `vsl/{project_slug}/copy/panel-report.md`

Ask: "Review these files. When ready:
  - **APPROVE** → proceed to voiceover + image generation
  - **REVISE** → provide feedback (which file, what to change)
  - Specify **voice preference** for voiceover (default: Laura/speed 1.2)"

If REVISE: route feedback to appropriate phase agent, re-run from that point.
If APPROVE: proceed to Phases 7+8 in parallel.

Default voiceover: Laura (ID: FGY2WhTYpPnrIDTdsKH5), speed 1.2, eleven_v3, stability 0.65, similarity_boost 0.7, style 0.2

### 9. Start Phases 7 + 8 IN PARALLEL

Once Script Approval Gate passes:
- Spawn voiceover agent (Phase 7) — needs narrated script + voice settings from gate
- Spawn image gen agent (Phase 8) — needs scene prompts

Run both in parallel (they're independent). Remember: you are a THIN DISPATCHER — do not read skill files yourself.

### 10. HUMAN GATE — Image Review

When Phase 8 completes, pause and present images to user for review. Collect feedback.

### 11. Start Phase 9 (Image Revisions + 2K)

Spawn revision agent with user feedback. May involve multiple rounds.

### 12. Start Phase 10 (Video Re-alignment)

Once ALL images are finalized at 2K, spawn video re-alignment agent.

### 13. Start Phases 11 + 12 IN PARALLEL

Once Phase 10 completes:
- Spawn Kling video gen agent (Phase 11) — needs scene_prompts_final.md + camera_plan.json + final images
- Spawn sound design agent (Phase 12) — needs master_script.md + scene_prompts_final.md (does NOT need video clips)

Run both in parallel. For 60+ scenes, consider splitting Phase 11 into 2-3 batch agents.

### 14. VOICEOVER GATE — Human Review

After Phase 7 (Voiceover) completes (may have finished earlier during Phase 9-12):
1. Check duration within 20% of target
2. Verify whisper.json word count matches script (±5%)
3. Present to user: "Listen to voiceover. APPROVE / RE-GENERATE?"
4. If RE-GENERATE → re-run Phase 7 with feedback
5. If APPROVE → voiceover locked for post-production

### 15. Start Phase 13 (Post-Production)

Once Phase 7 (voiceover approved), Phase 11 (clips), AND Phase 12 (sound design) are ALL complete:
Spawn post-production agent. This assembles everything in Remotion.

### 16. Start Phase 14 (Final Edit)

Spawn final edit agent for last-mile polish.

### 17. Start Phase 15 (Final Gate)

Spawn quality audit agent. Result: PASS → deliver. FAIL → fix and re-run gate.

### 18. Deliver

Present final VSL to user:
- Final video: `vsl/{project_slug}/video/final/vsl_final.mp4`
- Duration, resolution, file size
- Final gate report: `vsl/{project_slug}/copy/final-gate-report.md`
- Complete project folder: `vsl/{project_slug}/`

---

## Ralph Loop Integration

Every agent in this workflow follows the Ralph Loop checkpoint protocol:

1. **Before every step**: Read checkpoint, check `owner_session_id` (session fence)
2. **Start of step**: Set status to `in_progress`, write checkpoint
3. **After step**: Verify result, set status to `complete` or `failed`, write checkpoint
4. **Heartbeat**: Update `last_updated_at` on every write
5. **On failure**: Increment `attempts`, retry up to 3 times, then `blocked`
6. **Atomic writes**: backup → tmp → rename

The orchestrator monitors checkpoints and respawns agents on context exhaustion.

### Recovery Behavior

If the main conversation crashes or you lose context:
1. User re-invokes `/project:vsl-production`
2. Orchestrator finds existing workflow in `vsl/{project_slug}/state/`
3. Reads manifest → identifies last incomplete phase
4. Reads that phase's checkpoint → identifies last incomplete step
5. Resumes from there. No lost work.

---

## Quick Reference

| Phase | Type | Depends On | Output |
|-------|------|-----------|--------|
| 1. Intake | Interactive | — | brief.md |
| 2. Research | Agent | Intake | research.md + handoff |
| 3. Scriptwriting | Agent Team (3) | Research | script.md + compliance + panel 90+ + humanizer |
| 4. Master Script | Agent (Director) | Script approved | master_script.md + handoff |
| 5. Camera Plan | Agent (Cinematographer) | Master Script | camera_plan.json |
| 6. Scene Breakdown | Agent | Camera Plan | scene_prompts.md + handoff |
| — VALIDATION GATE — | Orchestrator | Scenes + Master Script | Alignment check |
| — SCRIPT APPROVAL GATE — | Human Review | Validation Gate | User approves before voiceover |
| 7. Voiceover | Agent | Script Approved (parallel w/8) | voiceover.mp3 + whisper.json |
| 8. Image Gen V1 | Agent | Scenes validated (parallel w/7) | V1 draft images |
| — HUMAN GATE — | User Review | V1 Images | Feedback in handoff |
| 9. Image Revisions | Agent | Feedback | 2K final images |
| 10. Video Re-alignment | Agent | Final images | scene_prompts_final.md |
| 11. Kling Video Gen | Agent | Re-aligned prompts (parallel w/12) | Video clips |
| 12. Sound Design | Agent | Master Script (parallel w/11) | audio_design.json |
| — VOICEOVER GATE — | Human Review | Voiceover complete | User approves voiceover |
| 13. Post-Production | Agent (Remotion) | Clips + SFX + Voiceover | Assembled draft |
| 14. Final Edit | Agent | Draft assembled | Polished final MP4 |
| 15. Final Gate | Agent (Quality Audit) | Final edit complete | PASS/FAIL |
