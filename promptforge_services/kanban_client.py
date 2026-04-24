from __future__ import annotations

from typing import Any

import httpx

from promptforge_services.kanban_manifest_builder import (
    KanbanImportManifest,
    KanbanImportResponse,
    KanbanWorkspaceBinding,
)


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
