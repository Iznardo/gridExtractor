"""Descarga de replays (.rofl) — proxy de streaming.

El navegador pide a NUESTRA API (`/games/{id}/replay`, sin api-key). El backend
descarga la ROFL de GRID con la cabecera `x-api-key` server-side y reenvia los
bytes en streaming. La api-key NUNCA llega al navegador (ni en la URL ni en
cabeceras), asi que no aparece en las DevTools ni en links compartibles.

Endpoint de GRID (lo da el cliente, no grid-minion):
    GET https://api.grid.gg/file-download/replay/riot/series/{series}/games/{n}

La descarga puede ser de decenas de MB: se hace con `requests` + `stream=True`
y se reenvia por chunks. El endpoint es `def` (sync) → FastAPI lo corre en su
threadpool, asi que el streaming no bloquea el event loop.
"""

from __future__ import annotations

import logging
import os
import re

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from psycopg.rows import dict_row

from src.db.conn import get_conn

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
def download_replay(game_id: int):
    api_key = os.environ.get("GRID_API_KEY")
    if not api_key:
        log.error("GRID_API_KEY ausente en el entorno de la API.")
        raise HTTPException(503, "Descarga de replays no configurada en el servidor.")

    # Conexion corta solo para resolver la serie/numero; se cierra antes de
    # empezar el streaming (no retenemos conexion de BD durante la descarga).
    with get_conn() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(_META_SQL, {"game_id": game_id})
            row = cur.fetchone()

    if row is None:
        raise HTTPException(404, "Partida no encontrada.")
    if row["grid_series_id"] is None or row["game_number"] is None:
        raise HTTPException(404, "Esta partida no tiene replay de GRID (p. ej. soloq).")

    url = (
        f"{GRID_BASE}/file-download/replay/riot/series/"
        f"{row['grid_series_id']}/games/{row['game_number']}"
    )

    # La api-key va en cabecera, jamas en la URL — no se loguea aunque se loguee
    # la URL. No logueamos cabeceras.
    upstream = requests.get(
        url,
        headers={"x-api-key": api_key, "Accept": "application/octet-stream"},
        stream=True,
        timeout=(10, 300),
    )

    if upstream.status_code == 404:
        upstream.close()
        raise HTTPException(404, "Replay no disponible en GRID todavia.")
    if upstream.status_code in (401, 403):
        upstream.close()
        log.error("GRID rechazo la api-key al descargar replay (%s).", upstream.status_code)
        raise HTTPException(502, "Error de credenciales con GRID.")
    if upstream.status_code != 200:
        upstream.close()
        raise HTTPException(502, f"GRID devolvio {upstream.status_code}.")

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
