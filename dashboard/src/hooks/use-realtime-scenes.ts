'use client'

import { useEffect, useState, useRef } from 'react'
import { createClient } from '@/lib/supabase/client'
import type { Scene } from '@/lib/types'
import type { RealtimeChannel } from '@supabase/supabase-js'

/**
 * Subscribes to Supabase Realtime postgres_changes on the scenes table,
 * filtered by production_id. Returns live-updating scenes, connection status,
 * and a reconnecting flag (true after 10s disconnect).
 *
 * Uses channelRef to prevent React Strict Mode double-subscription.
 */
export function useRealtimeScenes(initialData: Scene[], productionId: string) {
  const [scenes, setScenes] = useState<Scene[]>(initialData)
  const [realtimeStatus, setRealtimeStatus] = useState<string>('CLOSED')
  const [disconnectedAt, setDisconnectedAt] = useState<number | null>(null)
  const [showReconnecting, setShowReconnecting] = useState(false)
  const channelRef = useRef<RealtimeChannel | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sync when initialData changes (SSR re-fetch)
  useEffect(() => {
    setScenes(initialData)
  }, [initialData])

  useEffect(() => {
    const supabase = createClient()

    // Prevent double-subscription in Strict Mode
    if (channelRef.current) {
      supabase.removeChannel(channelRef.current)
    }

    const channel = supabase
      .channel(`scenes-${productionId}`)
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'scenes',
          filter: `production_id=eq.${productionId}`,
        },
        (payload) => {
          const updated = payload.new as Scene
          setScenes((prev) =>
            prev.map((s) => (s.id === updated.id ? { ...s, ...updated } : s))
          )
        }
      )
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'scenes',
          filter: `production_id=eq.${productionId}`,
        },
        (payload) => {
          const newScene = payload.new as Scene
          setScenes((prev) => {
            // Avoid duplicates (might get both SSR and realtime)
            if (prev.some((s) => s.id === newScene.id)) return prev
            // Insert in correct position by scene_index
            const updated = [...prev, newScene].sort((a, b) => a.scene_index - b.scene_index)
            return updated
          })
        }
      )
      .subscribe((status) => {
        setRealtimeStatus(status)
        if (status === 'SUBSCRIBED') {
          setDisconnectedAt(null)
          setShowReconnecting(false)
          if (timerRef.current) {
            clearTimeout(timerRef.current)
            timerRef.current = null
          }
        } else if (status === 'CLOSED' || status === 'CHANNEL_ERROR') {
          const now = Date.now()
          setDisconnectedAt((prev) => prev ?? now)
          // Show reconnecting banner after 10 seconds
          timerRef.current = setTimeout(() => {
            setShowReconnecting(true)
          }, 10_000)
        }
      })

    channelRef.current = channel

    return () => {
      supabase.removeChannel(channel)
      channelRef.current = null
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [productionId])

  function updateSceneOptimistic(sceneId: string, patch: Partial<Scene>) {
    setScenes((prev) => prev.map((s) => (s.id === sceneId ? { ...s, ...patch } : s)))
  }

  return { scenes, realtimeStatus, showReconnecting, updateSceneOptimistic }
}
