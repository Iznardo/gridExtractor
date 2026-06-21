"""Ventana Scrims — endpoint enriquecido por partida.

`GET /scrims/games` devuelve UNA fila por scrim del equipo scouteado, con todo
lo necesario para que el front calcule (con funciones puras) los bloques del
dashboard: pools ya salen de /scouting; aquí van último bloque, duos, trios,
vs-equipos y vs-picks.

Team-céntrico y solo `game_type='SCRIM'` con `result IN ('BLUE','RED')` (las
NONE no cuentan, coherente con la regla de win-rate del resto de la API).

Bloque = games contra un mismo rival en una fecha; `block_game_number` numera la
secuencia dentro del bloque (game 1, 2, 3… vs ese rival ese día).
"""

from __future__ import annotations

from datetime import date

import psycopg
from fastapi import APIRouter, Depends, Query

from src.api.deps import db_conn

router = APIRouter(tags=["scrims"], prefix="/scrims")


# Pivot del lineup propio por rol + lista plana de picks rivales, por partida.
# Patrón team-céntrico copiado de draft_stats.py (filtro (team1&BLUE)|(team2&RED)).
_SQL = """
WITH base AS (
  SELECT
    g.id, g.date, g.game_number, g.version, g.result,
    d.first_pick_team_id,
    CASE WHEN g.team1_id = %(team_id)s THEN 'BLUE' ELSE 'RED' END AS our_side,
    CASE WHEN g.team1_id = %(team_id)s THEN g.team2_id ELSE g.team1_id END AS rival_id
  FROM games g
  JOIN drafts d ON d.id = g.draft_id
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
  SELECT n.id AS game_id,
    max(p.champ_id) FILTER (WHERE pl.role = 'TOP')     AS top,
    max(p.champ_id) FILTER (WHERE pl.role = 'JUNGLE')  AS jungle,
    max(p.champ_id) FILTER (WHERE pl.role = 'MID')     AS mid,
    max(p.champ_id) FILTER (WHERE pl.role = 'ADC')     AS adc,
    max(p.champ_id) FILTER (WHERE pl.role = 'SUPPORT') AS support
  FROM numbered n
  JOIN picks   p  ON p.game_id = n.id AND p.side = n.our_side
  JOIN players pl ON pl.id = p.player_id
  GROUP BY n.id
),
rival_picks AS (
  -- Ordenados por ROL (TOP→SUPPORT) para que el draft rival se vea alineado con
  -- el nuestro. No se pivota a columnas: así no perdemos picks si en scrims hay
  -- roles duplicados/sucios; champ_id desempata roles desconocidos.
  SELECT n.id AS game_id,
    array_agg(p.champ_id ORDER BY
      CASE pl.role
        WHEN 'TOP' THEN 1 WHEN 'JUNGLE' THEN 2 WHEN 'MID' THEN 3
        WHEN 'ADC' THEN 4 WHEN 'SUPPORT' THEN 5 ELSE 9
      END,
      p.champ_id
    ) AS champs
  FROM numbered n
  JOIN picks   p  ON p.game_id = n.id AND p.side <> n.our_side
  JOIN players pl ON pl.id = p.player_id
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
    team_id: int = Query(..., description="Equipo a trackear (obligatorio)"),
    date_from: date | None = Query(None, description="Solo scrims desde esta fecha"),
    patch: str | None = Query(None, description="games.version, ej. 14.23"),
    conn: psycopg.Connection = Depends(db_conn),
):
    params = {"team_id": team_id, "date_from": date_from, "patch": patch}
    with conn.cursor() as cur:
        cur.execute(_SQL, params)
        rows = cur.fetchall()
    return [_shape(r) for r in rows]
