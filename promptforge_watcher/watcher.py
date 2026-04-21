from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from threading import Lock
from typing import Callable

import psycopg
import yaml
from watchdog.events import FileSystemEvent, FileSystemEventHandler, FileSystemMovedEvent
from watchdog.observers import Observer

from promptforge_services.llm.router import get_llm_router
from promptforge_services.models import PrepareDeliveryRequest, RenderRequest
from promptforge_watcher.models import StoredLLMRun
from promptforge_services.pipeline import (
    parse_directives,
    prepare_delivery_request,
    preprocess_request,
    render_request,
)
from promptforge_watcher.config import WatcherConfig
from promptforge_watcher.delivery import dispatch_delivery
from promptforge_watcher.models import EligibilityResult, ImportBundle, ImportResult, ParsedNote
from promptforge_watcher.repository import WatcherRepository, build_repository
from promptforge_watcher.webhook import build_webhook_payload, post_webhook
from promptforge_watcher.writeback import write_back_note


def run() -> None:
    cfg = WatcherConfig()
    repository = build_repository(cfg.database_url)
    normalized_watch_folder = _normalize_watch_folder(cfg.watch_folder)
    watch_path = Path(cfg.vault_path) / normalized_watch_folder
    stabilization_seconds = float(cfg.stabilization_seconds)
    seen_hashes: dict[str, str] = {}

    print(
        f"PromptForge watcher starting. Watching: {watch_path} "
        f"(watch_folder={cfg.watch_folder!r} normalized={normalized_watch_folder!r})"
    )
    if not watch_path.exists():
        print("Watch path does not exist yet.")
        return

    candidates = sorted(path for path in watch_path.rglob("*.md") if _is_processable_markdown_path(path))
    print(f"Discovered {len(candidates)} markdown note(s).")
    for note_path in candidates:
        try:
            _process_note_path(
                note_path=note_path,
                cfg=cfg,
                repository=repository,
                seen_hashes=seen_hashes,
                source="startup",
            )
        except Exception as e:
            print(f"Error processing note {note_path}: {str(e)}")
            _write_workflow_error_record(
                note_path=str(note_path),
                error_type="watcher_exception",
                error_message=str(e),
                database_url=cfg.database_url,
            )

    pending: dict[Path, float] = {}
    pending_lock = Lock()

    def _enqueue(note_path: Path) -> None:
        with pending_lock:
            pending[note_path] = time.monotonic() + stabilization_seconds

    observer = Observer()
    handler = _VaultEventHandler(watch_path=watch_path, on_change=_enqueue)
    observer.schedule(handler, str(watch_path), recursive=True)
    observer.start()
    print("Event-driven watcher active. Waiting for note changes.")

    try:
        while True:
            ready = _drain_ready_paths(pending, pending_lock)
            for note_path in ready:
                try:
                    _process_note_path(
                        note_path=note_path,
                        cfg=cfg,
                        repository=repository,
                        seen_hashes=seen_hashes,
                        source="event",
                    )
                except Exception as e:
                    print(f"Error processing note {note_path}: {str(e)}")
                    _write_workflow_error_record(
                        note_path=str(note_path),
                        error_type="watcher_exception",
                        error_message=str(e),
                        database_url=cfg.database_url,
                    )
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Watcher stopping.")
    finally:
        observer.stop()
        observer.join()


def import_note(
    note: ParsedNote,
    *,
    repository: WatcherRepository,
    webhook_url: str,
    webhook_enabled: bool = False,
    bundle: ImportBundle | None = None,
) -> ImportResult:
    bundle = bundle or _build_import_bundle(note)
    result = repository.import_bundle(bundle)
    if result.imported and webhook_enabled:
        payload = build_webhook_payload(
            result,
            project_slug=bundle.preprocess.resolved_project,
            prompt_type=bundle.preprocess.resolved_prompt_type,
            destination=bundle.delivery.delivery.destination,
            mode=bundle.delivery.delivery.mode,
            requires_review=bundle.delivery.delivery.requires_review,
            render=bundle.render,
            delivery=bundle.delivery,
        )
        post_webhook(webhook_url, payload)
    return result


def _process_note_path(
    *,
    note_path: Path,
    cfg: WatcherConfig,
    repository: WatcherRepository,
    seen_hashes: dict[str, str],
    source: str,
) -> None:
    if not note_path.exists():
        return
    if not _is_processable_markdown_path(note_path):
        return

    note = load_note(note_path, Path(cfg.vault_path))
    known_hash = seen_hashes.get(note.relative_path)
    if known_hash == note.note_hash:
        print(f"- skipped ({source}): {note.relative_path} (unchanged_hash)")
        return
    seen_hashes[note.relative_path] = note.note_hash

    eligibility = evaluate_eligibility(note, cfg.watch_folder)
    status = "eligible" if eligibility.eligible else "skipped"
    print(f"- {status} ({source}): {note.relative_path}")
    if eligibility.reasons:
        print(f"  reasons: {', '.join(eligibility.reasons)}")
        if "outside_watch_folder" in eligibility.reasons:
            watch_prefix = f"{_normalize_watch_folder(cfg.watch_folder)}/"
            print(f"  detail: relative_path={note.relative_path!r} expected_prefix={watch_prefix!r}")
        return

    bundle = _build_import_bundle(note)
    result = import_note(
        note,
        repository=repository,
        webhook_url=cfg.webhook_url,
        webhook_enabled=cfg.webhook_enabled,
        bundle=bundle,
    )
    if result.imported:
        dispatched = dispatch_delivery(
            note=note,
            render=bundle.render,
            delivery=bundle.delivery,
            result=result,
            vault_path=cfg.vault_path,
            processed_folder=cfg.processed_folder,
        )
        if result.delivery is not None and dispatched.status != result.delivery.status:
            repository.update_delivery_status(
                result.delivery.id,
                status=dispatched.status,
                error_text=dispatched.error_text,
            )
        print(f"  imported: intake_note_id={result.intake_note.id} prompt_generation_id={result.prompt_generation.id}")
        if _run_succeeded(result=result, delivery_status=dispatched.status):
            processed_path = write_back_note(
                note_path=note_path,
                note=note,
                preprocess=bundle.preprocess,
                delivery=bundle.delivery,
                result=result,
                processed_folder=cfg.processed_folder,
                delivery_status=dispatched.status,
            )
            print(f"  note_writeback: {processed_path}")
        else:
            print("  note_writeback: skipped (run_not_successful; source note preserved)")
        if dispatched.output_path:
            print(f"  delivery_output: {dispatched.output_path}")
    else:
        print(f"  skipped: {result.skipped_reason}")


def _is_processable_markdown_path(note_path: Path) -> bool:
    if note_path.suffix.lower() != ".md":
        return False

    excluded_suffixes = (".swp", ".swx", ".tmp", ".part", ".crdownload")
    lower_path = str(note_path).lower()
    if any(lower_path.endswith(suffix) for suffix in excluded_suffixes):
        return False

    for segment in note_path.parts:
        if segment.startswith("."):
            return False

    name = note_path.name
    if name.startswith(("~", "._", ".")) or name.endswith(("~", ".tmp")):
        return False

    return True


def _drain_ready_paths(pending: dict[Path, float], pending_lock: Lock) -> list[Path]:
    now = time.monotonic()
    ready: list[Path] = []
    with pending_lock:
        for path, deadline in list(pending.items()):
            if deadline <= now:
                ready.append(path)
                pending.pop(path, None)
    return ready


def _run_succeeded(*, result: ImportResult, delivery_status: str) -> bool:
    if not result.imported:
        return False
    if result.processing_run is None or result.processing_run.status != "completed":
        return False
    if result.prompt_generation is None or result.prompt_generation.status != "rendered":
        return False
    return delivery_status != "failed"


class _VaultEventHandler(FileSystemEventHandler):
    def __init__(self, *, watch_path: Path, on_change: Callable[[Path], None]) -> None:
        super().__init__()
        self.watch_path = watch_path
        self.on_change = on_change

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle(event)

    def on_moved(self, event: FileSystemMovedEvent) -> None:
        self._handle(event, path_override=event.dest_path)

    def _handle(self, event: FileSystemEvent, *, path_override: str | None = None) -> None:
        if event.is_directory:
            return
        path = Path(path_override or event.src_path)
        if not path.is_absolute():
            path = (self.watch_path / path).resolve()
        if not _is_processable_markdown_path(path):
            return
        self.on_change(path)


def load_note(note_path: Path, vault_path: Path) -> ParsedNote:
    raw_text = note_path.read_text(encoding="utf-8")
    frontmatter, body_markdown = _split_frontmatter(raw_text)
    control_text, transcript_text = _extract_sections(body_markdown)

    if "## Control" not in body_markdown:
        raise ValueError("missing_section:Control")
    if "## Transcript" not in body_markdown:
        raise ValueError("missing_section:Transcript")

    note_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    relative_path = note_path.relative_to(vault_path).as_posix()
    return ParsedNote(
        vault_path=str(vault_path),
        relative_path=relative_path,
        title=note_path.stem,
        frontmatter=frontmatter,
        body_markdown=body_markdown,
        control_text=control_text,
        transcript_text=transcript_text,
        note_hash=note_hash,
    )


def evaluate_eligibility(note: ParsedNote, watch_folder: str) -> EligibilityResult:
    reasons: list[str] = []
    watch_prefix = f"{_normalize_watch_folder(watch_folder)}/"
    if not note.relative_path.startswith(watch_prefix):
        reasons.append("outside_watch_folder")
    if not note.relative_path.endswith(".md"):
        reasons.append("non_markdown")
    if note.frontmatter.get("watch_eligible", True) is False:
        reasons.append("watch_eligible_false")
    if str(note.frontmatter.get("status", "new")).strip().lower() != "new":
        reasons.append("status_not_new")
    if not (note.transcript_text or "").strip():
        reasons.append("empty_transcript")
    return EligibilityResult(eligible=not reasons, reasons=reasons)


def _normalize_watch_folder(watch_folder: str) -> str:
    normalized = watch_folder.strip().replace("\\", "/").strip("/")
    return normalized or "Inbox/Voice"


def _preprocess_payload(note: ParsedNote):
    from promptforge_services.models import PreprocessRequest

    return PreprocessRequest(
        frontmatter=note.frontmatter,
        control_text=note.control_text,
        transcript_text=note.transcript_text or "",
    )


def _build_import_bundle(note: ParsedNote) -> ImportBundle:
    preprocess = preprocess_request(payload=_preprocess_payload(note))
    render = render_request(
        RenderRequest(
            contract_name="agent_task_v1",
            payload=preprocess.draft_structured_output.model_dump(),
        )
    )

    llm_runs: list[StoredLLMRun] = []
    router = get_llm_router()
    if router.supports("review"):
        start = time.monotonic()
        review = router.review_prompt(render.final_prompt_markdown)
        elapsed_ms = max(0, int((time.monotonic() - start) * 1000))
        if review is not None:
            polished = (review.raw_response or {}).get("polished_prompt")
            if polished and isinstance(polished, str) and polished.strip():
                render = render.model_copy(update={"final_prompt_markdown": polished.strip()})
            llm_runs.append(StoredLLMRun(
                provider_name=review.provider_name,
                model_name=review.model_name,
                mode="review",
                latency_ms=review.latency_ms or elapsed_ms,
                summary=review.summary,
                findings_json=list(review.findings) if review.findings else None,
                raw_response_json=review.raw_response,
            ))

    delivery = prepare_delivery_request(
        PrepareDeliveryRequest(
            contract_name="agent_task_v1",
            payload=render.payload.model_dump(),
            priority=str(note.frontmatter.get("priority", "normal")),
        )
    )
    return ImportBundle(note=note, preprocess=preprocess, render=render, delivery=delivery, llm_runs=llm_runs)


def _split_frontmatter(raw_text: str) -> tuple[dict, str]:
    if not raw_text.startswith("---\n"):
        return {}, raw_text.strip()

    _, remainder = raw_text.split("---\n", 1)
    frontmatter_text, separator, body = remainder.partition("\n---\n")
    if not separator:
        return {}, raw_text.strip()
    loaded = yaml.safe_load(frontmatter_text) or {}
    return loaded, body.strip()


def _extract_sections(body_markdown: str) -> tuple[str | None, str | None]:
    pattern = re.compile(r"^##\s+(Control|Transcript)\s*$", re.IGNORECASE | re.MULTILINE)
    matches = list(pattern.finditer(body_markdown))
    if matches:
        sections: dict[str, str] = {}
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body_markdown)
            name = match.group(1).strip().lower()
            sections[name] = body_markdown[start:end].strip()
        return sections.get("control"), sections.get("transcript")

    blocks = [block.strip() for block in re.split(r"\n\s*\n", body_markdown) if block.strip()]
    if blocks:
        candidate = blocks[0]
        directives = parse_directives(candidate)
        if any(
            getattr(directives, field) is not None
            for field in (
                "project",
                "prompt_type",
                "destination",
                "target_identifier",
                "mode",
                "priority",
                "requires_review",
            )
        ):
            transcript = "\n\n".join(blocks[1:]).strip() or None
            return candidate, transcript
    return None, body_markdown.strip() or None


def _write_workflow_error_record(
    *,
    note_path: str,
    error_type: str,
    error_message: str,
    database_url: str | None,
) -> None:
    if not database_url:
        print("Database URL not configured; skipping error record.")
        return
    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO workflow_error_records (id, note_path, error_type, error_message)
                    VALUES (gen_random_uuid(), %s, %s, %s)
                    """,
                    (note_path, error_type, error_message),
                )
                conn.commit()
    except Exception as insert_error:
        print(f"Failed to write error record to workflow_error_records: {str(insert_error)}")
