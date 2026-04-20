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


def _delivery_history(client: TestClient, prompt_generation_id: str) -> list[dict[str, object]]:
    response = client.get("/console/deliveries", params={"prompt_generation_id": prompt_generation_id})
    assert response.status_code == 200
    return response.json()["deliveries"]


def test_target_health_reports_reality(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    with TestClient(app) as client:
        live_response = client.get(f"/console/targets/{CLAUDE_TARGET_ID}/health")
        assert live_response.status_code == 200
        live_body = live_response.json()
        assert live_body["targetId"] == CLAUDE_TARGET_ID
        assert live_body["targetType"] == "claude_session"
        assert live_body["healthStatus"] == "unknown"
        assert live_body["detail"] == "live_session_registry_unavailable"

        queue_response = client.get(f"/console/targets/{GENERIC_QUEUE_TARGET_ID}/health")
        assert queue_response.status_code == 200
        queue_body = queue_response.json()
        assert queue_body["targetId"] == GENERIC_QUEUE_TARGET_ID
        assert queue_body["targetType"] == "generic_queue"
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
        assert body["targetId"] == GENERIC_QUEUE_TARGET_ID
        assert body["targetType"] == "generic_queue"
        assert body["promptGenerationId"] == PROMPT_GENERATION_ID
        assert body["accepted"] is True
        assert body["status"] == "queued"
        assert body["machineStatus"] == "queued"
        assert body["externalIdentifier"] == "manual-review"
        assert body["sessionIdentifier"] is None
        assert body["errorText"] is None
        assert body["requestSummary"]["target_id"] == GENERIC_QUEUE_TARGET_ID
        assert body["responseSummary"]["queue_name"] == "manual-review"
        delivery_id = body["deliveryId"]

        deliveries = _delivery_history(client, PROMPT_GENERATION_ID)
        assert deliveries[0]["id"] == delivery_id
        assert deliveries[0]["status"] == "queued"
        assert deliveries[0]["target_id"] == GENERIC_QUEUE_TARGET_ID

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
        assert body["targetId"] == OBSIDIAN_TARGET_ID
        assert body["targetType"] == "obsidian_note"
        assert body["promptGenerationId"] == PROMPT_GENERATION_ID
        assert body["accepted"] is True
        assert body["status"] == "delivered"
        assert body["machineStatus"] == "delivered"
        output_path = Path(body["externalIdentifier"])
        assert tmp_path in output_path.parents
        assert output_path.exists()
        assert body["responseSummary"]["output_path"] == str(output_path)
        delivery_id = body["deliveryId"]

        deliveries = _delivery_history(client, PROMPT_GENERATION_ID)
        assert deliveries[0]["id"] == delivery_id
        assert deliveries[0]["status"] == "delivered"
        assert deliveries[0]["target_id"] == OBSIDIAN_TARGET_ID

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
        body = response.json()
        assert "not implemented in this environment" in body["detail"]

        deliveries = _delivery_history(client, PROMPT_GENERATION_ID)
        failed = next(row for row in deliveries if row["target_id"] == CLAUDE_TARGET_ID and row["status"] == "failed")
        assert failed["session_identifier"] == "claude-tax-main"
        assert failed["dispatch_response_json"]["machine_status"] == "unsupported"

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
