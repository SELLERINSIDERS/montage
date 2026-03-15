-- Migration 008: Auto Video Generation on Image Approval
--
-- 1. Add video_prompt column to scenes table (stores Kling motion prompt
--    separately from the image generation prompt in prompt_text).
-- 2. Rewrite propagate_review_decision() to:
--    a. Use video_prompt (not prompt_text) as original_prompt for video flags
--    b. Auto-enqueue a video_clip job when an image gate is approved
--       so video generation starts immediately without manual intervention.

-- ============================================================
-- 1. Add video_prompt column to scenes [CRITICAL]
-- ============================================================

ALTER TABLE scenes ADD COLUMN IF NOT EXISTS video_prompt TEXT;

-- ============================================================
-- 2. Rewrite propagate_review_decision() [CRITICAL]
--    Changes from migration 006:
--    - Uses video_prompt for video gate flagging
--    - Auto-enqueues video_clip job on image approval
--    All other functionality preserved.
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

  -- ----------------------------------------------------------------
  -- Auto-enqueue flagged decisions to regeneration_queue
  -- Uses ON CONFLICT to update feedback on duplicate active jobs
  -- ----------------------------------------------------------------
  IF NEW.decision = 'flagged' THEN
    -- Select the correct prompt based on gate type:
    -- video gates use video_prompt, image gates use prompt_text
    IF NEW.gate_type IN ('video_clip', 'video', 'final_video') THEN
      SELECT video_prompt INTO _original_prompt
        FROM scenes
        WHERE production_id = NEW.production_id
          AND scene_id = NEW.scene_id;
    ELSE
      SELECT prompt_text INTO _original_prompt
        FROM scenes
        WHERE production_id = NEW.production_id
          AND scene_id = NEW.scene_id;
    END IF;

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

  -- ----------------------------------------------------------------
  -- Auto-enqueue video generation when an image gate is approved
  -- This triggers video creation from the approved image automatically.
  -- ----------------------------------------------------------------
  IF NEW.decision = 'approved' AND NEW.gate_type IN ('image_1k', 'image_2k') THEN
    -- Get the video prompt for this scene (may be NULL if not yet populated;
    -- the pipeline will fall back to reading from camera_plan.json on disk)
    SELECT video_prompt INTO _original_prompt
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
      'video_clip',
      'Auto-triggered: image approved — generating video from approved image',
      '{}',
      _original_prompt,
      'pending'
    )
    ON CONFLICT (production_id, scene_id, gate_type)
      WHERE status IN ('pending', 'claimed', 'processing')
    DO UPDATE SET
      feedback_text   = EXCLUDED.feedback_text,
      flag_reasons    = EXCLUDED.flag_reasons,
      original_prompt = EXCLUDED.original_prompt,
      updated_at      = NOW();
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
