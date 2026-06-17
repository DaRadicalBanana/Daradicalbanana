"""Dead-simple file-based TTL cache with freshness metadata + serve-stale.

AnimeSchedule is a no-SLA dependency: we cache aggressively, and on upstream
failure we fall back to the last good cached payload (marked stale) rather than
erroring. Every cached entry records `fetched_at` so the UI can show freshness.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class CacheEntry:
    data: Any
    fetched_at: datetime
    age_sec: float
    fresh: bool


class FileCache:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self.root / f"{digest}.json"

    def get(self, key: str, ttl: int) -> CacheEntry | None:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            raw = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        fetched = float(raw.get("fetched_at_ts", 0))
        age = time.time() - fetched
        return CacheEntry(
            data=raw.get("data"),
            fetched_at=datetime.fromtimestamp(fetched, tz=timezone.utc),
            age_sec=age,
            fresh=age <= ttl,
        )

    def set(self, key: str, data: Any) -> None:
        p = self._path(key)
        payload = {"fetched_at_ts": time.time(), "data": data}
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload))
        tmp.replace(p)
