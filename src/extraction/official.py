"""Extraccion de partidos oficiales desde GRID.

Flujo (CLAUDE.md §2, §5.2, §5.5):

  config/tournaments.yaml  -> nombres
       │
       ▼
  allSeries (ESPORTS, orden ASC, con includeChildren) paginado
       │  skip series ya completas en BD
       ▼
  get_grid_events(series_id)  -> eventos crudos
  split_grid_series()          -> una lista por partida
       │
       ▼  por cada partida
  GameEventProcessor + observers (teams, draft, stats, objs, wards)
       │
       ▼
  auto-discovery (ensure_team, ensure_player)
  reconciliacion posicional (reconcile_player_roster §5.5)
  INSERT drafts / games / picks  (idempotente)

El procesado por partida/serie es compartido con scrims y vive en
`_persistence.py` (run_series + process_one_game). Aqui solo queda lo
especifico de oficiales: descubrimiento de series y la config del flujo.
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


# ---------------------------------------------------------------------------
# Descubrimiento de series
# ---------------------------------------------------------------------------

def iter_official_series(
    client: GridGraphQLClient,
    tournament_ids: list[str],
    since_iso: str | None,
) -> Generator[dict, None, None]:
    """Yield series nodes oficiales (orden ASC dentro de cada torneo).

    El orden cronologico GLOBAL entre torneos lo garantiza el caller
    (run.py ordena por startTimeScheduled antes de procesar, §5.5).
    """
    for tid in tournament_ids:
        yield from paginate(
            client,
            OFFICIAL_SERIES_BY_TOURNAMENT,
            "allSeries",
            {"tid": tid, "since": since_iso},
        )


def root_tournament_name(series_node: dict) -> str:
    """Sube por Tournament.parent hasta el root y devuelve su name."""
    t = series_node.get("tournament") or {}
    while t.get("parent"):
        t = t["parent"]
    return t.get("name") or ""


# ---------------------------------------------------------------------------
# Config del flujo para oficiales
# ---------------------------------------------------------------------------

def _official_cfg(series_node: dict) -> GameProcessingConfig:
    return GameProcessingConfig(
        game_type="OFFICIAL",
        tournament=root_tournament_name(series_node),
        label="Serie",
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
    """Descarga y procesa todas las partidas de una serie oficial."""
    return run_series(
        client_rest, client_graphql, conn, series_node,
        role_cache, champ_lookup,
        label="Serie",
        cfg_for_game=_official_cfg,
    )
