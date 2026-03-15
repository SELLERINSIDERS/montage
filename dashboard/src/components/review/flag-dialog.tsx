'use client'

import { useState, useEffect } from 'react'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { createClient } from '@/lib/supabase/client'
import { FLAG_REASONS, deriveGateType, type GateType } from '@/lib/constants'
import { toast } from 'sonner'
import type { Scene } from '@/lib/types'

interface FlagDialogProps {
  scene: Scene
  productionId: string
  currentPhase: string
  sceneCurrentGate?: string | null
  open: boolean
  onClose: () => void
  onFlagged: () => void
  onOptimisticUpdate?: (sceneId: string, patch: Partial<Scene>) => void
}

export function FlagDialog({ scene, productionId, currentPhase, sceneCurrentGate, open, onClose, onFlagged, onOptimisticUpdate }: FlagDialogProps) {
  const [selectedReasons, setSelectedReasons] = useState<string[]>([])
  const [feedback, setFeedback] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedGateType, setSelectedGateType] = useState<GateType>(() => deriveGateType(sceneCurrentGate, currentPhase))

  // Reset the gate type selector when dialog opens or scene changes
  useEffect(() => {
    if (open) {
      setSelectedGateType(deriveGateType(sceneCurrentGate, currentPhase))
    }
  }, [open, sceneCurrentGate, currentPhase])

  if (!open) return null

  function toggleReason(reason: string) {
    setSelectedReasons((prev) =>
      prev.includes(reason) ? prev.filter((r) => r !== reason) : [...prev, reason]
    )
  }

  async function handleSubmit() {
    if (selectedReasons.length === 0) return
    setLoading(true)

    const gateType = selectedGateType

    const GATE_FEEDBACK_FIELD: Record<string, keyof Scene> = {
      image_1k: 'feedback_image',
      video_clip: 'feedback_video',
      final_video: 'feedback_final',
    }
    const feedbackField = GATE_FEEDBACK_FIELD[gateType]
    const feedbackValue = selectedReasons.join(', ') + (feedback.trim() ? ` -- ${feedback.trim()}` : '')

    // Optimistic update so badge shows "Flagged" immediately
    if (onOptimisticUpdate) {
      onOptimisticUpdate(scene.id, {
        current_gate: `${gateType}:flagged`,
        flag_reasons: selectedReasons,
        asset_state: 'flagged',
        ...(feedbackField ? { [feedbackField]: feedbackValue } : {}),
      })
    }

    try {
      const supabase = createClient()
      const { data: { user } } = await supabase.auth.getUser()
      const { error } = await supabase.from('review_decisions').insert({
        production_id: productionId,
        scene_id: scene.scene_id,
        gate_type: gateType,
        decision: 'flagged',
        flag_reasons: selectedReasons,
        feedback: feedback.trim() || null,
        decided_by: user?.id ?? 'anonymous',
        decided_at: new Date().toISOString(),
        synced_to_pipeline: false,
      })
      if (error) throw error
      toast.success('Scene synced', { duration: 2000 })
      setSelectedReasons([])
      setFeedback('')
      onFlagged()
    } catch (err) {
      // Roll back optimistic update on failure
      if (onOptimisticUpdate) {
        onOptimisticUpdate(scene.id, {
          current_gate: scene.current_gate,
          flag_reasons: scene.flag_reasons,
          asset_state: scene.asset_state,
          ...(feedbackField ? { [feedbackField]: scene[feedbackField] as string | null } : {}),
        })
      }
      const msg = err instanceof Error ? err.message : (err as { message?: string })?.message ?? 'Unknown error'
      toast.error(`Failed to flag: ${msg}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[60] bg-black/60 flex items-center justify-center">
      <div
        className="bg-card rounded-xl border border-border p-5 w-full max-w-md mx-4 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div>
          <h3 className="text-base font-semibold">Flag Scene {scene.scene_id}</h3>
          <p className="text-sm text-muted-foreground mt-1">
            Select at least one reason for flagging this scene.
          </p>
        </div>

        {/* Regeneration target selector */}
        <div>
          <label className="text-sm text-muted-foreground block mb-2">
            What should be regenerated?
          </label>
          <div className="flex gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="gate-type"
                value="image_1k"
                checked={selectedGateType === 'image_1k'}
                onChange={() => setSelectedGateType('image_1k')}
                className="accent-primary"
              />
              <span className="text-sm">Image</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="gate-type"
                value="video_clip"
                checked={selectedGateType === 'video_clip'}
                onChange={() => setSelectedGateType('video_clip')}
                className="accent-primary"
              />
              <span className="text-sm">Video</span>
            </label>
          </div>
        </div>

        {/* Reason checkboxes */}
        <div className="space-y-2">
          {FLAG_REASONS.map((reason) => (
            <label
              key={reason}
              className="flex items-center gap-2.5 cursor-pointer group"
            >
              <div
                className={`size-4 rounded border flex items-center justify-center transition-colors ${
                  selectedReasons.includes(reason)
                    ? 'bg-primary border-primary'
                    : 'border-zinc-500 group-hover:border-zinc-400'
                }`}
                onClick={() => toggleReason(reason)}
              >
                {selectedReasons.includes(reason) && (
                  <svg
                    className="size-3 text-primary-foreground"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={3}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </div>
              <span className="text-sm">{reason}</span>
            </label>
          ))}
        </div>

        {/* Free-text feedback */}
        <div>
          <label className="text-sm text-muted-foreground block mb-1">
            Additional feedback (optional)
          </label>
          <textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Describe the issue in detail..."
            className="w-full h-20 bg-muted border border-border rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button
            className="bg-yellow-600 hover:bg-yellow-700 text-white gap-1.5"
            onClick={handleSubmit}
            disabled={selectedReasons.length === 0 || loading}
          >
            {loading && <Loader2 className="size-4 animate-spin" />}
            Flag Scene
          </Button>
        </div>
      </div>
    </div>
  )
}
