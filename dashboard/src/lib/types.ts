import type { STAGE_ORDER } from './constants'

export type Stage = (typeof STAGE_ORDER)[number]

export type Format = 'vsl' | 'ad' | 'ugc'

export type ProductionStatus = 'active' | 'paused' | 'completed' | 'error'

export interface Production {
  id: string
  format: Format
  slug: string
  display_name: string | null
  current_phase: string
  current_stage: string
  scene_count: number
  approved_count: number
  flagged_count: number
  pending_count: number
  latest_thumbnail_url: string | null
  heartbeat_at: string | null
  status: ProductionStatus
  manifest_data: Record<string, unknown> | null
  created_at: string
  updated_at: string
  completed_at: string | null
  user_id: string
}

export interface Scene {
  id: string
  production_id: string
  scene_id: string
  scene_index: number
  prompt_text: string | null
  image_1k_status: string
  image_2k_status: string
  video_status: string
  current_gate: string | null
  gate_attempts: number
  feedback: string | null
  feedback_image: string | null
  feedback_video: string | null
  feedback_final: string | null
  flag_reasons: string[] | null
  image_storage_path: string | null
  video_storage_path: string | null
  thumbnail_storage_path: string | null
  gate_timing: Record<string, unknown> | null
  regeneration_count: number
  prompt_version: number
  asset_state: string | null // 'pending' | 'generating' | 'generated' | 'approved' | 'flagged' | 'regenerating' | 'failed'
  updated_at: string
}

export interface ReviewDecision {
  id: string
  production_id: string
  scene_id: string
  gate_type: string
  decision: 'approved' | 'flagged' | 'deferred'
  flag_reasons: string[] | null
  feedback: string | null
  decided_by: string | null
  decided_at: string
  synced_to_pipeline: boolean
}
