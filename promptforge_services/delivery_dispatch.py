from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
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
_SHELL_COMMANDS = {"bash", "zsh", "sh", "fish", "tmux"}
_LIVE_TARGET_OPTION_KEYS = {
    "claude_session": "@promptforge_claude_session_id",
    "codex_session": "@promptforge_codex_session_id",
}


@dataclass(slots=True)
class _LiveSessionMatch:
    reachable: bool
    detail: str
    session_name: str | None = None
    pane_target: str | None = None
    session_identifier: str | None = None
    attached: bool | None = None
    busy: bool | None = None
    stale: bool | None = None
    error_text: str | None = None


def _libtmux_server() -> Any:
    if not shutil.which("tmux"):
        raise RuntimeError("tmux_binary_missing")
    try:
        import libtmux  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on runtime environment
        raise RuntimeError("libtmux_not_installed") from exc
    try:
        return libtmux.Server()
    except Exception as exc:  # pragma: no cover - depends on runtime environment
        raise RuntimeError(f"tmux_server_unreachable:{exc.__class__.__name__}") from exc


def _live_identifier(
    *,
    target_type: str,
    target_identifier: str,
    target_session_identifier: str | None,
) -> str:
    raw = target_session_identifier if target_session_identifier else target_identifier
    text = str(raw or "").strip()
    if target_type in {"claude_session", "codex_session"}:
        return text
    return text


def _session_option(session: Any, key: str) -> str | None:
    try:
        option = session.show_option(key)
    except Exception:
        return None
    value = str(getattr(option, "value", "") or "").strip()
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        value = value[1:-1]
    return value or None


def _session_name(session: Any) -> str:
    try:
        value = session.get("session_name")
    except Exception:
        value = getattr(session, "name", "")
    return str(value or "")


def _session_attached(session: Any) -> bool:
    try:
        return bool(session.get("session_attached"))
    except Exception:
        return bool(getattr(session, "attached", False))


def _session_hint(config_json: dict[str, Any]) -> str:
    return str(config_json.get("session_hint") or "").strip()


def _select_pane(session: Any) -> tuple[str | None, bool | None]:
    try:
        window = session.attached_window if _session_attached(session) and session.attached_window is not None else session.windows[0]
    except Exception:
        return None, None
    pane = None
    for attr in ("attached_pane", "active_pane"):
        pane = getattr(window, attr, None)
        if pane is not None:
            break
    if pane is None:
        try:
            pane = window.panes[0]
        except Exception:
            return None, None
    pane_id = str(getattr(pane, "pane_id", "") or "").strip()
    if not pane_id:
        return None, None
    current_command = str(getattr(pane, "current_command", "") or "").strip().lower()
    busy = None if not current_command else current_command not in _SHELL_COMMANDS
    return pane_id, busy


def _resolve_live_session(
    *,
    target_type: str,
    target_identifier: str,
    config_json: dict[str, Any],
    requested_session_identifier: str | None,
) -> _LiveSessionMatch:
    desired_identifier = _live_identifier(
        target_type=target_type,
        target_identifier=target_identifier,
        target_session_identifier=requested_session_identifier,
    )
    if target_type in {"claude_session", "codex_session"} and not desired_identifier:
        return _LiveSessionMatch(
            reachable=False,
            stale=True,
            detail="session_identifier_required",
            error_text="missing session identifier for live session target",
        )
    try:
        server = _libtmux_server()
    except RuntimeError as exc:
        detail = str(exc)
        return _LiveSessionMatch(
            reachable=False,
            stale=None,
            detail=detail,
            error_text=f"live session registry unavailable: {detail}",
        )
    try:
        sessions = list(server.sessions)
    except Exception as exc:  # pragma: no cover - depends on tmux runtime
        detail = f"tmux_list_failed:{exc.__class__.__name__}"
        return _LiveSessionMatch(
            reachable=False,
            stale=None,
            detail=detail,
            error_text=f"live session registry unavailable: {detail}",
        )
    if not sessions:
        return _LiveSessionMatch(
            reachable=False,
            stale=True,
            detail="tmux_sessions_empty",
            error_text="no local tmux sessions available",
        )

    option_key = _LIVE_TARGET_OPTION_KEYS.get(target_type, "")
    hint = _session_hint(config_json)
    scored: list[tuple[int, Any]] = []
    for session in sessions:
        name = _session_name(session)
        attached = _session_attached(session)
        score = 0
        if target_type == "chat_session":
            if desired_identifier and name == desired_identifier:
                score += 100
            elif desired_identifier and desired_identifier in name:
                score += 40
            if attached:
                score += 60
        else:
            if option_key:
                opt_value = _session_option(session, option_key)
                if opt_value and desired_identifier and opt_value == desired_identifier:
                    score += 140
            if desired_identifier and name == desired_identifier:
                score += 120
            elif desired_identifier and desired_identifier in name:
                score += 60
            if hint and hint in name:
                score += 40
            if attached:
                score += 20
        if score > 0:
            scored.append((score, session))
    if not scored and target_type == "chat_session":
        for session in sessions:
            if _session_attached(session):
                scored.append((10, session))

    if not scored:
        missing = desired_identifier or target_identifier or target_type
        return _LiveSessionMatch(
            reachable=False,
            stale=True,
            detail=f"session_not_found:{missing}",
            error_text=f"no tmux session matched '{missing}'",
        )

    _, chosen = max(scored, key=lambda item: item[0])
    name = _session_name(chosen)
    attached = _session_attached(chosen)
    pane_target, busy = _select_pane(chosen)
    if not pane_target:
        return _LiveSessionMatch(
            reachable=False,
            session_name=name,
            session_identifier=desired_identifier or name,
            attached=attached,
            stale=False,
            detail=f"pane_unavailable:{name}",
            error_text=f"tmux session '{name}' has no writable pane",
        )
    if target_type == "chat_session" and not attached:
        return _LiveSessionMatch(
            reachable=False,
            session_name=name,
            pane_target=pane_target,
            session_identifier=desired_identifier or name,
            attached=False,
            busy=busy,
            stale=False,
            detail=f"chat_session_not_attached:{name}",
            error_text=f"chat session '{name}' is not attached",
        )
    return _LiveSessionMatch(
        reachable=True,
        detail=f"tmux_session_ready:{name}",
        session_name=name,
        pane_target=pane_target,
        session_identifier=desired_identifier or name,
        attached=attached,
        busy=busy,
        stale=False,
    )


def _dispatch_live_session_payload(
    *,
    match: _LiveSessionMatch,
    payload_content: str,
) -> tuple[bool, str]:
    if not match.reachable or not match.pane_target:
        return False, match.error_text or "live session not reachable"
    try:
        server = _libtmux_server()
    except RuntimeError as exc:
        return False, f"live session registry unavailable: {exc}"
    try:
        server.cmd("set-buffer", "--", payload_content)
        server.cmd("paste-buffer", "-t", match.pane_target, "-d")
        server.cmd("send-keys", "-t", match.pane_target, "Enter")
    except Exception as exc:  # pragma: no cover - depends on tmux runtime
        return False, f"tmux_send_failed:{exc.__class__.__name__}"
    return True, "dispatched"


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
        match = _resolve_live_session(
            target_type=target_type,
            target_identifier=str(target_row.get("target_identifier") or ""),
            config_json=config_json,
            requested_session_identifier=None,
        )
        if match.reachable:
            return TargetHealth(
                status="ok",
                detail=match.detail,
                attached=match.attached,
                busy=match.busy,
                reachable=True,
                stale=False,
            )
        degraded_details = {"session_identifier_required", "tmux_sessions_empty"}
        degraded_prefixes = ("session_not_found:", "chat_session_not_attached:", "pane_unavailable:")
        status = "degraded" if (match.detail in degraded_details or match.detail.startswith(degraded_prefixes)) else "unknown"
        return TargetHealth(
            status=status,
            detail=match.detail,
            attached=match.attached,
            busy=match.busy,
            reachable=False,
            stale=match.stale,
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
        config_json = target_row.get("config_json") or {}
        match = _resolve_live_session(
            target_type=target_type,
            target_identifier=target_identifier,
            config_json=config_json,
            requested_session_identifier=target_session_identifier,
        )
        if not match.reachable:
            return DispatchOutcome(
                accepted=False,
                status="failed",
                error_text=match.error_text or f"live session unavailable: {match.detail}",
                session_identifier=match.session_identifier or target_session_identifier or target_identifier or None,
                request_summary=request_summary,
                response_summary={
                    "accepted": False,
                    "target_type": target_type,
                    "machine_status": "unavailable",
                    "detail": match.detail,
                    "attached": match.attached,
                    "busy": match.busy,
                    "reachable": False,
                    "stale": match.stale,
                    "resolved_session_name": match.session_name,
                    "resolved_pane_target": match.pane_target,
                },
            )
        if dry_run:
            return DispatchOutcome(
                accepted=True,
                status="queued",
                external_identifier=match.pane_target,
                session_identifier=match.session_identifier,
                request_summary=request_summary,
                response_summary={
                    "accepted": True,
                    "target_type": target_type,
                    "machine_status": "preview",
                    "detail": match.detail,
                    "attached": match.attached,
                    "busy": match.busy,
                    "reachable": True,
                    "resolved_session_name": match.session_name,
                    "resolved_pane_target": match.pane_target,
                },
            )
        dispatched, detail = _dispatch_live_session_payload(
            match=match,
            payload_content=payload_content,
        )
        if not dispatched:
            return DispatchOutcome(
                accepted=False,
                status="failed",
                error_text=detail,
                external_identifier=match.pane_target,
                session_identifier=match.session_identifier,
                request_summary=request_summary,
                response_summary={
                    "accepted": False,
                    "target_type": target_type,
                    "machine_status": "dispatch_failed",
                    "detail": detail,
                    "attached": match.attached,
                    "busy": match.busy,
                    "reachable": True,
                    "resolved_session_name": match.session_name,
                    "resolved_pane_target": match.pane_target,
                },
            )
        return DispatchOutcome(
            accepted=True,
            status="delivered",
            external_identifier=match.pane_target,
            session_identifier=match.session_identifier,
            request_summary=request_summary,
            response_summary={
                "accepted": True,
                "target_type": target_type,
                "machine_status": "delivered",
                "detail": detail,
                "attached": match.attached,
                "busy": match.busy,
                "reachable": True,
                "resolved_session_name": match.session_name,
                "resolved_pane_target": match.pane_target,
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
