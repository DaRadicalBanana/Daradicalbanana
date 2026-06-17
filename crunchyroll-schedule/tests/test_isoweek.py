"""Tests for ISO week handling, incl. the year-boundary divergence."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.isoweek import iso_week_for, iso_week_of  # noqa: E402


def test_today_context():
    # 2026-06-17 is ISO week 25 of 2026.
    iw = iso_week_for(date(2026, 6, 17))
    assert (iw.year, iw.week) == (2026, 25)


def test_early_july_is_week_27():
    iw = iso_week_of(2026, 7, 1)
    assert (iw.year, iw.week) == (2026, 27)


def test_year_boundary_uses_iso_year_not_calendar_year():
    # 2026-12-31 is a Thursday -> ISO week 53 of 2026.
    assert iso_week_for(date(2026, 12, 31)) == iso_week_of(2026, 12, 31)
    # 2027-01-01 (Friday) is still ISO week 53 of 2026, NOT week 1 of 2027.
    iw = iso_week_for(date(2027, 1, 1))
    assert iw.year == 2026 and iw.week == 53


def test_str_format():
    assert str(iso_week_of(2026, 7, 1)) == "2026-W27"
