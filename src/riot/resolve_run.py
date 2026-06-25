"""Utility: Riot ID -> PUUID (+ detection of the region played in).

Run:  python -m src.riot.resolve_run "Byron Love#1v9" [--region europe]

- Resolves the PUUID via Account-V1 and prints the canonical gameName/tagLine.
- Without --region, tries europe -> americas -> asia (Account-V1 is global, any
  cluster resolves).
- Also probes the 4 Match-V5 regions by requesting 1 match id in each, to find
  where the account plays (the platform comes from the id prefix).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from .client import RiotClient, RiotError
from .endpoints import get_account_by_riot_id
from .routing import REGIONS

REPO_ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger("riot")

_ACCOUNT_CLUSTERS = ("europe", "americas", "asia")


def parse_riot_id(riot_id: str) -> tuple[str, str]:
    if "#" not in riot_id:
        raise ValueError(f"Invalid Riot ID (missing '#'): {riot_id!r}")
    game_name, tag_line = riot_id.rsplit("#", 1)
    return game_name.strip(), tag_line.strip()


def resolve_account(
    client: RiotClient, riot_id: str, region: str | None = None
) -> dict | None:
    game_name, tag_line = parse_riot_id(riot_id)
    clusters = (region,) if region else _ACCOUNT_CLUSTERS
    for cluster in clusters:
        account = get_account_by_riot_id(client, cluster, game_name, tag_line)
        if account is not None:
            return account
    return None


def probe_match_regions(client: RiotClient, puuid: str) -> dict[str, str]:
    """region -> most recent match id, only for regions with matches."""
    found = {}
    for region in REGIONS:
        page = client.get(
            region,
            f"/lol/match/v5/matches/by-puuid/{puuid}/ids",
            {"start": 0, "count": 1},
        )
        if page:
            found[region] = page[0]
    return found


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Resolve a Riot ID to a PUUID.")
    parser.add_argument("riot_id", help='Riot ID in "Name#TAG" format.')
    parser.add_argument("--region", choices=_ACCOUNT_CLUSTERS, default=None,
                        help="Regional cluster for Account-V1 (optional).")
    args = parser.parse_args()

    client = RiotClient()
    try:
        account = resolve_account(client, args.riot_id, args.region)
    except RiotError as e:
        log.error("%s", e)
        return 1
    if account is None:
        log.error("Riot ID not found: %s", args.riot_id)
        return 1

    print(f"riot_id : {account.get('gameName')}#{account.get('tagLine')}")
    print(f"puuid   : {account.get('puuid')}")

    regions = probe_match_regions(client, account["puuid"])
    if not regions:
        print("regions : no matches in any region (empty matchlist)")
    for region, match_id in regions.items():
        platform = match_id.split("_", 1)[0]
        print(f"regions : {region} (platform {platform}, latest {match_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
