-- Migration 007: Fix RLS on regeneration_queue for trigger-based inserts
--
-- Problem: When a user flags a scene from the dashboard, the flow is:
--   1. Client inserts into review_decisions (allowed by RLS)
--   2. Trigger propagate_review_decision() fires
--   3. Trigger inserts into regeneration_queue -> BLOCKED by RLS
--
-- The trigger function runs as SECURITY INVOKER by default, so the
-- INSERT into regeneration_queue is evaluated against the user's RLS
-- policies. The existing policy only has a USING clause (which covers
-- SELECT/UPDATE/DELETE) but INSERT requires WITH CHECK.
--
-- Fix: Two-part approach:
--   A. Add an explicit WITH CHECK clause to the regeneration_queue policy
--      so authenticated users can INSERT rows for their own productions.
--   B. Mark propagate_review_decision() as SECURITY DEFINER so its
--      internal cross-table writes (scenes, productions, regeneration_queue)
--      bypass RLS. This is the correct pattern for cascade triggers.

-- ============================================================
-- Part A: Replace the regeneration_queue RLS policy
--         Add explicit WITH CHECK for INSERT operations
-- ============================================================

DROP POLICY IF EXISTS "Users see own regen queue" ON regeneration_queue;

CREATE POLICY "Users manage own regen queue" ON regeneration_queue
  FOR ALL
  USING (production_id IN (
    SELECT id FROM productions WHERE user_id = auth.uid()
  ))
  WITH CHECK (production_id IN (
    SELECT id FROM productions WHERE user_id = auth.uid()
  ));

-- ============================================================
-- Part B: Make propagate_review_decision() SECURITY DEFINER
--         so trigger-based inserts bypass RLS entirely.
--         This is safe because the trigger only fires on
--         authorized inserts into review_decisions (which has
--         its own RLS policy).
-- ============================================================

ALTER FUNCTION propagate_review_decision() SECURITY DEFINER;

-- ============================================================
-- Part C: Apply the same fix to generation_events and
--         prompt_versions for consistency. These tables also
--         only have USING without WITH CHECK.
-- ============================================================

DROP POLICY IF EXISTS "Users see own gen events" ON generation_events;

CREATE POLICY "Users manage own gen events" ON generation_events
  FOR ALL
  USING (production_id IN (
    SELECT id FROM productions WHERE user_id = auth.uid()
  ))
  WITH CHECK (production_id IN (
    SELECT id FROM productions WHERE user_id = auth.uid()
  ));

DROP POLICY IF EXISTS "Users see own prompt versions" ON prompt_versions;

CREATE POLICY "Users manage own prompt versions" ON prompt_versions
  FOR ALL
  USING (production_id IN (
    SELECT id FROM productions WHERE user_id = auth.uid()
  ))
  WITH CHECK (production_id IN (
    SELECT id FROM productions WHERE user_id = auth.uid()
  ));
