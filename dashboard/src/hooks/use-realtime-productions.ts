'use client'

import { useEffect, useState, useRef } from 'react'
import { createClient } from '@/lib/supabase/client'
import type { Production } from '@/lib/types'
import type { RealtimeChannel } from '@supabase/supabase-js'

/**
 * Subscribes to Supabase Realtime postgres_changes on the productions table.
 * Returns a live-updating productions array and the channel's connection status.
 *
 * Uses a stable Supabase client ref to prevent React Strict Mode double-subscription.
 */
export function useRealtimeProductions(initialData: Production[]) {
  const [productions, setProductions] = useState<Production[]>(initialData)
  const [realtimeStatus, setRealtimeStatus] = useState<string>('CLOSED')
  const channelRef = useRef<RealtimeChannel | null>(null)

  // Keep productions in sync when initialData changes (SSR re-fetch)
  useEffect(() => {
    setProductions(initialData)
  }, [initialData])

  useEffect(() => {
    const supabase = createClient()

    // Prevent double-subscription in Strict Mode
    if (channelRef.current) {
      supabase.removeChannel(channelRef.current)
    }

    const channel = supabase
      .channel('productions-realtime')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'productions',
        },
        (payload) => {
          const newProduction = payload.new as Production
          setProductions((prev) => {
            // Avoid duplicates
            if (prev.some((p) => p.id === newProduction.id)) return prev
            return [...prev, newProduction]
          })
        }
      )
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'productions',
        },
        (payload) => {
          const updated = payload.new as Production
          setProductions((prev) =>
            prev.map((p) => (p.id === updated.id ? updated : p))
          )
        }
      )
      .on(
        'postgres_changes',
        {
          event: 'DELETE',
          schema: 'public',
          table: 'productions',
        },
        (payload) => {
          const deleted = payload.old as { id: string }
          setProductions((prev) => prev.filter((p) => p.id !== deleted.id))
        }
      )
      .subscribe((status) => {
        setRealtimeStatus(status)
      })

    channelRef.current = channel

    return () => {
      supabase.removeChannel(channel)
      channelRef.current = null
    }
  }, [])

  return { productions, realtimeStatus }
}
