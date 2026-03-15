# Kling Video Workflow — Image-to-Video Ad Production

Enforced pipeline for generating images (Nano Banana / Gemini) and animating them into video clips using Kling V3. Every step is mandatory — do NOT skip any step or proceed without completing the checklist for each phase.

**REQUIRED SKILLS (read ALL before starting — full paths):**
1. `video-prompting-guide` — `.claude/commands/video-prompting-guide.md` — Prompt structure, scene templates, alignment checks
2. `kling-reference` — `docs/knowledge/video/kling.md` — Kling API params, model selection, camera control, image-to-video workflow
3. `muapi-seedance-2` — `.claude/skills/muapi-seedance-2/SKILL.md` — Professional camera grammar + alternative video generation
4. `sound-design` — `.claude/skills/sound-design/SKILL.md` — Scene-specific SFX map for post-production audio

---

## FEEDBACK LOOP (mandatory)
BEFORE starting: Run `supa-search-cc "kling motion video clip intent production feedback" --table learnings --limit 8`, plus REST filter `category=eq.video-feedback`. Inject results as "PAST FEEDBACK" block before writing any video prompts or motion descriptions.
AFTER any user rejection or correction to a clip (wrong motion, misread intent, quality issue): capture to `learnings` table with `stage: "kling-video"`.
Full protocol: Load the `feedback-loop` skill from your configured skills directory.

---

## HARD RULES (apply to EVERY phase)

### Rule 1: 1:1 Image-to-Video Parity (MANDATORY)

Every image prompt MUST have exactly ONE corresponding Kling video prompt. No exceptions.

```
1 image prompt = 1 Kling video prompt = 1 generated clip

Total image prompts == Total video prompts == Total Kling API calls
```

**How to count correctly**:
- Scenes with sub-shots (14A, 14B, 14C, 14D) = 4 images = 4 video prompts = 4 Kling clips
- Scenes that reuse an image (e.g., Scene 38 reuses Scene 16) = 0 new images, but still 1 video prompt = 1 Kling clip (the same image gets a different animation)
- Each image-video pair shares KLING PARAMS (camera, intensity, duration, mode, cfg_scale)
- After the script is complete, run a parity check: count all image prompts, count all video prompts — they must match

**Why this matters**: If you have 48 images but only 42 video prompts, 6 images won't be animated. If you have more video prompts than images, you'll have prompts pointing at nothing. The 1:1 rule eliminates this.

### Rule 2: Video Prompt Must Match the ACTUAL Image (not the script)

The video prompt describes motion for what's IN the generated image, NOT what the script originally described. If the image diverges from the script (different composition, different elements), the video prompt MUST be adapted to match the actual image content.

**Common mismatches to catch**:
| Issue | Wrong | Right |
|-------|-------|-------|
| Image shows hands lifting mineral from shoreline | "Orbit around crystal on dark substrate" | "Orbit around hand lifting mineral from shore" |
| Image shows person rubbing neck on bed edge | "Neural pathways flickering with blue light" | "Person rubbing neck, cold phone screen light" |
| Image says "NOT looking at viewer" | "Dolly in on her face looking at camera" | "Dolly in on her profile gazing at sunset" |
| Image has handmaidens in the scene | Video prompt ignores them | Video prompt mentions their subtle actions |
| Image is a vast field with a person walking | "Macro close-up of saffron threads" | "Person walking through saffron field, hand trailing flowers" |
| Image is a lab with test tubes + certificate | "Capsules on marble surface" | "Scientist holding certificate next to test tubes" |

### Rule 3: Camera Param Must Match Video Prompt Motion

The KLING PARAMS camera value and the video prompt's described motion must agree. If the param says `static` but the prompt says "slow dolly in," one of them is wrong. Fix the mismatch before generating.

### Rule 4: Model is `kling-v3` — Always

`kling-v3-omni` (O3) is NOT available on the direct Kling API (`api.klingai.com`). It only works via the web app or proxy APIs. Always use `kling-v3`.

### Rule 5: cfg_scale is `0.4` — Always

Lower cfg_scale = smoother motion, less jitter, more faithful to source image. Use `0.4` on every clip.

---

## MASTER SCRIPT INTEGRATION (When a Master Script Exists)

When the project has a master script (`vsl/{project_slug}/copy/master_script.md`), the master script is the **single binding source of truth**. It was written by the Director using the cinematic-director skill's AUTHOR mode (Section 13).

### What Changes When a Master Script Exists

| Phase | Without Master Script | With Master Script |
|-------|----------------------|-------------------|
| **Phase 1: Shot List** | Created from scratch based on brief | **DERIVED** from master script — don't invent shots |
| **Phase 2: Image Prompts** | Written independently | **MUST IMPLEMENT** master script Visual Direction (BINDING) |
| **Phase 4: Camera Motion** | Planned independently | **CONSUMED** from camera_plan.json (Cinematographer output) |
| **Phase 5: Video Prompts** | Written independently | **MUST ALIGN** with master script Camera Direction + camera_plan.json |

### The Film Crew Hierarchy

```
DIRECTOR → master_script.md (BINDING source of truth)
    ↓
CINEMATOGRAPHER → camera_plan.json (validated camera directions)
    ↓
THIS SKILL (Kling Workflow) → scene_prompts.md → [image revisions] → scene_prompts_final.md
    ↓
KLING MANIFEST → built from scene_prompts_final.md (NOT scene_prompts.md)
    ↓
KLING API → generated video clips
```

**Rule**: When a master script exists, this skill IMPLEMENTS — it does not re-interpret. If the master script says "static camera, 100mm macro, no hands," you write a static video prompt for a macro shot with no hands. You don't decide a zoom would look cooler.

### Alignment Validation (MANDATORY before generating)

Before sending any clip to Kling, verify alignment:

1. **Image prompt alignment** — run the 7-Point Check from video-prompting-guide (Subject, Framing, Lighting, Palette, Key Details, Exclusions, Scale Level)
2. **Video prompt alignment** — run the 5-Point Check (Camera motion, Motion elements, No invented elements, Matches actual image, Emotional tone)
3. **Camera plan match** — verify `camera_type` in camera_plan.json matches your video prompt's described motion

If ANY check fails → fix before generating. Do NOT generate clips from misaligned prompts.

### scene_prompts_final.md — The Correct Input After Image Revisions

When images go through multiple revision rounds (V1 → feedback → V2 → selective regenerations → 2K render), 30-60% of images may change significantly. The original `scene_prompts.md` video prompts become stale.

**After image revisions are complete**, a Video Re-alignment phase produces `scene_prompts_final.md` — video prompts re-aligned to match the ACTUAL final images.

**Rule**: When `scene_prompts_final.md` exists, use it (NOT `scene_prompts.md`) as the source for:
- Building the Kling manifest JSON
- All video prompt references
- Parity checks

If `scene_prompts_final.md` does not exist (no revision rounds, or standalone ad), use `scene_prompts.md` as normal.

---

## PHASE 1: BRIEF & SHOT LIST

**Skill: `nano-banana-kling-ad-workflow` (Section 1-2)**

### When a Master Script Exists

The shot list is **DERIVED** from the master script, not created independently. Read the master script and extract each scene into the shot list format. Do NOT invent new shots, change camera directions, or alter visual descriptions.

For each master script scene, map to:
```
Shot #: [scene number from master script]
Scene Goal: [from master script Emotional Intent]
Subject + Environment: [from master script Visual Direction — Subject + Environment]
Camera Style: [from master script Visual Direction — Framing]
Camera Motion: [from camera_plan.json — camera_type]
Motion Intensity: [from camera_plan.json — intensity]
Clip Duration: 5 (minimum Kling duration — trim shorter in post per master script Edit Timing)
On-Screen Line / Dialogue: [from master script Dialogue]
Audio Design: [from master script Atmosphere — Sound Palette + Emotional Tone]
Image Source: [generate / reuse Shot #XX per master script Callbacks]
```

### When NO Master Script Exists (standalone ads, quick videos)

Before generating ANY asset, capture these constraints. If the user hasn't provided them, ASK before proceeding:

| Constraint | Required? | Default |
|-----------|-----------|---------|
| Product or story concept | YES | — |
| Audience and tone | YES | — |
| Target duration | YES | 20-30s |
| Delivery format (Reels/TikTok/YouTube) | YES | Reels 9:16 |
| Budget ceiling in credits | NO | — |
| Number of shots | NO | 6 |

### Shot List Format (MANDATORY)

Create a numbered shot list with ALL of these fields per shot. Do not skip any field:

```
Shot #: [number]
Scene Goal: [what this shot accomplishes in the narrative]
Subject + Environment: [who/what + where]
Camera Style: [from video-prompting-guide shot types table]
Camera Motion: [from docs/knowledge/video/kling.md — see Phase 4]
Motion Intensity: [0.0-1.0 — see Phase 4]
Clip Duration: [3-5 seconds]
On-Screen Line / Dialogue: [text or "none"]
Audio Design: [scene audio — see Audio/Sound Design Framework below]
Image Source: [generate / reuse Shot #XX / real footage]
```

### Sub-Scene Counting Rule

If a scene has rapid cuts (e.g., "Ruled Egypt. Commanded navies. Spoke nine languages. Outlasted three Roman dictators."), each sub-cut is a SEPARATE shot with its own image and video prompt:

```
Shot 14A: Throne portrait (0.75s)     → 1 image + 1 video prompt
Shot 14B: Navy fleet (0.75s)           → 1 image + 1 video prompt
Shot 14C: Speaking with scrolls (0.75s)→ 1 image + 1 video prompt
Shot 14D: Ruins silhouette (0.75s)     → 1 image + 1 video prompt
Total: 4 images, 4 video prompts, 4 Kling clips (all generated at 5s, trimmed in post)
```

### Reuse Shots

Scenes that callback to earlier visuals should be marked as reuse:
```
Shot 38: Empire Callback — reuses Shot 16 image, NEW video prompt (different animation)
Shot 39: Sleepless Flash — reuses Shot 29A image + video prompt (same clip)
```
Reuse shots: 0 new images, but still count toward video prompt total if the animation is different.

### Narrative Flow (ENFORCED)
- Shots 1-2: **HOOK** — scroll-stopping opening
- Shots 3-N-1: **VALUE** — demonstrate product/story
- Shot N: **CTA** — clear call to action

### Product Placement Plan (MANDATORY for product VSLs)

Plan 4 product touchpoints in the shot list BEFORE generating any assets:

1. **BRAND INTRO** (~65%) — When brand name is first spoken, product MUST be visible in frame
2. **UGC USAGE** (~70%) — Real person using the product (taking capsule, drinking water with bottle visible)
3. **PRODUCT HERO** (~78%) — Commercial-quality product photography (studio or lifestyle setting)
4. **LIFESTYLE/CTA** (~85-90%) — Product in warm, lived-in setting near the call to action

**Tag every product scene**: `[PRODUCT REFERENCE: Upload actual bottle/package photo as reference]`

**Product visibility rule**: The viewer should NEVER hear the brand name without seeing the product. If the script says the brand name at 65%, the product bottle must be in the frame at 65%.

**UGC within cinematic VSLs**: The contrast between historical/cinematic sequences and modern UGC-feel product usage INCREASES trust. UGC moments feel like "proof" after the mythology sells the story. Don't worry about style clash — it's a feature, not a bug.

**AI can't invent your product**: ALWAYS upload the actual product photo as a reference image. Generic "supplement bottle" prompts produce generic bottles that don't match your brand.

### Parity Count (MANDATORY — include in shot list)

At the end of every shot list, add this count:

```
PARITY CHECK:
- Total unique image prompts to generate: XX
- Total reused images (no new generation): XX
- Total real footage shots (no AI generation): XX
- Total Kling video prompts needed: XX
- Total Kling API calls: XX
- Match confirmed: [YES/NO]
```

**CHECKPOINT 1**: Present the shot list WITH parity count to the user for approval before proceeding.

---

## PHASE 2: IMAGE GENERATION

**Skills: `nano-banana-kling-ad-workflow` (Section 3) + `video-prompting-guide` (Scene Templates)**

### Prompt Formula (MANDATORY — use this exact structure)

```
[subject], [action/pose], in [environment], [lighting], [camera framing],
[style anchors], [aspect ratio], ultra-clean composition, ad-grade, no text overlays
```

### Subject-First Rule (MANDATORY for story/VSL videos)

When the script names a person in the opening line, that person MUST be the first visual frame. Not their world, not their setting — THEM.

| Wrong | Right |
|-------|-------|
| Script: "The queen convinced..." → Visual: aerial of a city | Script: "The queen convinced..." → Visual: the queen at a table with maps |
| Script: "Einstein discovered..." → Visual: a university building | Script: "Einstein discovered..." → Visual: Einstein at a chalkboard |

**Why**: The viewer sees a PERSON and hears their name simultaneously = instant identification + scroll-stop. A landscape while a person's name is spoken creates a disconnect that kills the hook.

This applies to Shot 1 of any VSL. After the subject is established visually, subsequent shots can show locations, objects, and settings freely.

### Character Consistency (MANDATORY for recurring characters)

Character consistency is solved at the IMAGE generation step, not the video step. The direct Kling API (`api.klingai.com`) does not support element referencing — so every image must already contain the correct, consistent character before it goes to Kling for animation.

**How it works**: The source image IS the character reference. Kling animates what it sees in the image. If a recurring character looks the same in every source image, they'll look the same in every video clip.

**Character Anchor Block**: Define a frozen description for each recurring character. Include this EXACT block in every image prompt where that character appears:

```
CHARACTER ANCHOR EXAMPLE (include verbatim in every scene featuring this character):
"A striking woman in her early 30s, olive skin, sharp dark eyes with kohl liner,
black straight hair with gold beaded braids, wearing a white draped linen gown with a
broad collar necklace, gold arm cuffs, holding a gold ceremonial staff"
```

**Rules**:
- Write the anchor block ONCE at the start of the project
- Copy-paste it UNCHANGED into every image prompt for that character
- Never paraphrase, shorten, or "improve" the anchor — exact repetition = consistency
- If a scene requires a wardrobe change, create a NEW anchor block for that outfit
- Generate character scenes in batches (5-10 at a time) and cherry-pick the most consistent set
- Always keep the hero reference image (e.g., Scene 2) visible for comparison

**Why not Kling elements?** The direct Kling API (`api.klingai.com`) returns 404 on all element endpoints. Element referencing is only available via the web app UI or third-party proxy APIs (useapi.net, fal.ai). Our workflow uses the direct API, so consistency must be baked into the source images.

### Body-Part-Only Scenes (HIGHEST RISK)

When a scene shows ONLY a character's hands, forearm, skin, or other body part (no face visible), character consistency breaks almost every time. The generator has no face context to anchor identity.

**MANDATORY for body-part scenes** — include ALL of these in the image prompt:
1. **Age marker**: "hands of a woman in her late twenties" (NOT "elegant feminine hands")
2. **Skin quality**: "taut, smooth, youthful skin with visible pores" (NOT "visible skin detail")
3. **Ethnicity**: "olive Mediterranean complexion" (NOT "warm skin tones")
4. **Jewelry**: specific pieces visible on the body part (arm cuffs, bracelets, rings — must match the anchor)
5. **Character attribution**: "belonging to [CHARACTER NAME]" or "[CHARACTER ANCHOR]"

**Example — generates old hands**: `Close-up of elegant feminine hands with gold cuffs lifting a crystal`
**Example — generates consistent young hands**: `Close-up of elegant youthful feminine hands of a striking Egyptian queen in her late twenties — taut olive Mediterranean skin, gold arm cuffs and lapis lazuli bracelets, lifting a crystal`

### Callback/Reuse Scenes (Must Re-Anchor)

When a scene says "same as Scene X" or callbacks to an earlier visual, the generator does NOT know what Scene X looked like. ALWAYS include the full character anchor block — never rely on "same as before."

### Per-Shot Checklist (check ALL before generating)

- [ ] **Subject-First Rule**: If Shot 1 script names a person, that person is the visual subject
- [ ] Prompt follows the formula above (all 7 elements present)
- [ ] **Character anchor block** included verbatim for any recurring character
- [ ] **Aspect ratio** matches delivery format (9:16 for Reels/TikTok, 16:9 for YouTube)
- [ ] **Lighting** keyword specified (see `video-prompting-guide` lighting table)
- [ ] **Shot type** matches the shot list (close-up, wide, medium, etc.)
- [ ] No text overlays in the prompt (captions added in post)
- [ ] Dark/moody backgrounds for supplement/health content

### Generation Rules
- Generate **2-4 variations** per shot, pick the best one
- If character consistency drifts: add explicit anchor text to next prompt
- If scene looks noisy: simplify prompt, reduce style stacking
- Save all generated images to `video/output/kling/images/` with naming: `shot_01_description.png`

### Scene Type Templates (from `video-prompting-guide`)

Use the matching template based on scene type:

**Product/Ingredient Macro:**
```
"Extreme close-up macro of [SUBJECT]. Sharp focus, shallow DOF, dark moody background.
Studio lighting, [ASPECT] vertical, photorealistic."
```

**Lifestyle/Product Usage:**
```
"Medium shot of [PERSON] in [MODERN SETTING] with [PRODUCT]. Natural window lighting,
clean minimal background. [ASPECT] vertical, warm tones."
```

**Historical/Authority:**
```
"Cinematic [ASPECT] portrait. [CHARACTER ANCHOR] in [SETTING]. [LIGHTING].
Shallow depth of field. Photorealistic, 35mm film aesthetic."
```
**Note**: Use "35mm film aesthetic" instead of "film grain" — modern generators (Gemini/Nano Banana) handle raw film grain poorly (artifacts). The "35mm" trigger activates the right color response and depth characteristics without grain problems.

**Industrial/Problem Scene:**
```
"Wide establishing shot of [SETTING]. Cold blue-tinted lighting, steam/haze.
Ominous atmosphere. [ASPECT] vertical, cinematic."
```

**CHECKPOINT 2**: All images generated and saved. User approves hero frames before animation.

### Post-Generation Verification (MANDATORY)

After ALL images are generated, run this verification before writing ANY video prompts:

**Step 1: Visual Audit** — For each generated image, verify it matches its scene description. Note any divergences.

**Step 2: Adapt Video Prompts to Actual Images** — If the image diverges from the scripted scene (e.g., script says "warships" but image shows "palace interior"), **adapt the video motion prompt to the actual image content** — do NOT use the scripted video prompt blindly.

**Step 3: Parity Verification** — Count all image prompts and all video prompts. They must match:

```
GENERATION PARITY CHECK:
- Images generated: XX
- Images reused from earlier scenes: XX
- Video prompts written: XX
- Kling clips to generate: XX
- 1:1 MATCH: [YES/NO]
```

**Step 4: Cross-Reference Each Pair** — For every image, verify:
- [ ] The video prompt describes motion for what's ACTUALLY in this specific image
- [ ] The KLING PARAMS camera value matches the motion described in the video prompt
- [ ] Atmosphere elements in the video prompt match what's visible in the image
- [ ] If image has characters doing something (handmaiden pouring water, person rubbing neck), the video prompt mentions that action
- [ ] If image explicitly says "NOT looking at viewer," the video prompt doesn't say "looking at camera"

---

## PHASE 3: MODEL SELECTION

**Reference: `docs/knowledge/video/kling.md`**

### MANDATORY: Always use `kling-v3`

```
Model: kling-v3 (Kling 3.0)
Mode: std (standard) or pro (higher quality)
```

**NEVER use kling-v1, kling-v1.5, or kling-v2-master.** The project rule is: **always kling-v3**.

**Note on kling-v3-omni**: O3 (omni) is NOT available on the direct API (`api.klingai.com`) — returns "model is not supported". It's only available via the web app or proxy APIs. The direct API supports: kling-v3, kling-v2-1-master, kling-v2-master, kling-v1-6, kling-v1-5, kling-v1.

**Note on element referencing**: The direct Kling API does NOT support elements (returns 404). Character consistency is handled at the image generation step instead — see Phase 2: Character Consistency section.

**Note on audio**: The direct API does NOT generate audio. Audio is added in post-production (Remotion).

### Mode Selection
| Scenario | Mode | Notes |
|----------|------|-------|
| Quick test / single scene | `std` | Faster (~65-100s), smaller files (~4-5MB), good for validation |
| Full production batch | `pro` | Higher quality, ~100-250s per 5s clip (varies by scene complexity), 4.5-27MB per clip |
| Budget-constrained | `std` | Good enough for most ads |
| Re-generation after review | `pro` | When `std` output has visible artifacts or insufficient quality |

**Recommended workflow**: Use `std` for initial test of 1-2 scenes to validate prompts and images. Once validated, generate the full batch in `pro` mode for production quality. Pro mode is proven for full VSL production (51 clips generated in ~42 min with 3 concurrent workers).

### Duration Selection
| Clip Length | When |
|------------|------|
| `5` | Standard shot (any scene scripted 1-5s) |
| `10` | Extended shot (slow reveals, complex motion, 6-10s) |

**IMPORTANT**: Kling's minimum duration is 5 seconds. For scenes scripted under 5s (e.g., 1.5s, 3s), generate at 5s and trim to target length in post-production.

---

## PHASE 4: CAMERA MOTION PLANNING

**Skills: `docs/knowledge/video/kling.md` (Camera Control) + `video-prompting-guide` (Camera Movements)**

### When camera_plan.json Exists (from Cinematographer Skill)

If the project has a `camera_plan.json` (output of the Cinematographer skill, generated from the master script):

1. **Do NOT independently plan camera motions** — the Cinematographer already did this
2. **READ** `camera_plan.json` and use those values directly for each scene
3. The video prompt MUST describe motion consistent with the `camera_type` and `motion_reason` from the camera plan
4. Use the `motion_elements` from the camera plan in your video prompts — don't invent new ones
5. If a camera plan entry has `validated: false` or a flag, resolve with the Cinematographer before proceeding

**Skip the rest of Phase 4** if camera_plan.json exists — go directly to Phase 5 (generation).

### When NO camera_plan.json Exists (standalone mode)

### Available Camera Motions

| Motion | Value | Best For |
|--------|-------|----------|
| Zoom In | `zoom_in` | Focus on detail, dramatic reveal |
| Zoom Out | `zoom_out` | Reveal scene, establishing shots |
| Pan Left | `pan_left` | Survey scene, follow action |
| Pan Right | `pan_right` | Survey scene, follow action |
| Tilt Up | `tilt_up` | Reveal height, grandeur |
| Tilt Down | `tilt_down` | Reveal subject from above |
| Dolly In | `dolly_in` | Approach subject, intimacy |
| Dolly Out | `dolly_out` | Pull away, reveal context |
| Orbit Left | `orbit_left` | Product showcase, 3D feel |
| Orbit Right | `orbit_right` | Product showcase, 3D feel |
| Crane Up | `crane_up` | Hero shots, dramatic rise |
| Crane Down | `crane_down` | Descend to subject |
| Static | `static` | Contemplation, stability |

### Motion Intensity Scale

| Level | Value | Use For |
|-------|-------|---------|
| Subtle | 0.2 | Barely perceptible, portraits |
| Light | 0.4 | Gentle movement, calm scenes |
| Moderate | 0.6 | Standard animation level |
| Dynamic | 0.8 | Action scenes, high energy |
| Intense | 1.0 | Maximum drama |

### Cinematic Presets (Quick Reference)

| Preset | Motion | Intensity | When |
|--------|--------|-----------|------|
| Establishing | zoom_in | 0.4 | Opening wide shot |
| Dramatic Reveal | pan_right | 0.7 | Subject reveal |
| Hero Entrance | crane_up | 0.5 | Power shot |
| Product Orbit | orbit_right | 0.6 | Product showcase |
| Peaceful Static | static | 0.0 | Calm moment |
| Closing Pull-Back | zoom_out | 0.4 | End of sequence |

### Per-Shot Motion Checklist
- [ ] Camera motion selected from the table above
- [ ] Motion intensity set (0.0-1.0)
- [ ] **One motion per shot** — do NOT combine pan + zoom + tilt
- [ ] Motion matches the narrative purpose of the shot
- [ ] Prefer subtle motion (0.2-0.5) unless concept requires dynamic pacing
- [ ] Atmosphere elements noted: "dust particles", "steam rising", "hair moving slightly"

**CHECKPOINT 3**: Complete motion plan per shot approved before generating videos.

---

## PHASE 5: IMAGE-TO-VIDEO GENERATION

**Reference: `docs/knowledge/video/kling.md`**

### Pre-Generation Validation (MANDATORY per image)
- [ ] Image exists and is accessible
- [ ] Format: PNG, JPG, or WEBP
- [ ] Minimum dimensions: 512x512
- [ ] File size: under 10MB
- [ ] Aspect ratio matches target (9:16, 16:9, or 1:1)

### Kling Motion Prompt Formula (MANDATORY)

```
"[Camera motion description]. [Atmosphere elements — what moves in the scene].
Keep subject identity stable. Cinematic realism. [duration]s."
```

**Example** (Scene 01 — harbor):
```
"Slow aerial dolly forward over the harbor. Ships gently rocking on water.
Seagulls in the distance. Atmospheric haze drifting. Golden light shimmering
on water surface. 3.5 seconds. Smooth, cinematic movement."
```

### Negative Prompt (ALWAYS INCLUDE)

Every image-to-video call MUST include `negative_prompt`. Use the VSL style guide's "NEVER INCLUDE" list:

```
"text, words, letters, logos, watermarks, UI elements, buttons, overlays,
modern clothing in historical scenes, anachronistic objects, cartoonish,
illustrated style, blurry, distorted"
```

Adapt per project — the above is a general default. For supplement ads, add: `"bottles, product names, brand logos"`.

### Video Motion Prompt Rules (from `video-prompting-guide`)
- Describe ONLY the motion — the image already defines the visual
- **Match the prompt to what's IN the image**, not what was originally scripted
- Keep motion subtle unless the shot requires it
- One camera movement per clip
- Include atmosphere: "dust particles floating", "steam rising", "hair moving slightly"
- Specify duration target

### Generation Sequence

For each shot, execute in this exact order:

```
1. Validate image (dimensions, format, size)
2. Base64 encode RAW PNG (no JPEG compression — preserves full image quality). If RGBA, convert to RGB PNG first
3. Build motion prompt matching the ACTUAL image content
4. Set parameters:
   - model_name: "kling-v3" (ALWAYS)
   - mode: "std" (first pass) or "pro" (re-gen only)
   - duration: "5" or "10"
   - aspect_ratio: matching delivery format
   - cfg_scale: 0.4 (ALWAYS 0.4 — smoother motion, less jitter, faithful to source)
   - negative_prompt: see above
5. POST to /videos/image2video
7. Poll GET /videos/image2video/{task_id} (10s intervals, 600s max)
8. Download video to video/output/kling/clips/scene_XX_description.mp4
9. Verify: video plays, motion looks correct, no artifacts
```

### API Implementation

**Endpoint**: `POST https://api.klingai.com/v1/videos/image2video`
**Poll**: `GET https://api.klingai.com/v1/videos/image2video/{task_id}`
**Auth**: JWT (HS256) with `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` from `.env`

**Request body**:
```json
{
  "model_name": "kling-v3",
  "image": "<raw base64 string — NO data:image/...;base64, prefix>",
  "prompt": "<motion prompt>",
  "negative_prompt": "<negative prompt>",
  "duration": "5",
  "aspect_ratio": "9:16",
  "mode": "std",
  "cfg_scale": 0.4
}
```

**CRITICAL — base64 format**:
- The API rejects `data:image/png;base64,...` format. Send RAW base64 only.
- Send raw PNG — do NOT compress to JPEG. The quality loss from JPEG compression degrades fine details (faces, textures, hair) which carries through to the final video. Larger payload but maximum quality.
- If image is RGBA, convert to RGB PNG first (Kling doesn't handle alpha channels).
- Reference implementation: `video/kling/batch_generate.py` (sequential), `video/kling/batch_generate_concurrent.py` (concurrent)

**Batch runner**: For multi-scene VSLs, use `video/kling/batch_generate_concurrent.py` with a JSON manifest. Supports concurrent workers, resume (skips existing .mp4 files by size check), and dry-run validation.

**batch_results.json**: OVERWRITTEN on each run (not appended). Contains only results from the current run. Resume uses file existence checks, not this file. Archive results separately if tracking across multiple batches.

```bash
# Dry run — validate all images and scene count
python video/kling/batch_generate_concurrent.py <manifest.json> --output <dir> --mode pro --workers 3 --dry-run

# Full batch — 3 concurrent workers, pro mode
python video/kling/batch_generate_concurrent.py <manifest.json> --output <dir> --mode pro --workers 3

# Resume after crash — same command, completed scenes are skipped automatically
python video/kling/batch_generate_concurrent.py <manifest.json> --output <dir> --mode pro --workers 3
```

**Manifest format** (JSON array, one entry per scene — scene IDs can be alphanumeric e.g. "14c", "29c"):
```json
{
  "scene": "14c", "name": "languages_nine_nations",
  "image": "/absolute/path/to/scene_14c_languages_nine_nations.png",
  "prompt": "Static frame with subtle ambient motion... Keep subject identity stable. Cinematic realism. 5s.",
  "negative_prompt": "text, words, letters, logos, watermarks...",
  "duration": "5", "aspect_ratio": "9:16", "mode": "pro",
  "cfg_scale": 0.4, "model_name": "kling-v3"
}
```

**Manifest location**: `video/kling/manifests/` — store all manifests here for reproducibility.

### Rate Limiting & Concurrency
- **3 concurrent workers** is the safe maximum for the direct API — tested with 51 scenes
- **3s stagger** between job submissions to avoid burst rate limits
- If rate limited, the script retries automatically with 10s backoff
- Sequential `batch_generate.py` still available for cautious single-threaded runs

### Failure Handling
- **"Failure to pass the risk control system"**: Kling's content filter — often triggers on bath/nudity-adjacent scenes. **Retry usually works** (same command — resume skips completed, re-attempts failed). If persistent, soften the prompt language (remove "bathing", add more clothing/coverage descriptions)
- If faces drift: repeat identity anchors, reduce motion_strength
- If scenes look noisy: simplify motion prompt, reduce style stacking
- If cost rises too fast: reduce shot count, shorten clips
- If timeline slips: ship shorter cut first, extend later

**CHECKPOINT 4**: All clips generated. User reviews each clip before assembly.

---

## AUDIO / SOUND DESIGN FRAMEWORK

Every video clip MUST have an **AUDIO DESIGN** description alongside its video prompt. Silent video feels incomplete — viewers need audio to believe the scene. Audio design is written alongside the video prompt and implemented in Remotion post-production using layered sound effects and ambient tracks.

### Audio Design Prompt Formula (MANDATORY)

```
AUDIO DESIGN:
[Primary sound — the dominant audio element, directly tied to the main visual action]
[Ambient layer — continuous background atmosphere that establishes the environment]
[Detail sounds — 1-2 small, specific sounds that add realism and immersion]
[Emotional tone — one-word descriptor for the overall audio mood]
```

### Audio Categories by Scene Type

| Scene Type | Primary Sound | Ambient Layer | Detail Sounds | Examples |
|------------|--------------|---------------|---------------|----------|
| **Palace Interior** | Footsteps on stone, fabric rustle | Torch crackle, distant echo | Metal clink (jewelry), breath, distant murmur | Historical character scenes, throne room |
| **Sea / Water** | Waves crashing, water lapping | Wind over open water, distant seabirds | Rope creak, wood groan, sail snap | Fleet, Dead Sea, harbor |
| **Desert / Aerial** | Wind gusting | Vast open silence with low wind drone | Sand hissing, distant bird call | Dead Sea wide, aerial shots |
| **Military / March** | Rhythmic marching boots, armor clanking | Dust wind, distant horn/drum | Standard banner flapping, leather creak, breath | Army scenes |
| **Macro / Close-up** | Object-specific (water drip, crystal clink, coin scrape) | Low ambient hum or near-silence | Surface texture sound (fabric shift, metal ring) | Minerals, coins, ingredients |
| **Industrial / Cold** | Machine hum, fluorescent buzz | Low-frequency drone, sterile echo | Water flow, chemical hiss, air vent | Factory, water treatment, grocery |
| **Night / Bedroom** | Clock ticking or silence | Low-frequency room tone, distant traffic | Sheet rustle, breath, phone buzz | Sleepless scenes |
| **Lab / Modern** | Quiet precision sounds (glass clink, instrument beep) | Clean room ambient, soft air circulation | Capsule rattle, fabric shift | Lab, product scenes |
| **Nature / Organic** | Water flow, wind in foliage | Forest/field ambient, birdsong | Leaf rustle, dewdrop, insect hum | Spring, soil, harvest |
| **Peaceful / Calm** | Soft breathing, tea pour | Warm room tone, distant nature | Fabric shift, mug set down, gentle exhale | Calm evening, peaceful sleep |

### Audio Emotional Arc (Match the Visual Palette)

| Visual Palette | Audio Mood | Volume | Frequency Range |
|---------------|------------|--------|-----------------|
| **GOLDEN** (Acts 1-2, 4) | Warm, rich, full | Medium | Full range — bass warmth + detail highs |
| **DARK** (Act 3 pivot) | Ominous, sparse, tense | Low | Low-frequency dominant, thin highs |
| **COLD** (Act 3 problem) | Sterile, hollow, clinical | Medium-low | Flat, mid-range dominant, no bass warmth |
| **GOLDEN return** (Act 4-5) | Warm, confident, open | Medium-high | Rich bass + clear highs, wider stereo |

### Audio Design Rules

1. **Every clip gets audio** — No silent clips. Even a "quiet" scene needs room tone and micro-detail
2. **Primary sound matches primary visual motion** — If water is moving, you hear water. If soldiers march, you hear boots
3. **Ambient never cuts abruptly** — Cross-fade ambient layers between scenes (handled in Remotion)
4. **Detail sounds add realism** — The small sounds (jewelry clink, candle crackle, sand grain) are what make it feel REAL
5. **Emotional tone guides mixing** — GOLDEN scenes are warm and present; COLD scenes are thin and distant
6. **No music in audio design** — Music/score is a separate layer added in Remotion. Audio design = sound effects + ambience only
7. **Volume hierarchy**: Primary sound (loudest) → Ambient (medium) → Detail (subtle)
8. **Transition audio**: When visual palette shifts (GOLDEN → DARK), audio should shift too — warm → hollow
9. **Silence is a tool**: Use near-silence (just room tone) for maximum impact moments (e.g., "Twice." — Scene 06)

### Implementation in Remotion

Audio design descriptions are converted to layered sound in Remotion:

```
Layer 1: AMBIENT — Continuous background per act/palette (cross-faded between scenes)
Layer 2: PRIMARY — Scene-specific main sound (cuts with scene transitions)
Layer 3: DETAIL — Spot effects timed to specific visual moments
Layer 4: MUSIC/SCORE — Separate track (not part of audio design)
Layer 5: VOICEOVER — Narration track (not part of audio design)
```

Sound assets can be sourced from:
- Freesound.org (CC0/CC-BY)
- Epidemic Sound (licensed)
- Artlist (licensed)
- AI sound generation (ElevenLabs SFX, Stability Audio)

**CHECKPOINT 4.5**: Audio design written for every clip. User approves audio direction before sourcing sounds.

---

## PHASE 6: ASSEMBLY & DELIVERY

**Skill: `nano-banana-kling-ad-workflow` (Section 5-6)**

### Sequence Order (ENFORCED)
1. **Hook** (shots 1-2) — must stop the scroll
2. **Value demonstration** (middle shots) — show the product/story
3. **CTA** (final shot) — clear call to action

### Post-Production Checklist
- [ ] All clips sequenced in narrative order
- [ ] Transitions: hard cuts preferred (UGC-authentic), no fancy transitions
- [ ] Captions added if platform autoplay is muted (Reels, TikTok)
- [ ] Total runtime matches target duration
- [ ] Aspect ratio consistent across all clips
- [ ] **Audio design implemented**: ambient layers cross-faded, primary sounds per scene, detail sounds timed to visuals
- [ ] **Audio emotional arc**: GOLDEN=warm/rich, DARK=ominous/sparse, COLD=sterile/hollow
- [ ] Voiceover track layered on top of sound design
- [ ] Music/score added as separate layer (does NOT replace sound design)

### Cost & Quality Report (MANDATORY — output this at the end)

```
## Generation Report
- Total clips generated: X
- Clips used in final cut: X
- Model: kling-v3, Mode: [std/pro]
- Total duration: Xs
- Output format: [9:16 / 16:9 / 1:1]
- Output location: video/output/kling/
- Credits/cost estimate: $X

## Quality Assessment
- Shot consistency: [good/needs work]
- Motion quality: [smooth/jittery/too aggressive]
- What to improve next iteration: [specific notes]
```

---

## QUICK REFERENCE: The 6 Phases + Audio

```
PHASE 1: BRIEF & SHOT LIST → nano-banana-kling-ad-workflow (includes audio design per shot)
   ↓ (user approves shot list + PARITY COUNT)
PHASE 2: IMAGE GENERATION → nano-banana + video-prompting-guide
   ↓ (user approves hero frames + POST-GEN VERIFICATION with parity check)
PHASE 3: MODEL SELECTION → docs/knowledge/video/kling.md (ALWAYS kling-v3, cfg_scale 0.4)
   ↓
PHASE 4: CAMERA MOTION → docs/knowledge/video/kling.md + video-prompting-guide
   ↓ (user approves motion plan — verify camera params match video prompt text)
PHASE 5: IMAGE-TO-VIDEO → docs/knowledge/video/kling.md + existing Kling API
   ↓ (user reviews clips)
AUDIO: SOUND DESIGN → Audio Design Framework (primary + ambient + detail per clip)
   ↓ (user approves audio direction)
PHASE 6: ASSEMBLY → nano-banana-kling-ad-workflow + audio layers + cost report
```

### 5 Hard Rules (Always Enforced)
1. **1:1 Parity** — image count == video prompt count == Kling API calls
2. **Video prompt matches ACTUAL image** — not the original script description
3. **Camera param matches video prompt** — if param says `static`, prompt can't say "dolly in"
4. **Model is `kling-v3`** — v3-omni NOT available on direct API
5. **cfg_scale is `0.4`** — always, no exceptions

Every phase has a CHECKPOINT. Never skip a phase. Never proceed without completing all checklist items.
