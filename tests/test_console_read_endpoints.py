from __future__ import annotations

import pytest
from fastapi import HTTPException

from promptforge_services.console_api import (
    console_bootstrap,
    error_fingerprints,
    get_intake_lineage,
    get_intake_note,
    list_deliveries,
    list_dictionary_terms,
    list_failed_processing_runs,
    list_intake_notes,
    list_logs,
    list_projects,
    list_prompt_templates,
    list_prompts,
    list_delivery_targets,
    list_rules,
    list_rulesets,
    project_throughput,
    queue_depth,
    sla_summary,
)


PROJECTS_ENDPOINT = "/console/projects"
INTAKE_ENDPOINT = "/console/intake"
INTAKE_DETAIL_ENDPOINT = "/console/intake/aaaaaaaa-0000-4000-8000-000000000001"
INTAKE_LINEAGE_ENDPOINT = "/console/lineage/aaaaaaaa-0000-4000-8000-000000000001"
PROMPTS_ENDPOINT = "/console/prompts"
DELIVERIES_ENDPOINT = "/console/deliveries"
FAILED_PROCESSING_ENDPOINT = "/console/processing/failed"
RULESETS_ENDPOINT = "/console/rulesets"
RULES_ENDPOINT = "/console/rules"
DICTIONARY_ENDPOINT = "/console/dictionary"
TEMPLATES_ENDPOINT = "/console/templates"
TARGETS_ENDPOINT = "/console/targets"
LOGS_ENDPOINT = "/console/logs"
QUEUE_DEPTH_ENDPOINT = "/console/metrics/queue-depth"
THROUGHPUT_ENDPOINT = "/console/metrics/throughput"
SLA_ENDPOINT = "/console/metrics/sla"
ERROR_FINGERPRINTS_ENDPOINT = "/console/metrics/error-fingerprints"
BOOTSTRAP_ENDPOINT = "/console/bootstrap"

SUCCESS_NOTE_ID = "aaaaaaaa-0000-4000-8000-000000000001"
FAILURE_NOTE_ID = "aaaaaaaa-0000-4000-8000-000000000002"
QUEUE_NOTE_ID = "aaaaaaaa-0000-4000-8000-000000000003"
PROJECT_ID = "22222222-2222-4222-8222-222222222222"


@pytest.fixture()
def seeded_console_database_url: str:
    # The session fixture in conftest seeds the dedicated test schema and keeps
    # PROMPTFORGE_DATABASE_URL pointed at it for the duration of the session.
    return ""


def _as_dict(value: object) -> dict[str, object]:
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True)  # type: ignore[no-any-return]
    assert isinstance(value, dict)
    return value


def _assert_paginated(body: dict[str, object], *, total: int) -> None:
    pagination = body["pagination"]
    assert pagination["total"] == total
    assert pagination["has_more"] is False


def test_console_bootstrap_without_database_returns_expected_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROMPTFORGE_DATABASE_URL", raising=False)
    body = console_bootstrap()

    assert set(body) == {
        "projects",
        "intakeNotes",
        "utterances",
        "transcriptRevisions",
        "promptGenerations",
        "deliveries",
        "deliveryHistory",
        "processingRuns",
        "llmRuns",
        "rulesets",
        "rules",
        "termDictionary",
        "promptTemplates",
        "deliveryTargets",
        "logs",
        "healthSnapshot",
    }
    assert set(body["healthSnapshot"]) == {"api", "providers", "db", "queue_depth", "failures_24h"}


def test_console_bootstrap_with_database_keeps_original_shape(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    body = console_bootstrap()

    assert set(body) == {
        "projects",
        "intakeNotes",
        "utterances",
        "transcriptRevisions",
        "promptGenerations",
        "deliveries",
        "deliveryHistory",
        "processingRuns",
        "llmRuns",
        "rulesets",
        "rules",
        "termDictionary",
        "promptTemplates",
        "deliveryTargets",
        "logs",
        "healthSnapshot",
    }
    assert body["projects"]
    assert body["intakeNotes"]
    assert body["deliveries"]
    assert body["processingRuns"]
    assert set(body["healthSnapshot"]) == {"api", "providers", "db", "queue_depth", "failures_24h"}


@pytest.mark.parametrize(
    ("func", "kwargs"),
    [
        (list_projects, {"limit": "0"}),
        (list_intake_notes, {"offset": "-1"}),
        (list_prompts, {"status": "not-a-real-status"}),
        (list_deliveries, {"limit": "0"}),
        (list_failed_processing_runs, {"offset": "-1"}),
        (list_rulesets, {"scope": "not-a-scope"}),
        (list_rules, {"limit": "-1"}),
        (list_dictionary_terms, {"scope": "not-a-scope"}),
        (list_prompt_templates, {"offset": "-1"}),
        (list_delivery_targets, {"type": "not-a-target"}),
        (list_logs, {"level": "verbose"}),
        (queue_depth, {"priority": "super-high"}),
        (queue_depth, {"destination": "space"}),
        (project_throughput, {"window_hours": "0"}),
        (sla_summary, {"target_seconds": "0"}),
        (error_fingerprints, {"level": "verbose"}),
    ],
)
def test_console_read_endpoints_reject_invalid_params(func, kwargs) -> None:
    with pytest.raises(HTTPException) as exc_info:
        func(**kwargs)
    assert exc_info.value.status_code == 400
    assert str(exc_info.value.detail).startswith("invalid_")


@pytest.mark.parametrize(
    "func, kwargs",
    [
        (list_projects, {}),
        (list_intake_notes, {}),
        (get_intake_note, {"id": SUCCESS_NOTE_ID}),
        (get_intake_lineage, {"intakeNoteId": SUCCESS_NOTE_ID}),
        (list_prompts, {}),
        (list_deliveries, {}),
        (list_failed_processing_runs, {}),
        (list_rulesets, {}),
        (list_rules, {}),
        (list_dictionary_terms, {}),
        (list_prompt_templates, {}),
        (list_delivery_targets, {}),
        (list_logs, {}),
        (queue_depth, {}),
        (project_throughput, {}),
        (sla_summary, {}),
        (error_fingerprints, {}),
    ],
)
def test_console_read_endpoints_return_503_without_database(monkeypatch: pytest.MonkeyPatch, func, kwargs) -> None:
    monkeypatch.delenv("PROMPTFORGE_DATABASE_URL", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        func(**kwargs)
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "database_unconfigured"


def test_console_projects_happy_path(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    body = _as_dict(list_projects())

    _assert_paginated(body, total=3)
    assert [project["slug"] for project in body["projects"]] == ["promptforge", "the-tax-machine", "inbox"]


def test_console_intake_happy_path_and_filters(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    body = _as_dict(list_intake_notes(project_id=PROJECT_ID, status="processed"))
    _assert_paginated(body, total=1)
    assert body["intakeNotes"][0]["id"] == SUCCESS_NOTE_ID
    assert body["intakeNotes"][0]["status"] == "processed"

    body = _as_dict(list_intake_notes(project_id=PROJECT_ID))
    _assert_paginated(body, total=2)
    assert {row["id"] for row in body["intakeNotes"]} == {SUCCESS_NOTE_ID, QUEUE_NOTE_ID}


def test_console_intake_detail_and_not_found(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    body = _as_dict(get_intake_note(SUCCESS_NOTE_ID))
    assert body["note"]["id"] == SUCCESS_NOTE_ID
    assert body["note"]["status"] == "processed"

    with pytest.raises(HTTPException) as exc_info:
        get_intake_note("00000000-0000-4000-8000-000000000000")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "intake_note_not_found"


def test_console_lineage_happy_path_and_not_found(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    body = _as_dict(get_intake_lineage(SUCCESS_NOTE_ID))
    assert body["intake_note"]["id"] == SUCCESS_NOTE_ID
    assert [row["id"] for row in body["utterances"]] == ["bbbbbbbb-0000-4000-8000-000000000001"]
    assert [row["id"] for row in body["revisions"]] == [
        "cccccccc-0000-4000-8000-000000000001",
        "cccccccc-0000-4000-8000-000000000002",
    ]
    assert [row["id"] for row in body["promptGenerations"]] == ["dddddddd-0000-4000-8000-000000000001"]
    assert [row["id"] for row in body["deliveries"]] == ["eeeeeeee-0000-4000-8000-000000000001"]
    assert [row["id"] for row in body["processingRuns"]] == ["ffffffff-0000-4000-8000-000000000001"]

    with pytest.raises(HTTPException) as exc_info:
        get_intake_lineage("00000000-0000-4000-8000-000000000000")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "intake_note_not_found"


def test_console_prompts_happy_path_and_filters(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    body = _as_dict(list_prompts(intake_note_id=SUCCESS_NOTE_ID, status="rendered"))
    _assert_paginated(body, total=1)
    assert body["promptGenerations"][0]["id"] == "dddddddd-0000-4000-8000-000000000001"
    assert body["promptGenerations"][0]["status"] == "rendered"


def test_console_deliveries_happy_path_and_filters(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    body = _as_dict(list_deliveries(prompt_generation_id="dddddddd-0000-4000-8000-000000000001"))
    _assert_paginated(body, total=1)
    assert body["deliveries"][0]["id"] == "eeeeeeee-0000-4000-8000-000000000001"
    assert body["deliveries"][0]["status"] == "delivered"


def test_console_processing_failed_happy_path(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    body = _as_dict(list_failed_processing_runs())
    _assert_paginated(body, total=2)
    assert {row["status"] for row in body["processingRuns"]} == {"failed"}


def test_console_rulesets_and_rules_happy_path(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    body = _as_dict(list_rulesets())
    _assert_paginated(body, total=3)
    assert {row["scope"] for row in body["rulesets"]} == {"global", "project"}

    body = _as_dict(list_rules(ruleset_id="55555555-5555-4555-8555-555555555555"))
    _assert_paginated(body, total=2)
    assert {row["ruleset_id"] for row in body["rules"]} == {"55555555-5555-4555-8555-555555555555"}


def test_console_dictionary_templates_and_targets_happy_path(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    body = _as_dict(list_dictionary_terms(scope="project", project_id=PROJECT_ID))
    _assert_paginated(body, total=4)
    assert all(row["scope"] == "project" for row in body["termDictionary"])

    body = _as_dict(list_prompt_templates(scope="project", project_id=PROJECT_ID))
    _assert_paginated(body, total=1)
    assert body["promptTemplates"][0]["template_family_key"] == "agent_task_v1"

    body = _as_dict(list_delivery_targets(type="claude_session"))
    _assert_paginated(body, total=2)
    assert {row["target_type"] for row in body["deliveryTargets"]} == {"claude_session"}


def test_console_logs_happy_path_and_filters(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    body = _as_dict(list_logs(level="error", service="api", intake_note_id=FAILURE_NOTE_ID))
    assert body["pagination"]["total"] >= 2
    assert all(row["level"] == "error" for row in body["logs"])
    assert all(row["service"] == "api" for row in body["logs"])
    assert all(row["intake_note_id"] == FAILURE_NOTE_ID for row in body["logs"])


def test_console_metrics_queue_depth_throughput_sla_and_fingerprints(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    body = _as_dict(queue_depth())
    assert body["queue_depth"] == 2
    assert body["queued_count"] == 1
    assert body["dispatching_count"] == 1

    body = _as_dict(project_throughput(project_id=PROJECT_ID, window_hours="24"))
    assert body["project_id"] == PROJECT_ID
    assert body["project_slug"] == "the-tax-machine"
    assert body["completed_count"] == 1
    assert body["failed_count"] == 1
    assert body["throughput_per_hour"] == pytest.approx(2 / 24)

    body = _as_dict(sla_summary(project_id=PROJECT_ID, target_seconds="3600", window_hours="24"))
    assert body["project_id"] == PROJECT_ID
    assert body["project_slug"] == "the-tax-machine"
    assert body["on_time_count"] == 1
    assert body["breached_count"] == 1
    assert body["on_time_rate"] == pytest.approx(0.5)

    body = _as_dict(error_fingerprints(level="error", service="api", limit="10"))
    assert body["pagination"]["total"] == 1
    fingerprint = body["errorFingerprints"][0]
    assert fingerprint["count"] == 2
    assert fingerprint["sample_message"] == "render failed"
    assert fingerprint["sample_context"]["intake_note_id"] == FAILURE_NOTE_ID


def test_console_metrics_project_filters_return_404_for_missing_project(seeded_console_database_url: str) -> None:
    del seeded_console_database_url
    with pytest.raises(HTTPException) as exc_info:
        project_throughput(project_id="00000000-0000-4000-8000-000000000000")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "project_not_found"

    with pytest.raises(HTTPException) as exc_info:
        sla_summary(project_id="00000000-0000-4000-8000-000000000000")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "project_not_found"
