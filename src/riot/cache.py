"""On-disk cache of raw Match-V5 responses.

Used by the disk-based SoloQ verification runner (src/riot/soloq_run.py): if the
JSON is already in data/riot/, it is not requested again. The full raw payload
(10 participants, whole timeline) is kept so more fields can be extracted later
without re-downloading.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .client import RiotClient
from .endpoints import get_match, get_match_timeline

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "riot"
MATCHES_DIR = DATA_DIR / "matches"
EXTRACTED_DIR = DATA_DIR / "extracted"
ACCOUNTS_DIR = DATA_DIR / "accounts"

# A 404 (match unavailable) is cached as `null` to avoid retrying.


def _cached(path: Path, fetch: Callable[[], dict | None]) -> tuple[dict | None, bool]:
    """Return (json, from_cache). Caches the 404's None too."""
    if path.exists():
        return json.loads(path.read_text()), True
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False))
    return data, False


def fetch_match_cached(client: RiotClient, match_id: str) -> tuple[dict | None, bool]:
    path = MATCHES_DIR / f"{match_id}.json"
    return _cached(path, lambda: get_match(client, match_id))


def fetch_timeline_cached(client: RiotClient, match_id: str) -> tuple[dict | None, bool]:
    path = MATCHES_DIR / f"{match_id}_timeline.json"
    return _cached(path, lambda: get_match_timeline(client, match_id))
