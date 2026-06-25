"""Positional roster reconciliation from official games.

Updates a player's team_id, role, starter and last_update from the evidence of
an official game.

Rules:
- Applied only when the game date is newer than players.last_update (protects
  chronological order across runs).
- Sets starter=TRUE for the player who played and starter=FALSE for the others
  in the resulting (team, role).
- Never touches cosmetic data (name, etc.).
- Must run inside the caller's transaction (per-game savepoint).
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
    """Reconcile one player from one official game.

    Args:
        player_local_id: local players.id.
        team_local_id:   local teams.id of the team the player played for.
        role_observed:   normalized role (TOP/JUNGLE/MID/ADC/SUPPORT).
        game_date:       game date.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_update FROM players WHERE id = %s",
            (player_local_id,),
        )
        row = cur.fetchone()
        if row is None:
            log.error("reconcile: player %d not found in DB.", player_local_id)
            return

        last_update = row[0]  # may be None (freshly created player)

        # Skip if this game predates the last reconciled one. Same-day games do
        # apply: the caller processes in global chronological order, so the last
        # game of the day wins correctly.
        if last_update is not None and game_date < last_update.date():
            return

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

        # Demote other current starters in the same (team, role). Only those
        # already starter=TRUE, so substitutes who never played there are left
        # untouched.
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
