"""Async token-bucket limiter + 429 backoff helper.

Per the brief: design to the *lower* upstream limit (AniList ~30/min in its
degraded state) with exponential backoff on 429s, honoring Retry-After /
X-RateLimit-Reset when present.
"""
from __future__ import annotations

import asyncio
import time


class RateLimiter:
    def __init__(self, per_min: int):
        self.capacity = max(1, per_min)
        self.tokens = float(self.capacity)
        self.refill_per_sec = self.capacity / 60.0
        self.updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self.tokens = min(
                    self.capacity, self.tokens + (now - self.updated) * self.refill_per_sec
                )
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                wait = (1 - self.tokens) / self.refill_per_sec
                await asyncio.sleep(wait)


def retry_after_seconds(headers: dict[str, str], attempt: int) -> float:
    """How long to wait after a 429, preferring server-provided hints."""
    h = {k.lower(): v for k, v in headers.items()}
    ra = h.get("retry-after")
    if ra:
        try:
            return float(ra)
        except ValueError:
            pass
    reset = h.get("x-ratelimit-reset")
    if reset:
        try:
            delta = float(reset) - time.time()
            if delta > 0:
                return min(delta, 90.0)
        except ValueError:
            pass
    # Exponential backoff: 2,4,8,16 ... capped.
    return min(2 ** attempt, 60)
