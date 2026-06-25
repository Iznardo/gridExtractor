"""Reusable ensure_* helpers for the catalog tables (teams, players).

Hybrid-catalog rule:
- If grid_id already exists, return the local id without touching the row.
- If it does not, insert with the provided metadata and return the new id.
- Never update existing rows here. Positional reconciliation
  (team_id/role/starter/last_update) happens in the official extractor.

Shared by the bulk discovery and the per-game auto-discovery in the extractors.
"""

from __future__ import annotations

import psycopg


def ensure_team(
    conn: psycopg.Connection,
    grid_id: int,
    name: str,
    tag: str | None,
) -> tuple[int, bool]:
    """Return (local teams.id, is_new) for grid_id, creating the row if absent."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO teams (grid_id, name, tag)
            VALUES (%s, %s, %s)
            ON CONFLICT (grid_id) DO NOTHING
            RETURNING id
            """,
            (grid_id, name, tag),
        )
        row = cur.fetchone()
        if row is not None:
            return row[0], True
        # Row already existed; resolve its id by grid_id.
        cur.execute("SELECT id FROM teams WHERE grid_id = %s", (grid_id,))
        return cur.fetchone()[0], False


def ensure_player(
    conn: psycopg.Connection,
    grid_id: int,
    nickname: str,
    team_local_id: int | None,
    role: str | None = None,
) -> tuple[int, bool]:
    """Return (local players.id, is_new) for grid_id, creating the row if absent.

    On creation: starter=FALSE, last_update=NULL, role as given (already
    normalized) or NULL. Full positional reconciliation
    (team_id/starter/last_update) is done by the official extractor.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO players (grid_id, name, team_id, role)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (grid_id) DO NOTHING
            RETURNING id
            """,
            (grid_id, nickname, team_local_id, role),
        )
        row = cur.fetchone()
        if row is not None:
            return row[0], True
        cur.execute("SELECT id FROM players WHERE grid_id = %s", (grid_id,))
        return cur.fetchone()[0], False
