#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSOLE_API = ROOT / "promptforge_services" / "console_api.py"
SNAPSHOT = ROOT / "docs" / "contract-snapshot.json"
ALLOWED_METHODS = {"get", "post", "patch", "put", "delete"}


def extract_routes(source: str) -> list[dict[str, str]]:
    tree = ast.parse(source, filename=str(CONSOLE_API))
    routes: list[dict[str, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for decorator in node.decorator_list:
            route = _parse_route_decorator(decorator)
            if route is not None:
                routes.append(route)

    routes.sort(key=lambda item: (item["method"], item["path"]))
    return routes


def _parse_route_decorator(decorator: ast.AST) -> dict[str, str] | None:
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Attribute):
        return None
    if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "router":
        return None

    method = decorator.func.attr
    if method not in ALLOWED_METHODS or not decorator.args:
        return None

    path = _literal_string(decorator.args[0])
    if path is None:
        raise SystemExit(f"Unsupported non-literal route path on line {decorator.lineno}")

    return {"method": method.upper(), "path": path}


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def load_snapshot() -> list[dict[str, str]] | None:
    if not SNAPSHOT.exists():
        return None

    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    routes = data.get("routes") if isinstance(data, dict) else data
    if not isinstance(routes, list):
        raise SystemExit("Snapshot file is malformed: expected a route list")

    normalized: list[dict[str, str]] = []
    for item in routes:
        if not isinstance(item, dict):
            raise SystemExit("Snapshot file is malformed: expected route objects")
        method = item.get("method")
        path = item.get("path")
        if not isinstance(method, str) or not isinstance(path, str):
            raise SystemExit("Snapshot file is malformed: each route needs method and path")
        normalized.append({"method": method.upper(), "path": path})

    normalized.sort(key=lambda item: (item["method"], item["path"]))
    return normalized


def write_snapshot(routes: list[dict[str, str]]) -> None:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"routes": routes}
    SNAPSHOT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def format_route(route: dict[str, str]) -> str:
    return f'{route["method"]} {route["path"]}'


def main() -> int:
    source = CONSOLE_API.read_text(encoding="utf-8")
    current = extract_routes(source)
    snapshot = load_snapshot()

    if snapshot is None:
        write_snapshot(current)
        print(f"Generated {SNAPSHOT.relative_to(ROOT)} with {len(current)} routes.")
        return 0

    current_set = {format_route(route) for route in current}
    snapshot_set = {format_route(route) for route in snapshot}
    added = sorted(current_set - snapshot_set)
    removed = sorted(snapshot_set - current_set)

    if not added and not removed:
        print(f"No contract drift detected across {len(current)} routes.")
        return 0

    lines = ["Contract drift detected."]
    if added:
        lines.append("Added endpoints:")
        lines.extend(f"  + {item}" for item in added)
    if removed:
        lines.append("Removed endpoints:")
        lines.extend(f"  - {item}" for item in removed)

    message = "\n".join(lines)
    print(message, file=sys.stderr)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        github_summary = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title=Contract drift::{github_summary}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
