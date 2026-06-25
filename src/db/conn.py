"""PostgreSQL connection helpers.

Credentials come from the environment (loaded from .env if present). Connections
are handed out with autocommit=False so the caller owns transaction boundaries.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg


def db_kwargs() -> dict:
    """Connection parameters read from the environment.

    Shared by get_conn (extractors) and the API read-only pool (which also sets
    autocommit=True and a row_factory).
    """
    return {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": int(os.environ.get("PGPORT", "5432")),
        "user": os.environ["PGUSER"],
        "password": os.environ["PGPASSWORD"],
        "dbname": os.environ["PGDATABASE"],
    }


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """Yield a psycopg connection (autocommit=False); the caller commits."""
    conn = psycopg.connect(**db_kwargs(), autocommit=False)
    try:
        yield conn
    finally:
        conn.close()
