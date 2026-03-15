# Generate Images with Nano Banana at Scale

Generate images using Nano Banana (Google Gemini Image models) with concurrent execution, resume capability, and batch processing.

## FEEDBACK LOOP (mandatory)
BEFORE starting: Run `supa-search-cc "image generation pose lighting composition style production feedback" --table learnings --limit 8`, plus REST filter `category=eq.video-feedback`. Inject results as "PAST FEEDBACK" block before writing any image prompts.
AFTER any user rejection or correction to a generated image (pose wrong, lighting off, composition, style): capture to `learnings` table with `stage: "imagegen-v1"` or `"imagegen-v2"`.
Full protocol: Load the `feedback-loop` skill from your configured skills directory.

---

## STEP 0: Check for Existing Scripts FIRST (MANDATORY)

**Before writing ANY new script**, ALWAYS check `scripts/visuals/` for existing generation scripts:

```
Glob: scripts/visuals/generate_*.py
```

### If a matching script exists:
1. **Tell the user** which scripts are available (name + what they generate)
2. **Ask if they want to run an existing script** or create a new one
3. **If running existing**: just execute `python scripts/visuals/<script>.py` — it has resume capability (skips images >100KB, re-generates deleted ones)
4. **To regenerate specific images**: delete the target files from the output folder, then re-run the same script

### If the user provides a NEW prompts file (e.g., a new `docs/*.md` with image prompts):
1. Check if a script already exists for that prompt file
2. If not, THEN write a new script following the Batch Generation Script Template below
3. Save it to `scripts/visuals/generate_<project_name>.py` so it's reusable next time

### Existing Scripts Registry

| Script | Prompts Source | Output Folder | Images |
|--------|---------------|---------------|--------|
| `generate_vsl_scenes_v2.py` | VSL scenes V1 | `images/vsl_scenes/` | 48 scenes |
| `generate_blog_ad_visuals_v4.py` | `prompts/prompts_v4.md` | `images/blog_ads_v2/` | 10 ads |

**NEVER rewrite a script that already exists unless the prompts have changed.**

---

## Available Models

| Model | ID | Speed | Quality | Best For |
|-------|----|-------|---------|----------|
| **Nano Banana 2** | `gemini-3.1-flash-image-preview` | Fast (~15-30s at 1K) | Great | Batch generation, VSL scenes, rapid iteration |
| **Nano Banana Pro** | `gemini-3-pro-image-preview` | Slower (~30-60s) | Higher | Hero images, final ad creatives |

**Default to Nano Banana 2** for batch/scale work. Use Pro only when maximum quality matters on a small set.

## SDK & Auth

- **SDK**: `google-genai` (v1.65.0+) — `pip install google-genai`
- **API Key**: `.env` → `GEMINI_API_KEY`
- **Client**: `from google import genai; client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])`

## Core Generation Pattern

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

response = client.models.generate_content(
    model="gemini-3.1-flash-image-preview",  # or gemini-3-pro-image-preview
    contents=[prompt_text],
    config=types.GenerateContentConfig(
        response_modalities=["IMAGE"],  # IMAGE only — not ["TEXT", "IMAGE"]
        image_config=types.ImageConfig(
            aspect_ratio="4:5",   # see Aspect Ratios below
            image_size="1K",      # see Resolutions below
        ),
    ),
)

# Extract image — SDK returns RAW BYTES (not base64)
if response.candidates and response.candidates[0].content.parts:
    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.mime_type.startswith("image/"):
            image_data = part.inline_data.data  # raw PNG bytes
            filepath.write_bytes(image_data)
```

### CRITICAL: Raw Bytes, Not Base64

The SDK returns **raw PNG bytes** in `part.inline_data.data`. Do NOT `base64.b64decode()` — that produces corrupt 95-byte files. Write the bytes directly:

```python
# CORRECT
image_data = part.inline_data.data
filepath.write_bytes(image_data)

# WRONG — produces corrupt files
import base64
image_data = base64.b64decode(part.inline_data.data)  # ← NEVER DO THIS
```

## Resolutions

| Size | Time per Image | Concurrent Workers | Notes |
|------|---------------|-------------------|-------|
| `"1K"` | ~15-30s | 5 workers OK | **Recommended for batch generation** |
| `"2K"` | ~3-4 min | 1 worker ONLY | Deadlocks with concurrent requests. Use only for hero shots |
| `"512px"` | ~10s | 5+ workers OK | Drafts/previews only |
| `"4K"` | Very slow | 1 worker ONLY | Untested at scale, use sparingly |

**Rule: Use `"1K"` for any batch of 5+ images.** 2K+ hangs or deadlocks with concurrent workers.

## Aspect Ratios

| Ratio | Use Case |
|-------|----------|
| `"4:5"` | Meta feed ads (1080×1350) — **default for ads** |
| `"9:16"` | Stories / VSL scenes (1080×1920) |
| `"16:9"` | Landscape / YouTube thumbnails |
| `"1:1"` | Square format |
| `"3:4"`, `"4:3"`, `"2:3"`, `"3:2"`, `"5:4"`, `"21:9"` | Also supported |

## Batch Generation Script Template

This is the proven pattern from `scripts/visuals/generate_vsl_scenes_v2.py` (48 images, 0 failures).

```python
#!/usr/bin/env python3
"""
Batch Image Generation — [PROJECT NAME]
========================================
Model: gemini-3.1-flash-image-preview (Nano Banana 2)
Resolution: 1K | Aspect: 4:5
"""

import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types

# ─── CONFIG ──────────────────────────────────────────────────────────────
MODEL = "gemini-3.1-flash-image-preview"
IMAGE_SIZE = "1K"
ASPECT_RATIO = "4:5"
OUTPUT_DIR = Path("images/output_folder")
MAX_WORKERS = 5        # concurrent threads — 1K handles 5 fine
RETRY_COUNT = 3        # retries per image on failure
RATE_LIMIT_DELAY = 3   # seconds between batch submissions
SIGNAL_TIMEOUT = 120   # seconds max per generation call

# ─── CLIENT ──────────────────────────────────────────────────────────────
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# ─── PROMPTS ─────────────────────────────────────────────────────────────
# Each entry: { "id": "scene_01", "name": "short_name", "prompt": "..." }
SCENES = [
    {
        "id": "scene_01",
        "name": "descriptive_name",
        "prompt": """Your detailed image prompt here...""",
    },
    # ... more scenes
]

# ─── GENERATOR ───────────────────────────────────────────────────────────
def generate_image(scene):
    """Generate a single image with retries and skip logic."""
    scene_id = scene["id"]
    filename = f"{scene_id}_{scene['name']}.png"
    filepath = OUTPUT_DIR / filename

    # Resume capability — skip valid existing images (>100KB)
    if filepath.exists() and filepath.stat().st_size > 100_000:
        print(f"  [SKIP] {filename} — already exists ({filepath.stat().st_size:,} bytes)", flush=True)
        return {"scene": scene_id, "status": "skipped", "file": str(filepath)}

    for attempt in range(1, RETRY_COUNT + 1):
        try:
            print(f"  [{scene_id}] Attempt {attempt}/{RETRY_COUNT} — generating...", flush=True)

            response = client.models.generate_content(
                model=MODEL,
                contents=[scene["prompt"]],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio=ASPECT_RATIO,
                        image_size=IMAGE_SIZE,
                    ),
                ),
            )

            # Extract image — raw bytes, not base64
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                        image_data = part.inline_data.data
                        filepath.write_bytes(image_data)
                        size_kb = len(image_data) / 1024
                        print(f"  [{scene_id}] SUCCESS — {filename} ({size_kb:.0f} KB)", flush=True)
                        return {"scene": scene_id, "status": "success", "file": str(filepath), "size": len(image_data)}

            print(f"  [{scene_id}] WARNING — no image in response (attempt {attempt})", flush=True)
            if attempt < RETRY_COUNT:
                time.sleep(RATE_LIMIT_DELAY * 2)

        except Exception as e:
            print(f"  [{scene_id}] ERROR — {str(e)[:120]} (attempt {attempt})", flush=True)
            if attempt < RETRY_COUNT:
                time.sleep(10 * attempt)  # exponential backoff

    return {"scene": scene_id, "status": "failed", "file": None}

# ─── MAIN ────────────────────────────────────────────────────────────────
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total = len(SCENES)

    print(f"\n{'='*60}", flush=True)
    print(f"  Model: {MODEL}", flush=True)
    print(f"  Resolution: {IMAGE_SIZE} | Aspect: {ASPECT_RATIO}", flush=True)
    print(f"  Output: {OUTPUT_DIR}", flush=True)
    print(f"  Scenes: {total} | Workers: {MAX_WORKERS}", flush=True)
    print(f"{'='*60}\n", flush=True)

    results = {"success": [], "failed": [], "skipped": []}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for i, scene in enumerate(SCENES):
            future = executor.submit(generate_image, scene)
            futures[future] = scene
            # Stagger submissions to avoid burst rate limits
            if i > 0 and i % MAX_WORKERS == 0:
                time.sleep(RATE_LIMIT_DELAY)

        for future in as_completed(futures):
            scene = futures[future]
            try:
                result = future.result(timeout=SIGNAL_TIMEOUT)
                results[result["status"]].append(result)
            except Exception as e:
                print(f"  [{scene['id']}] FATAL — {e}", flush=True)
                results["failed"].append({"scene": scene["id"], "status": "failed"})

    # Summary
    print(f"\n{'='*60}", flush=True)
    print(f"  COMPLETE — Success: {len(results['success'])} | Skipped: {len(results['skipped'])} | Failed: {len(results['failed'])}", flush=True)
    if results["failed"]:
        print(f"  FAILED: {', '.join(r['scene'] for r in results['failed'])}", flush=True)
    if results["success"]:
        total_mb = sum(r.get("size", 0) for r in results["success"]) / (1024*1024)
        print(f"  Generated: {total_mb:.1f} MB", flush=True)
    print(f"  Output: {OUTPUT_DIR}", flush=True)
    print(f"{'='*60}\n", flush=True)

if __name__ == "__main__":
    main()
```

## Key Rules

### Always Do
1. **`flush=True` on every print** — Python buffers stdout when not in a terminal
2. **`response_modalities=["IMAGE"]`** — not `["TEXT", "IMAGE"]` for pure image generation
3. **Skip threshold > 100KB** — corrupt images are tiny (~95 bytes), valid images are 1-2MB
4. **Stagger concurrent submissions** — sleep `RATE_LIMIT_DELAY` every `MAX_WORKERS` submissions
5. **Exponential backoff on retries** — `time.sleep(10 * attempt)` between retries
6. **`load_dotenv()` at top** — before importing genai (needs `GEMINI_API_KEY`)

### Never Do
1. **Never `base64.b64decode()`** the SDK response — it's already raw bytes
2. **Never use 2K+ with concurrent workers** — deadlocks the API
3. **Never set `image_size` with Nano Banana Pro** (old `gemini-3-pro-image-preview`) — only Nano Banana 2 supports it
4. **Never skip the stagger delay** — burst requests trigger rate limits

## Epic Scale & People Avoidance

### Default to EPIC
Every image prompt should default to the MOST EPIC visualization possible. Think $100M Hollywood movie, not stock photography. Before writing any prompt, ask: "What's the most breathtaking, never-before-seen way to show this?"

**Scale Hierarchy** (default to highest that fits):
1. **COSMIC** — celestial, astronomical, impossible scale
2. **BIO-CINEMATIC** — inside the body, microscopic worlds made epic
3. **MYTHOLOGICAL** — hundreds of people, civilizations, empires
4. **ENVIRONMENTAL** — epic landscapes, natural forces
5. **METAPHORICAL** — abstract concepts as physical spectacles
6. **FIRST-PERSON POV** — camera IS the viewer's eyes (our hands, our view)
7. **INTIMATE** — close human moment (ONLY when emotionally earned)

### Not Every Scene Needs a Person
AI generators default to putting hands and people in every frame. FIGHT THIS. Before adding a person, ask: "Does the script literally describe a person? Or did I default to a person because I couldn't think of anything better?"

**Scenes that should NEVER have a person:**
- Scientific concepts → bio-cinematic visualization
- Time passing → cosmic/environmental
- Statistics → can have people but at MASSIVE scale (hundreds), not 1-2
- Trust/quality signals → metaphorical objects (golden scales, not lab gloves)
- Calm/peace → first-person POV (our hands on a book) or environment (candle flame)

### Consecutive People Rule
**Never more than 3 scenes in a row featuring people.** After every 3rd person-scene, insert a non-person break:
- Epic/environmental shot
- Bio-cinematic inside-the-body
- First-person POV (our hands, our perspective)
- Macro object (candle flame, golden scale, product)
- Metaphorical visualization

### First-Person POV Technique
When you need intimacy WITHOUT showing a person:
- Camera IS the viewer's eyes
- Show OUR hands, OUR perspective
- Examples: our hands holding a book, our hand on a mirror, our hand putting a phone down
- Creates personal connection without another person-face-shot

### Repetition Tracking
Track visual types across sequences. Max 2 of the same type per 20-scene window:
- Mineral/crystal close-ups
- Product bottle shots
- Face close-ups
- Single-person-standing-or-sitting shots
- Underwater/water scenes
- Lab/science imagery

**Gold standard examples**:
- Bio-cinematic intestinal villi absorbing golden particles (supplement absorption scene)
- Cosmic moon phases arcing across a night sky (passage of time)

## Naming Convention

```
{id}_{descriptive_name}.png
```

Examples:
- `scene_01_character_portrait.png` — VSL scenes
- `scene_14a_achievement_throne.png` — Sub-scenes with letter suffix
- `ad_01_recovery_gap.png` — Ad creatives
- `hero_01_product_shot.png` — Product images

The `id` field maps directly to the source prompt document for traceability.

## Performance Benchmarks (Tested Mar 2026)

| Setup | Throughput | Notes |
|-------|-----------|-------|
| 1K, 5 workers | ~10 images/min | **Best for batch** — 48 images in ~5 min |
| 1K, 1 worker | ~2 images/min | Safe fallback if rate limited |
| 2K, 1 worker | ~0.25 images/min | Hero shots only |

## Reference Scripts

| Script | What It Does |
|--------|-------------|
| `scripts/visuals/generate_vsl_scenes_v2.py` | 48 VSL scenes, 5 workers, 1K 4:5 — proven at scale (0 failures) |
| `scripts/visuals/generate_blog_ad_visuals_v4.py` | 10 blog ad images, sequential, Pro model |

## The 7-Element Image Prompt Formula

Every image prompt should include these 7 elements in this order for maximum quality and consistency:

```
1. [Subject + emotion]    — who/what + how they feel (the eye finds this first)
2. [Action/pose]          — what they're doing, body language
3. [Environment]          — where, with specific details (not generic)
4. [Lighting]             — named technique + direction + quality
5. [Camera + lens]        — shot size + angle + lens mm + aperture
6. [Style anchors]        — cinematic, ultra-photorealistic, 35mm film aesthetic
7. [Aspect ratio + meta]  — 4:5/9:16, "no text overlays", composition notes
```

**Example**:
```
A striking Egyptian queen in her late twenties with olive Mediterranean skin,     [1. Subject + emotion]
lifting a glowing mineral crystal from dark water,                                 [2. Action]
at the Dead Sea shoreline at golden hour,                                          [3. Environment]
warm torchlight from left with golden sunset backlight rim,                        [4. Lighting]
close-up, 85mm f/1.8, shallow DOF focused on hands and crystal,                  [5. Camera + lens]
cinematic, ultra-photorealistic, 35mm film aesthetic, 8K,                         [6. Style anchors]
4:5 vertical, ultra-clean composition, ad-grade, no text overlays                 [7. Aspect ratio + meta]
```

### Style Keyword Notes
- **Use "35mm film aesthetic"** — activates cinematic color response and depth
- **Avoid "film grain"** — modern generators (Gemini/Nano Banana) handle grain poorly, creates artifacts
- **Avoid keyword soup** — "beautiful, stunning, masterpiece, trending on artstation" is noise
- **One dominant style per prompt** — don't mix "watercolor" with "photorealistic"

### Photorealism Complexity Check (Before Writing Any Prompt)

AI generators break realism at 4+ detailed people in sharp focus. Before writing a prompt, count subjects and adjust element #5 (Camera + lens):

| Subjects | Tier | Camera + Lens (Element #5) |
|---|---|---|
| 0 (landscape/object) | ENVIRONMENTAL | 24mm f/4.0–f/8.0, wide/aerial, deep DOF |
| 1 (single person/animal) | SOLO | 85mm f/1.8–f/2.8, CU to medium, profile preferred |
| 2–3 | ENSEMBLE | 50mm f/2.0–f/2.8, 1 primary sharp, others softer |
| 4–10 | CROWD-REDUCED | Reduce to 2–3 foreground sharp, rest blurred. 85mm f/1.8 |
| 10+ (armies, crowds) | EPIC-REDUCED | Aerial 24mm OR 2–3 foreground + army as dust/silhouettes. 85mm f/1.8 |

**Material limit**: Max 4–5 distinct materials in the sharp-focus zone. Additional materials go in bokeh.

**Exempt scenes**: Bio-cinematic (neurons, cells), cosmic, metaphorical — these don't need lifestyle photorealism.

Full rules: Cinematic Director skill, Section 9.5.

---

## Character Consistency for Multi-Scene Projects (e.g., VSL)

AI generators have **NO memory between images**. When generating 10+ images of the same character, you MUST force consistency through explicit description.

### Character Anchor Block

Write a frozen description ONCE, then copy-paste UNCHANGED into every prompt for that character:

```
CHARACTER ANCHOR (copy-paste verbatim into every scene):
"[Age] [ethnicity] [gender], [skin detail with texture], [eye shape/color + detail],
[hair color/length/style + accessories], [specific facial features],
[bearing/posture]. [Clothing with colors and materials].
[Jewelry: every piece named explicitly]. [Consistency note]."
```

### Rules:
1. **Never paraphrase** the anchor — exact repetition = consistency
2. **Include in EVERY scene** with that character, even callbacks
3. **Body-part-only scenes** (hands, forearms, skin close-ups) are HIGHEST RISK — MUST include age, ethnicity, skin quality, and visible jewelry even though no face is shown
4. **Wardrobe changes** get a variant anchor noting what changes and what stays

### Body-Part-Only Scenes (HIGHEST RISK)

Without face context, the generator invents a random person. Always include:
- **Age marker**: "hands of a woman in her late twenties"
- **Skin quality**: "taut, smooth, youthful skin with visible pores"
- **Ethnicity**: "olive Mediterranean complexion"
- **Visible jewelry**: matching the character's anchor (arm cuffs, bracelets, etc.)

**WRONG**: `Close-up of elegant feminine hands with gold cuffs` → generates 25-60 year old random hands
**RIGHT**: `Close-up of elegant youthful feminine hands of a striking Egyptian queen in her late twenties — taut olive Mediterranean skin, gold arm cuffs and lapis lazuli bracelets` → generates consistent young hands

---

## Negative Constraints (ALWAYS include)

Every image prompt should end with explicit negative constraints to prevent common AI generation issues:

```
ALWAYS INCLUDE (adapt to your project):
- "no text, no words, no letters, no logos, no watermarks"
- "no UI elements, no buttons, no overlays"
- "ultra-clean composition, ad-grade"

FOR HISTORICAL SCENES, ALSO ADD:
- "no modern clothing, no anachronistic objects"
- "no cartoonish or illustrated style"
```

---

## Ad-Specific Prompt Rules

When generating ad creatives (not VSL scenes), also follow these:

### The SO WHAT Test
Every visual must answer: "Why would a person scrolling at 10 PM stop their thumb and click?"

### What Works
- Phone screenshots (notifications, Screen Time, iMessage) — instantly native
- Reddit-style UGC posts — dark mode, upvotes (no Reddit logo)
- Financial documents (credit card statements, budgets) — universal recognition
- Macro photography (saffron threads, minerals) — beautiful + surprising
- Data comparisons (bar charts with dramatic contrast) — shareable

### What Fails
- Abstract science visuals (brain waves, molecules) — SO WHAT?
- Academic citations / journal references — nobody cares
- Messy lifestyle photos without clear hook
- Phone frames with too much empty space
- Clean infographics with price tags — looks like an ad

### Compliance (Ads Only)
- No supplement bottles, pills, or product packaging
- No product names, brand logos, or brand names
- No trademarked names (Amazon, Reddit logo, GNC)
- No health claims on the visual itself
- Structure/function claims need asterisk + disclaimer
