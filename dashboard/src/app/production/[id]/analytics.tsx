/**
 * Production Analytics Section
 *
 * Displays stat cards (cost, time, retry rate, scenes) and phase breakdown table.
 * Reads analytics from the production record's analytics field (pushed by DashboardSync).
 * No charting library — pure stat cards + HTML table.
 */

interface PhaseDetail {
  phase_name: string
  duration_minutes: number
}

interface ProductionAnalyticsData {
  total_cost_estimate: number
  total_duration_minutes: number
  retry_rate_percent: number
  phases: PhaseDetail[]
  scene_count: number
  total_retries: number
}

interface ProductionAnalyticsProps {
  analytics: ProductionAnalyticsData | null | undefined
}

function formatDuration(minutes: number): string {
  if (minutes < 1) {
    const seconds = Math.round(minutes * 60)
    return `${seconds}s`
  }
  const hours = Math.floor(minutes / 60)
  const mins = Math.round(minutes % 60)
  if (hours > 0) {
    return `${hours}h ${mins}m`
  }
  return `${mins}m`
}

function formatPhaseDuration(minutes: number): string {
  const mins = Math.floor(minutes)
  const secs = Math.round((minutes - mins) * 60)
  if (mins > 0) {
    return `${mins}m ${secs}s`
  }
  return `${secs}s`
}

function formatCost(cost: number): string {
  if (cost === 0) {
    return '$0.00'
  }
  return `$${cost.toFixed(2)}`
}

const PHASE_LABELS: Record<string, string> = {
  script: 'Script',
  storyboard: 'Storyboard',
  scene_design: 'Scene Design',
  camera_plan: 'Camera Plan',
  compliance: 'Compliance',
  image_generation: 'Image Gen',
  image_1k: 'Image 1K',
  image_2k: 'Image 2K',
  image_review: 'Image Review',
  video_generation: 'Video Gen',
  video_review: 'Video Review',
  voiceover: 'Voiceover',
  sound_design: 'Sound Design',
  post_production: 'Post-Production',
  remotion_render: 'Remotion Render',
}

function phaseName(raw: string): string {
  return PHASE_LABELS[raw] ?? raw.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function ProductionAnalytics({ analytics }: ProductionAnalyticsProps) {
  if (!analytics) {
    return (
      <div className="mt-8 rounded-lg border border-dashed border-gray-300 p-8 text-center">
        <p className="text-sm text-gray-500">
          Analytics will appear once the production starts generating.
        </p>
      </div>
    )
  }

  const {
    total_cost_estimate,
    total_duration_minutes,
    retry_rate_percent,
    phases,
    scene_count,
  } = analytics

  // Determine if cost is subscription-only (Kling at $145)
  const isSubscriptionOnly = total_cost_estimate === 145.0

  return (
    <div className="mt-8 space-y-6">
      <h2 className="text-lg font-semibold text-gray-900">Production Analytics</h2>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-sm font-medium text-gray-500">Total Cost</p>
          <p className="mt-1 text-2xl font-bold text-gray-900">
            {isSubscriptionOnly ? 'Subscription' : formatCost(total_cost_estimate)}
          </p>
          {isSubscriptionOnly && (
            <p className="mt-0.5 text-xs text-gray-400">$145/mo</p>
          )}
        </div>

        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-sm font-medium text-gray-500">Total Time</p>
          <p className="mt-1 text-2xl font-bold text-gray-900">
            {formatDuration(total_duration_minutes)}
          </p>
        </div>

        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-sm font-medium text-gray-500">Retry Rate</p>
          <p className="mt-1 text-2xl font-bold text-gray-900">
            {retry_rate_percent.toFixed(1)}%
          </p>
        </div>

        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-sm font-medium text-gray-500">Scenes</p>
          <p className="mt-1 text-2xl font-bold text-gray-900">
            {scene_count} total
          </p>
        </div>
      </div>

      {/* Phase Breakdown Table */}
      {phases.length > 0 && (
        <div className="overflow-hidden rounded-lg bg-white shadow">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Phase
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Duration
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {phases.map((phase) => (
                <tr key={phase.phase_name}>
                  <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-gray-900">
                    {phaseName(phase.phase_name)}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                    {formatPhaseDuration(phase.duration_minutes)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
