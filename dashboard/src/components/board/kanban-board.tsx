'use client'

import { useState, useMemo, useEffect, Suspense } from 'react'
import { useRouter } from 'next/navigation'
import { STAGE_ORDER } from '@/lib/constants'
import { isStale } from '@/lib/utils'
import { StageColumn } from './stage-column'
import {
  FilterBar,
  type FormatFilter,
  type StatusFilter,
  type SortOption,
} from './filter-bar'
import { useRealtimeProductions } from '@/hooks/use-realtime-productions'
import { StaleDetector } from '@/components/notifications/stale-detector'
import { useReviewCount } from '@/lib/review-count-context'
import type { Production } from '@/lib/types'

interface KanbanBoardProps {
  initialData: Production[]
}

export function KanbanBoard({ initialData }: KanbanBoardProps) {
  const router = useRouter()
  const { productions: liveProductions, realtimeStatus } = useRealtimeProductions(initialData)
  const { setReviewCount } = useReviewCount()

  // Refresh SSR data when user navigates back to this page (tab/window focus)
  useEffect(() => {
    function handleVisibilityChange() {
      if (document.visibilityState === 'visible') {
        router.refresh()
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [router])
  const [format, setFormat] = useState<FormatFilter>('all')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [sort, setSort] = useState<SortOption>('recent')

  // Push review count to context for header badge
  const reviewCount = useMemo(
    () => liveProductions.filter((p) => p.flagged_count > 0 || p.pending_count > 0).length,
    [liveProductions]
  )

  // Sync review count to context (used by Header via ReviewCountProvider)
  useEffect(() => {
    setReviewCount(reviewCount)
  }, [reviewCount, setReviewCount])

  const filteredProductions = useMemo(() => {
    let result = liveProductions

    // Format filter
    if (format !== 'all') {
      result = result.filter((p) => p.format === format)
    }

    // Status filter
    if (status === 'active') {
      result = result.filter((p) => p.status === 'active')
    } else if (status === 'needs-attention') {
      result = result.filter(
        (p) => isStale(p.heartbeat_at, p.status, p.current_phase) || p.flagged_count > 0
      )
    } else if (status === 'paused') {
      result = result.filter((p) => p.status === 'paused')
    }

    // Sort
    result = [...result].sort((a, b) => {
      if (sort === 'recent') {
        return (
          new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
        )
      }
      if (sort === 'created') {
        return (
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        )
      }
      // name
      const nameA = a.display_name || a.slug
      const nameB = b.display_name || b.slug
      return nameA.localeCompare(nameB)
    })

    return result
  }, [liveProductions, format, status, sort])

  const groupedByStage = useMemo(() => {
    const groups: Record<string, Production[]> = {}
    for (const stage of STAGE_ORDER) {
      groups[stage] = []
    }
    for (const production of filteredProductions) {
      const stage = production.current_stage
      if (groups[stage]) {
        groups[stage].push(production)
      } else {
        // Unknown stage -- put in first column
        groups[STAGE_ORDER[0]].push(production)
      }
    }
    return groups
  }, [filteredProductions])

  return (
    <div>
      <StaleDetector productions={liveProductions} />
      <Suspense fallback={null}>
        <FilterBar
          onFormatChange={setFormat}
          onStatusChange={setStatus}
          onSortChange={setSort}
        />
      </Suspense>

      <div className="grid grid-cols-1 lg:grid-cols-3 xl:grid-cols-5 gap-4 p-6">
        {STAGE_ORDER.map((stage) => (
          <StageColumn
            key={stage}
            stageName={stage}
            productions={groupedByStage[stage]}
          />
        ))}
      </div>
    </div>
  )
}
