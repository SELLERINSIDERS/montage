# Remotion Audio — Add Sound Effects to Kling Video Clips

Apply layered audio (ocean waves, wind, creaking, ambience) to Kling-generated video clips using Remotion. This is the implementation step AFTER audio design is written in the Kling Video Workflow.

**Pipeline**: Kling generates silent video clips → Audio design describes what sounds each scene needs → **This skill applies those sounds in Remotion** → Final MP4 with embedded audio

---

## FEEDBACK LOOP (mandatory)
BEFORE starting: Run `supa-search-cc "captions remotion audio sfx post-production feedback" --table learnings --limit 8`, plus REST filter `category=eq.video-feedback`. Inject results as "PAST FEEDBACK" before writing any Remotion configuration.
AFTER any user correction to audio mix, caption rendering, or Remotion output: capture to `learnings` table with `stage: "post-production"`.
Full protocol: Load the `feedback-loop` skill from your configured skills directory.

---

## Project Setup

```
video/remotion-video/
├── src/
│   ├── Root.tsx              ← Dynamic composition registration from manifest
│   ├── SceneWithAudio.tsx    ← Audio layering component (accepts layers prop)
│   ├── audioDesigns.ts       ← Scene → SFX mapping (88 scenes, keyed by scene_id)
│   └── sceneManifest.ts      ← Auto-generated clip specs (ffprobe data)
├── public/
│   ├── sfx/                  ← Sound effect library (56 approved MP3 files)
│   └── vsl/                  ← Source video clips (symlink to Kling clips)
├── package.json
└── remotion.config.ts
```

**Required package**: `@remotion/media` (already installed)

---

## Step 1: Get Source Video Specs

Before creating the composition, get the exact dimensions, FPS, and duration from the source clip:

```bash
# Get width x height
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 <video_path>

# Get FPS
ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 <video_path>

# Get duration
ffprobe -v error -show_entries format=duration -of csv=p=0 <video_path>
```

**CRITICAL**: Use the EXACT dimensions from the source video. Never hardcode 1080x1920 or any assumed value. Calculate `durationInFrames = Math.round(duration * fps)`.

---

## Step 2: Source Sound Effects

### Free SFX Sources (Direct Download, No Signup)

| Source | License | Direct Links? | Best For |
|--------|---------|---------------|----------|
| [Orange Free Sounds](https://orangefreesounds.com) | CC BY-NC 4.0 | YES — `/wp-content/uploads/.../*.mp3` | Nature, ambient, wind, ocean |
| [Free Sounds Library](https://freesoundslibrary.com) | CC BY 4.0 | YES — `/wp-content/uploads/.../*.mp3` | Ship creaking, specific SFX |
| [Freesound.org](https://freesound.org) | CC0/CC-BY | Requires API key | Largest library, high quality |
| [Mixkit](https://mixkit.co/free-sound-effects/) | Mixkit License | Dynamic URLs (hard to script) | Ocean, sea, wind loops |

### Finding Direct Download URLs

1. Search the site for the sound you need
2. Open the individual sound effect page
3. Use WebFetch to extract the direct MP3 URL (look for `href` containing `.mp3`)
4. Download with `curl -L -o <output_path> "<url>"`
5. Verify with `file <path>` (must show `MPEG ADTS, layer III`) and `ffprobe` for duration

### SFX Library (`video/remotion-video/public/sfx/`)

Name files by what they ARE, not by scene. One file can be reused across many scenes. Scene-to-SFX mapping lives in `src/audioDesigns.ts`.

**Approved Sounds** (56 files — see `.claude/skills/sound-design/SKILL.md` for full descriptions)

*Original library (27 files):*
`ocean_waves`, `wind`, `desert_wind`, `water_lapping`, `birdsong`, `spring_water`, `crickets`, `torch_crackle`, `cave_reverb`, `whispers`, `jewelry_clink`, `fabric_rustle`, `metal_ring`, `ship_creak`, `paper_rustle`, `coins_on_wood`, `candle_flame`, `glass_set_down`, `sheets_rustle`, `clock_ticking`, `phone_alarm`, `earth_crack`, `steam_hiss`, `crowd_cheer`, `crowd_murmur`, `crowd_gasp`, `factory_ambience`

*Expanded library — V2 (29 new files):*
| Category | Files |
|----------|-------|
| Ancient/Historical | `temple_echo`, `silk_rustle`, `oars_rowing`, `harbor_ambience`, `stone_footsteps`, `horse_distant`, `shield_impact`, `ancient_market` |
| Nature/Outdoor | `light_breeze`, `strong_gust`, `rain_window`, `thunder_distant`, `night_forest`, `dawn_chorus`, `leaves_rustle`, `sand_blow`, `seagulls`, `river_flow`, `campfire` |
| Water/Mineral | `underwater_deep`, `bubbling_water`, `waterfall_distant`, `tide_wash` |
| Modern Atmosphere | `rain_gentle`, `distant_traffic`, `kitchen_hum`, `morning_quiet`, `wooden_door`, `quill_writing` |

**Banned Sounds** (NEVER use — see Banned Sounds section below)
`breathing_calm`, `breathing_restless`, `marching`, `war_drums`, `armor_clank`, `low_drone`, `electric_zap`, `crystal_ring`, `lab_glass`, `fluorescent_buzz`, `water_drip`, `water_splash_bath`, `room_tone`

**Diversity Cap**: No single sound > 20% of total scenes. If `wind.mp3` is in 17 scenes of an 88-scene VSL, use `light_breeze`, `strong_gust`, `leaves_rustle`, or `sand_blow` for the rest.

**Source**: All from orangefreesounds.com (CC BY-NC 4.0) and freesoundslibrary.com (CC BY 4.0).

---

## Step 3: Build the Audio Component

### SceneWithAudio — Data-Driven via `layers` Prop

The component accepts an `AudioLayer[]` prop so each scene gets its own audio config without code changes. Falls back to default ocean/wind/creak if no layers passed.

```tsx
import { Audio } from "@remotion/media";
import {
  AbsoluteFill, OffthreadVideo, Sequence, staticFile,
  useVideoConfig, interpolate, useCurrentFrame,
} from "remotion";

export interface AudioLayer {
  src: string;          // path relative to public/ (e.g. "sfx/torch_crackle.mp3")
  volume: number;       // 0-1
  loop: boolean;
  delaySeconds?: number; // optional delayed entry
  fadeIn?: boolean;      // fade in over 1s + fade out over last 1s
}

export const SceneWithAudio: React.FC<{
  videoSrc: string;
  layers?: AudioLayer[];
}> = ({ videoSrc, layers }) => {
  const { fps, durationInFrames } = useVideoConfig();

  const defaultLayers: AudioLayer[] = [
    { src: "sfx/ocean_waves.mp3", volume: 0.75, loop: true },
    { src: "sfx/wind.mp3", volume: 0.4, loop: true },
    { src: "sfx/ship_creak.mp3", volume: 0.25, loop: true, delaySeconds: 0.5 },
  ];

  const audioLayers = layers ?? defaultLayers;

  return (
    <AbsoluteFill>
      <OffthreadVideo src={videoSrc} muted style={{ width: "100%", height: "100%" }} />

      {audioLayers.map((layer, i) => {
        const delayFrames = Math.round((layer.delaySeconds ?? 0) * fps);
        const audioElement = (
          <Audio
            key={i}
            src={staticFile(layer.src)}
            volume={(f) => {
              if (layer.fadeIn) {
                const fadeIn = interpolate(f, [0, fps], [0, layer.volume], {
                  extrapolateRight: "clamp",
                });
                const fadeOut = interpolate(
                  f + delayFrames,
                  [durationInFrames - fps, durationInFrames],
                  [layer.volume, 0],
                  { extrapolateLeft: "clamp" }
                );
                return Math.min(fadeIn, fadeOut);
              }
              return layer.volume;
            }}
            loop={layer.loop}
          />
        );

        if (delayFrames > 0) {
          return (
            <Sequence key={i} from={delayFrames}>
              {audioElement}
            </Sequence>
          );
        }
        return audioElement;
      })}
    </AbsoluteFill>
  );
};
```

### Volume Hierarchy (ALWAYS follow this)

| Layer | Role | Volume Range | Loop? |
|-------|------|-------------|-------|
| Primary | Main sound matching the dominant visual | 0.6 - 0.8 | Usually yes |
| Ambient | Background atmosphere | 0.3 - 0.5 | Always yes |
| Detail | Small realism sounds | 0.15 - 0.3 | Sometimes |

### Banned Sounds (NEVER USE)

These sounds were tested and rejected — they sound unnatural, musical, repetitive, or annoying on short video clips.

| File | Reason | Use Instead |
|------|--------|-------------|
| `breathing_calm.mp3` | Sounds creepy/distracting | SILENT or `wind` at 0.2 |
| `breathing_restless.mp3` | Sounds creepy/distracting | `sheets_rustle` only |
| `marching.mp3` | Too musical/rhythmic | `desert_wind` + `wind` |
| `war_drums.mp3` | Music — not SFX | `desert_wind` + `wind` |
| `armor_clank.mp3` | Military music cluster | `wind` or `fabric_rustle` |
| `low_drone.mp3` | Sounds like background music | SILENT |
| `electric_zap.mp3` | Strange/unnatural | SILENT |
| `crystal_ring.mp3` | Melodic/musical effect | `desert_wind` or `water_lapping` |
| `lab_glass.mp3` | Repetitive clicking when looped | SILENT |
| `fluorescent_buzz.mp3` | Annoying clicking/buzzing | SILENT |
| `water_drip.mp3` | Repetitive bulb/plop sound | `wind` + `birdsong` |
| `water_splash_bath.mp3` | Repetitive splashing when looped | `wind` + `candle_flame` or `steam_hiss` |
| `room_tone.mp3` | Annoying hum/wave when looped; overused as filler across 26+ scenes | SILENT or `wind` at 0.2 max |

**Rule 1**: If it sounds like music, a rhythm, a melody, breathing, a repetitive click, or a constant hum — don't use it. Stick to natural ambient sounds with a visible source: wind, water lapping, desert wind, candle flame, steam, birdsong, crickets. When in doubt, use silence.

**Rule 2 — Background Atmosphere Only**: All sounds must function as background atmosphere, NEVER as action foley. SFX sets the environment — it does NOT narrate what a character is doing. If a woman drinks from a glass, do NOT play `glass_set_down.mp3` (that narrates her action). If a waterfall fills the frame, DO play water sounds (that IS the environment). The test: does the sound describe an ACTION or the ENVIRONMENT? Actions → SILENT. Environment → use at background volume. Voiceover is always the star.

### Advanced: Fade In/Out

```tsx
import { interpolate, useCurrentFrame } from "remotion";

// Fade in over first second, fade out over last second
const frame = useCurrentFrame();
const { fps, durationInFrames } = useVideoConfig();

<Audio
  src={staticFile("sfx/ocean_waves.mp3")}
  volume={(f) => {
    const fadeIn = interpolate(f, [0, fps], [0, 0.75], { extrapolateRight: "clamp" });
    const fadeOut = interpolate(f, [durationInFrames - fps, durationInFrames], [0.75, 0], { extrapolateLeft: "clamp" });
    return Math.min(fadeIn, fadeOut);
  }}
  loop
/>
```

### Advanced: Trim Audio Start Point

If the best part of a sound effect is in the middle, use `trimBefore`:

```tsx
<Audio
  src={staticFile("sfx/ocean_waves.mp3")}
  trimBefore={3 * fps}   // Skip first 3 seconds of the recording
  volume={0.75}
  loop
/>
```

### Advanced: Pitch Shifting (Render-Only)

```tsx
// Lower pitch = deeper, more ominous ocean
<Audio src={staticFile("sfx/ocean_waves.mp3")} toneFrequency={0.8} volume={0.75} loop />

// Higher pitch = lighter, more distant wind
<Audio src={staticFile("sfx/wind.mp3")} toneFrequency={1.2} volume={0.4} loop />
```

Note: Pitch shifting only works during `npx remotion render`, NOT in Studio preview.

---

## Step 4: Register Composition in Root.tsx

Import `SceneWithAudio` + `AudioLayer` type, and pass scene-specific layers via `defaultProps`:

```tsx
import { SceneWithAudio, AudioLayer } from "./SceneWithAudio";

// Inside RemotionRoot — one <Composition> per scene:
<Composition
  id="Scene01ExampleTorchlit"
  component={SceneWithAudio}
  width={860}           // ← FROM ffprobe, NOT hardcoded
  height={1068}         // ← FROM ffprobe, NOT hardcoded
  fps={24}              // ← FROM ffprobe, NOT hardcoded
  durationInFrames={121} // ← Math.round(duration * fps)
  defaultProps={{
    videoSrc: staticFile("scene_01_example_torchlit_close.mp4"),
    layers: [
      { src: "sfx/torch_crackle.mp3", volume: 0.7, loop: true, fadeIn: true },
      { src: "sfx/cave_reverb.mp3", volume: 0.35, loop: true },
      { src: "sfx/paper_rustle.mp3", volume: 0.2, loop: false, delaySeconds: 1.0 },
    ] as AudioLayer[],
  }}
/>
```

For batch rendering, import layers from the audio design map instead of inline:

```tsx
import { SCENE_AUDIO } from "./audioDesigns";

// Then use SCENE_AUDIO["scene_01"] as the layers prop
```

**CRITICAL**: The source video file must be in `video/remotion-video/public/`. Copy or symlink it there before rendering.

---

## Step 5: Render

```bash
cd video/remotion-video

# Render single scene
npx remotion render SceneWithAudio --output ../output/kling/clips/scene_XX_name_WITH_AUDIO.mp4 --codec h264

# Output: H.264 video + AAC audio, same dimensions as source
```

### Verify Output

```bash
ffprobe -v error -show_entries stream=codec_name,width,height,channels -show_entries format=duration -of default=noprint_wrappers=1 <output_path>
```

Confirm: `codec_name=h264`, correct width/height, `codec_name=aac`, `channels=2`, correct duration.

---

## Batch Workflow: Applying Audio to All Scenes

The audio design map in `src/audioDesigns.ts` maps all scenes to their AudioLayer arrays. The batch pipeline uses two scripts:

### 1. Generate Scene Manifest

```bash
python3 scripts/generate_scene_manifest.py
```

Runs ffprobe on all clips in the symlinked `public/vsl/` directory, outputs:
- `video/remotion-video/src/sceneManifest.ts` — TypeScript array for Remotion
- `state/scene_manifest.json` — JSON for the batch render script

### 2. Root.tsx — Dynamic Composition Registration

Root.tsx dynamically registers all scenes from the manifest + audio designs:

```tsx
import { SCENE_AUDIO } from "./audioDesigns";
import { SCENE_MANIFEST } from "./sceneManifest";

{SCENE_MANIFEST.map((scene) => (
  <Composition
    key={scene.compId}
    id={scene.compId}
    component={SceneWithAudio}
    width={scene.width}
    height={scene.height}
    fps={scene.fps}
    durationInFrames={scene.durationInFrames}
    defaultProps={{
      videoSrc: staticFile(scene.videoFile),
      layers: (SCENE_AUDIO[scene.id] ?? []) as AudioLayer[],
    }}
  />
))}
```

### 3. Batch Render

```bash
python3 scripts/batch_render_audio.py          # Render all scenes
python3 scripts/batch_render_audio.py --dry-run # Preview only
```

- Renders sequentially via `npx remotion render src/index.ts <compId> <output_path> --codec h264`
- **SILENT scenes** (empty `[]` in audioDesigns.ts) are COPIED unchanged — no Remotion re-encoding
- Skips scenes already completed (resume capability)
- Saves progress to `state/batch_render_audio_state.json`
- To re-render specific scenes: delete their entries from state JSON + delete output files, then re-run

### 4. Post-Render Verification (MANDATORY)

After every batch render, verify the output. The batch script can silently fail to copy SILENT scenes due to the PascalCase↔snake_case ID mismatch (see Mistake 6 in sound-design SKILL.md).

```bash
# For each audio scene: verify h264 video + aac audio streams
ffprobe -v error -show_entries stream=codec_name -of csv=p=0 <output_file>

# For each SILENT scene: verify exact file size match with original
# If sizes differ, the copy failed and the file was re-encoded through Remotion
```

### 5. Re-render After Audio Design Changes

When updating `audioDesigns.ts` (e.g., replacing banned sounds):
1. Edit the scene entries in `audioDesigns.ts`
2. Delete the affected scene entries from `state/batch_render_audio_state.json`
3. Delete the affected output files from the output directory (e.g., `video/output/kling/{project}_with_audio/`)
4. Re-run `python3 scripts/batch_render_audio.py` — only the cleared scenes will render

---

## Audio Design → Implementation Quick Reference

### Nature / Environment
| Audio Design Phrase | SFX File | Volume | Notes |
|-------------------|----------|--------|-------|
| "Waves crashing hard" | `ocean_waves.mp3` | 0.7-0.8 | Primary layer |
| "Gentle lapping water" | `ocean_waves.mp3` | 0.3-0.4 | Ambient layer |
| "Water lapping at shore" | `water_lapping.mp3` | 0.5-0.7 | Softer than ocean_waves |
| "Steady ocean wind" | `wind.mp3` | 0.35-0.5 | Loop always |
| "Hot desert wind" | `desert_wind.mp3` | 0.5-0.7 | Dry, desolate feel |
| "Birds at dawn" | `birdsong.mp3` | 0.3-0.5 | Morning/peaceful scenes |
| "Flowing stream/brook" | `spring_water.mp3` | 0.4-0.6 | Water treatment, mineral springs |
| "Evening crickets" | `crickets.mp3` | 0.25-0.4 | Night ambience |

### Palace / People
| Audio Design Phrase | SFX File | Volume | Notes |
|-------------------|----------|--------|-------|
| "Torch flames flickering" | `torch_crackle.mp3` | 0.4-0.7 | Palace interiors |
| "Stone chamber echo" | `cave_reverb.mp3` | 0.25-0.4 | Short, loop for continuous reverb |
| "Hushed whispers / conspiracy" | `whispers.mp3` | 0.3-0.5 | Political intrigue scenes |
| "Gold/jewelry tinkling" | `jewelry_clink.mp3` | 0.15-0.25 | Detail layer, don't loop |
| "Linen garment movement" | `fabric_rustle.mp3` | 0.15-0.25 | Subtle detail |
| "Interior silence / room tone" | SILENT (no sound) | — | **BANNED** — use silence for quiet interiors |

### Military / Action
| Audio Design Phrase | SFX File | Volume | Notes |
|-------------------|----------|--------|-------|
| "Blade ring / metallic chime" | `metal_ring.mp3` | 0.2-0.35 | Detail, don't loop |
| "Rope rigging / wood creaking" | `ship_creak.mp3` | 0.2-0.3 | Ship and dock scenes |

### Objects / Foley
| Audio Design Phrase | SFX File | Volume | Notes |
|-------------------|----------|--------|-------|
| "Scroll/papyrus rustling" | `paper_rustle.mp3` | 0.2-0.35 | Detail, delay 0.5-1s |
| "Coins on table / silver trade" | `coins_on_wood.mp3` | 0.2-0.3 | Detail, don't loop |
| "Oil lamp / candle flame" | `candle_flame.mp3` | 0.3-0.5 | Intimate fire, softer than torch |
| "Cup/goblet set down" | `glass_set_down.mp3` | 0.15-0.25 | One-shot detail |
| "Bed sheets rustling" | `sheets_rustle.mp3` | 0.2-0.3 | Bedroom/insomnia scenes |

### Modern
| Audio Design Phrase | SFX File | Volume | Notes |
|-------------------|----------|--------|-------|
| "Clock ticking" | `clock_ticking.mp3` | 0.35-0.5 | Metronomic, bedroom |
| "Phone alarm blaring" | `phone_alarm.mp3` | 0.6-0.8 | Jarring wake-up |

### Science / Abstract
| Audio Design Phrase | SFX File | Volume | Notes |
|-------------------|----------|--------|-------|
| "Earth cracking / desolation" | `earth_crack.mp3` | 0.5-0.7 | Dead Sea, barren land |

### Water
| Audio Design Phrase | SFX File | Volume | Notes |
|-------------------|----------|--------|-------|
| "Steam / hot vapor" | `steam_hiss.mp3` | 0.3-0.5 | Bath house, spa |

### Mood Recipes
| Mood | Recipe |
|------|--------|
| **Epic** | Primary high (0.7+), ambient medium (0.4), detail subtle (0.2) |
| **Tense** | Primary low (0.3), ambient high (0.5), detail sparse |
| **Calm** | All layers low (0.2-0.4), gentle fade in |
| **Commanding** | `torch_crackle` 0.7 + `cave_reverb` 0.35 + foley detail 0.2 |
| **Desolate** | `desert_wind` 0.6 + `earth_crack` 0.4 |
| **Intimate** | `candle_flame` 0.4 only (single layer) |
| **Maritime** | `ocean_waves` 0.7 + `wind` 0.4 + `ship_creak` 0.25 |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| No audio in output | Check `@remotion/media` is installed. Import `Audio` from `@remotion/media`, NOT `remotion` |
| Wrong aspect ratio | Get dimensions from `ffprobe`, set on `<Composition>`, NOT on the component |
| Audio sounds wrong / unrelated | Verify the MP3 is the right file: `ffprobe -v error -show_entries format=duration` + listen locally first |
| Audio too short / clicking | Use `loop` prop. Short files (< 2s) may click at loop boundary — use longer recordings |
| Pitch shifting not working | Only works during `npx remotion render`, NOT in Studio preview |
| Video file not found | Must be in `video/remotion-video/public/` — copy or symlink there |

---

## Files

| File | Purpose |
|------|---------|
| `video/remotion-video/src/SceneWithAudio.tsx` | Audio layering component (don't modify) |
| `video/remotion-video/src/audioDesigns.ts` | Scene → SFX mapping for all scenes |
| `video/remotion-video/src/sceneManifest.ts` | Auto-generated clip specs (width, height, fps, frames) |
| `video/remotion-video/src/Root.tsx` | Dynamic composition registration from manifest |
| `video/remotion-video/public/sfx/` | Sound effect library (56 approved + 13 banned MP3 files) |
| `video/remotion-video/public/vsl/` | Symlink to source video clips |
| `video/output/kling/{project}/` | Original silent Kling clips |
| `video/output/kling/{project}_with_audio/` | Final clips with SFX audio (or SILENT copies) |
| `scripts/generate_scene_manifest.py` | ffprobe all clips → generate manifest |
| `scripts/batch_render_audio.py` | Batch render with resume capability |
| `state/scene_manifest.json` | Clip specs for batch script |
| `state/batch_render_audio_state.json` | Render progress tracking |
| `docs/apply-audio-to-scenes-prompt.md` | Audio design prompt (approved sounds, combinations, pipeline) |
| `.claude/commands/kling-video-workflow.md` | Audio Design Framework (what sounds to use per scene type) |
