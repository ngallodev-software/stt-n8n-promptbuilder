from __future__ import annotations

import psycopg

from promptforge_services.schema_migrations import ensure_intake_notes_route_json


def test_ensure_intake_notes_route_json_is_idempotent(seeded_console_database_url: str) -> None:
    ensure_intake_notes_route_json(seeded_console_database_url)
    ensure_intake_notes_route_json(seeded_console_database_url)

    with psycopg.connect(seeded_console_database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'intake_notes'
                  AND column_name = 'route_json'
                """
            )
            row = cur.fetchone()

    assert row is not None
