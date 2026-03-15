'use client'

import { useRef, useEffect, useState, useCallback } from 'react'

export interface VideoScene {
  id: string
  label: string
  start_s: number
  duration_s: number
}

interface VideoPlayerWithMarkersProps {
  src: string
  scenes: VideoScene[]
  onSceneChange?: (sceneId: string) => void
  seekToTime?: number
}

export function VideoPlayerWithMarkers({
  src,
  scenes,
  onSceneChange,
  seekToTime,
}: VideoPlayerWithMarkersProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [activeSceneId, setActiveSceneId] = useState<string | null>(null)
  const [hoveredTick, setHoveredTick] = useState<number | null>(null)

  // Seek to time when seekToTime prop changes
  useEffect(() => {
    if (seekToTime !== undefined && videoRef.current) {
      videoRef.current.currentTime = seekToTime
    }
  }, [seekToTime])

  // Track current time and derive active scene
  const handleTimeUpdate = useCallback(() => {
    if (!videoRef.current) return
    const t = videoRef.current.currentTime
    setCurrentTime(t)

    // Find active scene
    for (let i = scenes.length - 1; i >= 0; i--) {
      if (t >= scenes[i].start_s) {
        if (scenes[i].id !== activeSceneId) {
          setActiveSceneId(scenes[i].id)
          onSceneChange?.(scenes[i].id)
        }
        break
      }
    }
  }, [scenes, activeSceneId, onSceneChange])

  const handleLoadedMetadata = useCallback(() => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration)
    }
  }, [])

  // Calculate total duration from scenes if video metadata not available
  const totalDuration = duration > 0
    ? duration
    : scenes.reduce((sum, s) => Math.max(sum, s.start_s + s.duration_s), 0)

  return (
    <div className="flex flex-col gap-2">
      {/* Video element */}
      <div className="relative bg-black rounded-lg overflow-hidden">
        <video
          ref={videoRef}
          src={src}
          controls
          className="w-full aspect-video"
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
        />
      </div>

      {/* Scene boundary timeline */}
      {totalDuration > 0 && scenes.length > 0 && (
        <div className="relative h-8 bg-zinc-900 rounded-md px-1">
          {/* Progress bar */}
          <div
            className="absolute top-0 left-0 h-full bg-white/5 rounded-md transition-all"
            style={{ width: `${(currentTime / totalDuration) * 100}%` }}
          />

          {/* Scene boundary tick marks */}
          {scenes.map((scene, idx) => {
            const position = (scene.start_s / totalDuration) * 100
            const isActive = scene.id === activeSceneId
            const isHovered = hoveredTick === idx

            return (
              <div
                key={scene.id}
                className="absolute top-0 h-full flex items-center"
                style={{ left: `${position}%` }}
                onMouseEnter={() => setHoveredTick(idx)}
                onMouseLeave={() => setHoveredTick(null)}
                onClick={() => {
                  if (videoRef.current) {
                    videoRef.current.currentTime = scene.start_s
                  }
                }}
              >
                {/* Tick mark */}
                <div
                  className={`w-px h-4 cursor-pointer transition-colors ${
                    isActive
                      ? 'bg-white'
                      : 'bg-white/40 hover:bg-white/70'
                  }`}
                />

                {/* Tooltip on hover */}
                {isHovered && (
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 whitespace-nowrap bg-zinc-800 text-white text-xs px-2 py-1 rounded shadow-lg z-20 pointer-events-none">
                    Scene {idx + 1} - {scene.label}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
