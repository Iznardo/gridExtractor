"""Team scouting window.

For a team, returns which champions each player has played, split by medium
(OFFICIAL / SCRIM / SOLOQ) in `by_medium` -> each medium broken down by player.
The "all mediums" aggregate (also per player) is derived by the consumer of
`by_medium`, so it is not returned separately.

Attribution via `players.team_id` (current roster): the only path common to the
3 mediums (soloq has no team1/team2) and the intended semantics — the pool of
the roster being scouted.
"""

from __future__ import annotations

from datetime import date

import psycopg
from fastapi import APIRouter, Depends, Query

from src.api.deps import db_conn

router = APIRouter(tags=["scouting"])


_SQL = """
SELECT pl.id AS player_id, pl.name AS player_name, pl.role,
       c.id AS champ_id, c.name AS champ_name, g.game_type,
       count(*) AS games,
       sum(CASE WHEN pk.result THEN 1 ELSE 0 END) AS wins
FROM picks pk
JOIN players pl  ON pl.id = pk.player_id
JOIN games g     ON g.id  = pk.game_id
JOIN champions c ON c.id  = pk.champ_id
WHERE pl.team_id = %(team_id)s
  AND (%(date_from)s::date IS NULL OR g.date >= %(date_from)s)
  AND (%(patch)s::text     IS NULL OR g.version = %(patch)s)
GROUP BY pl.id, pl.name, pl.role, c.id, c.name, g.game_type
"""

# Usual roster order; NULL/unknown roles go last.
_ROLE_ORDER = {"TOP": 0, "JUNGLE": 1, "MID": 2, "ADC": 3, "SUPPORT": 4}
_MEDIUMS = {"OFFICIAL": "official", "SCRIM": "scrim", "SOLOQ": "soloq"}


@router.get("/scouting/champion-pool")
def champion_pool(
    team_id: int = Query(..., description="Team to scout (required)"),
    date_from: date | None = Query(None, description="Only games from this date"),
    patch: str | None = Query(None, description="games.version, e.g. 14.23"),
    conn: psycopg.Connection = Depends(db_conn),
):
    with conn.cursor() as cur:
        cur.execute(_SQL, {"team_id": team_id, "date_from": date_from, "patch": patch})
        rows = cur.fetchall()

    # by_medium[medium][player_id] = {player, champions: {champ_id: {...}}}
    by_medium: dict[str, dict[int, dict]] = {"official": {}, "scrim": {}, "soloq": {}}

    for r in rows:
        medium = _MEDIUMS.get(r["game_type"])
        if medium is None:
            continue
        games = int(r["games"])
        wins = int(r["wins"] or 0)

        # --- per-player breakdown within the medium ---
        bucket = by_medium[medium]
        player = bucket.setdefault(r["player_id"], {
            "player": {
                "id": r["player_id"],
                "name": r["player_name"],
                "role": r["role"],
            },
            "champions": [],
        })
        player["champions"].append({
            "champion": {"id": r["champ_id"], "name": r["champ_name"]},
            "games": games,
            "wins": wins,
        })

    def _players_sorted(bucket: dict[int, dict]) -> list[dict]:
        rows_out = list(bucket.values())
        for p in rows_out:
            p["champions"].sort(key=lambda ch: (-ch["games"], ch["champion"]["name"]))
        rows_out.sort(key=lambda p: (
            _ROLE_ORDER.get(p["player"]["role"], 99),
            p["player"]["name"],
        ))
        return rows_out

    return {
        "team_id": team_id,
        "by_medium": {
            "official": _players_sorted(by_medium["official"]),
            "scrim":    _players_sorted(by_medium["scrim"]),
            "soloq":    _players_sorted(by_medium["soloq"]),
        },
    }


# --- player-shares: gold% and damage% per role (dashboard radar) -------------
#
# Per team game (our side), each player's share = their value / team total that
# game; then AVG per role. Mean of ratios (not ratio of means): every game
# weighs equally. Only OFFICIAL/SCRIM have full per-player stats; soloq is left
# out (no full team tracked).
_SHARES_SQL = """
WITH team_games AS (
  SELECT g.id,
    CASE WHEN g.team1_id = %(team_id)s THEN 'BLUE' ELSE 'RED' END AS our_side
  FROM games g
  WHERE g.result IN ('BLUE','RED')
    AND (g.team1_id = %(team_id)s OR g.team2_id = %(team_id)s)
    AND (%(game_types)s::text[] IS NULL OR g.game_type = ANY(%(game_types)s))
    AND (%(patch)s::text     IS NULL OR g.version = %(patch)s)
    AND (%(date_from)s::date  IS NULL OR g.date   >= %(date_from)s)
),
our_picks AS (
  SELECT tg.id AS game_id, pl.role,
    pl.name AS player_name,
    (pk.stats->>'gold')::numeric         AS gold,
    (pk.stats->>'damage_dealt')::numeric AS dmg
  FROM team_games tg
  JOIN picks   pk ON pk.game_id = tg.id AND pk.side = tg.our_side
  JOIN players pl ON pl.id = pk.player_id
  WHERE pk.stats ? 'gold' AND pk.stats ? 'damage_dealt'
    AND pl.role IS NOT NULL
),
per_game AS (
  SELECT game_id, SUM(gold) AS tg, SUM(dmg) AS td
  FROM our_picks GROUP BY game_id
)
SELECT op.role,
  COUNT(*) AS games,
  mode() WITHIN GROUP (ORDER BY op.player_name) AS player_name,
  AVG(100.0 * op.gold / NULLIF(pg.tg, 0)) AS gold_pct,
  AVG(100.0 * op.dmg / NULLIF(pg.td, 0)) AS dmg_pct
FROM our_picks op
JOIN per_game pg ON pg.game_id = op.game_id
GROUP BY op.role
"""


@router.get("/scouting/player-shares")
def player_shares(
    team_id: int = Query(..., description="Team to scout (required)"),
    game_types: str | None = Query(None, description="CSV: OFFICIAL,SCRIM"),
    patch: str | None = Query(None, description="games.version, e.g. 14.23"),
    date_from: date | None = Query(None, description="Only games from this date"),
    conn: psycopg.Connection = Depends(db_conn),
):
    gts = [s for s in (p.strip() for p in (game_types or "").split(",")) if s] or None
    params = {"team_id": team_id, "game_types": gts, "patch": patch, "date_from": date_from}
    with conn.cursor() as cur:
        cur.execute(_SHARES_SQL, params)
        rows = cur.fetchall()

    by_role = {
        r["role"]: {
            "role": r["role"],
            "player": r["player_name"],
            "games": r["games"],
            "gold_pct": round(float(r["gold_pct"]), 1) if r["gold_pct"] is not None else None,
            "dmg_pct": round(float(r["dmg_pct"]), 1) if r["dmg_pct"] is not None else None,
        }
        for r in rows
    }
    # Fixed roster order TOP->SUPPORT; roles without data are omitted.
    return [by_role[r] for r in ("TOP", "JUNGLE", "MID", "ADC", "SUPPORT") if r in by_role]
