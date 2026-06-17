"""ISO week helpers.

Critical: the AnimeSchedule timetable endpoint takes (year, week). These MUST be
the ISO-8601 week-numbering year and week, NOT the calendar year. Near a year
boundary the calendar year and the ISO year diverge (e.g. 2026-01-01 may be ISO
week 53 of 2025). Always derive both from `date.isocalendar()`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class IsoWeek:
    year: int  # ISO week-numbering year
    week: int  # 1..53

    def __str__(self) -> str:
        return f"{self.year}-W{self.week:02d}"


def iso_week_for(d: date) -> IsoWeek:
    cal = d.isocalendar()
    return IsoWeek(year=cal.year, week=cal.week)


def current_iso_week(tz: str) -> IsoWeek:
    """Current ISO week in the given IANA timezone (week boundaries are local)."""
    now = datetime.now(ZoneInfo(tz))
    return iso_week_for(now.date())


def iso_week_of(year: int, month: int, day: int) -> IsoWeek:
    return iso_week_for(date(year, month, day))


def week_offset(year: int, week: int, delta: int) -> IsoWeek:
    """The ISO week `delta` weeks away, computed via dates so year boundaries
    (and 52/53-week years) are handled correctly."""
    from datetime import timedelta

    monday = date.fromisocalendar(year, week, 1) + timedelta(weeks=delta)
    return iso_week_for(monday)


def week_window(year: int, week: int, before: int, after: int) -> list[IsoWeek]:
    """Weeks from `before` weeks back through `after` weeks ahead (inclusive)."""
    return [week_offset(year, week, d) for d in range(-before, after + 1)]
