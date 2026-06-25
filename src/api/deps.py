"""Shared API dependencies.

- `db_conn`: hands out a pooled connection (psycopg_pool) per request. The pool
  is created in the lifespan (`main.py`) with autocommit=True and
  row_factory=dict_row, so every connection comes ready for read-only use.
- `get_champ_map`: exposes the champion catalog (ChampMap) cached on
  `app.state`, to resolve names without hitting the DB on every draft. ChampMap
  reloads itself if a key is missing (new champion).
"""

from __future__ import annotations

import logging
import time
from typing import Iterator

import psycopg
from fastapi import Request

log = logging.getLogger("api")

# Minimum cooldown between ChampMap reloads on a miss, to avoid hammering the DB
# when unknown ids arrive in bursts.
_RELOAD_COOLDOWN_S = 60.0


class ChampMap:
    """id->name champion catalog, with lazy reload on a miss.

    Routes only call `.get(cid)`; if the id is absent (champion just added to
    `champions` by an extractor while the API was already running), one reload
    is attempted per cooldown window. It also self-heals when the DB was down at
    startup (empty map -> first access fills it).
    """

    def __init__(self, pool) -> None:
        self._pool = pool
        self._map: dict[int, str] = {}
        self._last_reload = 0.0

    def reload(self) -> int:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name FROM champions")
                self._map = {r["id"]: r["name"] for r in cur.fetchall()}
        self._last_reload = time.monotonic()
        return len(self._map)

    def _maybe_reload(self) -> None:
        if time.monotonic() - self._last_reload < _RELOAD_COOLDOWN_S:
            return
        try:
            self.reload()
        except Exception as e:  # DB down / transient: do not break the request
            log.warning("ChampMap: reload failed: %s", e)
            self._last_reload = time.monotonic()  # honor the cooldown anyway

    def get(self, cid: int | None) -> str | None:
        if cid is None:
            return None
        name = self._map.get(cid)
        if name is None:
            self._maybe_reload()
            name = self._map.get(cid)
        return name

    def __len__(self) -> int:
        return len(self._map)


def db_conn(request: Request) -> Iterator[psycopg.Connection]:
    with request.app.state.pool.connection() as conn:
        yield conn


def get_champ_map(request: Request) -> ChampMap:
    return request.app.state.champ_map
