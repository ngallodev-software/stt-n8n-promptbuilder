-- PromptForge MVP Postgres Schema
-- Production-grade baseline schema for an Obsidian-first voice-to-prompt system.
--
-- Design goals:
--   - Obsidian note is the human-facing intake artifact.
--   - Postgres is the canonical system of record.
--   - Text stages are append-only and queryable.
--   - Prompt generation and delivery are separate lifecycle domains.
--   - Rules and templates use append-only version rows with active pointers.
--   - Targets and live sessions support scoped overrides and traceability.
--   - Exact error records are stored separately from read-time fingerprints.
--   - The schema is optimized for auditability, reproducibility, and extension.
--
-- Scope precedence is implemented in application logic:
--   project > user > global
--
-- Assumptions:
--   - Single-user MVP today, but schema leaves room for future multi-user use.
--   - Source vault is on Debian host and watcher imports eligible notes.
--   - Deterministic processing is performed in Python services/scripts.
--   - Orchestration is handled by n8n.
--   - llama.cpp or equivalent local model endpoint handles transformation.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ----------------------------------------------------------------------------
-- Enum types
-- ----------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pf_scope') THEN
        CREATE TYPE pf_scope AS ENUM ('global', 'user', 'project');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pf_capture_type') THEN
        CREATE TYPE pf_capture_type AS ENUM ('voice', 'text', 'import');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pf_note_status') THEN
        CREATE TYPE pf_note_status AS ENUM (
            'new',
            'imported',
            'processing',
            'processed',
            'error',
            'archived'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pf_revision_kind') THEN
        CREATE TYPE pf_revision_kind AS ENUM (
            'raw',
            'directive_stripped',
            'deterministic_preprocessed',
            'llm_cleaned',
            'llm_structured_source',
            'final_rendered_prompt'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pf_producer_type') THEN
        CREATE TYPE pf_producer_type AS ENUM (
            'human',
            'watcher',
            'python',
            'llm',
            'renderer',
            'system'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pf_rule_type') THEN
        CREATE TYPE pf_rule_type AS ENUM (
            'cleanup',
            'expansion',
            'routing',
            'formatting',
            'safety',
            'terminology'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pf_prompt_generation_status') THEN
        CREATE TYPE pf_prompt_generation_status AS ENUM (
            'created',
            'preprocessed',
            'transforming',
            'structured_validating',
            'rendered',
            'failed'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pf_llm_run_mode') THEN
        CREATE TYPE pf_llm_run_mode AS ENUM ('review', 'inference');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pf_destination') THEN
        CREATE TYPE pf_destination AS ENUM (
            'chat',
            'cli',
            'obsidian_note',
            'queue_only'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pf_target_type') THEN
        CREATE TYPE pf_target_type AS ENUM (
            'none',
            'chat_session',
            'claude_session',
            'codex_session',
            'obsidian_note',
            'generic_queue'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pf_delivery_mode') THEN
        CREATE TYPE pf_delivery_mode AS ENUM (
            'draft',
            'queue',
            'auto_dispatch'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pf_delivery_status') THEN
        CREATE TYPE pf_delivery_status AS ENUM (
            'not_started',
            'queued',
            'dispatching',
            'delivered',
            'acked',
            'failed'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pf_processing_status') THEN
        CREATE TYPE pf_processing_status AS ENUM (
            'running',
            'completed',
            'failed'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pf_priority') THEN
        CREATE TYPE pf_priority AS ENUM (
            'low',
            'normal',
            'high',
            'urgent'
        );
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- Common helper trigger
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION pf_set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- Projects
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    vault_path TEXT,
    git_repo_url TEXT,
    default_prompt_type TEXT NOT NULL DEFAULT 'general',
    default_destination pf_destination NOT NULL DEFAULT 'queue_only',
    active_ruleset_id UUID NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_projects_slug_nonempty CHECK (length(trim(slug)) > 0),
    CONSTRAINT chk_projects_name_nonempty CHECK (length(trim(name)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_projects_active_ruleset_id
    ON projects(active_ruleset_id);

DROP TRIGGER IF EXISTS trg_projects_updated_at ON projects;
CREATE TRIGGER trg_projects_updated_at
BEFORE UPDATE ON projects
FOR EACH ROW
EXECUTE FUNCTION pf_set_updated_at();

-- ----------------------------------------------------------------------------
-- Intake notes
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS intake_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vault_path TEXT NOT NULL,
    note_relative_path TEXT NOT NULL UNIQUE,
    note_title TEXT NOT NULL,
    note_hash TEXT NULL,
    obsidian_created_at TIMESTAMPTZ NULL,
    imported_at TIMESTAMPTZ NULL,
    frontmatter_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    body_markdown TEXT NOT NULL,
    project_id UUID NULL REFERENCES projects(id) ON DELETE SET NULL,
    status pf_note_status NOT NULL DEFAULT 'new',
    watch_eligible BOOLEAN NOT NULL DEFAULT TRUE,
    source_device TEXT NOT NULL DEFAULT 'windows-main',
    last_error TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_intake_notes_title_nonempty CHECK (length(trim(note_title)) > 0),
    CONSTRAINT chk_intake_notes_path_nonempty CHECK (length(trim(note_relative_path)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_intake_notes_project_id ON intake_notes(project_id);
CREATE INDEX IF NOT EXISTS idx_intake_notes_status ON intake_notes(status);
CREATE INDEX IF NOT EXISTS idx_intake_notes_watch_eligible ON intake_notes(watch_eligible);
CREATE INDEX IF NOT EXISTS idx_intake_notes_imported_at ON intake_notes(imported_at);

ALTER TABLE intake_notes
    ADD COLUMN IF NOT EXISTS body_tsv tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(body_markdown, ''))
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_intake_notes_body_tsv
    ON intake_notes USING GIN (body_tsv);

-- ----------------------------------------------------------------------------
-- Utterances
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS utterances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intake_note_id UUID NOT NULL REFERENCES intake_notes(id) ON DELETE CASCADE,
    raw_text TEXT NOT NULL,
    directive_text TEXT NULL,
    project_id UUID NULL REFERENCES projects(id) ON DELETE SET NULL,
    scope pf_scope NOT NULL DEFAULT 'project',
    capture_type pf_capture_type NOT NULL DEFAULT 'voice',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_utterances_raw_text_nonempty CHECK (length(trim(raw_text)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_utterances_intake_note_id ON utterances(intake_note_id);
CREATE INDEX IF NOT EXISTS idx_utterances_project_id ON utterances(project_id);
CREATE INDEX IF NOT EXISTS idx_utterances_scope ON utterances(scope);

-- ----------------------------------------------------------------------------
-- Transcript revisions (append-only)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS transcript_revisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    utterance_id UUID NOT NULL REFERENCES utterances(id) ON DELETE CASCADE,
    revision_kind pf_revision_kind NOT NULL,
    content TEXT NOT NULL,
    producer_type pf_producer_type NOT NULL,
    producer_name TEXT NOT NULL,
    template_profile TEXT NULL,
    quality_score NUMERIC(5,2) NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_transcript_revisions_content_nonempty CHECK (length(trim(content)) > 0),
    CONSTRAINT chk_transcript_revisions_quality_score_range CHECK (
        quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 100)
    )
);

CREATE INDEX IF NOT EXISTS idx_transcript_revisions_utterance_id ON transcript_revisions(utterance_id);
CREATE INDEX IF NOT EXISTS idx_transcript_revisions_kind ON transcript_revisions(revision_kind);
CREATE INDEX IF NOT EXISTS idx_transcript_revisions_created_at ON transcript_revisions(created_at);

ALTER TABLE transcript_revisions
    ADD COLUMN IF NOT EXISTS content_tsv tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(content, ''))
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_transcript_revisions_content_tsv
    ON transcript_revisions USING GIN (content_tsv);

-- ----------------------------------------------------------------------------
-- Rulesets and rules
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS rulesets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    scope pf_scope NOT NULL,
    project_id UUID NULL REFERENCES projects(id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_rulesets_name_nonempty CHECK (length(trim(name)) > 0),
    CONSTRAINT chk_rulesets_version_positive CHECK (version > 0),
    UNIQUE(name, scope, project_id, version)
);

CREATE INDEX IF NOT EXISTS idx_rulesets_scope_project_active
    ON rulesets(scope, project_id, is_active);

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

CREATE TABLE IF NOT EXISTS rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ruleset_id UUID NOT NULL REFERENCES rulesets(id) ON DELETE CASCADE,
    rule_type pf_rule_type NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    match_conditions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    action_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rules_ruleset_id ON rules(ruleset_id);
CREATE INDEX IF NOT EXISTS idx_rules_type_priority ON rules(rule_type, priority);

-- ----------------------------------------------------------------------------
-- Term dictionary
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS term_dictionary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope pf_scope NOT NULL,
    project_id UUID NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_term TEXT NOT NULL,
    canonical_term TEXT NOT NULL,
    confidence NUMERIC(5,2) NOT NULL DEFAULT 1.00,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_term_dictionary_source_nonempty CHECK (length(trim(source_term)) > 0),
    CONSTRAINT chk_term_dictionary_canonical_nonempty CHECK (length(trim(canonical_term)) > 0),
    CONSTRAINT chk_term_dictionary_confidence_range CHECK (confidence >= 0 AND confidence <= 1.00),
    UNIQUE(scope, project_id, source_term)
);

CREATE INDEX IF NOT EXISTS idx_term_dictionary_scope_project
    ON term_dictionary(scope, project_id);

-- ----------------------------------------------------------------------------
-- Prompt templates
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS prompt_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    scope pf_scope NOT NULL,
    project_id UUID NULL REFERENCES projects(id) ON DELETE CASCADE,
    prompt_type TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    body_template TEXT NOT NULL,
    output_contract_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_prompt_templates_name_nonempty CHECK (length(trim(name)) > 0),
    CONSTRAINT chk_prompt_templates_prompt_type_nonempty CHECK (length(trim(prompt_type)) > 0),
    CONSTRAINT chk_prompt_templates_output_contract_nonempty CHECK (length(trim(output_contract_name)) > 0),
    CONSTRAINT chk_prompt_templates_version_positive CHECK (version > 0),
    UNIQUE(name, scope, project_id, version)
);

CREATE INDEX IF NOT EXISTS idx_prompt_templates_scope_project_type
    ON prompt_templates(scope, project_id, prompt_type);

CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_templates_active_global
    ON prompt_templates(scope, prompt_type)
    WHERE is_active AND project_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_templates_active_project
    ON prompt_templates(scope, project_id, prompt_type)
    WHERE is_active AND project_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- Prompt generations
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS prompt_generations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    utterance_id UUID NOT NULL REFERENCES utterances(id) ON DELETE CASCADE,
    project_id UUID NULL REFERENCES projects(id) ON DELETE SET NULL,
    prompt_type TEXT NOT NULL,
    selected_ruleset_id UUID NULL REFERENCES rulesets(id) ON DELETE SET NULL,
    selected_template_id UUID NULL REFERENCES prompt_templates(id) ON DELETE SET NULL,
    structured_output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    final_prompt_markdown TEXT NULL,
    requires_review BOOLEAN NOT NULL DEFAULT FALSE,
    status pf_prompt_generation_status NOT NULL DEFAULT 'created',
    error_text TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_prompt_generations_prompt_type_nonempty CHECK (length(trim(prompt_type)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_prompt_generations_utterance_id
    ON prompt_generations(utterance_id);
CREATE INDEX IF NOT EXISTS idx_prompt_generations_project_id
    ON prompt_generations(project_id);
CREATE INDEX IF NOT EXISTS idx_prompt_generations_status
    ON prompt_generations(status);

-- ----------------------------------------------------------------------------
-- LLM runs
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS llm_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    utterance_id UUID NOT NULL REFERENCES utterances(id) ON DELETE CASCADE,
    prompt_generation_id UUID NOT NULL REFERENCES prompt_generations(id) ON DELETE CASCADE,
    provider_name TEXT NULL,
    model_name TEXT NULL,
    mode pf_llm_run_mode NULL,
    latency_ms INTEGER NULL,
    token_usage_json JSONB NULL,
    fallback_chain_json JSONB NULL,
    summary TEXT NULL,
    findings_json JSONB NULL,
    raw_response_json JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_llm_runs_latency_nonnegative CHECK (latency_ms IS NULL OR latency_ms >= 0)
);

CREATE INDEX IF NOT EXISTS idx_llm_runs_utterance_id
    ON llm_runs(utterance_id);
CREATE INDEX IF NOT EXISTS idx_llm_runs_prompt_generation_id
    ON llm_runs(prompt_generation_id);
CREATE INDEX IF NOT EXISTS idx_llm_runs_mode
    ON llm_runs(mode);

-- ----------------------------------------------------------------------------
-- Delivery targets
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS delivery_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    target_type pf_target_type NOT NULL,
    target_identifier TEXT NOT NULL,
    scope pf_scope NOT NULL DEFAULT 'project',
    project_id UUID NULL REFERENCES projects(id) ON DELETE CASCADE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_auto_dispatch_safe BOOLEAN NOT NULL DEFAULT FALSE,
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_delivery_targets_name_nonempty CHECK (length(trim(name)) > 0),
    CONSTRAINT chk_delivery_targets_identifier_nonempty CHECK (length(trim(target_identifier)) > 0),
    UNIQUE(target_type, target_identifier)
);

CREATE INDEX IF NOT EXISTS idx_delivery_targets_scope_project
    ON delivery_targets(scope, project_id);
CREATE INDEX IF NOT EXISTS idx_delivery_targets_default
    ON delivery_targets(is_default);

-- ----------------------------------------------------------------------------
-- Delivery session registry
-- ----------------------------------------------------------------------------

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

DROP TRIGGER IF EXISTS trg_delivery_session_registry_updated_at ON delivery_session_registry;
CREATE TRIGGER trg_delivery_session_registry_updated_at
BEFORE UPDATE ON delivery_session_registry
FOR EACH ROW
EXECUTE FUNCTION pf_set_updated_at();

-- ----------------------------------------------------------------------------
-- Deliveries
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_generation_id UUID NOT NULL REFERENCES prompt_generations(id) ON DELETE CASCADE,
    delivery_target_id UUID NULL REFERENCES delivery_targets(id) ON DELETE SET NULL,
    destination pf_destination NOT NULL,
    target_type pf_target_type NOT NULL,
    target_identifier TEXT NOT NULL,
    mode pf_delivery_mode NOT NULL DEFAULT 'queue',
    status pf_delivery_status NOT NULL DEFAULT 'not_started',
    priority pf_priority NOT NULL DEFAULT 'normal',
    queued_at TIMESTAMPTZ NULL,
    dispatched_at TIMESTAMPTZ NULL,
    acked_at TIMESTAMPTZ NULL,
    session_identifier TEXT NULL,
    dispatch_request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    dispatch_response_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_text TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_deliveries_target_identifier_nonempty CHECK (length(trim(target_identifier)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_deliveries_prompt_generation_id
    ON deliveries(prompt_generation_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_status
    ON deliveries(status);
CREATE INDEX IF NOT EXISTS idx_deliveries_target
    ON deliveries(target_type, target_identifier);
CREATE INDEX IF NOT EXISTS idx_deliveries_priority_status
    ON deliveries(priority, status);
CREATE INDEX IF NOT EXISTS idx_deliveries_session_identifier
    ON deliveries(session_identifier);

-- ----------------------------------------------------------------------------
-- Processing runs
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS processing_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    utterance_id UUID NOT NULL REFERENCES utterances(id) ON DELETE CASCADE,
    workflow_name TEXT NOT NULL,
    status pf_processing_status NOT NULL DEFAULT 'running',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ NULL,
    error_stage TEXT NULL,
    trace_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT chk_processing_runs_workflow_name_nonempty CHECK (length(trim(workflow_name)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_processing_runs_utterance_id
    ON processing_runs(utterance_id);
CREATE INDEX IF NOT EXISTS idx_processing_runs_status
    ON processing_runs(status);

-- ----------------------------------------------------------------------------
-- Exact error records
-- ----------------------------------------------------------------------------

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

-- ----------------------------------------------------------------------------
-- Console runtime settings and admin audit
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS console_runtime_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope pf_scope NOT NULL,
    project_id UUID NULL REFERENCES projects(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value_json JSONB NOT NULL,
    updated_by_user_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_console_runtime_settings_key_nonempty CHECK (length(trim(key)) > 0),
    CONSTRAINT chk_console_runtime_settings_scope_project CHECK (
        (scope = 'project' AND project_id IS NOT NULL)
        OR (scope <> 'project' AND project_id IS NULL)
    ),
    UNIQUE(scope, project_id, key)
);

DROP TRIGGER IF EXISTS trg_console_runtime_settings_updated_at ON console_runtime_settings;
CREATE TRIGGER trg_console_runtime_settings_updated_at
BEFORE UPDATE ON console_runtime_settings
FOR EACH ROW
EXECUTE FUNCTION pf_set_updated_at();

CREATE INDEX IF NOT EXISTS idx_console_runtime_settings_scope_project
    ON console_runtime_settings(scope, project_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_console_runtime_settings_global_key
    ON console_runtime_settings(scope, key)
    WHERE project_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_console_runtime_settings_project_key
    ON console_runtime_settings(scope, project_id, key)
    WHERE project_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS console_secret_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope pf_scope NOT NULL,
    project_id UUID NULL REFERENCES projects(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    secret_value TEXT NULL,
    secret_ciphertext TEXT NULL,
    secret_key_version INTEGER NULL,
    configured BOOLEAN NOT NULL DEFAULT FALSE,
    last_rotated_at TIMESTAMPTZ NULL,
    updated_by_user_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_console_secret_settings_key_nonempty CHECK (length(trim(key)) > 0),
    CONSTRAINT chk_console_secret_settings_scope_project CHECK (
        (scope = 'project' AND project_id IS NOT NULL)
        OR (scope <> 'project' AND project_id IS NULL)
    ),
    CONSTRAINT chk_console_secret_settings_ciphertext_version CHECK (
        (secret_ciphertext IS NULL AND secret_key_version IS NULL)
        OR (secret_ciphertext IS NOT NULL AND secret_key_version IS NOT NULL AND secret_key_version > 0)
    ),
    UNIQUE(scope, project_id, key)
);

ALTER TABLE console_secret_settings
    ADD COLUMN IF NOT EXISTS secret_ciphertext TEXT NULL;
ALTER TABLE console_secret_settings
    ADD COLUMN IF NOT EXISTS secret_key_version INTEGER NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_console_secret_settings_ciphertext_version'
    ) THEN
        ALTER TABLE console_secret_settings
        ADD CONSTRAINT chk_console_secret_settings_ciphertext_version CHECK (
            (secret_ciphertext IS NULL AND secret_key_version IS NULL)
            OR (secret_ciphertext IS NOT NULL AND secret_key_version IS NOT NULL AND secret_key_version > 0)
        );
    END IF;
END $$;

DROP TRIGGER IF EXISTS trg_console_secret_settings_updated_at ON console_secret_settings;
CREATE TRIGGER trg_console_secret_settings_updated_at
BEFORE UPDATE ON console_secret_settings
FOR EACH ROW
EXECUTE FUNCTION pf_set_updated_at();

CREATE INDEX IF NOT EXISTS idx_console_secret_settings_scope_project
    ON console_secret_settings(scope, project_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_console_secret_settings_global_key
    ON console_secret_settings(scope, key)
    WHERE project_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_console_secret_settings_project_key
    ON console_secret_settings(scope, project_id, key)
    WHERE project_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS console_admin_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    scope pf_scope NULL,
    project_id UUID NULL REFERENCES projects(id) ON DELETE SET NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_console_admin_audit_log_action_nonempty CHECK (length(trim(action)) > 0),
    CONSTRAINT chk_console_admin_audit_log_actor_nonempty CHECK (length(trim(actor)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_console_admin_audit_log_action_created_at
    ON console_admin_audit_log(action, created_at DESC);

-- ----------------------------------------------------------------------------
-- Optional: materialized helper views for querying latest state
-- ----------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_latest_transcript_revision AS
SELECT DISTINCT ON (utterance_id)
    utterance_id,
    id AS transcript_revision_id,
    revision_kind,
    producer_type,
    producer_name,
    content,
    created_at
FROM transcript_revisions
ORDER BY utterance_id, created_at DESC, id DESC;

CREATE OR REPLACE VIEW v_latest_delivery AS
SELECT DISTINCT ON (prompt_generation_id)
    prompt_generation_id,
    id AS delivery_id,
    destination,
    target_type,
    target_identifier,
    mode,
    status,
    priority,
    queued_at,
    dispatched_at,
    acked_at,
    error_text,
    created_at
FROM deliveries
ORDER BY prompt_generation_id, created_at DESC, id DESC;

-- ----------------------------------------------------------------------------
-- Seed comments / usage notes
-- ----------------------------------------------------------------------------
COMMENT ON TABLE intake_notes IS
'Imported Obsidian note artifacts. Human-facing intake records, not the only workflow objects.';

COMMENT ON TABLE utterances IS
'Canonical raw language units extracted from intake notes.';

COMMENT ON TABLE transcript_revisions IS
'Append-only text stages for each utterance, including deterministic and LLM stages.';

COMMENT ON TABLE prompt_generations IS
'Structured output and final rendered prompt records, separate from delivery lifecycle.';

COMMENT ON TABLE deliveries IS
'Queue or dispatch records for final prompt artifacts. Multiple deliveries per prompt are allowed.';

COMMENT ON TABLE delivery_session_registry IS
'Persistent live-session registry for chat and CLI delivery targets, including historical session rows and current-pointer lookup.';

COMMENT ON TABLE workflow_error_records IS
'Append-only exact error records for human intervention and triage. Read-time fingerprint summaries should be computed from these rows, not stored here.';
