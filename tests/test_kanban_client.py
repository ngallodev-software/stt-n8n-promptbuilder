from __future__ import annotations

import pytest
import httpx

from promptforge_services.kanban_client import KanbanImportClientError, import_kanban_manifest
from promptforge_services.kanban_manifest_builder import (
    KanbanImportManifest,
    KanbanImportTask,
    KanbanWorkspaceBinding,
)


class _Response:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload


def test_import_kanban_manifest_unwraps_trpc_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, *, headers: dict[str, str], json: object, timeout: float) -> _Response:
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response(
            200,
            [
                {
                    "result": {
                        "data": {
                            "json": {
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
                            }
                        }
                    }
                }
            ],
        )

    monkeypatch.setattr("promptforge_services.kanban_client.httpx.post", fake_post)

    result = import_kanban_manifest(
        binding=KanbanWorkspaceBinding(
            kanbanBaseUrl="http://127.0.0.1:3000",
            kanbanWorkspaceId="workspace-123",
        ),
        manifest=KanbanImportManifest(
            tasks=[KanbanImportTask(externalTaskKey="pf:pg:pg_123", prompt="Build the feature.")]
        ),
    )

    assert captured["url"] == "http://127.0.0.1:3000/api/trpc/workspace.importTasks"
    assert captured["headers"] == {
        "Content-Type": "application/json",
        "x-kanban-workspace-id": "workspace-123",
    }
    assert result.ok is True
    assert result.applied is True
    assert result.task_mappings[0].task_id == "task-1"


def test_import_kanban_manifest_raises_for_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(*args: object, **kwargs: object) -> _Response:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("promptforge_services.kanban_client.httpx.post", fake_post)

    with pytest.raises(KanbanImportClientError, match="kanban_transport_error"):
        import_kanban_manifest(
            binding=KanbanWorkspaceBinding(
                kanbanBaseUrl="http://127.0.0.1:3000",
                kanbanWorkspaceId="workspace-123",
            ),
            manifest=KanbanImportManifest(
                tasks=[KanbanImportTask(externalTaskKey="pf:pg:pg_123", prompt="Build the feature.")]
            ),
        )
