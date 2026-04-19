from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs/planning/promptforge_postgres_schema.sql"
SEED_PATH = ROOT / "docs/planning/promptforge_seed_data.sql"
TEST_SCHEMA = "promptforge_test"


def _with_search_path(database_url: str, schema_name: str) -> str:
    parts = urlsplit(database_url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params["options"] = f"-csearch_path={schema_name},public"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment))


def _seed_console_database(database_url: str) -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    seed_sql = SEED_PATH.read_text(encoding="utf-8")
    custom_sql = """
    INSERT INTO intake_notes (
        id,
        vault_path,
        note_relative_path,
        note_title,
        note_hash,
        obsidian_created_at,
        imported_at,
        frontmatter_json,
        body_markdown,
        project_id,
        status,
        watch_eligible,
        source_device,
        last_error,
        created_at
    ) VALUES
    (
        'aaaaaaaa-0000-4000-8000-000000000001',
        '/vault/Inbox/Voice/success-note.md',
        'Inbox/Voice/success-note.md',
        'Success note',
        'success-hash',
        now() - interval '3 hours',
        now() - interval '2 hours 50 minutes',
        '{"project":"inbox"}'::jsonb,
        'Successful note body',
        '22222222-2222-4222-8222-222222222222',
        'processed',
        TRUE,
        'windows-main',
        NULL,
        now() - interval '3 hours'
    ),
    (
        'aaaaaaaa-0000-4000-8000-000000000002',
        '/vault/Inbox/Voice/failure-note.md',
        'Inbox/Voice/failure-note.md',
        'Failure note',
        'failure-hash',
        now() - interval '2 hours',
        now() - interval '1 hours 55 minutes',
        '{"project":"promptforge"}'::jsonb,
        'Failure note body',
        '33333333-3333-4333-8333-333333333333',
        'error',
        TRUE,
        'windows-main',
        'render pipeline failed',
        now() - interval '2 hours'
    ),
    (
        'aaaaaaaa-0000-4000-8000-000000000003',
        '/vault/Inbox/Voice/queue-note.md',
        'Inbox/Voice/queue-note.md',
        'Queue note',
        'queue-hash',
        now() - interval '90 minutes',
        now() - interval '85 minutes',
        '{"project":"inbox"}'::jsonb,
        'Queue note body',
        '22222222-2222-4222-8222-222222222222',
        'imported',
        TRUE,
        'windows-main',
        NULL,
        now() - interval '90 minutes'
    );

    INSERT INTO utterances (
        id,
        intake_note_id,
        raw_text,
        directive_text,
        project_id,
        scope,
        capture_type,
        created_at
    ) VALUES
    (
        'bbbbbbbb-0000-4000-8000-000000000001',
        'aaaaaaaa-0000-4000-8000-000000000001',
        'figure out the retry transitions',
        NULL,
        '22222222-2222-4222-8222-222222222222',
        'project',
        'voice',
        now() - interval '2 hours 45 minutes'
    ),
    (
        'bbbbbbbb-0000-4000-8000-000000000002',
        'aaaaaaaa-0000-4000-8000-000000000002',
        'compare the retry states to the review rules',
        NULL,
        '33333333-3333-4333-8333-333333333333',
        'project',
        'voice',
        now() - interval '1 hours 50 minutes'
    );

    INSERT INTO transcript_revisions (
        id,
        utterance_id,
        revision_kind,
        content,
        producer_type,
        producer_name,
        metadata_json,
        created_at
    ) VALUES
    (
        'cccccccc-0000-4000-8000-000000000001',
        'bbbbbbbb-0000-4000-8000-000000000001',
        'raw',
        'figure out the retry transitions',
        'watcher',
        'watcher',
        '{}'::jsonb,
        now() - interval '2 hours 44 minutes'
    ),
    (
        'cccccccc-0000-4000-8000-000000000002',
        'bbbbbbbb-0000-4000-8000-000000000001',
        'final_rendered_prompt',
        'Investigate the retry transitions and produce a patch plan.',
        'renderer',
        'renderer',
        '{"source":"render"}'::jsonb,
        now() - interval '2 hours 43 minutes'
    );

    INSERT INTO prompt_generations (
        id,
        utterance_id,
        project_id,
        prompt_type,
        selected_ruleset_id,
        selected_template_id,
        structured_output_json,
        final_prompt_markdown,
        requires_review,
        status,
        error_text,
        created_at
    ) VALUES
    (
        'dddddddd-0000-4000-8000-000000000001',
        'bbbbbbbb-0000-4000-8000-000000000001',
        '22222222-2222-4222-8222-222222222222',
        'coding-cli',
        '55555555-5555-4555-8555-555555555555',
        'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
        '{"destination":"cli"}'::jsonb,
        'Investigate the retry transitions and produce a patch plan.',
        FALSE,
        'rendered',
        NULL,
        now() - interval '2 hours 42 minutes'
    ),
    (
        'dddddddd-0000-4000-8000-000000000002',
        'bbbbbbbb-0000-4000-8000-000000000002',
        '33333333-3333-4333-8333-333333333333',
        'planning',
        '66666666-6666-4666-8666-666666666666',
        'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        '{"destination":"chat"}'::jsonb,
        'Prepare a change list for the review rules.',
        TRUE,
        'failed',
        'render pipeline failed',
        now() - interval '1 hours 48 minutes'
    ),
    (
        'dddddddd-0000-4000-8000-000000000003',
        'bbbbbbbb-0000-4000-8000-000000000001',
        '22222222-2222-4222-8222-222222222222',
        'coding-cli',
        '55555555-5555-4555-8555-555555555555',
        'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
        '{}'::jsonb,
        'Queue-only follow-up prompt.',
        FALSE,
        'created',
        NULL,
        now() - interval '85 minutes'
    );

    INSERT INTO deliveries (
        id,
        prompt_generation_id,
        delivery_target_id,
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
    ) VALUES
    (
        'eeeeeeee-0000-4000-8000-000000000001',
        'dddddddd-0000-4000-8000-000000000001',
        'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
        'cli',
        'claude_session',
        'claude-tax-main',
        'queue',
        'delivered',
        'high',
        now() - interval '2 hours 41 minutes',
        now() - interval '2 hours 39 minutes',
        now() - interval '2 hours 38 minutes',
        NULL,
        now() - interval '2 hours 41 minutes'
    ),
    (
        'eeeeeeee-0000-4000-8000-000000000002',
        'dddddddd-0000-4000-8000-000000000002',
        'ffffffff-ffff-4fff-8fff-ffffffffffff',
        'chat',
        'claude_session',
        'claude-promptforge-main',
        'queue',
        'failed',
        'urgent',
        now() - interval '1 hours 47 minutes',
        now() - interval '1 hours 46 minutes',
        NULL,
        'render pipeline failed',
        now() - interval '1 hours 47 minutes'
    ),
    (
        'eeeeeeee-0000-4000-8000-000000000003',
        'dddddddd-0000-4000-8000-000000000003',
        'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
        'queue_only',
        'generic_queue',
        'manual-review',
        'queue',
        'queued',
        'normal',
        now() - interval '82 minutes',
        NULL,
        NULL,
        NULL,
        now() - interval '82 minutes'
    ),
    (
        'eeeeeeee-0000-4000-8000-000000000004',
        'dddddddd-0000-4000-8000-000000000003',
        'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
        'queue_only',
        'generic_queue',
        'manual-review',
        'queue',
        'dispatching',
        'normal',
        now() - interval '81 minutes',
        now() - interval '80 minutes',
        NULL,
        NULL,
        now() - interval '81 minutes'
    );

    INSERT INTO processing_runs (
        id,
        utterance_id,
        workflow_name,
        status,
        started_at,
        ended_at,
        error_stage,
        trace_json
    ) VALUES
    (
        'ffffffff-0000-4000-8000-000000000001',
        'bbbbbbbb-0000-4000-8000-000000000001',
        'console-pipeline',
        'completed',
        now() - interval '2 hours 37 minutes',
        now() - interval '2 hours 36 minutes',
        NULL,
        '{"status":"ok"}'::jsonb
    ),
    (
        'ffffffff-0000-4000-8000-000000000002',
        'bbbbbbbb-0000-4000-8000-000000000002',
        'console-pipeline',
        'failed',
        now() - interval '1 hours 44 minutes',
        now() - interval '1 hours 43 minutes',
        'render',
        '{"error_text":"render failed"}'::jsonb
    ),
    (
        'ffffffff-0000-4000-8000-000000000003',
        'bbbbbbbb-0000-4000-8000-000000000002',
        'console-pipeline',
        'failed',
        now() - interval '1 hours 42 minutes',
        now() - interval '1 hours 41 minutes',
        'render',
        '{"error_text":"render failed"}'::jsonb
    );
    """

    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")
        conn.execute(f"CREATE SCHEMA {TEST_SCHEMA}")
        conn.execute(f"SET search_path TO {TEST_SCHEMA}, public")
        conn.execute(schema_sql)
        conn.execute(seed_sql)
        conn.execute(custom_sql)


@pytest.fixture(scope="session")
def seeded_console_database_url() -> Iterator[str]:
    database_url = os.getenv("PROMPTFORGE_DATABASE_URL")
    if not database_url:
        pytest.skip(
            "PROMPTFORGE_DATABASE_URL is not set; console read endpoint integration tests need a live Postgres database"
        )

    seeded_url = _with_search_path(database_url, TEST_SCHEMA)
    original = os.environ.get("PROMPTFORGE_DATABASE_URL")
    os.environ["PROMPTFORGE_DATABASE_URL"] = seeded_url
    try:
        _seed_console_database(database_url)
        yield seeded_url
    finally:
        try:
            with psycopg.connect(database_url, autocommit=True) as conn:
                conn.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")
        finally:
            if original is None:
                os.environ.pop("PROMPTFORGE_DATABASE_URL", None)
            else:
                os.environ["PROMPTFORGE_DATABASE_URL"] = original
