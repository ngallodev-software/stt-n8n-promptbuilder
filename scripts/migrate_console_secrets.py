#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

from promptforge_services.secrets import SecretsEncryptionError
from promptforge_services.secrets_migration import backfill_console_secret_rows


def main() -> int:
    database_url = os.getenv("PROMPTFORGE_DATABASE_URL")
    if not database_url:
        print("PROMPTFORGE_DATABASE_URL is required", file=sys.stderr)
        return 1
    try:
        migrated = backfill_console_secret_rows(database_url)
    except SecretsEncryptionError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"migrated_console_secrets={migrated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
