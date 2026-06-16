"""Endpoints de catalogo: pueblan los desplegables/filtros del front.

El front resuelve nombre->id contra estos endpoints (ej. autocompletar
"Aatrox" y enviar champ_id); la API de consulta se mantiene id-based.
"""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends

from src.api.deps import db_conn

router = APIRouter(tags=["catalog"])


@router.get("/champions")
def list_champions(conn: psycopg.Connection = Depends(db_conn)):
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, alias FROM champions ORDER BY name")
        return cur.fetchall()


@router.get("/teams")
def list_teams(conn: psycopg.Connection = Depends(db_conn)):
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, tag FROM teams ORDER BY name")
        return cur.fetchall()


@router.get("/players")
def list_players(
    team_id: int | None = None,
    role: str | None = None,
    conn: psycopg.Connection = Depends(db_conn),
):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, role, team_id, starter
            FROM players
            WHERE (%(team_id)s IS NULL OR team_id = %(team_id)s)
              AND (%(role)s    IS NULL OR role    = %(role)s)
            ORDER BY name
            """,
            {"team_id": team_id, "role": role},
        )
        return cur.fetchall()
