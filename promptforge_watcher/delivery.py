from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import BaseModel

from promptforge_services.models import PrepareDeliveryResponse, RenderResponse
from promptforge_watcher.models import ImportResult, ParsedNote


class DeliveryDispatchResult(BaseModel):
    status: str
    error_text: str | None = None
    output_path: str | None = None


def dispatch_delivery(
    *,
    note: ParsedNote,
    render: RenderResponse,
    delivery,
    result: ImportResult,
    vault_path: str,
    processed_folder: str,
) -> DeliveryDispatchResult:
    prepared: PrepareDeliveryResponse = delivery
    if prepared.delivery.mode != "auto_dispatch":
        return DeliveryDispatchResult(status=prepared.delivery.status)

    if prepared.delivery.target_type != "obsidian_note":
        return DeliveryDispatchResult(
            status="failed",
            error_text=f"unsupported_auto_dispatch_target:{prepared.delivery.target_type}",
        )

    output_dir = Path(vault_path) / processed_folder
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = _unique_path(output_dir / f"{note.title}.prompt.md")
    output_frontmatter = {
        "pf_version": 1,
        "status": "processed",
        "created_by": "promptforge",
        "source_note": note.relative_path,
        "project": render.payload.project_slug,
        "prompt_type": render.payload.prompt_type,
        "destination": prepared.delivery.destination,
        "target_identifier": prepared.delivery.target_identifier,
        "mode": prepared.delivery.mode,
        "delivery_status": "delivered",
        "imported_at": _timestamp(),
        "utterance_id": result.utterance.id if result.utterance else None,
        "prompt_generation_id": result.prompt_generation.id if result.prompt_generation else None,
        "delivery_id": result.delivery.id if result.delivery else None,
        "tags_generated": [
            "pf/generated",
            f"pf/project/{render.payload.project_slug}",
            f"pf/destination/{prepared.delivery.destination.replace('_', '-')}",
        ],
    }
    output_body = render.final_prompt_markdown.strip()
    output_path.write_text(_dump_note(output_frontmatter, output_body), encoding="utf-8")
    return DeliveryDispatchResult(status="delivered", output_path=str(output_path))


def _dump_note(frontmatter: dict, body: str) -> str:
    serialized = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=False).strip()
    return f"---\n{serialized}\n---\n\n{body.strip()}\n"


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
