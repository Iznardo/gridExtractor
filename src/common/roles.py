"""Role normalization for teams and players.

Shared by discovery and extraction.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# GRID role names (lowercase) mapped to the table format.
# Observed values: top, mid, jungle, bottom, support.
_ROLE_MAP: dict[str, str] = {
    "top": "TOP",
    "mid": "MID",
    "jungle": "JUNGLE",
    "bottom": "ADC",
    "support": "SUPPORT",
}

# Riot ordering convention: riot_id 1-5 = BLUE, 6-10 = RED.
# Slot within the team: 1/6=TOP, 2/7=JUNGLE, 3/8=MID, 4/9=ADC, 5/10=SUPPORT.
_ROLE_BY_RIOT_ID: dict[int, str] = {
    1: "TOP", 2: "JUNGLE", 3: "MID", 4: "ADC", 5: "SUPPORT",
    6: "TOP", 7: "JUNGLE", 8: "MID", 9: "ADC", 10: "SUPPORT",
}

# Riot Match-V5 teamPosition values mapped to the table format. Only reliable
# in soloq (in tournament-code customs Riot fills it with garbage).
_TEAM_POSITION_MAP: dict[str, str] = {
    "TOP": "TOP",
    "JUNGLE": "JUNGLE",
    "MIDDLE": "MID",
    "BOTTOM": "ADC",
    "UTILITY": "SUPPORT",
}


def normalize_role(raw: str | None) -> str | None:
    """Map a GRID role name to the table format.

    Returns None if raw is None or not in the known map (logs a warning so new
    values surface).
    """
    if not raw:
        return None
    normalized = _ROLE_MAP.get(raw.strip().lower())
    if normalized is None:
        log.warning("Unknown GRID role: %r — left NULL.", raw)
    return normalized


def role_from_riot_id(riot_id: int) -> str | None:
    """Return the role from Riot's participant ordering convention.

    Fallback when the GRID catalog has no role. Works for official games, where
    GRID preserves Riot's order (riot_id 1-5 = BLUE TOP/JG/MID/ADC/SUP,
    6-10 = RED likewise).
    """
    return _ROLE_BY_RIOT_ID.get(riot_id)


def normalize_team_position(raw: str | None) -> str | None:
    """Map a Riot Match-V5 teamPosition to the table format (soloq only).

    Returns None for empty/unknown values (e.g. "" in remake-ish data).
    """
    if not raw:
        return None
    return _TEAM_POSITION_MAP.get(raw.strip().upper())
