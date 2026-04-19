from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from psycopg.rows import dict_row

from promptforge_services.pipeline import llm_providers_health

router = APIRouter(prefix="/console", tags=["console"])


class DeliveryRerouteRequest(BaseModel):
    targetId: str


class DeliveryStatusRequest(BaseModel):
    status: str


class RulePatchRequest(BaseModel):
    enabled: bool | None = None
    priority: int | None = None


class DictionaryUpsertRequest(BaseModel):
    id: str | None = None
    scope: str | None = None
    project_id: str | None = None
    source_term: str | None = None
    normalized_term: str | None = None
    description: str | None = None


class TemplateActivateRequest(BaseModel):
    family: str


class PromptPriorityRequest(BaseModel):
    priority: str


def _db_url() -> str | None:
    return os.getenv("PROMPTFORGE_DATABASE_URL")


def _require_db_url() -> str:
    database_url = _db_url()
    if not database_url:
        raise HTTPException(status_code=503, detail="database_unconfigured")
    return database_url


def _fetch_all(database_url: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def _exec(database_url: str, sql: str, params: tuple[Any, ...] = ()) -> int:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            count = cur.rowcount
        conn.commit()
    return count


def _to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def _build_logs(
    intake_notes: list[dict[str, Any]],
    deliveries: list[dict[str, Any]],
    processing_runs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for run in processing_runs[:400]:
        stage_name = str(run.get("stage_name") or "pipeline")
        error_text = run.get("error_text")
        message = f"{stage_name}: {'failed' if error_text else 'completed'}"
        level = "error" if error_text else "info"
        intake_id = run.get("intake_note_id")
        payload = f"run|{run.get('id')}|{message}|{_to_iso(run.get('updated_at'))}"
        out.append(
            {
                "id": "log-" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16],
                "service": "api",
                "level": level,
                "message": error_text or message,
                "timestamp": _to_iso(run.get("updated_at")),
                "intake_note_id": intake_id,
                "utterance_id": None,
                "prompt_generation_id": None,
                "delivery_id": None,
                "fields": {"trace": run.get("trace_json")},
            }
        )
    for delivery in deliveries[:300]:
        status = str(delivery.get("status") or "")
        failure = delivery.get("failure_text")
        level = "error" if status == "failed" else "info"
        payload = f"delivery|{delivery.get('id')}|{status}|{_to_iso(delivery.get('updated_at'))}"
        out.append(
            {
                "id": "log-" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16],
                "service": "watcher",
                "level": level,
                "message": failure or f"delivery_{status}",
                "timestamp": _to_iso(delivery.get("updated_at")),
                "intake_note_id": None,
                "utterance_id": None,
                "prompt_generation_id": delivery.get("prompt_generation_id"),
                "delivery_id": delivery.get("id"),
                "fields": {},
            }
        )
    for note in intake_notes[:200]:
        payload = f"intake|{note.get('id')}|{note.get('status')}|{_to_iso(note.get('updated_at'))}"
        out.append(
            {
                "id": "log-" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16],
                "service": "watcher",
                "level": "warn" if note.get("status") == "error" else "info",
                "message": f"note_{note.get('status')}",
                "timestamp": _to_iso(note.get("updated_at")),
                "intake_note_id": note.get("id"),
                "utterance_id": None,
                "prompt_generation_id": None,
                "delivery_id": None,
                "fields": {"path": note.get("note_relative_path")},
            }
        )
    out.sort(key=lambda row: row["timestamp"], reverse=True)
    return out[:500]


def _empty_bootstrap() -> dict[str, Any]:
    return {
        "projects": [],
        "intakeNotes": [],
        "utterances": [],
        "transcriptRevisions": [],
        "promptGenerations": [],
        "deliveries": [],
        "deliveryHistory": [],
        "processingRuns": [],
        "llmRuns": [],
        "rulesets": [],
        "rules": [],
        "termDictionary": [],
        "promptTemplates": [],
        "deliveryTargets": [],
        "logs": [],
        "healthSnapshot": {
            "api": {"status": "degraded", "latency_ms": 0, "checked_at": datetime.now(timezone.utc).isoformat()},
            "providers": [],
            "db": {"status": "degraded", "latency_ms": 0},
            "queue_depth": 0,
            "failures_24h": 0,
        },
    }


@router.get("/bootstrap")
def console_bootstrap() -> dict[str, Any]:
    database_url = _db_url()
    if not database_url:
        return _empty_bootstrap()

    projects = _fetch_all(
        database_url,
        """
        SELECT id, name, slug, description, created_at, updated_at
        FROM projects
        ORDER BY updated_at DESC
        LIMIT 500
        """,
    )
    intake_notes = _fetch_all(
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
            COALESCE(frontmatter_json, '{}'::jsonb) AS frontmatter_json,
            COALESCE(last_error, '') AS last_error,
            created_at,
            COALESCE(imported_at, created_at) AS updated_at
        FROM intake_notes
        ORDER BY created_at DESC
        LIMIT 1200
        """,
    )
    utterances = _fetch_all(
        database_url,
        """
        SELECT id, intake_note_id, created_at
        FROM utterances
        ORDER BY created_at DESC
        LIMIT 1200
        """,
    )
    transcript_revisions = _fetch_all(
        database_url,
        """
        SELECT
            id,
            utterance_id,
            revision_kind::text AS revision_kind,
            producer_type::text AS producer_type,
            producer_name,
            content AS content_text,
            COALESCE(metadata_json, '{}'::jsonb) AS metadata_json,
            created_at
        FROM transcript_revisions
        ORDER BY created_at DESC
        LIMIT 3000
        """,
    )
    prompt_generations = _fetch_all(
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
            COALESCE(ld.created_at, pg.created_at) AS updated_at
        FROM prompt_generations pg
        JOIN utterances u ON u.id = pg.utterance_id
        LEFT JOIN LATERAL (
            SELECT d.*
            FROM deliveries d
            WHERE d.prompt_generation_id = pg.id
            ORDER BY d.created_at DESC
            LIMIT 1
        ) ld ON TRUE
        ORDER BY pg.created_at DESC
        LIMIT 1200
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
            COALESCE(d.acked_at, d.dispatched_at, d.created_at) AS updated_at
        FROM deliveries d
        ORDER BY d.created_at DESC
        LIMIT 2000
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
        ORDER BY pr.started_at DESC
        LIMIT 2500
        """,
    )
    llm_runs = _fetch_all(
        database_url,
        """
        SELECT
            id,
            prompt_generation_id,
            COALESCE(provider_name, 'unknown') AS provider_name,
            COALESCE(model_name, 'unknown') AS model_name,
            COALESCE(mode::text, 'inference') AS mode,
            COALESCE(latency_ms, 0) AS latency_ms,
            COALESCE((token_usage_json->>'input_tokens')::int, 0) AS input_tokens,
            COALESCE((token_usage_json->>'output_tokens')::int, 0) AS output_tokens,
            created_at
        FROM llm_runs
        ORDER BY created_at DESC
        LIMIT 2000
        """,
    )
    rulesets = _fetch_all(
        database_url,
        """
        SELECT
            id,
            name,
            scope::text AS scope,
            project_id,
            is_active AS active,
            description,
            created_at AS updated_at
        FROM rulesets
        ORDER BY created_at DESC
        LIMIT 500
        """,
    )
    rules = _fetch_all(
        database_url,
        """
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
        ORDER BY created_at DESC
        LIMIT 3000
        """,
    )
    term_dictionary = _fetch_all(
        database_url,
        """
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
        ORDER BY created_at DESC
        LIMIT 3000
        """,
    )
    prompt_templates = _fetch_all(
        database_url,
        """
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
        ORDER BY created_at DESC
        LIMIT 1500
        """,
    )
    delivery_targets = _fetch_all(
        database_url,
        """
        SELECT
            id,
            name,
            target_type::text AS target_type,
            COALESCE(config_json->>'destination', 'queue_only') AS destination,
            scope::text AS scope,
            project_id,
            TRUE AS enabled,
            FALSE AS is_sensitive,
            NOT is_auto_dispatch_safe AS requires_confirmation,
            'prod'::text AS environment,
            'ok'::text AS validation_status,
            created_at AS updated_at
        FROM delivery_targets
        ORDER BY created_at DESC
        LIMIT 1500
        """,
    )
    queue_depth_rows = _fetch_all(
        database_url,
        """
        SELECT COUNT(*)::int AS queued_count
        FROM deliveries
        WHERE status IN ('queued', 'dispatching')
        """,
    )
    failures_24h_rows = _fetch_all(
        database_url,
        """
        SELECT COUNT(*)::int AS failures
        FROM processing_runs
        WHERE status = 'failed' AND started_at >= now() - interval '24 hours'
        """,
    )

    health = llm_providers_health()
    queue_depth = queue_depth_rows[0]["queued_count"] if queue_depth_rows else 0
    failures_24h = failures_24h_rows[0]["failures"] if failures_24h_rows else 0

    intake_payload = [
        {
            "id": row["id"],
            "project_id": row["project_id"],
            "note_relative_path": row["note_relative_path"],
            "status": row["status"],
            "watch_eligible": bool(row["watch_eligible"]),
            "source_device": row["source_device"],
            "body_text": row["body_text"],
            "frontmatter_original": row["frontmatter_json"],
            "frontmatter_current": row["frontmatter_json"],
            "metadata_json": {"last_error": row["last_error"]} if row["last_error"] else {},
            "created_at": _to_iso(row["created_at"]),
            "updated_at": _to_iso(row["updated_at"]),
        }
        for row in intake_notes
    ]
    utterance_payload = [
        {
            "id": row["id"],
            "intake_note_id": row["intake_note_id"],
            "speaker": None,
            "index": 0,
            "created_at": _to_iso(row["created_at"]),
        }
        for row in utterances
    ]
    logs = _build_logs(intake_payload, deliveries, processing_runs)

    return {
        "projects": [
            {
                "id": row["id"],
                "name": row["name"],
                "slug": row["slug"],
                "description": row["description"],
                "created_at": _to_iso(row["created_at"]),
                "updated_at": _to_iso(row["updated_at"]),
            }
            for row in projects
        ],
        "intakeNotes": intake_payload,
        "utterances": utterance_payload,
        "transcriptRevisions": [
            {
                "id": row["id"],
                "utterance_id": row["utterance_id"],
                "revision_kind": row["revision_kind"],
                "producer_type": row["producer_type"],
                "producer_name": row["producer_name"],
                "content_text": row["content_text"],
                "metadata_json": row["metadata_json"] or {},
                "created_at": _to_iso(row["created_at"]),
            }
            for row in transcript_revisions
        ],
        "promptGenerations": [
            {
                "id": row["id"],
                "intake_note_id": row["intake_note_id"],
                "status": row["status"],
                "requires_review": bool(row["requires_review"]),
                "prompt_type": row["prompt_type"],
                "ruleset_id": row["ruleset_id"],
                "template_id": row["template_id"],
                "destination": row["destination"],
                "mode": row["mode"],
                "priority": row["priority"],
                "structured_output_json": row["structured_output_json"] or {},
                "final_prompt_markdown": row["final_prompt_markdown"] or "",
                "validation_warnings": row["validation_warnings"] or [],
                "created_at": _to_iso(row["created_at"]),
                "updated_at": _to_iso(row["updated_at"]),
            }
            for row in prompt_generations
        ],
        "deliveries": [
            {
                "id": row["id"],
                "prompt_generation_id": row["prompt_generation_id"],
                "target_id": row["target_id"],
                "status": row["status"],
                "destination": row["destination"],
                "mode": row["mode"],
                "priority": row["priority"],
                "retry_count": int(row["retry_count"] or 0),
                "failure_text": row["failure_text"],
                "ack_text": row["ack_text"],
                "created_at": _to_iso(row["created_at"]),
                "updated_at": _to_iso(row["updated_at"]),
            }
            for row in deliveries
        ],
        "deliveryHistory": [row for row in deliveries if row.get("status") == "failed"],
        "processingRuns": [
            {
                "id": row["id"],
                "intake_note_id": row["intake_note_id"],
                "status": row["status"],
                "stage_name": row["stage_name"],
                "error_text": row["error_text"],
                "trace_json": row["trace_json"] or {},
                "created_at": _to_iso(row["created_at"]),
                "updated_at": _to_iso(row["updated_at"]),
            }
            for row in processing_runs
        ],
        "llmRuns": [
            {
                "id": row["id"],
                "prompt_generation_id": row["prompt_generation_id"],
                "provider_name": row["provider_name"],
                "model_name": row["model_name"],
                "mode": row["mode"],
                "latency_ms": int(row["latency_ms"] or 0),
                "input_tokens": int(row["input_tokens"] or 0),
                "output_tokens": int(row["output_tokens"] or 0),
                "created_at": _to_iso(row["created_at"]),
            }
            for row in llm_runs
        ],
        "rulesets": rulesets,
        "rules": rules,
        "termDictionary": term_dictionary,
        "promptTemplates": prompt_templates,
        "deliveryTargets": delivery_targets,
        "logs": logs,
        "healthSnapshot": {
            "api": {"status": "ok", "latency_ms": 0, "checked_at": datetime.now(timezone.utc).isoformat()},
            "providers": [
                {
                    "name": provider.provider_name,
                    "status": "ok" if provider.available else "degraded",
                    "latency_ms": 0,
                }
                for provider in health.providers
            ],
            "db": {"status": "ok", "latency_ms": 0},
            "queue_depth": int(queue_depth or 0),
            "failures_24h": int(failures_24h or 0),
        },
    }


@router.post("/deliveries/{delivery_id}/retry")
def retry_delivery(delivery_id: str) -> dict[str, Any]:
    database_url = _require_db_url()
    updated = _exec(
        database_url,
        """
        UPDATE deliveries
        SET status = 'queued',
            queued_at = now(),
            error_text = NULL
        WHERE id = %s
        """,
        (delivery_id,),
    )
    if updated == 0:
        raise HTTPException(status_code=404, detail="delivery_not_found")
    return {"ok": True, "message": "Retry queued"}


@router.post("/deliveries/{delivery_id}/reroute")
def reroute_delivery(delivery_id: str, payload: DeliveryRerouteRequest) -> dict[str, Any]:
    database_url = _require_db_url()
    target_rows = _fetch_all(
        database_url,
        """
        SELECT id, target_type::text AS target_type, target_identifier
        FROM delivery_targets
        WHERE id = %s
        LIMIT 1
        """,
        (payload.targetId,),
    )
    if not target_rows:
        raise HTTPException(status_code=404, detail="target_not_found")
    target = target_rows[0]
    updated = _exec(
        database_url,
        """
        UPDATE deliveries
        SET delivery_target_id = %s,
            target_type = %s::pf_target_type,
            target_identifier = %s
        WHERE id = %s
        """,
        (target["id"], target["target_type"], target["target_identifier"], delivery_id),
    )
    if updated == 0:
        raise HTTPException(status_code=404, detail="delivery_not_found")
    return {"ok": True}


@router.patch("/deliveries/{delivery_id}/status")
def patch_delivery_status(delivery_id: str, payload: DeliveryStatusRequest) -> dict[str, Any]:
    database_url = _require_db_url()
    updated = _exec(
        database_url,
        """
        UPDATE deliveries
        SET status = %s::pf_delivery_status
        WHERE id = %s
        """,
        (payload.status, delivery_id),
    )
    if updated == 0:
        raise HTTPException(status_code=404, detail="delivery_not_found")
    return {"ok": True}


@router.patch("/rules/{rule_id}")
def patch_rule(rule_id: str, payload: RulePatchRequest) -> dict[str, Any]:
    database_url = _require_db_url()
    row = _fetch_all(
        database_url,
        "SELECT enabled, priority FROM rules WHERE id = %s LIMIT 1",
        (rule_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="rule_not_found")
    current = row[0]
    enabled = payload.enabled if payload.enabled is not None else current["enabled"]
    priority = payload.priority if payload.priority is not None else current["priority"]
    _exec(
        database_url,
        """
        UPDATE rules
        SET enabled = %s,
            priority = %s
        WHERE id = %s
        """,
        (enabled, priority, rule_id),
    )
    return {"ok": True}


@router.post("/dictionary/upsert")
def upsert_dictionary(payload: DictionaryUpsertRequest) -> dict[str, Any]:
    database_url = _require_db_url()
    scope = payload.scope or "global"
    source_term = payload.source_term or ""
    normalized_term = payload.normalized_term or payload.source_term or ""
    if not source_term.strip():
        raise HTTPException(status_code=400, detail="source_term_required")
    if payload.id:
        _exec(
            database_url,
            """
            UPDATE term_dictionary
            SET scope = %s::pf_scope,
                project_id = %s,
                source_term = %s,
                canonical_term = %s,
                notes = %s
            WHERE id = %s
            """,
            (scope, payload.project_id, source_term, normalized_term, payload.description, payload.id),
        )
        return {"ok": True, "payload": payload.model_dump()}
    inserted = _fetch_all(
        database_url,
        """
        INSERT INTO term_dictionary (scope, project_id, source_term, canonical_term, notes)
        VALUES (%s::pf_scope, %s, %s, %s, %s)
        ON CONFLICT (scope, project_id, source_term)
        DO UPDATE SET canonical_term = EXCLUDED.canonical_term, notes = EXCLUDED.notes
        RETURNING id
        """,
        (scope, payload.project_id, source_term, normalized_term, payload.description),
    )
    out = payload.model_dump()
    out["id"] = inserted[0]["id"] if inserted else None
    return {"ok": True, "payload": out}


@router.post("/templates/{template_id}/activate")
def activate_template(template_id: str, payload: TemplateActivateRequest) -> dict[str, Any]:
    database_url = _require_db_url()
    _exec(
        database_url,
        """
        UPDATE prompt_templates
        SET is_active = FALSE
        WHERE output_contract_name = %s
        """,
        (payload.family,),
    )
    updated = _exec(
        database_url,
        "UPDATE prompt_templates SET is_active = TRUE WHERE id = %s",
        (template_id,),
    )
    if updated == 0:
        raise HTTPException(status_code=404, detail="template_not_found")
    return {"ok": True}


@router.post("/prompts/{prompt_generation_id}/force-review")
def force_prompt_review(prompt_generation_id: str) -> dict[str, Any]:
    database_url = _require_db_url()
    updated = _exec(
        database_url,
        "UPDATE prompt_generations SET requires_review = TRUE WHERE id = %s",
        (prompt_generation_id,),
    )
    if updated == 0:
        raise HTTPException(status_code=404, detail="prompt_generation_not_found")
    return {"ok": True}


@router.post("/prompts/{prompt_generation_id}/clone")
def clone_prompt(prompt_generation_id: str) -> dict[str, Any]:
    database_url = _require_db_url()
    rows = _fetch_all(
        database_url,
        """
        INSERT INTO prompt_generations (
            utterance_id, project_id, prompt_type, selected_ruleset_id, selected_template_id,
            structured_output_json, final_prompt_markdown, requires_review, status, error_text
        )
        SELECT
            utterance_id, project_id, prompt_type, selected_ruleset_id, selected_template_id,
            structured_output_json, final_prompt_markdown, requires_review, 'created'::pf_prompt_generation_status, NULL
        FROM prompt_generations
        WHERE id = %s
        RETURNING id
        """,
        (prompt_generation_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="prompt_generation_not_found")
    return {"ok": True, "newId": rows[0]["id"]}


@router.patch("/prompts/{prompt_generation_id}/priority")
def patch_prompt_priority(prompt_generation_id: str, payload: PromptPriorityRequest) -> dict[str, Any]:
    database_url = _require_db_url()
    updated = _exec(
        database_url,
        """
        UPDATE deliveries d
        SET priority = %s::pf_priority
        WHERE d.id = (
            SELECT d2.id
            FROM deliveries d2
            WHERE d2.prompt_generation_id = %s
            ORDER BY d2.created_at DESC
            LIMIT 1
        )
        """,
        (payload.priority, prompt_generation_id),
    )
    if updated == 0:
        raise HTTPException(status_code=404, detail="delivery_for_prompt_not_found")
    return {"ok": True}


@router.patch("/intake/{intake_note_id}/archive")
def archive_intake_note(intake_note_id: str) -> dict[str, Any]:
    database_url = _require_db_url()
    updated = _exec(
        database_url,
        """
        UPDATE intake_notes
        SET status = 'archived',
            watch_eligible = FALSE
        WHERE id = %s
        """,
        (intake_note_id,),
    )
    if updated == 0:
        raise HTTPException(status_code=404, detail="intake_note_not_found")
    return {"ok": True}
