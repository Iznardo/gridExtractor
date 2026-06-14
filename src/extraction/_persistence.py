"""Helpers de persistencia compartidos entre extractores (oficiales y scrims).

Aqui viven:
- Funciones de INSERT en drafts/games/picks (parametrizadas por game_type).
- Helpers de mapeo (pick_order, champion, fecha, lado de equipo).
- Comprobaciones de idempotencia (game_in_db, series_fully_in_db).
- Clases compartidas: RoleCache (catalogo de roles GRID), SeriesResult,
  RunStats (stats de la corrida).

Este modulo NO importa de official.py ni scrims.py para evitar ciclos.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime

import psycopg
from grid_minion import GridError, GridGraphQLClient

from src.common.roles import normalize_role, role_from_riot_id

from .queries import PLAYER_ROLES_BY_ID

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
# Idempotencia: comprobar si una serie/partida ya esta en BD
# ---------------------------------------------------------------------------

def count_games_in_db(conn: psycopg.Connection, grid_series_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM games WHERE grid_series_id = %s",
            (grid_series_id,),
        )
        return cur.fetchone()[0]


def game_in_db(conn: psycopg.Connection,
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
    db_count = count_games_in_db(conn, grid_series_id)
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
# cada equipo; el orden global (1-10) sigue el patron fijo del draft.
#
# Fase 1 (6 picks, despues de 6 bans alternos):
#   FP1(1), SP1(2), SP2(3), FP2(4), FP3(5), SP3(6)
#
# Fase 2 (4 picks, despues de 4 bans alternos empezando por SP):
#   SP4(7), FP4(8), FP5(9), SP5(10)
#
# SP double-pickea al cerrar fase 1 (SP3) y al abrir fase 2 (SP4),
# luego FP double-pickea (FP4, FP5), y SP cierra con el ultimo pick (SP5).
#
# pick_order=1 es el primer pick del draft (blind pick del FP);
# pick_order=10 es el ultimo (contrapick puro del SP).
FP_PICK_ORDER = {0: 1, 1: 4, 2: 5, 3: 8, 4: 9}
SP_PICK_ORDER = {0: 2, 1: 3, 2: 6, 3: 7, 4: 10}


def pick_order_for(champion_name: str | None,
                   draft_data: dict,
                   grid_team_id: int | None,
                   champ_lookup: dict[str, int]) -> int | None:
    """Devuelve el pick_order global (1-10) del campeon en el draft.

    Compara por champion ID (no por string) para evitar mismatches de
    formato entre GRID ("LeeSin") y Riot ("Lee Sin"). Desde grid-minion
    v0.2.0 los picks del draft son dicts `{"name", "id"}` ya normalizados
    contra Data Dragon, asi que el id sale directo del dict.
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
        order_map  = FP_PICK_ORDER
    else:
        picks_list = sp_picks
        order_map  = SP_PICK_ORDER

    for i, pick in enumerate(picks_list):
        if pick and pick.get("id") == champ_id:
            return order_map.get(i)
    return None


def parse_date(iso: str) -> date:
    """Extrae la parte DATE de un string ISO 8601."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()


def resolve_champ(champ_name: str | None,
                  champ_lookup: dict[str, int]) -> int | None:
    if not champ_name:
        return None
    cid = champ_lookup.get(champ_name)
    if cid is None:
        log.warning("Campeon desconocido: %r — champ_id NULL.", champ_name)
    return cid


def side_for_team(participants: list, grid_team_id: int) -> str:
    """Devuelve 'BLUE' o 'RED' segun el lado que jugo el equipo."""
    for p in participants:
        if p.grid_team_id == grid_team_id:
            return p.team_side
    return "BLUE"  # fallback


# ---------------------------------------------------------------------------
# Persistencia: draft, game, picks
# ---------------------------------------------------------------------------

def insert_draft(
    conn: psycopg.Connection,
    draft_data: dict,
    grid_team_id_to_local: dict[int, int],
    champ_lookup: dict[str, int],
) -> int:
    """Inserta una fila en drafts y devuelve su id."""
    fp = draft_data["fp"]
    sp = draft_data["sp"]

    def champ(entry):
        # v0.2.0: cada pick/ban es {"name", "id"} ya normalizado (o None en
        # un ban saltado). Usamos el id directo; si la libreria no lo resolvio
        # (id None) caemos al champ_lookup por nombre como ultimo recurso.
        if not entry:
            return None
        if entry.get("id") is not None:
            return entry["id"]
        return resolve_champ(entry.get("name"), champ_lookup)

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


def insert_game(
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
    game_type: str,
    tournament: str | None,
) -> int | None:
    """Inserta una fila en games. Devuelve games.id o None si ya existia.

    `game_type` debe ser 'OFFICIAL' o 'SCRIM'.
    `tournament` es el nombre del torneo (root para oficiales) o un
    placeholder ('SCRIM') para scrims.
    """
    game_date = parse_date(series_node["startTimeScheduled"])
    result    = winner if winner in ("BLUE", "RED") else "NONE"

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
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, now(), now()
            )
            ON CONFLICT (grid_series_id, game_number) DO NOTHING
            RETURNING id
            """,
            (
                game_date, version, game_type, tournament,
                team1_local, team2_local, result,
                draft_id,
                int(series_node["id"]), game_number,
                json.dumps(stats_json),
            ),
        )
        row = cur.fetchone()
        return row[0] if row else None


def insert_picks(
    conn: psycopg.Connection,
    *,
    game_id: int,
    winner: str | None,
    participants: list,
    player_grid_to_local: dict[int, int],
    game_stats: dict,
    champ_lookup: dict[str, int],
    draft_data: dict,
    builds_data: dict[int, dict] | None = None,
) -> None:
    """Inserta 10 filas en picks (una por participante).

    `builds_data` es la salida de `BuildObserver.get_builds()` (v0.2.0):
    `{participantId: {"build_path": [...], "skill_order": "..."}}`. Puede ser
    None / vacio si la partida no traia riot_livestats.
    """
    players_stats = game_stats.get("players") or {}
    builds_data   = builds_data or {}

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

            champ_id = resolve_champ(p.champion_name, champ_lookup)
            if champ_id is None:
                log.warning("Campeon %r sin id, skip pick.", p.champion_name)
                continue

            side       = p.team_side  # "BLUE" o "RED"
            result     = (side == winner)
            p_pick_ord = pick_order_for(p.champion_name, draft_data,
                                        p.grid_team_id, champ_lookup)

            p_stats = players_stats.get(p.riot_id) or {}
            b_stats = builds_data.get(p.riot_id) or {}
            # Contrato alineado con SoloQ (CLAUDE.md §10). runes/final_items
            # salen del PostGameObserver (Riot summary); skill_order/build_path
            # del BuildObserver (Riot livestats). Quedan fuera de alcance en
            # GRID: team_position, champ_level, vision_score, summoner_spells.
            stats_json = {
                "kills":        p_stats.get("kills"),
                "deaths":       p_stats.get("deaths"),
                "assists":      p_stats.get("assists"),
                "gold":         p_stats.get("gold"),
                "cs":           p_stats.get("cs"),
                "damage_dealt": p_stats.get("damage_dealt"),
                "kda_str":      p_stats.get("kda_str"),
                "runes":        p_stats.get("runes"),
                "final_items":  p_stats.get("final_items"),
                "skill_order":  b_stats.get("skill_order") or None,
                "build_path":   b_stats.get("build_path") or None,
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
                    side, result, p_pick_ord,
                    json.dumps(stats_json),
                ),
            )
