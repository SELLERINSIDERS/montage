'use client'

import { useState, useCallback } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Check, Flag, ImageIcon, Video } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { deriveGateType } from '@/lib/constants'
import { getPublicAssetUrl, getSceneStatus } from '@/lib/utils'
import { toast } from 'sonner'
import type { Scene } from '@/lib/types'

interface SignedUrlMap {
  [sceneId: string]: { thumbnail?: string; image?: string; video?: string }
}

interface SceneGridProps {
  scenes: Scene[]
  signedUrls: SignedUrlMap
  onSceneClick: (index: number) => void
  productionId: string
  currentPhase: string
  recentlyUpdatedIds?: Set<string>
  onOptimisticUpdate?: (sceneId: string, patch: Partial<Scene>) => void
}

function getStatusBadge(scene: Scene) {
  const status = getSceneStatus(scene)
  switch (status) {
    case 'generating':
      return <Badge className="bg-purple-500/20 text-purple-400 text-[10px] animate-pulse">Generating</Badge>
    case 'regenerating':
      return <Badge className="bg-purple-500/20 text-purple-400 text-[10px] animate-pulse">Regenerating</Badge>
    case 'failed':
      return <Badge className="bg-red-500/20 text-red-400 text-[10px]">Failed</Badge>
    case 'approved':
      return <Badge className="bg-green-500/20 text-green-400 text-[10px]">Approved</Badge>
    case 'flagged':
      return <Badge className="bg-yellow-500/20 text-yellow-400 text-[10px]">Flagged</Badge>
    case 'deferred':
      return <Badge className="bg-blue-500/20 text-blue-400 text-[10px]">Deferred</Badge>
    default:
      return <Badge className="bg-zinc-500/20 text-zinc-400 text-[10px]">Pending</Badge>
  }
}

export function SceneGrid({ scenes, signedUrls, onSceneClick, productionId, currentPhase, recentlyUpdatedIds, onOptimisticUpdate }: SceneGridProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [batchLoading, setBatchLoading] = useState(false)

  const toggleSelect = useCallback((sceneId: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(sceneId)) {
        next.delete(sceneId)
      } else {
        next.add(sceneId)
      }
      return next
    })
  }, [])

  async function batchDecision(decision: 'approved' | 'flagged') {
    if (selected.size === 0) return
    setBatchLoading(true)

    const GATE_FEEDBACK_FIELD: Record<string, keyof Scene> = {
      image_1k: 'feedback_image',
      video_clip: 'feedback_video',
      final_video: 'feedback_final',
    }

    // Store originals for rollback
    const rollbackPatches: Array<{ id: string; patch: Partial<Scene> }> = []

    // Optimistic update for all selected scenes — derive gate type per scene
    if (onOptimisticUpdate) {
      for (const sceneId of selected) {
        // Find the scene by scene_id to get its UUID
        const scene = scenes.find((s) => s.scene_id === sceneId)
        if (!scene) continue

        const sceneGateType = deriveGateType(scene.current_gate, currentPhase)
        const feedbackField = GATE_FEEDBACK_FIELD[sceneGateType]

        rollbackPatches.push({
          id: scene.id,
          patch: {
            current_gate: scene.current_gate,
            asset_state: scene.asset_state,
            flag_reasons: scene.flag_reasons,
            feedback_image: scene.feedback_image,
            feedback_video: scene.feedback_video,
            feedback_final: scene.feedback_final,
          }
        })
        if (decision === 'approved') {
          onOptimisticUpdate(scene.id, {
            current_gate: `${sceneGateType}:approved`,
            asset_state: 'approved',
            flag_reasons: [],
            ...(feedbackField ? { [feedbackField]: 'approved' } : {}),
          })
        } else {
          onOptimisticUpdate(scene.id, {
            current_gate: `${sceneGateType}:flagged`,
            asset_state: 'flagged',
            flag_reasons: ['Batch flagged'],
            ...(feedbackField ? { [feedbackField]: 'flagged' } : {}),
          })
        }
      }
    }

    try {
      const supabase = createClient()
      const { data: { user } } = await supabase.auth.getUser()
      const decisions = Array.from(selected).map((sceneId) => {
        const scene = scenes.find((s) => s.scene_id === sceneId)
        const sceneGateType = deriveGateType(scene?.current_gate, currentPhase)
        return {
          production_id: productionId,
          scene_id: sceneId,
          gate_type: sceneGateType,
          decision,
          decided_by: user?.id ?? 'anonymous',
          decided_at: new Date().toISOString(),
          synced_to_pipeline: false,
        }
      })

      const { error } = await supabase.from('review_decisions').insert(decisions)
      if (error) throw error

      toast.success(`${decision === 'approved' ? 'Approved' : 'Flagged'} ${selected.size} scenes`, { duration: 2000 })
      setSelected(new Set())
    } catch (err) {
      // Roll back optimistic updates
      if (onOptimisticUpdate) {
        for (const { id, patch } of rollbackPatches) {
          onOptimisticUpdate(id, patch)
        }
      }
      const msg = err instanceof Error ? err.message : (err as { message?: string })?.message ?? 'Unknown error'
      toast.error(`Failed to ${decision}: ${msg}`)
    } finally {
      setBatchLoading(false)
    }
  }

  return (
    <div>
      {/* Batch action bar */}
      {selected.size > 0 && (
        <div className="sticky top-0 z-10 bg-background/95 backdrop-blur border border-border rounded-lg p-3 mb-4 flex items-center gap-3">
          <span className="text-sm text-muted-foreground">{selected.size} selected</span>
          <Button
            size="sm"
            className="bg-green-600 hover:bg-green-700 text-white gap-1"
            onClick={() => batchDecision('approved')}
            disabled={batchLoading}
          >
            <Check className="size-3.5" />
            Approve Selected ({selected.size})
          </Button>
          <Button
            size="sm"
            className="bg-yellow-600 hover:bg-yellow-700 text-white gap-1"
            onClick={() => batchDecision('flagged')}
            disabled={batchLoading}
          >
            <Flag className="size-3.5" />
            Flag Selected ({selected.size})
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSelected(new Set())}
          >
            Clear
          </Button>
        </div>
      )}

      {/* Scene grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {scenes.map((scene, index) => {
          // Derive URL directly from live scene data so Realtime updates
          // (new image_storage_path after regeneration) are reflected immediately.
          // Falls back to SSR signedUrls for videos or missing paths.
          const urls = signedUrls[scene.id]
          const thumbUrl =
            getPublicAssetUrl(scene.thumbnail_storage_path || scene.image_storage_path) ||
            urls?.thumbnail ||
            urls?.image
          const isSelected = selected.has(scene.scene_id)
          const isRecentlyUpdated = recentlyUpdatedIds?.has(scene.id)

          return (
            <div
              key={scene.id}
              className={`relative group rounded-lg border overflow-hidden transition-all ${
                isSelected ? 'border-primary ring-2 ring-primary/50' : isRecentlyUpdated ? 'ring-2 ring-yellow-400/40 animate-pulse border-yellow-400/30' : 'border-border hover:border-accent'
              }`}
            >
              {/* Checkbox overlay */}
              <div
                className="absolute top-2 left-2 z-10"
                onClick={(e) => {
                  e.stopPropagation()
                  toggleSelect(scene.scene_id)
                }}
              >
                <div
                  className={`size-5 rounded border-2 flex items-center justify-center cursor-pointer transition-colors ${
                    isSelected
                      ? 'bg-primary border-primary text-primary-foreground'
                      : 'border-zinc-400 bg-black/40 opacity-0 group-hover:opacity-100'
                  }`}
                >
                  {isSelected && <Check className="size-3" />}
                </div>
              </div>

              {/* Thumbnail area - clickable */}
              <div
                className="aspect-video bg-muted cursor-pointer relative"
                onClick={() => onSceneClick(index)}
              >
                {thumbUrl ? (
                  <img
                    src={thumbUrl}
                    alt={`Scene ${scene.scene_id}`}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-muted-foreground text-xs">
                    No thumbnail
                  </div>
                )}
                {/* Asset type indicator */}
                {scene.video_storage_path ? (
                  <div className="absolute bottom-1.5 right-1.5 bg-black/50 rounded px-1 py-0.5 flex items-center">
                    <Video className="size-3.5 text-white/90" />
                  </div>
                ) : scene.image_storage_path ? (
                  <div className="absolute bottom-1.5 right-1.5 bg-black/50 rounded px-1 py-0.5 flex items-center">
                    <ImageIcon className="size-3.5 text-white/90" />
                  </div>
                ) : null}
              </div>

              {/* Scene info */}
              <div className="p-2 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium">{scene.scene_id}</span>
                  {getStatusBadge(scene)}
                </div>
                {scene.prompt_text && (
                  <p className="text-xs text-muted-foreground line-clamp-2">
                    {scene.prompt_text}
                  </p>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
