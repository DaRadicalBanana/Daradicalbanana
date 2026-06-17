"""Centralized configuration, loaded from environment.

Secrets (the AnimeSchedule token) are read from the environment only — never
hardcoded and never committed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    # Loads a local .env if present; in the web sandbox the value comes from a
    # configured environment secret instead.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # dotenv optional at runtime
    pass

ANIMESCHEDULE_BASE = "https://animeschedule.net/api/v3"
ANILIST_BASE = "https://graphql.anilist.co"


@dataclass(frozen=True)
class Settings:
    animeschedule_token: str | None
    timezone: str
    rate_per_min: int
    timetable_ttl: int
    seasonal_ttl: int
    cache_dir: Path

    @property
    def has_token(self) -> bool:
        return bool(self.animeschedule_token)


def load_settings() -> Settings:
    return Settings(
        animeschedule_token=os.getenv("ANIMESCHEDULE_TOKEN") or None,
        timezone=os.getenv("APP_TIMEZONE", "America/New_York"),
        rate_per_min=int(os.getenv("APP_RATE_PER_MIN", "30")),
        timetable_ttl=int(os.getenv("APP_TIMETABLE_TTL", "21600")),
        seasonal_ttl=int(os.getenv("APP_SEASONAL_TTL", "86400")),
        cache_dir=Path(os.getenv("APP_CACHE_DIR", str(Path(__file__).resolve().parent.parent / ".cache"))),
    )


settings = load_settings()
