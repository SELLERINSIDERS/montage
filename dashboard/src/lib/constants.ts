export const STAGE_MAP: Record<string, string> = {
  // Script & Design
  script: 'Script & Design',
  storyboard: 'Script & Design',
  scene_design: 'Script & Design',
  camera_plan: 'Script & Design',
  compliance: 'Script & Design',
  // Image Generation
  image_generation: 'Image Gen',
  image_1k: 'Image Gen',
  image_2k: 'Image Gen',
  image_review: 'Image Gen',
  // Video Generation
  video_generation: 'Video Gen',
  video_review: 'Video Gen',
  // Audio & Post
  voiceover: 'Audio & Post',
  sound_design: 'Audio & Post',
  post_production: 'Audio & Post',
  remotion_render: 'Audio & Post',
  // Complete
  complete: 'Complete',
  delivered: 'Complete',
}

export const STAGE_ORDER = [
  'Script & Design',
  'Image Gen',
  'Video Gen',
  'Audio & Post',
  'Complete',
] as const

export const FLAG_REASONS = [
  'Wrong composition',
  'Bad lighting',
  'Character issue',
  'Motion artifact',
  'Wrong scale',
  'Text/overlay issue',
  'Continuity break',
  'Other',
] as const

export const FORMAT_COLORS: Record<string, string> = {
  vsl: 'bg-purple-500/20 text-purple-400',
  ad: 'bg-blue-500/20 text-blue-400',
  ugc: 'bg-green-500/20 text-green-400',
}

export type GateType = 'image_1k' | 'video_clip' | 'final_video'

export const GATE_TYPE_MAP: Record<string, GateType> = {
  image_generation: 'image_1k',
  image_1k: 'image_1k',
  image_2k: 'image_1k',        // 2K approval reuses image_1k gate per user decision
  image_review: 'image_1k',
  video_generation: 'video_clip',
  video_review: 'video_clip',
  post_production: 'final_video',
  remotion_render: 'final_video',
  complete: 'final_video',
} as const

/**
 * Derive the correct gate_type from a scene's own current_gate field.
 * Falls back to the production's global phase via GATE_TYPE_MAP.
 *
 * Scene current_gate format: "{gate_type}:{status}" e.g. "video_clip:generated"
 */
const VALID_GATE_TYPES: Set<string> = new Set(['image_1k', 'image_2k', 'video_clip', 'final_video'])

export function deriveGateType(sceneCurrentGate?: string | null, fallbackPhase?: string): GateType {
  if (sceneCurrentGate) {
    const gateType = sceneCurrentGate.split(':')[0]
    if (VALID_GATE_TYPES.has(gateType)) {
      // image_2k approvals reuse the image_1k gate per existing convention
      return (gateType === 'image_2k' ? 'image_1k' : gateType) as GateType
    }
  }
  if (fallbackPhase) {
    return GATE_TYPE_MAP[fallbackPhase] ?? 'image_1k'
  }
  return 'image_1k'
}

export const KEYBOARD_SHORTCUTS: Record<string, string> = {
  a: 'approve',
  f: 'flag',
  d: 'defer',
  ArrowLeft: 'prev',
  ArrowRight: 'next',
  Escape: 'close',
}
