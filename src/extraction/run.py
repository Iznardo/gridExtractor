"""Entry point del extractor de partidos oficiales.

Lanzar:  python -m src.extraction.run [--since YYYY-MM-DD]

Opciones:
    --since YYYY-MM-DD   Solo procesar series con startTimeScheduled >= esa fecha.
                         Sin este flag se procesan todas las series del torneo
                         (la idempotencia se encarga de saltar las ya en BD).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from grid_minion import GridError, GridGraphQLClient, GridRestClient

from src.common.champions import build_lookup, ensure_loaded
from src.db.conn import get_conn
from src.discovery.run import build_client as build_graphql_client
from src.discovery.run import load_tournament_names, resolve_tournament_id

from .official import RoleCache, RunStats, iter_official_series, process_series

REPO_ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger("extraction")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Extrae partidos oficiales de GRID y los vuelca a la BD."
    )
    parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        default=None,
        help="Solo procesar series con startTimeScheduled >= esta fecha.",
    )
    args = parser.parse_args()
    since_iso = f"{args.since}T00:00:00Z" if args.since else None

    names = load_tournament_names()
    if not names:
        log.info("config/tournaments.yaml no tiene torneos. Añade alguno y relanza.")
        return 0

    log.info("Torneos a procesar: %s", names)

    api_key = os.environ.get("GRID_API_KEY")
    if not api_key:
        log.error("Falta GRID_API_KEY en el entorno (.env).")
        return 1

    client_gql  = build_graphql_client()
    client_rest = GridRestClient(api_key=api_key)

    # Resolver IDs de torneos
    tournament_ids: list[str] = []
    for name in names:
        try:
            tid = resolve_tournament_id(client_gql, name)
        except GridError as e:
            log.error("Error resolviendo torneo %r: %s", name, e)
            continue
        if tid:
            tournament_ids.append(tid)

    if not tournament_ids:
        log.error("No se resolvio ningun torneo. Revisa los nombres en tournaments.yaml.")
        return 1

    totals = RunStats()

    with get_conn() as conn:
        # Bootstrap: cargar tabla champions si esta vacia
        ensure_loaded(conn)
        champ_lookup = build_lookup(conn)
        log.info("Champions cargados: %d en lookup.", len(champ_lookup) // 2)

        role_cache = RoleCache(client_gql)

        for series_node in iter_official_series(client_gql, tournament_ids, since_iso):
            try:
                r = process_series(
                    client_rest, client_gql, conn,
                    series_node, role_cache, champ_lookup,
                )
                totals.add(r)
                conn.commit()
            except GridError as e:
                log.error("GridError en serie %s: %s", series_node.get("id"), e)
                totals.errors += 1

    log.info("Extraccion completada. %s", totals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
