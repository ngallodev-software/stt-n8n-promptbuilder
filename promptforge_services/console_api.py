from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from promptforge_services import console_queries as cq
from promptforge_services.console_models import (
    DictionaryTermDetailResponse,
    DictionaryTermListResponse,
    DictionaryTermRecord,
    DeliveryDetailResponse,
    DeliveryListResponse,
    DeliveryRecord,
    DeliveryTargetDetailResponse,
    DeliveryTargetListResponse,
    DeliveryTargetRecord,
    ErrorFingerprintListResponse,
    ErrorFingerprintRecord,
    IntakeNoteDetailResponse,
    IntakeNoteListResponse,
    IntakeNoteRecord,
    LogListResponse,
    LogRecord,
    NoteLineageResponse,
    PaginatedResponse,
    PaginationMeta,
    ProcessingRunRecord,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectRecord,
    PromptDetailResponse,
    PromptGenerationRecord,
    PromptListResponse,
    PromptTemplateDetailResponse,
    PromptTemplateListResponse,
    PromptTemplateRecord,
    QueueDepthResponse,
    RuleDetailResponse,
    RuleListResponse,
    RuleRecord,
    RuleSetRecord,
    RulesetDetailResponse,
    RulesetListResponse,
    SlaSummaryResponse,
    ThroughputSummaryResponse,
    TranscriptRevisionRecord,
    UtteranceRecord,
)
from promptforge_services.pipeline import llm_providers_health

router = APIRouter(prefix="/console", tags=["console"])

DEFAULT_LIMIT = 100
DEFAULT_OFFSET = 0
VALID_NOTE_STATUSES = {"new", "imported", "processing", "processed", "error", "archived"}
VALID_PROMPT_STATUSES = {"created", "preprocessed", "transforming", "structured_validating", "rendered", "failed"}
VALID_DELIVERY_STATUSES = {"not_started", "queued", "dispatching", "delivered", "acked", "failed"}
VALID_SCOPE_VALUES = {"global", "user", "project"}
VALID_LOG_LEVELS = {"debug", "info", "warn", "error"}
VALID_TARGET_TYPES = {"none", "chat_session", "claude_session", "codex_session", "obsidian_note", "generic_queue"}
VALID_PRIORITY_VALUES = {"low", "normal", "high", "urgent"}
VALID_DESTINATIONS = {"chat", "cli", "obsidian_note", "queue_only"}
DEFAULT_WINDOW_HOURS = 24
DEFAULT_SLA_TARGET_SECONDS = 3600


class ProcessingRunListResponse(PaginatedResponse[ProcessingRunRecord]):
    processing_runs: list[ProcessingRunRecord] = Field(alias="processingRuns")


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

    projects, _ = cq.fetch_projects(database_url, 500, 0)
    intake_notes, _ = cq.fetch_intake_notes(database_url, limit=1200, offset=0)
    utterances = cq.fetch_utterance_summaries(database_url, 1200)
    transcript_revisions = cq.fetch_transcript_revisions(database_url, limit=3000, ascending=False)
    prompt_generations, _ = cq.fetch_prompt_generations(database_url, limit=1200, offset=0, ascending=False)
    deliveries, _ = cq.fetch_deliveries(database_url, limit=2000, offset=0, ascending=False)
    processing_runs, _ = cq.fetch_processing_runs(database_url, limit=2500, offset=0, ascending=False)
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
    rulesets, _ = cq.fetch_rulesets(database_url, limit=500, offset=0)
    rules, _ = cq.fetch_rules(database_url, limit=3000, offset=0)
    term_dictionary, _ = cq.fetch_dictionary_terms(database_url, limit=3000, offset=0)
    prompt_templates, _ = cq.fetch_prompt_templates(database_url, limit=1500, offset=0)
    delivery_targets, _ = cq.fetch_delivery_targets(database_url, limit=1500, offset=0)
    log_intake_notes, log_deliveries, log_processing_runs = cq.fetch_log_sources(database_url)
    logs = _build_logs(log_intake_notes, log_deliveries, log_processing_runs)
    queue_depth_row = cq.fetch_queue_depth(database_url)
    queue_depth = int(queue_depth_row.get('queue_depth', 0))
    failures_24h_rows = _fetch_all(
        database_url,
        """
        SELECT COUNT(*)::int AS failures
        FROM processing_runs
        WHERE status = 'failed' AND started_at >= now() - interval '24 hours'
        """,
    )
    health = llm_providers_health()
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
            "frontmatter_original": row["frontmatter_original"],
            "frontmatter_current": row["frontmatter_current"],
            "metadata_json": row["metadata_json"],
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
            "queue_depth": queue_depth,
            "failures_24h": int(failures_24h or 0),
        },
    }


def _parse_int_param(name: str, value: str | None, default: int, minimum: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"invalid_{name}")
    if parsed < minimum:
        raise HTTPException(status_code=400, detail=f"invalid_{name}")
    return parsed


def _parse_limit_offset(limit: str | None, offset: str | None) -> tuple[int, int]:
    return (
        _parse_int_param("limit", limit, DEFAULT_LIMIT, 1),
        _parse_int_param("offset", offset, DEFAULT_OFFSET, 0),
    )


def _validated_choice(name: str, value: str | None, allowed: set[str]) -> str | None:
    if value is None or value == "":
        return None
    if value not in allowed:
        raise HTTPException(status_code=400, detail=f"invalid_{name}")
    return value


def _pagination_meta(total: int, limit: int, offset: int) -> PaginationMeta:
    return PaginationMeta(total=total, limit=limit, offset=offset, has_more=offset + limit < total)


def _paginated_response(response_cls: Any, field_name: str, items: list[Any], total: int, limit: int, offset: int) -> Any:
    return response_cls(pagination=_pagination_meta(total, limit, offset), **{field_name: items})


def _where_sql(clauses: list[str]) -> str:
    return " WHERE " + " AND ".join(clauses) if clauses else ""


def _project_record(row: dict[str, Any]) -> ProjectRecord:
    return ProjectRecord(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        description=row.get("description"),
        created_at=_to_iso(row["created_at"]),
        updated_at=_to_iso(row["updated_at"]),
    )


def _intake_note_record(row: dict[str, Any]) -> IntakeNoteRecord:
    return IntakeNoteRecord(
        id=row["id"],
        project_id=row.get("project_id"),
        note_relative_path=row["note_relative_path"],
        status=row["status"],
        watch_eligible=bool(row["watch_eligible"]),
        source_device=row["source_device"],
        body_text=row.get("body_text") or "",
        frontmatter_original=row.get("frontmatter_original") or {},
        frontmatter_current=row.get("frontmatter_current") or {},
        metadata_json=row.get("metadata_json") or {},
        created_at=_to_iso(row["created_at"]),
        updated_at=_to_iso(row["updated_at"]),
    )


def _utterance_record(row: dict[str, Any]) -> UtteranceRecord:
    return UtteranceRecord(
        id=row["id"],
        intake_note_id=row["intake_note_id"],
        raw_text=row["raw_text"],
        directive_text=row.get("directive_text"),
        project_id=row.get("project_id"),
        scope=row["scope"],
        capture_type=row["capture_type"],
        created_at=_to_iso(row["created_at"]),
    )


def _transcript_revision_record(row: dict[str, Any]) -> TranscriptRevisionRecord:
    return TranscriptRevisionRecord(
        id=row["id"],
        utterance_id=row["utterance_id"],
        revision_kind=row["revision_kind"],
        content_text=row["content_text"],
        producer_type=row["producer_type"],
        producer_name=row["producer_name"],
        template_profile=row.get("template_profile"),
        quality_score=row.get("quality_score"),
        metadata_json=row.get("metadata_json") or {},
        created_at=_to_iso(row["created_at"]),
    )


def _prompt_generation_record(row: dict[str, Any]) -> PromptGenerationRecord:
    return PromptGenerationRecord(
        id=row["id"],
        intake_note_id=row["intake_note_id"],
        status=row["status"],
        requires_review=bool(row["requires_review"]),
        prompt_type=row["prompt_type"],
        ruleset_id=row.get("ruleset_id"),
        template_id=row.get("template_id"),
        destination=row["destination"],
        mode=row["mode"],
        priority=row["priority"],
        structured_output_json=row.get("structured_output_json") or {},
        final_prompt_markdown=row.get("final_prompt_markdown") or "",
        validation_warnings=row.get("validation_warnings") or [],
        created_at=_to_iso(row["created_at"]),
        updated_at=_to_iso(row["updated_at"]),
    )


def _delivery_record(row: dict[str, Any]) -> DeliveryRecord:
    return DeliveryRecord(
        id=row["id"],
        prompt_generation_id=row["prompt_generation_id"],
        target_id=row.get("target_id"),
        status=row["status"],
        destination=row["destination"],
        mode=row["mode"],
        priority=row["priority"],
        retry_count=int(row.get("retry_count") or 0),
        failure_text=row.get("failure_text"),
        ack_text=row.get("ack_text"),
        created_at=_to_iso(row["created_at"]),
        updated_at=_to_iso(row["updated_at"]),
    )


def _processing_run_record(row: dict[str, Any]) -> ProcessingRunRecord:
    return ProcessingRunRecord(
        id=row["id"],
        intake_note_id=row["intake_note_id"],
        status=row["status"],
        stage_name=row["stage_name"],
        error_text=row.get("error_text"),
        trace_json=row.get("trace_json") or {},
        created_at=_to_iso(row["created_at"]),
        updated_at=_to_iso(row["updated_at"]),
    )


def _ruleset_record(row: dict[str, Any]) -> RuleSetRecord:
    return RuleSetRecord(
        id=row["id"],
        name=row["name"],
        scope=row["scope"],
        project_id=row.get("project_id"),
        active=bool(row["active"]),
        description=row.get("description"),
        updated_at=_to_iso(row["updated_at"]),
    )


def _rule_record(row: dict[str, Any]) -> RuleRecord:
    return RuleRecord(
        id=row["id"],
        ruleset_id=row["ruleset_id"],
        name=row["name"],
        rule_type=row["rule_type"],
        priority=int(row["priority"]),
        enabled=bool(row["enabled"]),
        pattern=row.get("pattern") or "",
        replacement=row.get("replacement") or "",
        description=row.get("description"),
        updated_at=_to_iso(row["updated_at"]),
    )


def _dictionary_term_record(row: dict[str, Any]) -> DictionaryTermRecord:
    return DictionaryTermRecord(
        id=row["id"],
        scope=row["scope"],
        project_id=row.get("project_id"),
        source_term=row["source_term"],
        normalized_term=row["normalized_term"],
        description=row.get("description"),
        created_at=_to_iso(row["created_at"]),
        updated_at=_to_iso(row["updated_at"]),
    )


def _prompt_template_record(row: dict[str, Any]) -> PromptTemplateRecord:
    return PromptTemplateRecord(
        id=row["id"],
        name=row["name"],
        prompt_type=row["prompt_type"],
        scope=row["scope"],
        project_id=row.get("project_id"),
        version=int(row["version"]),
        is_active=bool(row["is_active"]),
        template_family_key=row["template_family_key"],
        body=row["body"],
        updated_at=_to_iso(row["updated_at"]),
    )


def _delivery_target_record(row: dict[str, Any]) -> DeliveryTargetRecord:
    return DeliveryTargetRecord(
        id=row["id"],
        name=row["name"],
        target_type=row["target_type"],
        destination=row["destination"],
        scope=row["scope"],
        project_id=row.get("project_id"),
        enabled=bool(row["enabled"]),
        is_sensitive=bool(row["is_sensitive"]),
        requires_confirmation=bool(row["requires_confirmation"]),
        environment=row["environment"],
        validation_status=row["validation_status"],
        updated_at=_to_iso(row["updated_at"]),
    )


def _log_record(row: dict[str, Any]) -> LogRecord:
    return LogRecord(
        id=row["id"],
        service=row["service"],
        level=row["level"],
        message=row["message"],
        timestamp=_to_iso(row["timestamp"]),
        intake_note_id=row.get("intake_note_id"),
        utterance_id=row.get("utterance_id"),
        prompt_generation_id=row.get("prompt_generation_id"),
        delivery_id=row.get("delivery_id"),
        fields=row.get("fields") or {},
    )


def _fetch_project_row(database_url: str, project_id: str) -> dict[str, Any]:
    rows = _fetch_all(
        database_url,
        "SELECT id, slug FROM projects WHERE id = %s LIMIT 1",
        (project_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="project_not_found")
    return rows[0]


def _fetch_log_sources(
    database_url: str,
    intake_note_id: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    intake_notes, deliveries, processing_runs = _fetch_log_sources(database_url, intake_note_id)
    if intake_note_id and not intake_notes:
        raise HTTPException(status_code=404, detail="intake_note_not_found")
    return intake_notes, deliveries, processing_runs


def _build_log_records(
    intake_notes: list[dict[str, Any]],
    deliveries: list[dict[str, Any]],
    processing_runs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _build_logs(intake_notes, deliveries, processing_runs)


def _filter_logs(
    logs: list[dict[str, Any]],
    *,
    level: str | None,
    service: str | None,
    intake_note_id: str | None,
) -> list[dict[str, Any]]:
    filtered = logs
    if level is not None:
        filtered = [row for row in filtered if row.get("level") == level]
    if service is not None:
        filtered = [row for row in filtered if row.get("service") == service]
    if intake_note_id is not None:
        filtered = [row for row in filtered if row.get("intake_note_id") == intake_note_id]
    return filtered


def _window_bounds(window_hours: int) -> tuple[datetime, datetime]:
    window_end = datetime.now(timezone.utc)
    return window_end - timedelta(hours=window_hours), window_end



@router.get("/projects", response_model=ProjectListResponse)
def list_projects(limit: str | None = None, offset: str | None = None) -> ProjectListResponse:
    database_url = _require_db_url()
    limit_value, offset_value = _parse_limit_offset(limit, offset)
    rows, total = cq.fetch_projects(database_url, limit_value, offset_value)
    return ProjectListResponse(
        pagination=_pagination_meta(total, limit_value, offset_value),
        projects=[_project_record(row) for row in rows],
    )


@router.get("/intake", response_model=IntakeNoteListResponse)
def list_intake_notes(
    project_id: str | None = None,
    status: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
) -> IntakeNoteListResponse:
    database_url = _require_db_url()
    limit_value, offset_value = _parse_limit_offset(limit, offset)
    status_value = _validated_choice("status", status, VALID_NOTE_STATUSES)
    rows, total = cq.fetch_intake_notes(
        database_url,
        project_id=project_id,
        status=status_value,
        limit=limit_value,
        offset=offset_value,
    )
    return IntakeNoteListResponse(
        pagination=_pagination_meta(total, limit_value, offset_value),
        intake_notes=[_intake_note_record(row) for row in rows],
    )


@router.get("/intake/{id}", response_model=IntakeNoteDetailResponse)
def get_intake_note(id: str) -> IntakeNoteDetailResponse:
    database_url = _require_db_url()
    row = cq.fetch_intake_note(database_url, id)
    if not row:
        raise HTTPException(status_code=404, detail="intake_note_not_found")
    return IntakeNoteDetailResponse(note=_intake_note_record(row))


@router.get("/lineage/{intakeNoteId}", response_model=NoteLineageResponse)
def get_intake_lineage(intakeNoteId: str) -> NoteLineageResponse:
    database_url = _require_db_url()
    note_row = cq.fetch_intake_note(database_url, intakeNoteId)
    if not note_row:
        raise HTTPException(status_code=404, detail="intake_note_not_found")
    utterance_rows = cq.fetch_utterances_for_note(database_url, intakeNoteId)
    utterance_ids = [row["id"] for row in utterance_rows]
    revision_rows = cq.fetch_transcript_revisions(database_url, intake_note_id=intakeNoteId, limit=100000, ascending=True)
    prompt_rows, _ = cq.fetch_prompt_generations(
        database_url,
        intake_note_id=intakeNoteId,
        limit=100000,
        offset=0,
        ascending=True,
    )
    prompt_ids = [row["id"] for row in prompt_rows]
    delivery_rows: list[dict[str, Any]] = []
    if prompt_ids:
        delivery_rows = []
        for prompt_id in prompt_ids:
            rows, _ = cq.fetch_deliveries(
                database_url,
                prompt_generation_id=prompt_id,
                limit=100000,
                offset=0,
                ascending=True,
            )
            delivery_rows.extend(rows)
    processing_rows, _ = cq.fetch_processing_runs(
        database_url,
        intake_note_id=intakeNoteId,
        limit=100000,
        offset=0,
        ascending=True,
    )
    return NoteLineageResponse(
        intake_note=_intake_note_record(note_row),
        utterances=[_utterance_record(row) for row in utterance_rows],
        revisions=[_transcript_revision_record(row) for row in revision_rows],
        prompt_generations=[_prompt_generation_record(row) for row in prompt_rows],
        deliveries=[_delivery_record(row) for row in delivery_rows],
        processing_runs=[_processing_run_record(row) for row in processing_rows],
    )


@router.get("/prompts", response_model=PromptListResponse)
def list_prompts(
    intake_note_id: str | None = None,
    status: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
) -> PromptListResponse:
    database_url = _require_db_url()
    limit_value, offset_value = _parse_limit_offset(limit, offset)
    status_value = _validated_choice("status", status, VALID_PROMPT_STATUSES)
    rows, total = cq.fetch_prompt_generations(
        database_url,
        intake_note_id=intake_note_id,
        status=status_value,
        limit=limit_value,
        offset=offset_value,
        ascending=False,
    )
    return PromptListResponse(
        pagination=_pagination_meta(total, limit_value, offset_value),
        prompt_generations=[_prompt_generation_record(row) for row in rows],
    )


@router.get("/deliveries", response_model=DeliveryListResponse)
def list_deliveries(
    prompt_generation_id: str | None = None,
    status: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
) -> DeliveryListResponse:
    database_url = _require_db_url()
    limit_value, offset_value = _parse_limit_offset(limit, offset)
    status_value = _validated_choice("status", status, VALID_DELIVERY_STATUSES)
    rows, total = cq.fetch_deliveries(
        database_url,
        prompt_generation_id=prompt_generation_id,
        status=status_value,
        limit=limit_value,
        offset=offset_value,
        ascending=False,
    )
    return DeliveryListResponse(
        pagination=_pagination_meta(total, limit_value, offset_value),
        deliveries=[_delivery_record(row) for row in rows],
    )


@router.get("/processing/failed", response_model=ProcessingRunListResponse)
def list_failed_processing_runs(limit: str | None = None, offset: str | None = None) -> ProcessingRunListResponse:
    database_url = _require_db_url()
    limit_value, offset_value = _parse_limit_offset(limit, offset)
    rows, total = cq.fetch_processing_runs(
        database_url,
        status="failed",
        limit=limit_value,
        offset=offset_value,
        ascending=False,
    )
    return ProcessingRunListResponse(
        pagination=_pagination_meta(total, limit_value, offset_value),
        processing_runs=[_processing_run_record(row) for row in rows],
    )


@router.get("/rulesets", response_model=RulesetListResponse)
def list_rulesets(
    scope: str | None = None,
    project_id: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
) -> RulesetListResponse:
    database_url = _require_db_url()
    limit_value, offset_value = _parse_limit_offset(limit, offset)
    scope_value = _validated_choice("scope", scope, VALID_SCOPE_VALUES)
    rows, total = cq.fetch_rulesets(
        database_url,
        scope=scope_value,
        project_id=project_id,
        limit=limit_value,
        offset=offset_value,
    )
    return RulesetListResponse(
        pagination=_pagination_meta(total, limit_value, offset_value),
        rulesets=[_ruleset_record(row) for row in rows],
    )


@router.get("/rules", response_model=RuleListResponse)
def list_rules(
    ruleset_id: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
) -> RuleListResponse:
    database_url = _require_db_url()
    limit_value, offset_value = _parse_limit_offset(limit, offset)
    rows, total = cq.fetch_rules(database_url, ruleset_id=ruleset_id, limit=limit_value, offset=offset_value)
    return RuleListResponse(
        pagination=_pagination_meta(total, limit_value, offset_value),
        rules=[_rule_record(row) for row in rows],
    )


@router.get("/dictionary", response_model=DictionaryTermListResponse)
def list_dictionary_terms(
    scope: str | None = None,
    project_id: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
) -> DictionaryTermListResponse:
    database_url = _require_db_url()
    limit_value, offset_value = _parse_limit_offset(limit, offset)
    scope_value = _validated_choice("scope", scope, VALID_SCOPE_VALUES)
    rows, total = cq.fetch_dictionary_terms(
        database_url,
        scope=scope_value,
        project_id=project_id,
        limit=limit_value,
        offset=offset_value,
    )
    return DictionaryTermListResponse(
        pagination=_pagination_meta(total, limit_value, offset_value),
        term_dictionary=[_dictionary_term_record(row) for row in rows],
    )


@router.get("/templates", response_model=PromptTemplateListResponse)
def list_prompt_templates(
    scope: str | None = None,
    project_id: str | None = None,
    prompt_type: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
) -> PromptTemplateListResponse:
    database_url = _require_db_url()
    limit_value, offset_value = _parse_limit_offset(limit, offset)
    scope_value = _validated_choice("scope", scope, VALID_SCOPE_VALUES)
    rows, total = cq.fetch_prompt_templates(
        database_url,
        scope=scope_value,
        project_id=project_id,
        prompt_type=prompt_type,
        limit=limit_value,
        offset=offset_value,
    )
    return PromptTemplateListResponse(
        pagination=_pagination_meta(total, limit_value, offset_value),
        prompt_templates=[_prompt_template_record(row) for row in rows],
    )


@router.get("/targets", response_model=DeliveryTargetListResponse)
def list_delivery_targets(
    type: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
) -> DeliveryTargetListResponse:
    database_url = _require_db_url()
    limit_value, offset_value = _parse_limit_offset(limit, offset)
    type_value = _validated_choice("type", type, VALID_TARGET_TYPES)
    rows, total = cq.fetch_delivery_targets(
        database_url,
        type=type_value,
        limit=limit_value,
        offset=offset_value,
    )
    return DeliveryTargetListResponse(
        pagination=_pagination_meta(total, limit_value, offset_value),
        delivery_targets=[_delivery_target_record(row) for row in rows],
    )


@router.get("/logs", response_model=LogListResponse)
def list_logs(
    level: str | None = None,
    service: str | None = None,
    intake_note_id: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
) -> LogListResponse:
    database_url = _require_db_url()
    limit_value, offset_value = _parse_limit_offset(limit, offset)
    level_value = _validated_choice("level", level, VALID_LOG_LEVELS)
    intake_notes, deliveries, processing_runs = _fetch_log_sources(database_url, intake_note_id)
    logs = _build_log_records(intake_notes, deliveries, processing_runs)
    filtered_logs = _filter_logs(
        logs,
        level=level_value,
        service=service,
        intake_note_id=intake_note_id,
    )
    total = len(filtered_logs)
    page = filtered_logs[offset_value : offset_value + limit_value]
    return LogListResponse(
        pagination=_pagination_meta(total, limit_value, offset_value),
        logs=[_log_record(row) for row in page],
    )


@router.get("/metrics/queue-depth", response_model=QueueDepthResponse)
def queue_depth(
    priority: str | None = None,
    destination: str | None = None,
) -> QueueDepthResponse:
    database_url = _require_db_url()
    priority_value = _validated_choice("priority", priority, VALID_PRIORITY_VALUES)
    destination_value = _validated_choice("destination", destination, VALID_DESTINATIONS)
    row = cq.fetch_queue_depth(database_url, priority=priority_value, destination=destination_value)
    return QueueDepthResponse(
        queue_depth=int(row["queue_depth"]),
        queued_count=int(row["queued_count"]),
        dispatching_count=int(row["dispatching_count"]),
        observed_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/metrics/throughput", response_model=ThroughputSummaryResponse)
def project_throughput(
    project_id: str | None = None,
    window_hours: str | None = None,
) -> ThroughputSummaryResponse:
    database_url = _require_db_url()
    window_hours_value = _parse_int_param("window_hours", window_hours, DEFAULT_WINDOW_HOURS, 1)
    project_slug: str | None = None
    if project_id is not None and project_id != "":
        project_row = cq.fetch_project_by_id(database_url, project_id)
        if not project_row:
            raise HTTPException(status_code=404, detail="project_not_found")
        project_slug = project_row["slug"]
    row, window_start, window_end = cq.fetch_throughput_summary(
        database_url,
        project_id=project_id,
        window_hours=window_hours_value,
    )
    completed_count = int(row["completed_count"])
    failed_count = int(row["failed_count"])
    hours = max(window_hours_value, 1)
    return ThroughputSummaryResponse(
        project_id=project_id or None,
        project_slug=project_slug,
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
        completed_count=completed_count,
        failed_count=failed_count,
        throughput_per_hour=(completed_count + failed_count) / hours,
    )


@router.get("/metrics/sla", response_model=SlaSummaryResponse)
def sla_summary(
    project_id: str | None = None,
    target_seconds: str | None = None,
    window_hours: str | None = None,
) -> SlaSummaryResponse:
    database_url = _require_db_url()
    target_seconds_value = _parse_int_param("target_seconds", target_seconds, DEFAULT_SLA_TARGET_SECONDS, 1)
    window_hours_value = _parse_int_param("window_hours", window_hours, DEFAULT_WINDOW_HOURS, 1)
    project_slug: str | None = None
    if project_id is not None and project_id != "":
        project_row = cq.fetch_project_by_id(database_url, project_id)
        if not project_row:
            raise HTTPException(status_code=404, detail="project_not_found")
        project_slug = project_row["slug"]
    row, window_start, window_end = cq.fetch_sla_summary(
        database_url,
        project_id=project_id,
        target_seconds=target_seconds_value,
        window_hours=window_hours_value,
    )
    on_time_count = int(row["on_time_count"])
    breached_count = int(row["breached_count"])
    total = on_time_count + breached_count
    on_time_rate = (on_time_count / total) if total else 0.0
    return SlaSummaryResponse(
        project_id=project_id or None,
        project_slug=project_slug if project_id else None,
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
        target_seconds=target_seconds_value,
        on_time_count=on_time_count,
        breached_count=breached_count,
        on_time_rate=on_time_rate,
    )


@router.get("/metrics/error-fingerprints", response_model=ErrorFingerprintListResponse)
def error_fingerprints(
    level: str | None = None,
    service: str | None = None,
    intake_note_id: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
) -> ErrorFingerprintListResponse:
    database_url = _require_db_url()
    limit_value, offset_value = _parse_limit_offset(limit, offset)
    level_value = _validated_choice("level", level, VALID_LOG_LEVELS) or "error"
    intake_notes, deliveries, processing_runs = _fetch_log_sources(database_url, intake_note_id)
    logs = _build_log_records(intake_notes, deliveries, processing_runs)
    filtered_logs = _filter_logs(
        logs,
        level=level_value,
        service=service,
        intake_note_id=intake_note_id,
    )
    buckets: dict[str, dict[str, Any]] = {}
    for row in filtered_logs:
        message = str(row.get("message") or "")
        normalized_message = " ".join(message.lower().split())
        fingerprint_seed = f"{row.get('service', '')}|{row.get('level', '')}|{normalized_message}"
        fingerprint = hashlib.sha1(fingerprint_seed.encode("utf-8")).hexdigest()[:16]
        bucket = buckets.setdefault(
            fingerprint,
            {
                "fingerprint": fingerprint,
                "service": row.get("service"),
                "level": row.get("level"),
                "count": 0,
                "first_seen_at": row.get("timestamp"),
                "last_seen_at": row.get("timestamp"),
                "sample_message": row.get("message"),
                "sample_context": {
                    "intake_note_id": row.get("intake_note_id"),
                    "utterance_id": row.get("utterance_id"),
                    "prompt_generation_id": row.get("prompt_generation_id"),
                    "delivery_id": row.get("delivery_id"),
                    "service": row.get("service"),
                },
            },
        )
        bucket["count"] += 1
        timestamp = row.get("timestamp")
        if timestamp < bucket["first_seen_at"]:
            bucket["first_seen_at"] = timestamp
        if timestamp > bucket["last_seen_at"]:
            bucket["last_seen_at"] = timestamp
            bucket["sample_message"] = row.get("message")
            bucket["sample_context"] = {
                "intake_note_id": row.get("intake_note_id"),
                "utterance_id": row.get("utterance_id"),
                "prompt_generation_id": row.get("prompt_generation_id"),
                "delivery_id": row.get("delivery_id"),
                "service": row.get("service"),
            }
    fingerprints = sorted(buckets.values(), key=lambda item: (-int(item["count"]), str(item["last_seen_at"])),)
    total = len(fingerprints)
    page = fingerprints[offset_value : offset_value + limit_value]
    return ErrorFingerprintListResponse(
        pagination=_pagination_meta(total, limit_value, offset_value),
        error_fingerprints=[
            ErrorFingerprintRecord(
                fingerprint=item["fingerprint"],
                service=item.get("service"),
                level=item["level"],
                count=int(item["count"]),
                first_seen_at=_to_iso(item["first_seen_at"]),
                last_seen_at=_to_iso(item["last_seen_at"]),
                sample_message=item.get("sample_message"),
                sample_context=item.get("sample_context") or {},
            )
            for item in page
        ],
    )


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
