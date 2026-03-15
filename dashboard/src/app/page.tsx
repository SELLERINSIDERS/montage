import { createClient } from '@/lib/supabase/server'
import { KanbanBoard } from '@/components/board/kanban-board'
import type { Production } from '@/lib/types'

export default async function BoardPage() {
  const supabase = await createClient()

  // Fetch active, paused, and error productions
  const { data: activeProductions } = await supabase
    .from('productions')
    .select('*')
    .in('status', ['active', 'paused', 'error'])

  // Fetch recently completed productions (last 48 hours)
  const cutoff = new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString()
  const { data: completedProductions } = await supabase
    .from('productions')
    .select('*')
    .eq('status', 'completed')
    .gte('completed_at', cutoff)

  const productions: Production[] = [
    ...(activeProductions ?? []),
    ...(completedProductions ?? []),
  ] as Production[]

  if (productions.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center space-y-3">
          <p className="text-lg text-muted-foreground">No productions yet.</p>
          <p className="text-sm text-muted-foreground">
            Start one with{' '}
            <code className="bg-muted px-2 py-1 rounded text-sm">/vsl-production</code>{' '}
            in Claude.
          </p>
        </div>
      </div>
    )
  }

  return <KanbanBoard initialData={productions} />
}
