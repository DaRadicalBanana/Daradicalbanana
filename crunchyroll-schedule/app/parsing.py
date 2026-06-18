"""Tolerant parsing for AnimeSchedule JSON.

Two documented ambiguities the report flags, handled defensively here because we
cannot disambiguate without live data:

1. Field casing: docs say lowerCamelCase (`episodeDate`, `streams`) but a known
   Go wrapper uses PascalCase (`EpisodeDate`, `Streams`). `pick()` tries every
   variant.
2. Null datetimes serialize as the Go zero value `0001-01-01T00:00:00Z`.
   `parse_dt()` maps that (and any year <= 1) to None.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


def pick(d: dict[str, Any], *names: str, default: Any = None) -> Any:
    """Return the first present key among `names`, trying common casings.

    For each requested name we also try its lowerCamelCase and PascalCase forms,
    so callers can pass just one spelling.
    """
    if not isinstance(d, dict):
        return default
    for name in names:
        for variant in _casings(name):
            if variant in d:
                return d[variant]
    return default


def _casings(name: str) -> Iterable[str]:
    seen = set()
    candidates = [
        name,
        name[:1].lower() + name[1:],  # lowerCamel
        name[:1].upper() + name[1:],  # Pascal
    ]
    for c in candidates:
        if c not in seen:
            seen.add(c)
            yield c


# Go's time.Time zero value, how null datetimes come across the wire.
_ZERO_SENTINELS = {"0001-01-01t00:00:00z", "0001-01-01t00:00:00.000z", ""}


def parse_dt(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None.

    The `0001-01-01T00:00:00Z` sentinel (and any year <= 1) is treated as null.
    """
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _aware(value)
    if not isinstance(value, str):
        return None
    if value.strip().lower() in _ZERO_SENTINELS:
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.year <= 1:
        return None
    return _aware(dt)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _with_scheme(url: str) -> str:
    url = (url or "").strip()
    if url and not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def normalize_streams(value: Any) -> dict[str, str]:
    """Normalize AnimeSchedule's `streams` into a {platform: url} dict.

    The live API returns a LIST of objects, e.g.
        [{"platform": "crunchyroll", "name": "Crunchyroll", "url": "crunchyroll.com/.."}]
    but a dict ({"crunchyroll": "url"}) shape is also accepted (demo fixtures /
    older docs). Keys are lowercased platform names; URLs get an https:// scheme
    if missing (the API omits it).
    """
    out: dict[str, str] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            out[str(k).lower()] = _with_scheme(str(v))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                name = item.get("platform") or item.get("name") or item.get("site")
                url = item.get("url") or item.get("link") or ""
                if name:
                    out[str(name).lower()] = _with_scheme(str(url))
            elif isinstance(item, str):
                out[item.lower()] = ""
    return out


def detect_casing(sample: dict[str, Any]) -> str:
    """Best-effort report of which casing a live payload uses (for Step 2)."""
    keys = set(sample) if isinstance(sample, dict) else set()
    lower = {"episodeDate", "streams", "route", "episodeNumber"}
    pascal = {"EpisodeDate", "Streams", "Route", "EpisodeNumber"}
    if keys & pascal:
        return "PascalCase"
    if keys & lower:
        return "lowerCamelCase"
    return "unknown"
