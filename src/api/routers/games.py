"""Ventana 3 — Games.

Busca partidas por campeon, matchup (campeon vs campeon), parche, equipo y
fechas. Devuelve, ademas de los metadatos, las composiciones de cada lado
(que campeones se jugaron en BLUE vs RED). El detalle fino de la partida
(stats por jugador, draft) se obtiene luego con `/picks` / `/drafts` por
`game_id`.

`team1` = lado BLUE, `team2` = lado RED.
Matchup: `champ_id` + `champ_id2` ambos presentes; `opposing=true` los exige en
lados opuestos (el "vs" real). En soloq solo hay picks de jugadores trackeados,
asi que la composicion puede venir incompleta ahi.
"""

from __future__ import annotations

from datetime import date

import psycopg
from fastapi import APIRouter, Depends, Query

from src.api.deps import db_conn, get_champ_map
from src.api.pagination import Pagination, pagination

router = APIRouter(tags=["games"])


_SQL = """
SELECT
  g.id AS game_id, g.date, g.version, g.game_type, g.tournament, g.result,
  g.team1_id, t1.name AS team1_name, t1.tag AS team1_tag,
  g.team2_id, t2.name AS team2_name, t2.tag AS team2_tag,
  g.stats
FROM games g
LEFT JOIN teams t1 ON t1.id = g.team1_id
LEFT JOIN teams t2 ON t2.id = g.team2_id
WHERE (%(team_id)s::int   IS NULL OR g.team1_id = %(team_id)s OR g.team2_id = %(team_id)s)
  AND (%(patch)s::text     IS NULL OR g.version   = %(patch)s)
  AND (%(game_type)s::text IS NULL OR g.game_type = %(game_type)s)
  AND (%(date_from)s::date IS NULL OR g.date >= %(date_from)s)
  AND (%(date_to)s::date   IS NULL OR g.date <= %(date_to)s)
  AND (%(champ_id)s::int   IS NULL OR EXISTS (
        SELECT 1 FROM picks p WHERE p.game_id = g.id AND p.champ_id = %(champ_id)s))
  AND (%(champ_id2)s::int  IS NULL OR EXISTS (
        SELECT 1 FROM picks p WHERE p.game_id = g.id AND p.champ_id = %(champ_id2)s))
  AND (NOT %(opposing)s OR %(champ_id)s IS NULL OR %(champ_id2)s IS NULL OR EXISTS (
        SELECT 1 FROM picks pa JOIN picks pb ON pa.game_id = pb.game_id
        WHERE pa.game_id = g.id
          AND pa.champ_id = %(champ_id)s AND pb.champ_id = %(champ_id2)s
          AND pa.side <> pb.side))
ORDER BY g.date DESC, g.id DESC
LIMIT %(limit)s OFFSET %(offset)s
"""

# Composiciones de la pagina de partidas, en una sola query (evita N+1).
# Orden por rol del jugador (players.role) para que cada lado salga de TOP a
# SUPPORT — en oficiales/scrims `picks` no trae posicion, pero `players` si.
# (Soloq no pasa por aqui: su composicion sale de stats.participants.)
_PICKS_SQL = """
SELECT pk.game_id, pk.side, pk.champ_id
FROM picks pk
LEFT JOIN players pl ON pl.id = pk.player_id
WHERE pk.game_id = ANY(%(ids)s)
ORDER BY pk.game_id, pk.side,
  CASE pl.role WHEN 'TOP' THEN 0 WHEN 'JUNGLE' THEN 1 WHEN 'MID' THEN 2
               WHEN 'ADC' THEN 3 WHEN 'SUPPORT' THEN 4 ELSE 9 END,
  pk.pick_order NULLS LAST, pk.champ_id
"""


def _team_obj(tid, name, tag):
    if tid is None:
        return None
    return {"id": tid, "name": name, "tag": tag}


def _comp_from_stats(stats) -> dict | None:
    """Composicion (10 campeones) desde games.stats.participants — el caso de
    soloq, donde `picks` solo tiene a los jugadores trackeados. Devuelve None
    si no hay participants (oficiales/scrims: se usa `picks`)."""
    if not isinstance(stats, dict):
        return None
    parts = stats.get("participants")
    if not parts:
        return None
    comp = {"BLUE": [], "RED": []}
    for p in parts:
        side = p.get("team_side")
        cid = p.get("champion_id")
        if side in comp and cid is not None:
            comp[side].append(cid)
    return comp


def _shape(row: dict, comps: dict, champ_map: dict[int, str]) -> dict:
    comp = _comp_from_stats(row.get("stats")) or comps.get(
        row["game_id"], {"BLUE": [], "RED": []}
    )
    return {
        "game_id": row["game_id"],
        "date": row["date"],
        "version": row["version"],
        "game_type": row["game_type"],
        "tournament": row["tournament"],
        "result": row["result"],
        "team1": _team_obj(row["team1_id"], row["team1_name"], row["team1_tag"]),
        "team2": _team_obj(row["team2_id"], row["team2_name"], row["team2_tag"]),
        "blue_champions": [
            {"id": cid, "name": champ_map.get(cid)} for cid in comp["BLUE"]
        ],
        "red_champions": [
            {"id": cid, "name": champ_map.get(cid)} for cid in comp["RED"]
        ],
    }


@router.get("/games")
def list_games(
    team_id: int | None = None,
    patch: str | None = Query(None, description="games.version, ej. 14.23"),
    game_type: str | None = Query(None, description="OFFICIAL | SCRIM | SOLOQ"),
    champ_id: int | None = Query(None, description="Campeon presente en la partida"),
    champ_id2: int | None = Query(None, description="Segundo campeon (matchup)"),
    opposing: bool = Query(False, description="Exigir champ_id y champ_id2 en lados opuestos"),
    date_from: date | None = None,
    date_to: date | None = None,
    page: Pagination = Depends(pagination),
    conn: psycopg.Connection = Depends(db_conn),
    champ_map: dict[int, str] = Depends(get_champ_map),
):
    params = {
        "team_id": team_id,
        "patch": patch,
        "game_type": game_type,
        "champ_id": champ_id,
        "champ_id2": champ_id2,
        "opposing": opposing,
        "date_from": date_from,
        "date_to": date_to,
        "limit": page.limit,
        "offset": page.offset,
    }
    with conn.cursor() as cur:
        cur.execute(_SQL, params)
        rows = cur.fetchall()

        comps: dict[int, dict] = {}
        ids = [r["game_id"] for r in rows]
        if ids:
            cur.execute(_PICKS_SQL, {"ids": ids})
            for p in cur.fetchall():
                bucket = comps.setdefault(p["game_id"], {"BLUE": [], "RED": []})
                if p["side"] in bucket:
                    bucket[p["side"]].append(p["champ_id"])

    return [_shape(r, comps, champ_map) for r in rows]
