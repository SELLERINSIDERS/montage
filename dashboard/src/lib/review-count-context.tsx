'use client'

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'

interface ReviewCountContextValue {
  reviewCount: number
  setReviewCount: (count: number) => void
}

const ReviewCountContext = createContext<ReviewCountContextValue>({
  reviewCount: 0,
  setReviewCount: () => {},
})

export function ReviewCountProvider({ children }: { children: ReactNode }) {
  const [reviewCount, setReviewCount] = useState(0)
  return (
    <ReviewCountContext.Provider value={{ reviewCount, setReviewCount }}>
      {children}
    </ReviewCountContext.Provider>
  )
}

export function useReviewCount() {
  return useContext(ReviewCountContext)
}
