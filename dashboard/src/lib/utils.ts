import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import { STAGE_MAP, STAGE_ORDER } from "./constants"
import type { Scene } from './types'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Returns true if the production is active, mid-pipeline, and its heartbeat
 * is older than 30 minutes. Productions in terminal phases (complete, delivered)
 * or without a heartbeat are never considered stale.
 */
export function isStale(heartbeatAt: string | null, status: string, currentPhase?: string): boolean {
  if (status !== 'active') return false
  if (!heartbeatAt) return false
  const terminalPhases = ['complete', 'delivered']
  if (currentPhase && terminalPhases.includes(currentPhase)) return false
  const elapsed = Date.now() - new Date(heartbeatAt).getTime()
  return elapsed > 30 * 60 * 1000
}

/**
 * Maps a pipeline phase string to a grouped Kanban stage name.
 * Returns the first stage if the phase is unknown.
 */
export function getStageForPhase(phase: string): string {
  return STAGE_MAP[phase] ?? STAGE_ORDER[0]
}

/**
 * Constructs a public Supabase Storage URL from a storage path.
 * The production-assets bucket is public, so no signing is needed.
 * Using the path directly (not from SSR signedUrls) ensures Realtime
 * scene updates with new image_storage_path values are reflected immediately.
 */
export function getPublicAssetUrl(storagePath: string | null | undefined): string | undefined {
  if (!storagePath) return undefined
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  if (!url) return undefined
  return `${url}/storage/v1/object/public/production-assets/${storagePath}`
}

/**
 * Single source of truth for scene display status.
 * Used by scene grid badges, timeline colors, review queue filter, and production counts.
 */
export function getSceneStatus(scene: Scene): 'generating' | 'regenerating' | 'failed' | 'approved' | 'flagged' | 'deferred' | 'pending' {
  // Active generation states take priority
  if (scene.asset_state === 'generating') return 'generating'
  if (scene.asset_state === 'regenerating') return 'regenerating'
  if (scene.asset_state === 'failed') return 'failed'

  // Derive status from current_gate (most authoritative — set by DB trigger)
  // Use the gate prefix to determine which feedback column is relevant
  const gateParts = scene.current_gate?.split(':')
  const gatePrefix = gateParts?.[0]
  const gateDecision = gateParts?.[1]

  // If current_gate has an explicit decision, trust it
  if (gateDecision === 'approved') return 'approved'
  if (gateDecision === 'flagged') return 'flagged'
  if (gateDecision === 'deferred') return 'deferred'

  // Fallback: check per-gate feedback columns
  // Use the relevant column based on current gate, not OR-chain
  const fb = gatePrefix === 'final_video' ? scene.feedback_final
           : gatePrefix === 'video_clip'  ? scene.feedback_video
           : (scene.feedback_image || scene.feedback)

  if (fb === 'approved') return 'approved'
  if (fb === 'deferred') return 'deferred'
  if ((fb && fb !== 'approved' && fb !== 'deferred') || scene.flag_reasons?.length) return 'flagged'

  return 'pending'
}
