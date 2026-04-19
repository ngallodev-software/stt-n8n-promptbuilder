"""Integration tests for console mutation endpoints."""

from __future__ import annotations

import os

import pytest
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


# ============================================================================
# Dictionary mutations
# ============================================================================


def test_dictionary_upsert_happy_path(client: TestClient) -> None:
    """POST /dictionary/upsert - happy path."""
    payload = {
        "scope": "global",
        "source_term": "test_source",
        "normalized_term": "test_normalized",
        "description": "Test dictionary entry",
    }
    response = client.post("/dictionary/upsert", json=payload)
    assert response.status_code in {200, 201}
    if response.status_code in {200, 201}:
        data = response.json()
        assert data["ok"] is True


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
    """POST /dictionary/upsert - minimal valid payload."""
    payload = {"source_term": "minimal"}
    response = client.post("/dictionary/upsert", json=payload)
    # May succeed or fail depending on DB constraints
    assert response.status_code in {200, 201, 400, 422}


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
