"""Dependencias compartidas de la API.

- `db_conn`: entrega una conexion psycopg por request (row_factory dict_row),
  reutilizando `src.db.conn.get_conn` — no duplicamos la logica de conexion.
- `get_champ_map`: expone el catalogo de campeones (id -> name) cacheado en
  `app.state` durante el lifespan (ver `main.py`), para resolver nombres sin
  golpear la BD en cada draft.
"""

from __future__ import annotations

from typing import Iterator

import psycopg
from fastapi import Request
from psycopg.rows import dict_row

from src.db.conn import get_conn


def db_conn() -> Iterator[psycopg.Connection]:
    with get_conn() as conn:
        conn.row_factory = dict_row
        yield conn


def get_champ_map(request: Request) -> dict[int, str]:
    return request.app.state.champ_map
