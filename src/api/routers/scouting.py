"""Ventana 2 — Team scouting.

Devuelve, para un equipo, qué campeones ha jugado cada jugador, **separado por
medio** (OFFICIAL / SCRIM / SOLOQ) en `by_medium` → cada medio desglosado por
jugador. El agregado "todos los medios" (tambien por jugador) lo deriva el
consumidor de `by_medium`, asi que no se devuelve por separado.

Atribucion via `players.team_id` (roster actual): es la unica via comun a los
3 medios (soloq no tiene team1/team2) y la semantica deseada — la pool del
roster que se scoutea.

Se ampliara en el futuro (winrate por matchup, rango de parches, etc.).
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

# Orden de roster habitual; roles NULL/desconocidos van al final.
_ROLE_ORDER = {"TOP": 0, "JUNGLE": 1, "MID": 2, "ADC": 3, "SUPPORT": 4}
_MEDIUMS = {"OFFICIAL": "official", "SCRIM": "scrim", "SOLOQ": "soloq"}


@router.get("/scouting/champion-pool")
def champion_pool(
    team_id: int = Query(..., description="Equipo a scoutear (obligatorio)"),
    date_from: date | None = Query(None, description="Solo partidas desde esta fecha"),
    patch: str | None = Query(None, description="games.version, ej. 14.23"),
    conn: psycopg.Connection = Depends(db_conn),
):
    with conn.cursor() as cur:
        cur.execute(_SQL, {"team_id": team_id, "date_from": date_from, "patch": patch})
        rows = cur.fetchall()

    # by_medium[medio][player_id] = {player, champions: {champ_id: {...}}}
    by_medium: dict[str, dict[int, dict]] = {"official": {}, "scrim": {}, "soloq": {}}

    for r in rows:
        medium = _MEDIUMS.get(r["game_type"])
        if medium is None:
            continue
        games = int(r["games"])
        wins = int(r["wins"] or 0)

        # --- desglose por jugador dentro del medio ---
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
