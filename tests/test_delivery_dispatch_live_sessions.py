from __future__ import annotations

from promptforge_services import delivery_dispatch as dd


def _live_target(target_type: str = "claude_session") -> dict[str, object]:
    return {
        "id": "target-1",
        "target_type": target_type,
        "target_identifier": "claude-session-123",
        "config_json": {"adapter": "claude_cli"},
    }


def test_compute_target_health_live_session_when_registry_missing(monkeypatch) -> None:
    def _fake_resolve(**_: object) -> dd._LiveSessionMatch:
        return dd._LiveSessionMatch(
            reachable=False,
            detail="libtmux_not_installed",
            stale=None,
            error_text="live session registry unavailable: libtmux_not_installed",
        )

    monkeypatch.setattr(dd, "_resolve_live_session", _fake_resolve)

    health = dd.compute_target_health(_live_target())
    assert health.status == "unknown"
    assert health.detail == "libtmux_not_installed"
    assert health.reachable is False


def test_dispatch_live_session_dry_run_preview(monkeypatch) -> None:
    def _fake_resolve(**_: object) -> dd._LiveSessionMatch:
        return dd._LiveSessionMatch(
            reachable=True,
            detail="tmux_session_ready:dev",
            session_name="dev",
            pane_target="%7",
            session_identifier="claude-session-123",
            attached=True,
            busy=False,
            stale=False,
        )

    monkeypatch.setattr(dd, "_resolve_live_session", _fake_resolve)

    outcome = dd.dispatch_target_payload(
        target_row=_live_target(),
        payload_content="Test payload",
        prompt_generation_id="pg-1",
        delivery_id="delivery-1",
        target_session_identifier=None,
        dry_run=True,
    )
    assert outcome.accepted is True
    assert outcome.status == "queued"
    assert outcome.external_identifier == "%7"
    assert outcome.session_identifier == "claude-session-123"
    assert outcome.response_summary["machine_status"] == "preview"


def test_dispatch_live_session_unavailable(monkeypatch) -> None:
    def _fake_resolve(**_: object) -> dd._LiveSessionMatch:
        return dd._LiveSessionMatch(
            reachable=False,
            detail="session_not_found:claude-session-123",
            session_identifier="claude-session-123",
            stale=True,
            error_text="no tmux session matched 'claude-session-123'",
        )

    monkeypatch.setattr(dd, "_resolve_live_session", _fake_resolve)

    outcome = dd.dispatch_target_payload(
        target_row=_live_target(),
        payload_content="Test payload",
        prompt_generation_id="pg-1",
        delivery_id="delivery-1",
        target_session_identifier=None,
        dry_run=False,
    )
    assert outcome.accepted is False
    assert outcome.status == "failed"
    assert outcome.error_text == "no tmux session matched 'claude-session-123'"
    assert outcome.response_summary["machine_status"] == "unavailable"


def test_dispatch_live_session_send_failure(monkeypatch) -> None:
    def _fake_resolve(**_: object) -> dd._LiveSessionMatch:
        return dd._LiveSessionMatch(
            reachable=True,
            detail="tmux_session_ready:dev",
            session_name="dev",
            pane_target="%7",
            session_identifier="codex-session-999",
            attached=True,
            busy=True,
            stale=False,
        )

    def _fake_dispatch(**_: object) -> tuple[bool, str]:
        return False, "tmux_send_failed:RuntimeError"

    monkeypatch.setattr(dd, "_resolve_live_session", _fake_resolve)
    monkeypatch.setattr(dd, "_dispatch_live_session_payload", _fake_dispatch)

    outcome = dd.dispatch_target_payload(
        target_row=_live_target("codex_session"),
        payload_content="Test payload",
        prompt_generation_id="pg-1",
        delivery_id="delivery-1",
        target_session_identifier="codex-session-999",
        dry_run=False,
    )
    assert outcome.accepted is False
    assert outcome.status == "failed"
    assert outcome.error_text == "tmux_send_failed:RuntimeError"
    assert outcome.response_summary["machine_status"] == "dispatch_failed"


def test_dispatch_live_session_success(monkeypatch) -> None:
    def _fake_resolve(**_: object) -> dd._LiveSessionMatch:
        return dd._LiveSessionMatch(
            reachable=True,
            detail="tmux_session_ready:dev",
            session_name="dev",
            pane_target="%7",
            session_identifier="claude-session-123",
            attached=True,
            busy=False,
            stale=False,
        )

    def _fake_dispatch(**_: object) -> tuple[bool, str]:
        return True, "dispatched"

    monkeypatch.setattr(dd, "_resolve_live_session", _fake_resolve)
    monkeypatch.setattr(dd, "_dispatch_live_session_payload", _fake_dispatch)

    outcome = dd.dispatch_target_payload(
        target_row=_live_target(),
        payload_content="Test payload",
        prompt_generation_id="pg-1",
        delivery_id="delivery-1",
        target_session_identifier=None,
        dry_run=False,
    )
    assert outcome.accepted is True
    assert outcome.status == "delivered"
    assert outcome.external_identifier == "%7"
    assert outcome.session_identifier == "claude-session-123"
    assert outcome.response_summary["machine_status"] == "delivered"
