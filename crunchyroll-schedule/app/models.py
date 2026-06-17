"""Normalized data model surfaced to the UI.

Upstream shapes are deliberately NOT leaked past the client layer. Everything the
frontend sees is one of these, with timing confidence made explicit.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


class TimeConfidence(str, enum.Enum):
    # AnimeSchedule gave a dedicated CR sub time.
    CONFIRMED_SUB = "confirmed_sub"
    # Sub time unknown; AnimeSchedule fell back to the raw/JP broadcast time.
    # UI must label: "JP broadcast time (CR sub time unconfirmed)".
    JP_FALLBACK = "jp_fallback"
    # Future episode whose date is a projection (may shift).
    PROJECTED = "projected"
    # No usable time at all.
    UNKNOWN = "unknown"


@dataclass
class EpisodeRelease:
    route: str                      # AnimeSchedule slug, our join key fallback
    title: str
    episode_number: int | None
    subtracted_episode_number: int | None  # for multi-episode drops
    air_at: datetime | None         # aware UTC; None if no known time
    confidence: TimeConfidence
    length_min: int | None = None
    airing_status: str | None = None
    delayed_from: datetime | None = None
    delayed_until: datetime | None = None
    streams: dict[str, str] = field(default_factory=dict)

    @property
    def on_crunchyroll(self) -> bool:
        return any(k.lower() == "crunchyroll" for k in self.streams)


@dataclass
class Show:
    route: str
    title: str
    anilist_id: int | None = None
    mal_id: int | None = None
    cover_image_url: str | None = None
    crunchyroll_url: str | None = None
    # Last episode that has already released (<= now) and next scheduled (> now).
    last_released: EpisodeRelease | None = None
    next_scheduled: EpisodeRelease | None = None


@dataclass
class Freshness:
    fetched_at: datetime | None
    source: str
    stale: bool
    note: str | None = None


@dataclass
class WeeklySchedule:
    iso_year: int
    iso_week: int
    timezone: str
    is_current_week: bool = False
    # weekday index 0=Mon .. 6=Sun -> releases that fall on that local day
    days: dict[int, list[EpisodeRelease]] = field(default_factory=dict)
    shows: list[Show] = field(default_factory=list)
    freshness: list[Freshness] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def to_jsonable(obj: Any) -> Any:
    """asdict + datetime/enum serialization for the API layer."""
    def convert(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, enum.Enum):
            return o.value
        if isinstance(o, dict):
            return {k: convert(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [convert(v) for v in o]
        return o

    if hasattr(obj, "__dataclass_fields__"):
        return convert(asdict(obj))
    return convert(obj)
