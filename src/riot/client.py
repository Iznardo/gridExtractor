"""HTTP client for the Riot API.

- Auth via `X-Riot-Token` header (reads RIOT_API_KEY from the environment).
- Local rate limiter with two sliding windows (dev key limits: 20 req/1s and
  100 req/120s, configurable).
- 429 -> wait `Retry-After` and retry. 5xx -> exponential backoff with jitter,
  capped attempts.
- 404 -> returns None (resource does not exist; same convention as grid-minion:
  not an error).
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

# Development key limits. A production key allows raising these.
DEV_KEY_LIMITS = ((20, 1.0), (100, 120.0))


class RiotError(Exception):
    """Unrecoverable Riot API error (4xx other than 404/429, or retries
    exhausted)."""


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
        """GET https://{region}.api.riotgames.com{path}. Returns the parsed
        JSON, or None if the resource does not exist (404)."""
        url = f"https://{region}.api.riotgames.com{path}"
        backoff = 1.0
        for attempt in range(1, self.max_attempts + 1):
            self._throttle()
            try:
                resp = self._session.get(url, params=params, timeout=self.timeout_s)
            except requests.RequestException as e:
                if attempt == self.max_attempts:
                    raise RiotError(f"Network failure on {url}: {e}") from e
                log.warning("Network failure (attempt %d/%d): %s",
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
                log.warning("429 rate limit on %s — waiting %.0fs", path, retry_after)
                time.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                if attempt == self.max_attempts:
                    raise RiotError(f"Persistent {resp.status_code} on {url}")
                log.warning("%d from Riot (attempt %d/%d) on %s",
                            resp.status_code, attempt, self.max_attempts, path)
                time.sleep(backoff + random.uniform(0, backoff))
                backoff *= 2
                continue
            # 400/401/403/415...: unrecoverable. 403 is usually an expired dev key.
            raise RiotError(
                f"{resp.status_code} on {url}: {resp.text[:200]}"
                + (" (expired dev key?)" if resp.status_code == 403 else "")
            )
        raise RiotError(f"Retries exhausted on {url}")
