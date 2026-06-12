"""Cliente HTTP para la Riot API (RIOT_API.md §2-§5).

- Auth por cabecera `X-Riot-Token` (lee RIOT_API_KEY del entorno).
- Rate limiter local con dos ventanas deslizantes (limites de dev key:
  20 req/1s y 100 req/120s, configurables).
- 429 -> espera `Retry-After` y reintenta. 5xx -> backoff exponencial con
  jitter. Tope de intentos.
- 404 -> devuelve None (recurso inexistente; misma convencion que
  grid-minion: no es un error).
"""

from __future__ import annotations

import collections
import logging
import os
import random
import time
from typing import Any

import requests

log = logging.getLogger("riot")

# Limites de una development key. Una production key permite subirlos.
DEV_KEY_LIMITS = ((20, 1.0), (100, 120.0))


class RiotError(Exception):
    """Error no recuperable de la Riot API (4xx distinto de 404/429, o
    reintentos agotados)."""


class _SlidingWindow:
    def __init__(self, max_requests: int, period_s: float):
        self.max_requests = max_requests
        self.period_s = period_s
        self.timestamps: collections.deque[float] = collections.deque()

    def wait_time(self, now: float) -> float:
        while self.timestamps and now - self.timestamps[0] >= self.period_s:
            self.timestamps.popleft()
        if len(self.timestamps) < self.max_requests:
            return 0.0
        return self.timestamps[0] + self.period_s - now

    def record(self, now: float) -> None:
        self.timestamps.append(now)


class RiotClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        limits: tuple[tuple[int, float], ...] = DEV_KEY_LIMITS,
        timeout_s: float = 15.0,
        max_attempts: int = 5,
    ):
        self.api_key = api_key or os.environ["RIOT_API_KEY"]
        self.timeout_s = timeout_s
        self.max_attempts = max_attempts
        self._windows = [_SlidingWindow(n, p) for n, p in limits]
        self._session = requests.Session()
        self._session.headers["X-Riot-Token"] = self.api_key

    def _throttle(self) -> None:
        while True:
            now = time.monotonic()
            wait = max(w.wait_time(now) for w in self._windows)
            if wait <= 0:
                break
            time.sleep(wait)
        now = time.monotonic()
        for w in self._windows:
            w.record(now)

    def get(
        self, region: str, path: str, params: dict[str, Any] | None = None
    ) -> Any | None:
        """GET https://{region}.api.riotgames.com{path}. Devuelve el JSON
        parseado, o None si el recurso no existe (404)."""
        url = f"https://{region}.api.riotgames.com{path}"
        backoff = 1.0
        for attempt in range(1, self.max_attempts + 1):
            self._throttle()
            try:
                resp = self._session.get(url, params=params, timeout=self.timeout_s)
            except requests.RequestException as e:
                if attempt == self.max_attempts:
                    raise RiotError(f"Fallo de red en {url}: {e}") from e
                log.warning("Fallo de red (intento %d/%d): %s",
                            attempt, self.max_attempts, e)
                time.sleep(backoff + random.uniform(0, backoff))
                backoff *= 2
                continue

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", backoff))
                log.warning("429 rate limit en %s — esperando %.0fs", path, retry_after)
                time.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                if attempt == self.max_attempts:
                    raise RiotError(f"{resp.status_code} persistente en {url}")
                log.warning("%d de Riot (intento %d/%d) en %s",
                            resp.status_code, attempt, self.max_attempts, path)
                time.sleep(backoff + random.uniform(0, backoff))
                backoff *= 2
                continue
            # 400/401/403/415...: no recuperable. 403 suele ser dev key caducada.
            raise RiotError(
                f"{resp.status_code} en {url}: {resp.text[:200]}"
                + (" (¿dev key caducada?)" if resp.status_code == 403 else "")
            )
        raise RiotError(f"Reintentos agotados en {url}")
