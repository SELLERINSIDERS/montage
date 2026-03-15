import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ProductionCard } from './production-card'
import type { Production } from '@/lib/types'

interface StageColumnProps {
  stageName: string
  productions: Production[]
}

export function StageColumn({ stageName, productions }: StageColumnProps) {
  return (
    <div className="flex flex-col bg-muted/30 rounded-lg border border-border">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h3 className="text-sm font-medium">{stageName}</h3>
        <Badge variant="secondary" className="text-xs">
          {productions.length}
        </Badge>
      </div>

      <ScrollArea className="h-[calc(100vh-220px)]">
        <div className="p-3 space-y-3">
          {productions.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              No productions
            </p>
          ) : (
            productions.map((production) => (
              <ProductionCard key={production.id} production={production} />
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
