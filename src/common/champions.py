"""Load and maintain the `champions` table from Riot Data Dragon.

Usage:
    # Initial bootstrap or refresh:
    python -m src.common.champions

    # From another module:
    from src.common.champions import ensure_loaded, build_lookup
    ensure_loaded(conn)          # no-op if rows already exist
    lookup = build_lookup(conn)  # dict {name: id, alias: id}
    champ_id = lookup["Lee Sin"]   # 64
    champ_id = lookup["LeeSin"]    # 64
"""

from __future__ import annotations

import logging
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
    """Download champions from Data Dragon and upsert them into `champions`.

    Uses the latest version when `version` is None. Idempotent, and updates
    name/alias on a Riot rename (e.g. Nunu -> "Nunu & Willump") instead of
    keeping the stale value forever. Returns the count of new rows.
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
                ON CONFLICT (id) DO UPDATE
                   SET name = EXCLUDED.name, alias = EXCLUDED.alias
                 WHERE champions.name  IS DISTINCT FROM EXCLUDED.name
                    OR champions.alias IS DISTINCT FROM EXCLUDED.alias
                RETURNING (xmax = 0) AS is_insert
                """,
                (champ_id, name, alias),
            )
            row = cur.fetchone()
            if row and row[0]:
                inserted += 1

    conn.commit()
    log.info("Champions: %d new inserted (%d total in Data Dragon).",
             inserted, len(data))
    return inserted


def ensure_loaded(conn) -> None:
    """Run refresh_champions if the table is empty."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM champions")
        count = cur.fetchone()[0]
    if count == 0:
        log.info("champions table empty — loading from Data Dragon...")
        refresh_champions(conn)


def build_lookup(conn) -> dict[str, int]:
    """Return a dict mapping both name and alias to champion id.

    Example: {"Lee Sin": 64, "LeeSin": 64, "Aatrox": 266, ...}
    """
    lookup: dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, alias FROM champions")
        for champ_id, name, alias in cur.fetchall():
            lookup[name] = champ_id
            lookup[alias] = champ_id
    return lookup


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

    from src.db.conn import get_conn
    with get_conn() as conn:
        refresh_champions(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
