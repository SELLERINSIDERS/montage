'use client'

import { useRef, useEffect } from 'react'
import { Badge } from '@/components/ui/badge'
import { Mic, Volume2, Music, VolumeX } from 'lucide-react'

export interface FinalScene {
  id: string
  label: string
  duration_s: number
  start_s: number
  audio_type: string
}

interface FinalSceneGridProps {
  scenes: FinalScene[]
  activeSceneId?: string
  onSceneClick: (sceneId: string, startTime: number) => void
}

function audioIcon(audioType: string) {
  switch (audioType) {
    case 'voiceover_only':
      return <Mic className="size-3.5" />
    case 'scene_dominant':
      return <Volume2 className="size-3.5" />
    case 'mixed':
      return <Music className="size-3.5" />
    case 'silent':
      return <VolumeX className="size-3.5" />
    default:
      return null
  }
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  if (mins > 0) return `${mins}:${secs.toString().padStart(2, '0')}`
  return `${secs}s`
}

export function FinalSceneGrid({
  scenes,
  activeSceneId,
  onSceneClick,
}: FinalSceneGridProps) {
  const activeRef = useRef<HTMLDivElement>(null)

  // Auto-scroll active scene into view
  useEffect(() => {
    if (activeSceneId && activeRef.current) {
      activeRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
      })
    }
  }, [activeSceneId])

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
      {scenes.map((scene, index) => {
        const isActive = scene.id === activeSceneId
        return (
          <div
            key={scene.id}
            ref={isActive ? activeRef : undefined}
            className={`relative rounded-lg border p-3 cursor-pointer transition-all ${
              isActive
                ? 'border-blue-500 ring-2 ring-blue-500/30 bg-blue-500/5'
                : 'border-border hover:border-accent bg-card'
            }`}
            onClick={() => onSceneClick(scene.id, scene.start_s)}
          >
            {/* Scene number badge */}
            <div className="flex items-center justify-between mb-1.5">
              <Badge
                className={`text-[10px] px-1.5 ${
                  isActive
                    ? 'bg-blue-500/20 text-blue-400'
                    : 'bg-zinc-500/20 text-zinc-400'
                }`}
              >
                {index + 1}
              </Badge>

              <div className="flex items-center gap-1.5">
                {/* Audio type icon */}
                {scene.audio_type && (
                  <span className="text-muted-foreground" title={scene.audio_type}>
                    {audioIcon(scene.audio_type)}
                  </span>
                )}

                {/* Duration badge */}
                <Badge className="bg-zinc-800 text-zinc-300 text-[10px]">
                  {formatDuration(scene.duration_s)}
                </Badge>
              </div>
            </div>

            {/* Label */}
            <p className="text-xs text-foreground line-clamp-2 leading-snug">
              {scene.label || `Scene ${index + 1}`}
            </p>
          </div>
        )
      })}
    </div>
  )
}
