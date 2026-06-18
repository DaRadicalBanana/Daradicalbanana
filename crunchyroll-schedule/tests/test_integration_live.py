"""End-to-end validation of the LIVE (non-demo) service path against the real
AnimeSchedule v3 response shape captured from production (see debug.json):

  - fields are lowerCamelCase
  - `streams` is a LIST of {platform, name, url}
  - URLs may lack a scheme
  - dates are ISO 8601 with a tz offset, e.g. 2026-06-15T10:00:00-04:00

The HTTP layer is monkeypatched to return this real-shaped data; everything else
is the real production code (normalize_streams, parse_dt, _classify_cr,
_build_shows, window aggregation, ICS). This proves the deployed system works
without needing network access to it.
"""
import asyncio
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.cache import CacheEntry  # noqa: E402
from app.config import Settings  # noqa: E402
from app.ics import build_ics  # noqa: E402
from app.isoweek import current_iso_week  # noqa: E402
from app.models import TimeConfidence  # noqa: E402
from app.service import ScheduleService  # noqa: E402

TZ = "America/New_York"


def _stream(platform: str) -> dict:
    # Real shape: list of objects, URL without scheme.
    return {"platform": platform, "name": platform.title(), "url": f"www.{platform}.com/series/x"}


def _entry(route, ep, dt, platforms, air_type):
    # lowerCamelCase, offset datetime, list-shaped streams — exactly like live.
    iso = dt.strftime("%Y-%m-%dT%H:%M:%S-04:00")
    return {
        "route": route, "title": route.replace("-", " ").title(),
        "romaji": route, "english": route, "native": route,
        "airType": air_type, "airingStatus": "aired", "status": "Ongoing",
        "episodeNumber": ep, "episodes": 12, "lengthMin": 24,
        "episodeDate": iso,
        "delayedFrom": "0001-01-01T00:00:00Z", "delayedUntil": "0001-01-01T00:00:00Z",
        "imageVersionRoute": f"anime/jpg/default/{route}.jpg",
        "streams": [_stream(p) for p in platforms],
    }


def _real_timetable(air_type: str, year: int, week: int):
    """Mimic the live timetable for a week. Three shows:
    - cr-confirmed: on CR, sub time offset from raw  -> CONFIRMED_SUB
    - cr-jpfallback: on CR, sub time == raw time     -> JP_FALLBACK
    - other-platform: Apple/Amazon only              -> excluded
    Episode numbers/dates shift by week so a multi-week window yields last+next.
    """
    monday = date.fromisocalendar(year, week, 1)
    delta = week - current_iso_week(TZ).week
    wed = datetime.combine(monday + timedelta(days=2), time(12, 0))  # local naive
    raw_dt = wed
    if air_type == "raw":
        a_dt, b_dt = raw_dt, raw_dt
    else:  # sub
        a_dt, b_dt = raw_dt + timedelta(hours=1), raw_dt  # cr-jpfallback equals raw
    return [
        _entry("cr-confirmed", max(1, 6 + delta), a_dt, ["crunchyroll", "hidive"], air_type),
        _entry("cr-jpfallback", max(1, 4 + delta), b_dt, ["crunchyroll"], air_type),
        _entry("other-platform", max(1, 8 + delta), raw_dt, ["apple", "amazon"], air_type),
    ]


def _meta():
    return CacheEntry(data=None, fetched_at=datetime.now(timezone.utc), age_sec=0, fresh=True)


def _live_service() -> ScheduleService:
    settings = Settings(
        animeschedule_token="test-token", timezone=TZ, rate_per_min=30,
        timetable_ttl=10, seasonal_ttl=10, cache_dir=None, demo_mode=False,
    )
    # cache_dir None would break FileCache; give a temp dir.
    import tempfile
    from pathlib import Path
    settings = Settings(**{**settings.__dict__, "cache_dir": Path(tempfile.mkdtemp())})
    svc = ScheduleService(settings)

    async def fake_timetable(air_type, year, week, tz):
        return _real_timetable(air_type, year, week), _meta()

    async def fake_seasonal(season, year):
        return []  # skip AniList enrichment

    svc.animeschedule.timetable = fake_timetable
    svc.anilist.seasonal = fake_seasonal
    return svc


def _run():
    svc = _live_service()
    cw = current_iso_week(TZ)
    return svc, asyncio.run(svc.weekly(cw.year, cw.week, "sub"))


def test_live_path_is_not_demo():
    _, res = _run()
    assert res.air_type == "sub"
    assert not any(f.source == "sample" for f in res.freshness)
    assert any(f.source == "animeschedule" for f in res.freshness)
    assert not any(w.startswith("SAMPLE DATA") for w in res.warnings)
    assert not any(w.startswith("DEBUG:") for w in res.warnings)  # not empty


def test_live_path_filters_to_crunchyroll():
    _, res = _run()
    routes = {s.route for s in res.shows}
    assert "cr-confirmed" in routes
    assert "cr-jpfallback" in routes
    assert "other-platform" not in routes  # Apple/Amazon-only excluded


def test_live_path_grid_and_times():
    _, res = _run()
    all_eps = [e for eps in res.days.values() for e in eps]
    assert all_eps, "grid should be populated"
    cr = next(e for e in all_eps if e.route == "cr-confirmed")
    # 12:00 + 1h sub offset = 13:00 EDT -> 17:00 UTC
    assert cr.air_at.astimezone(timezone.utc).hour == 17
    # watch link got an https scheme
    assert cr.streams["crunchyroll"].startswith("https://")


def test_live_path_jp_fallback_classification():
    _, res = _run()
    all_eps = [e for eps in res.days.values() for e in eps]
    conf = {e.route: e.confidence for e in all_eps}
    assert conf["cr-jpfallback"] == TimeConfidence.JP_FALLBACK
    assert conf["cr-confirmed"] == TimeConfidence.CONFIRMED_SUB


def test_live_path_shows_have_last_and_next():
    _, res = _run()
    both = [s for s in res.shows if s.last_released and s.next_scheduled]
    assert both, "window aggregation should give last + next"


def test_live_path_cover_from_image_route():
    _, res = _run()
    cr = next(s for s in res.shows if s.route == "cr-confirmed")
    assert cr.cover_image_url is not None
    assert cr.cover_image_url.endswith("anime/jpg/default/cr-confirmed.jpg")
    assert cr.cover_image_url.startswith("https://")


def test_live_path_ics_feed():
    _, res = _run()
    ics = build_ics(res)
    assert ics.count("BEGIN:VEVENT") >= 1
    assert "crunchyroll.com" in ics  # real watch URL present
