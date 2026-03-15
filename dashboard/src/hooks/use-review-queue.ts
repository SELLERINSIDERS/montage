'use client'

import { useState, useMemo } from 'react'
import type { Scene } from '@/lib/types'
import { getSceneStatus } from '@/lib/utils'

interface UseReviewQueueOptions {
  scenes: Scene[]
}

/**
 * Hook for managing focused review mode that steps through only pending (unapproved) scenes.
 */
export function useReviewQueue({ scenes }: UseReviewQueueOptions) {
  const [isReviewMode, setIsReviewMode] = useState(false)

  const pendingScenes = useMemo(
    () => scenes.filter((s) => getSceneStatus(s) === 'pending'),
    [scenes]
  )

  return {
    isReviewMode,
    pendingScenes,
    totalPending: pendingScenes.length,
    startReview: () => setIsReviewMode(true),
    exitReview: () => setIsReviewMode(false),
  }
}
