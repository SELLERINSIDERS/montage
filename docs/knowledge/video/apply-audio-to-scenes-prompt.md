# Apply Audio to Kling Video Scenes

You are applying sound effects to silent Kling-generated video clips using Remotion. Follow this prompt exactly.

---

## What You're Doing

Taking silent 5-10s video clips and adding 2-3 layered sound effects to make them feel cinematic. NOT all clips need audio — only the ones the user specifies.

## Golden Rule: Sound Harmony

**Maximum 3 audio layers per scene.** Every sound in a scene must belong together — they should feel like parts of one environment, not competing tracks.

| Layers | Structure | Example |
|--------|-----------|---------|
| 2 layers | Primary + Ambient | Ocean waves + wind |
| 3 layers | Primary + Ambient + Detail | Torch crackle + room tone + paper rustle |

**Never do this:**
- 4+ sounds on one 5-second clip — it becomes noise
- Two competing primary sounds (e.g., ocean waves + marching)
- Detail sounds louder than the primary — they should whisper, not shout

**Sound pairing rules:**
- Primary and ambient must be from the SAME world (both nature, both indoor, both military)
- Detail sounds accent the scene — they don't define it
- If a scene is calm, ALL layers are calm. Don't mix calm ambient with jarring detail
- When in doubt, use fewer sounds at the right volume rather than more sounds

---

## Banned Sounds (NEVER USE)

These sounds were tested and rejected. Do NOT use them in any scene — they sound unnatural, musical, repetitive, or annoying on short video clips.

| File | Reason | Use Instead |
|------|--------|-------------|
| `breathing_calm.mp3` | Sounds creepy/distracting | `room_tone` or `wind` |
| `breathing_restless.mp3` | Sounds creepy/distracting | `room_tone` or `sheets_rustle` |
| `marching.mp3` | Too musical/rhythmic | `desert_wind` + `wind` |
| `war_drums.mp3` | Music — not SFX | `desert_wind` + `wind` |
| `armor_clank.mp3` | Military music cluster | `wind` or `fabric_rustle` |
| `low_drone.mp3` | Sounds like background music | `room_tone` + `wind` |
| `electric_zap.mp3` | Strange/unnatural | `room_tone` + `wind` |
| `crystal_ring.mp3` | Melodic/musical effect | `desert_wind` or `water_lapping` |
| `lab_glass.mp3` | Repetitive clicking when looped | `room_tone` + `fabric_rustle` |
| `fluorescent_buzz.mp3` | Annoying clicking/buzzing | `room_tone` + `wind` |
| `water_drip.mp3` | Repetitive bulb/plop sound | `wind` + `birdsong` |
| `water_splash_bath.mp3` | Repetitive splashing when looped | `wind` + `candle_flame` or `steam_hiss` |

**Rule**: If it sounds like music, a rhythm, a melody, breathing, or a repetitive click — don't use it. Stick to natural ambient sounds: wind, room tone, water lapping, desert wind, candle flame, steam, birdsong, crickets.

---

## SFX Library

All files are in `video/remotion-video/public/sfx/`. These are real recordings, not synthesized.

### Approved Sounds (use these)
| File | Duration | Sound |
|------|----------|-------|
| `ocean_waves.mp3` | 2:00 | Rolling ocean waves |
| `wind.mp3` | 1:32 | Heavy outdoor wind |
| `desert_wind.mp3` | 43s | Dry, hot desert wind |
| `water_lapping.mp3` | 2:23 | Gentle water at shore |
| `birdsong.mp3` | 2:00 | Morning birds chirping |
| `spring_water.mp3` | 1:12 | Flowing stream/brook |
| `crickets.mp3` | 1:30 | Evening cricket chorus |
| `torch_crackle.mp3` | 38s | Fire crackling on walls |
| `cave_reverb.mp3` | 2.6s | Stone chamber water echo |
| `whispers.mp3` | 1:02 | Hushed murmuring voices |
| `jewelry_clink.mp3` | 0.7s | Gold/metal tinkling |
| `fabric_rustle.mp3` | 5s | Linen cloth movement |
| `room_tone.mp3` | 25s | Interior ambient hum |
| `metal_ring.mp3` | 8.1s | Blade ring, metallic chime |
| `ship_creak.mp3` | 27s | Rope/wood creaking |
| `paper_rustle.mp3` | 11s | Scroll/parchment handling |
| `coins_on_wood.mp3` | 8.6s | Coins on wooden table |
| `candle_flame.mp3` | 31s | Soft candle/oil lamp flame |
| `glass_set_down.mp3` | 2.1s | Cup/goblet set down |
| `sheets_rustle.mp3` | 2.7s | Bed sheets moving |
| `clock_ticking.mp3` | 28s | Metronomic clock tick |
| `phone_alarm.mp3` | 5.5s | Aggressive phone alarm |
| `earth_crack.mp3` | 15s | Soil fracturing |
| `steam_hiss.mp3` | 33s | Hot steam/vapor |
| `crowd_cheer.mp3` | 7s | Large crowd cheering/applauding |
| `crowd_murmur.mp3` | 32s | Indistinct crowd murmur/ambience |
| `crowd_gasp.mp3` | 2s | Crowd gasping in surprise |
| `factory_ambience.mp3` | 12s | Industrial machinery/factory noise |

### Banned Sounds (NEVER use — see Banned Sounds section above)
`breathing_calm`, `breathing_restless`, `marching`, `war_drums`, `armor_clank`, `low_drone`, `electric_zap`, `crystal_ring`, `lab_glass`, `fluorescent_buzz`, `water_drip`, `water_splash_bath`

---

## Volume Rules

Every layer has a role. Follow this hierarchy strictly:

| Role | Volume | Loop? | Purpose |
|------|--------|-------|---------|
| **Primary** | 0.6 - 0.8 | Usually yes | The main sound — what you'd hear first if you were there |
| **Ambient** | 0.3 - 0.5 | Always yes | Background atmosphere — felt more than heard |
| **Detail** | 0.15 - 0.3 | Sometimes | Small realism touch — a single accent |

**If only using 2 layers:** Primary + Ambient. Skip detail.

---

## Proven Sound Combinations

These combinations are tested and harmonize well together. All banned sounds have been removed.

| Scene Type | Primary | Ambient | Detail (optional) |
|-----------|---------|---------|-------------------|
| **Sea / Fleet** | `ocean_waves` 0.7 | `wind` 0.4 | `ship_creak` 0.25 |
| **Palace Interior** | `torch_crackle` 0.6 | `cave_reverb` 0.35 | `paper_rustle` 0.2 |
| **Desert / Military** | `desert_wind` 0.65 | `wind` 0.35 | — |
| **Bedroom / Sleep** | `wind` 0.5 | `room_tone` 0.3 | — |
| **Insomnia** | `clock_ticking` 0.65 | `room_tone` 0.3 | — |
| **Morning Wake** | `phone_alarm` 0.7 | `room_tone` 0.25 | `sheets_rustle` 0.2 |
| **Political Intrigue** | `whispers` 0.5 | `torch_crackle` 0.35 | `fabric_rustle` 0.15 |
| **Dead Sea / Barren** | `desert_wind` 0.6 | `earth_crack` 0.4 | — |
| **Bath / Spa** | `wind` 0.6 | `candle_flame` 0.35 | — |
| **Science / Lab** | `room_tone` 0.5 | `fabric_rustle` 0.25 | — |
| **Mineral / Water** | `water_lapping` 0.6 | `desert_wind` 0.35 | — |
| **Peaceful Dawn** | `birdsong` 0.5 | `spring_water` 0.35 | — |
| **Evening / Night** | `wind` 0.6 | `crickets` 0.3 | — |
| **Trade / Market** | `coins_on_wood` 0.5 | `candle_flame` 0.3 | `fabric_rustle` 0.15 |
| **War Council** | `candle_flame` 0.5 | `wind` 0.25 | `paper_rustle` 0.2 |
| **Command / Authority** | `torch_crackle` 0.7 | `cave_reverb` 0.35 | `jewelry_clink` 0.15 |
| **Ship Deck** | `ocean_waves` 0.75 | `wind` 0.45 | `ship_creak` 0.25 |
| **Steam / Thermae** | `cave_reverb` 0.5 | `steam_hiss` 0.35 | — |
| **Triumph / Procession** | `crowd_cheer` 0.65 | `wind` 0.4 | `jewelry_clink` 0.15 |
| **Marketplace / Bazaar** | `crowd_murmur` 0.55 | `wind` 0.35 | — |
| **Industrial / Factory** | `factory_ambience` 0.55 | `wind` 0.3 | — |
| **Crowd Reaction** | `whispers` 0.5 | `cave_reverb` 0.35 | `crowd_gasp` 0.25 |

---

## Technical Pipeline

### Step 1: Get Video Specs

For each clip the user gives you, run ffprobe to get exact specs:

```bash
# Width x Height
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 <video_path>

# FPS
ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 <video_path>

# Duration in seconds
ffprobe -v error -show_entries format=duration -of csv=p=0 <video_path>
```

Calculate: `durationInFrames = Math.round(duration * fps)`

**NEVER guess or hardcode dimensions. Always use ffprobe values.**

### Step 2: Copy Video to Remotion Public Folder

```bash
cp <source_video> video/remotion-video/public/
```

### Step 3: Choose Audio Layers

Based on the scene content, pick 2-3 sounds from the proven combinations above. If the scene doesn't match any combination, construct one following these rules:
1. Pick ONE primary sound that matches the dominant visual
2. Pick ONE ambient sound from the same environment
3. Optionally pick ONE detail sound that adds subtle realism
4. All three must belong to the same world

### Step 4: Add Composition to Root.tsx

```tsx
import { SceneWithAudio, AudioLayer } from "./SceneWithAudio";

// Inside RemotionRoot — add this composition:
<Composition
  id="SceneXX"                    // Unique ID
  component={SceneWithAudio}
  width={860}                     // FROM ffprobe
  height={1068}                   // FROM ffprobe
  fps={24}                        // FROM ffprobe
  durationInFrames={121}          // Math.round(duration * fps)
  defaultProps={{
    videoSrc: staticFile("scene_xx_name.mp4"),
    layers: [
      { src: "sfx/primary_sound.mp3", volume: 0.7, loop: true, fadeIn: true },
      { src: "sfx/ambient_sound.mp3", volume: 0.35, loop: true },
      { src: "sfx/detail_sound.mp3", volume: 0.2, loop: false, delaySeconds: 0.5 },
    ] as AudioLayer[],
  }}
/>
```

**Key props:**
- `fadeIn: true` — smooth 1-second fade in at start, fade out at end (use on primary layer)
- `delaySeconds` — delay entry of detail sounds by 0.3-1.0s for realism
- `loop: true` — for sounds shorter than the video duration
- `loop: false` — for one-shot details (jewelry clink, glass set down, etc.)

### Step 5: Render

```bash
cd video/remotion-video
npx remotion render SceneXX --output ../output/kling/clips/scene_xx_name_WITH_AUDIO.mp4 --codec h264
```

### Step 6: Verify

```bash
ffprobe -v error -show_entries stream=codec_name,width,height,channels -show_entries format=duration -of default=noprint_wrappers=1 <output_path>
```

Confirm: video `h264`, correct dimensions, audio `aac`, `channels=2`, correct duration.

---

## Existing Audio Design Map

There is already a pre-built scene-to-audio mapping in `video/remotion-video/src/audioDesigns.ts`. This maps scene IDs (like `scene_01`, `scene_14a`) to their AudioLayer arrays. If a scene is already mapped there, use those layers. If the user wants different audio, override with new layers in the Composition's `defaultProps`.

---

## Batch Rendering

For rendering all scenes at once, use the batch pipeline:

1. **Generate manifest**: `python3 scripts/generate_scene_manifest.py` — runs ffprobe on all clips, outputs `sceneManifest.ts` + `scene_manifest.json`
2. **Batch render**: `python3 scripts/batch_render_audio.py` — renders all scenes sequentially with resume capability
3. **Re-render specific scenes**: Delete their entries from `state/batch_render_audio_state.json` and their output files, then re-run the batch script

Source clips go in `video/remotion-video/public/vsl/`, output goes to `video/output/kling/<project_slug>_sfx/`.

---

## Reference Files

| File | What It Is |
|------|-----------|
| `video/remotion-video/src/SceneWithAudio.tsx` | The audio component (don't modify) |
| `video/remotion-video/src/audioDesigns.ts` | Scene-to-audio map (51 entries, all scenes) |
| `video/remotion-video/src/sceneManifest.ts` | Auto-generated clip specs (width, height, fps, frames) |
| `video/remotion-video/src/Root.tsx` | Dynamic composition registration from manifest |
| `video/remotion-video/public/sfx/` | Sound effect library |
| `video/remotion-video/public/vsl/` | Source video clips (copied from project output) |
| `video/output/kling/<project_slug>/` | Original silent Kling clips |
| `video/output/kling/<project_slug>_sfx/` | Final clips with SFX audio |
| `scripts/generate_scene_manifest.py` | ffprobe all clips → generate manifest |
| `scripts/batch_render_audio.py` | Batch render with resume capability |
| `state/scene_manifest.json` | Clip specs for batch script |
| `state/batch_render_audio_state.json` | Render progress tracking |
| `.claude/commands/remotion-audio.md` | Full technical skill reference |

---

## Checklist Before Rendering

- [ ] ffprobe specs captured (exact width, height, fps, duration)
- [ ] Video copied to `video/remotion-video/public/`
- [ ] Max 3 audio layers chosen
- [ ] All layers are from the same sonic world (no mixing ocean + lab + alarm)
- [ ] Volume follows hierarchy: Primary > Ambient > Detail
- [ ] Primary layer has `fadeIn: true` for smooth entry
- [ ] Detail layer has `delaySeconds` (0.3-1.0s) if used
- [ ] Composition registered in Root.tsx with correct ID
- [ ] Output verified with ffprobe (h264 + aac + correct dimensions)
