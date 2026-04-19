from __future__ import annotations

import os
import stat
from datetime import datetime, timezone
from pathlib import Path

import yaml

from promptforge_services.models import PrepareDeliveryResponse, PreprocessResponse
from promptforge_watcher.models import ImportResult, ParsedNote


def write_back_note(
    *,
    note_path: Path,
    note: ParsedNote,
    preprocess: PreprocessResponse,
    delivery: PrepareDeliveryResponse,
    result: ImportResult,
    processed_folder: str,
    delivery_status: str,
) -> Path:
    source_stat = note_path.stat() if note_path.exists() else None
    frontmatter = dict(note.frontmatter)
    frontmatter.update(
        {
            "status": "processed",
            "project": preprocess.resolved_project,
            "destination": delivery.delivery.destination,
            "prompt_type": preprocess.resolved_prompt_type,
            "target_type": delivery.delivery.target_type,
            "target_identifier": delivery.delivery.target_identifier,
            "mode": delivery.delivery.mode,
            "priority": delivery.delivery.priority,
            "requires_review": delivery.delivery.requires_review,
            "watch_eligible": False,
            "imported_at": _timestamp(),
            "utterance_id": result.utterance.id if result.utterance else None,
            "prompt_generation_id": result.prompt_generation.id if result.prompt_generation else None,
            "delivery_status": delivery_status,
            "tags_generated": _generated_tags(
                project_slug=preprocess.resolved_project,
                destination=delivery.delivery.destination,
                mode=delivery.delivery.mode,
                requires_review=delivery.delivery.requires_review,
            ),
        }
    )
    rendered_note = _dump_note(frontmatter, note.body_markdown)
    destination_dir = Path(note.vault_path) / processed_folder
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = _unique_path(destination_dir / note_path.name)
    destination_path.write_text(rendered_note, encoding="utf-8")
    _preserve_file_metadata(destination_path, source_stat)
    if note_path != destination_path and note_path.exists():
        note_path.unlink()
    return destination_path


def _generated_tags(
    *,
    project_slug: str,
    destination: str,
    mode: str,
    requires_review: bool,
) -> list[str]:
    tags = [
        "pf/voice",
        f"pf/project/{project_slug}",
        f"pf/destination/{destination.replace('_', '-')}",
        f"pf/mode/{mode.replace('_', '-')}",
    ]
    if requires_review:
        tags.append("pf/review-required")
    return tags


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


def _preserve_file_metadata(path: Path, source_stat: os.stat_result | None) -> None:
    if source_stat is None:
        return
    try:
        os.chown(path, source_stat.st_uid, source_stat.st_gid)
    except (AttributeError, PermissionError, OSError):
        pass
    try:
        os.chmod(path, stat.S_IMODE(source_stat.st_mode))
    except (PermissionError, OSError):
        pass
