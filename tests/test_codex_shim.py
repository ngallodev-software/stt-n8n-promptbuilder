from __future__ import annotations

from scripts.codex_shim import _Handler


class _BrokenPipeWriter:
    def write(self, payload: bytes) -> None:
        raise BrokenPipeError()


class _DummyHandler:
    def __init__(self) -> None:
        self.wfile = _BrokenPipeWriter()
        self.status_code: int | None = None
        self.headers: list[tuple[str, str]] = []
        self.ended = False

    def send_response(self, code: int) -> None:
        self.status_code = code

    def send_header(self, key: str, value: str) -> None:
        self.headers.append((key, value))

    def end_headers(self) -> None:
        self.ended = True


def test_send_json_suppresses_broken_pipe() -> None:
    handler = _DummyHandler()

    _Handler._send_json(handler, 200, {"ok": True})

    assert handler.status_code == 200
    assert handler.ended is True
