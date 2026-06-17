"""Tests for demo mode: it must render a populated, correct schedule offline."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings  # noqa: E402
from app.fixtures.demo_data import build_demo_timetables  # noqa: E402
from app.isoweek import iso_week_of  # noqa: E402
from app.models import TimeConfidence  # noqa: E402
from app.service import ScheduleService  # noqa: E402


def _demo_settings(tmp_path) -> Settings:
    return Settings(
        animeschedule_token=None,
        timezone="America/New_York",
        rate_per_min=30,
        timetable_ttl=10,
        seasonal_ttl=10,
        cache_dir=tmp_path,
        demo_mode=True,
    )


def test_demo_filters_non_crunchyroll_and_populates(tmp_path):
    svc = ScheduleService(_demo_settings(tmp_path))
    iw = iso_week_of(2026, 7, 1)
    result = asyncio.run(svc.weekly(iw.year, iw.week))

    routes = {s.route for s in result.shows}
    assert routes, "demo should produce shows"
    # Netflix-only sample must be filtered out; CR ones kept.
    assert "elsewhere" not in routes
    assert "aetherbound-chronicle" in routes
    # Sample-data warning is surfaced first.
    assert result.warnings and result.warnings[0].startswith("SAMPLE DATA")
    assert any(f.source == "sample" for f in result.freshness)


def test_demo_flags_jp_fallback(tmp_path):
    svc = ScheduleService(_demo_settings(tmp_path))
    iw = iso_week_of(2026, 7, 1)
    result = asyncio.run(svc.weekly(iw.year, iw.week))

    all_eps = [e for eps in result.days.values() for e in eps]
    confidences = {e.route: e.confidence for e in all_eps}
    # The clockwork-apprentice fixture has sub time == raw time -> JP fallback.
    assert confidences.get("clockwork-apprentice") == TimeConfidence.JP_FALLBACK
    # A normal CR show with an offset sub time is confirmed.
    assert confidences.get("aetherbound-chronicle") == TimeConfidence.CONFIRMED_SUB


def test_demo_multi_episode_drop(tmp_path):
    sub, _ = build_demo_timetables(2026, 27)
    mirror = next(e for e in sub if e["Route"] == "mirror-twins")
    assert mirror["SubtractedEpisodeNumber"] == 11
    assert mirror["EpisodeNumber"] == 12


def test_demo_anchored_to_requested_week(tmp_path):
    sub_a, _ = build_demo_timetables(2026, 27)
    sub_b, _ = build_demo_timetables(2026, 30)
    # Different weeks -> different episode dates.
    a = {e["Route"]: e["EpisodeDate"] for e in sub_a}
    b = {e["Route"]: e["EpisodeDate"] for e in sub_b}
    assert a["aetherbound-chronicle"] != b["aetherbound-chronicle"]


def test_demo_episode_numbers_increment_across_weeks():
    sub_27, _ = build_demo_timetables(2026, 27)
    sub_28, _ = build_demo_timetables(2026, 28)
    e27 = next(e for e in sub_27 if e["Route"] == "aetherbound-chronicle")["EpisodeNumber"]
    e28 = next(e for e in sub_28 if e["Route"] == "aetherbound-chronicle")["EpisodeNumber"]
    assert e28 == e27 + 1


def test_demo_dub_excludes_shows_without_dub():
    sub, _ = build_demo_timetables(2026, 27, "sub")
    dub, _ = build_demo_timetables(2026, 27, "dub")
    sub_routes = {e["Route"] for e in sub}
    dub_routes = {e["Route"] for e in dub}
    # neon-garden-requiem and hollow-crown-saga have no dub in the sample set.
    assert "neon-garden-requiem" in sub_routes and "neon-garden-requiem" not in dub_routes
    assert dub_routes < sub_routes  # strict subset
    assert all(e["AirType"] == "dub" for e in dub)


def test_demo_dub_mode_through_service(tmp_path):
    svc = ScheduleService(_demo_settings(tmp_path))
    iw = iso_week_of(2026, 7, 1)
    sub_res = asyncio.run(svc.weekly(iw.year, iw.week, "sub"))
    dub_res = asyncio.run(svc.weekly(iw.year, iw.week, "dub"))
    assert sub_res.air_type == "sub" and dub_res.air_type == "dub"
    assert len(dub_res.shows) < len(sub_res.shows)


def test_shows_window_gives_last_and_next(tmp_path):
    # In demo mode the window spans w-1..w+2, so a show should be able to show
    # both a last-released and a next-scheduled episode.
    svc = ScheduleService(_demo_settings(tmp_path))
    cw = __import__("app.isoweek", fromlist=["current_iso_week"]).current_iso_week("America/New_York")
    result = asyncio.run(svc.weekly(cw.year, cw.week))
    have_both = [s for s in result.shows if s.last_released and s.next_scheduled]
    assert have_both, "window aggregation should yield shows with both last & next"
    s = have_both[0]
    assert s.last_released.air_at < s.next_scheduled.air_at
