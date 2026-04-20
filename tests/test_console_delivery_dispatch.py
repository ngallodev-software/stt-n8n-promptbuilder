from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from promptforge_services.api import app


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set",
)


OBSIDIAN_TARGET_ID = "34343434-3434-4434-8434-343434343434"
GENERIC_QUEUE_TARGET_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
CLAUDE_TARGET_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
PROMPT_GENERATION_ID = "dddddddd-0000-4000-8000-000000000001"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_target_health_reports_reality(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    with TestClient(app) as client:
        live_response = client.get(f"/console/targets/{CLAUDE_TARGET_ID}/health")
        assert live_response.status_code == 200
        live_body = live_response.json()
        assert live_body["healthStatus"] == "unknown"
        assert live_body["detail"] == "live_session_registry_unavailable"

        queue_response = client.get(f"/console/targets/{GENERIC_QUEUE_TARGET_ID}/health")
        assert queue_response.status_code == 200
        queue_body = queue_response.json()
        assert queue_body["healthStatus"] == "ok"


def test_generic_queue_dispatch_persists_attempt(seeded_console_database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMPTFORGE_VAULT_PATH", str(Path.cwd() / "vault"))
    with TestClient(app) as client:
        response = client.post(
            f"/console/targets/{GENERIC_QUEUE_TARGET_ID}/dispatch",
            json={
                "promptGenerationId": PROMPT_GENERATION_ID,
                "payloadContent": "Queue this prompt.",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["accepted"] is True
        assert body["status"] == "queued"
        assert body["machineStatus"] == "queued"
        delivery_id = body["deliveryId"]

    with psycopg.connect(seeded_console_database_url, row_factory=psycopg.rows.dict_row) as conn:
        row = conn.execute(
            """
            SELECT
                status::text AS status,
                queued_at,
                dispatched_at,
                session_identifier,
                dispatch_request_json,
                dispatch_response_json
            FROM deliveries
            WHERE id = %s
            """,
            (delivery_id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "queued"
    assert row["queued_at"] is not None
    assert row["session_identifier"] is None
    assert row["dispatch_request_json"]["target_id"] == GENERIC_QUEUE_TARGET_ID
    assert row["dispatch_response_json"]["machine_status"] == "queued"


def test_obsidian_dispatch_writes_note_and_persists_attempt(
    seeded_console_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PROMPTFORGE_VAULT_PATH", str(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            f"/console/targets/{OBSIDIAN_TARGET_ID}/dispatch",
            json={
                "promptGenerationId": PROMPT_GENERATION_ID,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["accepted"] is True
        assert body["status"] == "delivered"
        assert body["machineStatus"] == "delivered"
        output_path = Path(body["externalIdentifier"])
        assert output_path.exists()
        delivery_id = body["deliveryId"]

    with psycopg.connect(seeded_console_database_url, row_factory=psycopg.rows.dict_row) as conn:
        row = conn.execute(
            """
            SELECT
                status::text AS status,
                dispatched_at,
                session_identifier,
                dispatch_request_json,
                dispatch_response_json
            FROM deliveries
            WHERE id = %s
            """,
            (delivery_id,),
        ).fetchone()
    assert row is not None
    assert row["status"] == "delivered"
    assert row["dispatched_at"] is not None
    assert row["dispatch_response_json"]["output_path"] == str(output_path)


def test_live_session_dispatch_rejected_explicitly(
    seeded_console_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROMPTFORGE_VAULT_PATH", str(Path.cwd() / "vault"))
    with TestClient(app) as client:
        response = client.post(
            f"/console/targets/{CLAUDE_TARGET_ID}/dispatch",
            json={
                "promptGenerationId": PROMPT_GENERATION_ID,
                "targetSessionIdentifier": "claude-tax-main",
            },
        )
        assert response.status_code == 501
        assert "not implemented in this environment" in response.json()["detail"]

    with psycopg.connect(seeded_console_database_url, row_factory=psycopg.rows.dict_row) as conn:
        row = conn.execute(
            """
            SELECT status::text AS status, error_text, dispatch_response_json
            FROM deliveries
            WHERE target_type = 'claude_session'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
        ).fetchone()
    assert row is not None
    assert row["status"] == "failed"
    assert "not implemented in this environment" in (row["error_text"] or "")
    assert row["dispatch_response_json"]["machine_status"] == "unsupported"
