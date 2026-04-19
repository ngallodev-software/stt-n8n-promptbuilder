#!/usr/bin/env python3
"""
Minimal OpenAI-compatible HTTP shim that wraps `codex exec --full-auto`.

Exposes:
  POST /v1/chat/completions  — OpenAI chat completions format
  GET  /v1/models            — model list (returns single "codex" entry)
  GET  /healthz              — health check

The last user message is extracted and passed as the prompt to codex exec.
The response is wrapped in an OpenAI-shaped JSON object so
OpenAICompatibleProvider works without modification.

Usage:
  python3 scripts/codex_shim.py [--port 8765] [--codex /path/to/codex]
                                  [--model gpt-4.1] [--reasoning-effort medium]

Run as a background service on the host:
  nohup python3 scripts/codex_shim.py &
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer


def _run_codex(prompt: str, *, binary: str, model: str | None, reasoning_effort: str, workdir: str = "/tmp") -> str:
    cmd = [binary, "exec", "--full-auto", "--skip-git-repo-check", "--cd", workdir]
    if model:
        cmd.extend(["-m", model])
    cmd.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    cmd.append(prompt)
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    return result.stdout.strip()


def _extract_user_prompt(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            return str(content)
    return ""


def _chat_response(content: str, model: str, latency_ms: int) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "_promptforge_latency_ms": latency_ms,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _error_response(code: int, message: str) -> dict:
    return {"error": {"code": code, "message": message, "type": "shim_error"}}


class _Handler(BaseHTTPRequestHandler):
    binary: str = "codex"
    model: str | None = None
    reasoning_effort: str = "medium"
    display_model: str = "codex"

    def log_message(self, fmt: str, *args: object) -> None:  # suppress access log noise
        pass

    def _send_json(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path in ("/healthz", "/health"):
            self._send_json(200, {"ok": True})
        elif self.path.startswith("/v1/models"):
            self._send_json(200, {
                "object": "list",
                "data": [{"id": self.display_model, "object": "model", "owned_by": "codex-shim"}],
            })
        else:
            self._send_json(404, _error_response(404, "not_found"))

    def do_POST(self) -> None:
        if not self.path.startswith("/v1/chat/completions"):
            self._send_json(404, _error_response(404, "not_found"))
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError):
            self._send_json(400, _error_response(400, "invalid_json"))
            return

        messages = body.get("messages", [])
        prompt = _extract_user_prompt(messages)
        if not prompt:
            self._send_json(400, _error_response(400, "no_user_message"))
            return

        start = time.monotonic()
        try:
            output = _run_codex(
                prompt,
                binary=self.binary,
                model=self.model,
                reasoning_effort=self.reasoning_effort,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr[:500] if exc.stderr else ""
            self._send_json(502, _error_response(502, f"codex_exec_failed: {stderr}"))
            return
        except subprocess.TimeoutExpired:
            self._send_json(504, _error_response(504, "codex_exec_timeout"))
            return

        latency_ms = max(0, int((time.monotonic() - start) * 1000))
        self._send_json(200, _chat_response(output, self.display_model, latency_ms))


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenAI-compatible codex exec shim")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--codex", default="codex", help="Path to codex binary")
    parser.add_argument("--model", default=None, help="codex -m flag (default: omit)")
    parser.add_argument("--reasoning-effort", default="medium", dest="reasoning_effort")
    args = parser.parse_args()

    _Handler.binary = args.codex
    _Handler.model = args.model
    _Handler.reasoning_effort = args.reasoning_effort
    _Handler.display_model = args.model or "codex"

    server = HTTPServer((args.host, args.port), _Handler)
    print(f"codex shim listening on {args.host}:{args.port} (binary={args.codex})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
