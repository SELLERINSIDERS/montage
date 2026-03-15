'use client'

import { useEffect, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'

export function ConnectionBanner() {
  const [dbConnected, setDbConnected] = useState(true)
  const [realtimeConnected, setRealtimeConnected] = useState(true)

  // Periodic database health check
  useEffect(() => {
    const supabase = createClient()
    let interval: ReturnType<typeof setInterval>

    async function checkConnection() {
      try {
        const { error } = await supabase.from('productions').select('id', { count: 'exact', head: true })
        setDbConnected(!error)
      } catch {
        setDbConnected(false)
      }
    }

    checkConnection()
    interval = setInterval(checkConnection, 30_000)

    return () => clearInterval(interval)
  }, [])

  // Realtime connection status monitor
  useEffect(() => {
    const supabase = createClient()

    const channel = supabase
      .channel('connection-monitor')
      .subscribe((status) => {
        if (status === 'SUBSCRIBED') {
          setRealtimeConnected(true)
        } else if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT' || status === 'CLOSED') {
          setRealtimeConnected(false)
        }
      })

    return () => {
      supabase.removeChannel(channel)
    }
  }, [])

  const connected = dbConnected && realtimeConnected

  if (connected) return null

  const message = !dbConnected
    ? 'Cannot connect to Supabase. Data may be stale.'
    : 'Realtime connection lost. Board updates paused.'

  return (
    <div className="bg-red-900/80 text-red-100 px-4 py-2 text-sm flex items-center gap-2">
      <AlertTriangle className="h-4 w-4 flex-shrink-0" />
      <span>{message}</span>
    </div>
  )
}
