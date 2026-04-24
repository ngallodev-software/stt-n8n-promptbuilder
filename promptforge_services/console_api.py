from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlsplit

import psycopg
from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, ValidationError
from psycopg.rows import dict_row

from promptforge_services import console_queries as cq
from promptforge_services.kanban_client import KanbanImportClientError, import_kanban_manifest, list_kanban_workspaces
from promptforge_services.kanban_manifest_builder import (
    KanbanPromptApplyResponse,
    KanbanPromptPreviewResponse,
    KanbanWorkspaceBinding,
    build_kanban_import_manifest,
)
from promptforge_services.console_models import (
    ConsoleRuntimePatchRequest,
    ConsoleRuntimeSettings,
    ConsoleSecretsPatchRequest,
    ConsoleSettingsPermissions,
    ConsoleSettingsResponse,
    DictionaryTermDetailResponse,
    DictionaryTermListResponse,
    DictionaryTermRecord,
    DeliveryDetailResponse,
    DeliveryListResponse,
    DeliveryRecord,
    DeliveryTargetDispatchRequest,
    DeliveryTargetDispatchResponse,
    DeliveryTargetHealthResponse,
    DeliveryStatusRequest,
    DeliveryTargetDetailResponse,
    DeliveryTargetListResponse,
    DeliveryTargetRecord,
    DictionaryUpsertRequest,
    ErrorFingerprintListResponse,
    ErrorFingerprintRecord,
    HealthResponse,
    IntakeNoteDetailResponse,
    IntakeNoteListResponse,
    IntakeNoteRecord,
    KanbanWorkspaceDiscoveryResponse,
    LogListResponse,
    LogRecord,
    NoteLineageResponse,
    PaginatedResponse,
    PaginationMeta,
    ProcessingRunRecord,
    PromptPriorityRequest,
    PurgeArchivedNotesRequest,
    PurgeArchivedNotesResponse,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectRecord,
    PromptDetailResponse,
    PromptGenerationRecord,
    PromptListResponse,
    PromptTemplateCreateRequest,
    PromptTemplateDetailResponse,
    PromptTemplatePatchRequest,
    PromptTemplateListResponse,
    PromptTemplateRecord,
    RuleCreateRequest,
    RuleDryRunDiagnostic,
    RuleDryRunRequest,
    RuleDryRunResponse,
    RuleDryRunSummary,
    QueueDepthResponse,
    RuleDetailResponse,
    RuleListResponse,
    RulePatchRequest,
    RuleRecord,
    RuleSetRecord,
    Scope,
    SecretSettingMetadata,
    RulesetDetailResponse,
    RulesetListResponse,
    SlaSummaryResponse,
    TemplateActivateRequest,
    StrictBaseModel,
    ThroughputSummaryResponse,
    TranscriptRevisionRecord,
    UtteranceRecord,
    WorkflowErrorListResponse,
    WorkflowErrorRecord,
)
from promptforge_services.llm.config import LLMSettings
from promptforge_services.llm.router import get_llm_router
from promptforge_services.delivery_dispatch import DispatchOutcome, compute_target_health, dispatch_target_payload
from promptforge_services.pipeline import llm_providers_health
from promptforge_services.secrets import SecretsEncryptionError, encrypt_secret
from promptforge_watcher.config import WatcherConfig

router = APIRouter(prefix="/console", tags=["console"])

DEFAULT_LIMIT = 100
DEFAULT_OFFSET = 0
VALID_NOTE_STATUSES = {"new", "imported", "processing", "processed", "error", "archived"}
VALID_PROMPT_STATUSES = {"created", "preprocessed", "transforming", "structured_validating", "rendered", "failed"}
VALID_DELIVERY_STATUSES = {"not_started", "queued", "dispatching", "delivered", "acked", "failed"}
VALID_SCOPE_VALUES = {"global", "user", "project"}
VALID_LOG_LEVELS = {"debug", "info", "warn", "error"}
VALID_LOG_SERVICES = {"watcher", "api", "n8n", "postgres"}
VALID_TARGET_TYPES = {"none", "chat_session", "claude_session", "codex_session", "obsidian_note", "generic_queue"}
VALID_PRIORITY_VALUES = {"low", "normal", "high", "urgent"}
VALID_DESTINATIONS = {"chat", "cli", "obsidian_note", "queue_only"}
TERMINAL_DELIVERY_STATUSES = {"delivered", "acked", "failed"}
DEFAULT_WINDOW_HOURS = 24
DEFAULT_SLA_TARGET_SECONDS = 3600
RUNTIME_SETTING_KEYS = (
    "obsidianVaultPath",
    "webhookUrl",
    "llmMode",
    "codexBinary",
    "codexReasoningEffort",
    "openaiBaseUrl",
    "anthropicBaseUrl",
    "kanbanBaseUrl",
    "kanbanWorkspaceId",
)
SECRET_SETTING_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "PROMPTFORGE_OPENAI_COMPAT_API_KEY",
    "PROMPTFORGE_OLLAMA_API_KEY",
)
LOCAL_WEBHOOK_HOSTS = {"localhost", "127.0.0.1", "n8n"}


class ProcessingRunListResponse(PaginatedResponse[ProcessingRunRecord]):
    processing_runs: list[ProcessingRunRecord] = Field(alias="processingRuns")


RequestModelT = TypeVar("RequestModelT", bound=StrictBaseModel)


class DeliveryRerouteRequest(StrictBaseModel):
    targetId: str


class LLMAssistRequest(StrictBaseModel):
    prompt: str
    context_type: str = "general"
    context: dict[str, Any] | None = None


class LLMAssistResponse(StrictBaseModel):
    result: str
    provider: str | None = None
    model: str | None = None
    available: bool = True


def raise_400(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def raise_404(detail: str) -> HTTPException:
    return HTTPException(status_code=404, detail=detail)


def raise_503_db_unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="database_unconfigured")


def raise_503_secrets_unavailable(detail: str = "secrets_encryption_unconfigured") -> HTTPException:
    return HTTPException(status_code=503, detail=detail)


def raise_unsupported(
    code: str,
    message: str,
    *,
    endpoint: str,
    capability: str | None = None,
    machine_status: str = "unsupported",
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> HTTPException:
    detail = {
        "code": code,
        "message": message,
        "status": "unsupported",
        "machine_status": machine_status,
        "retryable": retryable,
        "endpoint": endpoint,
    }
    if capability:
        detail["capability"] = capability
    if details:
        detail["details"] = details
    return HTTPException(status_code=501, detail=detail)


def _db_url() -> str | None:
    return os.getenv("PROMPTFORGE_DATABASE_URL")


def _require_db_url() -> str:
    database_url = _db_url()
    if not database_url:
        raise raise_503_db_unavailable()
    return database_url


def _validate_request(model_cls: type[RequestModelT], payload: Any) -> RequestModelT:
    try:
        return model_cls.model_validate(payload)
    except ValidationError as exc:
        raise raise_400("invalid_request") from exc


def _fetch_all(database_url: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
    except psycopg.OperationalError as exc:
        raise raise_503_db_unavailable() from exc
    return [dict(row) for row in rows]


def _exec(database_url: str, sql: str, params: tuple[Any, ...] = ()) -> int:
    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                count = cur.rowcount
            conn.commit()
    except psycopg.OperationalError as exc:
        raise raise_503_db_unavailable() from exc
    return count


def _to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def _as_str(value: Any) -> str:
    return str(value)


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _normalize_scope(scope: Scope, project_id: str | None) -> tuple[str, str | None]:
    if scope == Scope.PROJECT and not project_id:
        raise raise_400("project_id_required")
    if scope == Scope.GLOBAL and project_id:
        raise raise_400("project_id_not_allowed")
    return scope.value, project_id


def _string_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _default_runtime_settings() -> dict[str, Any]:
    watcher = WatcherConfig()
    llm = LLMSettings.from_env()
    return {
        "obsidianVaultPath": watcher.vault_path,
        "webhookUrl": watcher.webhook_url,
        "llmMode": llm.mode,
        "codexBinary": llm.codex_binary,
        "codexReasoningEffort": llm.codex_reasoning_effort,
        "openaiBaseUrl": llm.openai_base_url or "https://api.openai.com/v1",
        "anthropicBaseUrl": llm.anthropic_base_url or "https://api.anthropic.com",
        "kanbanBaseUrl": watcher.kanban_base_url,
        "kanbanWorkspaceId": watcher.kanban_workspace_id,
        "llmAssistEnabled": False,
    }


def _default_secret_metadata() -> dict[str, dict[str, Any]]:
    llm = LLMSettings.from_env()
    env_values = {
        "OPENAI_API_KEY": llm.openai_api_key,
        "ANTHROPIC_API_KEY": llm.anthropic_api_key,
        "PROMPTFORGE_OPENAI_COMPAT_API_KEY": llm.openai_compat_api_key,
        "PROMPTFORGE_OLLAMA_API_KEY": llm.ollama_api_key,
    }
    return {
        key: {"configured": bool(env_values.get(key)), "last_rotated_at": None}
        for key in SECRET_SETTING_KEYS
    }


def _secret_metadata_from_row(row: dict[str, Any]) -> dict[str, Any]:
    configured = bool(row.get("configured"))
    has_stored_material = bool(row.get("secret_ciphertext")) or bool(row.get("secret_value"))
    return {
        "configured": configured or has_stored_material,
        "last_rotated_at": _to_iso(row.get("last_rotated_at")) if row.get("last_rotated_at") else None,
    }


def _coerce_non_empty_string(name: str, value: Any, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise raise_400(f"invalid_{name}")
    text = value.strip()
    if not text or len(text) > maximum:
        raise raise_400(f"invalid_{name}")
    return text


def _validate_url(name: str, value: Any, *, allow_http: bool = True, allow_local_http: bool = False) -> str:
    text = _coerce_non_empty_string(name, value, maximum=2048)
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise raise_400(f"invalid_{name}")
    if not allow_http and parsed.scheme != "https":
        if not (allow_local_http and parsed.scheme == "http" and parsed.hostname):
            raise raise_400(f"invalid_{name}")
        hostname = parsed.hostname.lower()
        if hostname not in LOCAL_WEBHOOK_HOSTS and "." in hostname:
            raise raise_400(f"invalid_{name}")
    return text


def _validate_optional_url(
    name: str,
    value: Any,
    *,
    allow_http: bool = True,
    allow_local_http: bool = False,
) -> str:
    if not isinstance(value, str):
        raise raise_400(f"invalid_{name}")
    text = value.strip()
    if not text:
        return ""
    return _validate_url(name, text, allow_http=allow_http, allow_local_http=allow_local_http)


def _normalize_runtime_update(runtime_patch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(runtime_patch, dict) or not runtime_patch:
        raise raise_400("invalid_runtime")
    unknown = sorted(set(runtime_patch) - set(RUNTIME_SETTING_KEYS))
    if unknown:
        raise raise_400(f"unknown_runtime_keys:{','.join(unknown)}")
    normalized: dict[str, Any] = {}
    for key, value in runtime_patch.items():
        if key == "obsidianVaultPath":
            text = _coerce_non_empty_string(key, value, maximum=1024)
            if not os.path.isabs(text):
                raise raise_400(f"invalid_{key}")
            normalized[key] = text
        elif key == "webhookUrl":
            normalized[key] = _validate_optional_url(key, value, allow_http=False, allow_local_http=True)
        elif key == "llmMode":
            if value not in {"deterministic_only", "deterministic_plus_review", "llm_inference_optional"}:
                raise raise_400(f"invalid_{key}")
            normalized[key] = value
        elif key == "codexBinary":
            normalized[key] = _coerce_non_empty_string(key, value, maximum=512)
        elif key == "codexReasoningEffort":
            if value not in {"low", "medium", "high"}:
                raise raise_400(f"invalid_{key}")
            normalized[key] = value
        elif key in {"openaiBaseUrl", "anthropicBaseUrl", "kanbanBaseUrl"}:
            normalized[key] = _validate_url(key, value, allow_http=True)
        elif key == "kanbanWorkspaceId":
            normalized[key] = _coerce_non_empty_string(key, value, maximum=256)
    return normalized


def _normalize_secret_update(secrets_patch: dict[str, Any]) -> dict[str, str]:
    if not isinstance(secrets_patch, dict) or not secrets_patch:
        raise raise_400("invalid_secrets")
    unknown = sorted(set(secrets_patch) - set(SECRET_SETTING_KEYS))
    if unknown:
        raise raise_400(f"unknown_secret_keys:{','.join(unknown)}")
    normalized: dict[str, str] = {}
    for key, value in secrets_patch.items():
        if not isinstance(value, str) or not value.strip():
            raise raise_400(f"invalid_{key}")
        normalized[key] = value.strip()
    return normalized


def _settings_tables_exist(database_url: str) -> bool:
    rows = _fetch_all(
        database_url,
        """
        SELECT
            to_regclass('console_runtime_settings') IS NOT NULL AS runtime_exists
        """,
    )
    if not rows:
        return False
    row = rows[0]
    return bool(row.get("runtime_exists"))


def _ensure_settings_tables(database_url: str) -> None:
    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
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
                    """
                )
                cur.execute(
                    """
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
                    """
                )
            conn.commit()
    except psycopg.Error as exc:
        raise raise_503_db_unavailable() from exc


def _validate_project_scope(database_url: str, scope: str, project_id: str | None) -> None:
    if scope == Scope.PROJECT.value and project_id:
        _fetch_project_row(database_url, project_id)


def _safe_fetch_settings_rows(
    database_url: str,
    *,
    scope: str,
    project_id: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not _settings_tables_exist(database_url):
        return [], []
    try:
        runtime_rows = _fetch_all(
            database_url,
            """
            SELECT key, value_json, updated_at
            FROM console_runtime_settings
            WHERE scope = %s::pf_scope AND project_id IS NOT DISTINCT FROM %s
            ORDER BY key ASC
            """,
            (scope, project_id),
        )
    except psycopg.Error:
        return [], []
    return runtime_rows, []


def _build_settings_payload(
    *,
    request: Request | None,
    scope: str = Scope.GLOBAL.value,
    project_id: str | None = None,
    database_url: str | None = None,
) -> ConsoleSettingsResponse:
    runtime_values = _default_runtime_settings()
    secret_values = _default_secret_metadata()
    updated_candidates: list[datetime] = [datetime.now(timezone.utc)]

    if database_url:
        _validate_project_scope(database_url, scope, project_id)
        runtime_rows, secret_rows = _safe_fetch_settings_rows(
            database_url,
            scope=scope,
            project_id=project_id,
        )
        for row in runtime_rows:
            key = str(row["key"])
            if key in runtime_values:
                if key == "webhookUrl" and row["value_json"] == "":
                    continue
                runtime_values[key] = row["value_json"]
                if isinstance(row.get("updated_at"), datetime):
                    updated_candidates.append(row["updated_at"])
        for row in secret_rows:
            key = str(row["key"])
            if key in secret_values:
                secret_values[key] = _secret_metadata_from_row(row)
                if isinstance(row.get("updated_at"), datetime):
                    updated_candidates.append(row["updated_at"])

    latest_updated = max(updated_candidates).astimezone(timezone.utc).isoformat()
    return ConsoleSettingsResponse(
        scope=Scope(scope),
        project_id=project_id,
        runtime=ConsoleRuntimeSettings.model_validate(runtime_values),
        secrets={key: SecretSettingMetadata.model_validate(value) for key, value in secret_values.items()},
        permissions=ConsoleSettingsPermissions(
            can_update_runtime=True,
            can_rotate_secrets=True,
            can_purge_archived_notes=True,
        ),
        updated_at=latest_updated,
    )


def _audit_log(
    database_url: str,
    *,
    action: str,
    actor: str,
    scope: str | None = None,
    project_id: str | None = None,
    payload: dict[str, Any],
) -> None:
    pass


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


def _empty_bootstrap(request: Request | None = None) -> dict[str, Any]:
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
        "settings": _build_settings_payload(request=request).model_dump(mode="json"),
        "healthSnapshot": {
            "api": {"status": "degraded", "latency_ms": 0, "checked_at": datetime.now(timezone.utc).isoformat()},
            "providers": [],
            "db": {"status": "degraded", "latency_ms": 0},
            "queue_depth": 0,
            "failures_24h": 0,
        },
    }


def _console_bootstrap_payload(request: Request | None = None) -> dict[str, Any]:
    database_url = _db_url()
    if not database_url:
        return _empty_bootstrap(request=request)

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
        "settings": _build_settings_payload(
            request=request,
            scope=Scope.GLOBAL.value,
            project_id=None,
            database_url=database_url,
        ).model_dump(mode="json"),
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


def console_bootstrap() -> dict[str, Any]:
    return _console_bootstrap_payload()


@router.get("/bootstrap")
def console_bootstrap_endpoint(request: Request) -> dict[str, Any]:
    return _console_bootstrap_payload(request=request)


def _check_db_health(database_url: str | None) -> str:
    if not database_url:
        return "error"
    try:
        with psycopg.connect(database_url) as conn:  # type: ignore
            with conn.cursor() as cur:
                cur.execute("SELECT 1")  # type: ignore
        return "ok"
    except Exception:
        return "error"


def _check_vault_health() -> str:
    vault_path = os.getenv("PROMPTFORGE_VAULT_PATH", "/vault")
    try:
        return "ok" if Path(vault_path).exists() else "error"
    except Exception:
        return "error"


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    database_url = _db_url()
    return HealthResponse(
        db=_check_db_health(database_url),  # type: ignore
        vault=_check_vault_health(),  # type: ignore
        watcher="unknown",
    )


@router.get("/settings", response_model=ConsoleSettingsResponse)
def get_console_settings(
    request: Request,
    scope: str | None = None,
    project_id: str | None = None,
) -> ConsoleSettingsResponse:
    scope_value = _validated_choice("scope", scope, {"global", "project"}) or Scope.GLOBAL.value
    normalized_scope, normalized_project_id = _normalize_scope(Scope(scope_value), project_id)
    return _build_settings_payload(
        request=request,
        scope=normalized_scope,
        project_id=normalized_project_id,
        database_url=_db_url(),
    )


@router.patch("/settings/runtime", response_model=ConsoleSettingsResponse)
def patch_console_runtime_settings(
    payload: ConsoleRuntimePatchRequest,
    request: Request,
) -> ConsoleSettingsResponse:
    actor = "system:console"
    database_url = _require_db_url()
    scope_value, project_value = _normalize_scope(payload.scope, payload.project_id)
    _validate_project_scope(database_url, scope_value, project_value)
    if not _settings_tables_exist(database_url):
        _ensure_settings_tables(database_url)
    normalized = _normalize_runtime_update(payload.runtime)

    previous_rows = _safe_fetch_settings_rows(
        database_url,
        scope=scope_value,
        project_id=project_value,
    )[0]
    previous_map = {str(row["key"]): row["value_json"] for row in previous_rows}

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                for key, value in normalized.items():
                    if key == "webhookUrl" and value == "":
                        cur.execute(
                            """
                            DELETE FROM console_runtime_settings
                            WHERE scope = %s::pf_scope
                              AND project_id IS NOT DISTINCT FROM %s
                              AND key = %s
                            """,
                            (scope_value, project_value, key),
                        )
                        continue
                    cur.execute(
                        """
                        UPDATE console_runtime_settings
                        SET value_json = %s::jsonb,
                            updated_by_user_id = %s,
                            updated_at = now()
                        WHERE scope = %s::pf_scope
                          AND project_id IS NOT DISTINCT FROM %s
                          AND key = %s
                        """,
                        (json.dumps(value), actor, scope_value, project_value, key),
                    )
                    if cur.rowcount == 0:
                        cur.execute(
                            """
                            INSERT INTO console_runtime_settings (
                                scope, project_id, key, value_json, updated_by_user_id
                            ) VALUES (%s::pf_scope, %s, %s, %s::jsonb, %s)
                            """,
                            (scope_value, project_value, key, json.dumps(value), actor),
                        )
            conn.commit()
    except psycopg.OperationalError as exc:
        raise raise_503_db_unavailable() from exc

    _audit_log(
        database_url,
        action="runtime_settings_updated",
        actor=actor,
        scope=scope_value,
        project_id=project_value,
        payload={
            "scope": scope_value,
            "project_id": project_value,
            "keys_changed": sorted(normalized),
            "changes": {
                key: {
                    "previous_hash": _string_hash(previous_map.get(key)),
                    "result_hash": _string_hash(value),
                }
                for key, value in normalized.items()
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    return _build_settings_payload(
        request=request,
        scope=scope_value,
        project_id=project_value,
        database_url=database_url,
    )


@router.get("/kanban/workspaces", response_model=KanbanWorkspaceDiscoveryResponse)
def discover_kanban_workspaces(base_url: str) -> KanbanWorkspaceDiscoveryResponse:
    normalized_base_url = _validate_url("kanbanBaseUrl", base_url, allow_http=True)
    try:
        return list_kanban_workspaces(kanban_base_url=normalized_base_url)
    except KanbanImportClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc




def _parse_int_param(name: str, value: str | None, default: int, minimum: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise raise_400(f"invalid_{name}")
    if parsed < minimum:
        raise raise_400(f"invalid_{name}")
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
        raise raise_400(f"invalid_{name}")
    return value


def _delivery_transition_allowed(current_status: str, requested_status: str) -> bool:
    allowed_transitions = {
        "not_started": {"queued", "failed"},
        "queued": {"queued", "dispatching", "failed"},
        "dispatching": {"delivered", "acked", "failed"},
        "delivered": {"acked"},
        "acked": set(),
        "failed": set(),
    }
    return requested_status in allowed_transitions.get(current_status, set())


def _terminal_mutation_locked(status: str, destination: str) -> bool:
    return status in TERMINAL_DELIVERY_STATUSES and destination != "queue_only"


def _pagination_meta(total: int, limit: int, offset: int) -> PaginationMeta:
    return PaginationMeta(total=total, limit=limit, offset=offset, has_more=offset + limit < total)


def _paginated_response(response_cls: Any, field_name: str, items: list[Any], total: int, limit: int, offset: int) -> Any:
    return response_cls(pagination=_pagination_meta(total, limit, offset), **{field_name: items})


def _where_sql(clauses: list[str]) -> str:
    return " WHERE " + " AND ".join(clauses) if clauses else ""


def _project_record(row: dict[str, Any]) -> ProjectRecord:
    return ProjectRecord(
        id=_as_str(row["id"]),
        name=row["name"],
        slug=row["slug"],
        description=row.get("description"),
        created_at=_to_iso(row["created_at"]),
        updated_at=_to_iso(row["updated_at"]),
    )


def _intake_note_record(row: dict[str, Any]) -> IntakeNoteRecord:
    return IntakeNoteRecord(
        id=_as_str(row["id"]),
        project_id=_as_optional_str(row.get("project_id")),
        note_relative_path=row["note_relative_path"],
        status=row["status"],
        watch_eligible=bool(row["watch_eligible"]),
        source_device=row.get("source_device") or "",
        body_text=row.get("body_text") or "",
        frontmatter_original=row.get("frontmatter_original") or {},
        frontmatter_current=row.get("frontmatter_current") or {},
        metadata_json=row.get("metadata_json") or {},
        created_at=_to_iso(row["created_at"]),
        updated_at=_to_iso(row["updated_at"]),
    )


def _utterance_record(row: dict[str, Any]) -> UtteranceRecord:
    return UtteranceRecord(
        id=_as_str(row["id"]),
        intake_note_id=_as_str(row["intake_note_id"]),
        raw_text=row["raw_text"],
        directive_text=row.get("directive_text"),
        project_id=_as_optional_str(row.get("project_id")),
        scope=row["scope"],
        capture_type=row["capture_type"],
        created_at=_to_iso(row["created_at"]),
    )


def _transcript_revision_record(row: dict[str, Any]) -> TranscriptRevisionRecord:
    return TranscriptRevisionRecord(
        id=_as_str(row["id"]),
        utterance_id=_as_str(row["utterance_id"]),
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
        id=_as_str(row["id"]),
        intake_note_id=_as_str(row["intake_note_id"]),
        status=row["status"],
        requires_review=bool(row["requires_review"]),
        prompt_type=row["prompt_type"],
        ruleset_id=_as_optional_str(row.get("ruleset_id")),
        template_id=_as_optional_str(row.get("template_id")),
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
        id=_as_str(row["id"]),
        prompt_generation_id=_as_str(row["prompt_generation_id"]),
        target_id=_as_optional_str(row.get("target_id")),
        session_identifier=_as_optional_str(row.get("session_identifier")),
        status=row["status"],
        destination=row["destination"],
        mode=row["mode"],
        priority=row["priority"],
        retry_count=int(row.get("retry_count") or 0),
        dispatch_request_json=row.get("dispatch_request_json") or {},
        dispatch_response_json=row.get("dispatch_response_json") or {},
        failure_text=row.get("failure_text"),
        ack_text=row.get("ack_text"),
        created_at=_to_iso(row["created_at"]),
        updated_at=_to_iso(row["updated_at"]),
    )


def _processing_run_record(row: dict[str, Any]) -> ProcessingRunRecord:
    return ProcessingRunRecord(
        id=_as_str(row["id"]),
        intake_note_id=_as_str(row["intake_note_id"]),
        status=row["status"],
        stage_name=row["stage_name"],
        error_text=row.get("error_text"),
        trace_json=row.get("trace_json") or {},
        created_at=_to_iso(row["created_at"]),
        updated_at=_to_iso(row["updated_at"]),
    )


def _ruleset_record(row: dict[str, Any]) -> RuleSetRecord:
    return RuleSetRecord(
        id=_as_str(row["id"]),
        name=row["name"],
        scope=row["scope"],
        project_id=_as_optional_str(row.get("project_id")),
        active=bool(row["active"]),
        description=row.get("description"),
        updated_at=_to_iso(row["updated_at"]),
    )


def _rule_record(row: dict[str, Any]) -> RuleRecord:
    return RuleRecord(
        id=_as_str(row["id"]),
        ruleset_id=_as_str(row["ruleset_id"]),
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
        id=_as_str(row["id"]),
        scope=row["scope"],
        project_id=_as_optional_str(row.get("project_id")),
        source_term=row["source_term"],
        normalized_term=row["normalized_term"],
        description=row.get("description"),
        created_at=_to_iso(row["created_at"]),
        updated_at=_to_iso(row["updated_at"]),
    )


def _prompt_template_record(row: dict[str, Any]) -> PromptTemplateRecord:
    return PromptTemplateRecord(
        id=_as_str(row["id"]),
        name=row["name"],
        prompt_type=row["prompt_type"],
        scope=row["scope"],
        project_id=_as_optional_str(row.get("project_id")),
        version=int(row["version"]),
        is_active=bool(row["is_active"]),
        template_family_key=row["template_family_key"],
        body=row["body"],
        updated_at=_to_iso(row["updated_at"]),
    )


def _delivery_target_record(row: dict[str, Any]) -> DeliveryTargetRecord:
    health = compute_target_health(row)
    return DeliveryTargetRecord(
        id=_as_str(row["id"]),
        name=row["name"],
        target_type=row["target_type"],
        target_identifier=row["target_identifier"],
        destination=row["destination"],
        scope=row["scope"],
        project_id=_as_optional_str(row.get("project_id")),
        enabled=bool(row["enabled"]),
        is_sensitive=bool(row["is_sensitive"]),
        requires_confirmation=bool(row["requires_confirmation"]),
        environment=row["environment"],
        validation_status=health.status,
        validation_detail=health.detail,
        updated_at=_to_iso(row["updated_at"]),
    )


def _raise_delivery_schema_dependency(exc: Exception) -> None:
    if isinstance(exc, psycopg.Error):
        sqlstate = getattr(exc, "sqlstate", None)
        if sqlstate in {"42703", "42P01"}:
            diag = getattr(exc, "diag", None)
            column_name = getattr(diag, "column_name", None)
            table_name = getattr(diag, "table_name", None)
            if column_name:
                detail = f"delivery_dispatch_schema_dependency_missing:deliveries.{column_name}"
            elif table_name:
                detail = f"delivery_dispatch_schema_dependency_missing:{table_name}"
            else:
                detail = "delivery_dispatch_schema_dependency_missing:deliveries.dispatch_columns"
            raise HTTPException(status_code=503, detail=detail) from exc
    raise exc


def _fetch_ruleset_row(database_url: str, ruleset_id: str) -> dict[str, Any] | None:
    rows = _fetch_all(
        database_url,
        """
        SELECT
            id,
            name,
            scope::text AS scope,
            project_id,
            version,
            is_active AS active,
            description,
            created_at AS updated_at
        FROM rulesets
        WHERE id = %s
        LIMIT 1
        """,
        (ruleset_id,),
    )
    return rows[0] if rows else None


def _fetch_rule_row(database_url: str, rule_id: str) -> dict[str, Any] | None:
    rows = _fetch_all(
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
        WHERE id = %s
        LIMIT 1
        """,
        (rule_id,),
    )
    return rows[0] if rows else None


def _fetch_prompt_template_row(database_url: str, template_id: str) -> dict[str, Any] | None:
    rows = _fetch_all(
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
        WHERE id = %s
        LIMIT 1
        """,
        (template_id,),
    )
    return rows[0] if rows else None


def _fetch_delivery_target_row(database_url: str, target_id: str) -> dict[str, Any] | None:
    return cq.fetch_delivery_target_by_id(database_url, target_id)


def _fetch_prompt_generation_row(database_url: str, prompt_generation_id: str) -> dict[str, Any] | None:
    return cq.fetch_prompt_generation_by_id(database_url, prompt_generation_id)


def _build_kanban_binding_for_prompt(
    *,
    database_url: str,
    project_id: str | None,
) -> KanbanWorkspaceBinding:
    if not project_id:
        raise raise_400("prompt_generation_project_scope_required")
    settings = _build_settings_payload(
        request=None,
        scope=Scope.PROJECT.value,
        project_id=project_id,
        database_url=database_url,
    )
    return KanbanWorkspaceBinding.model_validate(settings.runtime.model_dump())


def _build_prompt_generation_kanban_preview(
    *,
    database_url: str,
    prompt_generation_id: str,
) -> KanbanPromptPreviewResponse:
    row = _fetch_prompt_generation_row(database_url, prompt_generation_id)
    if not row:
        raise raise_404("prompt_generation_not_found")
    record = _prompt_generation_record(row)
    binding = _build_kanban_binding_for_prompt(
        database_url=database_url,
        project_id=_as_optional_str(row.get("project_id")),
    )
    build = build_kanban_import_manifest(record, binding)
    return KanbanPromptPreviewResponse(
        promptGenerationId=record.id,
        projectId=_as_optional_str(row.get("project_id")),
        sourceStatus=record.status,
        kanbanBaseUrl=binding.kanban_base_url,
        kanbanWorkspaceId=binding.kanban_workspace_id,
        build=build,
    )


def _fetch_delivery_row(database_url: str, delivery_id: str) -> dict[str, Any] | None:
    rows = _fetch_all(
        database_url,
        """
        SELECT
            id,
            prompt_generation_id,
            delivery_target_id AS target_id,
            session_identifier,
            status::text AS status,
            destination::text AS destination,
            mode::text AS mode,
            priority::text AS priority,
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
            COALESCE(dispatch_request_json, '{}'::jsonb) AS dispatch_request_json,
            COALESCE(dispatch_response_json, '{}'::jsonb) AS dispatch_response_json,
            error_text AS failure_text,
            NULL::text AS ack_text,
            created_at,
            COALESCE(acked_at, dispatched_at, queued_at, created_at) AS updated_at
        FROM deliveries d
        WHERE id = %s
        LIMIT 1
        """,
        (delivery_id,),
    )
    return rows[0] if rows else None


def _delivery_dispatch_response(
    *,
    delivery_row: dict[str, Any],
    target_row: dict[str, Any],
    outcome: DispatchOutcome,
    requested_at: str,
) -> DeliveryTargetDispatchResponse:
    return DeliveryTargetDispatchResponse(
        deliveryId=_as_str(delivery_row["id"]),
        targetId=_as_str(target_row["id"]),
        targetType=target_row["target_type"],
        accepted=outcome.accepted,
        status=outcome.status,
        machineStatus=outcome.response_summary.get("machine_status", outcome.status),
        externalIdentifier=outcome.external_identifier,
        sessionIdentifier=outcome.session_identifier,
        promptGenerationId=_as_optional_str(delivery_row.get("prompt_generation_id")),
        requestedAt=requested_at,
        dispatchedAt=_to_iso(delivery_row.get("dispatched_at")) if delivery_row.get("dispatched_at") else None,
        updatedAt=_to_iso(delivery_row.get("updated_at")),
        retryCount=int(delivery_row.get("retry_count") or 0),
        warnings=outcome.warnings,
        errorText=outcome.error_text,
        requestSummary=outcome.request_summary,
        responseSummary=outcome.response_summary,
    )


def _delivery_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _as_str(row["id"]),
        "prompt_generation_id": _as_str(row["prompt_generation_id"]),
        "target_id": _as_optional_str(row.get("target_id")),
        "session_identifier": _as_optional_str(row.get("session_identifier")),
        "status": row["status"],
        "destination": row["destination"],
        "mode": row["mode"],
        "priority": row["priority"],
        "retry_count": int(row.get("retry_count") or 0),
        "dispatch_request_json": row.get("dispatch_request_json") or {},
        "dispatch_response_json": row.get("dispatch_response_json") or {},
        "failure_text": row.get("failure_text"),
        "ack_text": row.get("ack_text"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "dispatched_at": row.get("dispatched_at"),
    }


def _create_delivery_attempt(
    database_url: str,
    *,
    target_row: dict[str, Any],
    prompt_generation_row: dict[str, Any] | None,
    payload_content: str,
    request: DeliveryTargetDispatchRequest,
) -> dict[str, Any]:
    destination = _as_str(
        (prompt_generation_row or {}).get("destination")
        or target_row.get("destination")
        or "queue_only"
    )
    mode = request.mode.value if hasattr(request.mode, "value") else (request.mode or (prompt_generation_row or {}).get("mode") or "queue")
    priority = request.priority.value if hasattr(request.priority, "value") else (request.priority or (prompt_generation_row or {}).get("priority") or "normal")
    delivery_target_id = _as_optional_str(target_row.get("id"))
    prompt_generation_id = _as_optional_str((prompt_generation_row or {}).get("id"))
    request_json = {
        "target_id": delivery_target_id,
        "prompt_generation_id": prompt_generation_id,
        "payload_content": payload_content[:1000],
        "target_session_identifier": request.target_session_identifier,
        "priority": priority,
        "mode": mode,
        "environment": request.environment,
        "dry_run": request.dry_run,
    }
    try:
        inserted = _fetch_all(
            database_url,
            """
            INSERT INTO deliveries (
                prompt_generation_id,
                delivery_target_id,
                destination,
                target_type,
                target_identifier,
                mode,
                status,
                priority,
                queued_at,
                session_identifier,
                dispatch_request_json
            ) VALUES (
                %s,
                %s,
                %s::pf_destination,
                %s::pf_target_type,
                %s,
                %s::pf_delivery_mode,
                'dispatching'::pf_delivery_status,
                %s::pf_priority,
                now(),
                %s,
                %s::jsonb
            )
            RETURNING id
            """,
            (
                prompt_generation_id,
                delivery_target_id,
                destination,
                target_row["target_type"],
                target_row["target_identifier"],
                mode,
                priority,
                request.target_session_identifier,
                json.dumps(request_json),
            ),
        )
    except Exception as exc:
        _raise_delivery_schema_dependency(exc)
        raise
    if not inserted:
        raise raise_503_db_unavailable()
    delivery_row = _fetch_delivery_row(database_url, _as_str(inserted[0]["id"]))
    if not delivery_row:
        raise raise_503_db_unavailable()
    return delivery_row


def _update_delivery_attempt(
    database_url: str,
    *,
    delivery_id: str,
    status: str,
    mode: str | None,
    priority: str | None,
    session_identifier: str | None,
    request_json: dict[str, Any],
    response_json: dict[str, Any],
    error_text: str | None = None,
) -> dict[str, Any]:
    queued_clause = "queued_at = now()," if status == "queued" else ""
    dispatched_clause = "dispatched_at = now()," if status in {"delivered", "acked", "failed"} else ""
    try:
        rows = _fetch_all(
            database_url,
            f"""
            UPDATE deliveries
            SET status = %s::pf_delivery_status,
                mode = COALESCE(%s::pf_delivery_mode, mode),
                priority = COALESCE(%s::pf_priority, priority),
                session_identifier = %s,
                dispatch_request_json = %s::jsonb,
                dispatch_response_json = %s::jsonb,
                {queued_clause}
                {dispatched_clause}
                error_text = %s
            WHERE id = %s
            RETURNING
                id,
                prompt_generation_id,
                delivery_target_id AS target_id,
                session_identifier,
                status::text AS status,
                destination::text AS destination,
                mode::text AS mode,
                priority::text AS priority,
                GREATEST(
                    0,
                    (
                        SELECT COUNT(*)::int - 1
                        FROM deliveries d2
                        WHERE d2.prompt_generation_id = deliveries.prompt_generation_id
                          AND d2.created_at <= deliveries.created_at
                          AND d2.status = 'failed'
                    )
                ) AS retry_count,
                COALESCE(dispatch_request_json, '{{}}'::jsonb) AS dispatch_request_json,
                COALESCE(dispatch_response_json, '{{}}'::jsonb) AS dispatch_response_json,
                error_text AS failure_text,
                NULL::text AS ack_text,
                created_at,
                COALESCE(dispatched_at, queued_at, created_at) AS updated_at,
                dispatched_at
            """,
            (
                status,
                mode,
                priority,
                session_identifier,
                json.dumps(request_json),
                json.dumps(response_json),
                error_text,
                delivery_id,
            ),
        )
    except Exception as exc:
        _raise_delivery_schema_dependency(exc)
        raise
    if not rows:
        raise raise_404("delivery_not_found")
    return _delivery_from_row(rows[0])


def _dispatch_delivery_attempt(
    database_url: str,
    *,
    delivery_row: dict[str, Any],
    target_row: dict[str, Any],
    request: DeliveryTargetDispatchRequest,
    payload_content: str,
    dry_run: bool,
) -> DeliveryTargetDispatchResponse:
    requested_at = datetime.now(timezone.utc).isoformat()
    outcome = dispatch_target_payload(
        target_row=target_row,
        payload_content=payload_content,
        prompt_generation_id=_as_optional_str(delivery_row.get("prompt_generation_id")),
        delivery_id=_as_str(delivery_row["id"]),
        target_session_identifier=request.target_session_identifier,
        dry_run=dry_run,
    )
    if dry_run:
        return _delivery_dispatch_response(
            delivery_row=delivery_row,
            target_row=target_row,
            outcome=outcome,
            requested_at=requested_at,
        )

    updated = _update_delivery_attempt(
        database_url,
        delivery_id=_as_str(delivery_row["id"]),
        status=outcome.status,
        session_identifier=outcome.session_identifier or request.target_session_identifier,
        request_json=outcome.request_summary,
        response_json=outcome.response_summary,
        error_text=outcome.error_text,
    )
    return _delivery_dispatch_response(
        delivery_row=updated,
        target_row=target_row,
        outcome=outcome,
        requested_at=requested_at,
    )


def _normalized_json_mapping(name: str, value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise raise_400(f"invalid_{name}")
    return value


def _is_empty_context_value(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _apply_rule_actions(sample_text: str, action_json: dict[str, Any]) -> tuple[str, dict[str, Any], list[str]]:
    output = sample_text
    warnings: list[str] = []
    applied_actions: list[str] = []
    metadata_changes: dict[str, Any] = {}

    def _mark_action(name: str, changed: bool) -> None:
        applied_actions.append(name)
        if changed:
            metadata_changes.setdefault("text_actions", []).append(name)

    if action_json.get("remove_leading_fillers"):
        new_output = re.sub(
            r"^(?:\s*(?:um|uh|erm|like|so|well|okay|you know)\b[\s,.\-]*)+",
            "",
            output,
            flags=re.IGNORECASE,
        )
        _mark_action("remove_leading_fillers", new_output != output)
        output = new_output

    if action_json.get("collapse_spaces"):
        new_output = re.sub(r"[ \t]+", " ", output)
        new_output = re.sub(r"\n[ \t]+", "\n", new_output)
        new_output = re.sub(r"[ \t]+\n", "\n", new_output)
        new_output = new_output.strip()
        _mark_action("collapse_spaces", new_output != output)
        output = new_output

    if action_json.get("normalize_punctuation"):
        new_output = re.sub(r"\s+([,.;:!?])", r"\1", output)
        new_output = re.sub(r"([,.;:!?])([^\s\n])", r"\1 \2", new_output)
        new_output = re.sub(r"\s+", " ", new_output).strip()
        _mark_action("normalize_punctuation", new_output != output)
        output = new_output

    if action_json.get("markdown_normalize"):
        new_output = re.sub(r"\r\n?", "\n", output)
        new_output = re.sub(r"[ \t]+\n", "\n", new_output)
        new_output = re.sub(r"\n{3,}", "\n\n", new_output)
        _mark_action("markdown_normalize", new_output != output)
        output = new_output

    if action_json.get("trim_trailing_whitespace"):
        new_output = re.sub(r"[ \t]+$", "", output, flags=re.MULTILINE)
        _mark_action("trim_trailing_whitespace", new_output != output)
        output = new_output

    replace_terms = action_json.get("replace_terms")
    if isinstance(replace_terms, dict):
        replacements = sorted(replace_terms.items(), key=lambda item: len(str(item[0])), reverse=True)
        new_output = output
        for source, target in replacements:
            if not isinstance(source, str) or not isinstance(target, str):
                warnings.append("invalid_replace_terms_entry")
                continue
            new_output = re.sub(re.escape(source), target, new_output, flags=re.IGNORECASE)
        _mark_action("replace_terms", new_output != output)
        output = new_output
    elif replace_terms is not None:
        warnings.append("unsupported_action:replace_terms")

    for key in ("default_destination", "default_target_type", "default_target_identifier", "default_mode"):
        if key in action_json:
            metadata_changes[key] = action_json[key]
            applied_actions.append(key)

    preserve_terms = action_json.get("preserve_terms")
    if preserve_terms is not None:
        if isinstance(preserve_terms, list):
            metadata_changes["preserve_terms"] = preserve_terms
            applied_actions.append("preserve_terms")
        else:
            warnings.append("unsupported_action:preserve_terms")

    for key in sorted(set(action_json) - {"remove_leading_fillers", "collapse_spaces", "normalize_punctuation", "markdown_normalize", "trim_trailing_whitespace", "replace_terms", "default_destination", "default_target_type", "default_target_identifier", "default_mode", "preserve_terms"}):
        warnings.append(f"unsupported_action:{key}")

    effect_summary = {
        "text_changed": output != sample_text,
        "applied_actions": applied_actions,
        "metadata_changes": metadata_changes,
    }
    return output, effect_summary, warnings


def _rule_matches_dry_run(
    row: dict[str, Any],
    *,
    sample_text: str,
    context: dict[str, Any],
) -> tuple[bool, str | None, list[str]]:
    conditions = row.get("pattern")
    if isinstance(conditions, str) and conditions:
        try:
            conditions_json = json.loads(conditions)
        except json.JSONDecodeError:
            return False, "invalid_conditions_json", ["invalid_conditions_json"]
    elif isinstance(conditions, dict):
        conditions_json = conditions
    else:
        conditions_json = {}

    warnings: list[str] = []
    for key, value in conditions_json.items():
        if key in {"stage", "project_slug", "prompt_type", "destination", "target_identifier", "mode", "priority", "applies_to"}:
            ctx_value = context.get(key)
            if _is_empty_context_value(ctx_value):
                warnings.append(f"unverified_condition:{key}")
                continue
            if str(ctx_value) != str(value):
                return False, f"condition_mismatch:{key}", warnings
            continue

        if key == "field":
            field_name = str(value).strip()
            if not field_name:
                warnings.append("invalid_condition:field")
                continue
            if bool(conditions_json.get("when_missing")):
                if not _is_empty_context_value(context.get(field_name)):
                    return False, f"condition_mismatch:{field_name}_present", warnings
                continue
            expected = conditions_json.get("value")
            if expected is None:
                warnings.append("unsupported_condition:field_value_missing")
                continue
            ctx_value = context.get(field_name)
            if _is_empty_context_value(ctx_value):
                warnings.append(f"unverified_condition:{field_name}")
                continue
            if str(ctx_value) != str(expected):
                return False, f"condition_mismatch:{field_name}", warnings
            continue

        if key == "contains":
            patterns = value if isinstance(value, list) else [value]
            for pattern in patterns:
                if not isinstance(pattern, str):
                    warnings.append("invalid_condition:contains")
                    continue
                if pattern not in sample_text:
                    return False, "condition_mismatch:contains", warnings
            continue

        if key == "not_contains":
            patterns = value if isinstance(value, list) else [value]
            for pattern in patterns:
                if not isinstance(pattern, str):
                    warnings.append("invalid_condition:not_contains")
                    continue
                if pattern in sample_text:
                    return False, "condition_mismatch:not_contains", warnings
            continue

        if key == "regex":
            if not isinstance(value, str) or not value.strip():
                warnings.append("invalid_condition:regex")
                continue
            try:
                if not re.search(value, sample_text, flags=re.IGNORECASE | re.MULTILINE):
                    return False, "condition_mismatch:regex", warnings
            except re.error:
                return False, "invalid_condition:regex", warnings + ["invalid_condition:regex"]
            continue

        if key in {"when_missing", "value"}:
            continue

        warnings.append(f"unsupported_condition:{key}")

    return True, None, warnings


def _rule_dry_run_payload(
    *,
    database_url: str,
    ruleset_id: str,
    request: RuleDryRunRequest,
) -> RuleDryRunResponse:
    ruleset_row = _fetch_ruleset_row(database_url, ruleset_id)
    if not ruleset_row:
        raise raise_404("ruleset_not_found")

    rows, _ = cq.fetch_rules(database_url, ruleset_id=ruleset_id, limit=5000, offset=0)
    current_output = request.sample_text
    matched: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    warnings: set[str] = set()
    metadata: dict[str, Any] = {
        "ruleset_id": _as_str(ruleset_row["id"]),
        "ruleset_name": ruleset_row["name"],
        "scope": ruleset_row["scope"],
        "project_id": _as_optional_str(ruleset_row.get("project_id")),
        "input_length": len(request.sample_text),
    }

    for row in rows:
        diagnostic_base = {
            "rule_id": _as_str(row["id"]),
            "ruleset_id": _as_str(row["ruleset_id"]),
            "name": row["name"],
            "rule_type": row["rule_type"],
            "priority": int(row["priority"]),
            "enabled": bool(row["enabled"]),
            "input_text": current_output,
            "output_text": current_output,
            "matched": False,
            "applied": False,
            "skipped_reason": None,
            "warnings": [],
            "effect_summary": {},
        }

        if not bool(row["enabled"]):
            diagnostic_base["skipped_reason"] = "disabled"
            skipped.append(diagnostic_base)
            continue

        try:
            matched_rule, skipped_reason, rule_warnings = _rule_matches_dry_run(
                row,
                sample_text=current_output,
                context=request.context,
            )
            diagnostic_base["warnings"] = rule_warnings
            warnings.update(rule_warnings)
            if not matched_rule:
                diagnostic_base["skipped_reason"] = skipped_reason or "not_matched"
                skipped.append(diagnostic_base)
                continue

            action_json = row.get("replacement")
            if isinstance(action_json, str) and action_json:
                try:
                    action_json_value = json.loads(action_json)
                except json.JSONDecodeError:
                    raise ValueError("invalid_action_json")
            elif isinstance(action_json, dict):
                action_json_value = action_json
            else:
                action_json_value = {}

            next_output, effect_summary, action_warnings = _apply_rule_actions(current_output, action_json_value)
            if action_warnings:
                diagnostic_base["warnings"] = list(dict.fromkeys([*diagnostic_base["warnings"], *action_warnings]))
                warnings.update(action_warnings)
            if effect_summary.get("metadata_changes"):
                metadata.update(effect_summary["metadata_changes"])
            diagnostic_base["matched"] = True
            diagnostic_base["applied"] = bool(effect_summary.get("text_changed")) or bool(effect_summary.get("metadata_changes"))
            diagnostic_base["output_text"] = next_output
            diagnostic_base["effect_summary"] = effect_summary
            current_output = next_output
            matched.append(diagnostic_base)
        except Exception as exc:  # pragma: no cover - defensive path for malformed stored JSON
            diagnostic_base["skipped_reason"] = "failed"
            diagnostic_base["warnings"] = [str(exc)]
            failed.append(diagnostic_base)
            warnings.add(str(exc))

    summary = RuleDryRunSummary(
        ruleset_id=_as_str(ruleset_row["id"]),
        total_rules=len(rows),
        matched_rules=len(matched),
        applied_rules=sum(1 for item in matched if item["applied"]),
        skipped_rules=len(skipped),
        failed_rules=len(failed),
        warnings=sorted(warnings),
        metadata=metadata,
    )
    return RuleDryRunResponse(
        original_input=request.sample_text,
        transformed_output=current_output,
        matched_rules=[
            RuleDryRunDiagnostic.model_validate(item)
            for item in matched
        ],
        skipped_rules=[
            RuleDryRunDiagnostic.model_validate(item)
            for item in skipped
        ],
        failed_rules=[
            RuleDryRunDiagnostic.model_validate(item)
            for item in failed
        ],
        summary=summary,
    )


def _log_record(row: dict[str, Any]) -> LogRecord:
    return LogRecord(
        id=_as_str(row["id"]),
        service=row["service"],
        level=row["level"],
        message=row["message"],
        timestamp=_to_iso(row["timestamp"]),
        intake_note_id=_as_optional_str(row.get("intake_note_id")),
        utterance_id=_as_optional_str(row.get("utterance_id")),
        prompt_generation_id=_as_optional_str(row.get("prompt_generation_id")),
        delivery_id=_as_optional_str(row.get("delivery_id")),
        fields=row.get("fields") or {},
    )


def _fetch_project_row(database_url: str, project_id: str) -> dict[str, Any]:
    rows = _fetch_all(
        database_url,
        "SELECT id, slug FROM projects WHERE id = %s LIMIT 1",
        (project_id,),
    )
    if not rows:
        raise raise_404("project_not_found")
    return rows[0]


def _fetch_log_sources(
    database_url: str,
    intake_note_id: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    intake_notes, deliveries, processing_runs = cq.fetch_log_sources(database_url, intake_note_id=intake_note_id)
    if intake_note_id and not intake_notes:
        raise raise_404("intake_note_not_found")
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


def _dispatch_target_payload(
    database_url: str,
    *,
    target_id: str,
    payload: DeliveryTargetDispatchRequest,
    delivery_id_override: str | None = None,
) -> DeliveryTargetDispatchResponse:
    vault_path = os.getenv("PROMPTFORGE_VAULT_PATH", "/vault")
    target_row = _fetch_delivery_target_row(database_url, target_id)
    if not target_row:
        raise raise_404("target_not_found")

    prompt_generation_row: dict[str, Any] | None = None
    if payload.prompt_generation_id:
        prompt_generation_row = _fetch_prompt_generation_row(database_url, payload.prompt_generation_id)
        if not prompt_generation_row:
            raise raise_404("prompt_generation_not_found")

    delivery_row: dict[str, Any] | None = None
    delivery_id = delivery_id_override or payload.delivery_id
    if delivery_id_override and payload.delivery_id and payload.delivery_id != delivery_id_override:
        raise raise_400("delivery_id_mismatch")
    if delivery_id:
        delivery_row = _fetch_delivery_row(database_url, delivery_id)
        if not delivery_row:
            raise raise_404("delivery_not_found")
        if _as_optional_str(delivery_row.get("target_id")) != _as_str(target_row["id"]):
            raise raise_400("delivery_target_mismatch")
        if payload.prompt_generation_id and _as_optional_str(delivery_row.get("prompt_generation_id")) != payload.prompt_generation_id:
            raise raise_400("delivery_prompt_generation_mismatch")
        if prompt_generation_row is None and _as_optional_str(delivery_row.get("prompt_generation_id")):
            prompt_generation_row = _fetch_prompt_generation_row(
                database_url,
                _as_str(delivery_row["prompt_generation_id"]),
            )
    elif not payload.dry_run:
        prompt_generation_id = payload.prompt_generation_id or _as_optional_str((prompt_generation_row or {}).get("id"))
        if not prompt_generation_id:
            raise raise_400("prompt_generation_id_required")
        payload_content = _dispatch_payload_content(payload, prompt_generation_row)
        delivery_row = _create_delivery_attempt(
            database_url,
            target_row=target_row,
            prompt_generation_row=prompt_generation_row,
            payload_content=payload_content,
            request=payload,
        )
    else:
        prompt_generation_id = payload.prompt_generation_id or _as_optional_str((prompt_generation_row or {}).get("id"))
        payload_content = _dispatch_payload_content(payload, prompt_generation_row)
        synthetic_delivery_id = delivery_id or f"preview-{hashlib.sha1(f'{target_id}|{prompt_generation_id}|{payload_content}'.encode('utf-8')).hexdigest()[:16]}"
        delivery_row = {
            "id": synthetic_delivery_id,
            "prompt_generation_id": prompt_generation_id or synthetic_delivery_id,
            "target_id": target_row["id"],
            "session_identifier": payload.target_session_identifier,
            "status": "dispatching",
            "destination": prompt_generation_row.get("destination") if prompt_generation_row else target_row.get("destination"),
            "mode": payload.mode or (prompt_generation_row or {}).get("mode") or "queue",
            "priority": payload.priority or (prompt_generation_row or {}).get("priority") or "normal",
            "retry_count": 0,
            "dispatch_request_json": {},
            "dispatch_response_json": {},
            "failure_text": None,
            "ack_text": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "dispatched_at": None,
        }

    payload_content = _dispatch_payload_content(payload, prompt_generation_row)
    if not payload_content:
        raise raise_400("payload_content_required")
    if payload.target_session_identifier and str(target_row["target_type"]) not in {"claude_session", "codex_session", "chat_session"}:
        raise raise_400("target_session_identifier_not_allowed")

    outcome = dispatch_target_payload(
        target_row=target_row,
        payload_content=payload_content,
        prompt_generation_id=_as_optional_str((prompt_generation_row or {}).get("id")) or _as_optional_str(delivery_row.get("prompt_generation_id")),
        delivery_id=_as_str(delivery_row["id"]),
        target_session_identifier=payload.target_session_identifier,
        dry_run=payload.dry_run,
        vault_path=vault_path,
    )
    target_type = str(target_row["target_type"])
    supported_types = {"obsidian_note", "generic_queue", "claude_session", "codex_session", "chat_session"}
    unsupported = target_type not in supported_types
    if payload.dry_run:
        if unsupported:
            raise raise_unsupported(
                "unsupported_target_type",
                outcome.error_text or f"unsupported_target_type:{target_type}",
                endpoint=f"/console/targets/{target_id}/dispatch",
                capability="delivery_dispatch",
                details={"target_type": target_type, "dry_run": True},
            )
        return _delivery_dispatch_response(
            delivery_row=delivery_row,
            target_row=target_row,
            outcome=outcome,
            requested_at=datetime.now(timezone.utc).isoformat(),
        )

    if unsupported:
        updated = _update_delivery_attempt(
            database_url,
            delivery_id=_as_str(delivery_row["id"]),
            status=outcome.status,
            mode=_as_optional_str(payload.mode) if payload.mode is not None else None,
            priority=_as_optional_str(payload.priority) if payload.priority is not None else None,
            session_identifier=outcome.session_identifier or payload.target_session_identifier,
            request_json=outcome.request_summary,
            response_json=outcome.response_summary,
            error_text=outcome.error_text,
        )
        raise raise_unsupported(
            "unsupported_target_type",
            outcome.error_text or f"unsupported_target_type:{target_type}",
            endpoint=f"/console/targets/{target_id}/dispatch",
            capability="delivery_dispatch",
            details={
                "target_type": target_type,
                "delivery_id": _as_str(updated["id"]),
                "status": updated["status"],
            },
        )

    updated = _update_delivery_attempt(
        database_url,
        delivery_id=_as_str(delivery_row["id"]),
        status=outcome.status,
        mode=_as_optional_str(payload.mode) if payload.mode is not None else None,
        priority=_as_optional_str(payload.priority) if payload.priority is not None else None,
        session_identifier=outcome.session_identifier or payload.target_session_identifier,
        request_json=outcome.request_summary,
        response_json=outcome.response_summary,
        error_text=outcome.error_text,
    )
    return _delivery_dispatch_response(
        delivery_row=updated,
        target_row=target_row,
        outcome=outcome,
        requested_at=datetime.now(timezone.utc).isoformat(),
    )


def _dispatch_payload_content(
    payload: DeliveryTargetDispatchRequest,
    prompt_generation_row: dict[str, Any] | None,
) -> str:
    if payload.payload_content and payload.payload_content.strip():
        return payload.payload_content.strip()
    if prompt_generation_row:
        text = _as_optional_str(prompt_generation_row.get("final_prompt_markdown")) or ""
        if text.strip():
            return text.strip()
    return ""



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
        raise raise_404("intake_note_not_found")
    return IntakeNoteDetailResponse(note=_intake_note_record(row))


@router.get("/lineage/{intakeNoteId}", response_model=NoteLineageResponse)
def get_intake_lineage(intakeNoteId: str) -> NoteLineageResponse:
    database_url = _require_db_url()
    note_row = cq.fetch_intake_note(database_url, intakeNoteId)
    if not note_row:
        raise raise_404("intake_note_not_found")
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


@router.get("/targets/{target_id}/health", response_model=DeliveryTargetHealthResponse)
def get_delivery_target_health(target_id: str) -> DeliveryTargetHealthResponse:
    database_url = _require_db_url()
    row = _fetch_delivery_target_row(database_url, target_id)
    if not row:
        raise raise_404("target_not_found")
    health = compute_target_health(row)
    return DeliveryTargetHealthResponse(
        targetId=_as_str(row["id"]),
        targetType=row["target_type"],
        healthStatus=health.status,
        detail=health.detail,
        attached=health.attached,
        busy=health.busy,
        reachable=health.reachable,
        stale=health.stale,
        updatedAt=_to_iso(row["updated_at"]),
    )


@router.post("/targets/{target_id}/dispatch", response_model=DeliveryTargetDispatchResponse)
def dispatch_target(
    target_id: str,
    payload: DeliveryTargetDispatchRequest,
) -> DeliveryTargetDispatchResponse:
    database_url = _require_db_url()
    return _dispatch_target_payload(database_url, target_id=target_id, payload=payload)


@router.post("/deliveries/{delivery_id}/dispatch", response_model=DeliveryTargetDispatchResponse)
def dispatch_delivery(
    delivery_id: str,
    payload: DeliveryTargetDispatchRequest,
) -> DeliveryTargetDispatchResponse:
    database_url = _require_db_url()
    delivery_row = _fetch_delivery_row(database_url, delivery_id)
    if not delivery_row:
        raise raise_404("delivery_not_found")
    target_id = _as_optional_str(delivery_row.get("target_id"))
    if not target_id:
        raise raise_404("target_not_found")
    return _dispatch_target_payload(
        database_url,
        target_id=target_id,
        payload=payload,
        delivery_id_override=delivery_id,
    )


@router.get("/logs", response_model=LogListResponse)
def list_logs(
    level: str | None = None,
    service: str | None = None,
    source: str | None = None,
    intake_note_id: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
) -> LogListResponse:
    database_url = _require_db_url()
    limit_value, offset_value = _parse_limit_offset(limit, offset)
    level_value = _validated_choice("level", level, VALID_LOG_LEVELS)
    intake_notes, deliveries, processing_runs = _fetch_log_sources(database_url, intake_note_id)
    logs = _build_log_records(intake_notes, deliveries, processing_runs)
    service_value = _validated_choice("service", service or source, VALID_LOG_SERVICES)
    filtered_logs = _filter_logs(
        logs,
        level=level_value,
        service=service_value,
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
        queued=int(row["queued"]),
        dispatching=int(row["dispatching"]),
        failed_last_24h=int(row["failed_last_24h"]),
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
            raise raise_404("project_not_found")
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
            raise raise_404("project_not_found")
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
    current_rows = _fetch_all(
        database_url,
        """
        SELECT status::text AS status, destination::text AS destination
        FROM deliveries
        WHERE id = %s
        LIMIT 1
        """,
        (delivery_id,),
    )
    if not current_rows:
        raise raise_404("delivery_not_found")
    current = current_rows[0]
    current_status = str(current["status"])
    destination = str(current.get("destination") or "")
    if _terminal_mutation_locked(current_status, destination):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "delivery_immutable_terminal_state",
                "message": f"delivery is immutable after terminal state: {current_status}",
                "current_status": current_status,
                "destination": destination,
            },
        )
    if destination != "queue_only" and current_status != "queued":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "delivery_retry_not_allowed",
                "message": f"retry is not allowed from {current_status}",
                "current_status": current_status,
                "destination": destination,
            },
        )
    attempt_rows = _fetch_all(
        database_url,
        "INSERT INTO delivery_attempts (delivery_id, outcome) VALUES (%s, 'pending') RETURNING id",
        (delivery_id,),
    )
    attempt_id = str(attempt_rows[0]["id"])
    updated = _exec(
        database_url,
        """
        UPDATE deliveries
        SET status = 'queued',
            queued_at = now(),
            error_text = NULL,
            latest_attempt_id = %s
        WHERE id = %s
        """,
        (attempt_id, delivery_id),
    )
    if updated == 0:
        raise raise_404("delivery_not_found")
    return {"ok": True, "message": "Retry queued", "attempt_id": attempt_id}


@router.post("/deliveries/{delivery_id}/reroute")
def reroute_delivery(delivery_id: str, payload: DeliveryRerouteRequest) -> dict[str, Any]:
    database_url = _require_db_url()
    current_rows = _fetch_all(
        database_url,
        """
        SELECT status::text AS status, destination::text AS destination
        FROM deliveries
        WHERE id = %s
        LIMIT 1
        """,
        (delivery_id,),
    )
    if not current_rows:
        raise raise_404("delivery_not_found")
    current = current_rows[0]
    current_status = str(current["status"])
    destination = str(current.get("destination") or "")
    if _terminal_mutation_locked(current_status, destination):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "delivery_reroute_locked",
                "message": f"reroute is not allowed from terminal status {current_status}",
                "current_status": current_status,
                "destination": destination,
            },
        )
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
        raise raise_404("target_not_found")
    target = target_rows[0]
    attempt_rows = _fetch_all(
        database_url,
        "INSERT INTO delivery_attempts (delivery_id, target_id, outcome) VALUES (%s, %s, 'pending') RETURNING id",
        (delivery_id, target["id"]),
    )
    attempt_id = str(attempt_rows[0]["id"])
    updated = _exec(
        database_url,
        """
        UPDATE deliveries
        SET delivery_target_id = %s,
            target_type = %s::pf_target_type,
            target_identifier = %s,
            latest_attempt_id = %s
        WHERE id = %s
        """,
        (target["id"], target["target_type"], target["target_identifier"], attempt_id, delivery_id),
    )
    if updated == 0:
        raise raise_404("delivery_not_found")
    return {"ok": True, "attempt_id": attempt_id}


@router.patch("/deliveries/{delivery_id}/status")
def patch_delivery_status(delivery_id: str, payload: DeliveryStatusRequest) -> dict[str, Any]:
    database_url = _require_db_url()
    current_rows = _fetch_all(
        database_url,
        """
        SELECT status::text AS status, destination::text AS destination
        FROM deliveries
        WHERE id = %s
        LIMIT 1
        """,
        (delivery_id,),
    )
    if not current_rows:
        raise raise_404("delivery_not_found")
    current = current_rows[0]
    current_status = str(current["status"])
    destination = str(current.get("destination") or "")
    requested_status = payload.status.value
    if _terminal_mutation_locked(current_status, destination):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "delivery_status_locked",
                "message": f"status update is not allowed from terminal status {current_status}",
                "current_status": current_status,
                "requested_status": requested_status,
                "destination": destination,
            },
        )
    if (
        destination != "queue_only"
        and current_status != requested_status
        and not _delivery_transition_allowed(current_status, requested_status)
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "delivery_status_transition_not_allowed",
                "message": f"cannot transition delivery from {current_status} to {requested_status}",
                "current_status": current_status,
                "requested_status": requested_status,
                "destination": destination,
            },
        )
    updated = _exec(
        database_url,
        """
        UPDATE deliveries
        SET status = %s::pf_delivery_status
        WHERE id = %s
        """,
        (payload.status.value, delivery_id),
    )
    if updated == 0:
        raise raise_404("delivery_not_found")
    return {"ok": True}


@router.patch("/rules/{rule_id}")
def patch_rule(rule_id: str, payload: RulePatchRequest) -> dict[str, Any]:
    database_url = _require_db_url()
    row = _fetch_all(
        database_url,
        "SELECT id, ruleset_id, enabled, priority FROM rules WHERE id = %s LIMIT 1",
        (rule_id,),
    )
    if not row:
        raise raise_404("rule_not_found")
    current = row[0]
    ruleset_id = _as_str(current["ruleset_id"])
    ruleset = _fetch_ruleset_row(database_url, ruleset_id)
    if not ruleset:
        raise raise_404("ruleset_not_found")
    enabled = payload.enabled if payload.enabled is not None else bool(current["enabled"])
    priority = payload.priority if payload.priority is not None else int(current["priority"])

    try:
        with psycopg.connect(database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO rulesets (name, scope, project_id, version, is_active, description)
                    VALUES (%s, %s::pf_scope, %s, %s, TRUE, %s)
                    RETURNING id
                    """,
                    (
                        ruleset["name"],
                        ruleset["scope"],
                        ruleset.get("project_id"),
                        int(ruleset["version"]) + 1,
                        ruleset.get("description"),
                    ),
                )
                new_ruleset_row = cur.fetchone()
                if not new_ruleset_row:
                    raise raise_404("ruleset_not_found")
                new_ruleset_id = _as_str(new_ruleset_row["id"])
                cur.execute(
                    """
                    INSERT INTO rules (
                        ruleset_id,
                        rule_type,
                        priority,
                        enabled,
                        match_conditions_json,
                        action_json,
                        notes
                    )
                    SELECT
                        %s,
                        rule_type,
                        CASE WHEN id = %s THEN %s ELSE priority END,
                        CASE WHEN id = %s THEN %s ELSE enabled END,
                        match_conditions_json,
                        action_json,
                        notes
                    FROM rules
                    WHERE ruleset_id = %s
                    """,
                    (new_ruleset_id, rule_id, priority, rule_id, enabled, ruleset_id),
                )
                cur.execute(
                    """
                    UPDATE rulesets
                    SET is_active = FALSE
                    WHERE name = %s
                      AND scope = %s::pf_scope
                      AND project_id IS NOT DISTINCT FROM %s
                      AND id <> %s
                    """,
                    (
                        ruleset["name"],
                        ruleset["scope"],
                        ruleset.get("project_id"),
                        new_ruleset_id,
                    ),
                )
                if ruleset["scope"] == Scope.PROJECT.value and ruleset.get("project_id"):
                    cur.execute(
                        """
                        UPDATE projects
                        SET active_ruleset_id = %s
                        WHERE id = %s
                        """,
                        (new_ruleset_id, ruleset["project_id"]),
                    )
            conn.commit()
    except psycopg.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="ruleset_conflict") from exc
    return {"ok": True}


@router.post("/rules", response_model=RuleDetailResponse)
def create_rule(payload: RuleCreateRequest) -> RuleDetailResponse:
    database_url = _require_db_url()
    if not _fetch_ruleset_row(database_url, payload.ruleset_id):
        raise raise_404("ruleset_not_found")
    match_conditions_json = _normalized_json_mapping("match_conditions_json", payload.match_conditions_json)
    action_json = _normalized_json_mapping("action_json", payload.action_json)
    try:
        rows = _fetch_all(
            database_url,
            """
            INSERT INTO rules (
                ruleset_id,
                rule_type,
                priority,
                enabled,
                match_conditions_json,
                action_json,
                notes
            ) VALUES (
                %s,
                %s::pf_rule_type,
                %s,
                %s,
                %s::jsonb,
                %s::jsonb,
                %s
            )
            RETURNING
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
            """,
            (
                payload.ruleset_id,
                payload.rule_type,
                payload.priority,
                payload.enabled,
                json.dumps(match_conditions_json),
                json.dumps(action_json),
                payload.notes,
            ),
        )
    except psycopg.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="rule_conflict") from exc
    if not rows:
        raise raise_404("rule_not_found")
    row = dict(rows[0])
    row["updated_at"] = datetime.now(timezone.utc)
    return RuleDetailResponse(rule=_rule_record(row))


@router.post("/rulesets/{ruleset_id}/dry-run", response_model=RuleDryRunResponse)
def dry_run_ruleset(ruleset_id: str, payload: RuleDryRunRequest) -> RuleDryRunResponse:
    database_url = _require_db_url()
    return _rule_dry_run_payload(database_url=database_url, ruleset_id=ruleset_id, request=payload)




@router.post("/templates", response_model=PromptTemplateDetailResponse)
def create_prompt_template(payload: PromptTemplateCreateRequest) -> PromptTemplateDetailResponse:
    database_url = _require_db_url()
    scope_value, project_id = _normalize_scope(payload.scope, payload.project_id)
    _validate_project_scope(database_url, scope_value, project_id)
    name = _coerce_non_empty_string("name", payload.name, maximum=512)
    prompt_type = _coerce_non_empty_string("prompt_type", payload.prompt_type, maximum=256)
    template_family_key = _coerce_non_empty_string("template_family_key", payload.template_family_key, maximum=512)
    body = _coerce_non_empty_string("body", payload.body, maximum=100000)
    if payload.version < 1:
        raise raise_400("invalid_version")
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO prompt_templates (
                        name,
                        scope,
                        project_id,
                        prompt_type,
                        version,
                        body_template,
                        output_contract_name,
                        is_active
                    ) VALUES (
                        %s,
                        %s::pf_scope,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    RETURNING
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
                    """,
                    (
                        name,
                        scope_value,
                        project_id,
                        prompt_type,
                        payload.version,
                        body,
                        template_family_key,
                        payload.is_active,
                    ),
                )
                row = cur.fetchone()
                if payload.is_active:
                    cur.execute(
                        """
                        UPDATE prompt_templates
                        SET is_active = FALSE
                        WHERE output_contract_name = %s
                          AND scope = %s::pf_scope
                          AND project_id IS NOT DISTINCT FROM %s
                          AND id <> %s
                        """,
                        (template_family_key, scope_value, project_id, row["id"]),
                    )
            conn.commit()
    except psycopg.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="template_conflict") from exc
    if not row:
        raise raise_404("template_not_found")
    row = dict(row)
    row["updated_at"] = datetime.now(timezone.utc)
    return PromptTemplateDetailResponse(prompt_template=_prompt_template_record(row))


@router.patch("/templates/{template_id}", response_model=PromptTemplateDetailResponse)
def patch_prompt_template(template_id: str, payload: PromptTemplatePatchRequest) -> PromptTemplateDetailResponse:
    database_url = _require_db_url()
    current = _fetch_prompt_template_row(database_url, template_id)
    if not current:
        raise raise_404("template_not_found")
    scope_value = payload.scope or Scope(current["scope"])
    project_id = payload.project_id if payload.project_id is not None else _as_optional_str(current.get("project_id"))
    _normalize_scope(scope_value, project_id)
    _validate_project_scope(database_url, scope_value.value, project_id)
    name = _coerce_non_empty_string("name", payload.name if payload.name is not None else current["name"], maximum=512)
    prompt_type = _coerce_non_empty_string(
        "prompt_type",
        payload.prompt_type if payload.prompt_type is not None else current["prompt_type"],
        maximum=256,
    )
    template_family_key = _coerce_non_empty_string(
        "template_family_key",
        payload.template_family_key if payload.template_family_key is not None else current["template_family_key"],
        maximum=512,
    )
    body = _coerce_non_empty_string("body", payload.body if payload.body is not None else current["body"], maximum=100000)
    current_version = int(current["version"])
    version = payload.version if payload.version is not None else current_version + 1
    if version < 1:
        raise raise_400("invalid_version")
    if version <= current_version:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "template_version_not_increasing",
                "message": "template patch must create a higher version",
                "current_version": current_version,
                "requested_version": version,
            },
        )
    is_active = payload.is_active if payload.is_active is not None else bool(current["is_active"])
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO prompt_templates (
                        name,
                        scope,
                        project_id,
                        prompt_type,
                        version,
                        body_template,
                        output_contract_name,
                        is_active
                    ) VALUES (
                        %s,
                        %s::pf_scope,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    RETURNING
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
                    """,
                    (
                        name,
                        scope_value.value,
                        project_id,
                        prompt_type,
                        version,
                        body,
                        template_family_key,
                        is_active,
                    ),
                )
                row = cur.fetchone()
                if is_active:
                    cur.execute(
                        """
                        UPDATE prompt_templates
                        SET is_active = FALSE
                        WHERE output_contract_name = %s
                          AND scope = %s::pf_scope
                          AND project_id IS NOT DISTINCT FROM %s
                          AND id <> %s
                        """,
                        (template_family_key, scope_value.value, project_id, row["id"]),
                    )
            conn.commit()
    except psycopg.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="template_conflict") from exc
    if not row:
        raise raise_404("template_not_found")
    row = dict(row)
    row["updated_at"] = datetime.now(timezone.utc)
    return PromptTemplateDetailResponse(prompt_template=_prompt_template_record(row))


@router.post("/templates/{template_id}/activate")
def activate_template(template_id: str, payload: TemplateActivateRequest) -> dict[str, Any]:
    database_url = _require_db_url()
    template = _fetch_prompt_template_row(database_url, template_id)
    if not template:
        raise raise_404("template_not_found")
    _exec(
        database_url,
        """
        UPDATE prompt_templates
        SET is_active = FALSE
        WHERE output_contract_name = %s
          AND scope = %s::pf_scope
          AND project_id IS NOT DISTINCT FROM %s
        """,
        (payload.family, template["scope"], template.get("project_id")),
    )
    updated = _exec(
        database_url,
        "UPDATE prompt_templates SET is_active = TRUE WHERE id = %s",
        (template_id,),
    )
    if updated == 0:
        raise raise_404("template_not_found")
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
        raise raise_404("prompt_generation_not_found")
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
        raise raise_404("prompt_generation_not_found")
    return {"ok": True, "newId": rows[0]["id"]}


@router.get("/prompts/{prompt_generation_id}/kanban/preview", response_model=KanbanPromptPreviewResponse)
def preview_prompt_kanban_import(prompt_generation_id: str) -> KanbanPromptPreviewResponse:
    database_url = _require_db_url()
    return _build_prompt_generation_kanban_preview(
        database_url=database_url,
        prompt_generation_id=prompt_generation_id,
    )


@router.post("/prompts/{prompt_generation_id}/kanban/apply", response_model=KanbanPromptApplyResponse)
def apply_prompt_to_kanban(prompt_generation_id: str) -> KanbanPromptApplyResponse:
    database_url = _require_db_url()
    preview = _build_prompt_generation_kanban_preview(
        database_url=database_url,
        prompt_generation_id=prompt_generation_id,
    )
    if not preview.build.ok or preview.build.manifest is None:
        return KanbanPromptApplyResponse(
            promptGenerationId=preview.prompt_generation_id,
            projectId=preview.project_id,
            kanbanBaseUrl=preview.kanban_base_url,
            kanbanWorkspaceId=preview.kanban_workspace_id,
            manifest=preview.build.manifest,
            preflightErrors=preview.build.errors,
        )
    try:
        result = import_kanban_manifest(
            binding=KanbanWorkspaceBinding(
                kanbanBaseUrl=preview.kanban_base_url,
                kanbanWorkspaceId=preview.kanban_workspace_id,
            ),
            manifest=preview.build.manifest,
        )
    except KanbanImportClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return KanbanPromptApplyResponse(
        promptGenerationId=preview.prompt_generation_id,
        projectId=preview.project_id,
        kanbanBaseUrl=preview.kanban_base_url,
        kanbanWorkspaceId=preview.kanban_workspace_id,
        manifest=preview.build.manifest,
        result=result,
        preflightErrors=[],
    )


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
        (payload.priority.value, prompt_generation_id),
    )
    if updated == 0:
        raise raise_404("delivery_for_prompt_not_found")
    return {"ok": True}


@router.post("/llm/assist", response_model=LLMAssistResponse)
def llm_assist(payload: LLMAssistRequest, request: Request) -> LLMAssistResponse:
    settings = _build_settings_payload(request=request)
    if not settings.runtime.llmAssistEnabled:
        raise HTTPException(
            status_code=501,
            detail={"detail": "LLM assist is not enabled. Enable via runtime settings."},
        )

    llm_router = get_llm_router()
    if not llm_router.enabled:
        raise HTTPException(
            status_code=501,
            detail={
                "code": "llm_assist_unavailable",
                "message": "LLM assist is not implemented in this environment",
                "supported": False,
                "endpoint": "/console/llm/assist",
                "transport": "llm_router",
            },
        )

    context = {**(payload.context or {}), "context_type": payload.context_type}
    review = llm_router.review_prompt(payload.prompt, context=context)
    if review is None:
        raise HTTPException(
            status_code=501,
            detail={
                "code": "llm_assist_unavailable",
                "message": "No configured LLM provider is available for assist",
                "supported": False,
                "endpoint": "/console/llm/assist",
                "transport": "llm_router",
            },
        )
    polished = (review.raw_response or {}).get("polished_prompt")
    text = polished or review.summary or ""
    return LLMAssistResponse(result=text, provider=review.provider_name, model=review.model_name)


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
        raise raise_404("intake_note_not_found")
    return {"ok": True}


@router.get("/errors/recent", response_model=WorkflowErrorListResponse)
def get_recent_errors(hours: int | None = None) -> WorkflowErrorListResponse:
    database_url = _require_db_url()
    hours_value = hours or 24
    rows = cq.fetch_recent_errors(database_url, hours_value)
    return WorkflowErrorListResponse(
        errors=[WorkflowErrorRecord(
            id=row["id"],
            note_path=row["note_path"],
            delivery_id=row["delivery_id"],
            error_type=row["error_type"],
            error_message=row["error_message"],
            failed_at=_to_iso(row["failed_at"]),
            dismissed_at=_to_iso(row["dismissed_at"]) if row["dismissed_at"] else None,
            created_at=_to_iso(row["created_at"]),
        ) for row in rows]
    )


@router.post("/errors/{error_id}/dismiss")
def dismiss_error(error_id: str) -> dict[str, Any]:
    database_url = _require_db_url()
    updated = cq.dismiss_error(database_url, error_id)
    return {"dismissed": updated > 0}
