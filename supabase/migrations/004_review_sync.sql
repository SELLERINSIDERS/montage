-- Migration 004: Review Sync
-- Adds per-gate feedback columns to scenes, a trigger on review_decisions
-- that propagates decisions to scenes and recomputes productions counts,
-- and a partial index for efficient pipeline sync queries.

-- ============================================================
-- 1. Per-gate feedback columns on scenes
--    These supplement (not replace) the existing `feedback` column.
--    Each maps to a specific review gate in the pipeline.
-- ============================================================

ALTER TABLE scenes ADD COLUMN IF NOT EXISTS feedback_image TEXT;
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS feedback_video TEXT;
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS feedback_final TEXT;

-- ============================================================
-- 2. Trigger function: propagate_review_decision()
--    Fires AFTER INSERT on review_decisions.
--    - Maps gate_type to the correct per-gate feedback column
--    - Updates the scene row with decision outcome
--    - Recomputes approved/flagged/pending counts on productions
--    Idempotent: overwrites prior values for same scene+gate.
-- ============================================================

CREATE OR REPLACE FUNCTION propagate_review_decision()
RETURNS TRIGGER AS $$
DECLARE
  _feedback_value TEXT;
BEGIN
  -- Build the feedback value based on decision type
  CASE NEW.decision
    WHEN 'approved' THEN
      _feedback_value := 'approved';
    WHEN 'flagged' THEN
      _feedback_value := COALESCE(array_to_string(NEW.flag_reasons, ', '), '')
        || CASE
             WHEN NEW.feedback IS NOT NULL AND NEW.feedback != ''
             THEN ' — ' || NEW.feedback
             ELSE ''
           END;
      -- Ensure we don't store an empty string
      IF _feedback_value = '' THEN
        _feedback_value := 'flagged';
      END IF;
    WHEN 'deferred' THEN
      _feedback_value := 'deferred';
    ELSE
      _feedback_value := NEW.decision;
  END CASE;

  -- Update the appropriate per-gate feedback column on the scene.
  -- Also update current_gate (e.g. 'image_1k:approved') and flag_reasons.
  CASE NEW.gate_type
    WHEN 'image_1k' THEN
      UPDATE scenes SET
        feedback_image = _feedback_value,
        current_gate   = NEW.gate_type || ':' || NEW.decision,
        flag_reasons   = CASE WHEN NEW.decision = 'flagged' THEN NEW.flag_reasons ELSE flag_reasons END,
        updated_at     = NOW()
      WHERE production_id = NEW.production_id
        AND scene_id = NEW.scene_id;

    WHEN 'video_clip' THEN
      UPDATE scenes SET
        feedback_video = _feedback_value,
        current_gate   = NEW.gate_type || ':' || NEW.decision,
        flag_reasons   = CASE WHEN NEW.decision = 'flagged' THEN NEW.flag_reasons ELSE flag_reasons END,
        updated_at     = NOW()
      WHERE production_id = NEW.production_id
        AND scene_id = NEW.scene_id;

    WHEN 'final_video' THEN
      UPDATE scenes SET
        feedback_final = _feedback_value,
        current_gate   = NEW.gate_type || ':' || NEW.decision,
        flag_reasons   = CASE WHEN NEW.decision = 'flagged' THEN NEW.flag_reasons ELSE flag_reasons END,
        updated_at     = NOW()
      WHERE production_id = NEW.production_id
        AND scene_id = NEW.scene_id;

    ELSE
      -- Unknown gate_type: log but don't fail
      RAISE WARNING 'propagate_review_decision: unknown gate_type "%"', NEW.gate_type;
  END CASE;

  -- Recompute productions counts based on current_gate values.
  -- current_gate is overwritten (not appended) so counts are always correct
  -- even when the same scene+gate receives multiple decisions.
  UPDATE productions SET
    approved_count = (
      SELECT COUNT(*) FROM scenes s
      WHERE s.production_id = NEW.production_id
        AND s.current_gate LIKE '%:approved'
    ),
    flagged_count = (
      SELECT COUNT(*) FROM scenes s
      WHERE s.production_id = NEW.production_id
        AND s.current_gate LIKE '%:flagged'
    ),
    pending_count = scene_count - (
      SELECT COUNT(*) FROM scenes s
      WHERE s.production_id = NEW.production_id
        AND s.current_gate LIKE '%:approved'
    ) - (
      SELECT COUNT(*) FROM scenes s
      WHERE s.production_id = NEW.production_id
        AND s.current_gate LIKE '%:flagged'
    )
  WHERE id = NEW.production_id;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 3. Trigger: fire after every insert on review_decisions
-- ============================================================

DROP TRIGGER IF EXISTS trg_propagate_review_decision ON review_decisions;
CREATE TRIGGER trg_propagate_review_decision
  AFTER INSERT ON review_decisions
  FOR EACH ROW
  EXECUTE FUNCTION propagate_review_decision();

-- ============================================================
-- 4. Partial index for pipeline sync queries (DBSYNC-03)
--    Efficiently finds unsynced decisions per production.
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_review_decisions_pipeline_sync
  ON review_decisions(production_id, synced_to_pipeline)
  WHERE synced_to_pipeline = FALSE;
