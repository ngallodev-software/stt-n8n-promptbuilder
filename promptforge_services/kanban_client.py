from __future__ import annotations

from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx

from promptforge_services.kanban_manifest_builder import (
    KanbanImportManifest,
    KanbanImportResponse,
    KanbanWorkspaceBinding,
)
from promptforge_services.console_models import KanbanWorkspaceDiscoveryResponse


class KanbanImportClientError(RuntimeError):
    pass


def _rewrite_loopback_base_url(base_url: str) -> str | None:
    parsed = urlsplit(base_url)
    hostname = (parsed.hostname or "").lower()
    if hostname not in {"127.0.0.1", "localhost"}:
        return None
    if parsed.port is not None:
        netloc = f"host.docker.internal:{parsed.port}"
    else:
        netloc = "host.docker.internal"
    rewritten = SplitResult(
        scheme=parsed.scheme,
        netloc=netloc,
        path=parsed.path,
        query=parsed.query,
        fragment=parsed.fragment,
    )
    return urlunsplit(rewritten).rstrip("/")


def _candidate_base_urls(base_url: str) -> list[str]:
    normalized = base_url.rstrip("/")
    if not normalized:
        return []
    candidates = [normalized]
    rewritten = _rewrite_loopback_base_url(normalized)
    if rewritten and rewritten not in candidates:
        candidates.append(rewritten)
    return candidates


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


def _request_with_loopback_fallback(
    *,
    method: str,
    base_url: str,
    path: str,
    timeout_seconds: float,
    headers: dict[str, str] | None = None,
    json_payload: object | None = None,
) -> tuple[httpx.Response, str]:
    candidates = _candidate_base_urls(base_url)
    if not candidates:
        raise KanbanImportClientError("kanban_base_url_missing")

    last_error: httpx.HTTPError | None = None
    for candidate in candidates:
        try:
            response = httpx.request(
                method,
                f"{candidate}{path}",
                headers=headers,
                json=json_payload,
                timeout=timeout_seconds,
            )
            return response, candidate
        except httpx.HTTPError as exc:
            last_error = exc

    assert last_error is not None
    tried = ",".join(candidates)
    raise KanbanImportClientError(
        f"kanban_transport_error:{last_error.__class__.__name__}:tried={tried}"
    ) from last_error


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

    response, _ = _request_with_loopback_fallback(
        method="POST",
        base_url=base_url,
        path="/api/trpc/workspace.importTasks",
        headers={
            "Content-Type": "application/json",
            "x-kanban-workspace-id": workspace_id,
        },
        json_payload=manifest.model_dump(by_alias=True, exclude_none=True),
        timeout_seconds=timeout_seconds,
    )

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

    response, _ = _request_with_loopback_fallback(
        method="GET",
        base_url=base_url,
        path="/api/trpc/projects.list",
        timeout_seconds=timeout_seconds,
    )

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
