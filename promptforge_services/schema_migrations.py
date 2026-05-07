from __future__ import annotations

import psycopg


def ensure_intake_notes_route_json(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                ALTER TABLE intake_notes
                ADD COLUMN IF NOT EXISTS route_json JSONB NOT NULL DEFAULT '{}'::jsonb;

                CREATE INDEX IF NOT EXISTS idx_intake_notes_route_family
                ON intake_notes ((route_json->>'route_family'));

                CREATE INDEX IF NOT EXISTS idx_intake_notes_route_supported
                ON intake_notes ((route_json->>'supported'));
                """
            )
        conn.commit()
