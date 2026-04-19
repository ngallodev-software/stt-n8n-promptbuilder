from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from typing import Any

import psycopg

from promptforge_watcher.models import (
    ImportBundle,
    ImportResult,
    StoredLLMRun,
    StoredDelivery,
    StoredIntakeNote,
    StoredProcessingRun,
    StoredPromptGeneration,
    StoredUtterance,
)


class WatcherRepository(ABC):
    @abstractmethod
    def import_bundle(self, bundle: ImportBundle) -> ImportResult:
        raise NotImplementedError

    @abstractmethod
    def update_delivery_status(
        self,
        delivery_id: str,
        *,
        status: str,
        error_text: str | None = None,
    ) -> None:
        raise NotImplementedError


class InMemoryWatcherRepository(WatcherRepository):
    def __init__(self) -> None:
        self._notes_by_path: dict[str, StoredIntakeNote] = {}
        self.imported_rows: list[dict[str, Any]] = []

    def import_bundle(self, bundle: ImportBundle) -> ImportResult:
        existing = self._notes_by_path.get(bundle.note.relative_path)
        if existing is not None:
            return ImportResult(imported=False, skipped_reason="duplicate_note_path", intake_note=existing)

        intake_note = StoredIntakeNote(
            id=_uuid(),
            note_relative_path=bundle.note.relative_path,
            note_hash=bundle.note.note_hash,
            status="imported",
        )
        utterance = StoredUtterance(
            id=_uuid(),
            intake_note_id=intake_note.id,
            raw_text=bundle.note.transcript_text or "",
        )
        prompt_generation = StoredPromptGeneration(
            id=_uuid(),
            utterance_id=utterance.id,
            status="rendered",
        )
        delivery = StoredDelivery(
            id=_uuid(),
            prompt_generation_id=prompt_generation.id,
            status=bundle.delivery.delivery.status,
            target_identifier=bundle.delivery.delivery.target_identifier,
        )
        processing_run = StoredProcessingRun(
            id=_uuid(),
            utterance_id=utterance.id,
            status="completed",
        )
        self._notes_by_path[bundle.note.relative_path] = intake_note
        self.imported_rows.append(
            {
                "intake_note": intake_note.model_dump(),
                "utterance": utterance.model_dump(),
                "prompt_generation": prompt_generation.model_dump(),
                "delivery": delivery.model_dump(),
                "processing_run": processing_run.model_dump(),
                "llm_runs": [self._materialize_llm_run(run) for run in bundle.llm_runs],
                "preprocess": bundle.preprocess.model_dump(),
                "render": bundle.render.model_dump(),
                "preprocess_response": bundle.preprocess,
                "render_response": bundle.render,
                "delivery_response": bundle.delivery,
            }
        )
        return ImportResult(
            imported=True,
            intake_note=intake_note,
            utterance=utterance,
            prompt_generation=prompt_generation,
            delivery=delivery,
            processing_run=processing_run,
        )

    def update_delivery_status(
        self,
        delivery_id: str,
        *,
        status: str,
        error_text: str | None = None,
    ) -> None:
        for row in self.imported_rows:
            delivery = row.get("delivery")
            if delivery and delivery.get("id") == delivery_id:
                delivery["status"] = status
                delivery["error_text"] = error_text
                break

    def _materialize_llm_run(self, llm_run: StoredLLMRun) -> dict[str, Any]:
        row = llm_run.model_dump()
        row["id"] = row.get("id") or _uuid()
        return row


class PostgresWatcherRepository(WatcherRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def import_bundle(self, bundle: ImportBundle) -> ImportResult:
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, note_hash FROM intake_notes WHERE note_relative_path = %s",
                    (bundle.note.relative_path,),
                )
                existing = cur.fetchone()
                if existing is not None:
                    return ImportResult(
                        imported=False,
                        skipped_reason="duplicate_note_path",
                        intake_note=StoredIntakeNote(
                            id=str(existing[0]),
                            note_relative_path=bundle.note.relative_path,
                            note_hash=bundle.note.note_hash,
                            status="skipped",
                        ),
                    )

                project_id = self._project_id(cur, bundle.preprocess.resolved_project)
                intake_note_id = _uuid()
                utterance_id = _uuid()
                prompt_generation_id = _uuid()
                delivery_id = _uuid()
                processing_run_id = _uuid()

                cur.execute(
                    """
                    INSERT INTO intake_notes (
                        id, vault_path, note_relative_path, note_title, note_hash, imported_at,
                        frontmatter_json, body_markdown, project_id, status, watch_eligible, source_device
                    ) VALUES (
                        %s, %s, %s, %s, %s, now(),
                        %s::jsonb, %s, %s, 'imported', %s, %s
                    )
                    """,
                    (
                        intake_note_id,
                        bundle.note.vault_path,
                        bundle.note.relative_path,
                        bundle.note.title,
                        bundle.note.note_hash,
                        json.dumps(bundle.note.frontmatter),
                        bundle.note.body_markdown,
                        project_id,
                        bool(bundle.note.frontmatter.get("watch_eligible", True)),
                        str(bundle.note.frontmatter.get("source_device", "windows-main")),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO utterances (
                        id, intake_note_id, raw_text, directive_text, project_id, scope, capture_type
                    ) VALUES (%s, %s, %s, %s, %s, 'project', 'voice')
                    """,
                    (
                        utterance_id,
                        intake_note_id,
                        bundle.note.transcript_text or "",
                        bundle.note.control_text,
                        project_id,
                    ),
                )
                self._insert_revision(
                    cur,
                    utterance_id,
                    "raw",
                    bundle.note.transcript_text or "",
                    "watcher",
                    "obsidian-importer",
                    {"source_section": "Transcript"},
                )
                self._insert_revision(
                    cur,
                    utterance_id,
                    "directive_stripped",
                    bundle.note.transcript_text or "",
                    "python",
                    "promptforge-normalize",
                    {"removed_directive_lines": len((bundle.note.control_text or "").splitlines())},
                )
                self._insert_revision(
                    cur,
                    utterance_id,
                    "deterministic_preprocessed",
                    bundle.preprocess.normalized_transcript,
                    "python",
                    "promptforge-normalize",
                    {
                        "project_slug": bundle.preprocess.resolved_project,
                        "prompt_type": bundle.preprocess.resolved_prompt_type,
                        "warnings": bundle.preprocess.warnings,
                    },
                )
                self._insert_revision(
                    cur,
                    utterance_id,
                    "final_rendered_prompt",
                    bundle.render.final_prompt_markdown,
                    "renderer",
                    "promptforge-render",
                    {"template_name": bundle.render.template_name},
                )
                cur.execute(
                    """
                    INSERT INTO prompt_generations (
                        id, utterance_id, project_id, prompt_type, structured_output_json,
                        final_prompt_markdown, requires_review, status
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, 'rendered')
                    """,
                    (
                        prompt_generation_id,
                        utterance_id,
                        project_id,
                        bundle.render.payload.prompt_type,
                        json.dumps(bundle.render.payload.model_dump()),
                        bundle.render.final_prompt_markdown,
                        bundle.render.payload.requires_review,
                    ),
                )
                for llm_run in bundle.llm_runs:
                    self._insert_llm_run(
                        cur,
                        prompt_generation_id=prompt_generation_id,
                        utterance_id=utterance_id,
                        llm_run=llm_run,
                    )
                cur.execute(
                    """
                    INSERT INTO deliveries (
                        id, prompt_generation_id, destination, target_type, target_identifier,
                        mode, status, priority, queued_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                    """,
                    (
                        delivery_id,
                        prompt_generation_id,
                        bundle.delivery.delivery.destination,
                        bundle.delivery.delivery.target_type,
                        bundle.delivery.delivery.target_identifier,
                        bundle.delivery.delivery.mode,
                        bundle.delivery.delivery.status,
                        bundle.delivery.delivery.priority,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO processing_runs (
                        id, utterance_id, workflow_name, status, ended_at, trace_json
                    ) VALUES (%s, %s, %s, 'completed', now(), %s::jsonb)
                    """,
                    (
                        processing_run_id,
                        utterance_id,
                        "promptforge-intake-v1",
                        json.dumps(
                            {
                                "steps": [
                                    "load_note",
                                    "deterministic_preprocess",
                                    "validate_contract",
                                    "render_prompt",
                                    "prepare_delivery",
                                ]
                            }
                        ),
                    ),
                )
            conn.commit()

        return ImportResult(
            imported=True,
            intake_note=StoredIntakeNote(
                id=intake_note_id,
                note_relative_path=bundle.note.relative_path,
                note_hash=bundle.note.note_hash,
                status="imported",
            ),
            utterance=StoredUtterance(
                id=utterance_id,
                intake_note_id=intake_note_id,
                raw_text=bundle.note.transcript_text or "",
            ),
            prompt_generation=StoredPromptGeneration(
                id=prompt_generation_id,
                utterance_id=utterance_id,
                status="rendered",
            ),
            delivery=StoredDelivery(
                id=delivery_id,
                prompt_generation_id=prompt_generation_id,
                status=bundle.delivery.delivery.status,
                target_identifier=bundle.delivery.delivery.target_identifier,
            ),
            processing_run=StoredProcessingRun(
                id=processing_run_id,
                utterance_id=utterance_id,
                status="completed",
            ),
        )

    def update_delivery_status(
        self,
        delivery_id: str,
        *,
        status: str,
        error_text: str | None = None,
    ) -> None:
        dispatched_clause = "dispatched_at = now()," if status in {"delivered", "acked", "failed"} else ""
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE deliveries
                    SET status = %s,
                        {dispatched_clause}
                        error_text = %s
                    WHERE id = %s
                    """,
                    (status, error_text, delivery_id),
                )
            conn.commit()

    def _project_id(self, cur: psycopg.Cursor[Any], project_slug: str) -> str | None:
        cur.execute("SELECT id FROM projects WHERE slug = %s", (project_slug,))
        row = cur.fetchone()
        return None if row is None else str(row[0])

    def _insert_revision(
        self,
        cur: psycopg.Cursor[Any],
        utterance_id: str,
        revision_kind: str,
        content: str,
        producer_type: str,
        producer_name: str,
        metadata: dict[str, Any],
    ) -> None:
        cur.execute(
            """
            INSERT INTO transcript_revisions (
                utterance_id, revision_kind, content, producer_type, producer_name, metadata_json
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            """,
            (utterance_id, revision_kind, content, producer_type, producer_name, json.dumps(metadata)),
        )

    def _insert_llm_run(
        self,
        cur: psycopg.Cursor[Any],
        *,
        prompt_generation_id: str,
        utterance_id: str,
        llm_run: StoredLLMRun,
    ) -> None:
        cur.execute(
            """
            INSERT INTO llm_runs (
                id, utterance_id, prompt_generation_id, provider_name, model_name, mode,
                latency_ms, token_usage_json, fallback_chain_json, summary, findings_json,
                raw_response_json
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s::jsonb, %s::jsonb, %s, %s::jsonb, %s::jsonb
            )
            """,
            (
                llm_run.id or _uuid(),
                utterance_id,
                prompt_generation_id,
                llm_run.provider_name,
                llm_run.model_name,
                llm_run.mode,
                llm_run.latency_ms,
                json.dumps(llm_run.token_usage_json) if llm_run.token_usage_json is not None else None,
                json.dumps(llm_run.fallback_chain) if llm_run.fallback_chain is not None else None,
                llm_run.summary,
                json.dumps(llm_run.findings_json) if llm_run.findings_json is not None else None,
                json.dumps(llm_run.raw_response_json) if llm_run.raw_response_json is not None else None,
            ),
        )

    def _materialize_llm_run(self, llm_run: StoredLLMRun) -> dict[str, Any]:
        row = llm_run.model_dump()
        row["id"] = row.get("id") or _uuid()
        return row


def build_repository(database_url: str | None) -> WatcherRepository:
    if database_url:
        return PostgresWatcherRepository(database_url)
    return InMemoryWatcherRepository()


def _uuid() -> str:
    return str(uuid.uuid4())
