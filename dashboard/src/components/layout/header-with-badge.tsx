'use client'

import { useReviewCount } from '@/lib/review-count-context'
import { Header } from './header'

/**
 * Wrapper that reads reviewCount from context and passes it to Header.
 * This bridges the layout-level Header with the page-level KanbanBoard.
 */
export function HeaderWithBadge() {
  const { reviewCount } = useReviewCount()
  return <Header reviewCount={reviewCount} />
}
