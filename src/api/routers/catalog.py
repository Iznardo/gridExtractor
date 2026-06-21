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


@router.get("/tournaments")
def list_tournaments(conn: psycopg.Connection = Depends(db_conn)):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT tournament FROM games "
            "WHERE tournament IS NOT NULL ORDER BY tournament"
        )
        return [r["tournament"] for r in cur.fetchall()]


@router.get("/patches")
def list_patches(conn: psycopg.Connection = Depends(db_conn)):
    # Orden semantico (major.minor) por numero, no lexicografico: si no, "16.9"
    # saldria por encima de "16.12". Solo versiones con formato N.N; el resto
    # (p. ej. 'Unknown', ya excluido) caeria fuera del split numerico.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT version FROM (
              SELECT DISTINCT version,
                     split_part(version, '.', 1)::int AS major,
                     split_part(version, '.', 2)::int AS minor
              FROM games
              WHERE version IS NOT NULL
                AND version <> 'Unknown'
                AND version ~ '^[0-9]+\\.[0-9]+$'
            ) v
            ORDER BY major DESC, minor DESC
            """
        )
        return [r["version"] for r in cur.fetchall()]


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
            WHERE (%(team_id)s::int  IS NULL OR team_id = %(team_id)s::int)
              AND (%(role)s::text    IS NULL OR role    = %(role)s::text)
            ORDER BY name
            """,
            {"team_id": team_id, "role": role},
        )
        return cur.fetchall()
