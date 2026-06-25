"""Backfill games.stats.meta.duration_s for OFFICIAL and SCRIM games.

Downloads only the (lightweight) Riot Summary per game; failing that, Tencent
Details (LPL). Updates the field via JSONB path without touching the rest of
the record.

Run:
    python -m src.extraction.patch_duration [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from grid_minion import GridError, GridRestClient

from src.db.conn import get_conn
from src.extraction._persistence import _extract_duration_s, MidGameStatsObserver

REPO_ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("patch_duration")


def _fetch_duration_s(client: GridRestClient, series_id: int, game_number: int) -> float | None:
    """Get the duration from the Riot Summary, falling back to Tencent Details."""
    riot_summary = None
    tencent_raw = None

    try:
        riot_summary = client.get_riot_summary(str(series_id), game_number)
    except GridError as e:
        log.debug("Riot Summary unavailable for %d g%d: %s", series_id, game_number, e)

    if riot_summary is None:
        try:
            tencent_raw = client.get_tencent_details(str(series_id), game_number)
        except GridError as e:
            log.debug("Tencent Details unavailable for %d g%d: %s", series_id, game_number, e)

    # Empty MidGameStatsObserver as a placeholder (no midgame proxy, since we are
    # not reprocessing the full bundle — only the summary).
    return _extract_duration_s(riot_summary, tencent_raw, MidGameStatsObserver())


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Backfill duration_s on existing games.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be updated without touching the DB.")
    args = parser.parse_args()

    api_key = os.environ.get("GRID_API_KEY")
    if not api_key:
        log.error("GRID_API_KEY missing from .env.")
        return 1

    client = GridRestClient(api_key=api_key)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, grid_series_id, game_number, game_type
                FROM games
                WHERE game_type IN ('OFFICIAL', 'SCRIM')
                  AND grid_series_id IS NOT NULL
                  AND (stats->'meta'->>'duration_s') IS NULL
                ORDER BY date ASC, id ASC
            """)
            rows = cur.fetchall()

    total = len(rows)
    log.info("%d games without duration_s.", total)
    if total == 0:
        return 0

    updated = 0
    failed = 0

    with get_conn() as conn:
        for i, row in enumerate(rows, 1):
            game_id, series_id, game_number, game_type = row

            duration_s = _fetch_duration_s(client, series_id, game_number)

            if duration_s is None:
                log.warning("[%d/%d] %s series=%d g%d: no duration available, skip.",
                            i, total, game_type, series_id, game_number)
                failed += 1
                time.sleep(0.1)
                continue

            log.info("[%d/%d] %s series=%d g%d -> %.1fs",
                     i, total, game_type, series_id, game_number, duration_s)

            if not args.dry_run:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE games
                        SET stats = jsonb_set(
                                stats,
                                '{meta,duration_s}',
                                %s::jsonb
                            ),
                            updated_at = now()
                        WHERE id = %s
                    """, (json.dumps(round(duration_s, 1)), game_id))
                conn.commit()
                updated += 1
            else:
                updated += 1

            # Small pause to avoid hammering the GRID API.
            time.sleep(0.15)

    label = "would be updated" if args.dry_run else "updated"
    log.info("Done. %d games %s, %d without data.", updated, label, failed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
