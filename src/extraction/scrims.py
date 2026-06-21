"""Extraccion de scrims desde GRID.

Flujo (CLAUDE.md §2, §5.2, §5.4 — sin reconciliacion §5.5):

  allSeries (SCRIM, orden ASC, sin filtro de torneo) paginado
       │  skip series ya completas en BD
       ▼
  get_grid_events(series_id)  -> eventos crudos
  split_grid_series()          -> una lista por partida
       │
       ▼  por cada partida
  GameEventProcessor + observers (teams, draft, stats, objs, wards)
       │
       ▼
  auto-discovery (ensure_team, ensure_player) con WARNING si is_new
  INSERT drafts / games / picks  (game_type='SCRIM', tournament='SCRIM')

El procesado por partida/serie es compartido con oficiales y vive en
`_persistence.py` (run_series + process_one_game). Las diferencias de
scrims se expresan via GameProcessingConfig:
- No filtra por torneo: descarga todas las scrims `PUBLISHED` de la cuenta.
- warn_on_new=True: WARNING al crear team/player para auditoria manual.
- reconcile=False: scrims no tocan team_id/role/starter/last_update (§5.5).
- discover_teams_from_draft=True: rescata equipos del draft si no hay
  participants jugados (remake no jugado).
- game_type='SCRIM', tournament='SCRIM' fijo.
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


# ---------------------------------------------------------------------------
# Descubrimiento de series
# ---------------------------------------------------------------------------

def iter_scrim_series(
    client: GridGraphQLClient,
    since_iso: str | None,
) -> Generator[dict, None, None]:
    """Yield series nodes de scrims en orden cronologico ASC.

    Sin filtro de torneo ni de equipo: descarga todas las scrims
    `PUBLISHED` que GRID exponga a la cuenta.
    """
    yield from paginate(
        client,
        SCRIM_SERIES,
        "allSeries",
        {"since": since_iso},
    )


# ---------------------------------------------------------------------------
# Config del flujo para scrims
# ---------------------------------------------------------------------------

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
    """Descarga y procesa todas las partidas de una serie de scrim."""
    return run_series(
        client_rest, client_graphql, conn, series_node,
        role_cache, champ_lookup,
        label="Scrim",
        cfg_for_game=_scrim_cfg,
    )
