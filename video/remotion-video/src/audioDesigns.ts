/**
 * Audio Design Map — Example VSL (3 Scenes)
 *
 * This file maps scene IDs to their audio layers for SFX overlay.
 * Replace with your own scene audio designs.
 *
 * Volume hierarchy (ALWAYS enforced):
 *   Primary  0.6-0.8  (dominant sound matching main visual)
 *   Ambient  0.3-0.5  (continuous background atmosphere)
 *   Detail   0.15-0.3 (small realism sounds, often delayed)
 */

import type { AudioLayer } from "./SceneWithAudio";

export const SCENE_AUDIO: Record<string, AudioLayer[]> = {
  // Example scene with layered audio
  scene_01: [
    { src: "sfx/ambient_wind.mp3", volume: 0.7, loop: true, fadeIn: true },
    { src: "sfx/birds.mp3", volume: 0.3, loop: true },
  ],

  // Example silent scene
  scene_02: [],

  // Example scene with delayed detail sound
  scene_03: [
    { src: "sfx/water_flow.mp3", volume: 0.6, loop: true },
    { src: "sfx/stone_step.mp3", volume: 0.2, loop: false, delaySeconds: 0.5 },
  ],
};
