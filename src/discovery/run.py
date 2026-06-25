"""Bulk discovery of teams and players from GRID.

Flow:

  config/tournaments.yaml  -> names
       │
       ▼
  tournaments(filter:{name:{contains}})  -> resolve tournamentId
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

from .queries import PLAYERS_BY_TEAM, SERIES_BY_TOURNAMENTS, TOURNAMENTS_BY_NAME


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "tournaments.yaml"

log = logging.getLogger("discovery")


def load_tournament_names() -> list[str]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    names = data.get("tournaments") or []
    if not isinstance(names, list):
        raise ValueError(
            f"{CONFIG_PATH}: the `tournaments` field must be a YAML list."
        )
    return [n for n in names if isinstance(n, str) and n.strip()]


def build_client() -> GridGraphQLClient:
    api_key = os.environ.get("GRID_API_KEY")
    if not api_key:
        log.error("GRID_API_KEY missing from the environment (.env).")
        sys.exit(1)
    return GridGraphQLClient(api_key=api_key)


def resolve_tournament_id(
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
            "Tournament %r: no exact match. Candidates (contains): %s",
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

    names = load_tournament_names()
    if not names:
        log.info("config/tournaments.yaml has no tournaments. Add some and rerun.")
        return 0

    log.info("Tournaments to process: %s", names)
    client = build_client()

    teams_by_grid: dict[int, dict[str, Any]] = {}
    players_by_grid: dict[int, dict[str, Any]] = {}

    for name in names:
        try:
            tid = resolve_tournament_id(client, name)
        except GridError as e:
            log.error("GraphQL error resolving tournament %r: %s", name, e)
            continue
        if not tid:
            continue
        log.info("Tournament %r -> id %s. Discovering teams...", name, tid)
        try:
            accumulate_teams(
                paginate(client, SERIES_BY_TOURNAMENTS, "allSeries", {"tid": tid}),
                teams_by_grid,
            )
        except GridError as e:
            log.error("GraphQL error paginating series of %r: %s", name, e)
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
