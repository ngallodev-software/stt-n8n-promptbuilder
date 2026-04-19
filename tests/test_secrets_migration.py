from __future__ import annotations

import psycopg
from cryptography.fernet import Fernet
from psycopg.rows import dict_row

from promptforge_services.secrets import decrypt_secret
from promptforge_services.secrets_migration import backfill_console_secret_rows


def _fetch_one(database_url: str, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
    return dict(row) if row else {}


def test_backfill_console_secret_rows_encrypts_plaintext_and_audits(
    seeded_console_database_url: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROMPTFORGE_SECRETS_MASTER_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("PROMPTFORGE_SECRETS_KEY_VERSION", "7")

    with psycopg.connect(seeded_console_database_url, autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO console_secret_settings (
                scope, project_id, key, secret_value, configured, last_rotated_at, updated_by_user_id
            ) VALUES ('global', NULL, 'LEGACY_TEST_SECRET', 'legacy-openai-secret', TRUE, now(), 'legacy')
            """
        )

    migrated = backfill_console_secret_rows(seeded_console_database_url)
    assert migrated == 1

    stored = _fetch_one(
        seeded_console_database_url,
        """
        SELECT secret_value, secret_ciphertext, secret_key_version, configured
        FROM console_secret_settings
        WHERE scope = 'global' AND project_id IS NULL AND key = 'LEGACY_TEST_SECRET'
        LIMIT 1
        """,
    )
    assert stored["secret_value"] is None
    assert stored["secret_key_version"] == 7
    assert stored["configured"] is True
    assert stored["secret_ciphertext"]
    assert decrypt_secret(str(stored["secret_ciphertext"])) == "legacy-openai-secret"

    audit = _fetch_one(
        seeded_console_database_url,
        """
        SELECT actor, payload_json
        FROM console_admin_audit_log
        WHERE action = 'secret_settings_backfilled'
        ORDER BY created_at DESC
        LIMIT 1
        """,
    )
    assert audit["actor"] == "system:migration"
    assert audit["payload_json"]["count"] == 1
    assert audit["payload_json"]["keys_migrated"] == ["LEGACY_TEST_SECRET"]


def test_backfill_console_secret_rows_is_noop_without_plaintext(
    seeded_console_database_url: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROMPTFORGE_SECRETS_MASTER_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("PROMPTFORGE_SECRETS_KEY_VERSION", "1")

    migrated = backfill_console_secret_rows(seeded_console_database_url)
    assert migrated == 0
