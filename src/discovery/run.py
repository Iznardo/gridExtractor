"""Discovery en bloque de equipos y jugadores desde GRID.

Flujo (CLAUDE.md §6, DISCOVERY_PLAN.md §3):

  config/tournaments.yaml  -> nombres
       │
       ▼
  tournaments(filter:{name:{contains}})  -> resolver tournamentId
       │
       ▼
  allSeries(filter:{tournament:{id, includeChildren:true}, types:[ESPORTS]}) paginado
       │  solo equipos — Series.players[] incompleto en GRID
       ▼
  teams[]  -> ensure_team
       │
       ▼
  por cada equipo: players(filter:{teamIdFilter:{id}}) paginado
       │  roster completo: titulares + suplentes
       ▼
  ensure_player (con role normalizado)

Lanzar:  python -m src.discovery.run
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Generator

import yaml
from dotenv import load_dotenv
from grid_minion import GridError, GridGraphQLClient

from src.db.conn import get_conn
from src.db.upsert import ensure_player, ensure_team

from .queries import PLAYERS_BY_TEAM, SERIES_BY_TOURNAMENTS, TOURNAMENTS_BY_NAME


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "tournaments.yaml"

log = logging.getLogger("discovery")

# Mapeo de nombres de rol de GRID (minusculas, verificados empiricamente)
# al formato de la tabla. Valores observados: top, mid, jungle, bottom, support.
_ROLE_MAP: dict[str, str] = {
    "top": "TOP",
    "mid": "MID",
    "jungle": "JUNGLE",
    "bottom": "ADC",
    "support": "SUPPORT",
}


def normalize_role(raw: str | None) -> str | None:
    """Convierte el nombre de rol de GRID al formato de la tabla.

    Devuelve None si raw es None o no esta en el mapa conocido (con
    warning para detectar valores nuevos).
    """
    if not raw:
        return None
    normalized = _ROLE_MAP.get(raw.strip().lower())
    if normalized is None:
        log.warning("Rol desconocido de GRID: %r — se deja NULL.", raw)
    return normalized


# ---------------------------------------------------------------------------
# Config y arranque
# ---------------------------------------------------------------------------

def load_tournament_names() -> list[str]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    names = data.get("tournaments") or []
    if not isinstance(names, list):
        raise ValueError(
            f"{CONFIG_PATH}: el campo `tournaments` debe ser una lista YAML."
        )
    return [n for n in names if isinstance(n, str) and n.strip()]


def build_client() -> GridGraphQLClient:
    api_key = os.environ.get("GRID_API_KEY")
    if not api_key:
        log.error("Falta GRID_API_KEY en el entorno (.env).")
        sys.exit(1)
    return GridGraphQLClient(api_key=api_key)


# ---------------------------------------------------------------------------
# GraphQL: paginacion Relay generica + queries especificas
# ---------------------------------------------------------------------------

def _paginate(
    client: GridGraphQLClient,
    query: str,
    root_key: str,
    variables: dict[str, Any],
) -> Generator[dict, None, None]:
    """Genera nodos de una conexion Relay paginando hasta agotar.

    Parametros:
        root_key: clave del campo raiz en `data` (ej. "allSeries", "players").
        variables: se fusionan con {"after": cursor} en cada pagina.
    """
    cursor: str | None = None
    while True:
        data = client.query_central(query, variables={**variables, "after": cursor})
        conn = data.get(root_key) or {}
        for edge in conn.get("edges") or []:
            node = edge.get("node")
            if node:
                yield node
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
        if not cursor:
            break


def resolve_tournament_id(
    client: GridGraphQLClient,
    name: str,
) -> str | None:
    """Devuelve el ID del torneo cuyo `name` coincide exacto con `name`.

    Devuelve None si hay 0 matches o ambiguedad (avisar y saltar).
    La jerarquia de subfases se resuelve en SERIES_BY_TOURNAMENTS con
    `includeChildren: { equals: true }`.
    """
    data = client.query_central(TOURNAMENTS_BY_NAME, variables={"name": name})
    edges = (data.get("tournaments") or {}).get("edges") or []
    candidates = [e["node"] for e in edges if e.get("node")]
    exact = [n for n in candidates if n.get("name") == name]
    if not exact:
        log.warning(
            "Torneo %r: sin coincidencia exacta. Candidatos (contains): %s",
            name,
            [c.get("name") for c in candidates] or "[]",
        )
        return None
    if len(exact) > 1:
        log.warning(
            "Torneo %r: %d coincidencias exactas, ambiguo. IDs: %s",
            name,
            len(exact),
            [n.get("id") for n in exact],
        )
        return None
    return exact[0]["id"]


# ---------------------------------------------------------------------------
# Acumulacion y volcado a BD
# ---------------------------------------------------------------------------

def accumulate_teams(
    series_nodes,
    teams_by_grid: dict[int, dict[str, Any]],
) -> None:
    """Extrae equipos de los nodos Series, deduplicando por grid_id."""
    for series in series_nodes:
        for tp in series.get("teams") or []:
            base = (tp or {}).get("baseInfo") or {}
            tid = base.get("id")
            if tid is None:
                continue
            teams_by_grid.setdefault(
                int(tid),
                {
                    "grid_id": int(tid),
                    "name": base.get("name"),
                    "tag": base.get("nameShortened"),
                },
            )


def accumulate_players(
    client: GridGraphQLClient,
    teams_by_grid: dict[int, dict[str, Any]],
    players_by_grid: dict[int, dict[str, Any]],
) -> None:
    """Para cada equipo descubierto, consulta sus jugadores directamente.

    Usamos el team_grid_id por el que consultamos (no Player.team.id) para
    evitar asociaciones erroneas si un jugador cambio de equipo recientemente.
    """
    for team_grid_id in teams_by_grid:
        for p in _paginate(client, PLAYERS_BY_TEAM, "players",
                           {"teamId": str(team_grid_id)}):
            pid = p.get("id")
            if pid is None:
                continue
            roles = p.get("roles") or []
            raw_roles = [r.get("name") for r in roles if r.get("name")]
            role = normalize_role(raw_roles[0]) if raw_roles else None
            players_by_grid.setdefault(
                int(pid),
                {
                    "grid_id": int(pid),
                    "nickname": p.get("nickname"),
                    "team_grid_id": team_grid_id,   # equipo por el que consultamos
                    "role": role,
                },
            )


def write_to_db(
    teams_by_grid: dict[int, dict[str, Any]],
    players_by_grid: dict[int, dict[str, Any]],
) -> tuple[int, int]:
    """Inserta teams y players de forma idempotente. Equipos primero por FK.

    Devuelve (n_teams_nuevos, n_players_nuevos).
    """
    teams_new = players_new = 0
    with get_conn() as conn:
        team_grid_to_local: dict[int, int] = {}
        for t in teams_by_grid.values():
            local_id, is_new = ensure_team(
                conn, grid_id=t["grid_id"], name=t["name"], tag=t["tag"],
            )
            team_grid_to_local[t["grid_id"]] = local_id
            teams_new += is_new

        for p in players_by_grid.values():
            team_local = team_grid_to_local.get(p["team_grid_id"])
            _, is_new = ensure_player(
                conn,
                grid_id=p["grid_id"],
                nickname=p["nickname"],
                team_local_id=team_local,
                role=p.get("role"),
            )
            players_new += is_new

        conn.commit()

    return teams_new, players_new


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    names = load_tournament_names()
    if not names:
        log.info(
            "config/tournaments.yaml no tiene torneos. Anade alguno y relanza."
        )
        return 0

    log.info("Torneos a procesar: %s", names)
    client = build_client()

    teams_by_grid: dict[int, dict[str, Any]] = {}
    players_by_grid: dict[int, dict[str, Any]] = {}

    for name in names:
        try:
            tid = resolve_tournament_id(client, name)
        except GridError as e:
            log.error("GraphQL error resolviendo torneo %r: %s", name, e)
            continue
        if not tid:
            continue
        log.info("Torneo %r -> id %s. Descubriendo equipos...", name, tid)
        try:
            accumulate_teams(
                _paginate(client, SERIES_BY_TOURNAMENTS, "allSeries", {"tid": tid}),
                teams_by_grid,
            )
        except GridError as e:
            log.error("GraphQL error paginando series de %r: %s", name, e)
            continue

    log.info("Equipos acumulados (deduplicados): %d", len(teams_by_grid))
    log.info("Consultando jugadores por equipo...")

    try:
        accumulate_players(client, teams_by_grid, players_by_grid)
    except GridError as e:
        log.error("GraphQL error consultando jugadores: %s", e)

    log.info("Jugadores acumulados (deduplicados): %d", len(players_by_grid))

    teams_new, players_new = write_to_db(teams_by_grid, players_by_grid)

    log.info(
        "Equipos: %d procesados, %d nuevos.",
        len(teams_by_grid), teams_new,
    )
    log.info(
        "Jugadores: %d procesados, %d nuevos.",
        len(players_by_grid), players_new,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
