import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ProductionCard } from '../production-card'
import type { Production } from '@/lib/types'

function makeProduction(overrides: Partial<Production> = {}): Production {
  return {
    id: 'test-id-1',
    format: 'vsl',
    slug: 'test-production',
    display_name: 'Test Production',
    current_phase: 'image_1k',
    current_stage: 'Image Gen',
    scene_count: 20,
    approved_count: 12,
    flagged_count: 0,
    pending_count: 8,
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

describe('ProductionCard', () => {
  it('renders production name and format badge', () => {
    render(<ProductionCard production={makeProduction()} />)

    expect(screen.getByText('Test Production')).toBeInTheDocument()
    expect(screen.getByText('VSL')).toBeInTheDocument()
  })

  it('shows stale badge when heartbeat >30min old and status active', () => {
    const staleTime = new Date(Date.now() - 60 * 60 * 1000).toISOString()
    render(
      <ProductionCard
        production={makeProduction({
          heartbeat_at: staleTime,
          status: 'active',
        })}
      />
    )

    expect(screen.getByText('Needs Attention')).toBeInTheDocument()
  })

  it('does not show stale badge when heartbeat is recent', () => {
    render(
      <ProductionCard
        production={makeProduction({
          heartbeat_at: new Date().toISOString(),
          status: 'active',
        })}
      />
    )

    expect(screen.queryByText('Needs Attention')).not.toBeInTheDocument()
  })

  it('shows approval progress', () => {
    render(
      <ProductionCard
        production={makeProduction({
          approved_count: 12,
          scene_count: 20,
        })}
      />
    )

    expect(screen.getByText('12/20 approved')).toBeInTheDocument()
  })

  it('shows flagged count badge when flagged_count > 0', () => {
    render(
      <ProductionCard
        production={makeProduction({
          flagged_count: 3,
        })}
      />
    )

    expect(screen.getByText('3 flagged')).toBeInTheDocument()
  })

  it('does not show flagged badge when flagged_count is 0', () => {
    render(
      <ProductionCard
        production={makeProduction({
          flagged_count: 0,
        })}
      />
    )

    expect(screen.queryByText(/flagged/)).not.toBeInTheDocument()
  })

  it('links to /production/{id}', () => {
    render(
      <ProductionCard
        production={makeProduction({ id: 'abc-123' })}
      />
    )

    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/production/abc-123')
  })

  it('uses slug as name when display_name is null', () => {
    render(
      <ProductionCard
        production={makeProduction({
          display_name: null,
          slug: 'my-slug',
        })}
      />
    )

    expect(screen.getByText('my-slug')).toBeInTheDocument()
  })
})
