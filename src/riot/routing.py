"""Riot API routing: platform -> region.

Account-V1 and Match-V5 use *regional* hosts (americas/asia/europe/sea); the
matchId carries a *platform* prefix (KR_..., EUW1_...), from which the region is
derived. The mapping has changed over time (OCE/SEA) — if Riot adds platforms,
update the table against the official docs.
"""

from __future__ import annotations

REGIONS = ("americas", "asia", "europe", "sea")

PLATFORM_TO_REGION = {
    "na1": "americas",
    "br1": "americas",
    "la1": "americas",
    "la2": "americas",
    "kr": "asia",
    "jp1": "asia",
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    "me1": "europe",
    "oc1": "sea",
    "ph2": "sea",
    "sg2": "sea",
    "th2": "sea",
    "tw2": "sea",
    "vn2": "sea",
}


def platform_to_region(platform: str) -> str:
    try:
        return PLATFORM_TO_REGION[platform.lower()]
    except KeyError:
        raise ValueError(f"Unknown platform: {platform!r}") from None


def region_from_match_id(match_id: str) -> str:
    """'KR_8232000299' -> 'asia'."""
    return platform_to_region(match_id.split("_", 1)[0])


def match_sort_key(match_id: str) -> int:
    """The match id's number, for sorting newest to oldest."""
    try:
        return int(match_id.split("_", 1)[1])
    except (IndexError, ValueError):
        return 0
