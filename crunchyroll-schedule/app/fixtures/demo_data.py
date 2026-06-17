"""Generate PascalCase sample timetables anchored to a given ISO week.

The shape mirrors the live AnimeSchedule v3 timetable response so the same
normalization code path runs on demo data. Times are computed from the ISO
week's Monday so the calendar always looks alive (some episodes already
released, some upcoming) whatever week is viewed.

The sample set intentionally includes:
  - confirmed CR sub times (offset after the raw/JP broadcast),
  - a JP-fallback case (release time == raw time) -> "CR time unconfirmed",
  - a multi-episode drop (SubtractedEpisodeNumber),
  - a delayed entry (DelayedUntil set; null dates use the 0001 sentinel),
  - a non-Crunchyroll show (must be filtered out),
  - shows with and without an English dub (so the Sub/Dub toggle differs).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

_ZERO = "0001-01-01T00:00:00Z"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class _ShowCfg:
    title: str
    route: str
    weekday: int          # 0=Mon
    hour: int
    minute: int
    ep_no: int
    streams: dict
    sub_fallback: bool    # sub time == raw time
    sub_off: int          # minutes after raw when not a fallback
    has_dub: bool
    dub_fallback: bool
    dub_off: int
    subtracted: int | None = None
    delayed: bool = False


_CR = "https://www.crunchyroll.com/series/"
_SHOWS = [
    _ShowCfg("Aetherbound Chronicle", "aetherbound-chronicle", 0, 14, 0, 7, {"crunchyroll": _CR + "aetherbound"}, False, 60, True, False, 180),
    _ShowCfg("Neon Garden Requiem", "neon-garden-requiem", 1, 15, 30, 6, {"crunchyroll": _CR + "neon-garden", "hidive": "https://www.hidive.com/x"}, False, 30, False, False, 0),
    _ShowCfg("The Clockwork Apprentice", "clockwork-apprentice", 2, 13, 0, 8, {"crunchyroll": _CR + "clockwork"}, True, 0, True, True, 0),
    _ShowCfg("Saltwind Voyagers", "saltwind-voyagers", 3, 16, 0, 7, {"crunchyroll": _CR + "saltwind"}, False, 90, True, False, 240),
    _ShowCfg("Double Feature: Mirror Twins", "mirror-twins", 4, 12, 0, 12, {"crunchyroll": _CR + "mirror-twins"}, False, 45, True, False, 200, subtracted=11),
    _ShowCfg("Hollow Crown Saga", "hollow-crown-saga", 5, 17, 0, 5, {"crunchyroll": _CR + "hollow-crown"}, False, 60, False, False, 0, delayed=True),
    _ShowCfg("Petal Static", "petal-static", 6, 11, 0, 9, {"crunchyroll": _CR + "petal-static"}, False, 30, True, False, 150),
    _ShowCfg("Streaming-Exclusive Elsewhere", "elsewhere", 2, 18, 0, 4, {"netflix": "https://www.netflix.com/title/x"}, False, 0, False, False, 0),
]


def _entry(s: _ShowCfg, ep_no, subtracted, episode_date, air_type) -> dict:
    base = {
        "Title": s.title,
        "Route": s.route,
        "Romaji": s.title,
        "English": s.title,
        "AirType": air_type,
        "AiringStatus": "airing",
        "EpisodeNumber": ep_no,
        "SubtractedEpisodeNumber": subtracted if subtracted is not None else 0,
        "Episodes": 12,
        "LengthMin": 24,
        "EpisodeDate": _iso(episode_date),
        "Streams": s.streams,
        "DelayedFrom": _ZERO,
        "DelayedUntil": _ZERO,
    }
    if s.delayed:
        base["AiringStatus"] = "delayed"
        base["DelayedUntil"] = _iso(episode_date + timedelta(days=7))
    return base


# Anchor week: episode numbers in _SHOWS are "as of" this ISO week; other weeks
# increment/decrement so a multi-week window shows realistic last/next episodes.
_ANCHOR_WEEK = 27


def build_demo_timetables(year: int, week: int, air_type: str = "sub"):
    """Return (primary_entries, raw_entries) as lists of PascalCase dicts.

    `primary_entries` is the `sub` or `dub` timetable per `air_type`; for dub,
    only shows that have a dub are included (so the toggle visibly differs).
    `raw_entries` is always the full raw/JP timetable, used for fallback
    classification.
    """
    monday = date.fromisocalendar(year, week, 1)
    delta = week - _ANCHOR_WEEK
    primary: list[dict] = []
    raw: list[dict] = []
    for s in _SHOWS:
        eff_ep = max(1, s.ep_no + delta)
        eff_sub = max(1, s.subtracted + delta) if s.subtracted is not None else None
        day = monday + timedelta(days=s.weekday)
        raw_dt = datetime.combine(day, time(s.hour, s.minute), tzinfo=timezone.utc)
        raw.append(_entry(s, eff_ep, eff_sub, raw_dt, "raw"))

        if air_type == "dub":
            if not s.has_dub:
                continue
            dt = raw_dt if s.dub_fallback else raw_dt + timedelta(minutes=s.dub_off)
            primary.append(_entry(s, eff_ep, eff_sub, dt, "dub"))
        else:
            dt = raw_dt if s.sub_fallback else raw_dt + timedelta(minutes=s.sub_off)
            primary.append(_entry(s, eff_ep, eff_sub, dt, "sub"))
    return primary, raw
