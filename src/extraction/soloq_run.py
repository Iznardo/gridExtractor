"""Entry point for the SoloQ extractor (phase 2: DB persistence).

Run:  python -m src.extraction.soloq_run --since YYYY-MM-DD [--limit N]

Flow:
1. Refresh champions from Data Dragon (cheap; avoids losing picks when a new
   champion is released).
2. Load tracked accounts from the accounts table (populated by
   src/riot/accounts_sync.py).
3. List Ranked Solo/Duo match ids (queue 420) per region since --since,
   deduplicating across accounts.
4. Filter against the DB by riot_api_id BEFORE downloading anything.
5. Insert each match in its own transaction (games + picks). Remakes are
   skipped. No on-disk cache: the DB is the idempotency layer.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.db.conn import get_conn
from src.riot.client import RiotClient, RiotError
from src.riot.endpoints import RANKED_SOLO_QUEUE, get_match_ids
from src.riot.routing import match_sort_key

from .soloq import (
    ChampionIds,
    filter_new_match_ids,
    load_tracked_accounts,
    process_match,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger("extraction")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Extract soloq from the Riot API into the database."
    )
    parser.add_argument("--since", metavar="YYYY-MM-DD", required=True,
                        help="Only matches from this date (UTC).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap on new matches to process.")
    args = parser.parse_args()

    start_time = int(
        datetime.strptime(args.since, "%Y-%m-%d")
        .replace(tzinfo=timezone.utc).timestamp()
    )

    client = RiotClient()
    stats: Counter[str] = Counter()

    with get_conn() as conn:
        tracked = load_tracked_accounts(conn)
        if not tracked:
            log.error("The accounts table is empty — run "
                      "`python -m src.riot.accounts_sync` first.")
            return 1
        log.info("Tracked accounts: %d.", len(tracked))

        champions = ChampionIds(conn)

        # Match ids per region, deduplicated union across accounts.
        by_region: dict[str, list] = defaultdict(list)
        for account in tracked.values():
            by_region[account.region].append(account)
        all_ids: set[str] = set()
        for region, accounts in by_region.items():
            for account in accounts:
                ids = get_match_ids(client, region, account.puuid,
                                    queue=RANKED_SOLO_QUEUE,
                                    start_time=start_time)
                log.info("puuid %s... (%s): %d matches since %s.",
                         account.puuid[:12], region, len(ids), args.since)
                all_ids.update(ids)

        match_ids = sorted(all_ids, key=match_sort_key, reverse=True)
        new_ids = filter_new_match_ids(conn, match_ids)
        stats["already_in_db"] = len(match_ids) - len(new_ids)
        if args.limit is not None:
            new_ids = new_ids[: args.limit]
        log.info("%d matches listed, %d already in DB, %d to process.",
                 len(match_ids), stats["already_in_db"], len(new_ids))

        for match_id in new_ids:
            try:
                stats[process_match(client, conn, match_id, tracked, champions)] += 1
                conn.commit()
            except RiotError as e:
                log.error("RiotError on %s: %s", match_id, e)
                conn.rollback()
                stats["errors"] += 1
            except Exception:
                conn.rollback()
                raise

    log.info("SoloQ extraction complete. inserted=%d remakes=%d "
             "already_in_db=%d no_detail=%d no_tracked=%d dup=%d errors=%d",
             stats["inserted"], stats["remake"], stats["already_in_db"],
             stats["no_detail"], stats["no_tracked"], stats["dup"],
             stats["errors"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
