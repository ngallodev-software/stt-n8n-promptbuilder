-- HUMAN REVIEW REQUIRED before running against live DB
-- Phase 2: append-only delivery attempt history

CREATE TABLE IF NOT EXISTS delivery_attempts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  delivery_id UUID NOT NULL REFERENCES deliveries(id),
  target_id UUID REFERENCES delivery_targets(id),
  attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  outcome VARCHAR(32) NOT NULL DEFAULT 'pending', -- pending/success/failure/skipped
  error_detail TEXT,
  response_payload JSONB
);

ALTER TABLE deliveries ADD COLUMN IF NOT EXISTS latest_attempt_id UUID REFERENCES delivery_attempts(id);
