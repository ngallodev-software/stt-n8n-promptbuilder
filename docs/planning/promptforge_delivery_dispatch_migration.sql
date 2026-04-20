-- Adds dispatch traceability columns to deliveries without changing existing rows.

ALTER TABLE IF EXISTS deliveries
    ADD COLUMN IF NOT EXISTS session_identifier TEXT NULL;

ALTER TABLE IF EXISTS deliveries
    ADD COLUMN IF NOT EXISTS dispatch_request_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE IF EXISTS deliveries
    ADD COLUMN IF NOT EXISTS dispatch_response_json JSONB NOT NULL DEFAULT '{}'::jsonb;
