"""Extraction of official games from GRID.

Flow:

  config/tournaments.yaml  -> names
       │
       ▼
  allSeries (ESPORTS, ASC order, includeChildren) paginated
       │  skip series already complete in DB
       ▼
  get_grid_events(series_id)  -> raw events
  split_grid_series()          -> one list per game
       │
       ▼  per game
  GameEventProcessor + observers (teams, draft, stats, objs, wards)
       │
       ▼
  auto-discovery (ensure_team, ensure_player)
  positional reconciliation (reconcile_player_roster)
  INSERT drafts / games / picks  (idempotent)

The per-game/series processing is shared with scrims and lives in
`_persistence.py` (run_series + process_one_game). This module holds only what
is official-specific: series discovery and the flow config.
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
from .queries import OFFICIAL_SERIES_BY_TOURNAMENT

log = logging.getLogger("extraction")


def iter_official_series(
    client: GridGraphQLClient,
    tournament_ids: list[str],
    since_iso: str | None,
) -> Generator[dict, None, None]:
    """Yield official series nodes (ASC order within each tournament).

    Global chronological order across tournaments is the caller's job (run.py
    sorts by startTimeScheduled before processing).
    """
    for tid in tournament_ids:
        yield from paginate(
            client,
            OFFICIAL_SERIES_BY_TOURNAMENT,
            "allSeries",
            {"tid": tid, "since": since_iso},
        )


def root_tournament_name(series_node: dict) -> str:
    """Walk up Tournament.parent to the root and return its name."""
    t = series_node.get("tournament") or {}
    while t.get("parent"):
        t = t["parent"]
    return t.get("name") or ""


def _official_cfg(series_node: dict) -> GameProcessingConfig:
    return GameProcessingConfig(
        game_type="OFFICIAL",
        tournament=root_tournament_name(series_node),
        label="Series",
        reconcile=True,
        warn_on_new=False,
        require_participants=True,
        discover_teams_from_draft=False,
        pass_tencent=True,
    )


def process_series(
    client_rest: GridRestClient,
    client_graphql: GridGraphQLClient,
    conn: psycopg.Connection,
    series_node: dict,
    role_cache: RoleCache,
    champ_lookup: dict[str, int],
) -> SeriesResult:
    """Download and process every game of an official series."""
    return run_series(
        client_rest, client_graphql, conn, series_node,
        role_cache, champ_lookup,
        label="Series",
        cfg_for_game=_official_cfg,
    )
