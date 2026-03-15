'use client'

import { useState, useRef, useEffect } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { LogOut, Bell } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { createClient } from '@/lib/supabase/client'

interface HeaderProps {
  reviewCount?: number
}

export function Header({ reviewCount = 0 }: HeaderProps) {
  const router = useRouter()
  const pathname = usePathname()
  const supabase = createClient()
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const handleSignOut = async () => {
    await supabase.auth.signOut()
    router.push('/login')
  }

  const handleBellClick = () => {
    if (reviewCount > 0) {
      setDropdownOpen((prev) => !prev)
    } else {
      // No items -- navigate to board with no filter
      if (pathname !== '/') {
        router.push('/')
      }
    }
  }

  const handleViewAll = () => {
    setDropdownOpen(false)
    router.push('/?status=needs-attention')
  }

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false)
      }
    }
    if (dropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [dropdownOpen])

  return (
    <header className="border-b border-border bg-card px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold tracking-tight">VSL Dashboard</h1>
        <span className="text-sm text-muted-foreground">Production Dashboard</span>
      </div>
      <div className="flex items-center gap-3">
        {/* Notification bell */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={handleBellClick}
            className="relative p-1.5 rounded-md hover:bg-muted transition-colors"
            aria-label={`Notifications${reviewCount > 0 ? ` (${reviewCount} items)` : ''}`}
          >
            <Bell className="h-5 w-5 text-muted-foreground" />
            {reviewCount > 0 && (
              <span className="absolute -top-1 -right-1 flex items-center justify-center min-w-[18px] h-[18px] px-1 text-[10px] font-bold bg-red-500 text-white rounded-full">
                {reviewCount}
              </span>
            )}
          </button>

          {/* Dropdown */}
          {dropdownOpen && (
            <div className="absolute right-0 top-full mt-2 w-72 bg-card border border-border rounded-lg shadow-lg z-50">
              <div className="px-4 py-3 border-b border-border">
                <p className="text-sm font-medium">Notifications</p>
              </div>
              <div className="px-4 py-3">
                {reviewCount > 0 ? (
                  <div className="space-y-2">
                    <p className="text-sm text-muted-foreground">
                      {reviewCount} production{reviewCount !== 1 ? 's' : ''} need{reviewCount === 1 ? 's' : ''} attention
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full"
                      onClick={handleViewAll}
                    >
                      View all
                    </Button>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">All clear -- no items need attention.</p>
                )}
              </div>
            </div>
          )}
        </div>
        <Button variant="ghost" size="sm" onClick={handleSignOut}>
          <LogOut className="h-4 w-4 mr-2" />
          Sign Out
        </Button>
      </div>
    </header>
  )
}
