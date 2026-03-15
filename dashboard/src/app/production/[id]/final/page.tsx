import { createClient } from '@/lib/supabase/server'
import { notFound } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import { FinalReview } from '../final-review'
import type { FinalScene } from '@/components/review/final-scene-grid'
import type { VideoVersion } from '@/components/review/version-timeline'

interface Props {
  params: Promise<{ id: string }>
}

export default async function FinalReviewPage({ params }: Props) {
  const { id } = await params
  const supabase = await createClient()

  // Fetch production
  const { data: production, error: prodError } = await supabase
    .from('productions')
    .select('*')
    .eq('id', id)
    .single()

  if (prodError || !production) {
    notFound()
  }

  // Extract post_production scenes from production data
  const postProduction = (production as Record<string, unknown>).post_production as
    | Record<string, unknown>
    | null
    | undefined

  const manifestData = (production as Record<string, unknown>).manifest_data as
    | Record<string, unknown>
    | null
    | undefined

  // Get scenes from post_production EDL data or manifest
  let scenes: FinalScene[] = []
  if (postProduction && Array.isArray(postProduction.edl_scenes)) {
    scenes = (postProduction.edl_scenes as Record<string, unknown>[]).map(
      (s) => ({
        id: (s.id as string) || '',
        label: (s.label as string) || '',
        duration_s: (s.duration_s as number) || 0,
        start_s: (s.start_s as number) || 0,
        audio_type: (s.audio_type as string) || '',
      })
    )
  }

  // Fetch video versions from production_videos table
  const { data: videoVersions } = await supabase
    .from('production_videos')
    .select('*')
    .eq('production_id', id)
    .order('version', { ascending: true })

  const versions: VideoVersion[] = (videoVersions ?? []).map(
    (v: Record<string, unknown>) => ({
      version: (v.version as number) || 0,
      quality: (v.quality as string) || 'preview',
      storage_url: (v.storage_url as string) || '',
      rendered_at: (v.rendered_at as string) || '',
      render_duration_s: (v.render_duration_s as number) || 0,
      is_approved: (v.is_approved as boolean) || false,
    })
  )

  const displayName =
    (production as Record<string, unknown>).display_name ||
    (production as Record<string, unknown>).slug ||
    'Production'

  return (
    <div className="container mx-auto px-4 py-6 max-w-7xl">
      {/* Back button */}
      <Link
        href={`/production/${id}`}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="size-4" />
        Back to production
      </Link>

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold">
          Final Review: {displayName as string}
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Review rendered video, navigate by scene, and approve the final cut.
        </p>
      </div>

      {/* Final review component */}
      <FinalReview
        productionId={id}
        initialScenes={scenes}
        initialVersions={versions}
      />
    </div>
  )
}
