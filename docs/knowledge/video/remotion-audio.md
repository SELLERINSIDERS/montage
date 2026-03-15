---
domain: video-production
updated: 2026-03-08
tags: [remotion, audio, sfx, post-production]
---

# Remotion Audio — Post-Production Sound Design

## Skill
`/project:remotion-audio` — full reference for adding SFX to Kling clips

## Components
- **SceneWithAudio**: `video/remotion-video/src/SceneWithAudio.tsx` — accepts `layers` prop (AudioLayer[])
- **Audio design map**: `video/remotion-video/src/audioDesigns.ts` — maps 88 scenes (snake_case keys) to AudioLayer arrays
- **Scene manifest**: `video/remotion-video/src/sceneManifest.ts` — auto-generated from ffprobe (PascalCase compIds)
- **Root.tsx**: Dynamic composition registration from manifest + audio designs

## ID Format Warning
- audioDesigns.ts uses **snake_case** keys: `scene_01`, `scene_26`
- sceneManifest.ts uses **PascalCase** compIds: `Scene01OpeningShot`, `Scene26ProductReveal`
- The batch render script must convert between formats. See Mistake 6 in sound-design SKILL.md.

## SFX Library
Location: `video/remotion-video/public/sfx/` — 56 approved + 13 banned = 69 total MP3 files

**Approved (56)**: See `.claude/skills/sound-design/SKILL.md` for full descriptions
- Original (27): ocean_waves, wind, desert_wind, water_lapping, birdsong, spring_water, crickets, torch_crackle, cave_reverb, whispers, jewelry_clink, fabric_rustle, metal_ring, ship_creak, paper_rustle, coins_on_wood, candle_flame, glass_set_down, sheets_rustle, clock_ticking, phone_alarm, earth_crack, steam_hiss, crowd_cheer, crowd_murmur, crowd_gasp, factory_ambience
- Expanded V2 (29): temple_echo, silk_rustle, oars_rowing, harbor_ambience, stone_footsteps, horse_distant, shield_impact, ancient_market, light_breeze, strong_gust, rain_window, thunder_distant, night_forest, dawn_chorus, leaves_rustle, sand_blow, seagulls, river_flow, campfire, underwater_deep, bubbling_water, waterfall_distant, tide_wash, rain_gentle, distant_traffic, kitchen_hum, morning_quiet, wooden_door, quill_writing

**Banned (13)**: room_tone, breathing_calm, breathing_restless, marching, war_drums, armor_clank, low_drone, electric_zap, crystal_ring, lab_glass, fluorescent_buzz, water_drip, water_splash_bath

## Pipeline
1. `python3 scripts/generate_scene_manifest.py` — ffprobe all clips → manifest
2. Edit `audioDesigns.ts` — assign layers per scene (empty `[]` = SILENT)
3. `python3 scripts/batch_render_audio.py` — renders audio scenes via Remotion, copies SILENT scenes unchanged
4. Verify: audio scenes have h264+aac, SILENT scenes match original file size

## Volume Hierarchy
- Primary: 0.6-0.8
- Ambient: 0.3-0.5
- Detail: 0.15-0.3

## Diversity Cap
No single sound > 20% of total scenes.

## Output
- Source clips: `{project}/video/clips/`
- Final with audio: `{project}/video/clips_with_audio/`

## Render Performance
- 123 clips (102 audio + 21 SILENT copies) in ~11 min (~5.4s avg per audio scene)
- SILENT copies: <0.1s each

## Critical Rules
- ALWAYS get exact width/height/fps from `ffprobe` — NEVER hardcode dimensions
- Free SFX sources: orangefreesounds.com (CC BY-NC 4.0), freesoundslibrary.com (CC BY 4.0)
- Mixkit has dynamic download URLs — do NOT use for scripted downloads
- PascalCase compIds ≠ snake_case scene keys — must convert between formats
