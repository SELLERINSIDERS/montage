'use client'

import { useState, useCallback, useEffect } from 'react'
import { createClient } from '@/lib/supabase/client'
import { toast } from 'sonner'
import {
  VideoPlayerWithMarkers,
  type VideoScene,
} from '@/components/review/video-player-with-markers'
import {
  FinalSceneGrid,
  type FinalScene,
} from '@/components/review/final-scene-grid'
import {
  VersionTimeline,
  type VideoVersion,
} from '@/components/review/version-timeline'

interface FinalReviewProps {
  productionId: string
  initialScenes: FinalScene[]
  initialVersions: VideoVersion[]
}

export function FinalReview({
  productionId,
  initialScenes,
  initialVersions,
}: FinalReviewProps) {
  const [scenes] = useState<FinalScene[]>(initialScenes)
  const [versions, setVersions] = useState<VideoVersion[]>(initialVersions)
  const [currentVersion, setCurrentVersion] = useState<number>(
    initialVersions.length > 0
      ? initialVersions[initialVersions.length - 1].version
      : 0
  )
  const [activeSceneId, setActiveSceneId] = useState<string | undefined>()
  const [seekTime, setSeekTime] = useState<number | undefined>()
  const [approving, setApproving] = useState(false)

  // Current video URL
  const currentVideoVersion = versions.find((v) => v.version === currentVersion)
  const videoSrc = currentVideoVersion?.storage_url ?? ''

  // Map FinalScene to VideoScene for the player
  const videoScenes: VideoScene[] = scenes.map((s) => ({
    id: s.id,
    label: s.label,
    start_s: s.start_s,
    duration_s: s.duration_s,
  }))

  // Scene click handler - seek video
  const handleSceneClick = useCallback((sceneId: string, startTime: number) => {
    setSeekTime(startTime)
    setActiveSceneId(sceneId)
  }, [])

  // Scene change from video playback
  const handleSceneChange = useCallback((sceneId: string) => {
    setActiveSceneId(sceneId)
  }, [])

  // Version select - switch video
  const handleVersionSelect = useCallback((version: VideoVersion) => {
    setCurrentVersion(version.version)
  }, [])

  // Approve final
  const handleApprove = useCallback(
    async (version: VideoVersion) => {
      setApproving(true)
      try {
        const supabase = createClient()

        // Mark version approved in production_videos
        const { error: vError } = await supabase
          .from('production_videos')
          .update({ is_approved: true, updated_at: new Date().toISOString() })
          .eq('production_id', productionId)
          .eq('version', version.version)

        if (vError) throw vError

        // Update production status
        const { error: pError } = await supabase
          .from('productions')
          .update({
            current_stage: 'Complete',
            current_phase: 'complete',
            status: 'completed',
            completed_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          })
          .eq('id', productionId)

        if (pError) throw pError

        // Update local state
        setVersions((prev) =>
          prev.map((v) =>
            v.version === version.version ? { ...v, is_approved: true } : v
          )
        )

        toast.success(`Version ${version.version} approved as final!`)
      } catch (err) {
        const msg = err instanceof Error ? err.message : (err as { message?: string })?.message ?? 'Unknown error'
        toast.error(`Failed to approve: ${msg}`)
      } finally {
        setApproving(false)
      }
    },
    [productionId]
  )

  // Reset seek time after seeking
  useEffect(() => {
    if (seekTime !== undefined) {
      const timer = setTimeout(() => setSeekTime(undefined), 100)
      return () => clearTimeout(timer)
    }
  }, [seekTime])

  if (!videoSrc) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No rendered video available yet. Render a preview or final version first.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Main layout: video + scene grid */}
      <div className="flex flex-col lg:flex-row gap-4">
        {/* Video player - 60% on desktop */}
        <div className="lg:w-3/5 space-y-3">
          <VideoPlayerWithMarkers
            src={videoSrc}
            scenes={videoScenes}
            onSceneChange={handleSceneChange}
            seekToTime={seekTime}
          />

          {/* Version timeline below player */}
          <VersionTimeline
            versions={versions}
            currentVersion={currentVersion}
            onVersionSelect={handleVersionSelect}
            onApprove={handleApprove}
          />
        </div>

        {/* Scene grid sidebar - 40% on desktop */}
        <div className="lg:w-2/5">
          <h3 className="text-sm font-medium text-muted-foreground mb-2">
            Scenes ({scenes.length})
          </h3>
          <div className="max-h-[70vh] overflow-y-auto pr-1">
            <FinalSceneGrid
              scenes={scenes}
              activeSceneId={activeSceneId}
              onSceneClick={handleSceneClick}
            />
          </div>
        </div>
      </div>

      {/* Approval status banner */}
      {versions.some((v) => v.is_approved) && (
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4 text-center">
          <p className="text-green-400 font-medium">
            Final version approved. Production is complete.
          </p>
        </div>
      )}

      {approving && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-card rounded-lg p-6 text-center">
            <p className="text-sm">Approving final version...</p>
          </div>
        </div>
      )}
    </div>
  )
}
