-- Migration 006: Fix Regeneration Pipeline
-- Addresses duplicate job prevention, asset_state consistency,
-- foreign key integrity, stale job reclamation, and index cleanup.

-- ============================================================
-- 1. Prevent Duplicate Regeneration Jobs [CRITICAL]
--    Partial unique index ensures only one active job per
--    scene+gate combination at any time.
-- ============================================================

CREATE UNIQUE INDEX IF NOT EXISTS idx_regen_queue_active_scene_gate
  ON regeneration_queue(production_id, scene_id, gate_type)
  WHERE status IN ('pending', 'claimed', 'processing');

-- ============================================================
-- 2. CHECK Constraint on scenes.asset_state [MEDIUM]
--    Enforces the known set of valid states at the DB level.
-- ============================================================

DO $$ BEGIN
  ALTER TABLE scenes ADD CONSTRAINT chk_scenes_asset_state
    CHECK (asset_state IS NULL OR asset_state IN (
      'pending', 'generating', 'generated', 'approved',
      'flagged', 'regenerating', 'failed'
    ));
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- 3. Composite FK: regeneration_queue -> scenes [MEDIUM]
--    Uses the existing UNIQUE(production_id, scene_id) on scenes.
-- ============================================================

DO $$ BEGIN
  ALTER TABLE regeneration_queue
    ADD CONSTRAINT fk_regen_queue_scene
    FOREIGN KEY (production_id, scene_id)
    REFERENCES scenes(production_id, scene_id)
    ON DELETE CASCADE;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- 4. Composite FK: review_decisions -> scenes [MEDIUM]
--    Uses the existing UNIQUE(production_id, scene_id) on scenes.
-- ============================================================

DO $$ BEGIN
  ALTER TABLE review_decisions
    ADD CONSTRAINT fk_review_decisions_scene
    FOREIGN KEY (production_id, scene_id)
    REFERENCES scenes(production_id, scene_id)
    ON DELETE CASCADE;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- 5. Rewrite propagate_review_decision() [CRITICAL]
--    Changes from migration 005:
--    - asset_state = 'approved' on approval decisions
--    - ON CONFLICT dedup for regeneration_queue inserts
--    All existing functionality preserved.
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
  -- On approval: clear flag_reasons AND set asset_state = 'approved'.
  -- On flagged: set flag_reasons; asset_state set later in regen block.
  CASE NEW.gate_type
    WHEN 'image_1k' THEN
      UPDATE scenes SET
        feedback_image = _feedback_value,
        current_gate   = NEW.gate_type || ':' || NEW.decision,
        flag_reasons   = CASE WHEN NEW.decision = 'approved' THEN '{}'
                              WHEN NEW.decision = 'flagged'  THEN NEW.flag_reasons
                              ELSE flag_reasons END,
        asset_state    = CASE WHEN NEW.decision = 'approved' THEN 'approved'
                              WHEN NEW.decision = 'flagged'  THEN asset_state
                              ELSE asset_state END,
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
        asset_state    = CASE WHEN NEW.decision = 'approved' THEN 'approved'
                              WHEN NEW.decision = 'flagged'  THEN asset_state
                              ELSE asset_state END,
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
        asset_state    = CASE WHEN NEW.decision = 'approved' THEN 'approved'
                              WHEN NEW.decision = 'flagged'  THEN asset_state
                              ELSE asset_state END,
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
        asset_state    = CASE WHEN NEW.decision = 'approved' THEN 'approved'
                              WHEN NEW.decision = 'flagged'  THEN asset_state
                              ELSE asset_state END,
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
  -- Uses ON CONFLICT to update feedback on duplicate active jobs
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
    )
    ON CONFLICT (production_id, scene_id, gate_type)
      WHERE status IN ('pending', 'claimed', 'processing')
    DO UPDATE SET
      feedback_text  = EXCLUDED.feedback_text,
      flag_reasons   = EXCLUDED.flag_reasons,
      original_prompt = EXCLUDED.original_prompt,
      updated_at     = NOW();

    -- Increment regeneration_count and set asset_state = 'flagged'
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

-- Re-bind the trigger (function body is replaced above)
DROP TRIGGER IF EXISTS trg_propagate_review_decision ON review_decisions;
CREATE TRIGGER trg_propagate_review_decision
  AFTER INSERT ON review_decisions
  FOR EACH ROW
  EXECUTE FUNCTION propagate_review_decision();

-- ============================================================
-- 6. Stale Job Reclaim Function [HIGH]
--    Recovers stuck jobs that exceeded the timeout threshold.
--    Jobs under max_attempts are re-queued as 'pending'.
--    Jobs at or above max_attempts are marked 'failed'.
--    Returns total number of jobs affected.
-- ============================================================

CREATE OR REPLACE FUNCTION reclaim_stuck_regen_jobs(
  p_timeout_minutes INTEGER DEFAULT 15
)
RETURNS INTEGER AS $$
DECLARE
  _reclaimed INTEGER := 0;
  _failed INTEGER := 0;
BEGIN
  -- Re-queue jobs that haven't exceeded max_attempts
  WITH reclaimed AS (
    UPDATE regeneration_queue
    SET status = 'pending',
        claimed_by = NULL,
        claimed_at = NULL
    WHERE status IN ('claimed', 'processing')
      AND updated_at < NOW() - (p_timeout_minutes * INTERVAL '1 minute')
      AND attempt_count < max_attempts
    RETURNING production_id, scene_id
  )
  SELECT COUNT(*) INTO _reclaimed FROM reclaimed;

  -- Also reset corresponding scenes back to 'flagged'
  UPDATE scenes SET asset_state = 'flagged'
  WHERE (production_id, scene_id) IN (
    SELECT production_id, scene_id FROM regeneration_queue
    WHERE status = 'pending'
      AND claimed_by IS NULL
      AND updated_at > NOW() - INTERVAL '1 minute'
  );

  -- Fail jobs that exceeded max_attempts
  WITH failed AS (
    UPDATE regeneration_queue
    SET status = 'failed',
        error_message = 'Exceeded max attempts after worker timeout',
        completed_at = NOW()
    WHERE status IN ('claimed', 'processing')
      AND updated_at < NOW() - (p_timeout_minutes * INTERVAL '1 minute')
      AND attempt_count >= max_attempts
    RETURNING production_id, scene_id
  )
  SELECT COUNT(*) INTO _failed FROM failed;

  -- Set failed scenes to 'failed' state
  UPDATE scenes SET asset_state = 'failed'
  WHERE (production_id, scene_id) IN (
    SELECT production_id, scene_id FROM regeneration_queue
    WHERE status = 'failed'
      AND error_message = 'Exceeded max attempts after worker timeout'
      AND completed_at > NOW() - INTERVAL '1 minute'
  );

  RETURN _reclaimed + _failed;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 7. Drop Redundant Index [LOW]
--    idx_review_unsynced (from 001) is superseded by the
--    composite idx_review_decisions_pipeline_sync (from 004).
-- ============================================================

DROP INDEX IF EXISTS idx_review_unsynced;

-- ============================================================
-- 8. Optimize Pending Queue Index [LOW]
--    Remove status from index columns — the partial WHERE
--    clause already filters to status = 'pending', so including
--    status in the B-tree wastes space.
-- ============================================================

DROP INDEX IF EXISTS idx_regen_queue_pending;
CREATE INDEX idx_regen_queue_pending
  ON regeneration_queue(created_at)
  WHERE status = 'pending';
