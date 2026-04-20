-- Adds versioning guards, persistent session registry rows, and exact error history.
-- Safe to apply after promptforge_postgres_schema.sql on an existing database.

CREATE UNIQUE INDEX IF NOT EXISTS idx_rulesets_active_global
    ON rulesets(scope)
    WHERE is_active AND project_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_rulesets_active_project
    ON rulesets(scope, project_id)
    WHERE is_active AND project_id IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_projects_active_ruleset_id'
    ) THEN
        ALTER TABLE projects
        ADD CONSTRAINT fk_projects_active_ruleset_id
        FOREIGN KEY (active_ruleset_id) REFERENCES rulesets(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_projects_active_ruleset_id
    ON projects(active_ruleset_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_templates_active_global
    ON prompt_templates(scope, prompt_type)
    WHERE is_active AND project_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_templates_active_project
    ON prompt_templates(scope, project_id, prompt_type)
    WHERE is_active AND project_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS delivery_session_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    delivery_target_id UUID NULL REFERENCES delivery_targets(id) ON DELETE SET NULL,
    target_type pf_target_type NOT NULL,
    target_identifier TEXT NOT NULL,
    session_identifier TEXT NOT NULL,
    session_status TEXT NOT NULL DEFAULT 'active',
    provider_name TEXT NULL,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    is_attached BOOLEAN NOT NULL DEFAULT TRUE,
    is_busy BOOLEAN NOT NULL DEFAULT FALSE,
    is_reachable BOOLEAN NOT NULL DEFAULT TRUE,
    is_stale BOOLEAN NOT NULL DEFAULT FALSE,
    last_seen_at TIMESTAMPTZ NULL,
    heartbeat_at TIMESTAMPTZ NULL,
    ended_at TIMESTAMPTZ NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_delivery_session_registry_target_identifier_nonempty CHECK (length(trim(target_identifier)) > 0),
    CONSTRAINT chk_delivery_session_registry_session_identifier_nonempty CHECK (length(trim(session_identifier)) > 0),
    CONSTRAINT chk_delivery_session_registry_session_status CHECK (
        session_status IN ('active', 'stale', 'closed', 'failed')
    ),
    CONSTRAINT chk_delivery_session_registry_target_type CHECK (
        target_type IN ('chat_session', 'claude_session', 'codex_session')
    )
);

CREATE INDEX IF NOT EXISTS idx_delivery_session_registry_target
    ON delivery_session_registry(target_type, target_identifier, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_delivery_session_registry_status
    ON delivery_session_registry(session_status, is_current);
CREATE UNIQUE INDEX IF NOT EXISTS idx_delivery_session_registry_session_identifier
    ON delivery_session_registry(session_identifier);
CREATE UNIQUE INDEX IF NOT EXISTS idx_delivery_session_registry_current_target
    ON delivery_session_registry(target_type, target_identifier)
    WHERE is_current;
CREATE INDEX IF NOT EXISTS idx_delivery_session_registry_delivery_target_id
    ON delivery_session_registry(delivery_target_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_deliveries_session_identifier
    ON deliveries(session_identifier);

DROP TRIGGER IF EXISTS trg_delivery_session_registry_updated_at ON delivery_session_registry;
CREATE TRIGGER trg_delivery_session_registry_updated_at
BEFORE UPDATE ON delivery_session_registry
FOR EACH ROW
EXECUTE FUNCTION pf_set_updated_at();

CREATE TABLE IF NOT EXISTS workflow_error_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_kind TEXT NOT NULL,
    project_id UUID NULL REFERENCES projects(id) ON DELETE SET NULL,
    intake_note_id UUID NULL REFERENCES intake_notes(id) ON DELETE SET NULL,
    utterance_id UUID NULL REFERENCES utterances(id) ON DELETE SET NULL,
    prompt_generation_id UUID NULL REFERENCES prompt_generations(id) ON DELETE SET NULL,
    delivery_id UUID NULL REFERENCES deliveries(id) ON DELETE SET NULL,
    processing_run_id UUID NULL REFERENCES processing_runs(id) ON DELETE SET NULL,
    delivery_target_id UUID NULL REFERENCES delivery_targets(id) ON DELETE SET NULL,
    stage_name TEXT NULL,
    error_class TEXT NULL,
    error_code TEXT NULL,
    error_message TEXT NOT NULL,
    error_context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    human_intervention_required BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_workflow_error_records_source_kind CHECK (
        source_kind IN (
            'intake_note',
            'utterance',
            'prompt_generation',
            'delivery',
            'processing_run',
            'console_action',
            'system'
        )
    ),
    CONSTRAINT chk_workflow_error_records_message_nonempty CHECK (length(trim(error_message)) > 0),
    CONSTRAINT chk_workflow_error_records_source_present CHECK (
        intake_note_id IS NOT NULL
        OR utterance_id IS NOT NULL
        OR prompt_generation_id IS NOT NULL
        OR delivery_id IS NOT NULL
        OR processing_run_id IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_workflow_error_records_created_at
    ON workflow_error_records(created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_error_records_source_kind
    ON workflow_error_records(source_kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_error_records_human_intervention
    ON workflow_error_records(human_intervention_required, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_error_records_project_id
    ON workflow_error_records(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_error_records_intake_note_id
    ON workflow_error_records(intake_note_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_error_records_utterance_id
    ON workflow_error_records(utterance_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_error_records_delivery_id
    ON workflow_error_records(delivery_id);
CREATE INDEX IF NOT EXISTS idx_workflow_error_records_delivery_target_id
    ON workflow_error_records(delivery_target_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_error_records_processing_run_id
    ON workflow_error_records(processing_run_id);
CREATE INDEX IF NOT EXISTS idx_workflow_error_records_prompt_generation_id
    ON workflow_error_records(prompt_generation_id);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_workflow_error_records_source_present'
    ) THEN
        ALTER TABLE workflow_error_records
        DROP CONSTRAINT chk_workflow_error_records_source_present;
    END IF;
    ALTER TABLE workflow_error_records
    ADD CONSTRAINT chk_workflow_error_records_source_present CHECK (
        source_kind IN ('console_action', 'system')
        OR intake_note_id IS NOT NULL
        OR utterance_id IS NOT NULL
        OR prompt_generation_id IS NOT NULL
        OR delivery_id IS NOT NULL
        OR processing_run_id IS NOT NULL
        OR delivery_target_id IS NOT NULL
        OR project_id IS NOT NULL
    );
END $$;
