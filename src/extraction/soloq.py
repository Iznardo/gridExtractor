"""SoloQ extraction: Riot API -> DB (games + picks).

Unlike official/scrims there is no grid-minion: the API layer lives in
src/riot/ (client, endpoints, extract_match). This module handles persistence:

- Idempotency by `games.riot_api_id` (full matchId, "EUW1_..."): filtered
  against the DB BEFORE downloading anything.
- One game = one games row (draft_id NULL: the drafts table is exclusive to
  official/scrims) + one picks row per tracked account present. All 10
  participants, bans included, are stored in games.stats.
- Remakes are not inserted.
- No roster reconciliation (official only) and no auto-discovery: accounts
  already link to existing players via accounts_sync.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg

from src.common.champions import refresh_champions
from src.riot.client import RiotClient
from src.riot.endpoints import get_match, get_match_timeline
from src.riot.extract import extract_match, is_remake

log = logging.getLogger("extraction")


@dataclass
class TrackedAccount:
    account_id: int
    player_id: int
    puuid: str
    region: str


# ---------------------------------------------------------------------------
# Accounts and idempotency
# ---------------------------------------------------------------------------

def load_tracked_accounts(conn: psycopg.Connection) -> dict[str, TrackedAccount]:
    """{puuid: TrackedAccount} for every account in the DB."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, player_id, puuid, region FROM accounts")
        return {
            puuid.strip(): TrackedAccount(account_id, player_id, puuid.strip(), region)
            for account_id, player_id, puuid, region in cur.fetchall()
        }


def filter_new_match_ids(
    conn: psycopg.Connection, match_ids: list[str]
) -> list[str]:
    """Drop match ids already inserted, without spending requests."""
    if not match_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT riot_api_id FROM games WHERE riot_api_id = ANY(%s)",
            (match_ids,),
        )
        existing = {row[0] for row in cur.fetchall()}
    return [m for m in match_ids if m not in existing]


# ---------------------------------------------------------------------------
# Mapping: extract -> rows
# ---------------------------------------------------------------------------

# picks.stats key contract. kills/deaths/assists/gold/cs match the GRID picks
# (_persistence.insert_picks); the rest are the contract that official/scrims
# will fill from GRID in the future builds phase.
def pick_stats_from_player(player: dict) -> dict:
    return {
        "kills": player.get("kills"),
        "deaths": player.get("deaths"),
        "assists": player.get("assists"),
        "gold": player.get("gold"),
        "cs": player.get("cs"),
        "champ_level": player.get("champ_level"),
        "vision_score": player.get("vision_score"),
        "team_position": player.get("team_position"),
        "summoner_spells": player.get("summoner_spells"),
        "final_items": player.get("final_items"),
        "runes": player.get("runes"),
        "build_path": player.get("build_path"),
        "skill_order": player.get("skill_order"),
    }


def game_stats_from_extract(extract: dict) -> dict:
    return {
        "queue_id": extract.get("queue_id"),
        "platform": extract.get("platform"),
        "game_duration_s": extract.get("game_duration_s"),
        "game_creation_ms": extract.get("game_creation"),
        "bans": extract.get("bans"),
        "participants": extract.get("participants"),
    }


def insert_soloq_game(conn: psycopg.Connection, extract: dict) -> int | None:
    """Insert the games row. Return games.id, or None if it already existed."""
    creation_ms = extract.get("game_creation") or 0
    game_date = datetime.fromtimestamp(creation_ms / 1000, tz=timezone.utc).date()
    winner = extract.get("winner")
    result = winner if winner in ("BLUE", "RED") else "NONE"

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO games (date, version, game_type, tournament,
                               team1_id, team2_id, result, draft_id,
                               riot_api_id, stats, created_at, updated_at)
            VALUES (%s, %s, 'SOLOQ', 'SOLOQ',
                    NULL, NULL, %s, NULL,
                    %s, %s, now(), now())
            ON CONFLICT (riot_api_id) DO NOTHING
            RETURNING id
            """,
            (
                game_date, extract.get("game_version"), result,
                extract.get("match_id"),
                json.dumps(game_stats_from_extract(extract)),
            ),
        )
        row = cur.fetchone()
        return row[0] if row else None


def insert_soloq_picks(
    conn: psycopg.Connection,
    game_id: int,
    extract: dict,
    tracked: dict[str, TrackedAccount],
    known_champ_ids: set[int],
) -> int:
    """One picks row per tracked player present. Return rows inserted."""
    inserted = 0
    with conn.cursor() as cur:
        for player in extract.get("players", []):
            account = tracked.get(player.get("puuid"))
            if account is None:
                continue
            champ_id = player.get("champion_id")
            if champ_id not in known_champ_ids:
                log.warning("%s: champion_id %s not in champions — skip pick.",
                            extract.get("match_id"), champ_id)
                continue
            cur.execute(
                """
                INSERT INTO picks
                    (player_id, account_id, game_id, champ_id,
                     side, result, pick_order, stats)
                VALUES (%s, %s, %s, %s, %s, %s, NULL, %s)
                """,
                (
                    account.player_id, account.account_id, game_id, champ_id,
                    player.get("team_side"), bool(player.get("win")),
                    json.dumps(pick_stats_from_player(player)),
                ),
            )
            inserted += 1
    return inserted


# ---------------------------------------------------------------------------
# Single-match processing
# ---------------------------------------------------------------------------

class ChampionIds:
    """Set of champion ids in the DB, with at most one Data Dragon refresh per
    run if a new champion appears."""

    def __init__(self, conn: psycopg.Connection):
        self._conn = conn
        self._ids = self._load()
        self._refreshed = False

    def _load(self) -> set[int]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT id FROM champions")
            return {row[0] for row in cur.fetchall()}

    def ensure(self, needed: set[int]) -> set[int]:
        missing = needed - self._ids
        if missing and not self._refreshed:
            log.info("Unknown champion ids %s — refreshing Data Dragon.",
                     sorted(missing))
            refresh_champions(self._conn)
            self._refreshed = True
            self._ids = self._load()
        return self._ids


def process_match(
    client: RiotClient,
    conn: psycopg.Connection,
    match_id: str,
    tracked: dict[str, TrackedAccount],
    champions: ChampionIds,
) -> str:
    """Download, extract and insert one match. Returns a status for stats:
    'inserted' | 'remake' | 'no_detail' | 'no_tracked' | 'dup'."""
    match = get_match(client, match_id)
    if match is None:
        log.warning("%s: detail unavailable (404) — skip.", match_id)
        return "no_detail"
    if is_remake(match):
        log.info("%s: remake — not inserted.", match_id)
        return "remake"

    timeline = get_match_timeline(client, match_id)
    if timeline is None:
        log.warning("%s: timeline unavailable (404) — pick without build/skills.",
                    match_id)

    extract = extract_match(match, timeline, set(tracked))
    if extract is None:
        log.warning("%s: no tracked puuid in the match — skip.", match_id)
        return "no_tracked"

    # Resolve champions BEFORE opening the inserts: refresh_champions commits
    # internally and must not split the match transaction.
    needed = {p.get("champion_id") for p in extract["players"]}
    known_champ_ids = champions.ensure(needed)

    game_id = insert_soloq_game(conn, extract)
    if game_id is None:
        log.info("%s: already in DB (conflict) — skip.", match_id)
        return "dup"
    n_picks = insert_soloq_picks(conn, game_id, extract, tracked, known_champ_ids)
    log.info("%s: inserted (game_id=%d, %d picks).", match_id, game_id, n_picks)
    return "inserted"
