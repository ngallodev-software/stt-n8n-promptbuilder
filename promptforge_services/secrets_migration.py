from __future__ import annotations

import json
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from promptforge_services.secrets import encrypt_secret


def backfill_console_secret_rows(database_url: str) -> int:
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, key, secret_value
                FROM console_secret_settings
                WHERE secret_value IS NOT NULL
                  AND length(trim(secret_value)) > 0
                ORDER BY updated_at ASC, created_at ASC, id ASC
                """
            )
            rows = [dict(row) for row in cur.fetchall()]
            if not rows:
                conn.commit()
                return 0

            migrated_keys: list[str] = []
            for row in rows:
                encrypted = encrypt_secret(str(row["secret_value"]))
                cur.execute(
                    """
                    UPDATE console_secret_settings
                    SET secret_value = NULL,
                        secret_ciphertext = %s,
                        secret_key_version = %s,
                        configured = TRUE,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (encrypted.ciphertext, encrypted.key_version, row["id"]),
                )
                migrated_keys.append(str(row["key"]))

            cur.execute(
                """
                INSERT INTO console_admin_audit_log (action, actor, payload_json, created_at)
                VALUES (%s, %s, %s::jsonb, %s)
                """,
                (
                    "secret_settings_backfilled",
                    "system:migration",
                    json.dumps(
                        {
                            "keys_migrated": migrated_keys,
                            "count": len(migrated_keys),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    ),
                    datetime.now(timezone.utc),
                ),
            )
        conn.commit()
    return len(rows)
