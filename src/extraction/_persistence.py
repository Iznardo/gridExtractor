"""Persistence helpers shared by the extractors (official and scrims).

Contains:
- INSERT functions for drafts/games/picks (parameterized by game_type).
- Mapping helpers (pick_order, champion, date, team side).
- Idempotency checks (game_in_db, series_fully_in_db).
- Shared classes: RoleCache (GRID role catalog), SeriesResult, RunStats.

This module does not import from official.py or scrims.py, to avoid cycles.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime

import psycopg
from grid_minion import (
    GridError,
    GridGraphQLClient,
    GridRestClient,
    extract_grid_game_state,
    group_riot_livestats_fragments,
    split_grid_series,
)
from grid_minion.sources import normalize_tencent_details
from grid_minion.observers import (
    BuildObserver,
    DraftObserver,
    GameEventProcessor,
    MidGameStatsObserver,
    ObjectiveKilledObserver,
    PostGameObserver,
    SoloKillObserver,
    TeamsObserver,
    WardsObserver,
)

from src.common.roles import normalize_role, role_from_riot_id
from src.db.reconcile import reconcile_player_roster
from src.db.upsert import ensure_player, ensure_team

from .queries import PLAYER_ROLES_BY_ID

log = logging.getLogger("extraction")


# ---------------------------------------------------------------------------
# Run summary stats
# ---------------------------------------------------------------------------

@dataclass
class SeriesResult:
    skipped: bool = False
    no_events: bool = False
    games_new: int = 0
    games_skipped: int = 0     # already in DB (idempotency, not an issue)
    games_discarded: int = 0   # bad data: empty draft, no winner, no participants
    errors: int = 0


@dataclass
class RunStats:
    series_skipped: int = 0
    series_no_events: int = 0
    series_processed: int = 0
    games_new: int = 0
    games_skipped: int = 0
    games_discarded: int = 0
    errors: int = 0

    def add(self, r: SeriesResult) -> None:
        if r.skipped:
            self.series_skipped += 1
        elif r.no_events:
            self.series_no_events += 1
        else:
            self.series_processed += 1
        self.games_new += r.games_new
        self.games_skipped += r.games_skipped
        self.games_discarded += r.games_discarded
        self.errors += r.errors

    def __str__(self) -> str:
        return (
            f"series: {self.series_processed} processed, "
            f"{self.series_skipped} skipped (already in DB), "
            f"{self.series_no_events} without data | "
            f"games: {self.games_new} new, "
            f"{self.games_skipped} skipped (already in DB), "
            f"{self.games_discarded} discarded (bad data), "
            f"{self.errors} errors"
        )


# ---------------------------------------------------------------------------
# GRID role catalog cache (one instance per run)
# ---------------------------------------------------------------------------

class RoleCache:
    """Caches Player.roles[].name (normalized) by grid_player_id.

    One GraphQL query per unique player in the run, not per game. Falls back to
    the riot_id ordering convention when GRID has no role.
    """

    def __init__(self, client: GridGraphQLClient) -> None:
        self._cache: dict[int, str | None] = {}
        self._client = client

    def role_for(self, grid_player_id: int, riot_id: int) -> str | None:
        if grid_player_id not in self._cache:
            try:
                data = self._client.query_central(
                    PLAYER_ROLES_BY_ID,
                    variables={"pid": str(grid_player_id)},
                )
                roles = ((data.get("player") or {}).get("roles") or [])
                raw = roles[0]["name"] if roles else None
                self._cache[grid_player_id] = normalize_role(raw)
            except GridError as e:
                log.warning("RoleCache: error querying player %d: %s",
                            grid_player_id, e)
                self._cache[grid_player_id] = None

        return self._cache[grid_player_id] or role_from_riot_id(riot_id)


# ---------------------------------------------------------------------------
# Idempotency: is a series/game already in the DB?
# ---------------------------------------------------------------------------

def count_games_in_db(conn: psycopg.Connection, grid_series_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM games WHERE grid_series_id = %s",
            (grid_series_id,),
        )
        return cur.fetchone()[0]


def game_in_db(conn: psycopg.Connection,
               grid_series_id: int, game_number: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM games WHERE grid_series_id = %s AND game_number = %s",
            (grid_series_id, game_number),
        )
        return cur.fetchone() is not None


def series_fully_in_db(
    conn: psycopg.Connection,
    grid_series_id: int,
    client_graphql: GridGraphQLClient,
    series_id: str,
) -> bool:
    """True if every finished game of the series is already in the DB.

    Calls get_series_state (lightweight GraphQL) and compares with the DB count.
    Returns False when undetermined (error), so nothing is skipped by mistake.
    """
    db_count = count_games_in_db(conn, grid_series_id)
    if db_count == 0:
        return False
    try:
        state = client_graphql.get_series_state(series_id)
        if not state:
            return False
        finished = sum(1 for g in (state.get("games") or []) if g.get("finished"))
        return db_count >= finished > 0
    except GridError as e:
        log.warning("series_fully_in_db: get_series_state %s failed: %s",
                    series_id, e)
        return False


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

# Global pick order in standard competitive LoL draft. fp.picks[i] and
# sp.picks[i] are each team's picks in chronological order; the global order
# (1-10) follows the fixed draft pattern.
#
# Phase 1 (6 picks, after 6 alternating bans):
#   FP1(1), SP1(2), SP2(3), FP2(4), FP3(5), SP3(6)
#
# Phase 2 (4 picks, after 4 alternating bans starting with SP):
#   SP4(7), FP4(8), FP5(9), SP5(10)
#
# pick_order=1 is the first pick of the draft (FP blind pick);
# pick_order=10 is the last (pure SP counterpick).
FP_PICK_ORDER = {0: 1, 1: 4, 2: 5, 3: 8, 4: 9}
SP_PICK_ORDER = {0: 2, 1: 3, 2: 6, 3: 7, 4: 10}


def pick_order_for(champion_name: str | None,
                   draft_data: dict,
                   grid_team_id: int | None,
                   champ_lookup: dict[str, int]) -> int | None:
    """Return the champion's global pick_order (1-10) in the draft.

    Compares by champion ID (not string) to avoid format mismatches between
    GRID ("LeeSin") and Riot ("Lee Sin"). Draft picks are dicts
    `{"name", "id"}` already normalized against Data Dragon, so the id comes
    straight from the dict.
    """
    if not champion_name or grid_team_id is None:
        return None

    champ_id = champ_lookup.get(champion_name)
    if champ_id is None:
        return None

    fp_team_id = draft_data["fp"].get("team_id")
    if fp_team_id is None:
        # FP team unknown: every participant would fall into the SP branch,
        # attributing the whole game to second-pick pick_orders it doesn't
        # actually have (decision 2026-07-13: no order at all is preferable
        # to a false one — the game is excluded from FP/SP and
        # blind/counter stats instead).
        return None

    fp_picks   = draft_data["fp"].get("picks") or []
    sp_picks   = draft_data["sp"].get("picks") or []

    if str(grid_team_id) == str(fp_team_id):
        picks_list = fp_picks
        order_map  = FP_PICK_ORDER
    else:
        picks_list = sp_picks
        order_map  = SP_PICK_ORDER

    for i, pick in enumerate(picks_list):
        if pick and pick.get("id") == champ_id:
            return order_map.get(i)
    return None


def parse_date(iso: str) -> date:
    """Return the DATE part of an ISO 8601 string."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()


def resolve_champ(champ_name: str | None,
                  champ_lookup: dict[str, int]) -> int | None:
    if not champ_name:
        return None
    cid = champ_lookup.get(champ_name)
    if cid is None:
        log.warning("Unknown champion: %r — champ_id NULL.", champ_name)
    return cid


# Draft placeholder used when a scrim's recorded draft cannot be trusted for
# the game actually played (blind pick, or a dodged draft left orphaned).
EMPTY_DRAFT: dict = {"fp": {}, "sp": {}}


def draft_champ_ids(draft_data: dict) -> set[int]:
    """Champion ids picked in the draft (fp+sp), ignoring gaps."""
    return {
        p["id"]
        for side in ("fp", "sp")
        for p in (draft_data.get(side) or {}).get("picks") or []
        if p and p.get("id") is not None
    }


def played_champ_ids(participants: list,
                     champ_lookup: dict[str, int]) -> set[int]:
    """Champion ids actually played, per participants (resolved by id)."""
    ids = {
        resolve_champ(p.champion_name, champ_lookup)
        for p in participants if p.champion_name
    }
    ids.discard(None)
    return ids


def draft_missing_reason_for(
    draft_data: dict,
    participants: list,
    champ_lookup: dict[str, int],
) -> str | None:
    """Whether the recorded draft is unusable for the game actually played.

    None means the draft is trustworthy (or there isn't enough evidence from
    participants to distinguish it from a real one). Only called when
    draft_found is already True — the no_draft_events case is handled by the
    caller before this.
    """
    known = [p for p in participants if p.champion_name]
    if len(known) != 10:
        # Not enough resolved champions to compare against — behave as
        # before (accept the recorded draft).
        return None
    drafted = draft_champ_ids(draft_data)
    if len(drafted) < 10:
        return "draft_partial"
    played = played_champ_ids(participants, champ_lookup)
    if drafted != played:
        return "draft_mismatch"
    return None


SMITE_ID = 11


def smite_suspect_sides(participants: list,
                        players_stats: dict) -> set[str]:
    """Sides whose riot_id ordering looks broken (picks.role tripwire).

    The role persisted per pick comes from the riot_id ordering convention
    (1/6=TOP .. 5/10=SUPPORT). Cheap internal signal to detect a shuffled
    order: the participant derived as JUNGLE must carry Smite. A side is
    suspect when its derived jungler verifiably does NOT carry Smite while
    another participant of the same side does. Without spell data (broken
    scrim with no summary) there is no signal — the convention is trusted.
    """
    by_side: dict[str, list] = {}
    for p in participants:
        by_side.setdefault(p.team_side, []).append(p)

    suspects: set[str] = set()
    for side, plist in by_side.items():
        has_smite: dict[int, bool] = {}
        for p in plist:
            spells = (players_stats.get(p.riot_id) or {}).get("summoner_spells")
            if spells:
                has_smite[p.riot_id] = SMITE_ID in spells
        jungler = next((p for p in plist
                        if role_from_riot_id(p.riot_id) == "JUNGLE"), None)
        if jungler is None or jungler.riot_id not in has_smite:
            continue
        others_with_smite = any(v for rid, v in has_smite.items()
                                if rid != jungler.riot_id)
        if not has_smite[jungler.riot_id] and others_with_smite:
            suspects.add(side)
    return suspects


# ---------------------------------------------------------------------------
# Persistence: draft, game, picks
# ---------------------------------------------------------------------------

def insert_draft(
    conn: psycopg.Connection,
    draft_data: dict,
    grid_team_id_to_local: dict[int, int],
    champ_lookup: dict[str, int],
) -> int:
    """Insert a drafts row and return its id."""
    fp = draft_data["fp"]
    sp = draft_data["sp"]

    def champ(entry):
        # Each pick/ban is {"name", "id"} already normalized (or None for a
        # skipped ban). Use the id directly; fall back to name lookup if the
        # library could not resolve it (id None).
        if not entry:
            return None
        if entry.get("id") is not None:
            return entry["id"]
        return resolve_champ(entry.get("name"), champ_lookup)

    fp_team_id_str = fp.get("team_id")
    fp_local = None
    if fp_team_id_str:
        fp_local = grid_team_id_to_local.get(int(fp_team_id_str))

    fp_picks = fp.get("picks") or []
    sp_picks = sp.get("picks") or []
    fp_bans  = fp.get("bans")  or []
    sp_bans  = sp.get("bans")  or []

    # Pad to 5 elements (may arrive incomplete in remakes).
    def pad(lst, n=5):
        return (list(lst) + [None] * n)[:n]

    fp_picks = pad(fp_picks)
    sp_picks = pad(sp_picks)
    fp_bans  = pad(fp_bans)
    sp_bans  = pad(sp_bans)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO drafts (
                first_pick_team_id,
                ban1,  ban2,  ban3,  ban4,  ban5,
                ban6,  ban7,  ban8,  ban9,  ban10,
                pick1, pick2, pick3, pick4, pick5,
                pick6, pick7, pick8, pick9, pick10
            ) VALUES (
                %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            RETURNING id
            """,
            (
                fp_local,
                champ(fp_bans[0]),  champ(fp_bans[1]),  champ(fp_bans[2]),
                champ(fp_bans[3]),  champ(fp_bans[4]),
                champ(sp_bans[0]),  champ(sp_bans[1]),  champ(sp_bans[2]),
                champ(sp_bans[3]),  champ(sp_bans[4]),
                champ(fp_picks[0]), champ(fp_picks[1]), champ(fp_picks[2]),
                champ(fp_picks[3]), champ(fp_picks[4]),
                champ(sp_picks[0]), champ(sp_picks[1]), champ(sp_picks[2]),
                champ(sp_picks[3]), champ(sp_picks[4]),
            ),
        )
        return cur.fetchone()[0]


def insert_game(
    conn: psycopg.Connection,
    *,
    series_node: dict,
    game_number: int,
    winner: str | None,
    version: str | None,
    team1_local: int | None,
    team2_local: int | None,
    draft_id: int | None,
    game_stats: dict,
    objs_data: dict,
    wards_data: list,
    solokills_data: list,
    game_type: str,
    tournament: str | None,
    duration_s: float | None = None,
) -> int | None:
    """Insert a games row. Return games.id, or None if it already existed.

    `game_type` must be 'OFFICIAL' or 'SCRIM'. `tournament` is the tournament
    name (root, for official games) or a placeholder ('SCRIM') for scrims.
    """
    game_date = parse_date(series_node["startTimeScheduled"])
    result    = winner if winner in ("BLUE", "RED") else "NONE"

    meta = dict(game_stats.get("meta", {}))
    if duration_s is not None:
        meta["duration_s"] = round(duration_s, 1)

    stats_json = {
        "meta":       meta,
        "objectives": objs_data,
        "wards":      wards_data,
        "solokills":  solokills_data,
    }

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO games (
                date, version, game_type, tournament,
                team1_id, team2_id, result,
                draft_id, grid_series_id, game_number,
                stats, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, now(), now()
            )
            ON CONFLICT (grid_series_id, game_number) DO NOTHING
            RETURNING id
            """,
            (
                game_date, version, game_type, tournament,
                team1_local, team2_local, result,
                draft_id,
                int(series_node["id"]), game_number,
                json.dumps(stats_json),
            ),
        )
        row = cur.fetchone()
        return row[0] if row else None


def insert_picks(
    conn: psycopg.Connection,
    *,
    game_id: int,
    winner: str | None,
    participants: list,
    player_grid_to_local: dict[int, int],
    game_stats: dict,
    champ_lookup: dict[str, int],
    draft_data: dict,
    suspect_sides: set[str],
    builds_data: dict[int, dict] | None = None,
    midgame_data: dict[int, dict] | None = None,
) -> None:
    """Insert 10 picks rows (one per participant).

    `builds_data`: output of `BuildObserver.get_builds()` — `{pid: {build_path, skill_order}}`.
    `midgame_data`: output of `MidGameStatsObserver.get_mid_game_stats()` — `{pid: {marks: {7: {...}, 14: {...}}}}`.
    Both may be None/empty when there was no riot_livestats.
    `suspect_sides`: from `smite_suspect_sides`, computed once by the caller
    (also used for roster reconciliation, so both stay consistent).

    `picks.role` = role played in THIS game, from the riot_id ordering
    convention. On a side flagged by the Smite tripwire the 5 picks go in with
    role NULL (we prefer a missing role over a false one).
    """
    players_stats = game_stats.get("players") or {}
    builds_data   = builds_data or {}
    midgame_data  = midgame_data or {}

    with conn.cursor() as cur:
        for p in participants:
            if p.grid_player_id is None:
                log.warning("Participant riot_id=%d without grid_player_id, skip pick.",
                            p.riot_id)
                continue

            player_local = player_grid_to_local.get(int(p.grid_player_id))
            if player_local is None:
                log.warning("Player grid_id=%s unresolved, skip pick.",
                            p.grid_player_id)
                continue

            champ_id = resolve_champ(p.champion_name, champ_lookup)
            if champ_id is None:
                log.warning("Champion %r without id, skip pick.", p.champion_name)
                continue

            side       = p.team_side  # "BLUE" or "RED"
            result     = (side == winner)
            p_pick_ord = pick_order_for(p.champion_name, draft_data,
                                        p.grid_team_id, champ_lookup)
            # Per-game role from the riot_id convention — NOT RoleCache, which
            # prefers GRID's *current* declared role (staleness on rerolls).
            p_role     = (None if side in suspect_sides
                          else role_from_riot_id(p.riot_id))

            p_stats = players_stats.get(p.riot_id) or {}
            b_stats = builds_data.get(p.riot_id) or {}
            m_stats = midgame_data.get(p.riot_id) or {}
            # Stats contract aligned with SoloQ. runes/final_items/
            # summoner_spells come from PostGameObserver (Riot summary or
            # Tencent); skill_order/build_path from BuildObserver (Riot
            # livestats); midgame from MidGameStatsObserver. Out of scope in
            # GRID: team_position, champ_level, vision_score.
            stats_json = {
                "kills":        p_stats.get("kills"),
                "deaths":       p_stats.get("deaths"),
                "assists":      p_stats.get("assists"),
                "gold":         p_stats.get("gold"),
                "cs":           p_stats.get("cs"),
                "damage_dealt": p_stats.get("damage_dealt"),
                "kda_str":      p_stats.get("kda_str"),
                "runes":        p_stats.get("runes"),
                "final_items":  p_stats.get("final_items"),
                "summoner_spells": p_stats.get("summoner_spells"),
                "skill_order":  b_stats.get("skill_order") or None,
                "build_path":   b_stats.get("build_path") or None,
                "midgame":      m_stats.get("marks") or None,
            }

            cur.execute(
                """
                INSERT INTO picks
                    (player_id, account_id, game_id, champ_id,
                     side, result, pick_order, role, stats)
                VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    player_local, game_id, champ_id,
                    side, result, p_pick_ord, p_role,
                    json.dumps(stats_json),
                ),
            )


# ---------------------------------------------------------------------------
# Unified processing flow (official and scrims share ~85%)
# ---------------------------------------------------------------------------

class GameAlreadyInDB(Exception):
    """Signals that insert_game hit ON CONFLICT (the game already existed).

    Raised to force a rollback of the per-game savepoint and avoid leaving an
    orphan draft (insert_draft runs before insert_game). The caller treats it
    as 'game skipped', not an error.
    """


@dataclass
class GameProcessingConfig:
    """Behavioral differences between the official and scrim flows.

    The rest of the processing (observers, draft, discovery, INSERTs) is
    identical and lives in process_one_game.
    """
    game_type: str                    # 'OFFICIAL' | 'SCRIM'
    tournament: str                   # tournament name or 'SCRIM'
    label: str                        # log prefix: 'Series' | 'Scrim'
    reconcile: bool                   # reconcile roster (official only)
    warn_on_new: bool                 # WARNING when creating team/player (scrims)
    require_participants: bool        # skip if no participants (official)
    discover_teams_from_draft: bool   # derive teams from the draft if missing (scrims)
    pass_tencent: bool                # include tencent_details in the bundle
    allow_missing_draft: bool = False # SCRIM: insert game+picks with draft_id
                                      # NULL when there is no usable draft
                                      # (blind pick or a dodged/orphaned one)


def _extract_duration_s(
    riot_summary: dict | None,
    tencent_raw: dict | None,
    midgame: MidGameStatsObserver,
) -> float | None:
    """Game duration in seconds. Priority: Riot Summary > Tencent > midgame proxy.

    Riot switched gameDuration units from seconds to ms in patch 11.20.
    Heuristic: a value > 7200 (2h in seconds, impossible) is ms.
    """
    if riot_summary:
        raw = riot_summary.get("gameDuration")
        if raw:
            return raw / 1000 if raw > 7200 else float(raw)
    if tencent_raw:
        dur = normalize_tencent_details(tencent_raw).get("game_duration_s")
        if dur:
            return float(dur)
    if midgame._max_game_time >= 0:
        return midgame._max_game_time / 1000
    return None


def _build_processor():
    """Create the processor and observers in the required attach order."""
    proc    = GameEventProcessor()
    teams   = TeamsObserver()
    draft   = DraftObserver()
    stats   = PostGameObserver()
    objs    = ObjectiveKilledObserver()
    wards   = WardsObserver(teams_observer=teams)
    builds  = BuildObserver()
    midgame = MidGameStatsObserver()
    solos   = SoloKillObserver(teams_observer=teams)
    for o in (teams, draft, stats, objs, wards, builds, midgame, solos):
        proc.attach(o)
    return proc, teams, draft, stats, objs, wards, builds, midgame, solos


def _gather_participants(teams: TeamsObserver) -> list:
    """Participants riot_id 1..10 that the TeamsObserver could resolve."""
    return [
        p for i in range(1, 11)
        if (p := teams.get_player_by_id(i)) is not None
    ]


def _assign_blue_red(participants: list,
                     grid_team_id_to_local: dict[int, int]
                     ) -> tuple[int | None, int | None]:
    """team1=BLUE, team2=RED by convention."""
    team1_local = team2_local = None
    for p in participants:
        if p.grid_team_id is None:
            continue
        local = grid_team_id_to_local.get(int(p.grid_team_id))
        if p.team_side == "BLUE" and team1_local is None:
            team1_local = local
        elif p.team_side == "RED" and team2_local is None:
            team2_local = local
    return team1_local, team2_local


def process_one_game(
    client_rest: GridRestClient,
    conn: psycopg.Connection,
    series_node: dict,
    series_id: str,
    game_number: int,
    raw_game: list,
    role_cache: RoleCache,
    champ_lookup: dict[str, int],
    *,
    cfg: GameProcessingConfig,
    grid_game_state=None,
    riot_livestats=None,
) -> bool:
    """Process one game: observers -> auto-discovery -> INSERT.

    Flow shared by official and scrims; the differences live in `cfg`. Returns
    True if inserted, False if skipped. Raises GameAlreadyInDB when insert_game
    hits ON CONFLICT (to roll back the savepoint).
    """
    proc, teams, draft, stats, objs, wards, builds, midgame, solos = _build_processor()

    tencent_raw    = (client_rest.get_tencent_details(series_id, game_number)
                       if cfg.pass_tencent else None)
    riot_summary_raw = client_rest.get_riot_summary(series_id,
                                                     game_number=game_number)

    proc.process_bundle(
        grid_game_state=grid_game_state,
        tencent_details=tencent_raw,
        grid_livestats=raw_game,
        riot_summary=riot_summary_raw,
        riot_livestats=riot_livestats,
    )

    # No draft events: either a real skip (official, or scrims that don't
    # allow it), or a blind-pick scrim — decided below, once we know cfg.
    draft_data = draft.get_draft()
    draft_missing_reason: str | None = None
    if not draft_data["draft_found"]:
        if not cfg.allow_missing_draft:
            log.warning("%s %s game %d: empty draft (no draft events), skip.",
                        cfg.label, series_id, game_number)
            return False
        draft_missing_reason = "no_draft_events"

    game_stats = stats.get_game_stats(teams)
    winner = game_stats["meta"].get("winner")

    # Without a valid winner the game is not inserted; it stays in the logs for
    # manual review (we prefer no game over biased data).
    if winner not in ("BLUE", "RED"):
        log.warning("%s %s game %d: no winner (winner=%r), not inserted. "
                    "Review manually.",
                    cfg.label, series_id, game_number, winner)
        return False

    if game_stats["meta"].get("winner_source") == "gold_heuristic":
        log.warning("%s %s game %d: winner from gold heuristic "
                    "(suspect data).", cfg.label, series_id, game_number)

    participants = _gather_participants(teams)
    if cfg.require_participants and not participants:
        log.warning("%s %s game %d: no participants, skip.",
                    cfg.label, series_id, game_number)
        return False

    # Blind pick can also happen after a dodged draft: the feed keeps an
    # orphaned draft that does not match what was actually played. Only
    # checked when we can compare against all 10 played champions — with
    # fewer known there isn't enough evidence to distrust the recorded draft.
    if cfg.allow_missing_draft and draft_missing_reason is None:
        draft_missing_reason = draft_missing_reason_for(
            draft_data, participants, champ_lookup)
    if draft_missing_reason:
        log.warning("%s %s game %d: draft not usable (%s), inserting with "
                    "draft_id=NULL and pick_order=NULL.",
                    cfg.label, series_id, game_number, draft_missing_reason)
        game_stats["meta"]["draft_missing_reason"] = draft_missing_reason
        draft_data = EMPTY_DRAFT

    # --- Auto-discovery: teams ---
    series_teams_by_grid = {
        int(t["baseInfo"]["id"]): t["baseInfo"]
        for t in (series_node.get("teams") or [])
    }
    grid_team_id_to_local: dict[int, int] = {}

    def _discover_team(gid: int) -> None:
        if gid in grid_team_id_to_local:
            return
        base = series_teams_by_grid.get(gid, {})
        name = base.get("name") or f"Team_{gid}"
        local_id, is_new = ensure_team(
            conn, grid_id=gid, name=name, tag=base.get("nameShortened"),
        )
        if is_new and cfg.warn_on_new:
            log.warning("%s %s game %d: created new TEAM in DB "
                        "(grid_id=%d, name=%r) - review manually.",
                        cfg.label, series_id, game_number, gid, name)
        grid_team_id_to_local[gid] = local_id

    for p in participants:
        if p.grid_team_id is not None:
            _discover_team(int(p.grid_team_id))

    # Scrims with no played participants: recover teams from the draft itself.
    if cfg.discover_teams_from_draft:
        for side in ("fp", "sp"):
            tid_str = (draft_data.get(side) or {}).get("team_id")
            if tid_str:
                _discover_team(int(tid_str))

    team1_local, team2_local = _assign_blue_red(participants,
                                                grid_team_id_to_local)

    # Per-game role from the riot_id ordering convention — the same evidence
    # persisted as picks.role, and (since 2026-07-13) also what reconciliation
    # uses. NOT RoleCache/Central Data, which is GRID's *currently* declared
    # role: a snapshot of today that would leak into old games processed out
    # of order and isn't protected by the chronological order that guards
    # team_id/starter (see F9, full_audit_2026-07-13.md). RoleCache is kept
    # only for ensure_player's metadata on newly discovered players.
    suspect_sides = smite_suspect_sides(participants, game_stats.get("players") or {})
    for side in sorted(suspect_sides):
        log.warning("%s %s game %d side %s: derived JUNGLE has no Smite "
                    "but a teammate does — participant order suspect, "
                    "role=NULL for that side (roster and picks alike).",
                    cfg.label, series_id, game_number, side)

    # --- Auto-discovery: players (+ reconciliation for official games only) ---
    game_date = parse_date(series_node["startTimeScheduled"])
    player_grid_to_local: dict[int, int] = {}

    for p in participants:
        if p.grid_player_id is None:
            log.warning("%s %s game %d: participant riot_id=%d without "
                        "grid_player_id, skip.",
                        cfg.label, series_id, game_number, p.riot_id)
            continue

        grid_pid = int(p.grid_player_id)
        team_local = (grid_team_id_to_local.get(int(p.grid_team_id))
                      if p.grid_team_id else None)
        role_obs = role_cache.role_for(grid_pid, p.riot_id)
        role_game = (None if p.team_side in suspect_sides
                     else role_from_riot_id(p.riot_id))
        nickname = p.summoner_name or f"Player_{grid_pid}"

        local_id, is_new = ensure_player(
            conn, grid_id=grid_pid, nickname=nickname,
            team_local_id=team_local, role=role_obs,
        )
        if is_new and cfg.warn_on_new:
            log.warning("%s %s game %d: created new PLAYER in DB "
                        "(grid_id=%d, nickname=%r, team_local=%s, role=%s) - "
                        "review manually.",
                        cfg.label, series_id, game_number, grid_pid, nickname,
                        team_local, role_obs)
        player_grid_to_local[grid_pid] = local_id

        if cfg.reconcile and role_game and team_local:
            reconcile_player_roster(
                conn, player_local_id=local_id, team_local_id=team_local,
                role_observed=role_game, game_date=game_date,
            )

    # --- INSERT draft / game / picks ---
    draft_id = (None if draft_missing_reason
                else insert_draft(conn, draft_data, grid_team_id_to_local,
                                  champ_lookup))

    game_id = insert_game(
        conn,
        series_node=series_node,
        game_number=game_number,
        winner=winner,
        version=game_stats["meta"].get("version"),
        team1_local=team1_local,
        team2_local=team2_local,
        draft_id=draft_id,
        game_stats=game_stats,
        objs_data=objs.get_all_objectives(),
        wards_data=wards.get_wards(),
        solokills_data=solos.get_solokills(),
        game_type=cfg.game_type,
        tournament=cfg.tournament,
        duration_s=_extract_duration_s(riot_summary_raw, tencent_raw, midgame),
    )

    # ON CONFLICT -> roll back the savepoint so the just-inserted draft is not
    # left orphaned (race between concurrent runs).
    if game_id is None:
        raise GameAlreadyInDB(
            f"{cfg.label} {series_id} game {game_number}: "
            "already in DB (ON CONFLICT)."
        )

    insert_picks(
        conn,
        game_id=game_id,
        winner=winner,
        participants=participants,
        player_grid_to_local=player_grid_to_local,
        game_stats=game_stats,
        champ_lookup=champ_lookup,
        draft_data=draft_data,
        suspect_sides=suspect_sides,
        builds_data=builds.get_builds(),
        midgame_data=midgame.get_mid_game_stats(),
    )
    return True


def run_series(
    client_rest: GridRestClient,
    client_graphql: GridGraphQLClient,
    conn: psycopg.Connection,
    series_node: dict,
    role_cache: RoleCache,
    champ_lookup: dict[str, int],
    *,
    label: str,
    cfg_for_game,
) -> SeriesResult:
    """Download and process every game of a series (official or scrim).

    `cfg_for_game(series_node) -> GameProcessingConfig` resolves the per-game
    config (the official tournament depends on series_node). `label` is the
    series-level log prefix.
    """
    series_id      = series_node["id"]
    grid_series_id = int(series_id)
    result         = SeriesResult()

    if series_fully_in_db(conn, grid_series_id, client_graphql, series_id):
        log.debug("%s %s: already complete in DB, skip.", label, series_id)
        result.skipped = True
        return result

    try:
        full = client_rest.get_grid_events(series_id)
    except GridError as e:
        log.error("%s %s: error downloading events: %s", label, series_id, e)
        result.errors += 1
        return result

    if not full:
        log.info("%s %s: no events available, skip.", label, series_id)
        result.no_events = True
        return result

    games = split_grid_series(full)
    log.info("%s %s: %d game(s).", label, series_id, len(games))

    # GRID end-state: version + draftActions fallback (mainly LPL).
    grid_state = None
    try:
        grid_state = client_rest.get_grid_endstate(series_id)
    except GridError as e:
        log.warning("%s %s: get_grid_endstate failed: %s",
                    label, series_id, e)

    # Fragmented Riot LiveStats: in LPL this is not a single file per game but
    # N fragments per series that must be grouped.
    fragments_grouped = None
    try:
        frags = client_rest.get_riot_livestats_fragments(series_id)
        if frags:
            fragments_grouped = group_riot_livestats_fragments(
                frags, expected_games=len(games)
            )
    except GridError:
        pass

    def _riot_ls_for(game_number: int):
        """Single file first; fall back to fragments (LPL)."""
        ls = client_rest.get_riot_livestats(series_id, game_number)
        if ls is not None:
            return ls
        if (fragments_grouped
                and fragments_grouped.get("confidence") != "low"):
            fg = fragments_grouped.get("games") or []
            if game_number - 1 < len(fg):
                return fg[game_number - 1]
        return None

    for i, raw_game in enumerate(games):
        game_number = i + 1

        if game_in_db(conn, grid_series_id, game_number):
            log.debug("%s %s game %d: already in DB, skip.",
                      label, series_id, game_number)
            result.games_skipped += 1
            continue

        try:
            with conn.transaction():
                inserted = process_one_game(
                    client_rest, conn, series_node,
                    series_id, game_number, raw_game,
                    role_cache, champ_lookup,
                    cfg=cfg_for_game(series_node),
                    grid_game_state=(
                        extract_grid_game_state(grid_state, game_number)
                        if grid_state else None
                    ),
                    riot_livestats=_riot_ls_for(game_number),
                )
            if inserted:
                result.games_new += 1
                log.info("%s %s game %d: inserted.",
                         label, series_id, game_number)
            else:
                # process_one_game returned False: bad data (empty draft, no
                # winner, no participants), not an idempotency skip.
                result.games_discarded += 1

        except GameAlreadyInDB as e:
            log.info("%s", e)
            result.games_skipped += 1
        except Exception:
            log.exception("%s %s game %d: unexpected failure, continuing.",
                          label, series_id, game_number)
            result.errors += 1

    return result
