"""Ventana 1 — Drafts.

Lista drafts (oficiales y scrims; soloq queda fuera porque no tiene draft).
Filtros por equipo, rival, parche, fase de pick (first/second) y campeon jugado.

Recordatorio de esquema (CLAUDE.md / extractores):
- `games.team1_id` = lado BLUE, `team2_id` = lado RED.
- En `drafts`, pick1..5/ban1..5 = equipo FIRST PICK; pick6..10/ban6..10 =
  equipo SECOND PICK (cada grupo en orden cronologico del equipo).
- First/second pick esta DESACOPLADO de blue/red (cambio 2026): se exponen
  ambos ejes por separado, sin inferir uno del otro.
"""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import db_conn, get_champ_map
from src.api.pagination import Pagination, pagination

router = APIRouter(tags=["drafts"])


_SQL = """
SELECT
  g.id AS game_id, g.date, g.version, g.game_type, g.tournament, g.result,
  g.team1_id, t1.name AS team1_name, t1.tag AS team1_tag,
  g.team2_id, t2.name AS team2_name, t2.tag AS team2_tag,
  d.first_pick_team_id, tf.name AS fp_name, tf.tag AS fp_tag,
  d.ban1,d.ban2,d.ban3,d.ban4,d.ban5,d.ban6,d.ban7,d.ban8,d.ban9,d.ban10,
  d.pick1,d.pick2,d.pick3,d.pick4,d.pick5,d.pick6,d.pick7,d.pick8,d.pick9,d.pick10
FROM games g
JOIN drafts d   ON d.id = g.draft_id
LEFT JOIN teams t1 ON t1.id = g.team1_id
LEFT JOIN teams t2 ON t2.id = g.team2_id
LEFT JOIN teams tf ON tf.id = d.first_pick_team_id
WHERE g.draft_id IS NOT NULL
  AND (%(team_id)s::int   IS NULL OR g.team1_id = %(team_id)s OR g.team2_id = %(team_id)s)
  AND (%(rival_id)s::int  IS NULL OR g.team1_id = %(rival_id)s OR g.team2_id = %(rival_id)s)
  AND (%(patch)s::text     IS NULL OR g.version   = %(patch)s)
  AND (%(game_type)s::text  IS NULL OR g.game_type  = %(game_type)s)
  AND (%(tournament)s::text IS NULL OR g.tournament = %(tournament)s)
  AND (%(pick_phase)s::text IS NULL OR
       (%(pick_phase)s = 'first'  AND d.first_pick_team_id =  %(team_id)s) OR
       (%(pick_phase)s = 'second' AND d.first_pick_team_id <> %(team_id)s))
  AND (%(champ_id)s::int IS NULL OR (
       CASE
         WHEN %(team_id)s IS NOT NULL AND d.first_pick_team_id =  %(team_id)s
              THEN %(champ_id)s = ANY(ARRAY[d.pick1,d.pick2,d.pick3,d.pick4,d.pick5])
         WHEN %(team_id)s IS NOT NULL AND d.first_pick_team_id <> %(team_id)s
              THEN %(champ_id)s = ANY(ARRAY[d.pick6,d.pick7,d.pick8,d.pick9,d.pick10])
         ELSE %(champ_id)s = ANY(ARRAY[d.pick1,d.pick2,d.pick3,d.pick4,d.pick5,
                                       d.pick6,d.pick7,d.pick8,d.pick9,d.pick10])
       END))
ORDER BY g.date DESC, g.id DESC
LIMIT %(limit)s OFFSET %(offset)s
"""


def _champ(champ_map: dict[int, str], cid: int | None):
    if cid is None:
        return None
    return {"id": cid, "name": champ_map.get(cid)}


def _team_obj(tid, name, tag):
    if tid is None:
        return None
    return {"id": tid, "name": name, "tag": tag}


def _shape(row: dict, champ_map: dict[int, str]) -> dict:
    fp_id = row["first_pick_team_id"]
    if fp_id is not None and fp_id == row["team1_id"]:
        fp_side = "BLUE"
    elif fp_id is not None and fp_id == row["team2_id"]:
        fp_side = "RED"
    else:
        fp_side = None

    first_pick_team = None
    if fp_id is not None:
        first_pick_team = {
            "id": fp_id, "name": row["fp_name"], "tag": row["fp_tag"],
            "side": fp_side,
        }

    return {
        "game_id": row["game_id"],
        "date": row["date"],
        "version": row["version"],
        "game_type": row["game_type"],
        "tournament": row["tournament"],
        "result": row["result"],
        "team1": _team_obj(row["team1_id"], row["team1_name"], row["team1_tag"]),
        "team2": _team_obj(row["team2_id"], row["team2_name"], row["team2_tag"]),
        "first_pick_team": first_pick_team,
        "first_pick": {
            "bans":  [_champ(champ_map, row[f"ban{i}"])  for i in range(1, 6)],
            "picks": [_champ(champ_map, row[f"pick{i}"]) for i in range(1, 6)],
        },
        "second_pick": {
            "bans":  [_champ(champ_map, row[f"ban{i}"])  for i in range(6, 11)],
            "picks": [_champ(champ_map, row[f"pick{i}"]) for i in range(6, 11)],
        },
    }


@router.get("/drafts")
def list_drafts(
    team_id: int | None = None,
    rival_id: int | None = None,
    patch: str | None = Query(None, description="games.version, ej. 14.23"),
    pick_phase: str | None = Query(None, pattern="^(first|second)$"),
    champ_id: int | None = None,
    game_type: str | None = Query(None, description="OFFICIAL | SCRIM"),
    tournament: str | None = None,
    page: Pagination = Depends(pagination),
    conn: psycopg.Connection = Depends(db_conn),
    champ_map: dict[int, str] = Depends(get_champ_map),
):
    if pick_phase and team_id is None:
        raise HTTPException(400, "pick_phase requiere team_id")

    params = {
        "team_id": team_id,
        "rival_id": rival_id,
        "patch": patch,
        "pick_phase": pick_phase,
        "champ_id": champ_id,
        "game_type": game_type,
        "tournament": tournament,
        "limit": page.limit,
        "offset": page.offset,
    }
    with conn.cursor() as cur:
        cur.execute(_SQL, params)
        rows = cur.fetchall()
    return [_shape(r, champ_map) for r in rows]
