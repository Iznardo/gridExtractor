"""Replay download (.rofl) — streaming proxy.

The browser asks OUR API (`/games/{id}/replay`, no api-key). The backend
downloads the ROFL from GRID with the `x-api-key` header server-side and streams
the bytes back. The api-key NEVER reaches the browser (neither in the URL nor in
headers), so it does not show up in DevTools or shareable links.

GRID endpoint (provided by the client, not grid-minion):
    GET https://api.grid.gg/file-download/replay/riot/series/{series}/games/{n}

A download can be tens of MB: done with `requests` + `stream=True` and forwarded
in chunks. The endpoint is `def` (sync) so FastAPI runs it in its threadpool,
keeping the streaming off the event loop.
"""

from __future__ import annotations

import logging
import os
import re

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

log = logging.getLogger("api.replays")
router = APIRouter(tags=["replays"])

GRID_BASE = "https://api.grid.gg"
CHUNK = 1 << 16  # 64 KiB

_META_SQL = """
SELECT g.grid_series_id, g.game_number, g.date, g.game_type,
       t1.tag AS t1_tag, t1.name AS t1_name,
       t2.tag AS t2_tag, t2.name AS t2_name
FROM games g
LEFT JOIN teams t1 ON t1.id = g.team1_id
LEFT JOIN teams t2 ON t2.id = g.team2_id
WHERE g.id = %(game_id)s
"""


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", s).strip("-") or "team"


def _filename(row: dict) -> str:
    t1 = _slug(row["t1_tag"] or row["t1_name"] or "BLUE")
    t2 = _slug(row["t2_tag"] or row["t2_name"] or "RED")
    return f"{t1}_vs_{t2}_{row['date']}_G{row['game_number']}.rofl"


@router.get("/games/{game_id}/replay")
def download_replay(game_id: int, request: Request):
    api_key = os.environ.get("GRID_API_KEY")
    if not api_key:
        log.error("GRID_API_KEY missing from the API environment.")
        raise HTTPException(503, "Replay download not configured on the server.")

    # Short pool connection only to resolve series/number; returned to the pool
    # BEFORE streaming starts (we do not hold a connection during the download,
    # which can take minutes and would exhaust the pool).
    with request.app.state.pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_META_SQL, {"game_id": game_id})
            row = cur.fetchone()

    if row is None:
        raise HTTPException(404, "Game not found.")
    if row["grid_series_id"] is None or row["game_number"] is None:
        raise HTTPException(404, "This game has no GRID replay (e.g. soloq).")

    url = (
        f"{GRID_BASE}/file-download/replay/riot/series/"
        f"{row['grid_series_id']}/games/{row['game_number']}"
    )

    # The api-key goes in a header, never in the URL — it is not logged even if
    # the URL is. We do not log headers.
    upstream = requests.get(
        url,
        headers={"x-api-key": api_key, "Accept": "application/octet-stream"},
        stream=True,
        timeout=(10, 300),
    )

    if upstream.status_code == 404:
        upstream.close()
        raise HTTPException(404, "Replay not available on GRID yet.")
    if upstream.status_code in (401, 403):
        upstream.close()
        log.error("GRID rejected the api-key on replay download (%s).", upstream.status_code)
        raise HTTPException(502, "Credential error with GRID.")
    if upstream.status_code != 200:
        upstream.close()
        raise HTTPException(502, f"GRID returned {upstream.status_code}.")

    def stream():
        try:
            for chunk in upstream.iter_content(CHUNK):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    headers = {"Content-Disposition": f'attachment; filename="{_filename(row)}"'}
    clen = upstream.headers.get("Content-Length")
    if clen:
        headers["Content-Length"] = clen

    return StreamingResponse(
        stream(), media_type="application/octet-stream", headers=headers
    )
