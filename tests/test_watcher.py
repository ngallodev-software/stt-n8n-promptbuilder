from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

import yaml
from watchdog.events import DirCreatedEvent, FileCreatedEvent, FileMovedEvent

from promptforge_watcher.config import WatcherConfig
from promptforge_watcher.delivery import dispatch_delivery
from promptforge_watcher.models import StoredLLMRun
from promptforge_watcher.repository import InMemoryWatcherRepository
from promptforge_watcher.watcher import (
    _VaultEventHandler,
    _build_import_bundle,
    _drain_ready_paths,
    _is_processable_markdown_path,
    _process_note_path,
    evaluate_eligibility,
    import_note,
    load_note,
)
from promptforge_watcher.writeback import write_back_note


SEED_NOTE = """---
pf_version: 1
capture_type: voice
status: new
created_by: obsidian
project: inbox
destination: queue_only
prompt_type: general
target_type: none
target_identifier: ""
mode: queue
priority: normal
requires_review: false
template_profile: default
source_device: windows-main
watch_eligible: true
imported_at: null
utterance_id: null
prompt_generation_id: null
delivery_status: not_started
tags_generated: []
---

## Control
project is thtaxmachine
prompt type is codingcli
destination is cli
target is claude-tax-main

## Transcript
um figure out why the retry state transitions do not line up with the review and error policy and prepare a patch plan
"""


class WatcherTests(unittest.TestCase):
    def test_is_processable_markdown_path_filters_hidden_and_temp(self) -> None:
        self.assertTrue(_is_processable_markdown_path(Path("/vault/Inbox/Voice/note.md")))
        self.assertFalse(_is_processable_markdown_path(Path("/vault/Inbox/Voice/.note.md")))
        self.assertFalse(_is_processable_markdown_path(Path("/vault/.hidden/note.md")))
        self.assertFalse(_is_processable_markdown_path(Path("/vault/Inbox/Voice/~note.md")))
        self.assertFalse(_is_processable_markdown_path(Path("/vault/Inbox/Voice/note.md.tmp")))
        self.assertFalse(_is_processable_markdown_path(Path("/vault/Inbox/Voice/note.txt")))

    def test_drain_ready_paths_returns_due_entries(self) -> None:
        from threading import Lock

        lock = Lock()
        pending = {
            Path("/vault/Inbox/Voice/ready.md"): 0.0,
            Path("/vault/Inbox/Voice/not-ready.md"): 9999999999.0,
        }
        ready = _drain_ready_paths(pending, lock)
        self.assertEqual(ready, [Path("/vault/Inbox/Voice/ready.md")])
        self.assertIn(Path("/vault/Inbox/Voice/not-ready.md"), pending)
        self.assertNotIn(Path("/vault/Inbox/Voice/ready.md"), pending)

    def test_vault_event_handler_enqueues_only_processable_files(self) -> None:
        captured: list[Path] = []
        handler = _VaultEventHandler(
            watch_path=Path("/vault/Inbox/Voice"),
            on_change=lambda path: captured.append(path),
        )
        handler.on_created(FileCreatedEvent("/vault/Inbox/Voice/new-note.md"))
        handler.on_modified(FileCreatedEvent("/vault/Inbox/Voice/.hidden.md"))
        handler.on_created(FileCreatedEvent("/vault/Inbox/Voice/new-note.md.tmp"))
        handler.on_created(DirCreatedEvent("/vault/Inbox/Voice/subdir"))

        self.assertEqual(captured, [Path("/vault/Inbox/Voice/new-note.md")])

    def test_vault_event_handler_enqueues_move_destination(self) -> None:
        captured: list[Path] = []
        handler = _VaultEventHandler(
            watch_path=Path("/vault/Inbox/Voice"),
            on_change=lambda path: captured.append(path),
        )
        handler.on_moved(FileMovedEvent("/vault/Inbox/Voice/tmp.md.tmp", "/vault/Inbox/Voice/new-note.md"))

        self.assertEqual(captured, [Path("/vault/Inbox/Voice/new-note.md")])

    def test_load_note_extracts_frontmatter_and_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            note_path = vault_path / "Inbox" / "Voice" / "retry-state-plan.md"
            note_path.parent.mkdir(parents=True)
            note_path.write_text(SEED_NOTE, encoding="utf-8")

            parsed = load_note(note_path, vault_path)

            self.assertEqual(parsed.vault_path, str(vault_path))
            self.assertEqual(parsed.relative_path, "Inbox/Voice/retry-state-plan.md")
            self.assertEqual(parsed.frontmatter["project"], "inbox")
            self.assertIn("project is thtaxmachine", parsed.control_text or "")
            self.assertTrue((parsed.transcript_text or "").startswith("um figure out"))
            self.assertEqual(len(parsed.note_hash), 64)

    def test_eligibility_accepts_seeded_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            note_path = vault_path / "Inbox" / "Voice" / "retry-state-plan.md"
            note_path.parent.mkdir(parents=True)
            note_path.write_text(SEED_NOTE, encoding="utf-8")

            parsed = load_note(note_path, vault_path)
            eligibility = evaluate_eligibility(parsed, "Inbox/Voice")

            self.assertTrue(eligibility.eligible)
            self.assertEqual(eligibility.reasons, [])

    def test_eligibility_accepts_seeded_note_with_slashed_watch_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            note_path = vault_path / "Inbox" / "Voice" / "retry-state-plan.md"
            note_path.parent.mkdir(parents=True)
            note_path.write_text(SEED_NOTE, encoding="utf-8")

            parsed = load_note(note_path, vault_path)
            eligibility = evaluate_eligibility(parsed, "/Inbox/Voice/")

            self.assertTrue(eligibility.eligible)
            self.assertEqual(eligibility.reasons, [])

    def test_import_note_persists_bundle_in_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            note_path = vault_path / "Inbox" / "Voice" / "retry-state-plan.md"
            note_path.parent.mkdir(parents=True)
            note_path.write_text(SEED_NOTE, encoding="utf-8")

            parsed = load_note(note_path, vault_path)
            repository = InMemoryWatcherRepository()

            result = import_note(
                parsed,
                repository=repository,
                webhook_url="http://example.invalid/webhook",
                webhook_enabled=False,
            )

            self.assertTrue(result.imported)
            self.assertIsNotNone(result.intake_note)
            self.assertIsNotNone(result.prompt_generation)
            self.assertIsNotNone(result.delivery)
            self.assertEqual(result.delivery.target_identifier, "claude-tax-main")
            self.assertEqual(len(repository.imported_rows), 1)
            self.assertEqual(repository.imported_rows[0]["llm_runs"], [])

    def test_import_note_persists_optional_llm_runs_in_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            note_path = vault_path / "Inbox" / "Voice" / "retry-state-plan.md"
            note_path.parent.mkdir(parents=True)
            note_path.write_text(SEED_NOTE, encoding="utf-8")

            parsed = load_note(note_path, vault_path)
            repository = InMemoryWatcherRepository()
            bundle = _build_import_bundle(parsed).model_copy(
                update={
                    "llm_runs": [
                        StoredLLMRun(
                            provider_name="openai",
                            model_name="gpt-4.1-mini",
                            mode="review",
                            latency_ms=842,
                            token_usage_json={"input_tokens": 1832, "output_tokens": 214},
                            fallback_chain=["openai", "anthropic"],
                            summary="Prompt looks structurally valid.",
                            findings_json={
                                "findings": [
                                    {
                                        "severity": "low",
                                        "message": "No blocking issues found.",
                                    }
                                ]
                            },
                            raw_response_json={"status": "success", "provider": "openai"},
                        )
                    ]
                }
            )

            result = import_note(
                parsed,
                repository=repository,
                webhook_url="http://example.invalid/webhook",
                webhook_enabled=False,
                bundle=bundle,
            )

            self.assertTrue(result.imported)
            row = repository.imported_rows[0]
            self.assertEqual(len(row["llm_runs"]), 1)
            llm_run = row["llm_runs"][0]
            self.assertEqual(llm_run["provider_name"], "openai")
            self.assertEqual(llm_run["model_name"], "gpt-4.1-mini")
            self.assertEqual(llm_run["mode"], "review")
            self.assertEqual(llm_run["latency_ms"], 842)
            self.assertEqual(llm_run["token_usage_json"]["input_tokens"], 1832)
            self.assertEqual(llm_run["fallback_chain"], ["openai", "anthropic"])
            self.assertEqual(llm_run["summary"], "Prompt looks structurally valid.")
            self.assertEqual(llm_run["findings_json"]["findings"][0]["severity"], "low")

    def test_import_note_skips_duplicate_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            note_path = vault_path / "Inbox" / "Voice" / "retry-state-plan.md"
            note_path.parent.mkdir(parents=True)
            note_path.write_text(SEED_NOTE, encoding="utf-8")

            parsed = load_note(note_path, vault_path)
            repository = InMemoryWatcherRepository()

            first = import_note(
                parsed,
                repository=repository,
                webhook_url="http://example.invalid/webhook",
                webhook_enabled=False,
            )
            second = import_note(
                parsed,
                repository=repository,
                webhook_url="http://example.invalid/webhook",
                webhook_enabled=False,
            )

            self.assertTrue(first.imported)
            self.assertFalse(second.imported)
            self.assertEqual(second.skipped_reason, "duplicate_note_path")

    def test_write_back_note_moves_processed_note_and_updates_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            note_path = vault_path / "Inbox" / "Voice" / "retry-state-plan.md"
            note_path.parent.mkdir(parents=True)
            note_path.write_text(SEED_NOTE, encoding="utf-8")
            os.chmod(note_path, 0o640)
            original_stat = note_path.stat()

            parsed = load_note(note_path, vault_path)
            repository = InMemoryWatcherRepository()
            result = import_note(
                parsed,
                repository=repository,
                webhook_url="http://example.invalid/webhook",
                webhook_enabled=False,
            )
            row = repository.imported_rows[0]

            written_path = write_back_note(
                note_path=note_path,
                note=parsed,
                preprocess=row["preprocess_response"],
                delivery=row["delivery_response"],
                result=result,
                processed_folder="Processed/Voice",
                delivery_status=result.delivery.status,
            )

            self.assertFalse(note_path.exists())
            self.assertTrue(written_path.exists())
            written_stat = written_path.stat()
            self.assertEqual(stat.S_IMODE(written_stat.st_mode), stat.S_IMODE(original_stat.st_mode))
            self.assertEqual(written_stat.st_uid, original_stat.st_uid)
            self.assertEqual(written_stat.st_gid, original_stat.st_gid)
            raw_text = written_path.read_text(encoding="utf-8")
            frontmatter = yaml.safe_load(raw_text.split("---\n", 2)[1])
            self.assertEqual(frontmatter["status"], "processed")
            self.assertFalse(frontmatter["watch_eligible"])
            self.assertEqual(frontmatter["project"], "the-tax-machine")
            self.assertEqual(frontmatter["delivery_status"], "queued")

    def test_dispatch_delivery_writes_obsidian_output_for_auto_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            note_path = vault_path / "Inbox" / "Voice" / "obsidian-delivery.md"
            note_path.parent.mkdir(parents=True)
            note_path.write_text(
                """---
status: new
watch_eligible: true
project: promptforge
destination: obsidian_note
prompt_type: planning
target_identifier: ""
mode: auto_dispatch
priority: high
requires_review: false
---

## Transcript
prepare an implementation note for the watcher roadmap
""",
                encoding="utf-8",
            )

            parsed = load_note(note_path, vault_path)
            repository = InMemoryWatcherRepository()
            result = import_note(
                parsed,
                repository=repository,
                webhook_url="http://example.invalid/webhook",
                webhook_enabled=False,
            )
            row = repository.imported_rows[0]

            dispatched = dispatch_delivery(
                note=parsed,
                render=row["render_response"],
                delivery=row["delivery_response"],
                result=result,
                vault_path=str(vault_path),
                processed_folder="Processed/Voice",
            )

            self.assertEqual(dispatched.status, "delivered")
            self.assertIsNotNone(dispatched.output_path)
            output_text = Path(dispatched.output_path).read_text(encoding="utf-8")
            self.assertIn("prepare an implementation note for the watcher roadmap", output_text.lower())

    def test_repository_update_delivery_status_mutates_in_memory_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            note_path = vault_path / "Inbox" / "Voice" / "retry-state-plan.md"
            note_path.parent.mkdir(parents=True)
            note_path.write_text(SEED_NOTE, encoding="utf-8")

            parsed = load_note(note_path, vault_path)
            repository = InMemoryWatcherRepository()
            result = import_note(
                parsed,
                repository=repository,
                webhook_url="http://example.invalid/webhook",
                webhook_enabled=False,
            )

            repository.update_delivery_status(result.delivery.id, status="failed", error_text="boom")

            row = repository.imported_rows[0]["delivery"]
            self.assertEqual(row["status"], "failed")
            self.assertEqual(row["error_text"], "boom")

    def test_process_note_path_skips_repeated_unchanged_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            note_path = vault_path / "Inbox" / "Voice" / "retry-state-plan.md"
            note_path.parent.mkdir(parents=True)
            note_path.write_text(
                """---
status: new
watch_eligible: false
project: inbox
destination: queue_only
prompt_type: general
---

## Transcript
keep me skipped
""",
                encoding="utf-8",
            )

            cfg = WatcherConfig(
                vault_path=str(vault_path),
                watch_folder="Inbox/Voice",
                processed_folder="Processed/Voice",
                webhook_enabled=False,
            )
            repository = InMemoryWatcherRepository()
            seen_hashes: dict[str, str] = {}

            _process_note_path(
                note_path=note_path,
                cfg=cfg,
                repository=repository,
                seen_hashes=seen_hashes,
                source="event",
            )
            _process_note_path(
                note_path=note_path,
                cfg=cfg,
                repository=repository,
                seen_hashes=seen_hashes,
                source="event",
            )

            self.assertEqual(len(repository.imported_rows), 0)
            self.assertEqual(len(seen_hashes), 1)


if __name__ == "__main__":
    unittest.main()
