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
    demo_mode: bool
    debug_enabled: bool = False  # exposes /api/debug; keep off in production
    img_base: str = "https://img.animeschedule.net/production/assets/public/img/"

    @property
    def has_token(self) -> bool:
        return bool(self.animeschedule_token)


def _truthy(v: str | None) -> bool | None:
    if v is None:
        return None
    return v.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    token = os.getenv("ANIMESCHEDULE_TOKEN") or None
    demo_override = _truthy(os.getenv("APP_DEMO"))
    # Demo mode renders sample data with no network. Default it ON when there's
    # no token so the app is always runnable; an explicit APP_DEMO wins.
    demo = demo_override if demo_override is not None else (token is None)
    return Settings(
        animeschedule_token=token,
        timezone=os.getenv("APP_TIMEZONE", "America/New_York"),
        rate_per_min=int(os.getenv("APP_RATE_PER_MIN", "30")),
        timetable_ttl=int(os.getenv("APP_TIMETABLE_TTL", "21600")),
        seasonal_ttl=int(os.getenv("APP_SEASONAL_TTL", "86400")),
        cache_dir=Path(os.getenv("APP_CACHE_DIR", str(Path(__file__).resolve().parent.parent / ".cache"))),
        demo_mode=demo,
        debug_enabled=bool(_truthy(os.getenv("APP_DEBUG"))),
        # Base URL prefix for AnimeSchedule cover images (entry.imageVersionRoute
        # is appended). Configurable in case the CDN path changes; images fail
        # gracefully in the UI if this is wrong.
        img_base=os.getenv(
            "ANIMESCHEDULE_IMG_BASE",
            "https://img.animeschedule.net/production/assets/public/img/",
        ),
    )


settings = load_settings()
