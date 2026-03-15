'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { createClient } from '@/lib/supabase/client'
import { deriveGateType, type GateType } from '@/lib/constants'
import { toast } from 'sonner'
import type { Scene } from '@/lib/types'
import { ReviewActions } from './review-actions'
import { FlagDialog } from './flag-dialog'
import { useKeyboardShortcuts } from '@/hooks/use-keyboard-shortcuts'
import { getPublicAssetUrl } from '@/lib/utils'

interface SignedUrlMap {
  [sceneId: string]: { thumbnail?: string; image?: string; video?: string }
}

interface ReviewModalProps {
  scenes: Scene[]
  initialIndex: number
  productionId: string
  currentPhase: string
  open: boolean
  onOpenChange: (open: boolean) => void
  signedUrls: SignedUrlMap
  reviewMode: boolean
  pendingScenes: Scene[]
  onOptimisticUpdate: (sceneId: string, patch: Partial<Scene>) => void
}

export function ReviewModal({
  scenes,
  initialIndex,
  productionId,
  currentPhase,
  open,
  onOpenChange,
  signedUrls,
  reviewMode,
  pendingScenes,
  onOptimisticUpdate,
}: ReviewModalProps) {
  const [currentIndex, setCurrentIndex] = useState(initialIndex)
  const [flagDialogOpen, setFlagDialogOpen] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const touchStartRef = useRef<number | null>(null)

  // Sync initialIndex when it changes from outside
  useEffect(() => {
    setCurrentIndex(initialIndex)
  }, [initialIndex])

  const scene = scenes[currentIndex]

  const navigateNext = useCallback(() => {
    if (reviewMode && pendingScenes.length > 0) {
      // In review mode, find the next pending scene after current
      const currentPendingIdx = pendingScenes.findIndex((s) => s.id === scene?.id)
      if (currentPendingIdx >= 0 && currentPendingIdx < pendingScenes.length - 1) {
        const nextPending = pendingScenes[currentPendingIdx + 1]
        const nextIdx = scenes.findIndex((s) => s.id === nextPending.id)
        if (nextIdx >= 0) setCurrentIndex(nextIdx)
      }
    } else {
      setCurrentIndex((prev) => Math.min(prev + 1, scenes.length - 1))
    }
  }, [reviewMode, pendingScenes, scene, scenes])

  const navigatePrev = useCallback(() => {
    if (reviewMode && pendingScenes.length > 0) {
      const currentPendingIdx = pendingScenes.findIndex((s) => s.id === scene?.id)
      if (currentPendingIdx > 0) {
        const prevPending = pendingScenes[currentPendingIdx - 1]
        const prevIdx = scenes.findIndex((s) => s.id === prevPending.id)
        if (prevIdx >= 0) setCurrentIndex(prevIdx)
      }
    } else {
      setCurrentIndex((prev) => Math.max(prev - 1, 0))
    }
  }, [reviewMode, pendingScenes, scene, scenes])

  const handleClose = useCallback(() => {
    onOpenChange(false)
  }, [onOpenChange])

  // Feedback field mapping for optimistic updates
  const GATE_FEEDBACK_FIELD: Record<string, keyof Scene> = {
    image_1k: 'feedback_image',
    video_clip: 'feedback_video',
    final_video: 'feedback_final',
  }

  // Direct decision writer for keyboard shortcuts
  const writeDecision = useCallback(async (decision: 'approved' | 'deferred') => {
    if (!scene) return

    // Capture next pending scene BEFORE optimistic update removes current from queue
    let nextSceneIndex: number | null = null
    if (reviewMode && pendingScenes.length > 1) {
      const currentPendingIdx = pendingScenes.findIndex(s => s.id === scene.id)
      const nextPending = pendingScenes[currentPendingIdx + 1] ?? pendingScenes[currentPendingIdx - 1]
      if (nextPending) {
        nextSceneIndex = scenes.findIndex(s => s.id === nextPending.id)
      }
    }

    // Optimistic update so badge changes immediately (same logic as ReviewActions)
    const gateType: GateType = deriveGateType(scene.current_gate, currentPhase)
    const feedbackField = GATE_FEEDBACK_FIELD[gateType]
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
      setTimeout(() => {
        if (nextSceneIndex !== null && nextSceneIndex >= 0) {
          setCurrentIndex(nextSceneIndex)
        } else {
          navigateNext()
        }
      }, 300)
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
    }
  }, [scene, productionId, currentPhase, reviewMode, pendingScenes, scenes, navigateNext, onOptimisticUpdate])

  const handleApprove = useCallback(() => {
    writeDecision('approved')
  }, [writeDecision])

  const handleFlag = useCallback(() => {
    setFlagDialogOpen(true)
  }, [])

  const handleDefer = useCallback(() => {
    writeDecision('deferred')
  }, [writeDecision])

  // Keyboard shortcuts
  useKeyboardShortcuts({
    actions: {
      approve: handleApprove,
      flag: handleFlag,
      defer: handleDefer,
      prev: navigatePrev,
      next: navigateNext,
      close: handleClose,
    },
    enabled: open && !flagDialogOpen,
  })

  // Autoplay video on scene change
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.load()
      videoRef.current.play().catch(() => {
        // Autoplay may be blocked by browser
      })
    }
  }, [currentIndex])

  // Touch handlers for swipe navigation
  function handleTouchStart(e: React.TouchEvent) {
    touchStartRef.current = e.touches[0].clientX
  }

  function handleTouchEnd(e: React.TouchEvent) {
    if (touchStartRef.current === null) return
    const diff = e.changedTouches[0].clientX - touchStartRef.current
    touchStartRef.current = null
    if (Math.abs(diff) > 50) {
      if (diff > 0) navigatePrev()
      else navigateNext()
    }
  }

  if (!open || !scene) return null

  const urls = signedUrls[scene.id]
  // Derive video URL from live scene data — reflects Realtime updates after regeneration.
  // Falls back to signed URL for backwards compatibility with scenes that lack video_storage_path.
  const videoUrl =
    getPublicAssetUrl(scene.video_storage_path) ||
    urls?.video
  // Derive image URL directly from live scene data — reflects Realtime updates immediately.
  const imageUrl =
    getPublicAssetUrl(scene.image_storage_path || scene.thumbnail_storage_path) ||
    urls?.image ||
    urls?.thumbnail

  function handleDecision(decision: 'approved' | 'flagged' | 'deferred') {
    // Auto-advance after approve or defer
    if (decision === 'approved' || decision === 'deferred') {
      setTimeout(() => navigateNext(), 300)
    }
  }

  function handleFlagged() {
    setFlagDialogOpen(false)
    setTimeout(() => navigateNext(), 300)
  }

  // Position in review queue
  const queuePosition = reviewMode
    ? `${pendingScenes.findIndex((s) => s.id === scene.id) + 1} of ${pendingScenes.length} pending`
    : `${currentIndex + 1} of ${scenes.length}`

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/90 flex flex-col" role="dialog" aria-modal="true">
        {/* Top bar */}
        <div className="flex items-center justify-between px-4 py-2 bg-black/50">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">Scene {scene.scene_id}</span>
            {reviewMode && (
              <Badge className="bg-yellow-500/20 text-yellow-400 text-[10px]">Review Mode</Badge>
            )}
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground">{queuePosition}</span>
            <Button variant="ghost" size="icon-sm" onClick={handleClose}>
              <X className="size-4" />
            </Button>
          </div>
        </div>

        {/* Main content */}
        <div
          className="flex-1 flex flex-col lg:flex-row min-h-0"
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
        >
          {/* Media area (70%) */}
          <div className="flex-1 lg:w-[70%] relative flex items-center justify-center p-4">
            {/* Left arrow */}
            <Button
              variant="ghost"
              size="icon"
              className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/40 hover:bg-black/60 z-10"
              onClick={navigatePrev}
              disabled={
                reviewMode
                  ? pendingScenes.findIndex((s) => s.id === scene.id) <= 0
                  : currentIndex <= 0
              }
            >
              <ChevronLeft className="size-6" />
            </Button>

            {/* Media player */}
            <div className="w-full max-h-full flex items-center justify-center">
              {videoUrl ? (
                <video
                  ref={videoRef}
                  src={videoUrl}
                  controls
                  className="max-w-full max-h-[calc(100vh-200px)] rounded-lg"
                  playsInline
                >
                  Your browser does not support the video tag.
                </video>
              ) : imageUrl ? (
                <img
                  src={imageUrl}
                  alt={`Scene ${scene.scene_id}`}
                  className="max-w-full max-h-[calc(100vh-200px)] rounded-lg object-contain"
                />
              ) : (
                <div className="flex items-center justify-center w-full h-64 bg-muted rounded-lg">
                  <p className="text-muted-foreground">No media generated yet</p>
                </div>
              )}
            </div>

            {/* Right arrow */}
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/40 hover:bg-black/60 z-10"
              onClick={navigateNext}
              disabled={
                reviewMode
                  ? pendingScenes.findIndex((s) => s.id === scene.id) >= pendingScenes.length - 1
                  : currentIndex >= scenes.length - 1
              }
            >
              <ChevronRight className="size-6" />
            </Button>
          </div>

          {/* Sidebar (30%) */}
          <div className="lg:w-[30%] border-t lg:border-t-0 lg:border-l border-border bg-card/50 flex flex-col">
            <ScrollArea className="flex-1">
              <div className="p-4 space-y-4">
                {/* Scene info */}
                <div>
                  <h3 className="text-sm font-semibold">
                    Scene {scene.scene_index + 1} of {scenes.length}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">{scene.scene_id}</p>
                </div>

                {/* Scene prompt */}
                {scene.prompt_text && (
                  <div>
                    <h4 className="text-xs font-medium text-muted-foreground mb-1">Scene Prompt</h4>
                    <p className="text-sm leading-relaxed">{scene.prompt_text}</p>
                  </div>
                )}

                {/* Gate info */}
                <div className="space-y-1">
                  <h4 className="text-xs font-medium text-muted-foreground">Gate Status</h4>
                  <div className="flex items-center gap-2 text-sm">
                    <span>Current gate:</span>
                    <Badge variant="outline" className="text-xs">
                      {scene.current_gate || 'None'}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Attempts: {scene.gate_attempts}
                  </p>
                </div>

                {/* Gate timing */}
                {scene.gate_timing && Object.keys(scene.gate_timing).length > 0 && (
                  <div>
                    <h4 className="text-xs font-medium text-muted-foreground mb-1">Gate History</h4>
                    <div className="space-y-1">
                      {Object.entries(scene.gate_timing).map(([gate, timing]) => (
                        <div key={gate} className="text-xs text-muted-foreground">
                          {gate}: {typeof timing === 'string' ? timing : JSON.stringify(timing)}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Per-gate feedback */}
                {(scene.feedback_image || scene.feedback_video || scene.feedback_final || scene.feedback) && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-medium text-muted-foreground">Feedback</h4>
                    {scene.feedback_image && (
                      <div className="text-sm">
                        <span className="text-xs text-muted-foreground">Image: </span>
                        {scene.feedback_image}
                      </div>
                    )}
                    {scene.feedback_video && (
                      <div className="text-sm">
                        <span className="text-xs text-muted-foreground">Video: </span>
                        {scene.feedback_video}
                      </div>
                    )}
                    {scene.feedback_final && (
                      <div className="text-sm">
                        <span className="text-xs text-muted-foreground">Final: </span>
                        {scene.feedback_final}
                      </div>
                    )}
                    {scene.feedback && !scene.feedback_image && !scene.feedback_video && !scene.feedback_final && (
                      <div className="text-sm">
                        <span className="text-xs text-muted-foreground">Legacy: </span>
                        {scene.feedback}
                      </div>
                    )}
                  </div>
                )}

                {/* Existing flag reasons */}
                {scene.flag_reasons && scene.flag_reasons.length > 0 && (
                  <div>
                    <h4 className="text-xs font-medium text-muted-foreground mb-1">Flag Reasons</h4>
                    <div className="flex flex-wrap gap-1">
                      {scene.flag_reasons.map((reason) => (
                        <Badge
                          key={reason}
                          variant="outline"
                          className="text-yellow-400 border-yellow-400 text-[10px]"
                        >
                          {reason}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Asset status */}
                <div className="space-y-1">
                  <h4 className="text-xs font-medium text-muted-foreground">Asset Status</h4>
                  <div className="grid grid-cols-2 gap-1 text-xs">
                    <span className="text-muted-foreground">Image 1K:</span>
                    <span>{scene.image_1k_status}</span>
                    <span className="text-muted-foreground">Image 2K:</span>
                    <span>{scene.image_2k_status}</span>
                    <span className="text-muted-foreground">Video:</span>
                    <span>{scene.video_status}</span>
                  </div>
                </div>
              </div>
            </ScrollArea>

            {/* Review actions pinned at bottom */}
            <div className="p-4 border-t border-border">
              <ReviewActions
                scene={scene}
                productionId={productionId}
                currentPhase={currentPhase}
                sceneCurrentGate={scene.current_gate}
                onDecision={handleDecision}
                onFlagRequest={() => setFlagDialogOpen(true)}
                onOptimisticUpdate={onOptimisticUpdate}
              />
            </div>
          </div>
        </div>

        {/* Bottom scene counter */}
        <div className="flex justify-center py-2 bg-black/50">
          <div className="flex gap-1">
            {scenes.length <= 20 ? (
              // Show dots for small scene counts
              scenes.map((s, i) => (
                <button
                  key={s.id}
                  className={`size-2 rounded-full transition-colors ${
                    i === currentIndex ? 'bg-white' : 'bg-white/30 hover:bg-white/50'
                  }`}
                  onClick={() => setCurrentIndex(i)}
                />
              ))
            ) : (
              // Show text counter for large scene counts
              <span className="text-xs text-muted-foreground">
                {currentIndex + 1} / {scenes.length}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Flag dialog */}
      <FlagDialog
        scene={scene}
        productionId={productionId}
        currentPhase={currentPhase}
        sceneCurrentGate={scene.current_gate}
        open={flagDialogOpen}
        onClose={() => setFlagDialogOpen(false)}
        onFlagged={handleFlagged}
        onOptimisticUpdate={onOptimisticUpdate}
      />
    </>
  )
}
