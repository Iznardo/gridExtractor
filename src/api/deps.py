"""Dependencias compartidas de la API.

- `db_conn`: entrega una conexion del pool (psycopg_pool) por request. El pool
  se crea en el lifespan (`main.py`) con autocommit=True y row_factory=dict_row,
  asi que cada conexion ya viene configurada para solo-lectura.
- `get_champ_map`: expone el catalogo de campeones (ChampMap) cacheado en
  `app.state` durante el lifespan, para resolver nombres sin golpear la BD en
  cada draft. ChampMap se auto-recarga si falta una clave (campeon nuevo).
"""

from __future__ import annotations

import logging
import time
from typing import Iterator

import psycopg
from fastapi import Request

log = logging.getLogger("api")

# Cooldown minimo entre recargas de ChampMap ante un miss, para no martillear la
# BD si llegan ids desconocidos en rafaga.
_RELOAD_COOLDOWN_S = 60.0


class ChampMap:
    """Catalogo id->name de campeones, con recarga perezosa ante un miss.

    Las rutas solo usan `.get(cid)`; si el id no esta (campeon recien anadido a
    `champions` por un extractor mientras la API ya corria), se intenta UNA
    recarga por ventana de cooldown. Tambien sirve como auto-curacion si la BD
    estaba caida al arrancar (mapa vacio -> primer acceso lo rellena).
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
        except Exception as e:  # BD caida / transitorio: no romper la request
            log.warning("ChampMap: recarga fallida: %s", e)
            self._last_reload = time.monotonic()  # respeta el cooldown igual

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
