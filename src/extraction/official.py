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
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Generator

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

from src.common.champions import build_lookup, ensure_loaded
from src.common.graphql import paginate
from src.common.roles import normalize_role, role_from_riot_id
from src.db.reconcile import reconcile_player_roster
from src.db.upsert import ensure_player, ensure_team

from .queries import OFFICIAL_SERIES_BY_TOURNAMENT, PLAYER_ROLES_BY_ID

log = logging.getLogger("extraction")


# ---------------------------------------------------------------------------
# Stats de resumen de la corrida
# ---------------------------------------------------------------------------

@dataclass
class SeriesResult:
    skipped: bool = False
    no_events: bool = False
    games_new: int = 0
    games_skipped: int = 0
    errors: int = 0


@dataclass
class RunStats:
    series_skipped: int = 0
    series_no_events: int = 0
    series_processed: int = 0
    games_new: int = 0
    games_skipped: int = 0
    errors: int = 0

    def add(self, r: SeriesResult) -> None:
        if r.skipped:
            self.series_skipped += 1
        elif r.no_events:
            self.series_no_events += 1
        else:
            self.series_processed += 1
        self.games_new += r.games_new
        self.games_skipped += r.games_skipped
        self.errors += r.errors

    def __str__(self) -> str:
        return (
            f"series: {self.series_processed} procesadas, "
            f"{self.series_skipped} skip (ya en BD), "
            f"{self.series_no_events} sin datos | "
            f"partidas: {self.games_new} nuevas, "
            f"{self.games_skipped} skip, "
            f"{self.errors} errores"
        )


# ---------------------------------------------------------------------------
# Cache de roles del catalogo de GRID (una corrida = una instancia)
# ---------------------------------------------------------------------------

class RoleCache:
    """Cachea Player.roles[].name (normalizado) por grid_player_id.

    Una query GraphQL por jugador UNICO en la corrida, no por partida.
    Fallback a la convencion de orden de riot_id si GRID no aporta rol.
    """

    def __init__(self, client: GridGraphQLClient) -> None:
        self._cache: dict[int, str | None] = {}
        self._client = client

    def role_for(self, grid_player_id: int, riot_id: int) -> str | None:
        if grid_player_id not in self._cache:
            try:
                data = self._client.query_central(
                    PLAYER_ROLES_BY_ID,
                    variables={"pid": str(grid_player_id)},
                )
                roles = ((data.get("player") or {}).get("roles") or [])
                raw = roles[0]["name"] if roles else None
                self._cache[grid_player_id] = normalize_role(raw)
            except GridError as e:
                log.warning("RoleCache: error consultando jugador %d: %s",
                            grid_player_id, e)
                self._cache[grid_player_id] = None

        return self._cache[grid_player_id] or role_from_riot_id(riot_id)


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
# Idempotencia: comprobar si una serie/partida ya esta en BD
# ---------------------------------------------------------------------------

def _count_games_in_db(conn: psycopg.Connection, grid_series_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM games WHERE grid_series_id = %s",
            (grid_series_id,),
        )
        return cur.fetchone()[0]


def _game_in_db(conn: psycopg.Connection,
                grid_series_id: int, game_number: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM games WHERE grid_series_id = %s AND game_number = %s",
            (grid_series_id, game_number),
        )
        return cur.fetchone() is not None


def series_fully_in_db(
    conn: psycopg.Connection,
    grid_series_id: int,
    client_graphql: GridGraphQLClient,
    series_id: str,
) -> bool:
    """True si las partidas finalizadas de la serie ya estan todas en BD.

    Llama a get_series_state (ligero, GraphQL) y compara con el count de BD.
    Si no se puede determinar (error), devuelve False para no saltarse nada.
    """
    db_count = _count_games_in_db(conn, grid_series_id)
    if db_count == 0:
        return False
    try:
        state = client_graphql.get_series_state(series_id)
        if not state:
            return False
        finished = sum(1 for g in (state.get("games") or []) if g.get("finished"))
        return db_count >= finished > 0
    except GridError as e:
        log.warning("series_fully_in_db: error en get_series_state %s: %s",
                    series_id, e)
        return False


# ---------------------------------------------------------------------------
# Helpers de mapeo
# ---------------------------------------------------------------------------

# Orden global de picks en el draft competitivo de LoL (formato estandar).
# fp.picks[i] y sp.picks[i] son los picks en orden cronologico dentro de
# cada equipo; el orden global (1-10) sigue el patron fijo de la fase 1 y 2.
#
# Fase 1 picks: FP1, SP1, SP2, FP2, FP3
# Fase 2 picks: SP3, FP4, FP5, SP4, SP5
#
# pick_order=1 es el primer pick del draft (blind pick del FP);
# pick_order=10 es el ultimo (ultimo counterpick del SP).
_FP_PICK_ORDER = {0: 1, 1: 4, 2: 5, 3: 7, 4: 8}
_SP_PICK_ORDER = {0: 2, 1: 3, 2: 6, 3: 9, 4: 10}


def _pick_order_for(champion_name: str | None,
                    draft_data: dict,
                    grid_team_id: int | None,
                    champ_lookup: dict[str, int]) -> int | None:
    """Devuelve el pick_order global (1-10) del campeon en el draft.

    Compara por champion ID (no por string) para evitar mismatches de
    formato entre GRID ("LeeSin") y Riot ("Lee Sin").
    """
    if not champion_name or grid_team_id is None:
        return None

    champ_id = champ_lookup.get(champion_name)
    if champ_id is None:
        return None

    fp_team_id = draft_data["fp"].get("team_id")
    fp_picks   = draft_data["fp"].get("picks") or []
    sp_picks   = draft_data["sp"].get("picks") or []

    if str(grid_team_id) == str(fp_team_id):
        picks_list = fp_picks
        order_map  = _FP_PICK_ORDER
    else:
        picks_list = sp_picks
        order_map  = _SP_PICK_ORDER

    for i, pick_name in enumerate(picks_list):
        if pick_name and champ_lookup.get(pick_name) == champ_id:
            return order_map.get(i)
    return None


def _parse_date(iso: str) -> date:
    """Extrae la parte DATE de un string ISO 8601."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()


def _resolve_champ(champ_name: str | None,
                   champ_lookup: dict[str, int]) -> int | None:
    if not champ_name:
        return None
    cid = champ_lookup.get(champ_name)
    if cid is None:
        log.warning("Campeon desconocido: %r — champ_id NULL.", champ_name)
    return cid


def _side_for_team(participants: list, grid_team_id: int) -> str:
    """Devuelve 'BLUE' o 'RED' segun el lado que jugo el equipo."""
    for p in participants:
        if p.grid_team_id == grid_team_id:
            return p.team_side
    return "BLUE"  # fallback


# ---------------------------------------------------------------------------
# Persistencia: draft, game, picks
# ---------------------------------------------------------------------------

def _insert_draft(
    conn: psycopg.Connection,
    draft_data: dict,
    grid_team_id_to_local: dict[int, int],
    champ_lookup: dict[str, int],
) -> int:
    """Inserta una fila en drafts y devuelve su id."""
    fp = draft_data["fp"]
    sp = draft_data["sp"]

    def champ(name):
        return _resolve_champ(name, champ_lookup)

    fp_team_id_str = fp.get("team_id")
    fp_local = None
    if fp_team_id_str:
        fp_local = grid_team_id_to_local.get(int(fp_team_id_str))

    fp_picks = fp.get("picks") or []
    sp_picks = sp.get("picks") or []
    fp_bans  = fp.get("bans")  or []
    sp_bans  = sp.get("bans")  or []

    # Rellenar hasta 5 elementos (puede venir incompleto en remakes)
    def pad(lst, n=5):
        return (list(lst) + [None] * n)[:n]

    fp_picks = pad(fp_picks)
    sp_picks = pad(sp_picks)
    fp_bans  = pad(fp_bans)
    sp_bans  = pad(sp_bans)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO drafts (
                first_pick_team_id,
                ban1,  ban2,  ban3,  ban4,  ban5,
                ban6,  ban7,  ban8,  ban9,  ban10,
                pick1, pick2, pick3, pick4, pick5,
                pick6, pick7, pick8, pick9, pick10
            ) VALUES (
                %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            RETURNING id
            """,
            (
                fp_local,
                champ(fp_bans[0]),  champ(fp_bans[1]),  champ(fp_bans[2]),
                champ(fp_bans[3]),  champ(fp_bans[4]),
                champ(sp_bans[0]),  champ(sp_bans[1]),  champ(sp_bans[2]),
                champ(sp_bans[3]),  champ(sp_bans[4]),
                champ(fp_picks[0]), champ(fp_picks[1]), champ(fp_picks[2]),
                champ(fp_picks[3]), champ(fp_picks[4]),
                champ(sp_picks[0]), champ(sp_picks[1]), champ(sp_picks[2]),
                champ(sp_picks[3]), champ(sp_picks[4]),
            ),
        )
        return cur.fetchone()[0]


def _insert_game(
    conn: psycopg.Connection,
    *,
    series_node: dict,
    game_number: int,
    winner: str | None,
    version: str | None,
    team1_local: int | None,
    team2_local: int | None,
    draft_id: int,
    game_stats: dict,
    objs_data: dict,
    wards_data: list,
) -> int | None:
    """Inserta una fila en games. Devuelve games.id o None si ya existia."""
    game_date  = _parse_date(series_node["startTimeScheduled"])
    tournament = root_tournament_name(series_node)
    result     = winner if winner in ("BLUE", "RED") else "NONE"

    stats_json = {
        "meta":       game_stats.get("meta", {}),
        "objectives": objs_data,
        "wards":      wards_data,
    }

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO games (
                date, version, game_type, tournament,
                team1_id, team2_id, result,
                draft_id, grid_series_id, game_number,
                stats, created_at, updated_at
            ) VALUES (
                %s, %s, 'OFFICIAL', %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, now(), now()
            )
            ON CONFLICT (grid_series_id, game_number) DO NOTHING
            RETURNING id
            """,
            (
                game_date, version, tournament,
                team1_local, team2_local, result,
                draft_id,
                int(series_node["id"]), game_number,
                json.dumps(stats_json),
            ),
        )
        row = cur.fetchone()
        return row[0] if row else None


def _insert_picks(
    conn: psycopg.Connection,
    *,
    game_id: int,
    winner: str | None,
    participants: list,
    player_grid_to_local: dict[int, int],
    game_stats: dict,
    champ_lookup: dict[str, int],
    draft_data: dict,
) -> None:
    """Inserta 10 filas en picks (una por participante)."""
    players_stats = game_stats.get("players") or {}

    with conn.cursor() as cur:
        for p in participants:
            if p.grid_player_id is None:
                log.warning("Participant riot_id=%d sin grid_player_id, skip pick.",
                            p.riot_id)
                continue

            player_local = player_grid_to_local.get(int(p.grid_player_id))
            if player_local is None:
                log.warning("Jugador grid_id=%s no resuelto, skip pick.",
                            p.grid_player_id)
                continue

            champ_id = _resolve_champ(p.champion_name, champ_lookup)
            if champ_id is None:
                log.warning("Campeon %r sin id, skip pick.", p.champion_name)
                continue

            side       = p.team_side  # "BLUE" o "RED"
            result     = (side == winner)
            pick_order = _pick_order_for(p.champion_name, draft_data,
                                         p.grid_team_id, champ_lookup)

            p_stats = players_stats.get(p.riot_id) or {}
            stats_json = {
                k: p_stats.get(k)
                for k in ("kills", "deaths", "assists", "gold",
                          "cs", "damage_dealt", "kda_str")
            }

            cur.execute(
                """
                INSERT INTO picks
                    (player_id, account_id, game_id, champ_id,
                     side, result, pick_order, stats)
                VALUES (%s, NULL, %s, %s, %s, %s, %s, %s)
                """,
                (
                    player_local, game_id, champ_id,
                    side, result, pick_order,
                    json.dumps(stats_json),
                ),
            )


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
        log.warning("Serie %s game %d: draft vacio, skip.",
                    series_id, game_number)
        return False

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
    game_date = _parse_date(series_node["startTimeScheduled"])
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
    draft_id = _insert_draft(conn, draft_data, grid_team_id_to_local,
                             champ_lookup)

    # --- INSERT game ---
    game_id = _insert_game(
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
    )

    if game_id is None:
        log.info("Serie %s game %d: ya existia en BD (ON CONFLICT).",
                 series_id, game_number)
        return False

    # --- INSERT picks ---
    _insert_picks(
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

        if _game_in_db(conn, grid_series_id, game_number):
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
