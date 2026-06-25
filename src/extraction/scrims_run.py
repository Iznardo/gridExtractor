"""Entry point for the scrim extractor.

Run:  python -m src.extraction.scrims_run [--since YYYY-MM-DD]

Options:
    --since YYYY-MM-DD   Only process scrims with startTimeScheduled >= that
                         date. Without it, all PUBLISHED scrims accessible from
                         our GRID account are processed (idempotency skips the
                         ones already in the DB).

Unlike the official extractor, there is no config/tournaments.yaml and no team
filter: it iterates over every SCRIM-type series GRID exposes. Auto-discovery
creates new teams and players as in official games, but logs a WARNING on each
creation for manual auditing. Roster is never reconciled.
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
        description="Extract scrims from GRID into the database."
    )
    parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        default=None,
        help="Only process scrims with startTimeScheduled >= this date.",
    )
    args = parser.parse_args()
    since_iso = f"{args.since}T00:00:00Z" if args.since else None

    api_key = os.environ.get("GRID_API_KEY")
    if not api_key:
        log.error("GRID_API_KEY missing from the environment (.env).")
        return 1

    client_gql  = build_graphql_client()
    client_rest = GridRestClient(api_key=api_key)

    totals = RunStats()

    with get_conn() as conn:
        # Refresh champions every run (idempotent). Fall back to whatever is in
        # the DB if Data Dragon is unreachable.
        try:
            refresh_champions(conn)
        except Exception as e:
            log.warning("Could not refresh champions from Data Dragon "
                        "(%s); using what is in the DB.", e)
            ensure_loaded(conn)
        champ_lookup = build_lookup(conn)
        log.info("Champions loaded: %d in lookup.", len(champ_lookup) // 2)

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
                log.error("GridError on scrim %s: %s",
                          series_node.get("id"), e)
                totals.errors += 1

    log.info("Scrim extraction complete. %s", totals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
