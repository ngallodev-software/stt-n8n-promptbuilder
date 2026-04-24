from __future__ import annotations

from fastapi.testclient import TestClient

from promptforge_services.api import app
from promptforge_services.console_models import (
    ConsoleRuntimeSettings,
    ConsoleSettingsPermissions,
    ConsoleSettingsResponse,
    Scope,
)


def _client() -> TestClient:
    return TestClient(app)


def _prompt_row() -> dict[str, object]:
    return {
        "id": "pg_123",
        "intake_note_id": "note_123",
        "status": "rendered",
        "requires_review": False,
        "prompt_type": "planning",
        "ruleset_id": None,
        "template_id": None,
        "destination": "queue_only",
        "mode": "queue",
        "priority": "normal",
        "structured_output_json": {},
        "final_prompt_markdown": "Build the feature.",
        "validation_warnings": [],
        "created_at": "2026-04-24T00:00:00Z",
        "updated_at": "2026-04-24T00:00:00Z",
        "project_id": "project-123",
    }


def _settings_response() -> ConsoleSettingsResponse:
    return ConsoleSettingsResponse(
        scope=Scope.PROJECT,
        project_id="project-123",
        runtime=ConsoleRuntimeSettings(
            obsidianVaultPath="/vault",
            webhookUrl="http://127.0.0.1/webhook",
            llmMode="deterministic_only",
            codexBinary="codex",
            codexReasoningEffort="medium",
            openaiBaseUrl="https://api.openai.com/v1",
            anthropicBaseUrl="https://api.anthropic.com",
            kanbanBaseUrl="http://127.0.0.1:3484",
            kanbanWorkspaceId="workspace-123",
        ),
        secrets={},
        permissions=ConsoleSettingsPermissions(
            can_update_runtime=True,
            can_rotate_secrets=True,
            can_purge_archived_notes=True,
        ),
        updated_at="2026-04-24T00:00:00Z",
    )


def test_preview_prompt_kanban_import(monkeypatch) -> None:
    monkeypatch.setattr("promptforge_services.console_api._require_db_url", lambda: "postgresql://example")
    monkeypatch.setattr("promptforge_services.console_api._fetch_prompt_generation_row", lambda *_args, **_kwargs: _prompt_row())
    monkeypatch.setattr("promptforge_services.console_api._build_settings_payload", lambda **_kwargs: _settings_response())

    response = _client().get("/console/prompts/pg_123/kanban/preview")
    assert response.status_code == 200
    body = response.json()
    assert body["promptGenerationId"] == "pg_123"
    assert body["kanbanBaseUrl"] == "http://127.0.0.1:3484"
    assert body["kanbanWorkspaceId"] == "workspace-123"
    assert body["build"]["ok"] is True
    assert body["build"]["manifest"]["tasks"][0]["externalTaskKey"] == "pf:pg:pg_123"


def test_apply_prompt_to_kanban(monkeypatch) -> None:
    monkeypatch.setattr("promptforge_services.console_api._require_db_url", lambda: "postgresql://example")
    monkeypatch.setattr("promptforge_services.console_api._fetch_prompt_generation_row", lambda *_args, **_kwargs: _prompt_row())
    monkeypatch.setattr("promptforge_services.console_api._build_settings_payload", lambda **_kwargs: _settings_response())
    monkeypatch.setattr(
        "promptforge_services.console_api.import_kanban_manifest",
        lambda **_kwargs: {
            "version": "v1",
            "ok": True,
            "applied": True,
            "taskMappings": [
                {
                    "externalTaskKey": "pf:pg:pg_123",
                    "taskId": "task-1",
                    "columnId": "backlog",
                    "created": True,
                }
            ],
            "linkResults": [],
            "startResults": [],
        },
    )

    response = _client().post("/console/prompts/pg_123/kanban/apply")
    assert response.status_code == 200
    body = response.json()
    assert body["promptGenerationId"] == "pg_123"
    assert body["preflightErrors"] == []
    assert body["result"]["ok"] is True
    assert body["result"]["taskMappings"][0]["taskId"] == "task-1"


def test_apply_prompt_to_kanban_requires_project_scope(monkeypatch) -> None:
    row = _prompt_row()
    row["project_id"] = None
    monkeypatch.setattr("promptforge_services.console_api._require_db_url", lambda: "postgresql://example")
    monkeypatch.setattr("promptforge_services.console_api._fetch_prompt_generation_row", lambda *_args, **_kwargs: row)

    response = _client().post("/console/prompts/pg_123/kanban/apply")
    assert response.status_code == 400
    assert response.json()["detail"] == "prompt_generation_project_scope_required"


def test_discover_kanban_workspaces(monkeypatch) -> None:
    monkeypatch.setattr(
        "promptforge_services.console_api.list_kanban_workspaces",
        lambda **_kwargs: {
            "currentWorkspaceId": "workspace-123",
            "workspaces": [
                {
                    "workspaceId": "workspace-123",
                    "name": "alpha",
                    "path": "/tmp/alpha",
                    "taskCounts": {"backlog": 1, "inProgress": 0, "review": 0, "trash": 0},
                }
            ],
        },
    )

    response = _client().get("/console/kanban/workspaces", params={"base_url": "http://127.0.0.1:3484"})
    assert response.status_code == 200
    body = response.json()
    assert body["currentWorkspaceId"] == "workspace-123"
    assert body["workspaces"][0]["workspaceId"] == "workspace-123"
