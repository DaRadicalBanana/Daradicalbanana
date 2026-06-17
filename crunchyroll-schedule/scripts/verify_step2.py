#!/usr/bin/env python3
"""Step 2 — live verification of the AnimeSchedule timetable response shape.

This is the script the brief's Step 2 calls for. It makes REAL authenticated
calls and verifies, against live JSON, the three things the report flags as
uncertain:

  1. Field casing  — lowerCamelCase (docs) vs PascalCase (wrapper)?
  2. Null datetimes — do they serialize as 0001-01-01T00:00:00Z?
  3. Sub->raw fallback detectability — can we tell a real CR sub time from a
     raw/JP fallback by diffing the sub and raw timetables?

It does NOT model or persist anything; it prints findings for review.

Usage:
    ANIMESCHEDULE_TOKEN=... python scripts/verify_step2.py
    # weeks default to the current ISO week and an early-July (Summer) week.

Requires network egress to animeschedule.net. In the Claude Code web sandbox
that host must be added to the environment's egress allowlist first.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.isoweek import current_iso_week, iso_week_of  # noqa: E402
from app.parsing import detect_casing, parse_dt, pick  # noqa: E402

BASE = "https://animeschedule.net/api/v3"
TZ = os.getenv("APP_TIMEZONE", "America/New_York")


def fetch(air_type: str, year: int, week: int, token: str) -> list:
    url = f"{BASE}/timetables/{air_type}"
    resp = httpx.get(
        url,
        params={"year": year, "week": week, "tz": TZ},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=30,
    )
    print(f"  GET {air_type} {year}-W{week:02d} -> HTTP {resp.status_code}")
    resp.raise_for_status()
    return resp.json()


def report_week(label: str, year: int, week: int, token: str) -> None:
    print(f"\n=== {label}: {year}-W{week:02d} (tz={TZ}) ===")
    sub = fetch("sub", year, week, token)
    raw = fetch("raw", year, week, token)
    print(f"  sub entries: {len(sub)} | raw entries: {len(raw)}")
    if not sub:
        print("  (empty sub timetable — nothing to inspect)")
        return

    sample = sub[0]
    # 1. casing
    print(f"\n  [1] casing: {detect_casing(sample)}")
    print(f"      top-level keys: {sorted(sample.keys())}")

    # 2. null datetime sentinel
    sentinel_hits = Counter()
    for e in sub:
        for field in ("episodeDate", "delayedFrom", "delayedUntil"):
            v = pick(e, field)
            if isinstance(v, str) and v.startswith("0001-01-01"):
                sentinel_hits[field] += 1
    print(f"\n  [2] null-datetime sentinel (0001-01-01...) counts: {dict(sentinel_hits) or 'none seen'}")
    print(f"      parse_dt of sentinel -> {parse_dt('0001-01-01T00:00:00Z')!r}")

    # 3. crunchyroll filter + sub vs raw fallback diff
    def key(e):
        return (pick(e, "route"), pick(e, "episodeNumber"))

    raw_index = {key(e): pick(e, "episodeDate") for e in raw}
    cr = [e for e in sub if any(k.lower() == "crunchyroll" for k in (pick(e, "streams") or {}))]
    confirmed = fallback = 0
    for e in cr:
        sub_dt = pick(e, "episodeDate")
        raw_dt = raw_index.get(key(e))
        if sub_dt and raw_dt and sub_dt == raw_dt:
            fallback += 1
        elif sub_dt:
            confirmed += 1
    print(f"\n  [3] crunchyroll entries: {len(cr)}")
    print(f"      confirmed CR sub time (sub != raw): {confirmed}")
    print(f"      JP fallback (sub == raw): {fallback}")
    if cr:
        ex = cr[0]
        trimmed = {
            "route": pick(ex, "route"),
            "title": pick(ex, "title"),
            "episodeNumber": pick(ex, "episodeNumber"),
            "episodeDate": pick(ex, "episodeDate"),
            "streams": pick(ex, "streams"),
        }
        print("\n  representative CR entry (trimmed):")
        print(json.dumps(trimmed, indent=2)[:1200])


def main() -> int:
    token = os.getenv("ANIMESCHEDULE_TOKEN")
    if not token:
        print("ERROR: ANIMESCHEDULE_TOKEN is not set.", file=sys.stderr)
        return 2
    try:
        cw = current_iso_week(TZ)
        report_week("current week", cw.year, cw.week, token)
        july = iso_week_of(2026, 7, 1)
        report_week("early-July (Summer)", july.year, july.week, token)
    except httpx.HTTPStatusError as exc:
        print(f"\nHTTP error: {exc.response.status_code} {exc.response.text[:200]}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"\nNetwork error (egress blocked?): {exc}", file=sys.stderr)
        return 1
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
