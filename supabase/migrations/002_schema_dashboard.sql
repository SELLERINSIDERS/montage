-- Supabase schema migration: Dashboard Integration
-- Phase 08 -- Adds production_videos table, analytics/post_production columns
-- Run in Supabase Dashboard -> SQL Editor

-- production_videos table (tracks rendered video versions per production)
CREATE TABLE IF NOT EXISTS production_videos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  production_id UUID NOT NULL REFERENCES productions(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  quality TEXT NOT NULL CHECK (quality IN ('preview', 'final')),
  storage_url TEXT,
  rendered_at TIMESTAMPTZ,
  render_duration_s REAL,
  is_approved BOOLEAN NOT NULL DEFAULT FALSE,
  file_size_bytes BIGINT,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(production_id, version, quality)
);

-- Add JSONB columns to productions for dashboard analytics and post-production data
ALTER TABLE productions ADD COLUMN IF NOT EXISTS analytics JSONB DEFAULT '{}'::jsonb;
ALTER TABLE productions ADD COLUMN IF NOT EXISTS post_production JSONB DEFAULT '{}'::jsonb;

-- Row Level Security for production_videos
ALTER TABLE production_videos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own videos" ON production_videos
  FOR ALL USING (production_id IN (SELECT id FROM productions WHERE user_id = auth.uid()));

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_production_videos_production ON production_videos(production_id);
CREATE INDEX IF NOT EXISTS idx_production_videos_approved ON production_videos(is_approved) WHERE is_approved = TRUE;

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE production_videos;
