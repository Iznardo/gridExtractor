"""SoloQ verification runner: extract + inspect, without the DB.

Run:  python -m src.riot.soloq_run --since YYYY-MM-DD [--account "X#Y"] [--limit N]

Flow:
1. Read the accounts in config/soloq_accounts.yaml and resolve their PUUIDs
   (cached in data/riot/accounts/).
2. List Ranked Solo/Duo match ids (queue=420) since --since.
3. Deduplicate the union across accounts: if two tracked accounts share a match,
   it is processed once with the full set of PUUIDs (same model the phase-2
   persistence uses).
4. Per match: detail + timeline (cached in data/riot/matches/), extract_match,
   write to data/riot/extracted/{matchId}.json, and a readable summary on screen
   for manual verification.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .cache import ACCOUNTS_DIR, EXTRACTED_DIR, fetch_match_cached, fetch_timeline_cached
from .client import RiotClient, RiotError
from .endpoints import RANKED_SOLO_QUEUE, get_match_ids
from .extract import extract_match
from .resolve_run import probe_match_regions, resolve_account

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "soloq_accounts.yaml"

log = logging.getLogger("riot")


def resolve_account_cached(client: RiotClient, riot_id: str) -> dict | None:
    path = ACCOUNTS_DIR / f"{riot_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    account = resolve_account(client, riot_id)
    if account is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(account, ensure_ascii=False))
    return account


def match_sort_key(match_id: str) -> int:
    """The match id's number, for sorting newest to oldest."""
    try:
        return int(match_id.split("_", 1)[1])
    except (IndexError, ValueError):
        return 0


def summary_line(extract: dict, player: dict) -> str:
    creation_ms = extract.get("game_creation") or 0
    date = datetime.fromtimestamp(creation_ms / 1000, tz=timezone.utc)
    kda = f"{player.get('kills')}/{player.get('deaths')}/{player.get('assists')}"
    result = "WIN " if player.get("win") else "LOSS"
    n_items = len(player.get("build_path") or [])
    return (f"{extract.get('match_id')}  {date:%Y-%m-%d %H:%M}  "
            f"{player.get('riot_id')}  {player.get('champion_name'):<12} "
            f"{player.get('team_position') or '?':<7} {result} {kda:<8} "
            f"cs {player.get('cs'):<3}  skill {player.get('skill_order') or '-'}  "
            f"build {n_items} events")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Extract SoloQ matches (queue 420) for the tracked accounts."
    )
    parser.add_argument("--since", metavar="YYYY-MM-DD", required=True,
                        help="Only matches from this date (UTC).")
    parser.add_argument("--account", default=None,
                        help="Process only this Riot ID from the YAML.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap on matches to process (the most recent ones).")
    args = parser.parse_args()

    start_time = int(
        datetime.strptime(args.since, "%Y-%m-%d")
        .replace(tzinfo=timezone.utc).timestamp()
    )

    config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    accounts = config.get("accounts") or []
    if args.account:
        accounts = [a for a in accounts if a.get("riot_id") == args.account]
    if not accounts:
        log.error("No accounts to process (check %s / --account).", CONFIG_PATH)
        return 1

    client = RiotClient()

    # 1-2. Resolve puuids and list match ids per account.
    tracked_puuids: set[str] = set()
    all_match_ids: set[str] = set()
    for entry in accounts:
        riot_id = entry.get("riot_id")
        account = resolve_account_cached(client, riot_id)
        if account is None:
            log.warning("Account not found in Account-V1: %s — skip.", riot_id)
            continue
        puuid = account["puuid"]
        tracked_puuids.add(puuid)

        region = entry.get("region")
        if not region:
            found = probe_match_regions(client, puuid)
            if not found:
                log.warning("%s: no matches in any region — skip.", riot_id)
                continue
            region = max(found, key=lambda r: match_sort_key(found[r]))
            log.warning("%s: region autodetected '%s' — set it in %s.",
                        riot_id, region, CONFIG_PATH.name)

        ids = get_match_ids(client, region, puuid,
                            queue=RANKED_SOLO_QUEUE, start_time=start_time)
        log.info("%s (%s): %d soloq matches since %s.",
                 riot_id, region, len(ids), args.since)
        all_match_ids.update(ids)

    # 3. Deduplicated union, newest to oldest.
    match_ids = sorted(all_match_ids, key=match_sort_key, reverse=True)
    if args.limit is not None:
        match_ids = match_ids[: args.limit]
    log.info("Total to process: %d matches (deduplicated union).", len(match_ids))

    # 4. Download, extract and dump.
    downloaded = cached = extracted = errors = 0
    for match_id in match_ids:
        try:
            match, m_cached = fetch_match_cached(client, match_id)
            timeline, t_cached = fetch_timeline_cached(client, match_id)
        except RiotError as e:
            log.error("RiotError on %s: %s", match_id, e)
            errors += 1
            continue
        if m_cached and t_cached:
            cached += 1
        else:
            downloaded += 1
        if match is None:
            log.warning("%s: detail unavailable (404) — skip.", match_id)
            continue
        if timeline is None:
            log.warning("%s: timeline unavailable (404) — no build/skills.", match_id)

        result = extract_match(match, timeline, tracked_puuids)
        if result is None:
            log.warning("%s: no tracked puuid in the match — skip.", match_id)
            continue
        EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
        (EXTRACTED_DIR / f"{match_id}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2)
        )
        extracted += 1
        for player in result["players"]:
            print(summary_line(result, player))

    log.info("Done. listed=%d downloaded=%d from_cache=%d extracted=%d errors=%d",
             len(match_ids), downloaded, cached, extracted, errors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
