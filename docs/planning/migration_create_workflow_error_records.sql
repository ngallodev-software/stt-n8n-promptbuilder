-- Phase 2: workflow error records for watcher parse/dispatch failures

CREATE TABLE IF NOT EXISTS workflow_error_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  note_path TEXT,
  delivery_id UUID REFERENCES deliveries(id),
  error_type VARCHAR(64) NOT NULL,
  error_message TEXT NOT NULL,
  failed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  dismissed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workflow_error_records_created_at_idx
  ON workflow_error_records (created_at DESC);
