'use client'

import { useEffect } from 'react'
import { KEYBOARD_SHORTCUTS } from '@/lib/constants'

interface UseKeyboardShortcutsOptions {
  actions: {
    approve: () => void
    flag: () => void
    defer: () => void
    prev: () => void
    next: () => void
    close: () => void
  }
  enabled: boolean
}

/**
 * Hook that binds keyboard shortcuts for the review modal.
 * Automatically disables when focus is on input/textarea/select elements.
 */
export function useKeyboardShortcuts({ actions, enabled }: UseKeyboardShortcutsOptions) {
  useEffect(() => {
    if (!enabled) return

    function handleKeyDown(e: KeyboardEvent) {
      // Disable shortcuts when typing in form elements
      const tag = (document.activeElement?.tagName ?? '').toLowerCase()
      if (tag === 'input' || tag === 'textarea' || tag === 'select') {
        return
      }

      const action = KEYBOARD_SHORTCUTS[e.key]
      if (!action) return

      e.preventDefault()

      switch (action) {
        case 'approve':
          actions.approve()
          break
        case 'flag':
          actions.flag()
          break
        case 'defer':
          actions.defer()
          break
        case 'prev':
          actions.prev()
          break
        case 'next':
          actions.next()
          break
        case 'close':
          actions.close()
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [enabled, actions])
}
