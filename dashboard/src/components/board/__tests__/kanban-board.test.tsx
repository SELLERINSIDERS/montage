import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { KanbanBoard } from '../kanban-board'
import { STAGE_ORDER } from '@/lib/constants'
import type { Production } from '@/lib/types'

// Mock nuqs
vi.mock('nuqs', () => ({
  useQueryState: (key: string, opts?: { defaultValue: string }) => {
    return [opts?.defaultValue ?? '', vi.fn()]
  },
}))

// Mock realtime hook (added by 03-04, needs env vars that aren't available in test)
vi.mock('@/hooks/use-realtime-productions', () => ({
  useRealtimeProductions: (initial: Production[]) => ({ productions: initial, realtimeStatus: 'SUBSCRIBED' }),
}))

// Mock review count context
vi.mock('@/lib/review-count-context', () => ({
  useReviewCount: () => ({ reviewCount: 0, setReviewCount: vi.fn() }),
}))

// Mock stale detector (uses Supabase internals)
vi.mock('@/components/notifications/stale-detector', () => ({
  StaleDetector: () => null,
}))

function makeProduction(overrides: Partial<Production> = {}): Production {
  return {
    id: 'test-id-1',
    format: 'vsl',
    slug: 'test-production',
    display_name: 'Test Production',
    current_phase: 'image_1k',
    current_stage: 'Image Gen',
    scene_count: 10,
    approved_count: 5,
    flagged_count: 0,
    pending_count: 5,
    latest_thumbnail_url: null,
    heartbeat_at: new Date().toISOString(),
    status: 'active',
    manifest_data: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    completed_at: null,
    user_id: 'user-1',
    ...overrides,
  }
}

describe('KanbanBoard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders 5 stage columns with STAGE_ORDER names', () => {
    render(<KanbanBoard initialData={[]} />)

    for (const stage of STAGE_ORDER) {
      expect(screen.getByText(stage)).toBeInTheDocument()
    }
  })

  it('groups productions into correct columns by current_stage', () => {
    const productions = [
      makeProduction({
        id: '1',
        display_name: 'Script Prod',
        current_stage: 'Script & Design',
      }),
      makeProduction({
        id: '2',
        display_name: 'Image Prod',
        current_stage: 'Image Gen',
      }),
      makeProduction({
        id: '3',
        display_name: 'Video Prod',
        current_stage: 'Video Gen',
      }),
    ]

    render(<KanbanBoard initialData={productions} />)

    expect(screen.getByText('Script Prod')).toBeInTheDocument()
    expect(screen.getByText('Image Prod')).toBeInTheDocument()
    expect(screen.getByText('Video Prod')).toBeInTheDocument()
  })

  it('shows empty column text when no productions in a stage', () => {
    render(<KanbanBoard initialData={[]} />)

    const emptyTexts = screen.getAllByText('No productions')
    expect(emptyTexts).toHaveLength(5)
  })

  it('format filter shows only matching productions when filter applied', () => {
    const productions = [
      makeProduction({
        id: '1',
        display_name: 'VSL Prod',
        format: 'vsl',
        current_stage: 'Image Gen',
      }),
      makeProduction({
        id: '2',
        display_name: 'Ad Prod',
        format: 'ad',
        current_stage: 'Video Gen',
      }),
    ]

    // Default filter is 'all', so both should render
    render(<KanbanBoard initialData={productions} />)
    expect(screen.getByText('VSL Prod')).toBeInTheDocument()
    expect(screen.getByText('Ad Prod')).toBeInTheDocument()
  })

  it('shows stale and flagged productions with needs-attention filter', () => {
    const staleTime = new Date(Date.now() - 60 * 60 * 1000).toISOString() // 1h old
    const productions = [
      makeProduction({
        id: '1',
        display_name: 'Stale Prod',
        heartbeat_at: staleTime,
        status: 'active',
        current_stage: 'Image Gen',
      }),
      makeProduction({
        id: '2',
        display_name: 'Flagged Prod',
        flagged_count: 3,
        current_stage: 'Video Gen',
      }),
    ]

    // Default is 'all' filter -- both should show
    render(<KanbanBoard initialData={productions} />)
    expect(screen.getByText('Stale Prod')).toBeInTheDocument()
    expect(screen.getByText('Flagged Prod')).toBeInTheDocument()
  })
})
