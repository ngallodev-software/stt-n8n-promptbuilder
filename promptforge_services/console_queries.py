from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row


def _fetch_all(database_url: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def _count_value(rows: list[dict[str, Any]], key: str = "total") -> int:
    return int(rows[0][key]) if rows else 0


def _where_sql(clauses: list[str]) -> str:
    return " WHERE " + " AND ".join(clauses) if clauses else ""


def fetch_projects(database_url: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    total_rows = _fetch_all(database_url, "SELECT COUNT(*)::int AS total FROM projects")
    rows = _fetch_all(
        database_url,
        """
        SELECT id, name, slug, description, created_at, updated_at
        FROM projects
        ORDER BY updated_at DESC, created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (limit, offset),
    )
    return rows, _count_value(total_rows)


def fetch_intake_notes(
    database_url: str,
    *,
    project_id: str | None = None,
    status: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if project_id is not None and project_id != "":
        clauses.append("project_id = %s")
        params.append(project_id)
    if status is not None and status != "":
        clauses.append("status = %s::pf_note_status")
        params.append(status)
    where_sql = _where_sql(clauses)
    total_rows = _fetch_all(
        database_url,
        f"SELECT COUNT(*)::int AS total FROM intake_notes{where_sql}",
        tuple(params),
    )
    rows = _fetch_all(
        database_url,
        f"""
        SELECT
            id,
            project_id,
            note_relative_path,
            status::text AS status,
            watch_eligible,
            source_device,
            COALESCE(body_markdown, '') AS body_text,
            COALESCE(frontmatter_json, '{{}}'::jsonb) AS frontmatter_original,
            COALESCE(frontmatter_json, '{{}}'::jsonb) AS frontmatter_current,
            COALESCE(route_json, '{{}}'::jsonb) AS route_json,
            CASE
                WHEN last_error IS NULL AND COALESCE(route_json, '{{}}'::jsonb) = '{{}}'::jsonb THEN '{{}}'::jsonb
                ELSE jsonb_strip_nulls(
                    jsonb_build_object(
                        'last_error', last_error,
                        'route', COALESCE(route_json, '{{}}'::jsonb)
                    )
                )
            END AS metadata_json,
            created_at,
            COALESCE(imported_at, created_at) AS updated_at
        FROM intake_notes
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    )
    return rows, _count_value(total_rows)


def fetch_intake_note(database_url: str, note_id: str) -> dict[str, Any] | None:
    rows = _fetch_all(
        database_url,
        """
        SELECT
            id,
            project_id,
            note_relative_path,
            status::text AS status,
            watch_eligible,
            source_device,
            COALESCE(body_markdown, '') AS body_text,
            COALESCE(frontmatter_json, '{}'::jsonb) AS frontmatter_original,
            COALESCE(frontmatter_json, '{}'::jsonb) AS frontmatter_current,
            COALESCE(route_json, '{}'::jsonb) AS route_json,
            CASE
                WHEN last_error IS NULL AND COALESCE(route_json, '{}'::jsonb) = '{}'::jsonb THEN '{}'::jsonb
                ELSE jsonb_strip_nulls(
                    jsonb_build_object(
                        'last_error', last_error,
                        'route', COALESCE(route_json, '{}'::jsonb)
                    )
                )
            END AS metadata_json,
            created_at,
            COALESCE(imported_at, created_at) AS updated_at
        FROM intake_notes
        WHERE id = %s
        LIMIT 1
        """,
        (note_id,),
    )
    return rows[0] if rows else None


def fetch_utterances_for_note(database_url: str, note_id: str) -> list[dict[str, Any]]:
    return _fetch_all(
        database_url,
        """
        SELECT
            id,
            intake_note_id,
            raw_text,
            directive_text,
            project_id,
            scope::text AS scope,
            capture_type::text AS capture_type,
            created_at
        FROM utterances
        WHERE intake_note_id = %s
        ORDER BY created_at ASC, id ASC
        """,
        (note_id,),
    )


def fetch_utterance_summaries(database_url: str, limit: int) -> list[dict[str, Any]]:
    return _fetch_all(
        database_url,
        """
        SELECT id, intake_note_id, created_at
        FROM utterances
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )


def fetch_transcript_revisions(
    database_url: str,
    *,
    intake_note_id: str | None = None,
    limit: int,
    ascending: bool = False,
) -> list[dict[str, Any]]:
    order_sql = "ASC" if ascending else "DESC"
    params: list[Any] = []
    where_sql = ""
    if intake_note_id is not None and intake_note_id != "":
        where_sql = "WHERE u.intake_note_id = %s"
        params.append(intake_note_id)
    return _fetch_all(
        database_url,
        f"""
        SELECT
            tr.id,
            tr.utterance_id,
            tr.revision_kind::text AS revision_kind,
            tr.producer_type::text AS producer_type,
            tr.producer_name,
            tr.content AS content_text,
            COALESCE(tr.metadata_json, '{{}}'::jsonb) AS metadata_json,
            tr.created_at
        FROM transcript_revisions tr
        JOIN utterances u ON u.id = tr.utterance_id
        {where_sql}
        ORDER BY tr.created_at {order_sql}, tr.id {order_sql}
        LIMIT %s
        """,
        (*params, limit),
    )


def fetch_prompt_generations(
    database_url: str,
    *,
    intake_note_id: str | None = None,
    status: str | None = None,
    limit: int,
    offset: int = 0,
    ascending: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if intake_note_id is not None and intake_note_id != "":
        clauses.append("u.intake_note_id = %s")
        params.append(intake_note_id)
    if status is not None and status != "":
        clauses.append("pg.status = %s::pf_prompt_generation_status")
        params.append(status)
    where_sql = _where_sql(clauses)
    order_sql = "ASC" if ascending else "DESC"
    total_rows = _fetch_all(
        database_url,
        f"""
        SELECT COUNT(*)::int AS total
        FROM prompt_generations pg
        JOIN utterances u ON u.id = pg.utterance_id
        {where_sql}
        """,
        tuple(params),
    )
    rows = _fetch_all(
        database_url,
        f"""
        SELECT
            pg.id,
            u.intake_note_id,
            pg.status::text AS status,
            pg.requires_review,
            pg.prompt_type,
            pg.selected_ruleset_id AS ruleset_id,
            pg.selected_template_id AS template_id,
            COALESCE(ld.destination::text, 'queue_only') AS destination,
            COALESCE(ld.mode::text, 'queue') AS mode,
            COALESCE(ld.priority::text, 'normal') AS priority,
            COALESCE(pg.structured_output_json, '{{}}'::jsonb) AS structured_output_json,
            COALESCE(pg.final_prompt_markdown, '') AS final_prompt_markdown,
            '[]'::jsonb AS validation_warnings,
            pg.created_at,
            COALESCE(ld.created_at, pg.created_at) AS updated_at
        FROM prompt_generations pg
        JOIN utterances u ON u.id = pg.utterance_id
        LEFT JOIN LATERAL (
            SELECT d.*
            FROM deliveries d
            WHERE d.prompt_generation_id = pg.id
            ORDER BY d.created_at DESC, d.id DESC
            LIMIT 1
        ) ld ON TRUE
        {where_sql}
        ORDER BY pg.created_at {order_sql}, pg.id {order_sql}
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    )
    return rows, _count_value(total_rows)


def fetch_prompt_generation_by_id(database_url: str, prompt_generation_id: str) -> dict[str, Any] | None:
    rows = _fetch_all(
        database_url,
        """
        SELECT
            pg.id,
            u.intake_note_id,
            pg.status::text AS status,
            pg.requires_review,
            pg.prompt_type,
            pg.selected_ruleset_id AS ruleset_id,
            pg.selected_template_id AS template_id,
            COALESCE(ld.destination::text, 'queue_only') AS destination,
            COALESCE(ld.mode::text, 'queue') AS mode,
            COALESCE(ld.priority::text, 'normal') AS priority,
            COALESCE(pg.structured_output_json, '{}'::jsonb) AS structured_output_json,
            COALESCE(pg.final_prompt_markdown, '') AS final_prompt_markdown,
            '[]'::jsonb AS validation_warnings,
            pg.created_at,
            COALESCE(ld.created_at, pg.created_at) AS updated_at,
            pg.project_id
        FROM prompt_generations pg
        JOIN utterances u ON u.id = pg.utterance_id
        LEFT JOIN LATERAL (
            SELECT d.*
            FROM deliveries d
            WHERE d.prompt_generation_id = pg.id
            ORDER BY d.created_at DESC, d.id DESC
            LIMIT 1
        ) ld ON TRUE
        WHERE pg.id = %s
        LIMIT 1
        """,
        (prompt_generation_id,),
    )
    return rows[0] if rows else None


def fetch_deliveries(
    database_url: str,
    *,
    prompt_generation_id: str | None = None,
    status: str | None = None,
    limit: int,
    offset: int = 0,
    ascending: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if prompt_generation_id is not None and prompt_generation_id != "":
        clauses.append("d.prompt_generation_id = %s")
        params.append(prompt_generation_id)
    if status is not None and status != "":
        clauses.append("d.status = %s::pf_delivery_status")
        params.append(status)
    where_sql = _where_sql(clauses)
    order_sql = "ASC" if ascending else "DESC"
    total_rows = _fetch_all(database_url, f"SELECT COUNT(*)::int AS total FROM deliveries d{where_sql}", tuple(params))
    rows = _fetch_all(
        database_url,
        f"""
        SELECT
            d.id,
            d.prompt_generation_id,
            d.delivery_target_id AS target_id,
            d.session_identifier,
            d.status::text AS status,
            d.destination::text AS destination,
            d.mode::text AS mode,
            d.priority::text AS priority,
            GREATEST(
                0,
                (
                    SELECT COUNT(*)::int - 1
                    FROM deliveries d2
                    WHERE d2.prompt_generation_id = d.prompt_generation_id
                      AND d2.created_at <= d.created_at
                      AND d2.status = 'failed'
                )
                ) AS retry_count,
            COALESCE(d.dispatch_request_json, '{{}}'::jsonb) AS dispatch_request_json,
            COALESCE(d.dispatch_response_json, '{{}}'::jsonb) AS dispatch_response_json,
            d.error_text AS failure_text,
            NULL::text AS ack_text,
            d.created_at,
            COALESCE(d.acked_at, d.dispatched_at, d.queued_at, d.created_at) AS updated_at
        FROM deliveries d
        {where_sql}
        ORDER BY d.created_at {order_sql}, d.id {order_sql}
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    )
    return rows, _count_value(total_rows)


def fetch_processing_runs(
    database_url: str,
    *,
    intake_note_id: str | None = None,
    status: str | None = None,
    limit: int,
    offset: int = 0,
    ascending: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if intake_note_id is not None and intake_note_id != "":
        clauses.append("u.intake_note_id = %s")
        params.append(intake_note_id)
    if status is not None and status != "":
        clauses.append("pr.status = %s")
        params.append(status)
    where_sql = _where_sql(clauses)
    order_sql = "ASC" if ascending else "DESC"
    total_rows = _fetch_all(
        database_url,
        f"""
        SELECT COUNT(*)::int AS total
        FROM processing_runs pr
        JOIN utterances u ON u.id = pr.utterance_id
        {where_sql}
        """,
        tuple(params),
    )
    rows = _fetch_all(
        database_url,
        f"""
        SELECT
            pr.id,
            u.intake_note_id,
            pr.status::text AS status,
            COALESCE(pr.error_stage, pr.workflow_name) AS stage_name,
            COALESCE(pr.trace_json->>'error_text', pr.trace_json->'failure'->>'code') AS error_text,
            COALESCE(pr.trace_json, '{{}}'::jsonb) AS trace_json,
            pr.started_at AS created_at,
            COALESCE(pr.ended_at, pr.started_at) AS updated_at
        FROM processing_runs pr
        JOIN utterances u ON u.id = pr.utterance_id
        {where_sql}
        ORDER BY pr.started_at {order_sql}, pr.id {order_sql}
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    )
    return rows, _count_value(total_rows)


def fetch_rulesets(
    database_url: str,
    *,
    scope: str | None = None,
    project_id: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if scope is not None and scope != "":
        clauses.append("scope = %s::pf_scope")
        params.append(scope)
    if project_id is not None and project_id != "":
        clauses.append("project_id = %s")
        params.append(project_id)
    where_sql = _where_sql(clauses)
    total_rows = _fetch_all(database_url, f"SELECT COUNT(*)::int AS total FROM rulesets{where_sql}", tuple(params))
    rows = _fetch_all(
        database_url,
        f"""
        SELECT
            id,
            name,
            scope::text AS scope,
            project_id,
            is_active AS active,
            description,
            created_at AS updated_at
        FROM rulesets
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    )
    return rows, _count_value(total_rows)


def fetch_rules(
    database_url: str,
    *,
    ruleset_id: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if ruleset_id is not None and ruleset_id != "":
        clauses.append("ruleset_id = %s")
        params.append(ruleset_id)
    where_sql = _where_sql(clauses)
    total_rows = _fetch_all(database_url, f"SELECT COUNT(*)::int AS total FROM rules{where_sql}", tuple(params))
    rows = _fetch_all(
        database_url,
        f"""
        SELECT
            id,
            ruleset_id,
            COALESCE(notes, rule_type::text || ' rule') AS name,
            rule_type::text AS rule_type,
            priority,
            enabled,
            COALESCE(match_conditions_json::text, '') AS pattern,
            COALESCE(action_json::text, '') AS replacement,
            notes AS description,
            created_at AS updated_at
        FROM rules
        {where_sql}
        ORDER BY priority ASC, created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    )
    return rows, _count_value(total_rows)


def fetch_dictionary_terms(
    database_url: str,
    *,
    scope: str | None = None,
    project_id: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if scope is not None and scope != "":
        clauses.append("scope = %s::pf_scope")
        params.append(scope)
    if project_id is not None and project_id != "":
        clauses.append("project_id = %s")
        params.append(project_id)
    where_sql = _where_sql(clauses)
    total_rows = _fetch_all(database_url, f"SELECT COUNT(*)::int AS total FROM term_dictionary{where_sql}", tuple(params))
    rows = _fetch_all(
        database_url,
        f"""
        SELECT
            id,
            scope::text AS scope,
            project_id,
            source_term,
            canonical_term AS normalized_term,
            notes AS description,
            created_at,
            created_at AS updated_at
        FROM term_dictionary
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    )
    return rows, _count_value(total_rows)


def fetch_prompt_templates(
    database_url: str,
    *,
    scope: str | None = None,
    project_id: str | None = None,
    prompt_type: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if scope is not None and scope != "":
        clauses.append("scope = %s::pf_scope")
        params.append(scope)
    if project_id is not None and project_id != "":
        clauses.append("project_id = %s")
        params.append(project_id)
    if prompt_type is not None and prompt_type != "":
        clauses.append("prompt_type = %s")
        params.append(prompt_type)
    where_sql = _where_sql(clauses)
    total_rows = _fetch_all(database_url, f"SELECT COUNT(*)::int AS total FROM prompt_templates{where_sql}", tuple(params))
    rows = _fetch_all(
        database_url,
        f"""
        SELECT
            id,
            name,
            prompt_type,
            scope::text AS scope,
            project_id,
            version,
            is_active,
            output_contract_name AS template_family_key,
            body_template AS body,
            created_at AS updated_at
        FROM prompt_templates
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    )
    return rows, _count_value(total_rows)


def fetch_delivery_targets(
    database_url: str,
    *,
    type: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if type is not None and type != "":
        clauses.append("target_type = %s::pf_target_type")
        params.append(type)
    where_sql = _where_sql(clauses)
    total_rows = _fetch_all(database_url, f"SELECT COUNT(*)::int AS total FROM delivery_targets{where_sql}", tuple(params))
    rows = _fetch_all(
        database_url,
        f"""
        SELECT
            id,
            name,
            target_type::text AS target_type,
            target_identifier,
            COALESCE(config_json->>'destination', 'queue_only') AS destination,
            scope::text AS scope,
            project_id,
            TRUE AS enabled,
            FALSE AS is_sensitive,
            NOT is_auto_dispatch_safe AS requires_confirmation,
            'prod'::text AS environment,
            CASE
                WHEN target_type IN ('claude_session', 'codex_session', 'chat_session') THEN 'unknown'
                WHEN target_type = 'obsidian_note' THEN CASE
                    WHEN COALESCE(config_json->>'target_folder', '') <> '' THEN 'ok'
                    ELSE 'degraded'
                END
                WHEN target_type = 'generic_queue' THEN CASE
                    WHEN COALESCE(config_json->>'queue_name', '') <> '' THEN 'ok'
                    ELSE 'degraded'
                END
                ELSE 'error'
            END AS validation_status,
            CASE
                WHEN target_type IN ('claude_session', 'codex_session', 'chat_session') THEN 'live_session_registry_unavailable'
                WHEN target_type = 'obsidian_note' AND COALESCE(config_json->>'target_folder', '') = '' THEN 'target_folder_missing'
                WHEN target_type = 'generic_queue' AND COALESCE(config_json->>'queue_name', '') = '' THEN 'queue_name_missing'
                ELSE NULL
            END AS validation_detail,
            COALESCE(config_json, '{{}}'::jsonb) AS config_json,
            created_at AS updated_at
        FROM delivery_targets
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    )
    return rows, _count_value(total_rows)


def fetch_delivery_target_by_id(database_url: str, target_id: str) -> dict[str, Any] | None:
    rows = _fetch_all(
        database_url,
        """
        SELECT
            id,
            name,
            target_type::text AS target_type,
            target_identifier,
            COALESCE(config_json->>'destination', 'queue_only') AS destination,
            scope::text AS scope,
            project_id,
            TRUE AS enabled,
            FALSE AS is_sensitive,
            NOT is_auto_dispatch_safe AS requires_confirmation,
            'prod'::text AS environment,
            CASE
                WHEN target_type IN ('claude_session', 'codex_session', 'chat_session') THEN 'unknown'
                WHEN target_type = 'obsidian_note' THEN CASE
                    WHEN COALESCE(config_json->>'target_folder', '') <> '' THEN 'ok'
                    ELSE 'degraded'
                END
                WHEN target_type = 'generic_queue' THEN CASE
                    WHEN COALESCE(config_json->>'queue_name', '') <> '' THEN 'ok'
                    ELSE 'degraded'
                END
                ELSE 'error'
            END AS validation_status,
            CASE
                WHEN target_type IN ('claude_session', 'codex_session', 'chat_session') THEN 'live_session_registry_unavailable'
                WHEN target_type = 'obsidian_note' AND COALESCE(config_json->>'target_folder', '') = '' THEN 'target_folder_missing'
                WHEN target_type = 'generic_queue' AND COALESCE(config_json->>'queue_name', '') = '' THEN 'queue_name_missing'
                ELSE NULL
            END AS validation_detail,
            COALESCE(config_json, '{}'::jsonb) AS config_json,
            created_at AS updated_at
        FROM delivery_targets
        WHERE id = %s
        LIMIT 1
        """,
        (target_id,),
    )
    return rows[0] if rows else None


def fetch_log_sources(
    database_url: str,
    *,
    intake_note_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if intake_note_id:
        intake_notes = _fetch_all(
            database_url,
            """
            SELECT
                id,
                status::text AS status,
                note_relative_path,
                COALESCE(route_json, '{}'::jsonb) AS route_json,
                created_at,
                COALESCE(imported_at, created_at) AS updated_at
            FROM intake_notes
            WHERE id = %s
            LIMIT 1
            """,
            (intake_note_id,),
        )
        if not intake_notes:
            return [], [], []
        deliveries = _fetch_all(
            database_url,
            """
            SELECT
                d.id,
                d.prompt_generation_id,
                d.delivery_target_id AS target_id,
                d.status::text AS status,
                d.destination::text AS destination,
                d.mode::text AS mode,
                d.priority::text AS priority,
                GREATEST(
                    0,
                    (
                        SELECT COUNT(*)::int - 1
                        FROM deliveries d2
                        WHERE d2.prompt_generation_id = d.prompt_generation_id
                          AND d2.created_at <= d.created_at
                          AND d2.status = 'failed'
                    )
                ) AS retry_count,
                d.error_text AS failure_text,
                NULL::text AS ack_text,
                d.created_at,
                COALESCE(d.acked_at, d.dispatched_at, d.queued_at, d.created_at) AS updated_at
            FROM deliveries d
            JOIN prompt_generations pg ON pg.id = d.prompt_generation_id
            JOIN utterances u ON u.id = pg.utterance_id
            WHERE u.intake_note_id = %s
            ORDER BY d.created_at DESC, d.id DESC
            LIMIT 500
            """,
            (intake_note_id,),
        )
        processing_runs = _fetch_all(
            database_url,
            """
            SELECT
                pr.id,
                u.intake_note_id,
                pr.status::text AS status,
                COALESCE(pr.error_stage, pr.workflow_name) AS stage_name,
                COALESCE(pr.trace_json->>'error_text', pr.trace_json->'failure'->>'code') AS error_text,
                COALESCE(pr.trace_json, '{}'::jsonb) AS trace_json,
                pr.started_at AS created_at,
                COALESCE(pr.ended_at, pr.started_at) AS updated_at
            FROM processing_runs pr
            JOIN utterances u ON u.id = pr.utterance_id
            WHERE u.intake_note_id = %s
            ORDER BY pr.started_at DESC, pr.id DESC
            LIMIT 500
            """,
            (intake_note_id,),
        )
        return intake_notes, deliveries, processing_runs

    intake_notes = _fetch_all(
        database_url,
        """
        SELECT
            id,
            status::text AS status,
            note_relative_path,
            COALESCE(route_json, '{}'::jsonb) AS route_json,
            created_at,
            COALESCE(imported_at, created_at) AS updated_at
        FROM intake_notes
        ORDER BY created_at DESC, id DESC
        LIMIT 200
        """,
    )
    deliveries = _fetch_all(
        database_url,
        """
        SELECT
            d.id,
            d.prompt_generation_id,
            d.delivery_target_id AS target_id,
            d.status::text AS status,
            d.destination::text AS destination,
            d.mode::text AS mode,
            d.priority::text AS priority,
            GREATEST(
                0,
                (
                    SELECT COUNT(*)::int - 1
                    FROM deliveries d2
                    WHERE d2.prompt_generation_id = d.prompt_generation_id
                      AND d2.created_at <= d.created_at
                      AND d2.status = 'failed'
                )
            ) AS retry_count,
            d.error_text AS failure_text,
            NULL::text AS ack_text,
            d.created_at,
            COALESCE(d.acked_at, d.dispatched_at, d.queued_at, d.created_at) AS updated_at
        FROM deliveries d
        ORDER BY d.created_at DESC, d.id DESC
        LIMIT 300
        """,
    )
    processing_runs = _fetch_all(
        database_url,
        """
        SELECT
            pr.id,
            u.intake_note_id,
            pr.status::text AS status,
            COALESCE(pr.error_stage, pr.workflow_name) AS stage_name,
            COALESCE(pr.trace_json->>'error_text', pr.trace_json->'failure'->>'code') AS error_text,
            COALESCE(pr.trace_json, '{}'::jsonb) AS trace_json,
            pr.started_at AS created_at,
            COALESCE(pr.ended_at, pr.started_at) AS updated_at
        FROM processing_runs pr
        JOIN utterances u ON u.id = pr.utterance_id
        ORDER BY pr.started_at DESC, pr.id DESC
        LIMIT 400
        """,
    )
    return intake_notes, deliveries, processing_runs


def fetch_queue_depth(
    database_url: str,
    *,
    priority: str | None = None,
    destination: str | None = None,
) -> dict[str, Any]:
    clauses = ["status IN ('queued', 'dispatching')"]
    params: list[Any] = []
    if priority is not None and priority != "":
        clauses.append("priority = %s::pf_priority")
        params.append(priority)
    if destination is not None and destination != "":
        clauses.append("destination = %s::pf_destination")
        params.append(destination)
    where_sql = _where_sql(clauses)
    rows = _fetch_all(
        database_url,
        f"""
        SELECT
            COUNT(*) FILTER (WHERE status = 'queued')::int AS queued,
            COUNT(*) FILTER (WHERE status = 'dispatching')::int AS dispatching
        FROM deliveries
        {where_sql}
        """,
        tuple(params),
    )
    delivery_stats = rows[0] if rows else {"queued": 0, "dispatching": 0}

    error_rows = _fetch_all(
        database_url,
        """
        SELECT COUNT(*)::int AS failed_last_24h
        FROM workflow_error_records
        WHERE created_at >= NOW() - INTERVAL '24 hours'
        """,
    )
    failed_count = error_rows[0]["failed_last_24h"] if error_rows else 0

    return {
        "queued": delivery_stats["queued"],
        "dispatching": delivery_stats["dispatching"],
        "failed_last_24h": failed_count,
    }


def fetch_project_by_id(database_url: str, project_id: str) -> dict[str, Any] | None:
    rows = _fetch_all(
        database_url,
        "SELECT id, slug FROM projects WHERE id = %s LIMIT 1",
        (project_id,),
    )
    return rows[0] if rows else None


def fetch_throughput_summary(
    database_url: str,
    *,
    project_id: str | None,
    window_hours: int,
) -> tuple[dict[str, Any], datetime, datetime]:
    window_end = datetime.now(timezone.utc)
    window_start = window_end - timedelta(hours=window_hours)
    clauses = ["d.created_at >= %s", "d.created_at < %s"]
    params: list[Any] = [window_start, window_end]
    if project_id is not None and project_id != "":
        clauses.append("pg.project_id = %s")
        params.append(project_id)
    where_sql = _where_sql(clauses)
    rows = _fetch_all(
        database_url,
        f"""
        SELECT
            COUNT(*) FILTER (WHERE d.status IN ('delivered', 'acked'))::int AS completed_count,
            COUNT(*) FILTER (WHERE d.status = 'failed')::int AS failed_count
        FROM deliveries d
        JOIN prompt_generations pg ON pg.id = d.prompt_generation_id
        {where_sql}
        """,
        tuple(params),
    )
    return (rows[0] if rows else {"completed_count": 0, "failed_count": 0}), window_start, window_end


def fetch_sla_summary(
    database_url: str,
    *,
    project_id: str | None,
    target_seconds: int,
    window_hours: int,
) -> tuple[dict[str, Any], datetime, datetime]:
    window_end = datetime.now(timezone.utc)
    window_start = window_end - timedelta(hours=window_hours)
    clauses = [
        "COALESCE(i.imported_at, i.created_at) >= %s",
        "COALESCE(i.imported_at, i.created_at) < %s",
        "d.status IN ('delivered', 'acked', 'failed')",
    ]
    params: list[Any] = [window_start, window_end]
    if project_id is not None and project_id != "":
        clauses.append("i.project_id = %s")
        params.append(project_id)
    where_sql = _where_sql(clauses)
    rows = _fetch_all(
        database_url,
        f"""
        WITH terminal_events AS (
            SELECT DISTINCT ON (i.id)
                i.id AS intake_note_id,
                COALESCE(i.imported_at, i.created_at) AS imported_at,
                p.slug AS project_slug,
                d.status::text AS status,
                COALESCE(d.acked_at, d.dispatched_at, d.created_at) AS terminal_at
            FROM intake_notes i
            JOIN utterances u ON u.intake_note_id = i.id
            JOIN prompt_generations pg ON pg.utterance_id = u.id
            JOIN deliveries d ON d.prompt_generation_id = pg.id
            LEFT JOIN projects p ON p.id = i.project_id
            {where_sql}
            ORDER BY i.id, terminal_at ASC, d.created_at ASC, d.id ASC
        )
        SELECT
            COUNT(*) FILTER (WHERE status IN ('delivered', 'acked') AND EXTRACT(EPOCH FROM terminal_at - imported_at) <= %s)::int AS on_time_count,
            COUNT(*) FILTER (WHERE status = 'failed' OR EXTRACT(EPOCH FROM terminal_at - imported_at) > %s)::int AS breached_count,
            MAX(project_slug) AS project_slug
        FROM terminal_events
        """,
        (*params, target_seconds, target_seconds),
    )
    return (rows[0] if rows else {"on_time_count": 0, "breached_count": 0, "project_slug": None}), window_start, window_end


def fetch_recent_errors(database_url: str, hours: int = 24) -> list[dict[str, Any]]:
    return _fetch_all(
        database_url,
        """
        SELECT
            id,
            note_path,
            delivery_id,
            error_type,
            error_message,
            failed_at,
            dismissed_at,
            created_at
        FROM workflow_error_records
        WHERE created_at >= NOW() - INTERVAL '%s hours'
        ORDER BY created_at DESC
        LIMIT 100
        """,
        (hours,),
    )


def dismiss_error(database_url: str, error_id: str) -> int:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE workflow_error_records
                SET dismissed_at = now()
                WHERE id = %s AND dismissed_at IS NULL
                """,
                (error_id,),
            )
            count = cur.rowcount
        conn.commit()
    return count
