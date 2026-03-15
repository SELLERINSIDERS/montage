# VSL Video Production Framework

## What This Project Does
End-to-end video production pipeline: write scripts → compliance → images → video → voiceover → sound design → post-production. Supports three production types: VSLs, short ads, and UGC clips. Uses Kling AI, Remotion, HeyGen, ElevenLabs, and Whisper.

## Production Pipeline

The full VSL production cycle is orchestrated by `/project:vsl-production`:

1. **Script & Storyboard** — scene breakdown, shot descriptions, pacing
2. **Scene Design** (`/project:cinematic-director`) — Epic Scale Doctrine applied to every scene (Phase 4)
3. **Camera Plan** (`/project:cinematographer`) — validated camera directions → `camera_plan.json` (Phase 5)
4. **Image Generation** (`/project:nanobanana`) — Nano Banana Pro (Gemini) for scene frames
5. **Video Generation** (`/project:kling-video-workflow`) — Kling V3 image-to-video synthesis
6. **Voiceover** — ElevenLabs text-to-speech
7. **Sound Design** (`/project:sound-design`) — SFX mapping and layering (optional — Path A only)
8. **Post-Production** (`/project:video-editor`) — EDL generation for Remotion
9. **Audio Mix** (`/project:remotion-audio`) — Final SFX + voiceover composition in Remotion

Each command file contains detailed agent descriptions and instructions. Read the command when invoked.

### Skill Access Pattern
Skills can be stored in a shared directory (e.g., `shared/skills/`). Local `.claude/commands/` files are thin wrappers that load the real skill from there. This means team members working in any project can access and improve skills centrally.

## Quality Gates (Non-Negotiable)

All customer-facing scripts and voiceover text MUST pass compliance before production.

### Gate 1: FDA/FTC Compliance Check
- **References**: `banned-claims.md`, `approved-claims.md`, `disclaimer-triggers.md`
- **Result**: PASS / PASS WITH WARNINGS / FAIL — any FAIL blocks production

### Gate 2: 10-Expert Panel Review
For any script or narration copy, run the expert panel after compliance passes.
- **Threshold**: Average must be 90+ to approve

## Hard Rules

### Kling Video Generation
- **DEFAULT: UseAPI.net proxy** — `KLING_USE_PROXY=true` in `.env`. NEVER use direct API for production.
- **DEFAULT model: `kling-v3-omni`** (proxy maps this as `kling-v3-0`) — produces clips WITH embedded audio
- `cfg_scale: 0.4` ALWAYS
- Always include `negative_prompt`
- 10 MB image size limit
- **Audio**: proxy only — `enable_audio: true` + append `[Audio: ...]` to video prompt. Audio producer agent writes `audio_prompts.json` before manifest build.
- Proxy image flow: upload PNG to `/assets` → get CDN URL → reference URL in payload (NOT raw base64)
- Direct API fallback (testing only): raw base64 PNG, model `kling-v3`, NO audio
- Describe emotion/intent in motion prompts, not just mechanics
- Add explicit in-prompt negatives for pose control ("NOT standing, NOT facing, IS SITTING")

### Remotion / EDL
- EDL must specify exact pixel dimensions — Remotion hardcodes NOTHING
- Always get width/height/fps from `ffprobe` — NEVER hardcode
- SFX overlay: use `scripts/apply_sfx_to_clips.py` (batch) or `scripts/reapply_sfx_single.py` (single)
- Strip audio first when re-applying SFX

### Image Generation (Nano Banana Pro)
- `MAX_WORKERS=1` mandatory for 2K generation (concurrent deadlocks)
- 3-4 min/image at 2K, use `gemini-3.1-flash-image-preview` with `image_size="2K"`
- For multi-version: track which prompt came from which source. For 2K upscale use EXACT original prompt

### Compliance
- **Banned**: disease claims, drug claims, absolute claims, superiority claims
- **Personal Attributes trap**: YOU + NEGATIVE STATE = instant rejection

## Detailed Reference
Read topic files on demand — don't guess, use `Read()`:
- **Video production**: `docs/knowledge/video/` (kling, remotion-audio, vsl-pipeline, voiceover-captions, video-editing)
- **Shared**: `docs/knowledge/shared/` (compliance, image-generation, lessons-learned)

## Project Isolation — Non-Negotiable

Every production gets ONE folder. ALL deliverables live inside it. Nothing project-specific at root level.

### Production Types → Folder Roots

| Type | Folder | Phases active | Typical length |
|------|--------|--------------|----------------|
| VSL | `vsl/{slug}/` | All 15 | 3-6 min |
| Short Ad | `ads/{slug}/` | 13 (skip Research, Image Revisions) | 15-60 s |
| UGC Clip | `ugc/{slug}/` | 10 (skip Research, Master Script, Camera Plan, Voiceover, Image Revisions) | 15-30 s |

### Canonical Folder Structure (all types use the same layout)

```
{type}/{project_slug}/
├── README.md               ← project status + current phase
├── copy/                   ← brief, arc_sketch, script, master_script, compliance report
├── prompts/                ← scene_prompts.md, scene_prompts_final.md, camera_plan.json
├── images/v1/ + final/     ← all generated images
├── audio/                  ← voiceover.mp3 + whisper.json
├── video/clips/ + final/   ← Kling clips + rendered output
├── manifest/               ← kling_manifest.json + audio_design.json
└── state/                  ← workflow-manifest.json + all phase checkpoints/handoffs
```

**When starting any new project**: run `mkdir -p {type}/{slug}/{state,copy,prompts,images/v1,images/final,audio,video/clips,video/clips_with_audio,video/final,manifest}` first.

**To resume**: read `{type}/{slug}/state/workflow-manifest.json` — it tells you current phase, skipped phases, and paths to all files.

## Key File Locations
- **Remotion project**: `video/remotion-video/`
- **SFX scripts**: `scripts/apply_sfx_to_clips.py` (batch), `scripts/reapply_sfx_single.py` (single)
- **Video status**: `video/VIDEO_STATE.md`

## Pipeline Feedback Protocol (Standing Instruction)

Every production session runs this protocol automatically — no explicit invocation needed.

**BEFORE any generative phase** (image prompts, video prompts, scripts, EDL, SFX maps, camera plans):
Run feedback retrieval for the current stage. Inject retrieved entries as a "PAST FEEDBACK" block before writing anything.

**AFTER any user rejection or correction** (wrong pose, motion misread, caption too small, compliance fail, etc.):
Capture to the feedback system immediately. Confirm to the user: "Feedback saved — won't happen again."
