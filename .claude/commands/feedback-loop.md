---
name: feedback-loop
description: Pipeline self-learning system — captures user rejections and corrections at any production stage and retrieves past feedback before future generations. Invoke after any rejection/correction to save it, or before any generative phase to load past rules. Makes every production smarter than the last.
---

# Feedback Loop — VSL Wrapper

Load the Feedback Loop skill from your configured skills directory before doing anything.

> **Note:** Skills are not bundled in this repo. Configure your own skills directory and place the `feedback-loop/SKILL.md` skill there. See the project README for details.

Execute the capture or retrieval protocol exactly as the skill describes.

## VSL Project Context

**Two usage modes:**

**Mode 1 — Capture** (after any rejection or correction):
Run Section A of the skill. Use `supa-capture` to save the feedback to the `learnings` table with `category: "video-feedback"`. Confirm to the user: "Feedback saved — this won't happen again in future productions."

**Mode 2 — Retrieve** (before any generative phase):
Run Section B of the skill. Query the `learnings` table for `video-feedback` entries matching the current stage. Inject results as a "PAST FEEDBACK" block into your working context before writing any prompts.

## Stage IDs for This Project

Use these exact stage IDs in `applies_to` and topic fields:

| Phase | Stage ID |
|---|---|
| Script Writing (Phase 3) | `scriptwriting` |
| Master Script / Cinematic Director (Phase 4) | `master-script` |
| Camera Plan (Phase 5) | `camera-plan` |
| Image Generation V1 (Phase 8) | `imagegen-v1` |
| Image Generation V2 (Phase 9) | `imagegen-v2` |
| Video Realignment (Phase 10) | `video-realignment` |
| Kling Video Generation (Phase 11) | `kling-video` |
| Sound Design (Phase 12) | `sound-design` |
| Post-Production / Remotion (Phase 13) | `post-production` |
| Final Gate (Phase 15) | `final-gate` |

## Production Types

Use these exact values in `applies_to`:
- `vsl` — full-length VSL (3-6 min)
- `short_ad` — short ad (15-60s)
- `ugc` — UGC clip (15-30s)
