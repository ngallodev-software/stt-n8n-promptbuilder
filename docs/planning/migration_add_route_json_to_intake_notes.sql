-- Migration: Add route_json column to intake_notes
-- Date: 2026-04-24
-- Purpose: Store recursive voice routing metadata for notes processed under Inbox/Voice/**

-- Add route_json column with default empty object
ALTER TABLE intake_notes
ADD COLUMN IF NOT EXISTS route_json JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Index for route family queries
CREATE INDEX IF NOT EXISTS idx_intake_notes_route_family
ON intake_notes ((route_json->>'route_family'));

-- Index for supported routes
CREATE INDEX IF NOT EXISTS idx_intake_notes_route_supported
ON intake_notes ((route_json->>'supported'));
