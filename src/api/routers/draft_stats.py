"""Draft Stats — champion presence and pick-order statistics.

These share the same base filter as /drafts (team_id, rival_id, patch,
game_type, tournament, pick_phase) but without a champion filter or pagination:
they always return the full set of champions in the filtered drafts.
"""

from __future__ import annotations

from datetime import date

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import db_conn, get_champ_map

router = APIRouter(tags=["draft-stats"], prefix="/draft-stats")

# --- shared base filter -----------------------------------------------------

_BASE_FROM = """
FROM games g JOIN drafts d ON d.id = g.draft_id
WHERE g.draft_id IS NOT NULL
  -- only games with a winner; a NONE would count as a loss for every pick and
  -- bias the win_rate (and the presence denominator).
  AND g.result IN ('BLUE','RED')
  AND (%(team_id)s::int    IS NULL OR g.team1_id = %(team_id)s  OR g.team2_id = %(team_id)s)
  AND (%(rival_id)s::int   IS NULL OR g.team1_id = %(rival_id)s OR g.team2_id = %(rival_id)s)
  AND (%(patch)s::text     IS NULL OR g.version   = %(patch)s)
  AND (%(game_type)s::text  IS NULL OR g.game_type = %(game_type)s)
  AND (%(game_types)s::text[] IS NULL OR g.game_type = ANY(%(game_types)s))
  AND (%(tournament)s::text IS NULL OR g.tournament = %(tournament)s)
  AND (%(date_from)s::date  IS NULL OR g.date >= %(date_from)s)
  AND (%(pick_phase)s::text IS NULL OR
       (%(pick_phase)s = 'first'  AND d.first_pick_team_id =  %(team_id)s) OR
       (%(pick_phase)s = 'second' AND d.first_pick_team_id <> %(team_id)s))
"""

_BASE_CTE = """
SELECT g.id, g.result, g.team1_id, g.team2_id, d.first_pick_team_id,
       g.game_number, g.game_type, g.date,
       d.pick1,d.pick2,d.pick3,d.pick4,d.pick5,
       d.pick6,d.pick7,d.pick8,d.pick9,d.pick10,
       d.ban1,d.ban2,d.ban3,d.ban4,d.ban5,
       d.ban6,d.ban7,d.ban8,d.ban9,d.ban10
""" + _BASE_FROM

# --- champion presence -------------------------------------------------------

_PRESENCE_SQL = """
WITH base AS (""" + _BASE_CTE + """),
-- Effective game number:
--   - Scrims (each GRID series has a single game): the daily position against
--     the same rival is computed via ROW_NUMBER over (date, team pair, id).
--   - Official and others: the stored game_number (position in the Bo3/Bo5).
scrim_gn AS (
  SELECT id,
    ROW_NUMBER() OVER (
      PARTITION BY date,
                   LEAST(team1_id, team2_id),
                   GREATEST(team1_id, team2_id)
      ORDER BY id
    ) AS gn
  FROM base
  WHERE game_type = 'SCRIM'
),
effective_gn AS (
  SELECT b.id,
    COALESCE(s.gn, b.game_number::bigint) AS gn
  FROM base b
  LEFT JOIN scrim_gn s ON s.id = b.id
),
total AS (SELECT COUNT(*) AS n FROM base),
game_totals AS (
  SELECT
    COUNT(*) FILTER (WHERE gn = 1) AS g1,
    COUNT(*) FILTER (WHERE gn = 2) AS g2,
    COUNT(*) FILTER (WHERE gn = 3) AS g3,
    COUNT(*) FILTER (WHERE gn = 4) AS g4,
    COUNT(*) FILTER (WHERE gn = 5) AS g5
  FROM effective_gn
),
picks_raw AS (
  SELECT v.champ_id, v.is_fp, v.phase, e.gn AS game_number,
    CASE
      WHEN v.is_fp  AND g.first_pick_team_id = g.team1_id THEN (g.result = 'BLUE')
      WHEN v.is_fp  AND g.first_pick_team_id = g.team2_id THEN (g.result = 'RED')
      WHEN NOT v.is_fp AND g.first_pick_team_id = g.team1_id THEN (g.result = 'RED')
      WHEN NOT v.is_fp AND g.first_pick_team_id = g.team2_id THEN (g.result = 'BLUE')
      ELSE false
    END AS won,
    CASE
      WHEN %(team_id)s::int IS NULL THEN NULL
      WHEN     v.is_fp AND g.first_pick_team_id = %(team_id)s::int THEN 'by'
      WHEN NOT v.is_fp AND g.first_pick_team_id <> %(team_id)s::int THEN 'by'
      ELSE 'vs'
    END AS pick_side
  FROM base g
  JOIN effective_gn e ON e.id = g.id
  CROSS JOIN LATERAL (VALUES
    (g.pick1, true,  1),(g.pick2, true,  1),(g.pick3, true,  1),
    (g.pick4, true,  2),(g.pick5, true,  2),
    (g.pick6, false, 1),(g.pick7, false, 1),
    (g.pick8, false, 2),(g.pick9, false, 2),(g.pick10, false, 2)
  ) AS v(champ_id, is_fp, phase)
  WHERE v.champ_id IS NOT NULL
),
bans_raw AS (
  -- phase: ban1..5 = first-pick's bans (chronological), ban6..10 = second-pick.
  -- Phase 1 = each team's first 3 (slots 1,2,3 and 6,7,8); phase 2 = 4,5,9,10.
  SELECT v.champ_id, v.phase,
    CASE
      WHEN %(team_id)s::int IS NULL                                              THEN NULL
      WHEN     v.is_fp AND g.first_pick_team_id =  %(team_id)s::int             THEN 'by'
      WHEN NOT v.is_fp AND g.first_pick_team_id <> %(team_id)s::int             THEN 'by'
      ELSE 'vs'
    END AS ban_side
  FROM base g
  CROSS JOIN LATERAL (VALUES
    (g.ban1,  true, 1),(g.ban2,  true, 1),(g.ban3,  true, 1),(g.ban4,  true, 2),(g.ban5,  true, 2),
    (g.ban6, false, 1),(g.ban7, false, 1),(g.ban8, false, 1),(g.ban9, false, 2),(g.ban10, false, 2)
  ) AS v(champ_id, is_fp, phase)
  WHERE v.champ_id IS NOT NULL
),
pagg AS (
  SELECT champ_id,
    COUNT(*)                                                        AS picks,
    COUNT(*) FILTER (WHERE pick_side = 'by')                       AS picked_by,
    COUNT(*) FILTER (WHERE pick_side = 'vs')                       AS picked_vs,
    COUNT(*) FILTER (WHERE won)                                     AS wins,
    COUNT(*) FILTER (WHERE pick_side = 'by' AND won)               AS wins_by,
    COUNT(*) FILTER (WHERE pick_side = 'vs' AND won)               AS wins_vs,
    COUNT(*) FILTER (WHERE phase = 1)                              AS phase1,
    COUNT(*) FILTER (WHERE phase = 2)                              AS phase2,
    COUNT(*) FILTER (WHERE game_number = 1)                        AS g1,
    COUNT(*) FILTER (WHERE game_number = 1 AND won)                AS g1_wins,
    COUNT(*) FILTER (WHERE game_number = 1 AND pick_side = 'by')   AS g1_by,
    COUNT(*) FILTER (WHERE game_number = 1 AND pick_side = 'vs')   AS g1_vs,
    COUNT(*) FILTER (WHERE game_number = 2)                        AS g2,
    COUNT(*) FILTER (WHERE game_number = 2 AND won)                AS g2_wins,
    COUNT(*) FILTER (WHERE game_number = 2 AND pick_side = 'by')   AS g2_by,
    COUNT(*) FILTER (WHERE game_number = 2 AND pick_side = 'vs')   AS g2_vs,
    COUNT(*) FILTER (WHERE game_number = 3)                        AS g3,
    COUNT(*) FILTER (WHERE game_number = 3 AND won)                AS g3_wins,
    COUNT(*) FILTER (WHERE game_number = 3 AND pick_side = 'by')   AS g3_by,
    COUNT(*) FILTER (WHERE game_number = 3 AND pick_side = 'vs')   AS g3_vs,
    COUNT(*) FILTER (WHERE game_number = 4)                        AS g4,
    COUNT(*) FILTER (WHERE game_number = 4 AND won)                AS g4_wins,
    COUNT(*) FILTER (WHERE game_number = 4 AND pick_side = 'by')   AS g4_by,
    COUNT(*) FILTER (WHERE game_number = 4 AND pick_side = 'vs')   AS g4_vs,
    COUNT(*) FILTER (WHERE game_number = 5)                        AS g5,
    COUNT(*) FILTER (WHERE game_number = 5 AND won)                AS g5_wins,
    COUNT(*) FILTER (WHERE game_number = 5 AND pick_side = 'by')   AS g5_by,
    COUNT(*) FILTER (WHERE game_number = 5 AND pick_side = 'vs')   AS g5_vs
  FROM picks_raw GROUP BY champ_id
),
bagg AS (
  SELECT champ_id,
    COUNT(*)                                                  AS bans,
    COUNT(*) FILTER (WHERE ban_side = 'by')                   AS banned_by,
    COUNT(*) FILTER (WHERE ban_side = 'vs')                   AS banned_vs,
    COUNT(*) FILTER (WHERE ban_side = 'by' AND phase = 1)     AS banned_by_p1,
    COUNT(*) FILTER (WHERE ban_side = 'vs' AND phase = 1)     AS banned_vs_p1
  FROM bans_raw GROUP BY champ_id
)
SELECT
  COALESCE(p.champ_id, b.champ_id)                                              AS champ_id,
  COALESCE(p.picks, 0)                                                           AS picks,
  COALESCE(p.picked_by, 0)                                                       AS picked_by,
  COALESCE(p.picked_vs, 0)                                                       AS picked_vs,
  COALESCE(p.wins, 0)                                                             AS wins,
  COALESCE(p.wins_by, 0)                                                         AS wins_by,
  COALESCE(p.wins_vs, 0)                                                         AS wins_vs,
  COALESCE(p.phase1, 0)                                                           AS phase1,
  COALESCE(p.phase2, 0)                                                           AS phase2,
  COALESCE(b.bans, 0)                                                             AS bans,
  COALESCE(b.banned_by, 0)                                                       AS banned_by,
  COALESCE(b.banned_vs, 0)                                                       AS banned_vs,
  COALESCE(b.banned_by_p1, 0)                                                    AS banned_by_p1,
  COALESCE(b.banned_vs_p1, 0)                                                    AS banned_vs_p1,
  t.n                                                                             AS total_games,
  ROUND(100.0*(COALESCE(p.picks,0)+COALESCE(b.bans,0))/NULLIF(t.n,0), 1)       AS presence_pct,
  ROUND(100.0*COALESCE(p.picks,0)/NULLIF(t.n,0), 1)                             AS picked_pct,
  CASE WHEN COALESCE(p.picks,0) > 0
    THEN ROUND(100.0*p.wins/p.picks, 1) ELSE NULL END                           AS win_rate,
  COALESCE(p.g1, 0)       AS picks_g1,  COALESCE(p.g1_wins, 0)  AS wins_g1,
  COALESCE(p.g1_by, 0)    AS picks_g1_by, COALESCE(p.g1_vs, 0)  AS picks_g1_vs,
  COALESCE(p.g2, 0)       AS picks_g2,  COALESCE(p.g2_wins, 0)  AS wins_g2,
  COALESCE(p.g2_by, 0)    AS picks_g2_by, COALESCE(p.g2_vs, 0)  AS picks_g2_vs,
  COALESCE(p.g3, 0)       AS picks_g3,  COALESCE(p.g3_wins, 0)  AS wins_g3,
  COALESCE(p.g3_by, 0)    AS picks_g3_by, COALESCE(p.g3_vs, 0)  AS picks_g3_vs,
  COALESCE(p.g4, 0)       AS picks_g4,  COALESCE(p.g4_wins, 0)  AS wins_g4,
  COALESCE(p.g4_by, 0)    AS picks_g4_by, COALESCE(p.g4_vs, 0)  AS picks_g4_vs,
  COALESCE(p.g5, 0)       AS picks_g5,  COALESCE(p.g5_wins, 0)  AS wins_g5,
  COALESCE(p.g5_by, 0)    AS picks_g5_by, COALESCE(p.g5_vs, 0)  AS picks_g5_vs,
  gt.g1                   AS total_g1,
  gt.g2                   AS total_g2,
  gt.g3                   AS total_g3,
  gt.g4                   AS total_g4,
  gt.g5                   AS total_g5
FROM pagg p
FULL OUTER JOIN bagg b ON b.champ_id = p.champ_id
CROSS JOIN total t
CROSS JOIN game_totals gt
ORDER BY presence_pct DESC, picks DESC
"""

# --- pick order — slots ------------------------------------------------------

_SLOTS_SQL = """
WITH base AS (""" + _BASE_CTE + """),
total AS (SELECT COUNT(*) AS n FROM base),
slots AS (
  SELECT v.champ_id, v.slot, v.is_fp,
    CASE
      WHEN v.is_fp  AND g.first_pick_team_id = g.team1_id THEN (g.result = 'BLUE')
      WHEN v.is_fp  AND g.first_pick_team_id = g.team2_id THEN (g.result = 'RED')
      WHEN NOT v.is_fp AND g.first_pick_team_id = g.team1_id THEN (g.result = 'RED')
      WHEN NOT v.is_fp AND g.first_pick_team_id = g.team2_id THEN (g.result = 'BLUE')
      ELSE false
    END AS won
  FROM base g
  CROSS JOIN LATERAL (VALUES
    (g.pick1,  'b1',   true ),
    (g.pick2,  'b2_3', true ), (g.pick3,  'b2_3', true ),
    (g.pick4,  'b4_5', true ), (g.pick5,  'b4_5', true ),
    (g.pick6,  'r1_2', false), (g.pick7,  'r1_2', false),
    (g.pick8,  'r3',   false),
    (g.pick9,  'r4',   false),
    (g.pick10, 'r5',   false)
  ) AS v(champ_id, slot, is_fp)
  WHERE v.champ_id IS NOT NULL
    AND (%(team_id)s::int IS NULL
         OR v.is_fp = (g.first_pick_team_id = %(team_id)s::int))
)
SELECT champ_id, slot,
  COUNT(*) AS games,
  COUNT(*) FILTER (WHERE won) AS wins,
  ROUND(100.0 * COUNT(*) FILTER (WHERE won) / NULLIF(COUNT(*), 0), 1) AS win_rate,
  t.n AS total_games
FROM slots CROSS JOIN total t
GROUP BY champ_id, slot, t.n
ORDER BY slot, games DESC
"""

# --- pick order — distribution by role ---------------------------------------

_ROLE_SQL = """
WITH base_ids AS (
  SELECT g.id, g.team1_id, g.team2_id
  """ + _BASE_FROM + """
),
rp AS (
  SELECT pl.role,
    CASE p.pick_order
      WHEN 1  THEN 'b1'
      WHEN 4  THEN 'b2_3' WHEN 5  THEN 'b2_3'
      WHEN 8  THEN 'b4_5' WHEN 9  THEN 'b4_5'
      WHEN 2  THEN 'r1_2' WHEN 3  THEN 'r1_2'
      WHEN 6  THEN 'r3'
      WHEN 7  THEN 'r4'
      WHEN 10 THEN 'r5'
    END AS slot,
    CASE WHEN p.pick_order IN (1,4,5,8,9) THEN 'blue' ELSE 'red' END AS pick_side,
    p.result AS won
  FROM picks p
  JOIN base_ids g ON g.id = p.game_id
  JOIN players pl ON pl.id = p.player_id
  WHERE p.pick_order IS NOT NULL
    AND p.pick_order BETWEEN 1 AND 10
    AND pl.role IS NOT NULL
    AND (%(team_id)s::int IS NULL
         OR (g.team1_id = %(team_id)s::int AND p.side = 'BLUE')
         OR (g.team2_id = %(team_id)s::int AND p.side = 'RED'))
),
slot_totals AS (
  SELECT slot, pick_side, COUNT(*) AS tot FROM rp GROUP BY slot, pick_side
)
SELECT rp.role, rp.slot, rp.pick_side,
  COUNT(*) AS cnt,
  COUNT(*) FILTER (WHERE won) AS wins,
  ROUND(100.0 * COUNT(*) / NULLIF(st.tot, 0), 1) AS pct,
  ROUND(100.0 * COUNT(*) FILTER (WHERE won) / NULLIF(COUNT(*), 0), 1) AS win_rate
FROM rp
JOIN slot_totals st ON st.slot = rp.slot AND st.pick_side = rp.pick_side
GROUP BY rp.role, rp.slot, rp.pick_side, st.tot
ORDER BY rp.pick_side, rp.slot, rp.role
"""


def _base_params(
    team_id: int | None,
    rival_id: int | None,
    patch: str | None,
    pick_phase: str | None,
    game_type: str | None,
    tournament: str | None,
    game_types: list[str] | None = None,
    date_from: date | None = None,
) -> dict:
    return {
        "team_id": team_id,
        "rival_id": rival_id,
        "patch": patch,
        "pick_phase": pick_phase,
        "game_type": game_type,
        "game_types": game_types,
        "tournament": tournament,
        "date_from": date_from,
    }


def _parse_game_types(game_types: str | None) -> list[str] | None:
    """CSV 'OFFICIAL,SCRIM' -> ['OFFICIAL','SCRIM']. Empty/None -> None (no filter)."""
    if not game_types:
        return None
    parsed = [s for s in (p.strip() for p in game_types.split(",")) if s]
    return parsed or None


@router.get("/champion-presence")
def champion_presence(
    team_id: int | None = None,
    rival_id: int | None = None,
    patch: str | None = Query(None),
    pick_phase: str | None = Query(None, pattern="^(first|second)$"),
    game_type: str | None = Query(None),
    game_types: str | None = Query(None, description="CSV: OFFICIAL,SCRIM"),
    tournament: str | None = None,
    date_from: date | None = Query(None, description="Only games from this date"),
    conn: psycopg.Connection = Depends(db_conn),
    champ_map: dict[int, str] = Depends(get_champ_map),
):
    if pick_phase and team_id is None:
        raise HTTPException(400, "pick_phase requires team_id")

    params = _base_params(
        team_id, rival_id, patch, pick_phase, game_type, tournament,
        _parse_game_types(game_types), date_from=date_from,
    )
    with conn.cursor() as cur:
        cur.execute(_PRESENCE_SQL, params)
        rows = cur.fetchall()

    return [
        {
            "champ_id": r["champ_id"],
            "champ_name": champ_map.get(r["champ_id"]),
            "picks": r["picks"],
            "picked_by": r["picked_by"],
            "picked_vs": r["picked_vs"],
            "wins": r["wins"],
            "wins_by": r["wins_by"],
            "wins_vs": r["wins_vs"],
            "phase1": r["phase1"],
            "phase2": r["phase2"],
            "bans": r["bans"],
            "banned_by": r["banned_by"],
            "banned_vs": r["banned_vs"],
            "banned_by_p1": r["banned_by_p1"],
            "banned_vs_p1": r["banned_vs_p1"],
            "total_games": r["total_games"],
            "presence_pct": float(r["presence_pct"] or 0),
            "picked_pct": float(r["picked_pct"] or 0),
            "win_rate": float(r["win_rate"]) if r["win_rate"] is not None else None,
            "picks_g1": r["picks_g1"], "wins_g1": r["wins_g1"],
            "picks_g1_by": r["picks_g1_by"], "picks_g1_vs": r["picks_g1_vs"],
            "picks_g2": r["picks_g2"], "wins_g2": r["wins_g2"],
            "picks_g2_by": r["picks_g2_by"], "picks_g2_vs": r["picks_g2_vs"],
            "picks_g3": r["picks_g3"], "wins_g3": r["wins_g3"],
            "picks_g3_by": r["picks_g3_by"], "picks_g3_vs": r["picks_g3_vs"],
            "picks_g4": r["picks_g4"], "wins_g4": r["wins_g4"],
            "picks_g4_by": r["picks_g4_by"], "picks_g4_vs": r["picks_g4_vs"],
            "picks_g5": r["picks_g5"], "wins_g5": r["wins_g5"],
            "picks_g5_by": r["picks_g5_by"], "picks_g5_vs": r["picks_g5_vs"],
            "total_g1": r["total_g1"],
            "total_g2": r["total_g2"],
            "total_g3": r["total_g3"],
            "total_g4": r["total_g4"],
            "total_g5": r["total_g5"],
        }
        for r in rows
    ]


# --- role matchups (blind picks / counterpicks) -----------------------------

_ROLE_MATCHUP_BASE_CTE = """
WITH base_ids AS (
  SELECT g.id, g.team1_id, g.team2_id
  FROM games g JOIN drafts d ON d.id = g.draft_id
  WHERE g.draft_id IS NOT NULL
    AND g.result IN ('BLUE','RED')  -- exclude NONE from the win_rate
    AND (%(team_id)s::int    IS NULL OR g.team1_id = %(team_id)s  OR g.team2_id = %(team_id)s)
    AND (%(rival_id)s::int   IS NULL OR g.team1_id = %(rival_id)s OR g.team2_id = %(rival_id)s)
    AND (%(patch)s::text     IS NULL OR g.version   = %(patch)s)
    AND (%(game_type)s::text  IS NULL OR g.game_type = %(game_type)s)
    AND (%(game_types)s::text[] IS NULL OR g.game_type = ANY(%(game_types)s))
    AND (%(tournament)s::text IS NULL OR g.tournament = %(tournament)s)
    AND (%(date_from)s::date  IS NULL OR g.date >= %(date_from)s)
    AND (%(pick_phase)s::text IS NULL OR
         (%(pick_phase)s = 'first'  AND d.first_pick_team_id =  %(team_id)s) OR
         (%(pick_phase)s = 'second' AND d.first_pick_team_id <> %(team_id)s))
),
role_matchups AS (
  SELECT
    p1.champ_id AS blind_champ,
    p2.champ_id AS counter_champ,
    pl1.role,
    p1.result   AS blind_won,
    p2.result   AS counter_won
  FROM picks p1
  JOIN picks p2  ON p2.game_id = p1.game_id AND p2.side != p1.side
  JOIN base_ids g ON g.id = p1.game_id
  JOIN players pl1 ON pl1.id = p1.player_id
  JOIN players pl2 ON pl2.id = p2.player_id
  WHERE pl1.role = pl2.role
    AND p1.pick_order IS NOT NULL AND p1.pick_order BETWEEN 1 AND 10
    AND p2.pick_order IS NOT NULL AND p2.pick_order BETWEEN 1 AND 10
    AND pl1.role IS NOT NULL
    AND p1.pick_order < p2.pick_order
"""


def _build_role_picks_sql(pick_type: str) -> str:
    """SQL for /role-picks: groups by role and champion (blind or counter)."""
    our = "p1" if pick_type == "blind" else "p2"
    agg = "blind_champ" if pick_type == "blind" else "counter_champ"
    won = "blind_won" if pick_type == "blind" else "counter_won"
    return (
        _ROLE_MATCHUP_BASE_CTE
        + "    AND (%(team_id)s::int IS NULL\n"
        + "         OR (g.team1_id = %(team_id)s::int AND " + our + ".side = 'BLUE')\n"
        + "         OR (g.team2_id = %(team_id)s::int AND " + our + ".side = 'RED'))\n"
        + ")\n"
        + "SELECT role, " + agg + " AS champ_id,\n"
        + "  COUNT(*) AS games,\n"
        + "  COUNT(*) FILTER (WHERE " + won + ") AS wins\n"
        + "FROM role_matchups\n"
        + "GROUP BY role, " + agg + "\n"
        + "ORDER BY role, games DESC\n"
    )


def _build_role_matchup_sql(pick_type: str) -> str:
    """SQL for /role-pick-matchups: matchup detail for a specific champion."""
    our = "p1" if pick_type == "blind" else "p2"
    # blind: filter by the blind pick (p1) and show the counters (p2).
    # counter: filter by the counter (p2) and show the blinds (p1).
    filter_pick = "p1" if pick_type == "blind" else "p2"
    agg = "counter_champ" if pick_type == "blind" else "blind_champ"
    won = "blind_won" if pick_type == "blind" else "counter_won"
    return (
        _ROLE_MATCHUP_BASE_CTE
        + "    AND (%(team_id)s::int IS NULL\n"
        + "         OR (g.team1_id = %(team_id)s::int AND " + our + ".side = 'BLUE')\n"
        + "         OR (g.team2_id = %(team_id)s::int AND " + our + ".side = 'RED'))\n"
        + "    AND " + filter_pick + ".champ_id = %(champ_id)s::int\n"
        + "    AND pl1.role = %(role)s::text\n"
        + ")\n"
        + "SELECT " + agg + " AS champ_id,\n"
        + "  COUNT(*) AS games,\n"
        + "  COUNT(*) FILTER (WHERE " + won + ") AS wins\n"
        + "FROM role_matchups\n"
        + "GROUP BY " + agg + "\n"
        + "ORDER BY games DESC\n"
    )


@router.get("/role-picks")
def role_picks(
    pick_type: str = Query(..., alias="type", pattern="^(blind|counter)$"),
    team_id: int | None = None,
    rival_id: int | None = None,
    patch: str | None = Query(None),
    pick_phase: str | None = Query(None, pattern="^(first|second)$"),
    game_type: str | None = Query(None),
    game_types: str | None = Query(None, description="CSV: OFFICIAL,SCRIM"),
    tournament: str | None = None,
    date_from: date | None = Query(None, description="Only games from this date"),
    conn: psycopg.Connection = Depends(db_conn),
    champ_map: dict[int, str] = Depends(get_champ_map),
):
    if pick_phase and team_id is None:
        raise HTTPException(400, "pick_phase requires team_id")

    sql = _build_role_picks_sql(pick_type)
    params = _base_params(
        team_id, rival_id, patch, pick_phase, game_type, tournament,
        _parse_game_types(game_types), date_from=date_from,
    )
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    result: dict[str, list] = {}
    for r in rows:
        role = r["role"]
        entry = {
            "champ_id": r["champ_id"],
            "champ_name": champ_map.get(r["champ_id"]),
            "games": r["games"],
            "wins": r["wins"],
            "win_rate": round(100.0 * r["wins"] / r["games"], 1) if r["games"] else None,
        }
        result.setdefault(role, []).append(entry)
    return result


@router.get("/role-pick-matchups")
def role_pick_matchups(
    champ_id: int = Query(...),
    role: str = Query(...),
    pick_type: str = Query(..., alias="type", pattern="^(blind|counter)$"),
    team_id: int | None = None,
    rival_id: int | None = None,
    patch: str | None = Query(None),
    pick_phase: str | None = Query(None, pattern="^(first|second)$"),
    game_type: str | None = Query(None),
    game_types: str | None = Query(None, description="CSV: OFFICIAL,SCRIM"),
    tournament: str | None = None,
    date_from: date | None = Query(None, description="Only games from this date"),
    conn: psycopg.Connection = Depends(db_conn),
    champ_map: dict[int, str] = Depends(get_champ_map),
):
    if pick_phase and team_id is None:
        raise HTTPException(400, "pick_phase requires team_id")

    sql = _build_role_matchup_sql(pick_type)
    params = {
        **_base_params(
            team_id, rival_id, patch, pick_phase, game_type, tournament,
            _parse_game_types(game_types), date_from=date_from,
        ),
        "champ_id": champ_id,
        "role": role,
    }
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        {
            "champ_id": r["champ_id"],
            "champ_name": champ_map.get(r["champ_id"]),
            "games": r["games"],
            "wins": r["wins"],
            "win_rate": round(100.0 * r["wins"] / r["games"], 1) if r["games"] else None,
        }
        for r in rows
    ]


@router.get("/pick-order")
def pick_order(
    team_id: int | None = None,
    rival_id: int | None = None,
    patch: str | None = Query(None),
    pick_phase: str | None = Query(None, pattern="^(first|second)$"),
    game_type: str | None = Query(None),
    game_types: str | None = Query(None, description="CSV: OFFICIAL,SCRIM"),
    tournament: str | None = None,
    date_from: date | None = Query(None, description="Only games from this date"),
    conn: psycopg.Connection = Depends(db_conn),
    champ_map: dict[int, str] = Depends(get_champ_map),
):
    if pick_phase and team_id is None:
        raise HTTPException(400, "pick_phase requires team_id")

    params = _base_params(
        team_id, rival_id, patch, pick_phase, game_type, tournament,
        _parse_game_types(game_types), date_from=date_from,
    )
    with conn.cursor() as cur:
        cur.execute(_SLOTS_SQL, params)
        slot_rows = cur.fetchall()
        cur.execute(_ROLE_SQL, params)
        role_rows = cur.fetchall()

    slots = [
        {
            "champ_id": r["champ_id"],
            "champ_name": champ_map.get(r["champ_id"]),
            "slot": r["slot"],
            "games": r["games"],
            "wins": r["wins"],
            "win_rate": float(r["win_rate"]) if r["win_rate"] is not None else None,
            "total_games": r["total_games"],
        }
        for r in slot_rows
    ]
    role_dist = [
        {
            "role": r["role"],
            "slot": r["slot"],
            "pick_side": r["pick_side"],
            "cnt": r["cnt"],
            "wins": r["wins"],
            "pct": float(r["pct"] or 0),
            "win_rate": float(r["win_rate"]) if r["win_rate"] is not None else None,
        }
        for r in role_rows
    ]
    return {"slots": slots, "role_dist": role_dist}


# --- team matchups (most played) --------------------------------------------

# Shared CTE: the team's game ids + filters (multi-source). Unlike the rest of
# the module, this endpoint is always team-centric (team_id required).
_TEAM_MATCHUP_BASE = """
WITH base_ids AS (
  SELECT g.id, g.team1_id, g.team2_id
  FROM games g JOIN drafts d ON d.id = g.draft_id
  WHERE g.draft_id IS NOT NULL
    AND g.result IN ('BLUE','RED')  -- exclude NONE from the win_rate
    AND (g.team1_id = %(team_id)s OR g.team2_id = %(team_id)s)
    AND (%(game_types)s::text[] IS NULL OR g.game_type = ANY(%(game_types)s))
    AND (%(patch)s::text      IS NULL OR g.version    = %(patch)s)
    AND (%(tournament)s::text IS NULL OR g.tournament = %(tournament)s)
    AND (%(date_from)s::date  IS NULL OR g.date >= %(date_from)s)
)
"""

# One row per scouted team's pick, paired with the same-lane rival.
# LATERAL ... LIMIT 1 deduplicates scrims with duplicated roles (like
# matchups.py). "our" = the scouted team's side in each game.
# Also carries the lane snapshots (CS/gold @7 and @14, from picks.stats.midgame)
# of both sides to compute per-matchup lane diffs.
_TEAM_LANE_PAIRS_CTE = _TEAM_MATCHUP_BASE + """,
lane_pairs AS (
  SELECT pl.role AS role, our.champ_id AS our_champ,
         opp.opp_champ, our.result AS won,
         (our.stats->'midgame'->'7'->>'cs')::numeric     AS our_cs7,
         (our.stats->'midgame'->'7'->>'gold')::numeric   AS our_gold7,
         (our.stats->'midgame'->'14'->>'cs')::numeric    AS our_cs14,
         (our.stats->'midgame'->'14'->>'gold')::numeric  AS our_gold14,
         opp.opp_cs7, opp.opp_gold7, opp.opp_cs14, opp.opp_gold14
  FROM picks our
  JOIN base_ids g ON g.id = our.game_id
  JOIN players pl ON pl.id = our.player_id
  JOIN LATERAL (
    SELECT o.champ_id AS opp_champ,
           (o.stats->'midgame'->'7'->>'cs')::numeric     AS opp_cs7,
           (o.stats->'midgame'->'7'->>'gold')::numeric   AS opp_gold7,
           (o.stats->'midgame'->'14'->>'cs')::numeric    AS opp_cs14,
           (o.stats->'midgame'->'14'->>'gold')::numeric  AS opp_gold14
    FROM picks o JOIN players plo ON plo.id = o.player_id AND plo.role = pl.role
    WHERE o.game_id = our.game_id AND o.side <> our.side
    LIMIT 1
  ) opp ON true
  WHERE pl.role IS NOT NULL
    AND ((g.team1_id = %(team_id)s AND our.side = 'BLUE')
      OR (g.team2_id = %(team_id)s AND our.side = 'RED'))
)
"""

# Lane diffs: mean of (ours - rival) in CS/gold @7 and @14. AVG ignores NULLs,
# so it only averages games where both sides have the snapshot; diff_games_N
# exposes that sample size (may be < games if midgame was missing).
_TEAM_MATCHUP_SQL = _TEAM_LANE_PAIRS_CTE + """
SELECT role, our_champ, opp_champ,
  COUNT(*) AS games,
  COUNT(*) FILTER (WHERE won) AS wins,
  AVG(our_cs7    - opp_cs7)    AS cs_diff_7,
  AVG(our_gold7  - opp_gold7)  AS gold_diff_7,
  AVG(our_cs14   - opp_cs14)   AS cs_diff_14,
  AVG(our_gold14 - opp_gold14) AS gold_diff_14,
  COUNT(*) FILTER (WHERE our_cs7  IS NOT NULL AND opp_cs7  IS NOT NULL) AS diff_games_7,
  COUNT(*) FILTER (WHERE our_cs14 IS NOT NULL AND opp_cs14 IS NOT NULL) AS diff_games_14
FROM lane_pairs
GROUP BY role, our_champ, opp_champ
ORDER BY role, games DESC
"""

# Baseline by (role, champion): the team's WR with that champion IN THAT ROLE
# against ALL rivals (including the matchup's). Role-specific: a flexed champion
# has a different baseline per role. The frontend subtracts the specific row to
# get the "rest of the rivals" -> the delta excludes the matchup itself.
_TEAM_BASELINE_SQL = _TEAM_LANE_PAIRS_CTE + """
SELECT role, our_champ AS champ_id,
  COUNT(*) AS games,
  COUNT(*) FILTER (WHERE won) AS wins
FROM lane_pairs
GROUP BY role, our_champ
"""

@router.get("/team-matchups")
def team_matchups(
    team_id: int = Query(..., description="Team to scout (required)"),
    game_types: str | None = Query(None, description="CSV: OFFICIAL,SCRIM"),
    patch: str | None = Query(None),
    tournament: str | None = None,
    date_from: date | None = Query(None, description="Only games from this date"),
    conn: psycopg.Connection = Depends(db_conn),
    champ_map: dict[int, str] = Depends(get_champ_map),
):
    params = {
        "team_id": team_id,
        "game_types": _parse_game_types(game_types),
        "patch": patch,
        "tournament": tournament,
        "date_from": date_from,
    }
    with conn.cursor() as cur:
        cur.execute(_TEAM_MATCHUP_SQL, params)
        mu_rows = cur.fetchall()
        cur.execute(_TEAM_BASELINE_SQL, params)
        bl_rows = cur.fetchall()

    def _avg(v, nd: int = 1):
        return round(float(v), nd) if v is not None else None

    matchups: dict[str, list] = {}
    for r in mu_rows:
        matchups.setdefault(r["role"], []).append({
            "our_champ_id": r["our_champ"],
            "our_champ_name": champ_map.get(r["our_champ"]),
            "opp_champ_id": r["opp_champ"],
            "opp_champ_name": champ_map.get(r["opp_champ"]),
            "games": r["games"],
            "wins": r["wins"],
            "win_rate": round(100.0 * r["wins"] / r["games"], 1) if r["games"] else None,
            # lane diffs (mean ours - rival); gold rounded to integer
            "cs_diff_7":    _avg(r["cs_diff_7"]),
            "gold_diff_7":  _avg(r["gold_diff_7"], 0),
            "cs_diff_14":   _avg(r["cs_diff_14"]),
            "gold_diff_14": _avg(r["gold_diff_14"], 0),
            "diff_games_7":  r["diff_games_7"],
            "diff_games_14": r["diff_games_14"],
        })

    # baseline[role][champ_id] = the team's WR with that champion in that role
    # (all rivals). The frontend subtracts the matchup row to exclude it.
    baseline: dict[str, dict[int, dict]] = {}
    for r in bl_rows:
        baseline.setdefault(r["role"], {})[r["champ_id"]] = {
            "games": r["games"],
            "wins": r["wins"],
            "win_rate": round(100.0 * r["wins"] / r["games"], 1) if r["games"] else None,
        }
    return {"matchups": matchups, "baseline": baseline}


# lane-matchup: WR of ONE matchup as played by other teams (on-demand).
#
# A separate endpoint rather than another field in /team-matchups: computing
# this "vs other teams" for ALL of a team's matchups at once requires lane-
# pairing (LATERAL) every pick in the DB -> ~17s, unacceptable on page load. A
# single (role, our champ, rival) pair filters by champ_id (indexed) and
# resolves in ~4-12ms. The frontend requests it on-demand on hover over a
# specific matchup and React Query caches it per pair.
_LANE_MATCHUP_SQL = """
WITH all_ids AS (
  SELECT g.id, g.team1_id, g.team2_id
  FROM games g JOIN drafts d ON d.id = g.draft_id
  WHERE g.draft_id IS NOT NULL
    AND g.result IN ('BLUE','RED')
    AND (%(game_types)s::text[] IS NULL OR g.game_type = ANY(%(game_types)s))
    AND (%(patch)s::text      IS NULL OR g.version    = %(patch)s)
    AND (%(tournament)s::text IS NULL OR g.tournament = %(tournament)s)
    AND (%(date_from)s::date  IS NULL OR g.date >= %(date_from)s)
),
pairs AS (
  SELECT a.result AS won,
         CASE WHEN a.side = 'BLUE' THEN g.team1_id ELSE g.team2_id END AS team_id
  FROM picks a
  JOIN all_ids g ON g.id = a.game_id
  JOIN players pl ON pl.id = a.player_id AND pl.role = %(role)s
  JOIN LATERAL (
    SELECT 1
    FROM picks o JOIN players plo ON plo.id = o.player_id AND plo.role = pl.role
    WHERE o.game_id = a.game_id AND o.side <> a.side AND o.champ_id = %(opp)s
    LIMIT 1
  ) opp ON true
  WHERE a.champ_id = %(our)s
)
SELECT COUNT(*) AS games, COUNT(*) FILTER (WHERE won) AS wins
FROM pairs
WHERE team_id IS DISTINCT FROM %(team_id)s
"""


@router.get("/lane-matchup")
def lane_matchup(
    team_id: int = Query(..., description="Team to exclude from the sample (the scouted one)"),
    role: str = Query(..., description="TOP/JUNGLE/MID/ADC/SUPPORT"),
    our: int = Query(..., description="champ_id of the scouted side"),
    opp: int = Query(..., description="champ_id of the lane rival"),
    game_types: str | None = Query(None, description="CSV: OFFICIAL,SCRIM"),
    patch: str | None = Query(None),
    tournament: str | None = None,
    date_from: date | None = Query(None, description="Only games from this date"),
    conn: psycopg.Connection = Depends(db_conn),
):
    """WR of `our` vs `opp` in `role` as played by ALL teams except `team_id`.

    An "others playing it" reference: how this same matchup goes for the rest of
    the teams, to contrast with the team's own performance. Respects the context
    filters (game type, patch, tournament) active in the view.
    """
    params = {
        "team_id": team_id,
        "role": role,
        "our": our,
        "opp": opp,
        "game_types": _parse_game_types(game_types),
        "patch": patch,
        "tournament": tournament,
        "date_from": date_from,
    }
    with conn.cursor() as cur:
        cur.execute(_LANE_MATCHUP_SQL, params)
        r = cur.fetchone()

    games = r["games"] if r else 0
    wins = r["wins"] if r else 0
    return {
        "games": games,
        "wins": wins,
        "win_rate": round(100.0 * wins / games, 1) if games else None,
    }
