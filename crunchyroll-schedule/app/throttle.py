"""Tiny in-memory per-IP fixed-window rate limiter.

Suitable for a single-process deployment (Render Starter runs WEB_CONCURRENCY=1).
No external deps; O(1) per check with opportunistic pruning to bound memory.
"""
from __future__ import annotations

import time


class IPRateLimiter:
    def __init__(self, limit: int, window: float = 60.0):
        self.limit = limit
        self.window = window
        self._hits: dict[str, tuple[float, int]] = {}  # ip -> (window_start, count)

    def check(self, ip: str, now: float | None = None) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.time() if now is None else now
        start, count = self._hits.get(ip, (now, 0))
        if now - start >= self.window:
            start, count = now, 0
        count += 1
        self._hits[ip] = (start, count)
        if len(self._hits) > 10000:
            self._prune(now)
        if count <= self.limit:
            return True, 0
        return False, int(self.window - (now - start)) + 1

    def _prune(self, now: float) -> None:
        self._hits = {
            ip: v for ip, v in self._hits.items() if now - v[0] < self.window
        }


def client_ip(request) -> str:
    """Best-effort client IP behind Render's proxy (X-Forwarded-For left-most)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
