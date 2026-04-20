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
              'console_runtime_settings',
              'console_secret_settings',
              'console_admin_audit_log'
          )
        """,
    )
    assert row["table_count"] == 3


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


def test_console_settings_runtime_patch_success_and_audit(seeded_console_database_url: str) -> None:
    client = _client()
    payload = {
        "scope": "global",
        "project_id": None,
        "runtime": {
            "obsidianVaultPath": "/srv/promptforge/vault",
            "webhookUrl": "https://hooks.internal/promptforge",
            "codexReasoningEffort": "high",
        },
    }
    response = client.patch(
        "/console/settings/runtime",
        json=payload,
        headers={"X-PromptForge-Role": "admin", "X-PromptForge-Actor": "user:test-admin"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["obsidianVaultPath"] == "/srv/promptforge/vault"
    assert body["runtime"]["webhookUrl"] == "https://hooks.internal/promptforge"
    assert body["runtime"]["codexReasoningEffort"] == "high"

    audit = _fetch_one(
        seeded_console_database_url,
        """
        SELECT actor, payload_json
        FROM console_admin_audit_log
        WHERE action = 'runtime_settings_updated'
        ORDER BY created_at DESC
        LIMIT 1
        """,
    )
    assert audit["actor"] == "user:test-admin"
    assert sorted(audit["payload_json"]["keys_changed"]) == [
        "codexReasoningEffort",
        "obsidianVaultPath",
        "webhookUrl",
    ]


def test_console_settings_runtime_patch_validation_failures(seeded_console_database_url: str) -> None:
    client = _client()
    response = client.patch(
        "/console/settings/runtime",
        json={"scope": "global", "project_id": None, "runtime": {"webhookUrl": "ftp://bad.example"}},
        headers={"X-PromptForge-Role": "admin"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_webhookUrl"


def test_console_settings_secrets_stubbed_returns_structured_error(seeded_console_database_url: str) -> None:
    client = _client()
    del seeded_console_database_url
    response = client.patch(
        "/console/settings/secrets",
        json={
            "scope": "global",
            "project_id": None,
            "secrets": {
                "OPENAI_API_KEY": "sk-test-secret",
                "ANTHROPIC_API_KEY": "anthropic-secret",
            },
        },
        headers={"X-PromptForge-Role": "admin", "X-PromptForge-Actor": "user:secret-admin"},
    )
    assert response.status_code == 501
    detail = response.json()["detail"]
    assert detail["code"] == "settings_secrets_stubbed"
    assert detail["status"] == "unsupported"
    assert detail["endpoint"] == "/console/settings/secrets"


def test_console_settings_secret_permission_failure(seeded_console_database_url: str) -> None:
    client = _client()
    response = client.patch(
        "/console/settings/secrets",
        json={"scope": "global", "project_id": None, "secrets": {"OPENAI_API_KEY": "sk-test"}},
        headers={"X-PromptForge-Role": "viewer"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"


def test_console_settings_secret_rotation_fails_closed_without_master_key(
    seeded_console_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del seeded_console_database_url
    monkeypatch.delenv("PROMPTFORGE_SECRETS_MASTER_KEY", raising=False)
    client = _client()
    response = client.patch(
        "/console/settings/secrets",
        json={"scope": "global", "project_id": None, "secrets": {"OPENAI_API_KEY": "sk-test"}},
        headers={"X-PromptForge-Role": "admin"},
    )
    assert response.status_code == 501
    assert response.json()["detail"]["code"] == "settings_secrets_stubbed"


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
    assert body == {
        "code": "llm_assist_unavailable",
        "message": "LLM assist is not implemented in this environment",
        "supported": False,
        "endpoint": "/console/llm/assist",
        "transport": "llm_router",
    }


def test_console_settings_reads_never_return_raw_secret_values(seeded_console_database_url: str) -> None:
    with psycopg.connect(seeded_console_database_url, autocommit=True) as conn:
        updated = conn.execute(
            """
            UPDATE console_secret_settings
            SET secret_value = NULL,
                secret_ciphertext = 'gAAAAABlegacy-placeholder',
                secret_key_version = 1,
                configured = TRUE,
                last_rotated_at = now(),
                updated_by_user_id = 'tester',
                updated_at = now()
            WHERE scope = 'global'
              AND project_id IS NULL
              AND key = 'PROMPTFORGE_OPENAI_COMPAT_API_KEY'
            """
        )
        if updated.rowcount == 0:
            conn.execute(
                """
                INSERT INTO console_secret_settings (
                    scope, project_id, key, secret_value, secret_ciphertext, secret_key_version,
                    configured, last_rotated_at, updated_by_user_id
                ) VALUES (
                    'global', NULL, 'PROMPTFORGE_OPENAI_COMPAT_API_KEY', NULL, 'gAAAAABlegacy-placeholder', 1,
                    TRUE, now(), 'tester'
                )
                """
            )

    client = _client()
    response = client.get("/console/settings")
    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert "gAAAAABlegacy-placeholder" not in serialized
    assert "secret_value" not in serialized
    assert "secret_ciphertext" not in serialized


def test_console_purge_archived_notes_stubbed_returns_structured_error(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    client = _client()
    response = client.post(
        "/console/admin/purge-archived-notes",
        json={"confirm": "purge archived notes"},
        headers={"X-PromptForge-Role": "admin", "X-PromptForge-Actor": "user:purger"},
    )
    assert response.status_code == 501
    detail = response.json()["detail"]
    assert detail["code"] == "purge_archived_notes_stubbed"
    assert detail["status"] == "unsupported"
    assert detail["endpoint"] == "/console/admin/purge-archived-notes"


def test_console_purge_archived_notes_permission_and_confirmation_failures(
    seeded_console_database_url: str,
) -> None:
    del seeded_console_database_url
    with psycopg.connect(seeded_console_database_url, autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO intake_notes (
                id, vault_path, note_relative_path, note_title, note_hash, imported_at,
                frontmatter_json, body_markdown, project_id, status, watch_eligible, source_device, created_at
            ) VALUES (
                'aaaaaaaa-0000-4000-8000-000000000099',
                '/vault/Inbox/Voice/archived-note.md',
                'Inbox/Voice/archived-note.md',
                'Archived note',
                'archived-hash',
                now(),
                '{}'::jsonb,
                'Archived body',
                %s,
                'archived',
                FALSE,
                'windows-main',
                now()
            );
            INSERT INTO utterances (
                id, intake_note_id, raw_text, project_id, scope, capture_type, created_at
            ) VALUES (
                'bbbbbbbb-0000-4000-8000-000000000099',
                'aaaaaaaa-0000-4000-8000-000000000099',
                'archived utterance',
                %s,
                'project',
                'voice',
                now()
            );
            INSERT INTO transcript_revisions (
                id, utterance_id, revision_kind, content, producer_type, producer_name, metadata_json, created_at
            ) VALUES (
                'cccccccc-0000-4000-8000-000000000099',
                'bbbbbbbb-0000-4000-8000-000000000099',
                'raw',
                'archived utterance',
                'watcher',
                'tester',
                '{}'::jsonb,
                now()
            );
            INSERT INTO prompt_generations (
                id, utterance_id, project_id, prompt_type, structured_output_json,
                final_prompt_markdown, requires_review, status, created_at
            ) VALUES (
                'dddddddd-0000-4000-8000-000000000099',
                'bbbbbbbb-0000-4000-8000-000000000099',
                %s,
                'general',
                '{}'::jsonb,
                'Archived prompt',
                FALSE,
                'rendered',
                now()
            );
            INSERT INTO llm_runs (
                id, utterance_id, prompt_generation_id, provider_name, model_name, mode, created_at
            ) VALUES (
                '99999999-0000-4000-8000-000000000099',
                'bbbbbbbb-0000-4000-8000-000000000099',
                'dddddddd-0000-4000-8000-000000000099',
                'openai',
                'gpt-test',
                'review',
                now()
            );
            INSERT INTO deliveries (
                id, prompt_generation_id, destination, target_type, target_identifier, mode, status, priority, created_at
            ) VALUES (
                'eeeeeeee-0000-4000-8000-000000000099',
                'dddddddd-0000-4000-8000-000000000099',
                'queue_only',
                'generic_queue',
                'archived-target',
                'queue',
                'queued',
                'normal',
                now()
            );
            INSERT INTO processing_runs (
                id, utterance_id, workflow_name, status, started_at, ended_at, trace_json
            ) VALUES (
                'ffffffff-0000-4000-8000-000000000099',
                'bbbbbbbb-0000-4000-8000-000000000099',
                'archived-flow',
                'completed',
                now(),
                now(),
                '{}'::jsonb
            );
            """,
            (PROJECT_ID, PROJECT_ID, PROJECT_ID),
        )

    client = _client()
    denied = client.post(
        "/console/admin/purge-archived-notes",
        json={"confirm": "purge archived notes"},
        headers={"X-PromptForge-Role": "viewer"},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "forbidden"

    bad_confirm = client.post(
        "/console/admin/purge-archived-notes",
        json={"confirm": "delete stuff"},
        headers={"X-PromptForge-Role": "admin"},
    )
    assert bad_confirm.status_code == 400
    assert bad_confirm.json()["detail"] == "confirmation_required"


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
        "can_purge_archived_notes",
    }
