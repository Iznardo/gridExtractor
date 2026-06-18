"""Ventana Picks / Matchups.

Una fila por pick focal, con el pick rival de carril como campo opcional.
Fuente del carril:
  OFFICIAL/SCRIM  → players.role  (self-join por rol en picks).
  SOLOQ           → picks.stats->>'team_position'  (cruzado con
                    games.stats->'participants', que guarda los 10).

blind/counter: solo OFFICIAL/SCRIM (derivado de pick_order relativo al rival).
Roles de soloq se normalizan al vocabulario interno: MIDDLE→MID, BOTTOM→ADC,
UTILITY→SUPPORT.
Partidas sin rival en el carril se devuelven con opponent=null.
"""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, Query

from src.api.deps import db_conn
from src.api.pagination import Pagination, pagination

router = APIRouter(tags=["matchups"])

# Expresión SQL que normaliza el rol al vocabulario MID/ADC/SUPPORT.
_ROLE = """
  CASE
    WHEN g.game_type != 'SOLOQ' THEN pl.role
    WHEN pk.stats->>'team_position' = 'MIDDLE'  THEN 'MID'
    WHEN pk.stats->>'team_position' = 'BOTTOM'  THEN 'ADC'
    WHEN pk.stats->>'team_position' = 'UTILITY' THEN 'SUPPORT'
    ELSE pk.stats->>'team_position'
  END
"""

_SQL = f"""
SELECT
  g.id         AS game_id,
  g.date,
  g.version,
  g.game_type,
  g.tournament,
  g.result     AS game_result,
  g.team1_id,  t1.name AS team1_name,  t1.tag AS team1_tag,
  g.team2_id,  t2.name AS team2_name,  t2.tag AS team2_tag,
  -- pick focal
  pk.id          AS pick_id,
  pk.side        AS pick_side,
  pk.result      AS pick_result,
  pk.pick_order,
  pk.stats       AS pick_stats,
  pl.id          AS player_id,
  pl.name        AS player_name,
  c.id           AS champ_id,
  c.name         AS champ_name,
  ({_ROLE})      AS role,
  -- rival GRID (OFFICIAL/SCRIM) vía LATERAL
  grid_op.opp_pick_id,
  grid_op.opp_side,
  grid_op.opp_result,
  grid_op.opp_pick_order,
  grid_op.opp_stats,
  grid_op.opp_player_id,
  grid_op.opp_player_name,
  grid_op.opp_champ_id,
  grid_op.opp_champ_name,
  -- rival SoloQ (solo campeón, de games.stats.participants)
  soloq_op.opp_champ_id    AS soloq_opp_champ_id,
  soloq_op.opp_side        AS soloq_opp_side,
  soloq_op.opp_champ_name  AS soloq_opp_champ_name
FROM picks pk
JOIN games   g   ON g.id  = pk.game_id
JOIN players pl  ON pl.id = pk.player_id
JOIN champions c ON c.id  = pk.champ_id
LEFT JOIN teams t1 ON t1.id = g.team1_id
LEFT JOIN teams t2 ON t2.id = g.team2_id
-- rival GRID: mismo game_id, lado opuesto, mismo role (LIMIT 1 — datos sucios en scrims)
LEFT JOIN LATERAL (
  SELECT
    op.id          AS opp_pick_id,
    op.side        AS opp_side,
    op.result      AS opp_result,
    op.pick_order  AS opp_pick_order,
    op.stats       AS opp_stats,
    opp_pl.id      AS opp_player_id,
    opp_pl.name    AS opp_player_name,
    opp_c.id       AS opp_champ_id,
    opp_c.name     AS opp_champ_name
  FROM picks op
  JOIN players   opp_pl ON opp_pl.id = op.player_id AND opp_pl.role = pl.role
  JOIN champions opp_c  ON opp_c.id  = op.champ_id
  WHERE op.game_id = pk.game_id
    AND op.side   != pk.side
  LIMIT 1
) grid_op ON g.game_type != 'SOLOQ' AND pl.role IS NOT NULL
-- rival SoloQ: mismo lane (team_position), lado opuesto, desde participants
LEFT JOIN LATERAL (
  SELECT
    (elem->>'champion_id')::int  AS opp_champ_id,
    elem->>'team_side'           AS opp_side,
    ch.name                      AS opp_champ_name
  FROM jsonb_array_elements(g.stats->'participants') AS elem
  JOIN champions ch ON ch.id = (elem->>'champion_id')::int
  WHERE elem->>'team_side'     != pk.side
    AND elem->>'team_position'  = pk.stats->>'team_position'
  LIMIT 1
) soloq_op ON g.game_type = 'SOLOQ'
              AND pk.stats->>'team_position' IS NOT NULL
              AND pk.stats->>'team_position' != ''
WHERE
  -- solo picks con rol conocido
  (  (g.game_type != 'SOLOQ' AND pl.role IS NOT NULL)
  OR (g.game_type  = 'SOLOQ'
      AND pk.stats->>'team_position' IS NOT NULL
      AND pk.stats->>'team_position' != ''))
  -- dedup GRID sin champ_id focal: mostrar solo lado BLUE (evita duplicar cada carril)
  AND (%(champ_id)s::int IS NOT NULL OR g.game_type = 'SOLOQ' OR pk.side = 'BLUE')
  -- filtros
  AND (%(game_type)s::text  IS NULL OR g.game_type  = %(game_type)s)
  AND (%(patch)s::text      IS NULL OR g.version    = %(patch)s)
  AND (%(tournament)s::text IS NULL OR g.tournament = %(tournament)s)
  AND (%(champ_id)s::int    IS NULL OR pk.champ_id  = %(champ_id)s)
  AND (%(role)s::text       IS NULL OR ({_ROLE})     = %(role)s)
  AND (%(champ_id2)s::int   IS NULL
       OR grid_op.opp_champ_id   = %(champ_id2)s
       OR soloq_op.opp_champ_id  = %(champ_id2)s)
  AND (%(pick_relation)s::text IS NULL
       OR g.game_type = 'SOLOQ'
       OR (%(pick_relation)s = 'blind'
           AND pk.pick_order          IS NOT NULL
           AND grid_op.opp_pick_order IS NOT NULL
           AND pk.pick_order < grid_op.opp_pick_order)
       OR (%(pick_relation)s = 'counter'
           AND pk.pick_order          IS NOT NULL
           AND grid_op.opp_pick_order IS NOT NULL
           AND pk.pick_order > grid_op.opp_pick_order))
ORDER BY g.date DESC, pk.id DESC
LIMIT %(limit)s OFFSET %(offset)s
"""


def _pick_relation(a: int | None, b: int | None) -> str | None:
    if a is None or b is None:
        return None
    return "blind" if a < b else "counter"


def _team_obj(tid, name, tag):
    if tid is None:
        return None
    return {"id": tid, "name": name, "tag": tag}


def _shape(row: dict) -> dict:
    is_soloq = row["game_type"] == "SOLOQ"

    pick_rel = None if is_soloq else _pick_relation(row["pick_order"], row.get("opp_pick_order"))
    focal = {
        "side": row["pick_side"],
        "result": row["pick_result"],
        "pick_order": row["pick_order"],
        "pick_relation": pick_rel,
        "player": {"id": row["player_id"], "name": row["player_name"]},
        "champion": {"id": row["champ_id"], "name": row["champ_name"]},
        "stats": row["pick_stats"],
    }

    opponent = None
    if not is_soloq and row.get("opp_pick_id") is not None:
        opponent = {
            "side": row["opp_side"],
            "result": row["opp_result"],
            "pick_order": row["opp_pick_order"],
            "pick_relation": _pick_relation(row["opp_pick_order"], row["pick_order"]),
            "player": {"id": row["opp_player_id"], "name": row["opp_player_name"]},
            "champion": {"id": row["opp_champ_id"], "name": row["opp_champ_name"]},
            "stats": row["opp_stats"],
        }
    elif is_soloq and row.get("soloq_opp_champ_id") is not None:
        opp_side = row["soloq_opp_side"]
        opp_result = (row["game_result"] == opp_side) if opp_side else None
        opponent = {
            "side": opp_side,
            "result": opp_result,
            "pick_order": None,
            "pick_relation": None,
            "player": None,       # untrackeado — no hay fila en picks
            "champion": {"id": row["soloq_opp_champ_id"], "name": row["soloq_opp_champ_name"]},
            "stats": None,
        }

    return {
        "game_id": row["game_id"],
        "date": row["date"],
        "version": row["version"],
        "game_type": row["game_type"],
        "tournament": row["tournament"],
        "role": row["role"],
        "game_result": row["game_result"],
        "team1": _team_obj(row["team1_id"], row["team1_name"], row["team1_tag"]),
        "team2": _team_obj(row["team2_id"], row["team2_name"], row["team2_tag"]),
        "pick": focal,
        "opponent": opponent,
    }


@router.get("/matchups")
def list_matchups(
    champ_id: int | None = None,
    champ_id2: int | None = None,
    role: str | None = Query(None, description="TOP|JUNGLE|MID|ADC|SUPPORT"),
    tournament: str | None = None,
    patch: str | None = Query(None, description="games.version, ej. 14.23"),
    pick_relation: str | None = Query(None, pattern="^(blind|counter)$"),
    game_type: str | None = Query(None, description="OFFICIAL | SCRIM | SOLOQ"),
    page: Pagination = Depends(pagination),
    conn: psycopg.Connection = Depends(db_conn),
):
    params = {
        "champ_id": champ_id,
        "champ_id2": champ_id2,
        "role": role,
        "tournament": tournament,
        "patch": patch,
        "pick_relation": pick_relation,
        "game_type": game_type,
        "limit": page.limit,
        "offset": page.offset,
    }
    with conn.cursor() as cur:
        cur.execute(_SQL, params)
        rows = cur.fetchall()
    return [_shape(r) for r in rows]
