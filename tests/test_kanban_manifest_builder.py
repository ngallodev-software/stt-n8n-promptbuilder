from __future__ import annotations

from promptforge_services.console_models import PromptGenerationRecord
from promptforge_services.kanban_manifest_builder import (
    KanbanWorkspaceBinding,
    build_kanban_import_manifest,
    derive_external_task_key,
    validate_kanban_binding,
)


def _prompt_generation(**overrides: object) -> PromptGenerationRecord:
    payload = {
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
        "final_prompt_markdown": "  Build the feature.  ",
        "validation_warnings": [],
        "created_at": "2026-04-24T00:00:00Z",
        "updated_at": "2026-04-24T00:00:00Z",
    }
    payload.update(overrides)
    return PromptGenerationRecord.model_validate(payload)


def test_derive_external_task_key_is_stable() -> None:
    assert derive_external_task_key("pg_123") == "pf:pg:pg_123"


def test_validate_kanban_binding_requires_both_values() -> None:
    errors = validate_kanban_binding(KanbanWorkspaceBinding(kanbanBaseUrl="http://127.0.0.1:3000"))
    assert [error.code for error in errors] == ["kanban_binding_missing_workspace_id"]


def test_build_kanban_import_manifest_returns_v1_payload() -> None:
    result = build_kanban_import_manifest(
        _prompt_generation(),
        KanbanWorkspaceBinding(
            kanbanBaseUrl="http://127.0.0.1:3000",
            kanbanWorkspaceId="workspace-123",
        ),
    )

    assert result.ok is True
    assert result.errors == []
    assert result.manifest is not None
    assert result.manifest.model_dump(by_alias=True, exclude_none=True) == {
        "version": "v1",
        "tasks": [
            {
                "externalTaskKey": "pf:pg:pg_123",
                "prompt": "Build the feature.",
            }
        ],
        "links": [],
    }


def test_build_kanban_import_manifest_fails_without_prompt() -> None:
    result = build_kanban_import_manifest(
        _prompt_generation(final_prompt_markdown="   "),
        KanbanWorkspaceBinding(
            kanbanBaseUrl="http://127.0.0.1:3000",
            kanbanWorkspaceId="workspace-123",
        ),
    )

    assert result.ok is False
    assert [error.code for error in result.errors] == ["kanban_manifest_missing_prompt"]


def test_build_kanban_import_manifest_fails_without_binding() -> None:
    result = build_kanban_import_manifest(_prompt_generation(), None)

    assert result.ok is False
    assert [error.code for error in result.errors] == [
        "kanban_binding_missing_base_url",
        "kanban_binding_missing_workspace_id",
    ]
