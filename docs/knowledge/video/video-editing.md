---
domain: video-production
updated: 2026-03-06
tags: [remotion, edl, videographer, editing, jump-cuts]
---

# Video Editing — EDL Architecture

## State File
`video/VIDEO_STATE.md` — full lessons learned, API reference, file locations

## Current Project
v2c tier list magnesium (70s, 1080x1920, Kate avatar + Bella voice, full-screen)

## Architecture
EDL-driven — videographer produces COMPLETE rendering spec, Remotion reads ALL values from EDL.

**CRITICAL**: EDL must specify exact pixel dimensions, font sizes, colors, spring configs. No prose descriptions. Remotion hardcodes NOTHING.

## Pipeline
script → HeyGen avatar → Whisper captions → **videographer v2 EDL** → Remotion render → final MP4

## Videographer
- **Script**: `video/editing/videographer.py` v2
- **Skill**: `.claude/commands/video-editor.md`

## EDL v2 Format
- `layers[]` — layout/content/animations per element
- `avatar_track.jump_cuts` — cut timing and scale
- `shelf_track` — with background pill
- `caption_track` — word-level timing

## Remotion Components
- `EDLLayer.tsx` — generic, reads ALL values from EDL
- `EDLShelf.tsx` — EDL-driven shelf display
- Legacy replaced: `TierCard.tsx`, `HookOverlay.tsx`, `RankedProductsBar.tsx`

## Jump Cuts
- **INSTANT**, content-driven
- Scales: 1.0-1.7, varied transform origins
- Minimum: 1 cut per 5 seconds
- TIGHT on emotional beats, WIDE on product reveals, EXTRA TIGHT for pattern breaks
