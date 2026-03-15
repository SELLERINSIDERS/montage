---
domain: video-production
updated: 2026-03-12
tags: [kling, video-generation, api, useapi, proxy]
---

# Kling AI — Video Generation

## DEFAULT: UseAPI.net Proxy (Production Path)

**ALWAYS use the proxy for production.** Set `KLING_USE_PROXY=true` in `.env`.

| | UseAPI.net Proxy (DEFAULT) | Direct Kling API (fallback only) |
|---|---|---|
| Env var | `KLING_USE_PROXY=true` | `KLING_USE_PROXY=false` |
| Auth key | `USEAPI_KEY` | `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` |
| Base URL | `https://api.useapi.net/v1/kling` | `https://api.klingai.com/v1` |
| Model | `kling-v3-0` (= kling-v3-omni) | `kling-v3` |
| Audio | `enable_audio: true` (embedded in clip) | Not supported — silent output |
| Image input | Upload to `/assets` → get URL → reference URL | Raw base64 in request body |
| Endpoint | `/videos/image2video-frames` | `/videos/image2video` |
| Task poll | `/tasks/{task_id}` | `/videos/image2video/{task_id}` |

**Why proxy?** `kling-v3-omni` (audio generation) is only available via proxy APIs. The direct API silently ignores `generate_audio: true` and returns no audio track. Proxy uses our Kling subscription (not API credits).

## Model

- **Default: `kling-v3-omni`** — accessed as `kling-v3-0` on UseAPI.net. Produces video WITH embedded audio.
- `kling-v3-omni` NOT available on direct API — returns "model is not supported" (code 1201)
- Fallback: `kling-v3` on direct API (no audio, requires API credits)
- Element referencing: NOT available on direct API (404). On proxy: available but not currently used — character consistency handled at image generation step using anchor blocks.

## Audio (Proxy Only)

- `enable_audio: true` in request payload → audio embedded in output clip
- Audio is derived from the video prompt — no separate audio field
- **Audio prompt pattern**: Append `[Audio: {description}]` to the video prompt. Example:
  `"Zoom in toward the eye. Pupil dilates slowly... [Audio: cold room silence, faint ticking clock, distant traffic hum]"`
- Audio producer agent writes `audio_prompts.json` per project → merged into video prompts before manifest build
- `add_sound()` method: post-process audio fallback for clips generated without audio (proxy-only)
- `download_audio()`: extract audio track as MP3 for Remotion independent volume control

## Standard Params

- `cfg_scale: 0.4` — ALWAYS
- Always include `negative_prompt`
- **Modes**: `std` for testing, `pro` for production batches
- **Durations**: 5s, 10s. Minimum is 5s — trim shorter scenes in post
- **Aspect ratios**: 9:16, 16:9, 1:1

## Image Constraints

- **Size limit**: 10MB max. If over, use `PIL Image.save(optimize=True)` — typically cuts 40-50% (e.g., 10.7→6.2MB)
- **Proxy format**: Upload PNG to `/assets` endpoint first (accepts `data:image/png;base64,...` format), get CDN URL back, reference URL in generation payload
- **Direct format**: RAW base64 (no `data:image/...;base64,` prefix). Convert RGBA→RGB PNG first

## Start + End Frame (image_tail)

- **Parameter**: `image_tail` — transitions from start frame to end frame in one clip
- Works on both proxy and direct API
- Processing time: ~120s in std mode
- Duration auto-set to 10s for dual-frame clips

## Client Code

- **Unified client**: `video/kling/api_client.py` — `KlingClient` class handles both backends
- `KLING_USE_PROXY=true` → proxy path. `false` or unset → direct API
- `batch_generate_concurrent.py` — 3 workers, resume, dry-run (uses api_client.py)
- `batch_generate.py` — sequential fallback

## Content Filter

- "Failure to pass the risk control system" — triggers on bath/nudity-adjacent scenes
- Retry usually works. If persistent, soften prompt language

## Production Benchmarks (Mar 2026)

- pro mode: ~100-250s per 5s clip, 4.5-27MB per clip (avg ~11MB)
- 11 clips: 3 workers, ~10 min, 11/11 success, zero rate limit issues
- 51 clips: 3 workers, ~42 min, 51/51 success (1 content filter retry)
- 86 clips: 3 workers hit 429 rate limits at ~scene 74. First pass: 74/86. Required retries with cooldown
- **Rate limit strategy**: Under 50 clips → 3 workers, no issues. 50-70 clips → 3 workers, monitor. 70+ clips → switch to 1 worker after scene 70. If 429 errors, wait 10 min (5 min NOT enough) then retry sequential

## Workflow Hard Rules (learned Mar 2026)

1. **Use proxy by default** — `KLING_USE_PROXY=true` in `.env`. Never use direct API for production.
2. **1:1 Image-Video Parity**: Every image prompt MUST have exactly 1 Kling video prompt. Count both — they must match
3. **Video prompt matches ACTUAL image**: Describe motion for what's IN the generated image, NOT the original script
4. **Camera param matches video prompt**: KLING PARAMS camera value and described motion must agree
5. **Include all image elements**: If image has handmaidens, people walking, specific actions — reference them
6. **Sub-scenes count separately**: Scene 14A-D = 4 images, 4 video prompts, 4 Kling API calls
7. **Reuse shots**: Can reuse an image with a DIFFERENT video prompt — counts as 0 new images but 1 video prompt
8. **Parity check mandatory**: After writing all prompts, count images vs video prompts — include in notes
9. **Audio prompts required for proxy**: Write `audio_prompts.json` before manifest build. Merge into video prompts via `[Audio: ...]` pattern.

## Cinematic Prompt Standards

- Source of truth: Cinematic Director Section 12 + Video Prompting Guide "Cinematic Standards"
- Every prompt needs: camera match + visible motion + atmosphere + technical grammar + 30-60 words
- Static camera ≤25% of total scenes — diversify across pan, dolly, zoom, tilt, crane, orbit
- Speed modifiers: "slow" ~10% (CTA/peaks), "quick" ~10% (hooks/montages), natural ~80%
- Atmosphere library in video-prompting-guide.md organized by scene type
- **Motion intent rule**: Always describe WHY something moves, not just WHAT. Kling interprets motion literally — attach emotional context
