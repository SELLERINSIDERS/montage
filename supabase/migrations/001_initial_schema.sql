-- Supabase schema migration: Production Dashboard
-- Phase 03, Plan 01 -- Initial schema for productions, scenes, review_decisions
-- Run in Supabase Dashboard -> SQL Editor

-- Productions table (one row per production)
CREATE TABLE productions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  format TEXT NOT NULL CHECK (format IN ('vsl', 'ad', 'ugc')),
  slug TEXT NOT NULL,
  display_name TEXT,
  current_phase TEXT NOT NULL DEFAULT 'script',
  current_stage TEXT NOT NULL DEFAULT 'Script & Design',
  scene_count INTEGER NOT NULL DEFAULT 0,
  approved_count INTEGER NOT NULL DEFAULT 0,
  flagged_count INTEGER NOT NULL DEFAULT 0,
  pending_count INTEGER NOT NULL DEFAULT 0,
  latest_thumbnail_url TEXT,
  heartbeat_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed', 'error')),
  manifest_data JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  user_id UUID REFERENCES auth.users(id),
  UNIQUE(format, slug)
);

-- Scenes table (one row per scene per production)
CREATE TABLE scenes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  production_id UUID REFERENCES productions(id) ON DELETE CASCADE,
  scene_id TEXT NOT NULL,
  scene_index INTEGER NOT NULL,
  prompt_text TEXT,
  image_1k_status TEXT DEFAULT 'pending',
  image_2k_status TEXT DEFAULT 'pending',
  video_status TEXT DEFAULT 'pending',
  current_gate TEXT,
  gate_attempts INTEGER DEFAULT 0,
  feedback TEXT,
  flag_reasons TEXT[],
  image_storage_path TEXT,
  video_storage_path TEXT,
  thumbnail_storage_path TEXT,
  gate_timing JSONB,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(production_id, scene_id)
);

-- Review decisions (dashboard writes, pipeline reads)
CREATE TABLE review_decisions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  production_id UUID REFERENCES productions(id) ON DELETE CASCADE,
  scene_id TEXT NOT NULL,
  gate_type TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('approved', 'flagged', 'deferred')),
  flag_reasons TEXT[],
  feedback TEXT,
  decided_by UUID REFERENCES auth.users(id),
  decided_at TIMESTAMPTZ DEFAULT NOW(),
  synced_to_pipeline BOOLEAN DEFAULT FALSE
);

-- Row Level Security
ALTER TABLE productions ENABLE ROW LEVEL SECURITY;
ALTER TABLE scenes ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_decisions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own productions" ON productions
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users see own scenes" ON scenes
  FOR ALL USING (production_id IN (SELECT id FROM productions WHERE user_id = auth.uid()));

CREATE POLICY "Users manage own reviews" ON review_decisions
  FOR ALL USING (production_id IN (SELECT id FROM productions WHERE user_id = auth.uid()));

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE productions;
ALTER PUBLICATION supabase_realtime ADD TABLE scenes;

-- Indexes for performance
CREATE INDEX idx_productions_status ON productions(status) WHERE status = 'active';
CREATE INDEX idx_scenes_production ON scenes(production_id);
CREATE INDEX idx_review_unsynced ON review_decisions(synced_to_pipeline) WHERE synced_to_pipeline = FALSE;
