"""Ventana Picks / Matchups (1v1 y 2v2).

1v1: una fila por pick focal, con el pick rival de carril como campo opcional.
2v2: además del pick focal (Aliado 1), un segundo aliado del mismo lado
     (Aliado 2) y los dos rivales derivados por rol del lado contrario. Se activa
     cuando llega `champ_id_b`.

Fuente del carril:
  OFFICIAL/SCRIM  → players.role  (self-join por rol en picks).
  SOLOQ           → picks.stats->>'team_position'  (cruzado con
                    games.stats->'participants', que guarda los 10).

blind/counter: solo OFFICIAL/SCRIM (derivado de pick_order relativo al rival),
solo en 1v1.
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


def _role_expr(pl_alias: str, pk_alias: str) -> str:
    """CASE que normaliza el rol al vocabulario MID/ADC/SUPPORT para un par
    (players, picks) dado por sus alias SQL."""
    return f"""
  CASE
    WHEN g.game_type != 'SOLOQ' THEN {pl_alias}.role
    WHEN {pk_alias}.stats->>'team_position' = 'MIDDLE'  THEN 'MID'
    WHEN {pk_alias}.stats->>'team_position' = 'BOTTOM'  THEN 'ADC'
    WHEN {pk_alias}.stats->>'team_position' = 'UTILITY' THEN 'SUPPORT'
    ELSE {pk_alias}.stats->>'team_position'
  END"""


_ROLE = _role_expr("pl", "pk")
_ROLE_ALLY = _role_expr("ally_pl", "ally")

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
  -- pick focal (Aliado 1)
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
  -- rival GRID de Aliado 1 (OFFICIAL/SCRIM) vía LATERAL
  grid_op.opp_pick_id,
  grid_op.opp_side,
  grid_op.opp_result,
  grid_op.opp_pick_order,
  grid_op.opp_stats,
  grid_op.opp_player_id,
  grid_op.opp_player_name,
  grid_op.opp_champ_id,
  grid_op.opp_champ_name,
  -- rival SoloQ de Aliado 1 (solo campeón, de games.stats.participants)
  soloq_op.opp_champ_id    AS soloq_opp_champ_id,
  soloq_op.opp_side        AS soloq_opp_side,
  soloq_op.opp_champ_name  AS soloq_opp_champ_name,
  -- Aliado 2 (solo 2v2)
  ally2.ally_pick_id,
  ally2.ally_side,
  ally2.ally_result,
  ally2.ally_pick_order,
  ally2.ally_stats,
  ally2.ally_player_id,
  ally2.ally_player_name,
  ally2.ally_champ_id,
  ally2.ally_champ_name,
  ally2.ally_role,
  -- rival GRID de Aliado 2
  grid_op_b.opp_pick_id      AS b_opp_pick_id,
  grid_op_b.opp_side         AS b_opp_side,
  grid_op_b.opp_result       AS b_opp_result,
  grid_op_b.opp_pick_order   AS b_opp_pick_order,
  grid_op_b.opp_stats        AS b_opp_stats,
  grid_op_b.opp_player_id    AS b_opp_player_id,
  grid_op_b.opp_player_name  AS b_opp_player_name,
  grid_op_b.opp_champ_id     AS b_opp_champ_id,
  grid_op_b.opp_champ_name   AS b_opp_champ_name,
  -- rival SoloQ de Aliado 2
  soloq_op_b.opp_champ_id    AS b_soloq_opp_champ_id,
  soloq_op_b.opp_side        AS b_soloq_opp_side,
  soloq_op_b.opp_champ_name  AS b_soloq_opp_champ_name
FROM picks pk
JOIN games   g   ON g.id  = pk.game_id
JOIN players pl  ON pl.id = pk.player_id
JOIN champions c ON c.id  = pk.champ_id
LEFT JOIN teams t1 ON t1.id = g.team1_id
LEFT JOIN teams t2 ON t2.id = g.team2_id
-- rival GRID Aliado 1: mismo game_id, lado opuesto, mismo role (LIMIT 1 — datos sucios en scrims)
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
-- rival SoloQ Aliado 1: mismo lane (team_position), lado opuesto, desde participants
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
-- Aliado 2 (solo 2v2): mismo game_id, mismo lado, otro pick, campeón = champ_id_b
LEFT JOIN LATERAL (
  SELECT
    ally.id          AS ally_pick_id,
    ally.side        AS ally_side,
    ally.result      AS ally_result,
    ally.pick_order  AS ally_pick_order,
    ally.stats       AS ally_stats,
    ally_pl.id       AS ally_player_id,
    ally_pl.name     AS ally_player_name,
    ally_pl.role     AS ally_player_role,
    ally_c.id        AS ally_champ_id,
    ally_c.name      AS ally_champ_name,
    ({_ROLE_ALLY})   AS ally_role
  FROM picks ally
  JOIN players   ally_pl ON ally_pl.id = ally.player_id
  JOIN champions ally_c  ON ally_c.id  = ally.champ_id
  WHERE ally.game_id = pk.game_id
    AND ally.side    = pk.side
    AND ally.id     != pk.id
    AND ally.champ_id = %(champ_id_b)s
    AND (%(role_b)s::text IS NULL OR ({_ROLE_ALLY}) = %(role_b)s)
  LIMIT 1
) ally2 ON %(champ_id_b)s::int IS NOT NULL
-- rival GRID Aliado 2: lado opuesto, mismo role que Aliado 2
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
  JOIN players   opp_pl ON opp_pl.id = op.player_id AND opp_pl.role = ally2.ally_player_role
  JOIN champions opp_c  ON opp_c.id  = op.champ_id
  WHERE op.game_id = pk.game_id
    AND op.side   != pk.side
  LIMIT 1
) grid_op_b ON g.game_type != 'SOLOQ' AND ally2.ally_player_role IS NOT NULL
-- rival SoloQ Aliado 2: mismo lane que Aliado 2, lado opuesto, desde participants
LEFT JOIN LATERAL (
  SELECT
    (elem->>'champion_id')::int  AS opp_champ_id,
    elem->>'team_side'           AS opp_side,
    ch.name                      AS opp_champ_name
  FROM jsonb_array_elements(g.stats->'participants') AS elem
  JOIN champions ch ON ch.id = (elem->>'champion_id')::int
  WHERE elem->>'team_side'     != pk.side
    AND elem->>'team_position'  = ally2.ally_stats->>'team_position'
  LIMIT 1
) soloq_op_b ON g.game_type = 'SOLOQ'
                AND ally2.ally_stats->>'team_position' IS NOT NULL
                AND ally2.ally_stats->>'team_position' != ''
WHERE
  -- solo picks con rol conocido
  (  (g.game_type != 'SOLOQ' AND pl.role IS NOT NULL)
  OR (g.game_type  = 'SOLOQ'
      AND pk.stats->>'team_position' IS NOT NULL
      AND pk.stats->>'team_position' != ''))
  -- dedup GRID sin champ_id focal: mostrar solo lado BLUE (evita duplicar cada carril)
  AND (%(champ_id)s::int IS NOT NULL OR g.game_type = 'SOLOQ' OR pk.side = 'BLUE')
  -- 2v2: el Aliado 2 debe existir en la partida
  AND (%(champ_id_b)s::int IS NULL OR ally2.ally_pick_id IS NOT NULL)
  -- filtros
  AND (%(game_type)s::text  IS NULL OR g.game_type  = %(game_type)s)
  AND (%(patch)s::text      IS NULL OR g.version    = %(patch)s)
  AND (%(tournament)s::text IS NULL OR g.tournament = %(tournament)s)
  AND (%(champ_id)s::int    IS NULL OR pk.champ_id  = %(champ_id)s)
  AND (%(role)s::text       IS NULL OR ({_ROLE})     = %(role)s)
  -- rival 1 (champ_id2): en 1v1 = rival del focal; en 2v2 = miembro del dúo rival
  AND (%(champ_id2)s::int IS NULL
       OR (%(champ_id_b)s::int IS NULL
           AND (grid_op.opp_champ_id   = %(champ_id2)s
                OR soloq_op.opp_champ_id = %(champ_id2)s))
       OR (%(champ_id_b)s::int IS NOT NULL
           AND %(champ_id2)s IN (
                COALESCE(grid_op.opp_champ_id,   soloq_op.opp_champ_id),
                COALESCE(grid_op_b.opp_champ_id, soloq_op_b.opp_champ_id))))
  -- rival 2 (champ_id2_b): solo 2v2, miembro del dúo rival
  AND (%(champ_id2_b)s::int IS NULL
       OR %(champ_id2_b)s IN (
            COALESCE(grid_op.opp_champ_id,   soloq_op.opp_champ_id),
            COALESCE(grid_op_b.opp_champ_id, soloq_op_b.opp_champ_id)))
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


def _side(side, result, pick_order, pick_relation, player, champion, stats) -> dict:
    return {
        "side": side,
        "result": result,
        "pick_order": pick_order,
        "pick_relation": pick_relation,
        "player": player,
        "champion": champion,
        "stats": stats,
    }


def _grid_opponent(row: dict, p: str) -> dict | None:
    """Construye un rival GRID (OFFICIAL/SCRIM) desde columnas con prefijo `p`
    (`opp_` para Aliado 1, `b_opp_` para Aliado 2)."""
    if row.get(f"{p}pick_id") is None:
        return None
    return _side(
        side=row[f"{p}side"],
        result=row[f"{p}result"],
        pick_order=row[f"{p}pick_order"],
        pick_relation=None,
        player={"id": row[f"{p}player_id"], "name": row[f"{p}player_name"]},
        champion={"id": row[f"{p}champ_id"], "name": row[f"{p}champ_name"]},
        stats=row[f"{p}stats"],
    )


def _soloq_opponent(row: dict, p: str, game_result) -> dict | None:
    """Rival SoloQ (solo campeón) desde columnas con prefijo `p`
    (`soloq_opp_` / `b_soloq_opp_`)."""
    if row.get(f"{p}champ_id") is None:
        return None
    opp_side = row[f"{p}side"]
    opp_result = (game_result == opp_side) if opp_side else None
    return _side(
        side=opp_side,
        result=opp_result,
        pick_order=None,
        pick_relation=None,
        player=None,  # untrackeado — no hay fila en picks
        champion={"id": row[f"{p}champ_id"], "name": row[f"{p}champ_name"]},
        stats=None,
    )


def _shape(row: dict) -> dict:
    is_soloq = row["game_type"] == "SOLOQ"
    game_result = row["game_result"]

    pick_rel = None if is_soloq else _pick_relation(row["pick_order"], row.get("opp_pick_order"))
    focal = _side(
        side=row["pick_side"],
        result=row["pick_result"],
        pick_order=row["pick_order"],
        pick_relation=pick_rel,
        player={"id": row["player_id"], "name": row["player_name"]},
        champion={"id": row["champ_id"], "name": row["champ_name"]},
        stats=row["pick_stats"],
    )

    # rival de Aliado 1
    if is_soloq:
        opponent = _soloq_opponent(row, "soloq_opp_", game_result)
    else:
        opponent = _grid_opponent(row, "opp_")
        if opponent is not None:
            opponent["pick_relation"] = _pick_relation(row["opp_pick_order"], row["pick_order"])

    # Aliado 2 + su rival (solo 2v2)
    pick_ally = None
    opponent_ally = None
    if row.get("ally_pick_id") is not None:
        ally_rel = None if is_soloq else _pick_relation(row["ally_pick_order"], row.get("b_opp_pick_order"))
        pick_ally = _side(
            side=row["ally_side"],
            result=row["ally_result"],
            pick_order=row["ally_pick_order"],
            pick_relation=ally_rel,
            player={"id": row["ally_player_id"], "name": row["ally_player_name"]},
            champion={"id": row["ally_champ_id"], "name": row["ally_champ_name"]},
            stats=row["ally_stats"],
        )
        if is_soloq:
            opponent_ally = _soloq_opponent(row, "b_soloq_opp_", game_result)
        else:
            opponent_ally = _grid_opponent(row, "b_opp_")
            if opponent_ally is not None:
                opponent_ally["pick_relation"] = _pick_relation(row["b_opp_pick_order"], row["ally_pick_order"])

    return {
        "game_id": row["game_id"],
        "date": row["date"],
        "version": row["version"],
        "game_type": row["game_type"],
        "tournament": row["tournament"],
        "role": row["role"],
        "game_result": game_result,
        "team1": _team_obj(row["team1_id"], row["team1_name"], row["team1_tag"]),
        "team2": _team_obj(row["team2_id"], row["team2_name"], row["team2_tag"]),
        "pick": focal,
        "opponent": opponent,
        "pick_ally": pick_ally,
        "opponent_ally": opponent_ally,
    }


@router.get("/matchups")
def list_matchups(
    champ_id: int | None = None,
    champ_id2: int | None = None,
    champ_id_b: int | None = Query(None, description="2v2: segundo aliado (mismo lado)"),
    champ_id2_b: int | None = Query(None, description="2v2: segundo rival"),
    role: str | None = Query(None, description="TOP|JUNGLE|MID|ADC|SUPPORT (Aliado 1)"),
    role_b: str | None = Query(None, description="2v2: rol del Aliado 2"),
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
        "champ_id_b": champ_id_b,
        "champ_id2_b": champ_id2_b,
        "role": role,
        "role_b": role_b,
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
