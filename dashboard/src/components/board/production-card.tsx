import Link from 'next/link'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { formatDistanceToNow } from 'date-fns'
import { isStale } from '@/lib/utils'
import { FORMAT_COLORS } from '@/lib/constants'
import type { Production } from '@/lib/types'

interface ProductionCardProps {
  production: Production
}

export function ProductionCard({ production }: ProductionCardProps) {
  const stale = isStale(production.heartbeat_at, production.status, production.current_phase)
  const name = production.display_name || production.slug

  return (
    <Link href={`/production/${production.id}`}>
      <Card
        className={`cursor-pointer transition-colors hover:border-accent ${
          stale ? 'border-red-500 border-2' : ''
        }`}
      >
        <CardHeader className="pb-2 px-4 pt-3">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium text-sm truncate">{name}</span>
            <Badge
              className={
                FORMAT_COLORS[production.format] ?? 'bg-muted text-muted-foreground'
              }
            >
              {production.format.toUpperCase()}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="px-4 pb-3 space-y-2">
          {production.latest_thumbnail_url && (
            <img
              src={production.latest_thumbnail_url}
              alt=""
              className="w-full h-24 object-cover rounded"
            />
          )}

          <p className="text-xs text-muted-foreground">{production.current_phase}</p>

          <div className="flex justify-between text-xs text-muted-foreground">
            <span>
              {production.approved_count}/{production.scene_count} approved
            </span>
            <span suppressHydrationWarning>
              {formatDistanceToNow(new Date(production.updated_at), {
                addSuffix: true,
              })}
            </span>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {stale && (
              <Badge variant="destructive" className="text-xs">
                Needs Attention
              </Badge>
            )}
            {production.status === 'completed' && (
              <Badge className="bg-green-500/20 text-green-400 text-xs">
                Complete
              </Badge>
            )}
            {production.flagged_count > 0 && (
              <Badge
                variant="outline"
                className="text-yellow-400 border-yellow-400 text-xs"
              >
                {production.flagged_count} flagged
              </Badge>
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}
