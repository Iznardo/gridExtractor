"""API read-only de gridExtractor (FastAPI).

Expone la BD `loldata` como contrato para el front (memoria
`frontend_api_decision`). Solo lectura: ningun endpoint escribe.

Modelo de despliegue: cada usuario corre su PROPIA API privada en local
(no es un servicio publico). Ver `api_audit.md`.

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
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from src.api.deps import ChampMap
from src.api.routers import catalog, draft_stats, drafts, games, matchups, picks, replays, scouting
from src.db.conn import db_kwargs

log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pool de conexiones read-only: una conexion nueva por request agota
    # max_connections bajo carga (audit A1). autocommit=True + dict_row dejan
    # cada conexion lista para solo-lectura (audit M4), sin transacciones
    # colgadas "idle in transaction".
    pool = ConnectionPool(
        kwargs={**db_kwargs(), "autocommit": True, "row_factory": dict_row},
        min_size=1,
        max_size=10,
        open=False,
    )
    # wait=False: no bloquear el arranque si la BD aun no esta lista (audit M1);
    # el pool reintenta en background y ChampMap se auto-cura en el primer miss.
    pool.open()
    app.state.pool = pool

    # Catalogo de campeones (id -> name) cacheado: evita resolver nombres contra
    # la BD en cada draft. ChampMap se auto-recarga si falta una clave.
    app.state.champ_map = ChampMap(pool)
    try:
        n = app.state.champ_map.reload()
        log.info("champ_map cargado: %d campeones", n)
    except Exception as e:
        # BD caida al arrancar: no tumbar la API. ChampMap se rellenara solo
        # en el primer acceso (audit M1).
        log.warning("champ_map no cargado al arranque (%s); se cargara bajo demanda.", e)

    try:
        yield
    finally:
        pool.close()


def create_app() -> FastAPI:
    load_dotenv()
    app = FastAPI(title="gridExtractor API", version="0.1.0", lifespan=lifespan)

    # CORS: el front JS corre aparte (dev en localhost). Abierto a cualquier
    # puerto de localhost/127.0.0.1 — coherente con el modelo de API privada
    # local. Si se sirve el front desde otro origen, ampliar aqui.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["GET"],
        allow_headers=["*"],
        # El front (fetch) necesita leer el nombre de fichero de la replay.
        expose_headers=["Content-Disposition"],
    )

    @app.get("/health", tags=["health"])
    def health():
        """Ping ligero: confirma que la API responde y la BD contesta.

        200 si la BD responde; 503 si no (sirve para healthcheck de contenedor
        y para que el front distinga 'API caida' de 'sin datos').
        """
        try:
            with app.state.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return {"status": "ok", "db": "ok"}
        except Exception as e:
            log.warning("health: BD no disponible: %s", e)
            return JSONResponse(
                status_code=503, content={"status": "degraded", "db": "down"}
            )

    for module in (catalog, drafts, draft_stats, scouting, games, picks, matchups, replays):
        app.include_router(module.router)

    return app


app = create_app()
