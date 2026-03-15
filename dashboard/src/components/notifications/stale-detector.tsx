'use client'

import { useEffect, useRef } from 'react'
import { toast } from 'sonner'
import { isStale } from '@/lib/utils'
import type { Production } from '@/lib/types'

interface StaleDetectorProps {
  productions: Production[]
}

/**
 * Side-effect component that monitors productions for:
 * 1. Stale heartbeat transitions (>30min) -- fires toast.error
 * 2. Batch completion (approved_count reaches scene_count) -- fires toast.success
 * 3. Tab title badge showing count of productions needing review
 *
 * Renders nothing visible.
 */
export function StaleDetector({ productions }: StaleDetectorProps) {
  const previousStaleIds = useRef<Set<string>>(new Set())
  const previousApprovedMap = useRef<Map<string, number>>(new Map())

  // Stale detection + batch completion (runs on interval and productions change)
  useEffect(() => {
    function check() {
      for (const production of productions) {
        const name = production.display_name || production.slug
        const stale = isStale(production.heartbeat_at, production.status, production.current_phase)

        // Stale transition detection
        if (stale && !previousStaleIds.current.has(production.id)) {
          toast.error(`Pipeline stale -- needs attention`, {
            description: name,
            duration: 10000,
          })
          previousStaleIds.current.add(production.id)
        } else if (!stale && previousStaleIds.current.has(production.id)) {
          // No longer stale -- allow re-detection
          previousStaleIds.current.delete(production.id)
        }

        // Batch completion detection
        const prevApproved = previousApprovedMap.current.get(production.id)
        if (
          prevApproved !== undefined &&
          prevApproved < production.scene_count &&
          production.approved_count >= production.scene_count &&
          production.scene_count > 0
        ) {
          toast.success(`All clips ready for review: ${name}`, {
            duration: 8000,
          })
        }
        previousApprovedMap.current.set(
          production.id,
          production.approved_count
        )
      }
    }

    // Run immediately on productions change
    check()

    // Run periodically for time-based stale detection
    const interval = setInterval(check, 60_000)
    return () => clearInterval(interval)
  }, [productions])

  // Tab title badge
  useEffect(() => {
    const reviewCount = productions.filter(
      (p) => p.flagged_count > 0 || p.pending_count > 0
    ).length

    document.title =
      reviewCount > 0
        ? `(${reviewCount}) VSL Dashboard`
        : 'VSL Dashboard'
  }, [productions])

  return null
}
