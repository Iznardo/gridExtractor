"""gridExtractor read-only API (FastAPI).

Exposes the `loldata` DB as the contract for the frontend. Read-only: no
endpoint writes.

Deployment model: each user runs their OWN private API locally (not a public
service).

Start (dev):
    uvicorn src.api.main:app --reload

Interactive docs (Swagger) at /docs.
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
from src.api.routers import catalog, draft_stats, drafts, games, matchups, picks, replays, scouting, scrims
from src.db.conn import db_kwargs

log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Read-only connection pool: a fresh connection per request would exhaust
    # max_connections under load. autocommit=True + dict_row keep each
    # connection ready for read-only use, with no "idle in transaction" hangs.
    pool = ConnectionPool(
        kwargs={**db_kwargs(), "autocommit": True, "row_factory": dict_row},
        min_size=1,
        max_size=10,
        open=False,
    )
    # wait=False: do not block startup if the DB is not ready yet; the pool
    # retries in the background and ChampMap self-heals on the first miss.
    pool.open()
    app.state.pool = pool

    # Cached champion catalog (id -> name): avoids resolving names against the
    # DB on every draft. ChampMap reloads itself if a key is missing.
    app.state.champ_map = ChampMap(pool)
    try:
        n = app.state.champ_map.reload()
        log.info("champ_map loaded: %d champions", n)
    except Exception as e:
        # DB down at startup: do not bring the API down. ChampMap fills itself
        # on first access.
        log.warning("champ_map not loaded at startup (%s); will load on demand.", e)

    try:
        yield
    finally:
        pool.close()


def create_app() -> FastAPI:
    load_dotenv()
    app = FastAPI(title="gridExtractor API", version="0.1.0", lifespan=lifespan)

    # CORS: the JS frontend runs separately (dev on localhost). Open to any
    # localhost/127.0.0.1 port, consistent with the local private-API model.
    # If the frontend is served from another origin, widen this.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["GET"],
        allow_headers=["*"],
        # The frontend (fetch) needs to read the replay's file name.
        expose_headers=["Content-Disposition"],
    )

    @app.get("/health", tags=["health"])
    def health():
        """Lightweight ping: confirms the API responds and the DB answers.

        200 if the DB responds; 503 otherwise (used by the container healthcheck
        and to let the frontend tell 'API down' from 'no data').
        """
        try:
            with app.state.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return {"status": "ok", "db": "ok"}
        except Exception as e:
            log.warning("health: DB unavailable: %s", e)
            return JSONResponse(
                status_code=503, content={"status": "degraded", "db": "down"}
            )

    for module in (catalog, drafts, draft_stats, scouting, scrims, games, picks, matchups, replays):
        app.include_router(module.router)

    return app


app = create_app()
