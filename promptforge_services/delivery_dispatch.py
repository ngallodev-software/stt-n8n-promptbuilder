from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class TargetHealth:
    status: str
    detail: str | None = None
    attached: bool | None = None
    busy: bool | None = None
    reachable: bool | None = None
    stale: bool | None = None


@dataclass(slots=True)
class DispatchOutcome:
    accepted: bool
    status: str
    error_text: str | None = None
    external_identifier: str | None = None
    session_identifier: str | None = None
    request_summary: dict[str, Any] = field(default_factory=dict)
    response_summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


LIVE_SESSION_TARGET_TYPES = {"claude_session", "codex_session", "chat_session"}


def _vault_path() -> str:
    return os.getenv("PROMPTFORGE_VAULT_PATH", "/vault")


def compute_target_health(target_row: dict[str, Any]) -> TargetHealth:
    target_type = str(target_row.get("target_type") or "")
    config_json = target_row.get("config_json") or {}
    if target_type == "obsidian_note":
        target_folder = str(config_json.get("target_folder") or "").strip()
        vault_path = _vault_path()
        if not target_folder:
            return TargetHealth(
                status="degraded",
                detail="target_folder_missing",
                attached=False,
                busy=False,
                reachable=True,
                stale=False,
            )
        destination_dir = Path(vault_path) / target_folder
        if destination_dir.exists():
            return TargetHealth(
                status="ok",
                detail="obsidian_target_ready",
                attached=True,
                busy=False,
                reachable=True,
                stale=False,
            )
        return TargetHealth(
            status="degraded",
            detail=f"target_folder_missing:{target_folder}",
            attached=False,
            busy=False,
            reachable=True,
            stale=False,
        )
    if target_type == "generic_queue":
        queue_name = str(config_json.get("queue_name") or "").strip()
        if queue_name:
            return TargetHealth(
                status="ok",
                detail=f"queue_ready:{queue_name}",
                attached=True,
                busy=False,
                reachable=True,
                stale=False,
            )
        return TargetHealth(
            status="degraded",
            detail="queue_name_missing",
            attached=False,
            busy=False,
            reachable=True,
            stale=False,
        )
    if target_type in LIVE_SESSION_TARGET_TYPES:
        return TargetHealth(
            status="unknown",
            detail="live_session_registry_unavailable",
            attached=None,
            busy=None,
            reachable=None,
            stale=None,
        )
    return TargetHealth(
        status="error",
        detail=f"unsupported_target_type:{target_type}",
        attached=False,
        busy=False,
        reachable=False,
        stale=False,
    )


def dispatch_target_payload(
    *,
    target_row: dict[str, Any],
    payload_content: str,
    prompt_generation_id: str | None,
    delivery_id: str,
    target_session_identifier: str | None,
    dry_run: bool,
    vault_path: str | None = None,
) -> DispatchOutcome:
    target_type = str(target_row.get("target_type") or "")
    target_identifier = str(target_row.get("target_identifier") or "")
    request_summary = {
        "delivery_id": delivery_id,
        "target_id": str(target_row.get("id") or ""),
        "target_type": target_type,
        "target_identifier": target_identifier,
        "target_session_identifier": target_session_identifier,
        "prompt_generation_id": prompt_generation_id,
        "payload_length": len(payload_content),
        "dry_run": dry_run,
    }

    if target_type in LIVE_SESSION_TARGET_TYPES:
        message = f"{target_type.replace('_', ' ').title()} delivery is not implemented in this environment"
        if target_session_identifier:
            message = f"{message}: {target_session_identifier}"
        return DispatchOutcome(
            accepted=False,
            status="failed",
            error_text=message,
            request_summary=request_summary,
            response_summary={
                "accepted": False,
                "target_type": target_type,
                "machine_status": "unsupported",
            },
        )

    if target_type == "generic_queue":
        return DispatchOutcome(
            accepted=True,
            status="queued",
            external_identifier=str(target_row.get("config_json", {}).get("queue_name") or target_identifier),
            request_summary=request_summary,
            response_summary={
                "accepted": True,
                "machine_status": "queued",
                "queue_name": str(target_row.get("config_json", {}).get("queue_name") or target_identifier),
            },
        )

    if target_type == "obsidian_note":
        config_json = target_row.get("config_json") or {}
        target_folder = str(config_json.get("target_folder") or "").strip()
        if not target_folder:
            return DispatchOutcome(
                accepted=False,
                status="failed",
                error_text="obsidian_target_folder_missing",
                request_summary=request_summary,
                response_summary={"accepted": False, "machine_status": "degraded"},
            )
        resolved_vault_path = vault_path or _vault_path()
        output_dir = Path(resolved_vault_path) / target_folder
        if dry_run:
            return DispatchOutcome(
                accepted=True,
                status="queued",
                external_identifier=str(output_dir / f"{delivery_id}.prompt.md"),
                request_summary=request_summary,
                response_summary={
                    "accepted": True,
                    "machine_status": "preview",
                    "target_folder": target_folder,
                },
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{delivery_id}.prompt.md"
        frontmatter = {
            "pf_version": 1,
            "status": "processed",
            "created_by": "promptforge-console",
            "target_type": target_type,
            "target_identifier": target_identifier,
            "prompt_generation_id": prompt_generation_id,
            "delivery_id": delivery_id,
            "delivery_status": "delivered",
            "imported_at": _timestamp(),
        }
        output_path.write_text(_dump_note(frontmatter, payload_content), encoding="utf-8")
        return DispatchOutcome(
            accepted=True,
            status="delivered",
            external_identifier=str(output_path),
            request_summary=request_summary,
            response_summary={
                "accepted": True,
                "machine_status": "delivered",
                "output_path": str(output_path),
            },
        )

    return DispatchOutcome(
        accepted=False,
        status="failed",
        error_text=f"unsupported_target_type:{target_type}",
        request_summary=request_summary,
        response_summary={"accepted": False, "machine_status": "unsupported"},
    )


def _dump_note(frontmatter: dict[str, Any], body: str) -> str:
    serialized = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=False).strip()
    return f"---\n{serialized}\n---\n\n{body.strip()}\n"


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
