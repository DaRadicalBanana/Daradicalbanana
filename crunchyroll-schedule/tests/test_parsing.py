"""Tests for casing-tolerant parsing and the null-datetime sentinel."""
import os
import sys
from datetime import timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.parsing import detect_casing, normalize_streams, parse_dt, pick  # noqa: E402


def test_normalize_streams_real_list_shape():
    # Exact shape from the live AnimeSchedule v3 timetable response.
    raw = [
        {"platform": "crunchyroll", "url": "www.crunchyroll.com/series/x", "name": "Crunchyroll"},
        {"platform": "amazon", "url": "amzn.to/41YU3bT", "name": "Amazon"},
    ]
    s = normalize_streams(raw)
    assert s["crunchyroll"] == "https://www.crunchyroll.com/series/x"  # scheme added
    assert s["amazon"] == "https://amzn.to/41YU3bT"
    assert "crunchyroll" in s


def test_normalize_streams_dict_shape_still_works():
    s = normalize_streams({"crunchyroll": "https://cr/x", "hidive": "https://h/y"})
    assert s["crunchyroll"] == "https://cr/x"


def test_normalize_streams_handles_none_and_garbage():
    assert normalize_streams(None) == {}
    assert normalize_streams("nope") == {}
    assert normalize_streams([{"no_name_field": 1}]) == {}


def test_parse_dt_with_offset_from_live_data():
    dt = parse_dt("2026-06-15T10:00:00-04:00")  # exact live format
    assert dt is not None and dt.hour == 14  # 10:00 EDT -> 14:00 UTC


def test_pick_handles_both_casings():
    lower = {"episodeDate": "2026-07-05T15:00:00Z", "streams": {"crunchyroll": "x"}}
    pascal = {"EpisodeDate": "2026-07-05T15:00:00Z", "Streams": {"crunchyroll": "x"}}
    assert pick(lower, "episodeDate") == "2026-07-05T15:00:00Z"
    assert pick(pascal, "episodeDate") == "2026-07-05T15:00:00Z"
    assert pick(lower, "streams") == {"crunchyroll": "x"}
    assert pick(pascal, "streams") == {"crunchyroll": "x"}


def test_pick_missing_returns_default():
    assert pick({}, "episodeDate", default="X") == "X"
    assert pick({"foo": 1}, "bar") is None


def test_parse_dt_zero_sentinel_is_none():
    assert parse_dt("0001-01-01T00:00:00Z") is None
    assert parse_dt("0001-01-01T00:00:00.000Z") is None
    assert parse_dt("") is None
    assert parse_dt(None) is None


def test_parse_dt_valid_is_utc_aware():
    dt = parse_dt("2026-07-05T15:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timezone.utc.utcoffset(None)
    assert dt.year == 2026 and dt.hour == 15


def test_parse_dt_offset_normalized_to_utc():
    dt = parse_dt("2026-07-05T20:00:00+05:00")
    assert dt is not None
    assert dt.hour == 15  # converted to UTC


def test_detect_casing():
    assert detect_casing({"EpisodeDate": 1}) == "PascalCase"
    assert detect_casing({"episodeDate": 1}) == "lowerCamelCase"
    assert detect_casing({"whatever": 1}) == "unknown"
