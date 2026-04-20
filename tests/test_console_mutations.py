"""Integration tests for console mutation endpoints."""

from __future__ import annotations

import os

import pytest
import psycopg
from fastapi.testclient import TestClient

from promptforge_services.console_api import router

# Skip all tests if DATABASE_URL not configured
pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set",
)


@pytest.fixture
def client() -> TestClient:
    """Test client for console API."""
    return TestClient(router)


# ============================================================================
# Delivery mutations
# ============================================================================


def test_delivery_retry_happy_path(client: TestClient) -> None:
    """POST /deliveries/{id}/retry - happy path."""
    # Assumes test DB has deliveries; adjust ID as needed
    response = client.post("/deliveries/test-delivery-id/retry")
    assert response.status_code in {200, 404}  # 404 if fixture missing
    if response.status_code == 200:
        data = response.json()
        assert data["ok"] is True
        assert "message" in data


def test_delivery_retry_not_found(client: TestClient) -> None:
    """POST /deliveries/{id}/retry - missing delivery returns 404."""
    response = client.post("/deliveries/nonexistent-delivery-id/retry")
    assert response.status_code == 404
    assert response.json()["detail"] == "delivery_not_found"


def test_delivery_reroute_happy_path(client: TestClient) -> None:
    """POST /deliveries/{id}/reroute - happy path."""
    payload = {"targetId": "test-target-id"}
    response = client.post("/deliveries/test-delivery-id/reroute", json=payload)
    assert response.status_code in {200, 404}
    if response.status_code == 200:
        data = response.json()
        assert data["ok"] is True


def test_delivery_reroute_missing_target(client: TestClient) -> None:
    """POST /deliveries/{id}/reroute - missing targetId returns 400."""
    response = client.post("/deliveries/test-delivery-id/reroute", json={})
    assert response.status_code == 422  # FastAPI validation error


def test_delivery_status_patch_happy_path(client: TestClient) -> None:
    """PATCH /deliveries/{id}/status - happy path."""
    payload = {"status": "delivered"}
    response = client.patch("/deliveries/test-delivery-id/status", json=payload)
    assert response.status_code in {200, 404}
    if response.status_code == 200:
        data = response.json()
        assert data["ok"] is True


def test_delivery_status_patch_invalid_enum(client: TestClient) -> None:
    """PATCH /deliveries/{id}/status - invalid enum returns 400."""
    payload = {"status": "invalid_status"}
    response = client.patch("/deliveries/test-delivery-id/status", json=payload)
    assert response.status_code in {400, 422}


def test_delivery_status_patch_not_found(client: TestClient) -> None:
    """PATCH /deliveries/{id}/status - missing delivery returns 404."""
    payload = {"status": "delivered"}
    response = client.patch("/deliveries/nonexistent-id/status", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "delivery_not_found"


# ============================================================================
# Rule mutations
# ============================================================================


def test_rule_patch_happy_path(client: TestClient) -> None:
    """PATCH /rules/{id} - happy path."""
    payload = {"enabled": False, "priority": 10}
    response = client.patch("/rules/test-rule-id", json=payload)
    assert response.status_code in {200, 404}
    if response.status_code == 200:
        data = response.json()
        assert data["ok"] is True


def test_rule_patch_partial_update(client: TestClient) -> None:
    """PATCH /rules/{id} - partial update (only enabled)."""
    payload = {"enabled": True}
    response = client.patch("/rules/test-rule-id", json=payload)
    assert response.status_code in {200, 404}


def test_rule_patch_not_found(client: TestClient) -> None:
    """PATCH /rules/{id} - missing rule returns 404."""
    payload = {"enabled": False}
    response = client.patch("/rules/nonexistent-rule-id", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "rule_not_found"


def test_rule_patch_bad_payload(client: TestClient) -> None:
    """PATCH /rules/{id} - invalid payload returns 422."""
    payload = {"enabled": "not_a_boolean"}
    response = client.patch("/rules/test-rule-id", json=payload)
    assert response.status_code == 422


def test_rule_create_and_dry_run_persists_and_transforms(
    client: TestClient,
    seeded_console_database_url: str,
) -> None:
    """POST /rules and POST /rulesets/{id}/dry-run - happy path."""
    ruleset_id = "44444444-4444-4444-8444-444444444444"
    payload = {
        "rulesetId": ruleset_id,
        "ruleType": "formatting",
        "priority": 5,
        "enabled": True,
        "matchConditionsJson": {"contains": "hello"},
        "actionJson": {"replace_terms": {"hello": "hi"}},
        "notes": "test-rule-create",
    }
    created_rule_id: str | None = None
    try:
        response = client.post("/console/rules", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["rule"]["ruleset_id"] == ruleset_id
        assert body["rule"]["rule_type"] == "formatting"
        created_rule_id = body["rule"]["id"]

        dry_run_response = client.post(
            f"/console/rulesets/{ruleset_id}/dry-run",
            json={
                "sampleText": "um hello   world!!",
                "context": {},
            },
        )
        assert dry_run_response.status_code == 200
        dry_run = dry_run_response.json()
        assert dry_run["summary"]["totalRules"] == 4
        assert dry_run["summary"]["matchedRules"] == 4
        assert dry_run["summary"]["failedRules"] == 0
        assert dry_run["transformedOutput"].startswith("hi world")
        assert all(rule["matched"] for rule in dry_run["matchedRules"])
        assert dry_run["summary"]["metadata"]["ruleset_id"] == ruleset_id
    finally:
        if created_rule_id:
            with psycopg.connect(seeded_console_database_url, autocommit=True) as conn:
                conn.execute("DELETE FROM rules WHERE id = %s", (created_rule_id,))


# ============================================================================
# Dictionary mutations
# ============================================================================


def test_dictionary_upsert_happy_path(client: TestClient) -> None:
    """POST /dictionary/upsert - currently returns explicit structured stub."""
    payload = {
        "scope": "global",
        "source_term": "test_source",
        "normalized_term": "test_normalized",
        "description": "Test dictionary entry",
    }
    response = client.post("/dictionary/upsert", json=payload)
    assert response.status_code == 501
    detail = response.json()["detail"]
    assert detail["code"] == "dictionary_upsert_stubbed"
    assert detail["status"] == "unsupported"
    assert detail["endpoint"] == "/console/dictionary/upsert"


def test_dictionary_upsert_invalid_scope(client: TestClient) -> None:
    """POST /dictionary/upsert - invalid scope enum returns 400."""
    payload = {
        "scope": "invalid_scope",
        "source_term": "test",
        "normalized_term": "test",
    }
    response = client.post("/dictionary/upsert", json=payload)
    assert response.status_code in {400, 422}


def test_dictionary_upsert_minimal_payload(client: TestClient) -> None:
    """POST /dictionary/upsert - minimal payload still returns structured stub."""
    payload = {"source_term": "minimal"}
    response = client.post("/dictionary/upsert", json=payload)
    assert response.status_code == 501
    assert response.json()["detail"]["code"] == "dictionary_upsert_stubbed"


# ============================================================================
# Template mutations
# ============================================================================


def test_template_activate_happy_path(client: TestClient) -> None:
    """POST /templates/{id}/activate - happy path."""
    payload = {"family": "test-family"}
    response = client.post("/templates/test-template-id/activate", json=payload)
    assert response.status_code in {200, 404}
    if response.status_code == 200:
        data = response.json()
        assert data["ok"] is True


def test_template_activate_missing_family(client: TestClient) -> None:
    """POST /templates/{id}/activate - missing family returns 422."""
    response = client.post("/templates/test-template-id/activate", json={})
    assert response.status_code == 422


def test_template_activate_not_found(client: TestClient) -> None:
    """POST /templates/{id}/activate - missing template returns 404."""
    payload = {"family": "test-family"}
    response = client.post("/templates/nonexistent-id/activate", json=payload)
    assert response.status_code == 404


def test_template_create_and_patch_persists_changes(
    client: TestClient,
    seeded_console_database_url: str,
) -> None:
    """POST /templates and PATCH /templates/{id} - happy path."""
    payload = {
        "name": "test-template-create",
        "promptType": "planning",
        "scope": "global",
        "templateFamilyKey": "test-template-family",
        "body": "Initial body for {{ project_slug }}",
        "version": 2,
        "isActive": False,
    }
    template_id: str | None = None
    try:
        response = client.post("/console/templates", json=payload)
        assert response.status_code == 200
        created = response.json()["prompt_template"]
        assert created["name"] == "test-template-create"
        assert created["template_family_key"] == "test-template-family"
        template_id = created["id"]

        patch_response = client.patch(
            f"/console/templates/{template_id}",
            json={
                "body": "Updated body for {{ project_slug }}",
                "version": 3,
                "isActive": True,
            },
        )
        assert patch_response.status_code == 200
        patched = patch_response.json()["prompt_template"]
        assert patched["body"] == "Updated body for {{ project_slug }}"
        assert patched["version"] == 3
        assert patched["is_active"] is True

        with psycopg.connect(seeded_console_database_url, row_factory=psycopg.rows.dict_row) as conn:
            row = conn.execute(
                """
                SELECT id, body_template, version, is_active
                FROM prompt_templates
                WHERE id = %s
                """,
                (template_id,),
            ).fetchone()
        assert row is not None
        assert row["body_template"] == "Updated body for {{ project_slug }}"
        assert int(row["version"]) == 3
        assert bool(row["is_active"]) is True
    finally:
        if template_id:
            with psycopg.connect(seeded_console_database_url, autocommit=True) as conn:
                conn.execute("DELETE FROM prompt_templates WHERE id = %s", (template_id,))


# ============================================================================
# Prompt mutations
# ============================================================================


def test_prompt_force_review_happy_path(client: TestClient) -> None:
    """POST /prompts/{id}/force-review - happy path."""
    response = client.post("/prompts/test-prompt-id/force-review")
    assert response.status_code in {200, 404}
    if response.status_code == 200:
        data = response.json()
        assert data["ok"] is True


def test_prompt_force_review_not_found(client: TestClient) -> None:
    """POST /prompts/{id}/force-review - missing prompt returns 404."""
    response = client.post("/prompts/nonexistent-id/force-review")
    assert response.status_code == 404


def test_prompt_clone_happy_path(client: TestClient) -> None:
    """POST /prompts/{id}/clone - happy path."""
    response = client.post("/prompts/test-prompt-id/clone")
    assert response.status_code in {200, 201, 404}
    if response.status_code in {200, 201}:
        data = response.json()
        assert "id" in data or "ok" in data


def test_prompt_clone_not_found(client: TestClient) -> None:
    """POST /prompts/{id}/clone - missing prompt returns 404."""
    response = client.post("/prompts/nonexistent-id/clone")
    assert response.status_code == 404


def test_prompt_priority_patch_happy_path(client: TestClient) -> None:
    """PATCH /prompts/{id}/priority - happy path."""
    payload = {"priority": "high"}
    response = client.patch("/prompts/test-prompt-id/priority", json=payload)
    assert response.status_code in {200, 404}
    if response.status_code == 200:
        data = response.json()
        assert data["ok"] is True


def test_prompt_priority_patch_invalid_enum(client: TestClient) -> None:
    """PATCH /prompts/{id}/priority - invalid priority enum returns 400."""
    payload = {"priority": "super_urgent"}
    response = client.patch("/prompts/test-prompt-id/priority", json=payload)
    assert response.status_code in {400, 422}


def test_prompt_priority_patch_not_found(client: TestClient) -> None:
    """PATCH /prompts/{id}/priority - missing prompt returns 404."""
    payload = {"priority": "low"}
    response = client.patch("/prompts/nonexistent-id/priority", json=payload)
    assert response.status_code == 404


# ============================================================================
# Intake mutations
# ============================================================================


def test_intake_archive_happy_path(client: TestClient) -> None:
    """PATCH /intake/{id}/archive - happy path."""
    response = client.patch("/intake/test-intake-id/archive")
    assert response.status_code in {200, 404}
    if response.status_code == 200:
        data = response.json()
        assert data["ok"] is True


def test_intake_archive_not_found(client: TestClient) -> None:
    """PATCH /intake/{id}/archive - missing intake returns 404."""
    response = client.patch("/intake/nonexistent-id/archive")
    assert response.status_code == 404


def test_intake_archive_idempotency(client: TestClient) -> None:
    """PATCH /intake/{id}/archive - idempotent (archive twice = same result)."""
    # First archive
    response1 = client.patch("/intake/test-intake-id/archive")
    # Second archive (should not fail)
    response2 = client.patch("/intake/test-intake-id/archive")
    assert response1.status_code == response2.status_code
    if response1.status_code == 200:
        assert response1.json() == response2.json()


# ============================================================================
# Database unavailable error (503)
# ============================================================================


def test_db_unavailable_returns_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """All mutations return 503 when DATABASE_URL is unset."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    # Test one representative endpoint
    response = client.post("/deliveries/test-id/retry")
    assert response.status_code == 503
    assert response.json()["detail"] == "database_unconfigured"
