'use client'

import { useState, useEffect, useRef, useMemo } from 'react'
import { ChevronDown, Check, X, Clock } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { useRealtimeJobs, type RegenerationJob } from '@/hooks/use-realtime-jobs'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Gate type color mapping
// ---------------------------------------------------------------------------
const GATE_COLORS: Record<string, string> = {
  image_1k: 'bg-blue-500/20 text-blue-400',
  image_2k: 'bg-indigo-500/20 text-indigo-400',
  video_clip: 'bg-purple-500/20 text-purple-400',
  final_video: 'bg-amber-500/20 text-amber-400',
}

const GATE_LABELS: Record<string, string> = {
  image_1k: '1K',
  image_2k: '2K',
  video_clip: 'Video',
  final_video: 'Final',
}

// ---------------------------------------------------------------------------
// Elapsed time helper
// ---------------------------------------------------------------------------
function useElapsedSeconds(startIso: string, active: boolean): number {
  const [elapsed, setElapsed] = useState(() =>
    Math.floor((Date.now() - new Date(startIso).getTime()) / 1000)
  )

  useEffect(() => {
    if (!active) return
    setElapsed(Math.floor((Date.now() - new Date(startIso).getTime()) / 1000))
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - new Date(startIso).getTime()) / 1000))
    }, 1000)
    return () => clearInterval(interval)
  }, [startIso, active])

  return elapsed
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m ${s.toString().padStart(2, '0')}s`
}

// ---------------------------------------------------------------------------
// Individual job row
// ---------------------------------------------------------------------------
function JobRow({ job, faded }: { job: RegenerationJob; faded: boolean }) {
  const isActive = job.status === 'claimed' || job.status === 'processing'
  const elapsed = useElapsedSeconds(job.created_at, isActive)

  const gateColor = GATE_COLORS[job.gate_type] ?? 'bg-muted text-muted-foreground'
  const gateLabel = GATE_LABELS[job.gate_type] ?? job.gate_type

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-3 py-2 rounded-lg border border-border/50 transition-opacity duration-500',
        faded ? 'opacity-40' : 'opacity-100'
      )}
    >
      {/* Status indicator */}
      <div className="shrink-0">
        {job.status === 'pending' && (
          <span className="inline-block size-2.5 rounded-full bg-yellow-400" />
        )}
        {(job.status === 'claimed' || job.status === 'processing') && (
          <span className="inline-block size-2.5 rounded-full bg-purple-400 animate-pulse" />
        )}
        {job.status === 'completed' && (
          <Check className="size-4 text-green-400" />
        )}
        {job.status === 'failed' && (
          <X className="size-4 text-red-400" />
        )}
      </div>

      {/* Scene ID */}
      <span className="text-sm font-mono font-medium w-12 shrink-0">
        {job.scene_id}
      </span>

      {/* Gate type badge */}
      <Badge className={cn('text-[10px] px-1.5 py-0 h-4 shrink-0', gateColor)}>
        {gateLabel}
      </Badge>

      {/* Status text + timing */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {job.status === 'pending' && (
            <span className="text-xs text-yellow-400">Queued</span>
          )}
          {(job.status === 'claimed' || job.status === 'processing') && (
            <>
              <span className="text-xs text-purple-400">Generating...</span>
              <span className="text-[10px] text-muted-foreground font-mono">
                {formatElapsed(elapsed)}
              </span>
            </>
          )}
          {job.status === 'completed' && (
            <>
              <span className="text-xs text-green-400">Done</span>
              <span className="text-[10px] text-muted-foreground font-mono">
                {formatElapsed(
                  Math.floor(
                    (new Date(job.updated_at).getTime() -
                      new Date(job.created_at).getTime()) /
                      1000
                  )
                )}
              </span>
            </>
          )}
          {job.status === 'failed' && (
            <>
              <span className="text-xs text-red-400">Failed</span>
              <span className="text-[10px] text-muted-foreground">
                attempt {job.attempt_count}
              </span>
            </>
          )}
        </div>
        {/* Truncated feedback */}
        {job.feedback_text && (
          <p className="text-[10px] text-muted-foreground truncate mt-0.5">
            {job.feedback_text.length > 60
              ? `${job.feedback_text.slice(0, 60)}...`
              : job.feedback_text}
          </p>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------
interface RegenerationActivityProps {
  productionId: string
}

export function RegenerationActivity({ productionId }: RegenerationActivityProps) {
  const { jobs, activeJobs } = useRealtimeJobs(productionId)
  const [expanded, setExpanded] = useState(false)
  const [fadedIds, setFadedIds] = useState<Set<string>>(new Set())
  const prevJobCountRef = useRef(jobs.length)

  const activeCount = activeJobs.length
  const hasActive = activeCount > 0

  // Auto-expand when a new job arrives (INSERT — job count increases)
  useEffect(() => {
    if (jobs.length > prevJobCountRef.current) {
      setExpanded(true)
    }
    prevJobCountRef.current = jobs.length
  }, [jobs.length])

  // Fade completed/failed jobs 30 seconds after they resolve
  useEffect(() => {
    const terminalJobs = jobs.filter(
      (j) => j.status === 'completed' || j.status === 'failed'
    )
    const timers: ReturnType<typeof setTimeout>[] = []

    for (const job of terminalJobs) {
      if (fadedIds.has(job.id)) continue
      const resolvedAt = new Date(job.updated_at).getTime()
      const msUntilFade = resolvedAt + 30_000 - Date.now()

      if (msUntilFade <= 0) {
        // Already past 30s — fade immediately
        setFadedIds((prev) => new Set(prev).add(job.id))
      } else {
        const timer = setTimeout(() => {
          setFadedIds((prev) => new Set(prev).add(job.id))
        }, msUntilFade)
        timers.push(timer)
      }
    }

    return () => timers.forEach(clearTimeout)
  }, [jobs, fadedIds])

  // Sort: active first (pending/claimed/processing), then terminal (completed/failed)
  const sortedJobs = useMemo(() => {
    const statusOrder: Record<string, number> = {
      processing: 0,
      claimed: 1,
      pending: 2,
      completed: 3,
      failed: 4,
    }
    return [...jobs].sort(
      (a, b) => (statusOrder[a.status] ?? 5) - (statusOrder[b.status] ?? 5)
    )
  }, [jobs])

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      {/* Header bar — always visible */}
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted/50 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-2.5">
          <Clock className="size-4 text-muted-foreground" />
          <span className="text-sm font-medium">Regeneration Queue</span>
          {hasActive && (
            <Badge
              className={cn(
                'text-[10px] px-1.5 py-0 h-4 bg-purple-500/20 text-purple-400',
                'animate-pulse'
              )}
            >
              {activeCount} active
            </Badge>
          )}
        </div>
        <ChevronDown
          className={cn(
            'size-4 text-muted-foreground transition-transform duration-200',
            expanded && 'rotate-180'
          )}
        />
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-border px-4 py-3 space-y-2 max-h-80 overflow-y-auto">
          {sortedJobs.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              No regeneration jobs
            </p>
          ) : (
            sortedJobs.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                faded={fadedIds.has(job.id)}
              />
            ))
          )}
        </div>
      )}
    </div>
  )
}
