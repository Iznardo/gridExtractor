"""Reconciliacion posicional de jugadores desde partidas oficiales.

Implementa CLAUDE.md §5.5: actualiza team_id, role, starter y last_update
de un jugador a partir de la evidencia de una partida oficial.

Reglas:
- Solo se aplica si la fecha de la partida es POSTERIOR a players.last_update
  (proteccion de orden cronologico entre corridas).
- Marca starter=TRUE al jugador que jugo, starter=FALSE a los demas en el
  mismo (equipo, rol) resultante.
- Nunca toca datos cosmeticos (name, etc.).
- Debe llamarse dentro de la transaccion del caller (savepoint por partida).
"""

from __future__ import annotations

import logging
from datetime import date

import psycopg

log = logging.getLogger(__name__)


def reconcile_player_roster(
    conn: psycopg.Connection,
    *,
    player_local_id: int,
    team_local_id: int,
    role_observed: str,
    game_date: date,
) -> None:
    """Aplica CLAUDE.md §5.5 para UN jugador en UNA partida oficial.

    Parametros:
        player_local_id: players.id local del jugador.
        team_local_id:   teams.id local del equipo en que jugo.
        role_observed:   rol normalizado (TOP/JUNGLE/MID/ADC/SUPPORT).
        game_date:       fecha de la partida (DATE).
    """
    with conn.cursor() as cur:
        # 1. Leer estado actual del jugador.
        cur.execute(
            "SELECT last_update FROM players WHERE id = %s",
            (player_local_id,),
        )
        row = cur.fetchone()
        if row is None:
            log.error("reconcile: jugador %d no existe en BD.", player_local_id)
            return

        last_update = row[0]  # puede ser None (jugador recien creado)

        # 2. Proteccion de orden cronologico: no reconciliar si la partida
        #    es anterior o igual a la ultima ya reconciliada.
        if last_update is not None and game_date <= last_update.date():
            return

        # 3. Actualizar campos posicionales del jugador.
        cur.execute(
            """
            UPDATE players
               SET team_id     = %s,
                   role        = %s,
                   starter     = TRUE,
                   last_update = %s
             WHERE id = %s
            """,
            (team_local_id, role_observed, game_date, player_local_id),
        )

        # 4. Marcar starter=FALSE para otros jugadores en el mismo (equipo, rol).
        #    Solo los que actualmente son starter=TRUE para no tocar suplentes
        #    que nunca han jugado en esa posicion.
        cur.execute(
            """
            UPDATE players
               SET starter = FALSE
             WHERE team_id = %s
               AND role    = %s
               AND id     <> %s
               AND starter = TRUE
            """,
            (team_local_id, role_observed, player_local_id),
        )
