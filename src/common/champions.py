"""Carga y mantenimiento de la tabla `champions` desde Riot Data Dragon.

Uso:
    # Bootstrap inicial o actualizacion:
    python -m src.common.champions

    # Desde otro modulo:
    from src.common.champions import ensure_loaded, build_lookup
    ensure_loaded(conn)          # no-op si ya hay filas
    lookup = build_lookup(conn)  # dict {name: id, alias: id}
    champ_id = lookup["Lee Sin"]   # 64
    champ_id = lookup["LeeSin"]    # 64
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import requests

log = logging.getLogger(__name__)

_VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
_CHAMPIONS_URL = "https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"


def _latest_version() -> str:
    resp = requests.get(_VERSIONS_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()[0]


def refresh_champions(conn, version: str | None = None) -> int:
    """Descarga campeones de Data Dragon y los upsertea en la tabla `champions`.

    Si `version` es None, usa la version mas reciente.
    Idempotente: INSERT ... ON CONFLICT (id) DO NOTHING.
    Devuelve cuantos campeones nuevos se insertaron.
    """
    if version is None:
        version = _latest_version()
        log.info("Data Dragon version: %s", version)

    url = _CHAMPIONS_URL.format(version=version)
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json().get("data") or {}

    inserted = 0
    with conn.cursor() as cur:
        for entry in data.values():
            champ_id = int(entry["key"])
            name = entry["name"]      # "Lee Sin", "Wukong"
            alias = entry["id"]       # "LeeSin", "MonkeyKing"
            cur.execute(
                """
                INSERT INTO champions (id, name, alias)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                RETURNING id
                """,
                (champ_id, name, alias),
            )
            if cur.fetchone():
                inserted += 1

    conn.commit()
    log.info("Champions: %d nuevos insertados (total: %d en Data Dragon).",
             inserted, len(data))
    return inserted


def ensure_loaded(conn) -> None:
    """Si la tabla esta vacia, lanza refresh_champions automaticamente."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM champions")
        count = cur.fetchone()[0]
    if count == 0:
        log.info("Tabla champions vacia — cargando desde Data Dragon...")
        refresh_champions(conn)


def build_lookup(conn) -> dict[str, int]:
    """Devuelve un dict que mapea name y alias a champion id.

    Ejemplo: {"Lee Sin": 64, "LeeSin": 64, "Aatrox": 266, ...}
    """
    lookup: dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, alias FROM champions")
        for champ_id, name, alias in cur.fetchall():
            lookup[name] = champ_id
            lookup[alias] = champ_id
    return lookup


# ---------------------------------------------------------------------------
# Mini-CLI
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

    from src.db.conn import get_conn
    with get_conn() as conn:
        refresh_champions(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
