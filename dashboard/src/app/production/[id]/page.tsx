import { createClient } from '@/lib/supabase/server'
import { notFound } from 'next/navigation'
import type { Production, Scene } from '@/lib/types'
import { ProductionDetail } from '@/components/review/production-detail'
import { ProductionAnalytics } from './analytics'
import { unstable_noStore as noStore } from 'next/cache'

export const dynamic = 'force-dynamic'

interface Props {
  params: Promise<{ id: string }>
}

export default async function ProductionDetailPage({ params }: Props) {
  noStore()
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

  // Fetch all scenes ordered by scene_index
  const { data: scenes } = await supabase
    .from('scenes')
    .select('*')
    .eq('production_id', id)
    .order('scene_index', { ascending: true })

  const sceneList: Scene[] = (scenes ?? []) as Scene[]

  // Build public URLs for thumbnails, images, and videos
  // The production-assets bucket is public, so we use getPublicUrl instead of signed URLs
  const signedUrls: Record<string, { thumbnail?: string; image?: string; video?: string }> = {}

  for (const scene of sceneList) {
    const urls: { thumbnail?: string; image?: string; video?: string } = {}

    if (scene.thumbnail_storage_path) {
      const { data } = supabase.storage
        .from('production-assets')
        .getPublicUrl(scene.thumbnail_storage_path)
      urls.thumbnail = data.publicUrl
    }

    if (scene.image_storage_path) {
      const { data } = supabase.storage
        .from('production-assets')
        .getPublicUrl(scene.image_storage_path)
      urls.image = data.publicUrl
    }

    if (scene.video_storage_path) {
      const { data } = supabase.storage
        .from('production-assets')
        .getPublicUrl(scene.video_storage_path)
      urls.video = data.publicUrl
    }

    if (urls.thumbnail || urls.image || urls.video) {
      signedUrls[scene.id] = urls
    }
  }

  // Extract analytics from production record (pushed by DashboardSync)
  const analyticsData = (production as Record<string, unknown>).analytics as
    | Record<string, unknown>
    | null
    | undefined

  return (
    <>
      <ProductionDetail
        production={production as Production}
        scenes={sceneList}
        signedUrls={signedUrls}
      />
      <div className="mx-auto max-w-7xl px-4 pb-8 sm:px-6 lg:px-8">
        <ProductionAnalytics analytics={analyticsData as Parameters<typeof ProductionAnalytics>[0]['analytics']} />
      </div>
    </>
  )
}
