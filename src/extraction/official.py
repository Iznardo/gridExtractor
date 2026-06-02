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

Los helpers de persistencia e idempotencia viven en `_persistence.py`,
compartidos con el extractor de scrims.
"""

from __future__ import annotations

import logging
from typing import Generator

import psycopg
from grid_minion import GridError, GridGraphQLClient, GridRestClient
from grid_minion import split_grid_series
from grid_minion.observers import (
    DraftObserver,
    GameEventProcessor,
    ObjectiveKilledObserver,
    PostGameObserver,
    TeamsObserver,
    WardsObserver,
)

from src.common.graphql import paginate
from src.db.reconcile import reconcile_player_roster
from src.db.upsert import ensure_player, ensure_team

from ._persistence import (
    RoleCache,
    SeriesResult,
    game_in_db,
    insert_draft,
    insert_game,
    insert_picks,
    parse_date,
    series_fully_in_db,
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
    """Yield series nodes oficiales en orden cronologico ASC."""
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
# Rescate del DraftObserver.draft_history
# ---------------------------------------------------------------------------

def _rescue_from_history(draft: DraftObserver, teams: TeamsObserver) -> dict | None:
    """Devuelve el ultimo draft del historial cuyos picks coinciden con lo jugado.

    Cuando grid-minion resetea el DraftObserver por una invalidacion tecnica
    del feed (no un remake real), el draft completo queda archivado en
    `draft_history`. Validamos contra TeamsObserver para no usar un draft
    descartado de un remake genuino donde los equipos cambiaron de campeones.

    Devuelve `None` si no hay historial, si no se puede validar, o si ningun
    entry coincide con los campeones jugados.
    """
    played = {
        p.champion_name
        for i in range(1, 11)
        if (p := teams.get_player_by_id(i)) is not None
        and p.champion_name
    }
    if len(played) != 10:
        return None

    history = getattr(draft, "draft_history", None) or []
    for h in reversed(history):
        fp_p = (h.get("fp") or {}).get("picks") or []
        sp_p = (h.get("sp") or {}).get("picks") or []
        if len(fp_p) == 5 and len(sp_p) == 5:
            if set(fp_p + sp_p) == played:
                return h
    return None


# ---------------------------------------------------------------------------
# Procesado de una partida individual
# ---------------------------------------------------------------------------

def _process_one_game(
    client_rest: GridRestClient,
    conn: psycopg.Connection,
    series_node: dict,
    series_id: str,
    game_number: int,
    raw_game: list,
    role_cache: RoleCache,
    champ_lookup: dict[str, int],
) -> bool:
    """Procesa una partida: observers -> auto-discovery -> reconciliacion -> INSERT.

    Devuelve True si se inserto, False si se salto.
    """
    # --- Observers ---
    proc  = GameEventProcessor()
    teams = TeamsObserver()
    draft = DraftObserver()
    stats = PostGameObserver()
    objs  = ObjectiveKilledObserver()
    wards = WardsObserver(teams_observer=teams)
    for o in (teams, draft, stats, objs, wards):
        proc.attach(o)

    proc.process_bundle(
        grid_livestats=raw_game,
        riot_summary=client_rest.get_riot_summary(series_id,
                                                  game_number=game_number),
        riot_livestats=client_rest.get_riot_livestats(series_id,
                                                      game_number=game_number),
    )

    draft_data = draft.get_draft()
    if not draft_data["draft_found"]:
        rescued = _rescue_from_history(draft, teams)
        if rescued is None:
            log.warning("Serie %s game %d: draft vacio sin historial "
                        "recuperable, skip.", series_id, game_number)
            return False
        log.info("Serie %s game %d: draft RESCATADO del historial "
                 "(picks coinciden con lo jugado).",
                 series_id, game_number)
        draft_data = rescued

    game_stats = stats.get_game_stats(teams)
    winner = game_stats["meta"].get("winner")

    if game_stats["meta"].get("winner_source") == "gold_heuristic":
        log.warning("Serie %s game %d: ganador por heuristica de oro "
                    "(datos de oficial sospechosos).", series_id, game_number)

    # --- Recoger participants (riot_id 1..10) ---
    participants = [
        p for i in range(1, 11)
        if (p := teams.get_player_by_id(i)) is not None
    ]
    if not participants:
        log.warning("Serie %s game %d: sin participants, skip.",
                    series_id, game_number)
        return False

    # --- Auto-discovery: equipos ---
    # Prioridad: datos del TeamsObserver; complementar con series_node si faltan.
    series_teams_by_grid = {
        int(t["baseInfo"]["id"]): t["baseInfo"]
        for t in (series_node.get("teams") or [])
    }

    grid_team_id_to_local: dict[int, int] = {}
    seen_team_ids: set[int] = set()
    for p in participants:
        if p.grid_team_id is None:
            continue
        gid = int(p.grid_team_id)
        if gid in seen_team_ids:
            continue
        seen_team_ids.add(gid)
        base = series_teams_by_grid.get(gid, {})
        local_id, _ = ensure_team(
            conn,
            grid_id=gid,
            name=base.get("name") or f"Team_{gid}",
            tag=base.get("nameShortened"),
        )
        grid_team_id_to_local[gid] = local_id

    # team1=BLUE, team2=RED por convencion
    team1_local = team2_local = None
    for p in participants:
        if p.grid_team_id is None:
            continue
        local = grid_team_id_to_local.get(int(p.grid_team_id))
        if p.team_side == "BLUE" and team1_local is None:
            team1_local = local
        elif p.team_side == "RED" and team2_local is None:
            team2_local = local

    # --- Auto-discovery: jugadores + reconciliacion ---
    game_date = parse_date(series_node["startTimeScheduled"])
    player_grid_to_local: dict[int, int] = {}

    for p in participants:
        if p.grid_player_id is None:
            log.warning("Participant riot_id=%d sin grid_player_id, skip.",
                        p.riot_id)
            continue

        grid_pid = int(p.grid_player_id)
        team_local = (grid_team_id_to_local.get(int(p.grid_team_id))
                      if p.grid_team_id else None)

        role_obs = role_cache.role_for(grid_pid, p.riot_id)

        local_id, _ = ensure_player(
            conn,
            grid_id=grid_pid,
            nickname=p.summoner_name or f"Player_{grid_pid}",
            team_local_id=team_local,
            role=role_obs,
        )
        player_grid_to_local[grid_pid] = local_id

        if role_obs and team_local:
            reconcile_player_roster(
                conn,
                player_local_id=local_id,
                team_local_id=team_local,
                role_observed=role_obs,
                game_date=game_date,
            )

    # --- INSERT draft ---
    draft_id = insert_draft(conn, draft_data, grid_team_id_to_local,
                            champ_lookup)

    # --- INSERT game (game_type='OFFICIAL', tournament=root) ---
    game_id = insert_game(
        conn,
        series_node=series_node,
        game_number=game_number,
        winner=winner,
        version=game_stats["meta"].get("version"),
        team1_local=team1_local,
        team2_local=team2_local,
        draft_id=draft_id,
        game_stats=game_stats,
        objs_data=objs.get_all_objectives(),
        wards_data=wards.get_wards(),
        game_type="OFFICIAL",
        tournament=root_tournament_name(series_node),
    )

    if game_id is None:
        log.info("Serie %s game %d: ya existia en BD (ON CONFLICT).",
                 series_id, game_number)
        return False

    # --- INSERT picks ---
    insert_picks(
        conn,
        game_id=game_id,
        winner=winner,
        participants=participants,
        player_grid_to_local=player_grid_to_local,
        game_stats=game_stats,
        champ_lookup=champ_lookup,
        draft_data=draft_data,
    )

    return True


# ---------------------------------------------------------------------------
# Procesado de una serie completa
# ---------------------------------------------------------------------------

def process_series(
    client_rest: GridRestClient,
    client_graphql: GridGraphQLClient,
    conn: psycopg.Connection,
    series_node: dict,
    role_cache: RoleCache,
    champ_lookup: dict[str, int],
) -> SeriesResult:
    """Descarga y procesa todas las partidas de una serie."""
    series_id      = series_node["id"]
    grid_series_id = int(series_id)
    result         = SeriesResult()

    if series_fully_in_db(conn, grid_series_id, client_graphql, series_id):
        log.debug("Serie %s: ya completa en BD, skip.", series_id)
        result.skipped = True
        return result

    try:
        full = client_rest.get_grid_events(series_id)
    except GridError as e:
        log.error("Serie %s: error descargando eventos: %s", series_id, e)
        result.errors += 1
        return result

    if not full:
        log.info("Serie %s: sin eventos disponibles, skip.", series_id)
        result.no_events = True
        return result

    games = split_grid_series(full)
    log.info("Serie %s (%s): %d partida(s).",
             series_id,
             root_tournament_name(series_node),
             len(games))

    for i, raw_game in enumerate(games):
        game_number = i + 1

        if game_in_db(conn, grid_series_id, game_number):
            log.debug("Serie %s game %d: ya en BD, skip.", series_id, game_number)
            result.games_skipped += 1
            continue

        try:
            with conn.transaction():
                inserted = _process_one_game(
                    client_rest, conn, series_node,
                    series_id, game_number, raw_game,
                    role_cache, champ_lookup,
                )
            if inserted:
                result.games_new += 1
                log.info("Serie %s game %d: insertada.", series_id, game_number)
            else:
                result.games_skipped += 1

        except Exception:
            log.exception("Serie %s game %d: fallo inesperado, sigo.",
                          series_id, game_number)
            result.errors += 1

    return result
