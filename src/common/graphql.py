"""Reusable GraphQL pagination helper (Relay pattern).

Shared by discovery and extraction.
"""

from __future__ import annotations

from typing import Any, Generator

from grid_minion import GridGraphQLClient


def paginate(
    client: GridGraphQLClient,
    query: str,
    root_key: str,
    variables: dict[str, Any],
) -> Generator[dict, None, None]:
    """Yield nodes from a Relay connection, following pages until exhausted.

    Args:
        root_key: name of the root field under `data` (e.g. "allSeries", "players").
        variables: merged with {"after": cursor} on each page.
    """
    cursor: str | None = None
    while True:
        data = client.query_central(query, variables={**variables, "after": cursor})
        conn = data.get(root_key) or {}
        for edge in conn.get("edges") or []:
            node = edge.get("node")
            if node:
                yield node
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
        if not cursor:
            break
