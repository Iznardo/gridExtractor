"""Scrims window — per-game enriched endpoint.

`GET /scrims/games` returns ONE row per scrim of the scouted team, with
everything the frontend needs to compute (with pure functions) the dashboard
blocks: pools come from /scouting; here go the latest block, duos, trios,
vs-teams and vs-picks.

Team-centric and only `game_type='SCRIM'` with `result IN ('BLUE','RED')` (NONE
does not count, consistent with the win-rate rule of the rest of the API).

A block = games against the same rival on one date; `block_game_number` numbers
the sequence within the block (game 1, 2, 3... vs that rival that day).
"""

from __future__ import annotations

from datetime import date

import psycopg
from fastapi import APIRouter, Depends, Query

from src.api.deps import db_conn

router = APIRouter(tags=["scrims"], prefix="/scrims")


# Pivot of our own lineup by role + flat list of rival picks, per game.
# Team-centric pattern shared with draft_stats.py (filter (team1&BLUE)|(team2&RED)).
_SQL = """
WITH base AS (
  SELECT
    g.id, g.date, g.game_number, g.version, g.result,
    d.first_pick_team_id,
    CASE WHEN g.team1_id = %(team_id)s THEN 'BLUE' ELSE 'RED' END AS our_side,
    CASE WHEN g.team1_id = %(team_id)s THEN g.team2_id ELSE g.team1_id END AS rival_id
  FROM games g
  LEFT JOIN drafts d ON d.id = g.draft_id
  WHERE g.game_type = 'SCRIM'
    AND g.result IN ('BLUE','RED')
    AND (g.team1_id = %(team_id)s OR g.team2_id = %(team_id)s)
    AND (%(date_from)s::date IS NULL OR g.date >= %(date_from)s)
    AND (%(patch)s::text     IS NULL OR g.version = %(patch)s)
),
numbered AS (
  SELECT b.*,
    ROW_NUMBER() OVER (
      PARTITION BY b.date, b.rival_id
      ORDER BY b.game_number NULLS LAST, b.id
    ) AS block_game_number
  FROM base b
),
our_lineup AS (
  -- p.role = role played in that game (picks.role), not the current roster
  -- role — rerolled/fill players land in the slot they actually played.
  SELECT n.id AS game_id,
    max(p.champ_id) FILTER (WHERE p.role = 'TOP')     AS top,
    max(p.champ_id) FILTER (WHERE p.role = 'JUNGLE')  AS jungle,
    max(p.champ_id) FILTER (WHERE p.role = 'MID')     AS mid,
    max(p.champ_id) FILTER (WHERE p.role = 'ADC')     AS adc,
    max(p.champ_id) FILTER (WHERE p.role = 'SUPPORT') AS support
  FROM numbered n
  JOIN picks   p  ON p.game_id = n.id AND p.side = n.our_side
  GROUP BY n.id
),
rival_picks AS (
  -- Ordered by ROLE played (TOP->SUPPORT) so the rival draft lines up with
  -- ours. Not pivoted to columns: that way we do not lose picks on sides with
  -- role=NULL (tripwired/incomplete); champ_id breaks ties for unknown roles.
  SELECT n.id AS game_id,
    array_agg(p.champ_id ORDER BY
      CASE p.role
        WHEN 'TOP' THEN 1 WHEN 'JUNGLE' THEN 2 WHEN 'MID' THEN 3
        WHEN 'ADC' THEN 4 WHEN 'SUPPORT' THEN 5 ELSE 9
      END,
      p.champ_id
    ) AS champs
  FROM numbered n
  JOIN picks   p  ON p.game_id = n.id AND p.side <> n.our_side
  GROUP BY n.id
)
SELECT
  n.id AS game_id, n.date, n.version,
  n.our_side, (n.result = n.our_side) AS won,
  (n.first_pick_team_id = %(team_id)s) AS first_pick,
  n.block_game_number,
  n.rival_id, t.name AS rival_name, t.tag AS rival_tag,
  ol.top, ol.jungle, ol.mid, ol.adc, ol.support,
  COALESCE(rp.champs, ARRAY[]::int[]) AS rival_champs
FROM numbered n
LEFT JOIN teams      t  ON t.id = n.rival_id
LEFT JOIN our_lineup ol ON ol.game_id = n.id
LEFT JOIN rival_picks rp ON rp.game_id = n.id
ORDER BY n.date DESC, n.block_game_number
"""


def _shape(row: dict) -> dict:
    return {
        "game_id": row["game_id"],
        "date": row["date"],
        "version": row["version"],
        "our_side": row["our_side"],
        "won": row["won"],
        "first_pick": row["first_pick"],
        "block_game_number": row["block_game_number"],
        "rival": {
            "id": row["rival_id"],
            "name": row["rival_name"],
            "tag": row["rival_tag"],
        } if row["rival_id"] is not None else None,
        "lineup": {
            "TOP": row["top"],
            "JUNGLE": row["jungle"],
            "MID": row["mid"],
            "ADC": row["adc"],
            "SUPPORT": row["support"],
        },
        "rival_champs": row["rival_champs"],
    }


@router.get("/games")
def scrim_games(
    team_id: int = Query(..., description="Team to track (required)"),
    date_from: date | None = Query(None, description="Only scrims from this date"),
    patch: str | None = Query(None, description="games.version, e.g. 14.23"),
    conn: psycopg.Connection = Depends(db_conn),
):
    params = {"team_id": team_id, "date_from": date_from, "patch": patch}
    with conn.cursor() as cur:
        cur.execute(_SQL, params)
        rows = cur.fetchall()
    return [_shape(r) for r in rows]
