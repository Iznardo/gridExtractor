"""Enrutamiento de la Riot API: plataforma -> region (RIOT_API.md §3).

Account-V1 y Match-V5 usan hosts *regionales* (americas/asia/europe/sea);
el matchId lleva prefijo de *plataforma* (KR_..., EUW1_...), de donde se
deriva la region. El mapeo ha cambiado historicamente (OCE/SEA) — si Riot
anade plataformas, actualizar la tabla contra la doc oficial.
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
        raise ValueError(f"Plataforma desconocida: {platform!r}") from None


def region_from_match_id(match_id: str) -> str:
    """'KR_8232000299' -> 'asia'."""
    return platform_to_region(match_id.split("_", 1)[0])
