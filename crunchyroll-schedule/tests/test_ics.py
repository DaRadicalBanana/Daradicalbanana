"""Tests for the iCalendar feed."""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ics import build_ics, build_ics_events  # noqa: E402
from app.models import EpisodeRelease, Show, TimeConfidence, WeeklySchedule  # noqa: E402

FUTURE = datetime.now(timezone.utc) + timedelta(days=2)


def _schedule_with(ep: EpisodeRelease, title="Test Show", url="https://cr/x"):
    sched = WeeklySchedule(iso_year=2026, iso_week=27, timezone="America/New_York")
    sched.shows = [Show(route=ep.route, title=title, crunchyroll_url=url, next_scheduled=ep)]
    return sched


def _ep(conf=TimeConfidence.CONFIRMED_SUB, **kw):
    return EpisodeRelease(
        route="test-show", title="Test Show", episode_number=6,
        subtracted_episode_number=None, air_at=FUTURE, confidence=conf,
        length_min=24, streams={"crunchyroll": "https://cr/x"}, **kw,
    )


def test_ics_structure_and_event():
    ics = build_ics(_schedule_with(_ep()))
    assert ics.startswith("BEGIN:VCALENDAR")
    assert ics.rstrip().endswith("END:VCALENDAR")
    assert "BEGIN:VEVENT" in ics and "END:VEVENT" in ics
    assert "SUMMARY:Test Show — Ep 6" in ics
    assert "URL:https://cr/x" in ics
    # CRLF line endings per RFC 5545
    assert "\r\n" in ics


def test_ics_marks_projection_and_jp_fallback():
    proj = build_ics(_schedule_with(_ep(conf=TimeConfidence.PROJECTED)))
    assert "(projected)" in proj
    jp = build_ics(_schedule_with(_ep(conf=TimeConfidence.JP_FALLBACK)))
    assert "JP time?" in jp


def test_ics_skips_shows_without_next():
    sched = WeeklySchedule(iso_year=2026, iso_week=27, timezone="America/New_York")
    sched.shows = [Show(route="x", title="No Next", next_scheduled=None)]
    ics = build_ics(sched)
    assert "BEGIN:VEVENT" not in ics


def test_ics_escapes_special_chars():
    ep = _ep()
    ics = build_ics(_schedule_with(ep, title="Re:Zero; Season, 3"))
    assert "Re:Zero\\; Season\\, 3" in ics


def test_ics_routes_filter():
    sched = WeeklySchedule(iso_year=2026, iso_week=27, timezone="America/New_York")
    sched.shows = [
        Show(route="keep", title="Keep", next_scheduled=_ep()),
        Show(route="drop", title="Drop", next_scheduled=_ep()),
    ]
    ics = build_ics(sched, routes={"keep"})
    assert "SUMMARY:Keep" in ics
    assert "SUMMARY:Drop" not in ics


def test_build_ics_events_from_release_list():
    eps = [
        _ep(),  # route "test-show", episode 6
    ]
    eps[0].title = "Cool Anime"
    ics = build_ics_events(eps, calname="Crunchyroll Schedule (sub)")
    assert ics.startswith("BEGIN:VCALENDAR")
    assert "X-WR-CALNAME:Crunchyroll Schedule (sub)" in ics
    assert "SUMMARY:Cool Anime — Ep 6" in ics
    assert ics.count("BEGIN:VEVENT") == 1


def test_build_ics_events_routes_filter_and_skip_no_time():
    keep = _ep(); keep.route = "keep"; keep.title = "Keep"
    drop = _ep(); drop.route = "drop"; drop.title = "Drop"
    notime = _ep(); notime.route = "keep"; notime.title = "NoTime"; notime.air_at = None
    ics = build_ics_events([keep, drop, notime], routes={"keep"})
    assert "SUMMARY:Keep" in ics
    assert "SUMMARY:Drop" not in ics      # filtered by routes
    assert "SUMMARY:NoTime" not in ics    # skipped (no air_at)
