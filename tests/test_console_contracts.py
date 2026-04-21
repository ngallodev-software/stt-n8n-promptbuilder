from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from promptforge_services.api import app


pytestmark = pytest.mark.skipif(
    not os.getenv("PROMPTFORGE_DATABASE_URL"),
    reason="PROMPTFORGE_DATABASE_URL not set",
)


PROMPT_GENERATION_ID = "dddddddd-0000-4000-8000-000000000001"
GENERIC_QUEUE_TARGET_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
CLAUDE_TARGET_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
PROJECT_ID = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _insert_delivery_target(
    database_url: str,
    *,
    target_id: str,
    name: str,
    target_type: str,
    target_identifier: str,
    scope: str = "global",
    project_id: str | None = None,
) -> None:
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO delivery_targets (
                id,
                name,
                target_type,
                target_identifier,
                scope,
                project_id,
                is_default,
                is_auto_dispatch_safe,
                config_json
            ) VALUES (
                %s,
                %s,
                %s::pf_target_type,
                %s,
                %s::pf_scope,
                %s,
                FALSE,
                FALSE,
                '{}'::jsonb
            )
            """,
            (target_id, name, target_type, target_identifier, scope, project_id),
        )


def _insert_delivery(
    database_url: str,
    *,
    delivery_id: str,
    destination: str,
    status: str,
    target_type: str,
    target_identifier: str,
    delivery_target_id: str | None = None,
) -> None:
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(
            """
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
                error_text
            ) VALUES (
                %s,
                %s,
                %s,
                %s::pf_destination,
                %s::pf_target_type,
                %s,
                'queue'::pf_delivery_mode,
                %s::pf_delivery_status,
                'normal'::pf_priority,
                now() - interval '5 minutes',
                CASE WHEN %s IN ('dispatching', 'delivered', 'acked', 'failed') THEN now() - interval '2 minutes' ELSE NULL END,
                CASE WHEN %s = 'failed' THEN 'seed failure' ELSE NULL END
            )
            """,
            (
                delivery_id,
                PROMPT_GENERATION_ID,
                delivery_target_id,
                destination,
                target_type,
                target_identifier,
                status,
                status,
                status,
            ),
        )


def _delete_rows(database_url: str, table: str, ids: list[str]) -> None:
    if not ids:
        return
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(f"DELETE FROM {table} WHERE id = ANY(%s::uuid[])", (ids,))


def test_dispatch_unsupported_target_type_returns_structured_envelope_and_persists_attempt(
    seeded_console_database_url: str,
    client: TestClient,
) -> None:
    target_id = str(uuid.uuid4())
    _insert_delivery_target(
        seeded_console_database_url,
        target_id=target_id,
        name="Unsupported target",
        target_type="none",
        target_identifier="unsupported-none-target",
    )
    created_delivery_id: str | None = None
    try:
        response = client.post(
            f"/console/targets/{target_id}/dispatch",
            json={
                "promptGenerationId": PROMPT_GENERATION_ID,
                "payloadContent": "Unsupported delivery test payload.",
            },
        )
        assert response.status_code == 501
        detail = response.json()["detail"]
        assert detail["code"] == "unsupported_target_type"
        assert detail["status"] == "unsupported"
        assert detail["machine_status"] == "unsupported"
        assert detail["retryable"] is False
        assert detail["endpoint"] == f"/console/targets/{target_id}/dispatch"
        assert detail["capability"] == "delivery_dispatch"
        assert detail["details"]["target_type"] == "none"
        created_delivery_id = detail["details"]["delivery_id"]
        assert detail["details"]["status"] == "failed"

        with psycopg.connect(seeded_console_database_url, row_factory=psycopg.rows.dict_row) as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    status::text AS status,
                    target_type::text AS target_type,
                    error_text,
                    dispatch_response_json
                FROM deliveries
                WHERE id = %s
                """,
                (created_delivery_id,),
            ).fetchone()
        assert row is not None
        assert row["status"] == "failed"
        assert row["target_type"] == "none"
        assert "unsupported_target_type:none" in str(row["error_text"])
        assert row["dispatch_response_json"]["machine_status"] == "unsupported"
    finally:
        _delete_rows(seeded_console_database_url, "deliveries", [created_delivery_id] if created_delivery_id else [])
        _delete_rows(seeded_console_database_url, "delivery_targets", [target_id])


def test_delivery_retry_rejects_terminal_non_queue_destination(
    seeded_console_database_url: str,
    client: TestClient,
) -> None:
    delivery_id = str(uuid.uuid4())
    _insert_delivery(
        seeded_console_database_url,
        delivery_id=delivery_id,
        destination="cli",
        status="delivered",
        target_type="claude_session",
        target_identifier="claude-contract-test",
        delivery_target_id=CLAUDE_TARGET_ID,
    )
    try:
        response = client.post(f"/console/deliveries/{delivery_id}/retry")
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "delivery_immutable_terminal_state"
        assert detail["current_status"] == "delivered"
        assert detail["destination"] == "cli"
    finally:
        _delete_rows(seeded_console_database_url, "deliveries", [delivery_id])


def test_delivery_reroute_rejects_terminal_non_queue_destination(
    seeded_console_database_url: str,
    client: TestClient,
) -> None:
    delivery_id = str(uuid.uuid4())
    _insert_delivery(
        seeded_console_database_url,
        delivery_id=delivery_id,
        destination="chat",
        status="failed",
        target_type="claude_session",
        target_identifier="claude-contract-test",
        delivery_target_id=CLAUDE_TARGET_ID,
    )
    try:
        response = client.post(
            f"/console/deliveries/{delivery_id}/reroute",
            json={"targetId": GENERIC_QUEUE_TARGET_ID},
        )
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "delivery_reroute_locked"
        assert detail["current_status"] == "failed"
        assert detail["destination"] == "chat"
    finally:
        _delete_rows(seeded_console_database_url, "deliveries", [delivery_id])


def test_delivery_status_patch_rejects_terminal_non_queue_destination(
    seeded_console_database_url: str,
    client: TestClient,
) -> None:
    delivery_id = str(uuid.uuid4())
    _insert_delivery(
        seeded_console_database_url,
        delivery_id=delivery_id,
        destination="cli",
        status="acked",
        target_type="claude_session",
        target_identifier="claude-contract-test",
        delivery_target_id=CLAUDE_TARGET_ID,
    )
    try:
        response = client.patch(f"/console/deliveries/{delivery_id}/status", json={"status": "queued"})
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "delivery_status_locked"
        assert detail["current_status"] == "acked"
        assert detail["requested_status"] == "queued"
        assert detail["destination"] == "cli"
    finally:
        _delete_rows(seeded_console_database_url, "deliveries", [delivery_id])


def test_delivery_queue_only_records_remain_mutable_for_retry_and_status(
    seeded_console_database_url: str,
    client: TestClient,
) -> None:
    delivery_id = str(uuid.uuid4())
    _insert_delivery(
        seeded_console_database_url,
        delivery_id=delivery_id,
        destination="queue_only",
        status="failed",
        target_type="generic_queue",
        target_identifier="manual-review",
        delivery_target_id=GENERIC_QUEUE_TARGET_ID,
    )
    try:
        retry_response = client.post(f"/console/deliveries/{delivery_id}/retry")
        assert retry_response.status_code == 200
        assert retry_response.json()["ok"] is True

        status_response = client.patch(f"/console/deliveries/{delivery_id}/status", json={"status": "acked"})
        assert status_response.status_code == 200
        assert status_response.json()["ok"] is True

        with psycopg.connect(seeded_console_database_url, row_factory=psycopg.rows.dict_row) as conn:
            row = conn.execute(
                "SELECT status::text AS status, destination::text AS destination FROM deliveries WHERE id = %s",
                (delivery_id,),
            ).fetchone()
        assert row is not None
        assert row["destination"] == "queue_only"
        assert row["status"] == "acked"
    finally:
        _delete_rows(seeded_console_database_url, "deliveries", [delivery_id])


def test_rule_patch_creates_append_only_ruleset_version(
    seeded_console_database_url: str,
    client: TestClient,
) -> None:
    ruleset_name = f"contract-ruleset-{uuid.uuid4().hex[:8]}"
    with psycopg.connect(seeded_console_database_url, row_factory=psycopg.rows.dict_row, autocommit=True) as conn:
        ruleset = conn.execute(
            """
            INSERT INTO rulesets (name, scope, project_id, version, is_active, description)
            VALUES (%s, 'project', %s, 11, TRUE, 'contract test ruleset')
            RETURNING id
            """,
            (ruleset_name, PROJECT_ID),
        ).fetchone()
        assert ruleset is not None
        original_ruleset_id = str(ruleset["id"])
        rule = conn.execute(
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
                'routing',
                30,
                TRUE,
                '{"field":"destination"}'::jsonb,
                '{"default_destination":"queue_only"}'::jsonb,
                'contract test rule'
            )
            RETURNING id
            """,
            (original_ruleset_id,),
        ).fetchone()
        assert rule is not None
        patched_rule_id = str(rule["id"])
        conn.execute(
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
                'cleanup',
                40,
                TRUE,
                '{"stage":"preprocess"}'::jsonb,
                '{"collapse_spaces":true}'::jsonb,
                'sibling rule'
            )
            """,
            (original_ruleset_id,),
        )

    try:
        response = client.patch(
            f"/console/rules/{patched_rule_id}",
            json={"enabled": False, "priority": 17},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

        with psycopg.connect(seeded_console_database_url, row_factory=psycopg.rows.dict_row) as conn:
            rulesets = conn.execute(
                """
                SELECT id, version, is_active
                FROM rulesets
                WHERE name = %s
                  AND scope = 'project'
                  AND project_id = %s
                ORDER BY version ASC
                """,
                (ruleset_name, PROJECT_ID),
            ).fetchall()
            assert len(rulesets) == 2
            assert int(rulesets[0]["version"]) == 11
            assert bool(rulesets[0]["is_active"]) is False
            assert int(rulesets[1]["version"]) == 12
            assert bool(rulesets[1]["is_active"]) is True
            new_ruleset_id = str(rulesets[1]["id"])

            old_rule = conn.execute(
                "SELECT enabled, priority FROM rules WHERE ruleset_id = %s AND id = %s",
                (original_ruleset_id, patched_rule_id),
            ).fetchone()
            assert old_rule is not None
            assert bool(old_rule["enabled"]) is True
            assert int(old_rule["priority"]) == 30

            patched_rule = conn.execute(
                """
                SELECT enabled, priority
                FROM rules
                WHERE ruleset_id = %s
                  AND notes = 'contract test rule'
                """,
                (new_ruleset_id,),
            ).fetchone()
            assert patched_rule is not None
            assert bool(patched_rule["enabled"]) is False
            assert int(patched_rule["priority"]) == 17
    finally:
        with psycopg.connect(seeded_console_database_url, autocommit=True) as conn:
            conn.execute(
                """
                DELETE FROM rulesets
                WHERE name = %s
                  AND scope = 'project'
                  AND project_id = %s
                """,
                (ruleset_name, PROJECT_ID),
            )


def test_template_patch_creates_append_only_version_row(
    seeded_console_database_url: str,
    client: TestClient,
) -> None:
    family_key = f"contract-template-family-{uuid.uuid4().hex[:8]}"
    with psycopg.connect(seeded_console_database_url, row_factory=psycopg.rows.dict_row, autocommit=True) as conn:
        template = conn.execute(
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
                'contract-template',
                'global',
                NULL,
                'planning',
                1,
                'Body v1',
                %s,
                TRUE
            )
            RETURNING id
            """,
            (family_key,),
        ).fetchone()
        assert template is not None
        template_id = str(template["id"])

    try:
        patch_response = client.patch(
            f"/console/templates/{template_id}",
            json={
                "body": "Body v2",
                "version": 2,
                "isActive": True,
            },
        )
        assert patch_response.status_code == 200
        body = patch_response.json()["prompt_template"]
        assert body["version"] == 2
        assert body["body"] == "Body v2"
        assert body["is_active"] is True
        new_template_id = body["id"]
        assert new_template_id != template_id

        with psycopg.connect(seeded_console_database_url, row_factory=psycopg.rows.dict_row) as conn:
            rows = conn.execute(
                """
                SELECT id, version, body_template, is_active
                FROM prompt_templates
                WHERE output_contract_name = %s
                ORDER BY version ASC
                """,
                (family_key,),
            ).fetchall()
        assert len(rows) == 2
        assert str(rows[0]["id"]) == template_id
        assert int(rows[0]["version"]) == 1
        assert rows[0]["body_template"] == "Body v1"
        assert bool(rows[0]["is_active"]) is False
        assert str(rows[1]["id"]) == new_template_id
        assert int(rows[1]["version"]) == 2
        assert rows[1]["body_template"] == "Body v2"
        assert bool(rows[1]["is_active"]) is True
    finally:
        with psycopg.connect(seeded_console_database_url, autocommit=True) as conn:
            conn.execute(
                "DELETE FROM prompt_templates WHERE output_contract_name = %s",
                (family_key,),
            )
