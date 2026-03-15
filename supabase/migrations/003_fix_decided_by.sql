-- Fix: review_decisions.decided_by was UUID REFERENCES auth.users(id),
-- but dashboard writes user UUID strings (or 'anonymous' fallback).
-- Change to TEXT and drop the FK constraint for flexibility.

ALTER TABLE review_decisions DROP CONSTRAINT IF EXISTS review_decisions_decided_by_fkey;
ALTER TABLE review_decisions ALTER COLUMN decided_by TYPE TEXT;
