"""Una funcion por endpoint de la Riot API (RIOT_API.md §6).

Todas reciben el RiotClient y devuelven el JSON parseado (o None en 404).
La region de match/timeline se deriva del prefijo del matchId.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from .client import RiotClient
from .routing import region_from_match_id

RANKED_SOLO_QUEUE = 420

# El matchlist devuelve como mucho 100 ids por pagina.
_PAGE_SIZE = 100


def get_account_by_riot_id(
    client: RiotClient, region: str, game_name: str, tag_line: str
) -> dict | None:
    path = (f"/riot/account/v1/accounts/by-riot-id/"
            f"{quote(game_name)}/{quote(tag_line)}")
    return client.get(region, path)


def get_account_by_puuid(client: RiotClient, region: str, puuid: str) -> dict | None:
    return client.get(region, f"/riot/account/v1/accounts/by-puuid/{puuid}")


def get_match_ids(
    client: RiotClient,
    region: str,
    puuid: str,
    *,
    queue: int | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
    page_size: int = _PAGE_SIZE,
) -> list[str]:
    """Lista completa de match ids del puuid, paginando hasta agotar.
    `start_time`/`end_time` en epoch SEGUNDOS (§6.2)."""
    path = f"/lol/match/v5/matches/by-puuid/{puuid}/ids"
    ids: list[str] = []
    start = 0
    while True:
        params: dict[str, Any] = {"start": start, "count": page_size}
        if queue is not None:
            params["queue"] = queue
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        page = client.get(region, path, params)
        if not page:
            break
        ids.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    return ids


def get_match(client: RiotClient, match_id: str) -> dict | None:
    region = region_from_match_id(match_id)
    return client.get(region, f"/lol/match/v5/matches/{match_id}")


def get_match_timeline(client: RiotClient, match_id: str) -> dict | None:
    region = region_from_match_id(match_id)
    return client.get(region, f"/lol/match/v5/matches/{match_id}/timeline")
