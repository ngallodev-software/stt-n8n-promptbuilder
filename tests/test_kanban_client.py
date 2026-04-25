from __future__ import annotations

import pytest
import httpx

from promptforge_services.kanban_client import KanbanImportClientError, import_kanban_manifest, list_kanban_workspaces
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

    def fake_request(
        self: httpx.Client,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: object | None = None,
        timeout: float,
    ) -> _Response:
        del self
        captured["method"] = method
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

    monkeypatch.setattr("promptforge_services.kanban_client.httpx.Client.request", fake_request)

    result = import_kanban_manifest(
        binding=KanbanWorkspaceBinding(
            kanbanBaseUrl="http://127.0.0.1:3484",
            kanbanWorkspaceId="workspace-123",
        ),
        manifest=KanbanImportManifest(
            tasks=[KanbanImportTask(externalTaskKey="pf:pg:pg_123", prompt="Build the feature.")]
        ),
    )

    assert captured["method"] == "POST"
    assert captured["url"] == "http://127.0.0.1:3484/api/trpc/workspace.importTasks"
    assert captured["headers"] == {
        "Content-Type": "application/json",
        "x-kanban-workspace-id": "workspace-123",
    }
    assert result.ok is True
    assert result.applied is True
    assert result.task_mappings[0].task_id == "task-1"


def test_import_kanban_manifest_retries_loopback_host_for_containerized_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_urls: list[str] = []

    def fake_request(
        self: httpx.Client,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: object | None = None,
        timeout: float,
    ) -> _Response:
        del self, method, headers, json, timeout
        seen_urls.append(url)
        if url.startswith("http://127.0.0.1:3484"):
            raise httpx.ConnectError("boom")
        return _Response(
            200,
            [{"result": {"data": {"json": {"version": "v1", "ok": True, "applied": True, "taskMappings": [], "linkResults": [], "startResults": []}}}}],
        )

    monkeypatch.setattr("promptforge_services.kanban_client.httpx.Client.request", fake_request)

    result = import_kanban_manifest(
        binding=KanbanWorkspaceBinding(
            kanbanBaseUrl="http://127.0.0.1:3484",
            kanbanWorkspaceId="workspace-123",
        ),
        manifest=KanbanImportManifest(
            tasks=[KanbanImportTask(externalTaskKey="pf:pg:pg_123", prompt="Build the feature.")]
        ),
    )

    assert seen_urls == [
        "http://127.0.0.1:3484/api/trpc/workspace.importTasks",
        "http://host.docker.internal:3484/api/trpc/workspace.importTasks",
    ]
    assert result.ok is True


def test_import_kanban_manifest_raises_for_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(*args: object, **kwargs: object) -> _Response:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("promptforge_services.kanban_client.httpx.Client.request", fake_request)

    with pytest.raises(KanbanImportClientError, match="kanban_transport_error:ConnectError:tried="):
        import_kanban_manifest(
            binding=KanbanWorkspaceBinding(
                kanbanBaseUrl="http://127.0.0.1:3484",
                kanbanWorkspaceId="workspace-123",
            ),
            manifest=KanbanImportManifest(
                tasks=[KanbanImportTask(externalTaskKey="pf:pg:pg_123", prompt="Build the feature.")]
            ),
        )


def test_list_kanban_workspaces_unwraps_projects_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(
        self: httpx.Client,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: object | None = None,
        timeout: float,
    ) -> _Response:
        del self, method, headers, json
        assert url == "http://127.0.0.1:3484/api/trpc/projects.list"
        assert timeout == 20.0
        return _Response(
            200,
            {
                "result": {
                    "data": {
                        "currentProjectId": "workspace-123",
                        "projects": [
                            {
                                "id": "workspace-123",
                                "name": "alpha",
                                "path": "/tmp/alpha",
                                "taskCounts": {"backlog": 1, "in_progress": 2, "review": 3, "trash": 4},
                            }
                        ],
                    }
                }
            },
        )

    monkeypatch.setattr("promptforge_services.kanban_client.httpx.Client.request", fake_request)

    result = list_kanban_workspaces(kanban_base_url="http://127.0.0.1:3484")
    assert result.current_workspace_id == "workspace-123"
    assert result.workspaces[0].workspace_id == "workspace-123"
    assert result.workspaces[0].task_counts.in_progress == 2


def test_list_kanban_workspaces_retries_loopback_host_for_containerized_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_urls: list[str] = []

    def fake_request(
        self: httpx.Client,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: object | None = None,
        timeout: float,
    ) -> _Response:
        del self, method, headers, json, timeout
        seen_urls.append(url)
        if url.startswith("http://127.0.0.1:3484"):
            raise httpx.ConnectError("boom")
        return _Response(200, {"result": {"data": {"currentProjectId": None, "projects": []}}})

    monkeypatch.setattr("promptforge_services.kanban_client.httpx.Client.request", fake_request)

    result = list_kanban_workspaces(kanban_base_url="http://127.0.0.1:3484")
    assert seen_urls == [
        "http://127.0.0.1:3484/api/trpc/projects.list",
        "http://host.docker.internal:3484/api/trpc/projects.list",
    ]
    assert result.workspaces == []


def test_list_kanban_workspaces_verifies_passcode_after_auth_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, str]] = []

    def fake_request(
        self: httpx.Client,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: object | None = None,
        timeout: float,
    ) -> _Response:
        del self, headers, timeout
        seen.append((method, url))
        if url.endswith("/api/trpc/projects.list") and len(seen) == 1:
            return _Response(401, {"error": "Authentication required."})
        if url.endswith("/api/passcode/verify"):
            assert json == {"passcode": "abc12345"}
            return _Response(200, {"ok": True})
        return _Response(200, {"result": {"data": {"currentProjectId": None, "projects": []}}})

    monkeypatch.setattr("promptforge_services.kanban_client.httpx.Client.request", fake_request)
    monkeypatch.setattr("promptforge_services.kanban_client.httpx.Client.post", lambda self, url, json=None, timeout=0: fake_request(self, "POST", url, json=json, timeout=timeout))

    result = list_kanban_workspaces(
        kanban_base_url="http://127.0.0.1:3484",
        kanban_passcode="abc12345",
    )
    assert seen == [
        ("GET", "http://127.0.0.1:3484/api/trpc/projects.list"),
        ("POST", "http://127.0.0.1:3484/api/passcode/verify"),
        ("GET", "http://127.0.0.1:3484/api/trpc/projects.list"),
    ]
    assert result.workspaces == []
