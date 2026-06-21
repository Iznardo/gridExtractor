"""Entry point del extractor de scrims.

Lanzar:  python -m src.extraction.scrims_run [--since YYYY-MM-DD]

Opciones:
    --since YYYY-MM-DD   Solo procesar scrims con startTimeScheduled >= esa
                         fecha. Sin este flag se procesan TODAS las scrims
                         PUBLISHED accesibles desde nuestra cuenta de GRID
                         (la idempotencia se encarga de saltar las ya en BD).

A diferencia del extractor de oficiales, no hay config/tournaments.yaml ni
filtro por equipo: se itera sobre todas las series de tipo SCRIM expuestas
por GRID. El auto-discovery crea equipos y jugadores nuevos como en
oficiales, pero loguea WARNING en cada creacion para auditoria manual.
NO se reconcilia roster (CLAUDE.md §5.5).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from grid_minion import GridError, GridRestClient

from src.common.champions import build_lookup, ensure_loaded, refresh_champions
from src.db.conn import get_conn
from src.discovery.run import build_client as build_graphql_client

from ._persistence import RoleCache, RunStats
from .scrims import iter_scrim_series, process_scrim_series

REPO_ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger("extraction")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Extrae scrims de GRID y los vuelca a la BD."
    )
    parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        default=None,
        help="Solo procesar scrims con startTimeScheduled >= esta fecha.",
    )
    args = parser.parse_args()
    since_iso = f"{args.since}T00:00:00Z" if args.since else None

    api_key = os.environ.get("GRID_API_KEY")
    if not api_key:
        log.error("Falta GRID_API_KEY en el entorno (.env).")
        return 1

    client_gql  = build_graphql_client()
    client_rest = GridRestClient(api_key=api_key)

    totals = RunStats()

    with get_conn() as conn:
        # audit #3: refrescar champions en cada corrida (idempotente). Si Data
        # Dragon no responde, caer a lo que haya en BD.
        try:
            refresh_champions(conn)
        except Exception as e:
            log.warning("No se pudo refrescar champions desde Data Dragon "
                        "(%s); uso lo que haya en BD.", e)
            ensure_loaded(conn)
        champ_lookup = build_lookup(conn)
        log.info("Champions cargados: %d en lookup.", len(champ_lookup) // 2)

        role_cache = RoleCache(client_gql)

        for series_node in iter_scrim_series(client_gql, since_iso):
            try:
                r = process_scrim_series(
                    client_rest, client_gql, conn,
                    series_node, role_cache, champ_lookup,
                )
                totals.add(r)
                conn.commit()
            except GridError as e:
                log.error("GridError en scrim %s: %s",
                          series_node.get("id"), e)
                totals.errors += 1

    log.info("Extraccion de scrims completada. %s", totals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
