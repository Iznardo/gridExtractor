"""Helpers `ensure_*` reutilizables para mantener el catalogo (teams, players).

Regla del modelo hibrido (CLAUDE.md §5.2, DISCOVERY_PLAN.md §5):
- Si el grid_id ya existe en BD: devolver el id local sin tocar la fila.
- Si no existe: insertar con los metadatos recibidos y devolver el id nuevo.
- NUNCA actualizar filas existentes desde aqui. La reconciliacion posicional
  (team_id/role/starter/last_update) ocurre en el extractor de oficiales,
  no aqui (CLAUDE.md §5.5).

Compartido por el discovery (poblado en bloque) y por el futuro
auto-discovery por partida (creacion al vuelo desde el extractor).
"""

from __future__ import annotations

import psycopg


def ensure_team(
    conn: psycopg.Connection,
    grid_id: int,
    name: str,
    tag: str | None,
) -> tuple[int, bool]:
    """Devuelve (teams.id local, is_new) para `grid_id`, creando la fila si no existe."""
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
        # Conflict silencioso: ya existia. Resolver el id por grid_id.
        cur.execute("SELECT id FROM teams WHERE grid_id = %s", (grid_id,))
        return cur.fetchone()[0], False


def ensure_player(
    conn: psycopg.Connection,
    grid_id: int,
    nickname: str,
    team_local_id: int | None,
    role: str | None = None,
) -> tuple[int, bool]:
    """Devuelve (players.id local, is_new) para `grid_id`, creando la fila si no existe.

    Al crear: starter=FALSE, last_update=NULL, role=lo que pase el caller
    (ya normalizado) o NULL. La reconciliacion posicional completa
    (team_id/starter/last_update) la hace el extractor de oficiales
    (CLAUDE.md §5.5).
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
