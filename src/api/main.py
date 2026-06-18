"""API read-only de gridExtractor (FastAPI).

Expone la BD `loldata` como contrato para el front (memoria
`frontend_api_decision`). Solo lectura: ningun endpoint escribe.

Arranque (dev):
    uvicorn src.api.main:app --reload

Docs interactivas (Swagger) en /docs.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row

from src.api.routers import catalog, drafts, games, matchups, picks, replays, scouting
from src.db.conn import get_conn

log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Catalogo de campeones (id -> name) cacheado una vez: ~170 filas, evita
    # 20 JOINs por draft al resolver nombres.
    with get_conn() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM champions")
            app.state.champ_map = {r["id"]: r["name"] for r in cur.fetchall()}
    log.info("champ_map cargado: %d campeones", len(app.state.champ_map))
    yield


def create_app() -> FastAPI:
    load_dotenv()
    app = FastAPI(title="gridExtractor API", version="0.1.0", lifespan=lifespan)

    # CORS: el front JS corre aparte (dev en localhost). Abierto a cualquier
    # puerto de localhost/127.0.0.1.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["GET"],
        allow_headers=["*"],
        # El front (fetch) necesita leer el nombre de fichero de la replay.
        expose_headers=["Content-Disposition"],
    )

    for module in (catalog, drafts, scouting, games, picks, matchups, replays):
        app.include_router(module.router)

    return app


app = create_app()
