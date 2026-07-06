"""Picks / Matchups window (1v1 and 2v2).

1v1: one row per focal pick, with the lane opponent's pick as an optional field.
2v2: besides the focal pick (Ally 1), a second ally on the same side (Ally 2) and
     the two rivals derived by role from the opposing side. Activated when
     `champ_id_b` is provided.

Lane source: picks.role — the role played IN THAT GAME (riot_id ordering
convention for OFFICIAL/SCRIM, team_position for SOLOQ; normalized at insert
time). Never players.role, which is the *current* roster role and would
misattribute historical games after a reroll.

blind/counter: OFFICIAL/SCRIM only (derived from pick_order relative to the
rival), 1v1 only.
Games with no lane opponent are returned with opponent=null.
"""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, Query

from src.api.deps import db_conn
from src.api.pagination import Pagination, pagination

router = APIRouter(tags=["matchups"])


_SQL = """
SELECT
  g.id         AS game_id,
  g.date,
  g.version,
  g.game_type,
  g.tournament,
  g.result     AS game_result,
  g.team1_id,  t1.name AS team1_name,  t1.tag AS team1_tag,
  g.team2_id,  t2.name AS team2_name,  t2.tag AS team2_tag,
  -- focal pick (Ally 1)
  pk.id          AS pick_id,
  pk.side        AS pick_side,
  pk.result      AS pick_result,
  pk.pick_order,
  pk.stats       AS pick_stats,
  pl.id          AS player_id,
  pl.name        AS player_name,
  c.id           AS champ_id,
  c.name         AS champ_name,
  pk.role,
  -- GRID opponent of Ally 1 (OFFICIAL/SCRIM) via LATERAL
  grid_op.opp_pick_id,
  grid_op.opp_side,
  grid_op.opp_result,
  grid_op.opp_pick_order,
  grid_op.opp_stats,
  grid_op.opp_player_id,
  grid_op.opp_player_name,
  grid_op.opp_champ_id,
  grid_op.opp_champ_name,
  -- SoloQ opponent of Ally 1 (champion only, from games.stats.participants)
  soloq_op.opp_champ_id    AS soloq_opp_champ_id,
  soloq_op.opp_side        AS soloq_opp_side,
  soloq_op.opp_champ_name  AS soloq_opp_champ_name,
  -- Ally 2 (2v2 only)
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
  -- GRID opponent of Ally 2
  grid_op_b.opp_pick_id      AS b_opp_pick_id,
  grid_op_b.opp_side         AS b_opp_side,
  grid_op_b.opp_result       AS b_opp_result,
  grid_op_b.opp_pick_order   AS b_opp_pick_order,
  grid_op_b.opp_stats        AS b_opp_stats,
  grid_op_b.opp_player_id    AS b_opp_player_id,
  grid_op_b.opp_player_name  AS b_opp_player_name,
  grid_op_b.opp_champ_id     AS b_opp_champ_id,
  grid_op_b.opp_champ_name   AS b_opp_champ_name,
  -- SoloQ opponent of Ally 2
  soloq_op_b.opp_champ_id    AS b_soloq_opp_champ_id,
  soloq_op_b.opp_side        AS b_soloq_opp_side,
  soloq_op_b.opp_champ_name  AS b_soloq_opp_champ_name
FROM picks pk
JOIN games   g   ON g.id  = pk.game_id
JOIN players pl  ON pl.id = pk.player_id
JOIN champions c ON c.id  = pk.champ_id
LEFT JOIN teams t1 ON t1.id = g.team1_id
LEFT JOIN teams t2 ON t2.id = g.team2_id
-- GRID opponent of Ally 1: same game_id, opposite side, same role (LIMIT 1 — dirty scrim data)
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
  JOIN players   opp_pl ON opp_pl.id = op.player_id
  JOIN champions opp_c  ON opp_c.id  = op.champ_id
  WHERE op.game_id = pk.game_id
    AND op.side   != pk.side
    AND op.role    = pk.role
  LIMIT 1
) grid_op ON g.game_type != 'SOLOQ' AND pk.role IS NOT NULL
-- SoloQ opponent of Ally 1: same lane (team_position), opposite side, from participants
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
-- Ally 2 (2v2 only): same game_id, same side, different pick, champion = champ_id_b
LEFT JOIN LATERAL (
  SELECT
    ally.id          AS ally_pick_id,
    ally.side        AS ally_side,
    ally.result      AS ally_result,
    ally.pick_order  AS ally_pick_order,
    ally.stats       AS ally_stats,
    ally_pl.id       AS ally_player_id,
    ally_pl.name     AS ally_player_name,
    ally_c.id        AS ally_champ_id,
    ally_c.name      AS ally_champ_name,
    ally.role        AS ally_role
  FROM picks ally
  JOIN players   ally_pl ON ally_pl.id = ally.player_id
  JOIN champions ally_c  ON ally_c.id  = ally.champ_id
  WHERE ally.game_id = pk.game_id
    AND ally.side    = pk.side
    AND ally.id     != pk.id
    AND ally.champ_id = %(champ_id_b)s
    AND (%(role_b)s::text IS NULL OR ally.role = %(role_b)s)
  LIMIT 1
) ally2 ON %(champ_id_b)s::int IS NOT NULL
-- GRID opponent of Ally 2: opposite side, same role as Ally 2
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
  JOIN players   opp_pl ON opp_pl.id = op.player_id
  JOIN champions opp_c  ON opp_c.id  = op.champ_id
  WHERE op.game_id = pk.game_id
    AND op.side   != pk.side
    AND op.role    = ally2.ally_role
  LIMIT 1
) grid_op_b ON g.game_type != 'SOLOQ' AND ally2.ally_role IS NOT NULL
-- SoloQ opponent of Ally 2: same lane as Ally 2, opposite side, from participants
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
  -- picks with a known role only
  pk.role IS NOT NULL
  -- GRID dedup without a focal champ_id: show BLUE side only (avoids duplicating each lane)
  AND (%(champ_id)s::int IS NOT NULL OR g.game_type = 'SOLOQ' OR pk.side = 'BLUE')
  -- 2v2: Ally 2 must exist in the game
  AND (%(champ_id_b)s::int IS NULL OR ally2.ally_pick_id IS NOT NULL)
  -- filters
  AND (%(game_type)s::text  IS NULL OR g.game_type  = %(game_type)s)
  AND (%(patch)s::text      IS NULL OR g.version    = %(patch)s)
  AND (%(tournament)s::text IS NULL OR g.tournament = %(tournament)s)
  AND (%(champ_id)s::int    IS NULL OR pk.champ_id  = %(champ_id)s)
  AND (%(role)s::text       IS NULL OR pk.role      = %(role)s)
  -- rival 1 (champ_id2): in 1v1 = focal's opponent; in 2v2 = member of the rival duo
  AND (%(champ_id2)s::int IS NULL
       OR (%(champ_id_b)s::int IS NULL
           AND (grid_op.opp_champ_id   = %(champ_id2)s
                OR soloq_op.opp_champ_id = %(champ_id2)s))
       OR (%(champ_id_b)s::int IS NOT NULL
           AND %(champ_id2)s IN (
                COALESCE(grid_op.opp_champ_id,   soloq_op.opp_champ_id),
                COALESCE(grid_op_b.opp_champ_id, soloq_op_b.opp_champ_id))))
  -- rival 2 (champ_id2_b): 2v2 only, member of the rival duo
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
    """Build a GRID opponent (OFFICIAL/SCRIM) from columns prefixed `p`
    (`opp_` for Ally 1, `b_opp_` for Ally 2)."""
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
    """SoloQ opponent (champion only) from columns prefixed `p`
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
        player=None,  # untracked — no row in picks
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

    # Ally 1's opponent
    if is_soloq:
        opponent = _soloq_opponent(row, "soloq_opp_", game_result)
    else:
        opponent = _grid_opponent(row, "opp_")
        if opponent is not None:
            opponent["pick_relation"] = _pick_relation(row["opp_pick_order"], row["pick_order"])

    # Ally 2 + its opponent (2v2 only)
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
    champ_id_b: int | None = Query(None, description="2v2: second ally (same side)"),
    champ_id2_b: int | None = Query(None, description="2v2: second rival"),
    role: str | None = Query(None, description="TOP|JUNGLE|MID|ADC|SUPPORT (Ally 1)"),
    role_b: str | None = Query(None, description="2v2: Ally 2's role"),
    tournament: str | None = None,
    patch: str | None = Query(None, description="games.version, e.g. 14.23"),
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
