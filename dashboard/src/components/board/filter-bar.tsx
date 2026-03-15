'use client'

import { useQueryState } from 'nuqs'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

export type FormatFilter = 'all' | 'vsl' | 'ad' | 'ugc'
export type StatusFilter = 'all' | 'active' | 'needs-attention' | 'paused'
export type SortOption = 'recent' | 'created' | 'name'

interface FilterBarProps {
  onFormatChange: (format: FormatFilter) => void
  onStatusChange: (status: StatusFilter) => void
  onSortChange: (sort: SortOption) => void
}

export function FilterBar({
  onFormatChange,
  onStatusChange,
  onSortChange,
}: FilterBarProps) {
  const [format, setFormat] = useQueryState('format', { defaultValue: 'all' })
  const [status, setStatus] = useQueryState('status', { defaultValue: 'all' })
  const [sort, setSort] = useQueryState('sort', { defaultValue: 'recent' })

  const handleFormatChange = (value: string) => {
    setFormat(value)
    onFormatChange(value as FormatFilter)
  }

  const handleStatusChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setStatus(e.target.value)
    onStatusChange(e.target.value as StatusFilter)
  }

  const handleSortChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setSort(e.target.value)
    onSortChange(e.target.value as SortOption)
  }

  return (
    <div className="flex items-center justify-between gap-4 px-6 py-3 border-b border-border">
      <Tabs value={format} onValueChange={handleFormatChange}>
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="vsl">VSL</TabsTrigger>
          <TabsTrigger value="ad">Ads</TabsTrigger>
          <TabsTrigger value="ugc">UGC</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="flex items-center gap-3">
        <select
          value={status}
          onChange={handleStatusChange}
          className="bg-muted text-sm rounded-md px-3 py-1.5 border border-input focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="all">All Status</option>
          <option value="active">Active</option>
          <option value="needs-attention">Needs Attention</option>
          <option value="paused">Paused</option>
        </select>

        <select
          value={sort}
          onChange={handleSortChange}
          className="bg-muted text-sm rounded-md px-3 py-1.5 border border-input focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="recent">Most Recent Activity</option>
          <option value="created">Creation Date</option>
          <option value="name">Name</option>
        </select>
      </div>
    </div>
  )
}
