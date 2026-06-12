"""Cache en disco de las respuestas crudas de Match-V5.

Mientras no hay BD (fase 1), la idempotencia (CLAUDE.md §5) vive aqui: si el
JSON ya esta en data/riot/, no se vuelve a pedir a la API. El crudo completo
(10 participantes, timeline entera) se conserva por si en el futuro queremos
extraer mas campos sin re-descargar.
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

# Un 404 (partida no disponible) se cachea como `null` para no insistir.


def _cached(path: Path, fetch: Callable[[], dict | None]) -> tuple[dict | None, bool]:
    """Devuelve (json, from_cache). Cachea tambien el None del 404."""
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
