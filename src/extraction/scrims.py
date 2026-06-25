"""Extraction of scrims from GRID.

Flow:

  allSeries (SCRIM, ASC order, no tournament filter) paginated
       │  skip series already complete in DB
       ▼
  get_grid_events(series_id)  -> raw events
  split_grid_series()          -> one list per game
       │
       ▼  per game
  GameEventProcessor + observers (teams, draft, stats, objs, wards)
       │
       ▼
  auto-discovery (ensure_team, ensure_player) with WARNING when is_new
  INSERT drafts / games / picks  (game_type='SCRIM', tournament='SCRIM')

The per-game/series processing is shared with official games and lives in
`_persistence.py` (run_series + process_one_game). Scrim differences are
expressed through GameProcessingConfig:
- No tournament filter: downloads every PUBLISHED scrim on the account.
- warn_on_new=True: WARNING on team/player creation for manual auditing.
- reconcile=False: scrims never touch team_id/role/starter/last_update.
- discover_teams_from_draft=True: recovers teams from the draft when there are
  no played participants (unplayed remake).
- game_type='SCRIM', tournament='SCRIM' fixed.
"""

from __future__ import annotations

import logging
from typing import Generator

import psycopg
from grid_minion import GridGraphQLClient, GridRestClient

from src.common.graphql import paginate

from ._persistence import (
    GameProcessingConfig,
    RoleCache,
    SeriesResult,
    run_series,
)
from .queries import SCRIM_SERIES

log = logging.getLogger("extraction")


def iter_scrim_series(
    client: GridGraphQLClient,
    since_iso: str | None,
) -> Generator[dict, None, None]:
    """Yield scrim series nodes in ASC chronological order.

    No tournament or team filter: downloads every PUBLISHED scrim GRID exposes
    to the account.
    """
    yield from paginate(
        client,
        SCRIM_SERIES,
        "allSeries",
        {"since": since_iso},
    )


def _scrim_cfg(series_node: dict) -> GameProcessingConfig:
    return GameProcessingConfig(
        game_type="SCRIM",
        tournament="SCRIM",
        label="Scrim",
        reconcile=False,
        warn_on_new=True,
        require_participants=False,
        discover_teams_from_draft=True,
        pass_tencent=False,
    )


def process_scrim_series(
    client_rest: GridRestClient,
    client_graphql: GridGraphQLClient,
    conn: psycopg.Connection,
    series_node: dict,
    role_cache: RoleCache,
    champ_lookup: dict[str, int],
) -> SeriesResult:
    """Download and process every game of a scrim series."""
    return run_series(
        client_rest, client_graphql, conn, series_node,
        role_cache, champ_lookup,
        label="Scrim",
        cfg_for_game=_scrim_cfg,
    )
