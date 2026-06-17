"""Picks — primitivo crudo de detalle / drill-down.

Una fila por (jugador, partida). Filtros por tipo de partida, jugador, campeon,
parche y partida concreta. `stats` se devuelve tal cual (JSONB; contrato
alineado oficiales/scrims/soloq, CLAUDE.md §10).
"""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, Query

from src.api.deps import db_conn
from src.api.pagination import Pagination, pagination

router = APIRouter(tags=["picks"])


_SQL = """
SELECT
  pk.id AS pick_id, pk.game_id, pk.side, pk.result, pk.pick_order, pk.stats,
  g.date, g.version, g.game_type, g.tournament,
  pl.id AS player_id, pl.name AS player_name, pl.role AS player_role,
  c.id  AS champ_id,  c.name  AS champ_name
FROM picks pk
JOIN games g     ON g.id  = pk.game_id
JOIN players pl  ON pl.id = pk.player_id
JOIN champions c ON c.id  = pk.champ_id
WHERE (%(game_type)s::text IS NULL OR g.game_type = %(game_type)s)
  AND (%(player_id)s::int IS NULL OR pk.player_id = %(player_id)s)
  AND (%(champ_id)s::int  IS NULL OR pk.champ_id  = %(champ_id)s)
  AND (%(patch)s::text     IS NULL OR g.version    = %(patch)s)
  AND (%(game_id)s::int   IS NULL OR pk.game_id   = %(game_id)s)
ORDER BY g.date DESC, pk.id DESC
LIMIT %(limit)s OFFSET %(offset)s
"""


def _shape(row: dict) -> dict:
    return {
        "pick_id": row["pick_id"],
        "game_id": row["game_id"],
        "date": row["date"],
        "version": row["version"],
        "game_type": row["game_type"],
        "tournament": row["tournament"],
        "side": row["side"],
        "result": row["result"],
        "pick_order": row["pick_order"],
        "player": {"id": row["player_id"], "name": row["player_name"], "role": row["player_role"]},
        "champion": {"id": row["champ_id"], "name": row["champ_name"]},
        "stats": row["stats"],
    }


@router.get("/picks")
def list_picks(
    game_type: str | None = Query(None, description="OFFICIAL | SCRIM | SOLOQ"),
    player_id: int | None = None,
    champ_id: int | None = None,
    patch: str | None = Query(None, description="games.version, ej. 14.23"),
    game_id: int | None = None,
    page: Pagination = Depends(pagination),
    conn: psycopg.Connection = Depends(db_conn),
):
    params = {
        "game_type": game_type,
        "player_id": player_id,
        "champ_id": champ_id,
        "patch": patch,
        "game_id": game_id,
        "limit": page.limit,
        "offset": page.offset,
    }
    with conn.cursor() as cur:
        cur.execute(_SQL, params)
        rows = cur.fetchall()
    return [_shape(r) for r in rows]
