"""Entry point for the official-game extractor.

Run:  python -m src.extraction.run [--since YYYY-MM-DD]

Options:
    --since YYYY-MM-DD   Only process series with startTimeScheduled >= that date.
                         Without it, all of the tournament's series are processed
                         (idempotency skips the ones already in the DB).
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
from src.discovery.run import load_tournament_entries, resolve_tournament

from ._persistence import RoleCache, RunStats
from .official import iter_official_series, process_series

REPO_ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger("extraction")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Extract official games from GRID into the database."
    )
    parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        default=None,
        help="Only process series with startTimeScheduled >= this date.",
    )
    args = parser.parse_args()
    since_iso = f"{args.since}T00:00:00Z" if args.since else None

    entries = load_tournament_entries()
    if not entries:
        log.info("config/tournaments.yaml has no tournaments. Add some and rerun.")
        return 0

    log.info("Tournaments to process: %s", entries)

    api_key = os.environ.get("GRID_API_KEY")
    if not api_key:
        log.error("GRID_API_KEY missing from the environment (.env).")
        return 1

    client_gql  = build_graphql_client()
    client_rest = GridRestClient(api_key=api_key)

    tournament_ids: list[str] = []
    for entry in entries:
        try:
            tid = resolve_tournament(client_gql, entry)
        except GridError as e:
            log.error("Error resolving tournament %r: %s", entry, e)
            continue
        if tid:
            tournament_ids.append(tid)

    if not tournament_ids:
        log.error("No tournament resolved. Check the entries in tournaments.yaml.")
        return 1

    totals = RunStats()

    with get_conn() as conn:
        # Refresh the champion catalog every run (cheap and idempotent) so games
        # with a newly added champion are not lost. Fall back to whatever is in
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

        # Global chronological order across tournaments (not just within each
        # one) so positional reconciliation never applies a stale roster.
        # startTimeScheduled is ISO 8601 -> lexicographic sort is valid.
        all_series = sorted(
            iter_official_series(client_gql, tournament_ids, since_iso),
            key=lambda s: s.get("startTimeScheduled") or "",
        )
        log.info("Series to process (global chronological order): %d",
                 len(all_series))

        for series_node in all_series:
            try:
                r = process_series(
                    client_rest, client_gql, conn,
                    series_node, role_cache, champ_lookup,
                )
                totals.add(r)
                conn.commit()
            except GridError as e:
                log.error("GridError on series %s: %s", series_node.get("id"), e)
                totals.errors += 1

    log.info("Extraction complete. %s", totals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
