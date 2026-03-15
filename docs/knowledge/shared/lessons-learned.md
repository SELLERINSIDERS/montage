---
domain: shared
updated: 2026-03-08
tags: [lessons, gotchas, debugging]
---

# Lessons Learned — Hard-Won Gotchas

## Meta Ads

### CBO Phase Failure (Feb 8-17)
- $953 spent, 1 purchase — CBO concentrated 54% of budget on one ad with 0 purchases
- 14 new ads got ZERO impressions — CBO starves new creatives
- **Lesson**: ABO for testing (equal budget per ad set), CBO for scaling winners only

### Dynamic Creative / AFS Trap
- `is_dynamic_creative` is IMMUTABLE after ad set creation
- `asset_feed_spec` ALWAYS triggers `is_dynamic_creative` — even with optimization_type REGULAR
- Cannot add multiple texts via API without dynamic creative
- **Lesson**: Standard creatives only. No two-phase approach. Extra text variants added manually in Ads Manager

### ATC Optimization
- ATC optimization campaign had zero-spend delivery issues
- Switched to Purchase optimization from day 1

### Token & Image Hashes
- Image hashes tied to token session — re-upload ALL images after token refresh
- Token: 60-day long-lived, must be exchanged before expiry

## Video Production

### Kling API
- `kling-v3-omni` NOT available on direct API (error 1201) — only use `kling-v3`
- `generate_audio: true` silently ignored — no audio in output despite accepted param
- Element referencing returns 404 — solve character consistency at image generation step
- Content filter ("risk control system" error) — retry usually works, soften language if persistent

### Remotion
- ALWAYS get exact width/height/fps from `ffprobe` — NEVER hardcode dimensions
- Dimensions vary between Kling clips; hardcoding breaks rendering
- **PascalCase↔snake_case ID mismatch**: audioDesigns.ts uses `scene_01` (snake_case), sceneManifest.ts uses `Scene01OpeningShot` (PascalCase). Any script matching between the two must convert formats: `re.match(r'Scene(\d+)', comp_id)` then `f"scene_{num.zfill(2)}"`. A naive `re.match(r'scene_\d+', comp_id)` will silently fail on PascalCase IDs.
- **Post-render SILENT verification**: After batch render, always verify SILENT scenes are exact copies (same file size as original). Remotion re-encoding adds a silent aac track that changes the file size — a "successful" render of a SILENT scene is actually a failure.

### Audio Sources
- Mixkit has dynamic download URLs that break over time
- Use orangefreesounds.com (CC BY-NC 4.0) or freesoundslibrary.com (CC BY 4.0) instead

### Kling — Video Motion Prompts
- **Describe emotion/intent, not just mechanics**: "foot tapping impatiently" → interpreted as enjoying music. "Legs shift uncomfortably, knees press together with visible tension" → reads as discomfort. Always state WHY motion happens, not just WHAT moves
- **11 clips at 3 workers**: Completed in ~10 min, zero rate limit issues. Rate limit problems only surface at 60+ clips

### Kling — SFX Overlay via ffmpeg
- Can apply SFX directly to Kling clips using ffmpeg (`-c:v copy` preserves video, overlay audio as AAC). Much faster than Remotion for per-clip SFX iteration
- **Re-applying SFX**: Must strip audio first (`ffmpeg -an`) before overlaying new layers on clips that already have baked-in audio
- Utility scripts: `scripts/apply_sfx_to_clips.py` (batch), `scripts/reapply_sfx_single.py` (single clip)

### Image Generation — 2K Quality
- **Sequential workers mandatory**: `MAX_WORKERS = 1` for 2K generation — concurrent requests deadlock at 2K resolution
- Each 2K image takes 3-4 minutes, outputs 5-7 MB per image
- Model for 2K: `gemini-3.1-flash-image-preview` with `image_size="2K"` param

### Image Generation — Pose Control
- AI consistently misinterprets complex poses (e.g., "sitting on toilet" → generated person facing toilet instead)
- **Fix**: Add explicit negatives IN the prompt itself — "They are NOT standing. They are NOT facing the toilet. They are SITTING." with specific body geometry: "knees bent at 90 degrees, shins vertical, feet directly below knees"
- May still require 2-3 regeneration attempts for complex body positioning
- **Recurrence (NightCap VSL Scene 03, March 2026)**: Woman standing at sink instead of seated at vanity — same failure mode, same fix applies. This lesson is only effective if applied at prompt-WRITE time, not after generation fails. Add a pose review pass to the pre-generation checklist: scan all prompts for non-standing subjects and enforce explicit negatives + body geometry before running the batch.

### Image Generation — Prompt Versioning
- When user selects images across multiple generation versions (V5/V6), track WHICH prompt came from WHICH source script
- For 2K upscale: must use the EXACT prompt that produced the approved 1K image — not a rewritten version
- Director's 8-Step Protocol rewrite (V6) produces minimal visual difference vs well-crafted V5 prompts — save the rewrite step for prompts that clearly need improvement

### ElevenLabs
- Voice speed varies by voice — Jessica/Hope are naturally slow even at high speed settings
- NO SSML support in v3 model — use audio tags like `[pause]`, `[calm]` instead

### Remotion — Post-Production Assembly (my-short-ad, March 2026)

**Whisper format mismatch**: `transcribe_api.py` produces `@remotion/captions` flat array format. `CaptionLayer` expects Whisper segments format `{segments: [{words: []}]}`. Convert with a one-time script → save as `whisper_segments.json`. The `handoff-voiceover.json` `whisper_data` field should point to the segments file, not the raw transcription output.

**Broken public/vsl symlink**: `video/remotion-video/public/vsl` was a symlink pointing to a deleted path from a prior project. Remotion's bundler silently fails on broken symlinks — remove them before render. Add cleanup step to post-production agent: `find video/remotion-video/public -xtype l -delete` before every render.

**Remotion bundler doesn't follow symlinks**: Clips and audio at project paths (e.g., `ads/my-short-ad/video/clips/`) must be **copied** (not symlinked) into `video/remotion-video/public/` so the bundler can include them. Copy as real files. Automate this in the post-production agent's `prepare_assets` step.

**Clip path convention in vsl_manifest.json**: The `clip_src` field must match the path as seen from `video/remotion-video/public/` (what `staticFile()` resolves). If clips are copied to `video/remotion-video/public/ads/my-short-ad/clips/`, then `clip_src` = `"ads/my-short-ad/clips/scene_01.mp4"`. The original project path (`ads/my-short-ad/video/clips/`) is different — don't confuse them.

**Captions linger during pauses**: `createTikTokStyleCaptions` sets `page.durationMs` to extend past the last spoken word (gap-fill). The page stays visible through post-word silence. Fix: after finding `currentPage`, check `currentMs > lastToken.toMs` and return `null` early. Subtitles now disappear the instant the last word ends. This is in `CaptionLayer.tsx`.

**`vsl_manifest.json` does NOT drive the Remotion render**: Props are hardcoded in `Root.tsx` `defaultProps`. Changing `vsl_manifest.json` has zero effect on the render output. All prop changes (caption_preset, scene durations, voiceover path, etc.) must be made directly in `Root.tsx`. The manifest is documentation only.

### Remotion — Captions (TikTok Style)

**Font size too small**: Default 48-72px on a 1924px tall video is barely visible. Use 80-110px for short-form ads. Scale: font should be ~4.5-6% of frame height.

**`-webkit-text-stroke` unreliable in Remotion headless Chrome**: Use 8-directional `textShadow` for stroke effect instead:
`"-3px -3px 0 #000, 3px -3px 0 #000, -3px 3px 0 #000, 3px 3px 0 #000, -3px 0 0 #000, 3px 0 0 #000, 0 -3px 0 #000, 0 3px 0 #000"`
This renders consistently and looks identical to a stroke.

**Real TikTok caption style = bg_pill, not color change**: Changing active word color (white → green) is barely noticeable. Use `highlightMode: "bg_pill"` with `activeBgColor: "#FFFC00"` and `activeColor: "#000000"`. Yellow box + black text on active word = immediate visual pop. Non-active words stay white with shadow outline. `CaptionPresets.ts` and `CaptionLayer.tsx` already support this via `highlightMode` field.

**Caption preset selection by brand type**: Match the preset to the product category:
- `tiktok_bold` — energy, hype, fitness, gaming (yellow pill, Montserrat, aggressive)
- `wellness_soft` — supplements, sleep, calm, recovery (Poppins SemiBold, soft shadow, warm cream active, no pill). **Use this for wellness/supplement products.**
- `clean_minimal` — general purpose, info content
- `cinematic_subtle` — historical/cinematic VSLs

**wellness_soft preset** (added March 2026): Poppins SemiBold 60-78px, white text, multi-layer soft drop shadow, warm cream active highlight `#F5D87E`, fade-in animation, `combineTokensMs: 1000`. Font file: `public/fonts/Poppins-SemiBold.woff2` (Google Fonts v24).

**Subtitle casing**: Whisper capitalizes the first word of each sentence. For wellness/supplement ads, use `textTransform: "lowercase"` on the preset — subtitles should feel conversational and uniform, not like formal sentences. `CaptionLayer.tsx` handles `"uppercase"`, `"lowercase"`, and `"none"`.

**Inconsistent subtitle font sizes**: `fitText` from `@remotion/layout-utils` calculates a dynamic font size per caption page based on text length — short pages (1-2 words) render larger than long pages (4-5 words), making the ad feel choppy. Fix: remove `fitText` entirely and always use `preset.fontSize.max` as a fixed size. `createTikTokStyleCaptions` handles line-breaking so overflow is not a concern. This was implemented in `CaptionLayer.tsx` — `fitText` import removed.
