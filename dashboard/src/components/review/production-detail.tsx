'use client'

import { useState, useEffect, useRef, useMemo } from 'react'
import Link from 'next/link'
import { ArrowLeft, Grid3X3, Clock, PlayCircle, Film, ImageIcon, Video, Layers } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { FORMAT_COLORS } from '@/lib/constants'
import type { Production, Scene } from '@/lib/types'
import { getSceneStatus } from '@/lib/utils'
import { SceneGrid } from './scene-grid'
import { SceneTimeline } from './scene-timeline'
import { ReviewModal } from './review-modal'
import { useReviewQueue } from '@/hooks/use-review-queue'
import { useRealtimeScenes } from '@/hooks/use-realtime-scenes'
import { RegenerationActivity } from './regeneration-activity'

interface SignedUrlMap {
  [sceneId: string]: { thumbnail?: string; image?: string; video?: string }
}

interface ProductionDetailProps {
  production: Production
  scenes: Scene[]
  signedUrls: SignedUrlMap
}

type AssetFilter = 'all' | 'images' | 'video' | 'final'

export function ProductionDetail({ production, scenes, signedUrls }: ProductionDetailProps) {
  const [view, setView] = useState<'grid' | 'timeline'>('grid')
  const [assetFilter, setAssetFilter] = useState<AssetFilter>('all')
  const [modalOpen, setModalOpen] = useState(false)
  const [modalIndex, setModalIndex] = useState(0)
  const [recentlyUpdatedIds, setRecentlyUpdatedIds] = useState<Set<string>>(new Set())
  const prevScenesRef = useRef<Scene[]>(scenes)

  const { scenes: liveScenes, realtimeStatus, showReconnecting, updateSceneOptimistic } = useRealtimeScenes(scenes, production.id)

  // Detect external scene updates and flash those cards
  useEffect(() => {
    const prev = prevScenesRef.current
    const updatedIds = new Set<string>()
    for (const scene of liveScenes) {
      const old = prev.find((s) => s.id === scene.id)
      if (old && old.updated_at !== scene.updated_at) {
        updatedIds.add(scene.id)
      }
    }
    prevScenesRef.current = liveScenes  // Always update, even when changes detected
    if (updatedIds.size > 0) {
      setRecentlyUpdatedIds(updatedIds)
      const timer = setTimeout(() => setRecentlyUpdatedIds(new Set()), 1500)
      return () => clearTimeout(timer)
    }
  }, [liveScenes])

  const reviewQueue = useReviewQueue({ scenes: liveScenes })

  // Filter scenes based on active asset type tab
  const filteredScenes = useMemo(() => {
    switch (assetFilter) {
      case 'images':
        return liveScenes.filter(s => (s.image_storage_path || s.image_1k_status !== 'pending') && !s.video_storage_path && s.video_status === 'pending')
      case 'video':
        return liveScenes.filter(s => s.video_storage_path || s.video_status !== 'pending')
      case 'final':
        return liveScenes.filter(s => s.current_gate?.startsWith('final_video') || s.feedback_final)
      default:
        return liveScenes
    }
  }, [liveScenes, assetFilter])

  // Counts per filter tab
  const filterCounts = useMemo(() => ({
    all: liveScenes.length,
    images: liveScenes.filter(s => (s.image_storage_path || s.image_1k_status !== 'pending') && !s.video_storage_path && s.video_status === 'pending').length,
    video: liveScenes.filter(s => s.video_storage_path || s.video_status !== 'pending').length,
    final: liveScenes.filter(s => s.current_gate?.startsWith('final_video') || s.feedback_final).length,
  }), [liveScenes])

  const name = production.display_name || production.slug
  // Compute live counts from realtime scenes instead of stale SSR production data
  const total = liveScenes.length || production.scene_count
  const approvedCount = liveScenes.filter((s) => getSceneStatus(s) === 'approved').length
  const flaggedCount = liveScenes.filter((s) => getSceneStatus(s) === 'flagged').length
  const generatingCount = liveScenes.filter(
    (s) => getSceneStatus(s) === 'generating' || getSceneStatus(s) === 'regenerating'
  ).length
  const pendingCount = liveScenes.filter((s) => getSceneStatus(s) === 'pending').length
  const approvedPct = total > 0 ? Math.round((approvedCount / total) * 100) : 0

  function handleSceneClick(index: number) {
    setModalIndex(index)
    setModalOpen(true)
  }

  // Pending scenes within the active filter
  const filteredPendingScenes = useMemo(() => {
    const filteredIds = new Set(filteredScenes.map(s => s.id))
    return reviewQueue.pendingScenes.filter(s => filteredIds.has(s.id))
  }, [filteredScenes, reviewQueue.pendingScenes])

  function handleReviewPending() {
    reviewQueue.startReview()
    if (filteredPendingScenes.length > 0) {
      const firstPendingIndex = filteredScenes.findIndex(
        (s) => s.id === filteredPendingScenes[0].id
      )
      setModalIndex(firstPendingIndex >= 0 ? firstPendingIndex : 0)
      setModalOpen(true)
    }
  }

  return (
    <div className="container mx-auto px-4 py-6 max-w-7xl">
      {/* Back button */}
      <Link
        href="/"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="size-4" />
        Back to board
      </Link>

      {/* Production header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{name}</h1>
            <Badge className={FORMAT_COLORS[production.format] ?? 'bg-muted text-muted-foreground'}>
              {production.format.toUpperCase()}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {production.current_phase} &middot; {production.status}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* View toggle */}
          <div className="flex items-center border border-border rounded-lg">
            <Button
              variant={view === 'grid' ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setView('grid')}
            >
              <Grid3X3 className="size-4 mr-1" />
              Grid
            </Button>
            <Button
              variant={view === 'timeline' ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setView('timeline')}
            >
              <Clock className="size-4 mr-1" />
              Timeline
            </Button>
          </div>

          {/* Review Final Video button — shown when post_production exists */}
          {production.manifest_data &&
            !!(production.manifest_data as Record<string, unknown>).post_production && (
              <Link href={`/production/${production.id}/final`}>
                <Button variant="outline" className="gap-1.5">
                  <Film className="size-4" />
                  Review Final Video
                </Button>
              </Link>
            )}

          {/* Review Pending button */}
          <Button onClick={handleReviewPending} className="gap-1.5">
            <PlayCircle className="size-4" />
            Review Pending
            {filteredPendingScenes.length > 0 && (
              <Badge className="bg-yellow-500/20 text-yellow-400 ml-1 text-xs">
                {filteredPendingScenes.length}
              </Badge>
            )}
          </Button>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-6">
        <div className="flex justify-between text-xs text-muted-foreground mb-1">
          <span>
            {approvedCount} approved, {flaggedCount} flagged,{' '}
            {generatingCount > 0 ? `${generatingCount} generating, ` : ''}
            {pendingCount} pending
          </span>
          <span>{approvedPct}%</span>
        </div>
        <div className="h-2 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-green-500 rounded-full transition-all"
            style={{ width: `${approvedPct}%` }}
          />
        </div>
      </div>

      {/* Regeneration activity panel */}
      <div className="mb-4">
        <RegenerationActivity productionId={production.id} />
      </div>

      {/* Asset type filter tabs */}
      <div className="flex items-center gap-2 mb-4">
        <div className="flex items-center border border-border rounded-lg">
          {([
            { key: 'all' as AssetFilter, label: 'All', icon: Layers },
            { key: 'images' as AssetFilter, label: 'Images', icon: ImageIcon },
            { key: 'video' as AssetFilter, label: 'Video', icon: Video },
            { key: 'final' as AssetFilter, label: 'Final', icon: Film },
          ]).map(({ key, label, icon: Icon }) => (
            <Button
              key={key}
              variant={assetFilter === key ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setAssetFilter(key)}
              className="gap-1.5"
            >
              <Icon className="size-4" />
              {label}
              <Badge
                variant="outline"
                className={`ml-0.5 text-[10px] px-1.5 py-0 h-4 ${
                  assetFilter === key ? 'border-primary/50 text-foreground' : 'border-border text-muted-foreground'
                }`}
              >
                {filterCounts[key]}
              </Badge>
            </Button>
          ))}
        </div>
        {assetFilter !== 'all' && (
          <span className="text-xs text-muted-foreground">
            Showing {filteredScenes.length} of {liveScenes.length} scenes
          </span>
        )}
      </div>

      {/* Reconnecting banner */}
      {showReconnecting && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg px-4 py-2 mb-4 text-sm text-yellow-400">
          Reconnecting to live updates...
        </div>
      )}

      {/* Scene views */}
      {view === 'grid' ? (
        <SceneGrid
          scenes={filteredScenes}
          signedUrls={signedUrls}
          onSceneClick={handleSceneClick}
          productionId={production.id}
          currentPhase={production.current_phase}
          recentlyUpdatedIds={recentlyUpdatedIds}
          onOptimisticUpdate={updateSceneOptimistic}
        />
      ) : (
        <SceneTimeline
          scenes={filteredScenes}
          signedUrls={signedUrls}
          onSceneClick={handleSceneClick}
        />
      )}

      {/* Review modal */}
      <ReviewModal
        scenes={filteredScenes}
        initialIndex={modalIndex}
        productionId={production.id}
        currentPhase={production.current_phase}
        open={modalOpen}
        onOpenChange={(open) => {
          setModalOpen(open)
          if (!open) reviewQueue.exitReview()
        }}
        signedUrls={signedUrls}
        reviewMode={reviewQueue.isReviewMode}
        pendingScenes={filteredPendingScenes}
        onOptimisticUpdate={updateSceneOptimistic}
      />
    </div>
  )
}
