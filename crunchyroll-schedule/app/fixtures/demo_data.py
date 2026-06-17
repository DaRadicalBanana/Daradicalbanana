"""Generate PascalCase sample timetables anchored to a given ISO week.

The shape mirrors the live AnimeSchedule v3 timetable response so the same
normalization code path runs on demo data. Times are computed from the ISO
week's Monday so the calendar always looks alive (some episodes already
released, some upcoming) whatever week is viewed.

SAMPLE_SUB intentionally includes:
  - confirmed CR sub times (SubTime offset after the raw/JP broadcast),
  - one JP-fallback case (sub time == raw time) -> "CR sub time unconfirmed",
  - a multi-episode drop (SubtractedEpisodeNumber),
  - a delayed entry (DelayedUntil set; null dates use the 0001 sentinel),
  - a non-Crunchyroll show (must be filtered out).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

_ZERO = "0001-01-01T00:00:00Z"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# (title, route, weekday[0=Mon], hour_utc, minute, ep_no, streams, fallback, sub_offset_min, subtracted, delayed)
_SHOWS = [
    ("Aetherbound Chronicle", "aetherbound-chronicle", 0, 14, 0, 7, {"crunchyroll": "https://www.crunchyroll.com/series/aetherbound"}, False, 60, None, False),
    ("Neon Garden Requiem", "neon-garden-requiem", 1, 15, 30, 6, {"crunchyroll": "https://www.crunchyroll.com/series/neon-garden", "hidive": "https://www.hidive.com/x"}, False, 30, None, False),
    ("The Clockwork Apprentice", "clockwork-apprentice", 2, 13, 0, 8, {"crunchyroll": "https://www.crunchyroll.com/series/clockwork"}, True, 0, None, False),  # JP fallback
    ("Saltwind Voyagers", "saltwind-voyagers", 3, 16, 0, 7, {"crunchyroll": "https://www.crunchyroll.com/series/saltwind"}, False, 90, None, False),
    ("Double Feature: Mirror Twins", "mirror-twins", 4, 12, 0, 12, {"crunchyroll": "https://www.crunchyroll.com/series/mirror-twins"}, False, 45, 11, False),  # multi-ep drop 11-12
    ("Hollow Crown Saga", "hollow-crown-saga", 5, 17, 0, 5, {"crunchyroll": "https://www.crunchyroll.com/series/hollow-crown"}, False, 60, None, True),  # delayed
    ("Petal Static", "petal-static", 6, 11, 0, 9, {"crunchyroll": "https://www.crunchyroll.com/series/petal-static"}, False, 30, None, False),
    ("Streaming-Exclusive Elsewhere", "elsewhere", 2, 18, 0, 4, {"netflix": "https://www.netflix.com/title/x"}, False, 0, None, False),  # not on CR -> filtered
]


def _entry(monday: date, title, route, wd, hour, minute, ep_no, streams, episode_date, *, subtracted, delayed, air_type):
    base = {
        "Title": title,
        "Route": route,
        "Romaji": title,
        "English": title,
        "AirType": air_type,
        "AiringStatus": "airing",
        "EpisodeNumber": ep_no,
        "SubtractedEpisodeNumber": subtracted if subtracted is not None else 0,
        "Episodes": 12,
        "LengthMin": 24,
        "EpisodeDate": _iso(episode_date),
        "Streams": streams,
        "DelayedFrom": _ZERO,
        "DelayedUntil": _ZERO,
    }
    if delayed:
        base["AiringStatus"] = "delayed"
        base["DelayedUntil"] = _iso(episode_date + timedelta(days=7))
    return base


# Anchor week: episode numbers in _SHOWS are "as of" this ISO week; other weeks
# increment/decrement so a multi-week window shows realistic last/next episodes.
_ANCHOR_WEEK = 27


def build_demo_timetables(year: int, week: int):
    """Return (sub_entries, raw_entries) as lists of PascalCase dicts."""
    monday = date.fromisocalendar(year, week, 1)
    delta = week - _ANCHOR_WEEK
    sub: list[dict] = []
    raw: list[dict] = []
    for (title, route, wd, hour, minute, ep_no, streams, fallback, sub_off, subtracted, delayed) in _SHOWS:
        eff_ep = max(1, ep_no + delta)
        eff_sub = (max(1, subtracted + delta) if subtracted is not None else None)
        day = monday + timedelta(days=wd)
        raw_dt = datetime.combine(day, time(hour, minute), tzinfo=timezone.utc)
        sub_dt = raw_dt if fallback else raw_dt + timedelta(minutes=sub_off)
        raw.append(_entry(monday, title, route, wd, hour, minute, eff_ep, streams, raw_dt, subtracted=eff_sub, delayed=delayed, air_type="raw"))
        sub.append(_entry(monday, title, route, wd, hour, minute, eff_ep, streams, sub_dt, subtracted=eff_sub, delayed=delayed, air_type="sub"))
    return sub, raw
