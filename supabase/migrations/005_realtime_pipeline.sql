-- Migration 005: Real-Time Pipeline Schema
-- Adds regeneration queue, generation events, prompt versioning,
-- and fixes the propagate_review_decision() trigger for the
-- feedback-to-regeneration pipeline.

-- ============================================================
-- 1. asset_status ENUM type
--    Available for new tables/columns. Not applied to existing
--    columns to avoid breaking running code.
-- ============================================================

DO $$ BEGIN
  CREATE TYPE asset_status AS ENUM (
    'pending',
    'generating',
    'generated',
    'approved',
    'flagged',
    'regenerating',
    'failed'
  );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- 2. New Tables
-- ============================================================

-- 2a. regeneration_queue — Job queue with claim semantics
--     Workers claim pending rows to prevent duplicate processing.
--     Flagged review decisions auto-enqueue via trigger (section 4).

CREATE TABLE IF NOT EXISTS regeneration_queue (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  production_id UUID NOT NULL REFERENCES productions(id) ON DELETE CASCADE,
  scene_id TEXT NOT NULL,
  gate_type TEXT NOT NULL,
  feedback_text TEXT,
  flag_reasons TEXT[],
  original_prompt TEXT,
  adjusted_prompt TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'claimed', 'processing', 'completed', 'failed')),
  claimed_by TEXT,
  claimed_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error_message TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2b. generation_events — Activity feed for real-time dashboard

CREATE TABLE IF NOT EXISTS generation_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  production_id UUID NOT NULL REFERENCES productions(id) ON DELETE CASCADE,
  scene_id TEXT,
  event_type TEXT NOT NULL,
  event_data JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2c. prompt_versions — Audit trail for prompt changes

CREATE TABLE IF NOT EXISTS prompt_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  production_id UUID NOT NULL REFERENCES productions(id) ON DELETE CASCADE,
  scene_id TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  prompt_text TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'original',
  feedback_reference TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(production_id, scene_id, version)
);

-- ============================================================
-- 3. Add columns to scenes table
--    regeneration_count: how many times this scene was regenerated
--    prompt_version: which prompt_versions.version is active
--    asset_state: free-text state tracker (mirrors asset_status values)
-- ============================================================

ALTER TABLE scenes ADD COLUMN IF NOT EXISTS regeneration_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS prompt_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS asset_state TEXT DEFAULT 'pending';

-- ============================================================
-- 4. Fix propagate_review_decision() trigger function
--    Fixes:
--    - Add image_2k gate_type handling (was missing)
--    - Clear flag_reasons on approval (was preserving stale reasons)
--    - Guard pending_count against going negative with GREATEST
--    - Auto-enqueue to regeneration_queue when decision = 'flagged'
-- ============================================================

CREATE OR REPLACE FUNCTION propagate_review_decision()
RETURNS TRIGGER AS $$
DECLARE
  _feedback_value TEXT;
  _approved_count INTEGER;
  _flagged_count  INTEGER;
  _scene_count    INTEGER;
  _original_prompt TEXT;
BEGIN
  -- Build the feedback value based on decision type
  CASE NEW.decision
    WHEN 'approved' THEN
      _feedback_value := 'approved';
    WHEN 'flagged' THEN
      _feedback_value := COALESCE(array_to_string(NEW.flag_reasons, ', '), '')
        || CASE
             WHEN NEW.feedback IS NOT NULL AND NEW.feedback != ''
             THEN ' -- ' || NEW.feedback
             ELSE ''
           END;
      IF _feedback_value = '' THEN
        _feedback_value := 'flagged';
      END IF;
    WHEN 'deferred' THEN
      _feedback_value := 'deferred';
    ELSE
      _feedback_value := NEW.decision;
  END CASE;

  -- Update the appropriate per-gate feedback column on the scene.
  -- On approval: clear flag_reasons. On flagged: set flag_reasons.
  CASE NEW.gate_type
    WHEN 'image_1k' THEN
      UPDATE scenes SET
        feedback_image = _feedback_value,
        current_gate   = NEW.gate_type || ':' || NEW.decision,
        flag_reasons   = CASE WHEN NEW.decision = 'approved' THEN '{}'
                              WHEN NEW.decision = 'flagged'  THEN NEW.flag_reasons
                              ELSE flag_reasons END,
        updated_at     = NOW()
      WHERE production_id = NEW.production_id
        AND scene_id = NEW.scene_id;

    WHEN 'image_2k' THEN
      UPDATE scenes SET
        feedback_image = _feedback_value,
        current_gate   = NEW.gate_type || ':' || NEW.decision,
        flag_reasons   = CASE WHEN NEW.decision = 'approved' THEN '{}'
                              WHEN NEW.decision = 'flagged'  THEN NEW.flag_reasons
                              ELSE flag_reasons END,
        updated_at     = NOW()
      WHERE production_id = NEW.production_id
        AND scene_id = NEW.scene_id;

    WHEN 'video_clip' THEN
      UPDATE scenes SET
        feedback_video = _feedback_value,
        current_gate   = NEW.gate_type || ':' || NEW.decision,
        flag_reasons   = CASE WHEN NEW.decision = 'approved' THEN '{}'
                              WHEN NEW.decision = 'flagged'  THEN NEW.flag_reasons
                              ELSE flag_reasons END,
        updated_at     = NOW()
      WHERE production_id = NEW.production_id
        AND scene_id = NEW.scene_id;

    WHEN 'final_video' THEN
      UPDATE scenes SET
        feedback_final = _feedback_value,
        current_gate   = NEW.gate_type || ':' || NEW.decision,
        flag_reasons   = CASE WHEN NEW.decision = 'approved' THEN '{}'
                              WHEN NEW.decision = 'flagged'  THEN NEW.flag_reasons
                              ELSE flag_reasons END,
        updated_at     = NOW()
      WHERE production_id = NEW.production_id
        AND scene_id = NEW.scene_id;

    ELSE
      RAISE WARNING 'propagate_review_decision: unknown gate_type "%"', NEW.gate_type;
  END CASE;

  -- Recompute productions counts with GREATEST guard against negatives
  SELECT COUNT(*) INTO _approved_count
    FROM scenes s
    WHERE s.production_id = NEW.production_id
      AND s.current_gate LIKE '%:approved';

  SELECT COUNT(*) INTO _flagged_count
    FROM scenes s
    WHERE s.production_id = NEW.production_id
      AND s.current_gate LIKE '%:flagged';

  SELECT scene_count INTO _scene_count
    FROM productions
    WHERE id = NEW.production_id;

  UPDATE productions SET
    approved_count = _approved_count,
    flagged_count  = _flagged_count,
    pending_count  = GREATEST(0, _scene_count - _approved_count - _flagged_count),
    updated_at     = NOW()
  WHERE id = NEW.production_id;

  -- Auto-enqueue flagged decisions to regeneration_queue
  IF NEW.decision = 'flagged' THEN
    -- Grab the original prompt for the regeneration job
    SELECT prompt_text INTO _original_prompt
      FROM scenes
      WHERE production_id = NEW.production_id
        AND scene_id = NEW.scene_id;

    INSERT INTO regeneration_queue (
      production_id,
      scene_id,
      gate_type,
      feedback_text,
      flag_reasons,
      original_prompt,
      status
    ) VALUES (
      NEW.production_id,
      NEW.scene_id,
      NEW.gate_type,
      NEW.feedback,
      NEW.flag_reasons,
      _original_prompt,
      'pending'
    );

    -- Increment regeneration_count on the scene
    UPDATE scenes SET
      regeneration_count = regeneration_count + 1,
      asset_state = 'flagged',
      updated_at = NOW()
    WHERE production_id = NEW.production_id
      AND scene_id = NEW.scene_id;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Re-bind the trigger (unchanged target, but function body is replaced)
DROP TRIGGER IF EXISTS trg_propagate_review_decision ON review_decisions;
CREATE TRIGGER trg_propagate_review_decision
  AFTER INSERT ON review_decisions
  FOR EACH ROW
  EXECUTE FUNCTION propagate_review_decision();

-- ============================================================
-- 5. Generic set_updated_at() trigger function
--    Applied to all tables with an updated_at column.
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- scenes
DROP TRIGGER IF EXISTS trg_scenes_updated_at ON scenes;
CREATE TRIGGER trg_scenes_updated_at
  BEFORE UPDATE ON scenes
  FOR EACH ROW
  EXECUTE FUNCTION set_updated_at();

-- productions
DROP TRIGGER IF EXISTS trg_productions_updated_at ON productions;
CREATE TRIGGER trg_productions_updated_at
  BEFORE UPDATE ON productions
  FOR EACH ROW
  EXECUTE FUNCTION set_updated_at();

-- regeneration_queue
DROP TRIGGER IF EXISTS trg_regen_queue_updated_at ON regeneration_queue;
CREATE TRIGGER trg_regen_queue_updated_at
  BEFORE UPDATE ON regeneration_queue
  FOR EACH ROW
  EXECUTE FUNCTION set_updated_at();

-- production_videos
DROP TRIGGER IF EXISTS trg_production_videos_updated_at ON production_videos;
CREATE TRIGGER trg_production_videos_updated_at
  BEFORE UPDATE ON production_videos
  FOR EACH ROW
  EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- 6. Indexes
-- ============================================================

-- Composite index on scenes for production + gate queries
CREATE INDEX IF NOT EXISTS idx_scenes_production_gate
  ON scenes(production_id, current_gate);

-- Composite index on review_decisions for dedup queries
CREATE INDEX IF NOT EXISTS idx_review_decisions_scene_gate
  ON review_decisions(production_id, scene_id, gate_type);

-- Regeneration queue: pending jobs (partial index)
CREATE INDEX IF NOT EXISTS idx_regen_queue_pending
  ON regeneration_queue(status, created_at)
  WHERE status = 'pending';

-- Regeneration queue: production lookup
CREATE INDEX IF NOT EXISTS idx_regen_queue_production
  ON regeneration_queue(production_id);

-- Generation events: recent events per production
CREATE INDEX IF NOT EXISTS idx_gen_events_production
  ON generation_events(production_id, created_at DESC);

-- Prompt versions: lookup by scene
CREATE INDEX IF NOT EXISTS idx_prompt_versions_scene
  ON prompt_versions(production_id, scene_id);

-- ============================================================
-- 7. Enable Realtime
-- ============================================================

ALTER PUBLICATION supabase_realtime ADD TABLE review_decisions;
ALTER PUBLICATION supabase_realtime ADD TABLE regeneration_queue;
ALTER PUBLICATION supabase_realtime ADD TABLE generation_events;

-- ============================================================
-- 8. Row Level Security
--    Same pattern as existing tables: users see rows for their
--    own productions via subquery on productions.user_id.
-- ============================================================

ALTER TABLE regeneration_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE generation_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE prompt_versions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own regen queue" ON regeneration_queue
  FOR ALL USING (production_id IN (
    SELECT id FROM productions WHERE user_id = auth.uid()
  ));

CREATE POLICY "Users see own gen events" ON generation_events
  FOR ALL USING (production_id IN (
    SELECT id FROM productions WHERE user_id = auth.uid()
  ));

CREATE POLICY "Users see own prompt versions" ON prompt_versions
  FOR ALL USING (production_id IN (
    SELECT id FROM productions WHERE user_id = auth.uid()
  ));
