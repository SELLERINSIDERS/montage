'use client'

import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area'
import { getPublicAssetUrl, getSceneStatus } from '@/lib/utils'
import type { Scene } from '@/lib/types'

interface SignedUrlMap {
  [sceneId: string]: { thumbnail?: string; image?: string; video?: string }
}

interface SceneTimelineProps {
  scenes: Scene[]
  signedUrls: SignedUrlMap
  onSceneClick: (index: number) => void
}

function getStatusColor(scene: Scene): string {
  const status = getSceneStatus(scene)
  switch (status) {
    case 'generating':
    case 'regenerating':
      return 'bg-purple-500'
    case 'failed':
      return 'bg-red-500'
    case 'approved':
      return 'bg-green-500'
    case 'flagged':
      return 'bg-yellow-500'
    case 'deferred':
      return 'bg-blue-500'
    default:
      return 'bg-zinc-500'
  }
}

function getStatusLabel(scene: Scene): string {
  const status = getSceneStatus(scene)
  switch (status) {
    case 'generating': return 'Generating'
    case 'regenerating': return 'Regenerating'
    case 'failed': return 'Failed'
    case 'approved': return 'Approved'
    case 'flagged': return 'Flagged'
    case 'deferred': return 'Deferred'
    default: return 'Pending'
  }
}

export function SceneTimeline({ scenes, signedUrls, onSceneClick }: SceneTimelineProps) {
  return (
    <ScrollArea className="w-full">
      <div className="flex items-center gap-1 pb-4 px-1 min-w-max">
        {scenes.map((scene, index) => {
          const urls = signedUrls[scene.id]
          const thumbUrl =
            getPublicAssetUrl(scene.thumbnail_storage_path || scene.image_storage_path) ||
            urls?.thumbnail ||
            urls?.image
          const statusColor = getStatusColor(scene)

          return (
            <div key={scene.id} className="flex items-center">
              {/* Scene card */}
              <div
                className="w-28 shrink-0 cursor-pointer rounded-lg border border-border hover:border-accent transition-colors overflow-hidden"
                onClick={() => onSceneClick(index)}
              >
                {/* Thumbnail */}
                <div className="aspect-video bg-muted relative">
                  {thumbUrl ? (
                    <img
                      src={thumbUrl}
                      alt={`Scene ${scene.scene_id}`}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-muted-foreground text-[10px]">
                      No media
                    </div>
                  )}
                  {/* Status dot */}
                  <div className={`absolute top-1 right-1 size-2.5 rounded-full ${statusColor}`} />
                </div>
                {/* Label */}
                <div className="p-1.5">
                  <p className="text-[10px] font-medium truncate">{scene.scene_id}</p>
                  <p className="text-[9px] text-muted-foreground">{getStatusLabel(scene)}</p>
                </div>
              </div>

              {/* Connector line (not after last) */}
              {index < scenes.length - 1 && (
                <div className="w-3 h-0.5 bg-border shrink-0" />
              )}
            </div>
          )
        })}
      </div>
      <ScrollBar orientation="horizontal" />
    </ScrollArea>
  )
}
