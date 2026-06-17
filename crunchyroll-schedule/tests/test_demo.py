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
