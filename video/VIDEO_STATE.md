# Video Ad Pipeline — State & Lessons Learned

## Current Version: v2c (2026-03-04)

### V2c Results
- **Output**: `video/output/final/tier_list_magnesium_v2b.mp4` (82MB, 70s, 1080x1920)
- **Avatar**: Kate talking photo, full-screen, Bella Friendly voice, Avatar IV motion
- **Script**: `video/scripts/tier_list_magnesium_v2.json`
- **EDL**: `video/remotion-video/public/edl.json` (videographer v2 — complete rendering spec)
- **Status**: EDL-driven architecture — all visual properties read from EDL, nothing hardcoded in Remotion

### V2c Architecture (EDL-Driven)
- **Avatar fills 100% of the frame** — it IS the background
- **EDL is a complete rendering specification** — every pixel position, dimension, font size, color, spring config
- **Remotion reads ALL values from EDL** — no hardcoded sizes, positions, or animations
- **19 content-driven jump cuts** (vs 8 before) — varied scales (1.0 to 1.5), 5+ transform origins
- **Product cards**: 700px wide, 320x320 product images, 72px grade badges — large enough to read
- **Shelf**: 100px thumbnails with dark background pill, grade labels
- **Enter/exit animations**: Spring configs (damping, stiffness) specified in EDL per layer
- **Winner pulse**: #1 product gets pulsing scale + enhanced glow

### V2c Changes from V2b
1. **Videographer v2** — complete rewrite, produces pixel-accurate rendering spec (not prose)
2. **EDL format v2** — `layers[]` array replaces `overlay_track`, each layer has full layout/content/animation specs
3. **EDLLayer.tsx** — generic layer renderer that reads ALL values from EDL JSON
4. **EDLShelf.tsx** — shelf renderer with EDL-specified dimensions, background pill, border radius
5. **Content-driven jump cuts** — emotional beats get TIGHT (1.35-1.4), product reveals get WIDE (1.0), re-engagement gets EXTRA TIGHT (1.5)
6. **Exit animations** — layers scale down + fade out before disappearing
7. **Minimum cut density** — at least 1 jump cut every 5 seconds (150 frames)
8. **Videographer skill** — `.claude/commands/video-editor.md` defines the complete EDL specification

---

## Pipeline Architecture (7 Steps)

```
1. SCRIPTWRITER → script JSON with segments, avatar config, visual overlays
2. COMPLIANCE CHECKER → scan for banned claims, structure/function language
3. PANEL REVIEWER → 10-expert panel, threshold 90+
4. AVATAR PRODUCER → HeyGen talking photo + Avatar IV → raw video
5. VIDEOGRAPHER → analyze script + captions → complete rendering spec (EDL v2)
6. COMPOSITOR → Remotion reads EDL → renders final MP4
7. QUALITY VERIFIER → extract frames → expert panel scoring → feedback loop
```

### Videographer Agent (Step 5)
- **Script**: `video/editing/videographer.py` (v2)
- **Skill**: `.claude/commands/video-editor.md`
- **Input**: script JSON + Whisper captions JSON
- **Output**: EDL v2 JSON with:
  - `avatar_track.jump_cuts` — content-driven framing with varied scales (1.0-1.7) and origins
  - `layers[]` — each layer has: `layout` (x, y, width, height, background, padding, border_radius), `content` (per-element font_size, color, font_family), `enter_animation` (spring damping/stiffness, from/to values), `exit_animation`, `winner_pulse`
  - `shelf_track` — thumbnail_size, gap, background, background_padding, grade_font_size, products[]
  - `caption_track` — font_size, highlight_color, stroke_width, combine_within_ms
  - `segment_timings` — Whisper-aligned boundaries
- **Key principle**: The videographer produces a COMPLETE rendering spec. Every value is a number/color/coordinate — no prose descriptions.

### V2b (archived) — Incomplete EDL
- EDL used string animation names ("slide_down_spring") — Remotion couldn't interpret
- No pixel dimensions for overlays — Remotion hardcoded tiny sizes (160x160 product images)
- Only 8 jump cuts with 2 scale values (1.0/1.2) — mechanical alternation
- 75% of EDL fields ignored by Remotion components

### V2 (archived) — Wrong Architecture
- Avatar at bottom 65%, overlays in separate zone above → everything tiny and disconnected
- Jump cuts used smooth 3-frame interpolation → not authentic

### V1 (archived) — First Prototype
- Sofia avatar, default voice, ~40% frame height, no jump cuts, no persistent products

---

## Lessons Learned

### Architecture (CRITICAL)
- **Avatar IS the background** — never push avatar to bottom and overlay above it
- **EDL must be a COMPLETE rendering specification** — every pixel, every font size, every spring config. If the EDL says "slide_down_spring" without numbers, Remotion has no way to execute it
- **Remotion components must READ the EDL** — no hardcoded values. The videographer decides sizes/positions, Remotion renders them
- **Jump cuts must be INSTANT** — frame N at one scale, frame N+1 at another. No transitions
- **Jump cuts must be content-driven** — tight on emotional beats, wide on product reveals, extra tight for pattern breaks. NOT mechanical alternation
- **Jump cuts need variety** — at least 3 different scale levels (1.0, 1.2, 1.4+), varied transform origins
- **Minimum 1 jump cut per 5 seconds** — prevents static dead zones
- **Product cards must be large** — 700px wide (65% of frame), 320px product images, 72px grade badges
- **Dark pills everywhere** — every overlay AND the shelf needs `rgba(0,0,0,0.4+)` background
- **Exit animations matter** — elements that just disappear look jarring

### HeyGen API
- **Talking photos preserve their background** — green screen may be ignored
- **Avatar IV motion prompts**: `custom_motion_prompt` field. Keep 1-2 clauses, positive only
- **Voice emotion**: `emotion` param (Excited, Friendly, Serious, Soothing, Broadcaster)
- **Credits**: ~45s video costs ~$5-8 with Avatar IV
- **File size**: 60MB+ for 70s video — extract audio before Whisper API (25MB limit)

### Remotion
- **Full-screen OffthreadVideo** with `objectFit: "cover"` and `objectPosition: "center top"`
- **Jump cuts**: Find last cut whose `frame <= currentFrame`, apply its scale. No interpolation
- **EDL-driven rendering**: All overlay properties come from EDL JSON — positions, sizes, colors, springs
- **Caption position**: `bottom: 220px` in 1920px frame
- **Radial vignette**: `radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.4) 100%)`

### Whisper Captions
- **OpenAI API preferred** over local whisper.cpp
- **25MB file limit** — extract audio to MP3 first (transcribe_api.py does this automatically)
- **Word-level timestamps**: `timestamp_granularities=["word"]` + `response_format="verbose_json"`
- **Caption format**: `{text, startMs, endMs, timestampMs, confidence}`

---

## HeyGen API Reference

### Avatar IV Motion Prompts
- **Endpoint**: `/v2/video/generate` with `use_avatar_iv_model: true`
- **Prompt formula**: [Body part] + [Action] + [Emotion/intensity]
- **Examples**: "Gestures naturally while speaking, warm smile"

### Voice Controls
| Parameter | Range | Notes |
|-----------|-------|-------|
| `emotion` | Excited, Friendly, Serious, Soothing, Broadcaster | Only on emotion-compatible voices |
| `speed` | 0.5 – 1.5 | Default: 1.0 |
| `pitch` | -50 to 50 | Default: 0 |

---

## Key Avatars
| Name | talking_photo_id | Voice | Notes |
|------|-----------------|-------|-------|
| Kate | `1c4f0c7552604526bf5f9a49822c3660` | Bella Friendly `628161fd1c79432d853b610e84dbc7a4` | Current primary |
| Sofia | See `sofia_avatar_config.json` | Default `20776652f64a458a8582705f4f2074d4` | 19 looks, retired |

## Kling AI (B-Roll / Text-to-Video)
- **API**: `https://api.klingai.com/v1`, JWT auth (HS256)
- **ALWAYS use `kling-v3`** — latest model, required. Never use v1/v2 (poor motion quality)
- **Modes**: `std` (standard), `pro` (higher quality)
- **Durations**: 5s, 10s (up to 15s on v3)
- **Script**: `video/kling/test_kling.py`
- **Output**: `video/output/kling/`
- **Keys**: `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` in `.env`

## File Locations
| File | Purpose |
|------|---------|
| `video/scripts/tier_list_magnesium_v2.json` | Current script (Kate, Bella, Avatar IV) |
| `video/editing/videographer.py` | Videographer agent v2 — produces complete rendering spec |
| `.claude/commands/video-editor.md` | Videographer skill — EDL format reference |
| `video/remotion-video/public/edl.json` | Current EDL v2 (pixel-accurate rendering spec) |
| `video/heygen/generate_avatar.py` | HeyGen API integration |
| `video/captions/transcribe_api.py` | OpenAI Whisper API transcription |
| `video/remotion-video/src/TierList/` | Remotion TierList composition |
| `video/remotion-video/src/TierList/ChromaKey.tsx` | FullScreenAvatar — full-frame video with instant jump cuts |
| `video/remotion-video/src/TierList/EDLLayer.tsx` | Generic EDL-driven layer renderer (reads all values from EDL) |
| `video/remotion-video/src/TierList/EDLShelf.tsx` | EDL-driven product shelf with background pill |
| `video/remotion-video/src/TierList/TierCard.tsx` | Legacy product card (replaced by EDLLayer) |
| `video/remotion-video/src/TierList/HookOverlay.tsx` | Legacy overlays (replaced by EDLLayer) |
| `video/remotion-video/src/TierList/RankedProductsBar.tsx` | Legacy shelf (replaced by EDLShelf) |
| `video/remotion-video/src/TierList/index.tsx` | Main composition — EDL v2 driven |
| `video/output/heygen/` | Raw avatar videos from HeyGen |
| `video/output/final/` | Rendered composite videos |
