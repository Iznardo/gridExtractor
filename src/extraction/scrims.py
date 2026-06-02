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

Diferencias clave con oficiales:
- No filtra por torneo: descarga todas las scrims `PUBLISHED` de la cuenta.
- Cuando ensure_team / ensure_player crean una fila nueva (is_new=True),
  se emite log.warning con grid_id, nombre y contexto de serie/partida
  para auditoria manual posterior.
- NO se llama a reconcile_player_roster: scrims no actualizan
  team_id/role/starter/last_update del jugador.
- INSERT con game_type='SCRIM' y tournament='SCRIM' fijo.
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
from src.db.upsert import ensure_player, ensure_team

from ._persistence import (
    RoleCache,
    SeriesResult,
    game_in_db,
    insert_draft,
    insert_game,
    insert_picks,
    series_fully_in_db,
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
# Rescate del DraftObserver.draft_history
# ---------------------------------------------------------------------------

def _rescue_from_history(draft: DraftObserver, teams: TeamsObserver) -> dict | None:
    """Devuelve el ultimo draft del historial cuyos picks coinciden con lo jugado.

    Cuando DraftObserver resetea por una invalidacion (remake o problema tecnico
    del feed), archiva el estado en `draft_history`. Buscamos hacia atras la
    primera entrada completa (5+5 picks) cuyos 10 campeones coincidan exactamente
    con los que TeamsObserver reporta como jugados.

    Validar contra TeamsObserver evita usar un draft descartado de un remake
    genuino donde los equipos cambiaron de campeones.

    Devuelve `None` si no hay historial, si no se puede validar (menos de 10
    campeones conocidos), o si ningun entry del historial coincide.
    """
    played = {
        p.champion_name
        for i in range(1, 11)
        if (p := teams.get_player_by_id(i)) is not None
        and p.champion_name
    }
    if len(played) != 10:
        return None  # no se puede validar de forma segura

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

def _process_one_scrim_game(
    client_rest: GridRestClient,
    conn: psycopg.Connection,
    series_node: dict,
    series_id: str,
    game_number: int,
    raw_game: list,
    role_cache: RoleCache,
    champ_lookup: dict[str, int],
) -> bool:
    """Procesa una scrim: observers -> auto-discovery con warning -> INSERT.

    Devuelve True si se inserto, False si se salto.
    """
    # --- Observers (identico a oficiales) ---
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
        # Rescate: tras un remake (draft completo + partida cancelada o
        # nuevo draft) el DraftObserver archiva el draft en draft_history
        # y resetea la mesa. Buscamos el ultimo draft completo del historial.
        rescued = _rescue_from_history(draft, teams)
        if rescued is None:
            log.warning("Scrim %s game %d: draft vacio sin historial "
                        "recuperable, skip.", series_id, game_number)
            return False
        log.info("Scrim %s game %d: draft RESCATADO del historial "
                 "(picks coinciden con lo jugado).",
                 series_id, game_number)
        draft_data = rescued

    game_stats = stats.get_game_stats(teams)
    winner = game_stats["meta"].get("winner")

    # --- Recoger participants (riot_id 1..10) ---
    # En el caso "remake de partida no jugada" puede que esten vacios o
    # incompletos: el flujo lo tolera (game + draft se insertan; las picks
    # solo entran si hay champion_name).
    participants = [
        p for i in range(1, 11)
        if (p := teams.get_player_by_id(i)) is not None
    ]

    # --- Auto-discovery: equipos (con WARNING si is_new) ---
    series_teams_by_grid = {
        int(t["baseInfo"]["id"]): t["baseInfo"]
        for t in (series_node.get("teams") or [])
    }

    grid_team_id_to_local: dict[int, int] = {}

    def _discover_team(gid: int) -> None:
        if gid in grid_team_id_to_local:
            return
        base = series_teams_by_grid.get(gid, {})
        name = base.get("name") or f"Team_{gid}"
        local_id, is_new = ensure_team(
            conn,
            grid_id=gid,
            name=name,
            tag=base.get("nameShortened"),
        )
        if is_new:
            log.warning(
                "Scrim %s game %d: creado TEAM nuevo en BD "
                "(grid_id=%d, name=%r) - revisar manualmente.",
                series_id, game_number, gid, name,
            )
        grid_team_id_to_local[gid] = local_id

    for p in participants:
        if p.grid_team_id is None:
            continue
        _discover_team(int(p.grid_team_id))

    # Si participants no aportan los equipos (partida no jugada), usar los
    # del draft rescatado para no perder esa info.
    for side in ("fp", "sp"):
        tid_str = (draft_data.get(side) or {}).get("team_id")
        if tid_str:
            _discover_team(int(tid_str))

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

    # --- Auto-discovery: jugadores (con WARNING si is_new) ---
    # NO se llama a reconcile_player_roster (CLAUDE.md §5.5).
    player_grid_to_local: dict[int, int] = {}

    for p in participants:
        if p.grid_player_id is None:
            log.warning("Scrim %s game %d: participant riot_id=%d sin "
                        "grid_player_id, skip pick.",
                        series_id, game_number, p.riot_id)
            continue

        grid_pid = int(p.grid_player_id)
        team_local = (grid_team_id_to_local.get(int(p.grid_team_id))
                      if p.grid_team_id else None)

        role_obs = role_cache.role_for(grid_pid, p.riot_id)
        nickname = p.summoner_name or f"Player_{grid_pid}"

        local_id, is_new = ensure_player(
            conn,
            grid_id=grid_pid,
            nickname=nickname,
            team_local_id=team_local,
            role=role_obs,
        )
        if is_new:
            log.warning(
                "Scrim %s game %d: creado PLAYER nuevo en BD "
                "(grid_id=%d, nickname=%r, team_local=%s, role=%s) - "
                "revisar manualmente.",
                series_id, game_number, grid_pid, nickname,
                team_local, role_obs,
            )
        player_grid_to_local[grid_pid] = local_id

    # --- INSERT draft ---
    draft_id = insert_draft(conn, draft_data, grid_team_id_to_local,
                            champ_lookup)

    # --- INSERT game (game_type='SCRIM', tournament='SCRIM') ---
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
        game_type="SCRIM",
        tournament="SCRIM",
    )

    if game_id is None:
        log.info("Scrim %s game %d: ya existia en BD (ON CONFLICT).",
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

def process_scrim_series(
    client_rest: GridRestClient,
    client_graphql: GridGraphQLClient,
    conn: psycopg.Connection,
    series_node: dict,
    role_cache: RoleCache,
    champ_lookup: dict[str, int],
) -> SeriesResult:
    """Descarga y procesa todas las partidas de una serie de scrim."""
    series_id      = series_node["id"]
    grid_series_id = int(series_id)
    result         = SeriesResult()

    if series_fully_in_db(conn, grid_series_id, client_graphql, series_id):
        log.debug("Scrim %s: ya completa en BD, skip.", series_id)
        result.skipped = True
        return result

    try:
        full = client_rest.get_grid_events(series_id)
    except GridError as e:
        log.error("Scrim %s: error descargando eventos: %s", series_id, e)
        result.errors += 1
        return result

    if not full:
        log.info("Scrim %s: sin eventos disponibles, skip.", series_id)
        result.no_events = True
        return result

    games = split_grid_series(full)
    log.info("Scrim %s: %d partida(s).", series_id, len(games))

    for i, raw_game in enumerate(games):
        game_number = i + 1

        if game_in_db(conn, grid_series_id, game_number):
            log.debug("Scrim %s game %d: ya en BD, skip.", series_id, game_number)
            result.games_skipped += 1
            continue

        try:
            with conn.transaction():
                inserted = _process_one_scrim_game(
                    client_rest, conn, series_node,
                    series_id, game_number, raw_game,
                    role_cache, champ_lookup,
                )
            if inserted:
                result.games_new += 1
                log.info("Scrim %s game %d: insertada.", series_id, game_number)
            else:
                result.games_skipped += 1

        except Exception:
            log.exception("Scrim %s game %d: fallo inesperado, sigo.",
                          series_id, game_number)
            result.errors += 1

    return result
