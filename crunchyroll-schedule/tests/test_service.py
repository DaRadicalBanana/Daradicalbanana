"""Unit tests for the core service logic: CR filter, sub->raw fallback
classification, and last-released / next-scheduled selection."""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings  # noqa: E402
from app.models import TimeConfidence  # noqa: E402
from app.service import ScheduleService  # noqa: E402

NOW = datetime.now(timezone.utc)


def _settings(tmp_path) -> Settings:
    return Settings(
        animeschedule_token="x", timezone="America/New_York", rate_per_min=30,
        timetable_ttl=10, seasonal_ttl=10, cache_dir=tmp_path, demo_mode=False,
    )


def _entry(route, ep, when, *, streams, raw_same=False):
    """Build a PascalCase sub entry; raw entry mirrors it (same time if fallback)."""
    iso = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "Route": route, "Title": route, "EpisodeNumber": ep,
        "SubtractedEpisodeNumber": 0, "EpisodeDate": iso, "Streams": streams,
        "DelayedFrom": "0001-01-01T00:00:00Z", "DelayedUntil": "0001-01-01T00:00:00Z",
    }


def test_classify_cr_filters_non_crunchyroll(tmp_path):
    svc = ScheduleService(_settings(tmp_path))
    sub = [
        _entry("on-cr", 1, NOW, streams={"crunchyroll": "u"}),
        _entry("netflix-only", 1, NOW, streams={"netflix": "u"}),
    ]
    cr = svc._classify_cr(sub, [])
    routes = {e.route for e in cr}
    assert routes == {"on-cr"}


def test_classify_cr_flags_jp_fallback_when_sub_equals_raw(tmp_path):
    svc = ScheduleService(_settings(tmp_path))
    t = NOW
    sub = [_entry("show", 3, t, streams={"crunchyroll": "u"})]
    raw_same = [_entry("show", 3, t, streams={"crunchyroll": "u"})]  # identical time
    cr = svc._classify_cr(sub, raw_same)
    assert cr[0].confidence == TimeConfidence.JP_FALLBACK


def test_classify_cr_confirmed_when_sub_offset_from_raw(tmp_path):
    svc = ScheduleService(_settings(tmp_path))
    sub = [_entry("show", 3, NOW + timedelta(hours=1), streams={"crunchyroll": "u"})]
    raw = [_entry("show", 3, NOW, streams={"crunchyroll": "u"})]
    cr = svc._classify_cr(sub, raw)
    assert cr[0].confidence == TimeConfidence.CONFIRMED_SUB


def test_build_shows_picks_last_and_next(tmp_path):
    svc = ScheduleService(_settings(tmp_path))
    sub = svc._classify_cr(
        [
            _entry("show", 5, NOW - timedelta(days=6), streams={"crunchyroll": "u"}),
            _entry("show", 6, NOW + timedelta(days=1), streams={"crunchyroll": "u"}),
            _entry("show", 7, NOW + timedelta(days=8), streams={"crunchyroll": "u"}),
        ],
        [],
    )
    shows = svc._build_shows(sub)
    assert len(shows) == 1
    s = shows[0]
    assert s.last_released.episode_number == 5
    assert s.next_scheduled.episode_number == 6  # soonest future, not the later one


def test_build_shows_handles_only_past_or_only_future(tmp_path):
    svc = ScheduleService(_settings(tmp_path))
    past = svc._build_shows(
        svc._classify_cr([_entry("p", 9, NOW - timedelta(days=1), streams={"crunchyroll": "u"})], [])
    )[0]
    assert past.last_released and past.next_scheduled is None
    fut = svc._build_shows(
        svc._classify_cr([_entry("f", 1, NOW + timedelta(days=1), streams={"crunchyroll": "u"})], [])
    )[0]
    assert fut.next_scheduled and fut.last_released is None
