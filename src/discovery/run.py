"""Bulk discovery of teams and players from GRID.

Flow:

  config/tournaments.yaml  -> names or numeric ids
       │
       ▼
  id  -> tournament(id:)                  (direct lookup)
  name -> tournaments(filter:{name:{contains}})  -> exact match
       │
       ▼  tournamentId
       │
       ▼
  allSeries(filter:{tournament:{id, includeChildren:true}, types:[ESPORTS]}) paginated
       │  teams only — Series.players[] is incomplete in GRID
       ▼
  teams[]  -> ensure_team
       │
       ▼
  per team: players(filter:{teamIdFilter:{id}}) paginated
       │  full roster: starters + substitutes
       ▼
  ensure_player (with normalized role)

Run:  python -m src.discovery.run
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from grid_minion import GridError, GridGraphQLClient

from src.db.conn import get_conn
from src.db.upsert import ensure_player, ensure_team

from src.common.graphql import paginate
from src.common.roles import normalize_role

from .queries import (
    PLAYERS_BY_TEAM,
    SERIES_BY_TOURNAMENTS,
    TOURNAMENT_BY_ID,
    TOURNAMENTS_BY_NAME,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "tournaments.yaml"

log = logging.getLogger("discovery")


def load_tournament_entries() -> list[str]:
    """Load tournament entries from the yaml.

    Each entry is either an exact tournament *name* (e.g. ``"LEC Spring 2026"``)
    or a numeric GRID tournament *id* (e.g. ``757825`` or ``"757825"``). Ids are
    returned as plain digit strings; classification (id vs name) happens at
    resolve time via ``str.isdigit()``. Booleans (YAML ``true``/``false``, which
    are ``int`` subclasses) are ignored.
    """
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    entries = data.get("tournaments") or []
    if not isinstance(entries, list):
        raise ValueError(
            f"{CONFIG_PATH}: the `tournaments` field must be a YAML list."
        )
    out: list[str] = []
    for e in entries:
        if isinstance(e, bool):
            continue
        if isinstance(e, int):
            out.append(str(e))
        elif isinstance(e, str) and e.strip():
            out.append(e.strip())
    return out


def build_client() -> GridGraphQLClient:
    api_key = os.environ.get("GRID_API_KEY")
    if not api_key:
        log.error("GRID_API_KEY missing from the environment (.env).")
        sys.exit(1)
    return GridGraphQLClient(api_key=api_key)


def resolve_tournament(
    client: GridGraphQLClient,
    entry: str,
) -> str | None:
    """Resolve a yaml entry to a GRID tournament id (or None to skip).

    Numeric entries are treated as ids and looked up directly; everything else
    goes through exact-name matching. Prefer ids for umbrella tournaments like
    LCK/LPL/LCS: the name search is capped at 50 results and their exact match
    sits past the first page, so name resolution silently misses them.
    """
    if entry.isdigit():
        return resolve_tournament_by_id(client, entry)
    return resolve_tournament_by_name(client, entry)


def resolve_tournament_by_id(
    client: GridGraphQLClient,
    tid: str,
) -> str | None:
    """Validate a tournament id exists and return it (logs its name).

    A null `tournament` (unknown id) is a skip, not an error.
    """
    data = client.query_central(TOURNAMENT_BY_ID, variables={"id": tid})
    node = data.get("tournament")
    if not node:
        log.warning("Tournament id %s: not found in GRID, skipping.", tid)
        return None
    log.info("Tournament id %s resolved to %r.", tid, node.get("name"))
    return str(node.get("id"))


def resolve_tournament_by_name(
    client: GridGraphQLClient,
    name: str,
) -> str | None:
    """Return the id of the tournament whose `name` matches exactly.

    Returns None on zero matches or ambiguity (logs and skips). The sub-stage
    hierarchy is resolved in SERIES_BY_TOURNAMENTS via
    `includeChildren: { equals: true }`.
    """
    data = client.query_central(TOURNAMENTS_BY_NAME, variables={"name": name})
    edges = (data.get("tournaments") or {}).get("edges") or []
    candidates = [e["node"] for e in edges if e.get("node")]
    exact = [n for n in candidates if n.get("name") == name]
    if not exact:
        log.warning(
            "Tournament %r: no exact match. Candidates (contains): %s. "
            "If this is an umbrella league (LCK/LPL/LCS...), use its numeric "
            "id in the yaml instead — name search is capped at 50 results.",
            name,
            [c.get("name") for c in candidates] or "[]",
        )
        return None
    if len(exact) > 1:
        log.warning(
            "Tournament %r: %d exact matches, ambiguous. IDs: %s",
            name,
            len(exact),
            [n.get("id") for n in exact],
        )
        return None
    return exact[0]["id"]


def accumulate_teams(
    series_nodes,
    teams_by_grid: dict[int, dict[str, Any]],
) -> None:
    """Extract teams from Series nodes, deduplicating by grid_id."""
    for series in series_nodes:
        for tp in series.get("teams") or []:
            base = (tp or {}).get("baseInfo") or {}
            tid = base.get("id")
            if tid is None:
                continue
            teams_by_grid.setdefault(
                int(tid),
                {
                    "grid_id": int(tid),
                    "name": base.get("name"),
                    "tag": base.get("nameShortened"),
                },
            )


def accumulate_players(
    client: GridGraphQLClient,
    teams_by_grid: dict[int, dict[str, Any]],
    players_by_grid: dict[int, dict[str, Any]],
) -> None:
    """Query each discovered team's players directly.

    Uses the team_grid_id we queried by (not Player.team.id) to avoid wrong
    associations if a player recently changed teams.
    """
    for team_grid_id in teams_by_grid:
        for p in paginate(client, PLAYERS_BY_TEAM, "players",
                           {"teamId": str(team_grid_id)}):
            pid = p.get("id")
            if pid is None:
                continue
            roles = p.get("roles") or []
            raw_roles = [r.get("name") for r in roles if r.get("name")]
            role = normalize_role(raw_roles[0]) if raw_roles else None
            players_by_grid.setdefault(
                int(pid),
                {
                    "grid_id": int(pid),
                    "nickname": p.get("nickname"),
                    "team_grid_id": team_grid_id,   # team we queried by
                    "role": role,
                },
            )


def write_to_db(
    teams_by_grid: dict[int, dict[str, Any]],
    players_by_grid: dict[int, dict[str, Any]],
) -> tuple[int, int]:
    """Insert teams and players idempotently (teams first for the FK).

    Returns (new_teams, new_players).
    """
    teams_new = players_new = 0
    with get_conn() as conn:
        team_grid_to_local: dict[int, int] = {}
        for t in teams_by_grid.values():
            # GRID may omit name; teams.name is NOT NULL and a None would break
            # the discovery's single commit (same fallback as the per-game
            # extractor).
            name = t["name"] or f"Team_{t['grid_id']}"
            local_id, is_new = ensure_team(
                conn, grid_id=t["grid_id"], name=name, tag=t["tag"],
            )
            team_grid_to_local[t["grid_id"]] = local_id
            teams_new += is_new

        for p in players_by_grid.values():
            team_local = team_grid_to_local.get(p["team_grid_id"])
            # Same guard: players.name is NOT NULL.
            nickname = p["nickname"] or f"Player_{p['grid_id']}"
            _, is_new = ensure_player(
                conn,
                grid_id=p["grid_id"],
                nickname=nickname,
                team_local_id=team_local,
                role=p.get("role"),
            )
            players_new += is_new

        conn.commit()

    return teams_new, players_new


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    entries = load_tournament_entries()
    if not entries:
        log.info("config/tournaments.yaml has no tournaments. Add some and rerun.")
        return 0

    log.info("Tournaments to process: %s", entries)
    client = build_client()

    teams_by_grid: dict[int, dict[str, Any]] = {}
    players_by_grid: dict[int, dict[str, Any]] = {}

    for entry in entries:
        try:
            tid = resolve_tournament(client, entry)
        except GridError as e:
            log.error("GraphQL error resolving tournament %r: %s", entry, e)
            continue
        if not tid:
            continue
        log.info("Tournament %r -> id %s. Discovering teams...", entry, tid)
        try:
            accumulate_teams(
                paginate(client, SERIES_BY_TOURNAMENTS, "allSeries", {"tid": tid}),
                teams_by_grid,
            )
        except GridError as e:
            log.error("GraphQL error paginating series of %r: %s", entry, e)
            continue

    log.info("Teams accumulated (deduplicated): %d", len(teams_by_grid))
    log.info("Querying players per team...")

    try:
        accumulate_players(client, teams_by_grid, players_by_grid)
    except GridError as e:
        log.error("GraphQL error querying players: %s", e)

    log.info("Players accumulated (deduplicated): %d", len(players_by_grid))

    teams_new, players_new = write_to_db(teams_by_grid, players_by_grid)

    log.info("Teams: %d processed, %d new.", len(teams_by_grid), teams_new)
    log.info("Players: %d processed, %d new.", len(players_by_grid), players_new)

    return 0


if __name__ == "__main__":
    sys.exit(main())
