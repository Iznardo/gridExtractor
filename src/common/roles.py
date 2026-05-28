"""Normalizacion de roles para teams y players.

Compartido por discovery y extraction (CLAUDE.md §5.2, §5.5).
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Mapeo de nombres de rol de GRID (minusculas, verificados empiricamente)
# al formato de la tabla. Valores observados: top, mid, jungle, bottom, support.
_ROLE_MAP: dict[str, str] = {
    "top": "TOP",
    "mid": "MID",
    "jungle": "JUNGLE",
    "bottom": "ADC",
    "support": "SUPPORT",
}

# Convencion de orden de Riot: riot_id 1-5 = BLUE, 6-10 = RED.
# Posicion dentro del equipo: 1/6=TOP, 2/7=JUNGLE, 3/8=MID, 4/9=ADC, 5/10=SUPPORT.
_ROLE_BY_RIOT_ID: dict[int, str] = {
    1: "TOP", 2: "JUNGLE", 3: "MID", 4: "ADC", 5: "SUPPORT",
    6: "TOP", 7: "JUNGLE", 8: "MID", 9: "ADC", 10: "SUPPORT",
}


def normalize_role(raw: str | None) -> str | None:
    """Convierte el nombre de rol de GRID al formato de la tabla.

    Devuelve None si raw es None o no esta en el mapa conocido (con
    warning para detectar valores nuevos).
    """
    if not raw:
        return None
    normalized = _ROLE_MAP.get(raw.strip().lower())
    if normalized is None:
        log.warning("Rol desconocido de GRID: %r — se deja NULL.", raw)
    return normalized


def role_from_riot_id(riot_id: int) -> str | None:
    """Devuelve el rol por convencion de orden de participants de Riot.

    Fallback cuando el catalogo de GRID no aporta rol.
    Funciona en oficiales donde GRID respeta el orden de Riot
    (riot_id 1-5 = BLUE TOP/JG/MID/ADC/SUP, 6-10 = RED idem).
    """
    return _ROLE_BY_RIOT_ID.get(riot_id)
