-- PromptForge MVP Seed Data Pack
-- Purpose:
--   Load realistic baseline configuration into the PromptForge schema.
--
-- Includes:
--   - projects
--   - rulesets
--   - rules
--   - term dictionary entries
--   - prompt templates
--   - delivery targets
--
-- Notes:
--   - Assumes the schema from promptforge_postgres_schema.sql is already loaded.
--   - Uses stable slugs/names that match prior artifacts.
--   - Safe for a fresh database; not written as an idempotent migration framework.

BEGIN;

-- ---------------------------------------------------------------------------
-- Projects
-- ---------------------------------------------------------------------------

INSERT INTO projects (
    id,
    slug,
    name,
    description,
    vault_path,
    git_repo_url,
    default_prompt_type,
    default_destination,
    metadata_json
) VALUES
(
    '11111111-1111-4111-8111-111111111111',
    'inbox',
    'Inbox',
    'Default unresolved project context used when routing cannot be resolved confidently.',
    '/vault/Inbox',
    NULL,
    'general',
    'queue_only',
    '{"review_queue_target":"manual-review"}'::jsonb
),
(
    '22222222-2222-4222-8222-222222222222',
    'the-tax-machine',
    'the-tax-machine',
    'Tax-return assembly portfolio project.',
    '/vault/Projects/the-tax-machine',
    'git@github.com:example/the-tax-machine.git',
    'coding-cli',
    'cli',
    '{"default_target_identifier":"claude-tax-main","has_diagrams":true}'::jsonb
),
(
    '33333333-3333-4333-8333-333333333333',
    'promptforge',
    'PromptForge',
    'Voice-to-prompt compiler and router project.',
    '/vault/Projects/promptforge',
    'git@github.com:example/promptforge.git',
    'planning',
    'chat',
    '{"default_target_identifier":"claude-promptforge-main"}'::jsonb
);

-- ---------------------------------------------------------------------------
-- Rulesets
-- ---------------------------------------------------------------------------

INSERT INTO rulesets (
    id,
    name,
    scope,
    project_id,
    version,
    is_active,
    description
) VALUES
(
    '44444444-4444-4444-8444-444444444444',
    'global-defaults',
    'global',
    NULL,
    1,
    TRUE,
    'Global cleanup, routing, formatting, and terminology defaults.'
),
(
    '55555555-5555-4555-8555-555555555555',
    'the-tax-machine-defaults',
    'project',
    '22222222-2222-4222-8222-222222222222',
    1,
    TRUE,
    'Project-specific prompt and terminology behavior for the-tax-machine.'
),
(
    '66666666-6666-4666-8666-666666666666',
    'promptforge-defaults',
    'project',
    '33333333-3333-4333-8333-333333333333',
    1,
    TRUE,
    'Project-specific rules for PromptForge planning and implementation.'
);

UPDATE projects
SET active_ruleset_id = CASE slug
    WHEN 'the-tax-machine' THEN '55555555-5555-4555-8555-555555555555'::uuid
    WHEN 'promptforge' THEN '66666666-6666-4666-8666-666666666666'::uuid
    ELSE active_ruleset_id
END
WHERE slug IN ('the-tax-machine', 'promptforge');

-- ---------------------------------------------------------------------------
-- Rules
-- ---------------------------------------------------------------------------

INSERT INTO rules (
    ruleset_id,
    rule_type,
    priority,
    enabled,
    match_conditions_json,
    action_json,
    notes
) VALUES
(
    '44444444-4444-4444-8444-444444444444',
    'cleanup',
    10,
    TRUE,
    '{"stage":"preprocess","applies_to":"all"}'::jsonb,
    '{"remove_leading_fillers":true,"collapse_spaces":true,"normalize_punctuation":true}'::jsonb,
    'Global transcript cleanup defaults.'
),
(
    '44444444-4444-4444-8444-444444444444',
    'routing',
    20,
    TRUE,
    '{"field":"destination","when_missing":true}'::jsonb,
    '{"default_destination":"queue_only","default_target_type":"generic_queue","default_target_identifier":"manual-review"}'::jsonb,
    'Safe fallback when routing cannot be resolved.'
),
(
    '44444444-4444-4444-8444-444444444444',
    'formatting',
    30,
    TRUE,
    '{"stage":"render"}'::jsonb,
    '{"markdown_normalize":true,"trim_trailing_whitespace":true}'::jsonb,
    'Global output formatting defaults.'
),
(
    '55555555-5555-4555-8555-555555555555',
    'routing',
    10,
    TRUE,
    '{"project_slug":"the-tax-machine","prompt_type":"coding-cli"}'::jsonb,
    '{"default_destination":"cli","default_target_identifier":"claude-tax-main","default_mode":"queue"}'::jsonb,
    'Default routing for tax-machine coding tasks.'
),
(
    '55555555-5555-4555-8555-555555555555',
    'terminology',
    15,
    TRUE,
    '{"project_slug":"the-tax-machine"}'::jsonb,
    '{"preserve_terms":["Form 1040","Schedule C","IRS","llama.cpp","n8n","Postgres"]}'::jsonb,
    'Protect high-value technical and domain terms.'
),
(
    '66666666-6666-4666-8666-666666666666',
    'routing',
    10,
    TRUE,
    '{"project_slug":"promptforge"}'::jsonb,
    '{"default_destination":"chat","default_target_identifier":"claude-promptforge-main","default_mode":"queue"}'::jsonb,
    'Default routing for PromptForge planning tasks.'
);

-- ---------------------------------------------------------------------------
-- Term dictionary
-- ---------------------------------------------------------------------------

INSERT INTO term_dictionary (
    scope,
    project_id,
    source_term,
    canonical_term,
    confidence,
    notes
) VALUES
('global', NULL, 'lama cpp', 'llama.cpp', 1.00, 'Common speech-to-text misspelling.'),
('global', NULL, 'lama dot cpp', 'llama.cpp', 1.00, 'Common dictated variant.'),
('global', NULL, 'postgres cue', 'Postgres queue', 0.95, 'Useful when discussing queue architectures.'),
('global', NULL, 'n 8 n', 'n8n', 1.00, 'Spacing variant from speech recognition.'),
('global', NULL, 'obsidian vault', 'Obsidian vault', 1.00, 'Canonical product phrase.'),
('global', NULL, 'coding cli', 'coding-cli', 1.00, 'Prompt type canonicalization.'),
('project', '22222222-2222-4222-8222-222222222222', 'thtaxmachine', 'the-tax-machine', 0.98, 'Observed likely dictated/mistyped project slug.'),
('project', '22222222-2222-4222-8222-222222222222', 'tax machine', 'the-tax-machine', 0.95, 'Friendly spoken project reference.'),
('project', '22222222-2222-4222-8222-222222222222', 'schedule c', 'Schedule C', 1.00, 'Tax domain canonical form.'),
('project', '22222222-2222-4222-8222-222222222222', 'form ten forty', 'Form 1040', 0.90, 'Speech-normalized tax form name.'),
('project', '33333333-3333-4333-8333-333333333333', 'prompt forge', 'PromptForge', 1.00, 'Product name spacing variant.'),
('project', '33333333-3333-4333-8333-333333333333', 'voice inbox', 'Inbox/Voice', 0.90, 'Canonical intake folder reference.');

-- ---------------------------------------------------------------------------
-- Prompt templates
-- ---------------------------------------------------------------------------

INSERT INTO prompt_templates (
    id,
    name,
    scope,
    project_id,
    prompt_type,
    version,
    body_template,
    output_contract_name,
    is_active
) VALUES
(
    '77777777-7777-4777-8777-777777777777',
    'coding-cli-default',
    'global',
    NULL,
    'coding-cli',
    1,
    'Project: {{ project_slug }}\nTarget: {{ target_identifier or "unassigned" }}\nMode: {{ mode }}\n\nTask:\n{{ final_prompt_markdown }}',
    'agent_task_v1',
    TRUE
),
(
    '88888888-8888-4888-8888-888888888888',
    'chat-prompt-default',
    'global',
    NULL,
    'general',
    1,
    'Project context: {{ project_slug }}\nPrompt type: {{ prompt_type }}\n\n{{ final_prompt_markdown }}',
    'chat_prompt_v1',
    TRUE
),
(
    '99999999-9999-4999-8999-999999999999',
    'delegation-default',
    'global',
    NULL,
    'delegation',
    1,
    'Delegate the following task for project {{ project_slug }}.\n\nDestination target: {{ target_identifier or "unassigned" }}\n\nTask:\n{{ final_prompt_markdown }}',
    'agent_task_v1',
    TRUE
),
(
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'review-item-default',
    'global',
    NULL,
    'review',
    1,
    'Review required.\n\nReason:\n{{ review_reason }}\n\nSuggested prompt:\n{{ suggested_prompt_markdown or "None generated." }}\n\nNotes:\n{% if notes %}{% for note in notes %}- {{ note }}\n{% endfor %}{% else %}- No additional notes.\n{% endif %}',
    'review_item_v1',
    TRUE
),
(
    'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    'obsidian-note-summary',
    'global',
    NULL,
    'planning',
    1,
    '## PromptForge Summary\n\n- Project: {{ project_slug or "unresolved" }}\n- Destination: {{ destination }}\n- Target: {{ target_identifier or "unassigned" }}\n- Requires review: {{ requires_review }}\n\n## Final Prompt\n\n{{ final_prompt_markdown }}',
    'obsidian_note_output_v1',
    TRUE
),
(
    'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
    'tax-machine-coding-cli',
    'project',
    '22222222-2222-4222-8222-222222222222',
    'coding-cli',
    1,
    'Project: {{ project_slug }}\nRepository target: {{ target_identifier or "claude-tax-main" }}\nMode: {{ mode }}\n\nTask:\n{{ final_prompt_markdown }}\n\nDeliverables:\n- affected files\n- state-machine changes\n- validation impacts\n- recommended tests',
    'agent_task_v1',
    TRUE
);

-- ---------------------------------------------------------------------------
-- Delivery targets
-- ---------------------------------------------------------------------------

INSERT INTO delivery_targets (
    id,
    name,
    target_type,
    target_identifier,
    scope,
    project_id,
    is_default,
    is_auto_dispatch_safe,
    config_json
) VALUES
(
    'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
    'Manual review queue',
    'generic_queue',
    'manual-review',
    'global',
    NULL,
    TRUE,
    FALSE,
    '{"adapter":"generic_queue","queue_name":"manual-review"}'::jsonb
),
(
    'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
    'Claude tax main',
    'claude_session',
    'claude-tax-main',
    'project',
    '22222222-2222-4222-8222-222222222222',
    TRUE,
    FALSE,
    '{"adapter":"claude_cli","session_hint":"tax-main","working_dir":"/srv/repos/the-tax-machine"}'::jsonb
),
(
    'ffffffff-ffff-4fff-8fff-ffffffffffff',
    'Claude PromptForge main',
    'claude_session',
    'claude-promptforge-main',
    'project',
    '33333333-3333-4333-8333-333333333333',
    TRUE,
    FALSE,
    '{"adapter":"claude_cli","session_hint":"promptforge-main","working_dir":"/srv/repos/promptforge"}'::jsonb
),
(
    '12121212-1212-4212-8212-121212121212',
    'PromptForge chat queue',
    'chat_session',
    'chat-promptforge-default',
    'project',
    '33333333-3333-4333-8333-333333333333',
    FALSE,
    FALSE,
    '{"adapter":"chat_queue","queue_name":"promptforge-chat"}'::jsonb
),
(
    '34343434-3434-4434-8434-343434343434',
    'Obsidian write-back target',
    'obsidian_note',
    'obsidian-writeback',
    'global',
    NULL,
    FALSE,
    FALSE,
    '{"adapter":"obsidian_note","target_folder":"Processed/Voice"}'::jsonb
);

COMMIT;
