from __future__ import annotations

from typing import Any

import httpx

from promptforge_services.kanban_manifest_builder import (
    KanbanImportManifest,
    KanbanImportResponse,
    KanbanWorkspaceBinding,
)
from promptforge_services.console_models import KanbanWorkspaceDiscoveryResponse


class KanbanImportClientError(RuntimeError):
    pass


def _unwrap_trpc_payload(value: Any) -> Any:
    envelope = value[0] if isinstance(value, list) and value else value
    if not isinstance(envelope, dict):
        return value
    result = envelope.get("result")
    if isinstance(result, dict):
        data = result.get("data")
        if isinstance(data, dict) and "json" in data:
            return data["json"]
        return data
    if "error" in envelope:
        return envelope["error"]
    return value


def import_kanban_manifest(
    *,
    binding: KanbanWorkspaceBinding,
    manifest: KanbanImportManifest,
    timeout_seconds: float = 20.0,
) -> KanbanImportResponse:
    base_url = (binding.kanban_base_url or "").rstrip("/")
    workspace_id = (binding.kanban_workspace_id or "").strip()
    if not base_url or not workspace_id:
        raise KanbanImportClientError("kanban_binding_invalid")

    try:
        response = httpx.post(
            f"{base_url}/api/trpc/workspace.importTasks",
            headers={
                "Content-Type": "application/json",
                "x-kanban-workspace-id": workspace_id,
            },
            json=manifest.model_dump(by_alias=True, exclude_none=True),
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise KanbanImportClientError(f"kanban_transport_error:{exc.__class__.__name__}") from exc

    payload = _unwrap_trpc_payload(response.json())
    if response.status_code != 200:
        raise KanbanImportClientError(f"kanban_http_error:{response.status_code}:{payload}")
    if not isinstance(payload, dict):
        raise KanbanImportClientError("kanban_response_invalid")
    return KanbanImportResponse.model_validate(payload)


def list_kanban_workspaces(
    *,
    kanban_base_url: str,
    timeout_seconds: float = 20.0,
) -> KanbanWorkspaceDiscoveryResponse:
    base_url = kanban_base_url.rstrip("/")
    if not base_url:
        raise KanbanImportClientError("kanban_base_url_missing")

    try:
        response = httpx.get(
            f"{base_url}/api/trpc/projects.list",
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise KanbanImportClientError(f"kanban_transport_error:{exc.__class__.__name__}") from exc

    payload = _unwrap_trpc_payload(response.json())
    if response.status_code != 200:
        raise KanbanImportClientError(f"kanban_http_error:{response.status_code}:{payload}")
    if not isinstance(payload, dict):
        raise KanbanImportClientError("kanban_response_invalid")

    normalized = {
        "currentWorkspaceId": payload.get("currentProjectId"),
        "workspaces": [
            {
                "workspaceId": workspace.get("id"),
                "name": workspace.get("name"),
                "path": workspace.get("path"),
                "taskCounts": {
                    "backlog": (workspace.get("taskCounts") or {}).get("backlog", 0),
                    "inProgress": (workspace.get("taskCounts") or {}).get("in_progress", 0),
                    "review": (workspace.get("taskCounts") or {}).get("review", 0),
                    "trash": (workspace.get("taskCounts") or {}).get("trash", 0),
                },
            }
            for workspace in payload.get("projects", [])
        ],
    }
    return KanbanWorkspaceDiscoveryResponse.model_validate(normalized)
