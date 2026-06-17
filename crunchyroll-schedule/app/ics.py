"""Build an iCalendar (.ics) feed of upcoming Crunchyroll episodes.

One VEVENT per show's next-scheduled episode. Times are emitted in UTC (with a
trailing Z) so the phone's calendar converts them to local time. Projections and
JP-broadcast fallbacks are marked in the title/description so a subscribed
calendar still reflects the honesty model.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import EpisodeRelease, TimeConfidence, WeeklySchedule

_PRODID = "-//cr-weekly-schedule//EN"


def _ics_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _esc(text: str) -> str:
    # RFC 5545 escaping for TEXT values.
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold long content lines to <=75 octets (RFC 5545), continuation = space."""
    out, cur = [], line
    while len(cur.encode("utf-8")) > 75:
        # find a cut point <=75 bytes
        cut = 75
        while len(cur[:cut].encode("utf-8")) > 75:
            cut -= 1
        out.append(cur[:cut])
        cur = " " + cur[cut:]
    out.append(cur)
    return "\r\n".join(out)


def _event(ep: EpisodeRelease, title: str, url: str | None) -> list[str]:
    start = ep.air_at
    end = start + timedelta(minutes=ep.length_min or 24)
    num = (
        f"{ep.subtracted_episode_number}-{ep.episode_number}"
        if ep.subtracted_episode_number
        else (ep.episode_number if ep.episode_number is not None else "?")
    )
    summary = f"{title} — Ep {num}"
    notes = []
    if ep.confidence == TimeConfidence.JP_FALLBACK:
        summary += " (JP time?)"
        notes.append("Time is the Japanese broadcast time; Crunchyroll sub time unconfirmed.")
    elif ep.confidence == TimeConfidence.PROJECTED:
        summary += " (projected)"
        notes.append("Projected date — may change.")
    notes.append("Source: AnimeSchedule.net. Personal schedule app.")
    uid = f"{ep.route}-{ep.episode_number}-{_ics_dt(start)}@cr-weekly-schedule"

    lines = [
        "BEGIN:VEVENT",
        _fold(f"UID:{uid}"),
        f"DTSTAMP:{_ics_dt(datetime.now(timezone.utc))}",
        f"DTSTART:{_ics_dt(start)}",
        f"DTEND:{_ics_dt(end)}",
        _fold(f"SUMMARY:{_esc(summary)}"),
        _fold(f"DESCRIPTION:{_esc(' '.join(notes))}"),
    ]
    if url:
        lines.append(_fold(f"URL:{_esc(url)}"))
    lines.append("END:VEVENT")
    return lines


def build_ics(schedule: WeeklySchedule, calname: str = "Crunchyroll Schedule") -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{_PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        _fold(f"X-WR-CALNAME:{_esc(calname)}"),
        "X-WR-TIMEZONE:UTC",
    ]
    for show in schedule.shows:
        ep = show.next_scheduled
        if not ep or not ep.air_at:
            continue
        lines += _event(ep, show.title, show.crunchyroll_url or (ep.streams or {}).get("crunchyroll"))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
