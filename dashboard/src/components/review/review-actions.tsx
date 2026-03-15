'use client'

import { useState } from 'react'
import { Check, Flag, Clock, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { createClient } from '@/lib/supabase/client'
import { deriveGateType } from '@/lib/constants'
import { toast } from 'sonner'
import type { Scene } from '@/lib/types'

const GATE_FEEDBACK_FIELD: Record<string, keyof Scene> = {
  image_1k: 'feedback_image',
  video_clip: 'feedback_video',
  final_video: 'feedback_final',
}

interface ReviewActionsProps {
  scene: Scene
  productionId: string
  currentPhase: string
  sceneCurrentGate?: string | null
  onDecision: (decision: 'approved' | 'flagged' | 'deferred') => void
  onFlagRequest: () => void
  onOptimisticUpdate: (sceneId: string, patch: Partial<Scene>) => void
}

export function ReviewActions({ scene, productionId, currentPhase, sceneCurrentGate, onDecision, onFlagRequest, onOptimisticUpdate }: ReviewActionsProps) {
  const [loading, setLoading] = useState<string | null>(null)

  async function handleDecision(decision: 'approved' | 'deferred') {
    setLoading(decision)
    // Optimistic update — badge changes immediately
    const gateType = deriveGateType(sceneCurrentGate, currentPhase)
    const feedbackField = GATE_FEEDBACK_FIELD[gateType]

    // Build a complete optimistic patch that satisfies all getStatusBadge() checks
    const optimisticPatch: Partial<Scene> = {
      current_gate: `${gateType}:${decision}`,
      ...(feedbackField ? { [feedbackField]: decision } : {}),
      ...(decision === 'approved'
        ? { asset_state: 'approved', flag_reasons: [] }
        : {}),
      ...(decision === 'deferred' ? { flag_reasons: [] } : {}),
    }

    onOptimisticUpdate(scene.id, optimisticPatch)

    try {
      const supabase = createClient()
      const { data: { user } } = await supabase.auth.getUser()
      const { error } = await supabase.from('review_decisions').insert({
        production_id: productionId,
        scene_id: scene.scene_id,
        gate_type: gateType,
        decision,
        decided_by: user?.id ?? 'anonymous',
        decided_at: new Date().toISOString(),
        synced_to_pipeline: false,
      })
      if (error) throw error
      toast.success('Scene synced', { duration: 2000 })
      onDecision(decision)
    } catch (err) {
      // Roll back optimistic update on failure
      onOptimisticUpdate(scene.id, {
        current_gate: scene.current_gate,
        asset_state: scene.asset_state,
        flag_reasons: scene.flag_reasons,
        ...(feedbackField ? { [feedbackField]: scene[feedbackField] as string | null } : {}),
      })
      const msg = err instanceof Error ? err.message : (err as { message?: string })?.message ?? 'Unknown error'
      toast.error(`Failed to ${decision}: ${msg}`)
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className="flex gap-2">
      <Button
        className="flex-1 bg-green-600 hover:bg-green-700 text-white gap-1.5"
        onClick={() => handleDecision('approved')}
        disabled={loading !== null}
      >
        {loading === 'approved' ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <Check className="size-4" />
        )}
        Approve
        <kbd className="ml-1 text-[10px] opacity-60 bg-white/10 px-1 rounded">A</kbd>
      </Button>

      <Button
        className="flex-1 bg-yellow-600 hover:bg-yellow-700 text-white gap-1.5"
        onClick={onFlagRequest}
        disabled={loading !== null}
      >
        <Flag className="size-4" />
        Flag
        <kbd className="ml-1 text-[10px] opacity-60 bg-white/10 px-1 rounded">F</kbd>
      </Button>

      <Button
        className="flex-1 bg-blue-600 hover:bg-blue-700 text-white gap-1.5"
        onClick={() => handleDecision('deferred')}
        disabled={loading !== null}
      >
        {loading === 'deferred' ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <Clock className="size-4" />
        )}
        Defer
        <kbd className="ml-1 text-[10px] opacity-60 bg-white/10 px-1 rounded">D</kbd>
      </Button>
    </div>
  )
}
