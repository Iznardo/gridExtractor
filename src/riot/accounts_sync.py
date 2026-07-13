"""Sync the accounts in config/soloq_accounts.yaml into the `accounts` table.

Run:  python -m src.riot.accounts_sync

For each YAML entry (riot_id, player, region):
- `player` must be the exact name in the `players` table (players come from GRID
  discovery; they are not created here). No player or no DB match -> WARNING and
  skip.
- Resolve the PUUID via Account-V1. The riot_id is used only to resolve: in the
  DB the only identity is the puuid (Riot IDs change).
- Region null -> autodetect by probing Match-V5, with a warning.
- The YAML is the source of truth for an existing puuid too: if `player` or
  `region` were edited since the last sync, the DB row is updated (and
  reported as `updated`), not silently left stale.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.db.conn import get_conn

from .client import RiotClient, RiotError
from .resolve_run import probe_match_regions, resolve_account
from .routing import match_sort_key

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "soloq_accounts.yaml"

log = logging.getLogger("riot")


def player_id_by_name(conn, name: str) -> int | None:
    """Find a player tolerating casing differences and team-tag prefixes.

    Priority:
    1. Case-insensitive exact: "Vladi" == "vladi".
    2. Input is a suffix after a space: "Vladi" matches "BDS Vladi".
    On ambiguity (multiple candidates) it warns and returns None.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name FROM players WHERE LOWER(name) = LOWER(%s)",
            (name,),
        )
        rows = cur.fetchall()
        if len(rows) == 1:
            if rows[0][1] != name:
                log.info("Name %r resolved as %r (casing).", name, rows[0][1])
            return rows[0][0]
        if len(rows) > 1:
            log.warning("Name %r ambiguous (%d matches) — use the exact name "
                        "in player:. Skip.", name, len(rows))
            return None

        # Fallback: input is a suffix after a space ("T1 Faker" -> "Faker").
        cur.execute(
            "SELECT id, name FROM players WHERE LOWER(name) LIKE '% ' || LOWER(%s)",
            (name,),
        )
        rows = cur.fetchall()
        if len(rows) == 1:
            log.info("Name %r resolved as %r (suffix with team tag).",
                     name, rows[0][1])
            return rows[0][0]
        if len(rows) > 1:
            candidates = [r[1] for r in rows]
            log.warning("Name %r ambiguous with suffix %s — use the exact name "
                        "in player:. Skip.", name, candidates)
            return None

        return None


def sync_account_row(conn, player_id: int, region: str, puuid: str) -> str:
    """Insert the account, or update it if the YAML's player/region changed.

    Returns 'new' / 'updated' / 'existing'.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT player_id, region FROM accounts WHERE puuid = %s",
            (puuid,),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO accounts (player_id, region, puuid) "
                "VALUES (%s, %s, %s)",
                (player_id, region, puuid),
            )
            return "new"

        old_player_id, old_region = row
        if (old_player_id, old_region) == (player_id, region):
            return "existing"

        cur.execute(
            "UPDATE accounts SET player_id = %s, region = %s WHERE puuid = %s",
            (player_id, region, puuid),
        )
        log.warning(
            "puuid %s...: updated from the YAML (player_id %s -> %s, "
            "region %s -> %s).",
            puuid[:12], old_player_id, player_id, old_region, region,
        )
        return "updated"


def sync_account(client: RiotClient, conn, entry: dict) -> str:
    """Process one YAML entry. Returns 'new'/'updated'/'existing'/'skipped'."""
    riot_id = entry.get("riot_id")
    player_name = entry.get("player")
    if not player_name:
        log.warning("%s: no 'player' in the YAML — fill it with the exact name "
                    "from the players table. Skip.", riot_id)
        return "skipped"

    player_id = player_id_by_name(conn, player_name)
    if player_id is None:
        log.warning("%s: player %r not found in players "
                    "(discovery pending, typo, or ambiguous?). Skip.",
                    riot_id, player_name)
        return "skipped"

    account = resolve_account(client, riot_id)
    if account is None:
        log.warning("%s: Riot ID not found in Account-V1. Skip.", riot_id)
        return "skipped"
    puuid = account["puuid"]

    region = entry.get("region")
    if not region:
        found = probe_match_regions(client, puuid)
        if not found:
            log.warning("%s: no matches in any region — cannot autodetect. "
                        "Set 'region' in the YAML. Skip.", riot_id)
            return "skipped"
        region = max(found, key=lambda r: match_sort_key(found[r]))
        log.warning("%s: region autodetected '%s' — set it in %s.",
                    riot_id, region, CONFIG_PATH.name)

    status = sync_account_row(conn, player_id, region, puuid)
    log.info("%s -> player %r (id=%d), region=%s, puuid=%s... [%s]",
             riot_id, player_name, player_id, region, puuid[:12],
             status.upper())
    return status


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    accounts = config.get("accounts") or []
    if not accounts:
        log.error("No accounts in %s.", CONFIG_PATH)
        return 1

    client = RiotClient()
    results = {"new": 0, "updated": 0, "existing": 0, "skipped": 0}
    with get_conn() as conn:
        for entry in accounts:
            try:
                results[sync_account(client, conn, entry)] += 1
            except RiotError as e:
                log.error("RiotError on %s: %s", entry.get("riot_id"), e)
                results["skipped"] += 1
        conn.commit()

    log.info("Sync complete: %d new, %d updated, %d existing, %d skipped.",
             results["new"], results["updated"], results["existing"],
             results["skipped"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
