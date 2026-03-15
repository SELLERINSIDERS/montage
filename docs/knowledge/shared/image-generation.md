---
domain: shared
updated: 2026-03-08
tags: [nano-banana, gemini, image-generation]
---

# Image Generation — Nano Banana Pro (Gemini)

## Model & Config
- **Model**: `gemini-3-pro-image-preview`
- **SDK**: `google-genai`
- **Key**: `.env` → `GEMINI_API_KEY`
- **Aspect**: 4:5 for feed (do NOT use `image_size` param — unsupported in SDK v1.47.0)

## Required Params
- 120s signal timeout
- Flush prints (for real-time output in scripts)
- 5s rate limit delays between calls
- 3 retries on failure

## SO WHAT Test
Every visual must answer: "Why would someone scrolling at 10PM stop and click?"

## What Works
- Phone screenshots (iMessage, Reddit, search results)
- Reddit-style UGC (community posts, upvotes)
- Financial documents (receipts, invoices, bank statements)
- Macro photography (ingredients, textures)
- Data comparisons (charts, rankings, tables)

## What Fails
- Abstract science (generic lab imagery)
- Academic citations (journal paper look)
- Price trivia (cost breakdowns)
- Messy photos without a clear click reason

## Agent Team (for Meta ad visuals)
prompt-creator → prompt-verifier → image-generator (see `/project:visual-ad-team`)

## 2K Production Quality
- **Model**: `gemini-3.1-flash-image-preview` with `image_size="2K"` param
- **Workers**: `MAX_WORKERS = 1` — MANDATORY. Concurrent 2K requests deadlock
- **Timing**: 3-4 minutes per image, 5-7 MB output per image
- **Timeout**: 300s (5 min) signal timeout for 2K
- **Script**: `scripts/visuals/generate_vsl_cleopatra_2k.py`

## Pose Control
- AI misinterprets complex body poses (e.g., "sitting on toilet" → person facing toilet)
- **Fix**: Add explicit in-prompt negatives: "They are NOT standing. They are NOT facing the toilet. They are SITTING." with geometry: "knees bent at 90 degrees, shins vertical, feet directly below knees"
- May need 2-3 regeneration attempts for complex poses

## Multi-Version Prompt Tracking
- When user selects images across versions (V5/V6), map each selection back to its source prompt script
- For 2K upscale: use the EXACT original prompt — never a rewritten version
- Director's 8-Step rewrite produces minimal visual difference vs well-crafted originals — only rewrite prompts that clearly need improvement

## Output
- **Ad visuals**: `images/blog_ads_v2/`, naming: `ad_XX_short_name.png`
- **VSL scenes**: `images/vsl_cleopatra_v{N}/`, `images/vsl_cleopatra_2k/` (final production)
- **Scripts**: `scripts/visuals/generate_blog_ad_visuals_v4.py` (latest ads), `scripts/visuals/generate_vsl_cleopatra_2k.py` (latest VSL)
