'use client'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { PlayCircle, CheckCircle2, Clock } from 'lucide-react'

export interface VideoVersion {
  version: number
  quality: string
  storage_url: string
  rendered_at: string
  render_duration_s: number
  is_approved: boolean
}

interface VersionTimelineProps {
  versions: VideoVersion[]
  currentVersion: number
  onVersionSelect: (version: VideoVersion) => void
  onApprove: (version: VideoVersion) => void
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function formatRenderTime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs}s`
}

export function VersionTimeline({
  versions,
  currentVersion,
  onVersionSelect,
  onApprove,
}: VersionTimelineProps) {
  if (versions.length === 0) {
    return (
      <div className="text-sm text-muted-foreground py-4 text-center">
        No rendered versions yet
      </div>
    )
  }

  // Find latest final-quality version for approve button
  const latestFinal = [...versions]
    .reverse()
    .find((v) => v.quality === 'final' && !v.is_approved)

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-muted-foreground">Versions</h3>
      <div className="flex flex-col gap-1.5">
        {versions.map((v) => {
          const isCurrent = v.version === currentVersion
          const isApproved = v.is_approved

          return (
            <div
              key={v.version}
              className={`flex items-center gap-3 p-2.5 rounded-lg border transition-colors ${
                isCurrent
                  ? 'border-blue-500/50 bg-blue-500/5'
                  : 'border-border hover:border-accent'
              }`}
            >
              {/* Version badge */}
              <Badge
                className={`text-xs ${
                  v.quality === 'final'
                    ? 'bg-green-500/20 text-green-400'
                    : 'bg-zinc-500/20 text-zinc-400'
                }`}
              >
                v{v.version}
              </Badge>

              {/* Quality label */}
              <span className="text-xs text-muted-foreground capitalize">
                {v.quality}
              </span>

              {/* Timestamp */}
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <Clock className="size-3" />
                {formatDate(v.rendered_at)}
              </span>

              {/* Render duration */}
              <span className="text-xs text-muted-foreground">
                ({formatRenderTime(v.render_duration_s)})
              </span>

              {/* Spacer */}
              <div className="flex-1" />

              {/* Approved badge */}
              {isApproved && (
                <Badge className="bg-green-500/20 text-green-400 gap-1">
                  <CheckCircle2 className="size-3" />
                  Approved
                </Badge>
              )}

              {/* Play button */}
              {!isCurrent && v.storage_url && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 gap-1"
                  onClick={() => onVersionSelect(v)}
                >
                  <PlayCircle className="size-3.5" />
                  Play
                </Button>
              )}

              {/* Approve button for latest final version */}
              {v === latestFinal && (
                <Button
                  size="sm"
                  className="h-7 px-3 gap-1 bg-green-600 hover:bg-green-700 text-white"
                  onClick={() => onApprove(v)}
                >
                  <CheckCircle2 className="size-3.5" />
                  Approve as Final
                </Button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
