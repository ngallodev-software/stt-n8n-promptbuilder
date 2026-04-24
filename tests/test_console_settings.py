from __future__ import annotations

import json
import os

import psycopg
import pytest
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from psycopg.rows import dict_row

from promptforge_services.api import app
from promptforge_services import console_api


PROJECT_ID = "22222222-2222-4222-8222-222222222222"


def _client() -> TestClient:
    return TestClient(app)


def _fetch_one(database_url: str, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
    return dict(row) if row else {}


@pytest.fixture(autouse=True)
def secrets_master_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("PROMPTFORGE_SECRETS_MASTER_KEY", key)
    monkeypatch.setenv("PROMPTFORGE_SECRETS_KEY_VERSION", "1")
    return key


def test_console_settings_schema_tables_exist(seeded_console_database_url: str) -> None:
    row = _fetch_one(
        seeded_console_database_url,
        """
        SELECT COUNT(*)::int AS table_count
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name IN (
              'console_runtime_settings'
          )
        """,
    )
    assert row["table_count"] == 1


def test_console_settings_reads_skip_missing_setting_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_fetch_all(database_url: str, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        calls.append(sql)
        if "to_regclass('console_runtime_settings')" in sql:
            return [{"runtime_exists": False, "secret_exists": False}]
        raise AssertionError("settings rows should not be queried when tables are absent")

    monkeypatch.setattr(console_api, "_fetch_all", fake_fetch_all)

    runtime_rows, secret_rows = console_api._safe_fetch_settings_rows(
        "postgresql://example",
        scope="global",
        project_id=None,
    )

    assert runtime_rows == []
    assert secret_rows == []
    assert len(calls) == 1


def test_console_settings_get_default_global_path(seeded_console_database_url: str) -> None:
    client = _client()
    response = client.get("/console/settings")
    assert response.status_code == 200
    body = response.json()

    assert body["scope"] == "global"
    assert body["project_id"] is None
    assert set(body["runtime"]) == {
        "obsidianVaultPath",
        "webhookUrl",
        "llmMode",
        "codexBinary",
        "codexReasoningEffort",
        "openaiBaseUrl",
        "anthropicBaseUrl",
        "kanbanBaseUrl",
        "kanbanWorkspaceId",
    }
    assert set(body["secrets"]) == {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "PROMPTFORGE_OPENAI_COMPAT_API_KEY",
        "PROMPTFORGE_OLLAMA_API_KEY",
    }
    assert body["permissions"] == {
        "can_update_runtime": True,
        "can_rotate_secrets": True,
        "can_purge_archived_notes": True,
    }


def test_console_settings_role_permissions(seeded_console_database_url: str) -> None:
    client = _client()

    viewer = client.get("/console/settings", headers={"X-PromptForge-Role": "viewer"})
    assert viewer.status_code == 200
    assert viewer.json()["permissions"] == {
        "can_update_runtime": False,
        "can_rotate_secrets": False,
        "can_purge_archived_notes": False,
    }

    operator = client.get("/console/settings", headers={"X-PromptForge-Role": "operator"})
    assert operator.status_code == 200
    assert operator.json()["permissions"] == {
        "can_update_runtime": False,
        "can_rotate_secrets": False,
        "can_purge_archived_notes": False,
    }


def test_console_settings_project_scope_read_supports_overrides(seeded_console_database_url: str) -> None:
    with psycopg.connect(seeded_console_database_url, autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO console_runtime_settings (scope, project_id, key, value_json, updated_by_user_id)
            VALUES ('project', %s, 'llmMode', '"llm_inference_optional"'::jsonb, 'tester')
            """,
            (PROJECT_ID,),
        )

    client = _client()
    response = client.get(
        "/console/settings",
        params={"scope": "project", "project_id": PROJECT_ID},
        headers={"X-PromptForge-Role": "operator"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "project"
    assert body["project_id"] == PROJECT_ID
    assert body["runtime"]["llmMode"] == "llm_inference_optional"




def test_console_settings_runtime_patch_validation_failures(seeded_console_database_url: str) -> None:
    client = _client()
    response = client.patch(
        "/console/settings/runtime",
        json={"scope": "global", "project_id": None, "runtime": {"webhookUrl": "ftp://bad.example"}},
        headers={"X-PromptForge-Role": "admin"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_webhookUrl"

    response = client.patch(
        "/console/settings/runtime",
        json={"scope": "global", "project_id": None, "runtime": {"kanbanWorkspaceId": "   "}},
        headers={"X-PromptForge-Role": "admin"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_kanbanWorkspaceId"


def test_console_settings_runtime_patch_allows_blank_webhook_url(seeded_console_database_url: str) -> None:
    client = _client()
    response = client.patch(
        "/console/settings/runtime",
        json={"scope": "global", "project_id": None, "runtime": {"webhookUrl": ""}},
        headers={"X-PromptForge-Role": "admin"},
    )
    assert response.status_code == 200
    assert response.json()["runtime"]["webhookUrl"] == ""


def test_console_settings_runtime_patch_bootstraps_missing_settings_tables(
    seeded_console_database_url: str,
) -> None:
    with psycopg.connect(seeded_console_database_url, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS console_secret_settings CASCADE")
        conn.execute("DROP TABLE IF EXISTS console_runtime_settings CASCADE")

    client = _client()
    response = client.patch(
        "/console/settings/runtime",
        json={"scope": "global", "project_id": None, "runtime": {"llmMode": "deterministic_only"}},
        headers={"X-PromptForge-Role": "admin"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "global"
    assert body["runtime"]["llmMode"] == "deterministic_only"

    row = _fetch_one(
        seeded_console_database_url,
        """
        SELECT key, value_json
        FROM console_runtime_settings
        WHERE scope = 'global'
          AND project_id IS NULL
          AND key = 'llmMode'
        """,
    )
    assert row["key"] == "llmMode"
    assert row["value_json"] == "deterministic_only"


def test_console_settings_runtime_patch_persists_kanban_binding(
    seeded_console_database_url: str,
) -> None:
    client = _client()
    response = client.patch(
        "/console/settings/runtime",
        json={
            "scope": "project",
            "project_id": PROJECT_ID,
            "runtime": {
                "kanbanBaseUrl": "http://127.0.0.1:3000",
                "kanbanWorkspaceId": "workspace-123",
            },
        },
        headers={"X-PromptForge-Role": "admin"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["kanbanBaseUrl"] == "http://127.0.0.1:3000"
    assert body["runtime"]["kanbanWorkspaceId"] == "workspace-123"

    row = _fetch_one(
        seeded_console_database_url,
        """
        SELECT key, value_json
        FROM console_runtime_settings
        WHERE scope = 'project'
          AND project_id = %s
          AND key = 'kanbanWorkspaceId'
        """,
        (PROJECT_ID,),
    )
    assert row["key"] == "kanbanWorkspaceId"
    assert row["value_json"] == "workspace-123"


def test_console_llm_assist_returns_structured_unsupported_response(
    seeded_console_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del seeded_console_database_url
    monkeypatch.setenv("PROMPTFORGE_LLM_ENABLED", "0")
    client = _client()
    response = client.post(
        "/console/llm/assist",
        json={
            "prompt": "polish this prompt",
            "context_type": "general",
            "context": {"project_slug": "the-tax-machine"},
        },
    )
    assert response.status_code == 501
    body = response.json()["detail"]
    assert body == {"detail": "LLM assist is not enabled. Enable via runtime settings."}




def test_console_bootstrap_includes_settings_block(seeded_console_database_url: str) -> None:
    client = _client()
    response = client.get("/console/bootstrap")
    assert response.status_code == 200
    body = response.json()
    assert "settings" in body
    assert body["settings"]["scope"] == "global"
    assert set(body["settings"]["permissions"]) == {
        "can_update_runtime",
        "can_rotate_secrets",
    }
