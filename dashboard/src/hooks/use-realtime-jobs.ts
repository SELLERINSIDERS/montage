'use client'

import { useEffect, useState, useRef } from 'react'
import { createClient } from '@/lib/supabase/client'
import type { RealtimeChannel } from '@supabase/supabase-js'

export interface RegenerationJob {
  id: string
  production_id: string
  scene_id: string
  gate_type: string
  feedback_text: string | null
  status: 'pending' | 'claimed' | 'processing' | 'completed' | 'failed'
  attempt_count: number
  created_at: string
  updated_at: string
}

/**
 * Subscribes to Supabase Realtime postgres_changes on the regeneration_queue
 * table, filtered by production_id. Returns live-updating jobs and active
 * (non-terminal) jobs.
 *
 * Uses channelRef to prevent React Strict Mode double-subscription.
 */
export function useRealtimeJobs(productionId: string) {
  const [jobs, setJobs] = useState<RegenerationJob[]>([])
  const channelRef = useRef<RealtimeChannel | null>(null)

  useEffect(() => {
    const supabase = createClient()

    // Prevent double-subscription in Strict Mode
    if (channelRef.current) {
      supabase.removeChannel(channelRef.current)
    }

    // Fetch initial jobs
    supabase
      .from('regeneration_queue')
      .select('*')
      .eq('production_id', productionId)
      .order('created_at', { ascending: false })
      .limit(50)
      .then(({ data }) => {
        if (data) setJobs(data as RegenerationJob[])
      })

    const channel = supabase
      .channel(`regen-jobs-${productionId}`)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'regeneration_queue',
          filter: `production_id=eq.${productionId}`,
        },
        (payload) => {
          const newJob = payload.new as RegenerationJob
          setJobs((prev) => [newJob, ...prev])
        }
      )
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'regeneration_queue',
          filter: `production_id=eq.${productionId}`,
        },
        (payload) => {
          const updated = payload.new as RegenerationJob
          setJobs((prev) =>
            prev.map((j) => (j.id === updated.id ? { ...j, ...updated } : j))
          )
        }
      )
      .subscribe()

    channelRef.current = channel

    return () => {
      supabase.removeChannel(channel)
      channelRef.current = null
    }
  }, [productionId])

  const activeJobs = jobs.filter(
    (j) => j.status === 'pending' || j.status === 'claimed' || j.status === 'processing'
  )

  return { jobs, activeJobs }
}
