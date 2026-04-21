from __future__ import annotations

import json
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from promptforge_services.secrets import encrypt_secret


def backfill_console_secret_rows(database_url: str) -> int:
    return 0
