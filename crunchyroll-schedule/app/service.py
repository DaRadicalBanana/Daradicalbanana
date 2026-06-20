"""Service layer: build the weekly Crunchyroll schedule.

Pipeline:
  1. Pull AnimeSchedule `sub` and `raw` timetables for the ISO week.
  2. Keep only entries whose Streams map contains a `crunchyroll` key
     (AnimeSchedule's Streams map is the authority on "is this on CR").
  3. Detect the sub->raw fallback: if a sub entry's time equals the same show's
     raw time for that episode, mark it JP_FALLBACK (CR sub time unconfirmed).
  4. Enrich with AniList (cover art, IDs, projected premieres for not-yet-aired
     Summer 2026 shows).
  5. Compute each show's last-released vs next-scheduled episode, in local tz.

NOTE: step 3's detection heuristic is unverified against live data — the sandbox
blocks egress to animeschedule.net. scripts/verify_step2.py exists to confirm it.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .cache import FileCache
from .clients.anilist import AniListClient, crunchyroll_url
from .clients.animeschedule import AnimeScheduleClient
from .config import Settings
from .isoweek import current_iso_week, iso_week_for, week_window
from .models import (
    DayGroup,
    ScheduleView,
    EpisodeRelease,
    Freshness,
    Show,
    TimeConfidence,
    WeeklySchedule,
)
from .parsing import _with_scheme, normalize_streams, parse_dt, pick
from .ratelimit import RateLimiter

# How many weeks around the requested week to scan when computing each show's
# last-released and next-scheduled episode for the Shows view.
WINDOW_BEFORE = 1
WINDOW_AFTER = 2

RANGES = ("daily", "weekly", "monthly")
PAGING_WINDOW_DAYS = 400  # how far prev/next may page from today


def _month_bounds(anchor: date) -> tuple[date, date]:
    start = anchor.replace(day=1)
    nxt = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, nxt - timedelta(days=1)


def _range_bounds(range_kind: str, anchor: date) -> tuple[date, date]:
    if range_kind == "daily":
        return anchor, anchor
    if range_kind == "monthly":
        return _month_bounds(anchor)
    monday = anchor - timedelta(days=anchor.weekday())  # weekly
    return monday, monday + timedelta(days=6)


def _weeks_for_bounds(start: date, end: date) -> list:
    weeks, d = [], start - timedelta(days=start.weekday())  # Monday of start's week
    while d <= end:
        weeks.append(iso_week_for(d))
        d += timedelta(days=7)
    return weeks


def _shift_anchor(range_kind: str, anchor: date, direction: int) -> date:
    if range_kind == "daily":
        return anchor + timedelta(days=direction)
    if range_kind == "weekly":
        return anchor + timedelta(days=7 * direction)
    # monthly: jump to the 1st of the prev/next month
    start = anchor.replace(day=1)
    if direction < 0:
        return (start - timedelta(days=1)).replace(day=1)
    return _month_bounds(start)[1] + timedelta(days=1)


def _range_title(range_kind: str, anchor: date, start: date, end: date, today: date) -> str:
    if range_kind == "daily":
        return ("Today · " if anchor == today else "") + anchor.strftime("%a, %b ") + str(anchor.day)
    if range_kind == "monthly":
        return anchor.strftime("%B %Y")
    return f"Week of {start.strftime('%b ')}{start.day}"


def _day_label(d: date, today: date) -> str:
    base = d.strftime("%a, %b ") + str(d.day)
    if d == today:
        return "Today · " + base
    if d == today + timedelta(days=1):
        return "Tomorrow · " + base
    return base


def _stream_census(sub_raw: list[dict], cr_entries: list) -> dict:
    """Inspect the live timetable response to explain why nothing matched.

    Surfaces the actual stream-key names, field names, streams shape, and a
    sample EpisodeDate so the real response shape can be seen without API access.
    """
    keys: set[str] = set()
    shape = "absent"
    sample_streams = None
    sample_fields: list[str] = []
    sample_date = None
    for e in sub_raw[:300]:
        s = pick(e, "streams")
        if isinstance(s, dict):
            shape = "dict"
            keys.update(map(str, s.keys()))
            if sample_streams is None:
                sample_streams = s
        elif isinstance(s, list):
            shape = "list"
            for item in s:
                if isinstance(item, dict):
                    keys.update(map(str, item.keys()))
                else:
                    keys.add(str(item))
            if sample_streams is None:
                sample_streams = s[:2]
    if sub_raw:
        first = sub_raw[0]
        if isinstance(first, dict):
            sample_fields = sorted(first.keys())
        sample_date = pick(first, "episodeDate")
    return {
        "entry_count": len(sub_raw),
        "cr_match_count": len(cr_entries),
        "streams_shape": shape,
        "stream_keys": sorted(keys)[:40],
        "sample_fields": sample_fields[:50],
        "sample_streams": sample_streams,
        "sample_date": sample_date,
    }


def _normalize_entry(raw: dict) -> EpisodeRelease:
    title = pick(raw, "title", "romaji", "english", default="") or ""
    english = pick(raw, "english") or None
    mt = pick(raw, "mediaTypes")
    media_type = None
    if isinstance(mt, list) and mt and isinstance(mt[0], dict):
        media_type = mt[0].get("name")
    elif isinstance(mt, str):
        media_type = mt
    return EpisodeRelease(
        route=pick(raw, "route", default="") or "",
        title=title,
        english_title=(english if english and english != title else None),
        episode_number=_as_int(pick(raw, "episodeNumber")),
        subtracted_episode_number=_as_int(pick(raw, "subtractedEpisodeNumber")),
        air_at=parse_dt(pick(raw, "episodeDate")),
        confidence=TimeConfidence.UNKNOWN,  # set later
        total_episodes=(_as_int(pick(raw, "episodes")) or None),
        media_type=media_type,
        length_min=_as_int(pick(raw, "lengthMin")),
        airing_status=pick(raw, "airingStatus", "status"),
        delayed_from=parse_dt(pick(raw, "delayedFrom")),
        delayed_until=parse_dt(pick(raw, "delayedUntil")),
        streams=normalize_streams(pick(raw, "streams")),
        image_route=pick(raw, "imageVersionRoute") or None,
    )


def _as_int(v) -> int | None:
    try:
        return int(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _key(entry: EpisodeRelease) -> tuple[str, int | None]:
    return (entry.route, entry.episode_number)


def _classify(sub: EpisodeRelease, raw_index: dict[tuple, EpisodeRelease]) -> TimeConfidence:
    """Confirmed CR sub time vs JP-broadcast fallback.

    If the sub timetable's time matches the raw timetable's time for the same
    (route, episode), AnimeSchedule almost certainly fell back to raw because no
    sub time was known -> flag as JP_FALLBACK.
    """
    if sub.air_at is None:
        return TimeConfidence.UNKNOWN
    raw = raw_index.get(_key(sub))
    if raw is not None and raw.air_at is not None and raw.air_at == sub.air_at:
        return TimeConfidence.JP_FALLBACK
    return TimeConfidence.CONFIRMED_SUB


def is_crunchyroll(entry: EpisodeRelease) -> bool:
    return entry.on_crunchyroll


class ScheduleService:
    def __init__(self, settings: Settings):
        self.settings = settings
        cache = FileCache(settings.cache_dir)
        limiter = RateLimiter(settings.rate_per_min)
        self.cache = cache
        self.animeschedule = AnimeScheduleClient(settings, cache, limiter)
        self.anilist = AniListClient(settings, cache, limiter)

    async def _week_cr_entries(self, air_type: str, year: int, week: int) -> tuple[list[EpisodeRelease], bool]:
        """Classified Crunchyroll entries for one ISO week. Returns (entries, is_sample)."""
        tz = self.settings.timezone
        if self.settings.demo_mode:
            from .fixtures.demo_data import build_demo_timetables

            sub_raw, raw_raw = build_demo_timetables(year, week, air_type)
            return self._classify_cr(sub_raw, raw_raw), True
        sub_raw, _ = await self.animeschedule.timetable(air_type, year, week, tz)
        raw_raw, _ = await self.animeschedule.timetable("raw", year, week, tz)
        return self._classify_cr(sub_raw or [], raw_raw or []), False

    async def schedule_view(self, range_kind: str, anchor: date, air_type: str = "sub") -> ScheduleView:
        """Daily / Weekly / Monthly schedule of CR releases grouped by date."""
        air_type = "dub" if air_type == "dub" else "sub"
        range_kind = range_kind if range_kind in RANGES else "daily"
        tz = self.settings.timezone
        local = ZoneInfo(tz)
        today = datetime.now(local).date()
        # Single source of truth for the navigable window (bounds upstream fan-out
        # and cache growth); the UI disables prev/next at the edges.
        lo, hi = today - timedelta(days=PAGING_WINDOW_DAYS), today + timedelta(days=PAGING_WINDOW_DAYS)
        anchor = max(lo, min(hi, anchor))
        start, end = _range_bounds(range_kind, anchor)
        prev_a = _shift_anchor(range_kind, anchor, -1)
        next_a = _shift_anchor(range_kind, anchor, +1)
        view = ScheduleView(
            range=range_kind,
            anchor=anchor.isoformat(),
            timezone=tz,
            air_type=air_type,
            title=_range_title(range_kind, anchor, start, end, today),
            prev_anchor=prev_a.isoformat(),
            next_anchor=next_a.isoformat(),
            has_prev=prev_a >= lo,
            has_next=next_a <= hi,
        )

        is_sample = False
        seen: set = set()
        by_date: dict[date, list[EpisodeRelease]] = {}
        weeks = _weeks_for_bounds(start, end)
        # Fetch the weeks concurrently (Monthly spans ~5 weeks); the rate limiter
        # still bounds actual request concurrency.
        results = await asyncio.gather(
            *(self._week_cr_entries(air_type, iw.year, iw.week) for iw in weeks),
            return_exceptions=True,
        )
        for iw, res in zip(weeks, results):
            if isinstance(res, Exception):
                view.warnings.append(f"AnimeSchedule unavailable for {iw}: {res}")
                continue
            entries, sample = res
            is_sample = is_sample or sample
            for e in entries:
                if not e.air_at:
                    continue
                d = e.air_at.astimezone(local).date()
                if d < start or d > end:
                    continue
                key = (e.route, e.episode_number, e.air_at.isoformat())
                if key in seen:
                    continue
                seen.add(key)
                if e.image_route:
                    e.cover_image_url = f"{self.settings.img_base}{e.image_route}"
                by_date.setdefault(d, []).append(e)

        if range_kind == "daily":
            dates = [start]
        elif range_kind == "weekly":
            dates = [start + timedelta(days=i) for i in range(7)]
        else:  # monthly: only dates with releases
            dates = sorted(by_date.keys())
        for d in dates:
            rel = sorted(by_date.get(d, []), key=lambda x: x.air_at)
            view.groups.append(
                DayGroup(
                    date=d.isoformat(),
                    weekday=d.strftime("%a"),
                    label=_day_label(d, today),
                    is_today=(d == today),
                    releases=rel,
                )
            )

        if any(e.confidence == TimeConfidence.JP_FALLBACK for rel in by_date.values() for e in rel):
            view.warnings.append("Some episodes show JP broadcast time (CR sub time unconfirmed).")
        if is_sample:
            view.warnings.insert(0, "SAMPLE DATA — not live Crunchyroll data.")
            view.freshness.append(Freshness(fetched_at=datetime.now(timezone.utc), source="sample", stale=False))
        else:
            view.freshness.append(Freshness(fetched_at=datetime.now(timezone.utc), source="animeschedule", stale=False))
        return view

    async def upcoming_releases(self, days: int, air_type: str = "sub") -> list[EpisodeRelease]:
        """Flat, chronological list of CR releases from now through `days` ahead
        (for the calendar feed). Deduped; covers resolved."""
        air_type = "dub" if air_type == "dub" else "sub"
        days = max(1, min(days, PAGING_WINDOW_DAYS))
        tz = self.settings.timezone
        local = ZoneInfo(tz)
        today = datetime.now(local).date()
        end = today + timedelta(days=days)
        now_utc = datetime.now(timezone.utc)
        weeks = _weeks_for_bounds(today, end)
        results = await asyncio.gather(
            *(self._week_cr_entries(air_type, iw.year, iw.week) for iw in weeks),
            return_exceptions=True,
        )
        seen: set = set()
        out: list[EpisodeRelease] = []
        for res in results:
            if isinstance(res, Exception):
                continue
            entries, _ = res
            for e in entries:
                if not e.air_at or e.air_at < now_utc:
                    continue  # upcoming only
                if e.air_at.astimezone(local).date() > end:
                    continue
                key = (e.route, e.episode_number, e.air_at.isoformat())
                if key in seen:
                    continue
                seen.add(key)
                if e.image_route:
                    e.cover_image_url = f"{self.settings.img_base}{e.image_route}"
                out.append(e)
        out.sort(key=lambda x: x.air_at)
        return out

    async def weekly(self, year: int, week: int, air_type: str = "sub") -> WeeklySchedule:
        air_type = "dub" if air_type == "dub" else "sub"
        tz = self.settings.timezone
        result = WeeklySchedule(iso_year=year, iso_week=week, timezone=tz, air_type=air_type)
        cw = current_iso_week(tz)
        result.is_current_week = (cw.year == year and cw.week == week)

        if self.settings.demo_mode:
            return self._demo_weekly(result)

        # ---- AnimeSchedule primary (sub|dub) + raw for the week (drives grid) ----
        try:
            sub_raw, sub_meta = await self.animeschedule.timetable(air_type, year, week, tz)
            raw_raw, _ = await self.animeschedule.timetable("raw", year, week, tz)
        except Exception as exc:  # auth/egress/availability
            result.warnings.append(f"AnimeSchedule unavailable: {exc}")
            result.freshness.append(Freshness(None, "animeschedule", stale=True, note=str(exc)))
            await self._enrich_only(result, year)
            if not result.shows:
                # Never show a blank app: fall back to clearly-labelled samples.
                return self._demo_weekly(result, reason="live data unavailable")
            return result

        # ---- window weeks for the Shows view (last-released + next-scheduled) ----
        window_pairs: list[tuple[list, list]] = []
        for iw in week_window(year, week, WINDOW_BEFORE, WINDOW_AFTER):
            if iw.year == year and iw.week == week:
                window_pairs.append((sub_raw or [], raw_raw or []))
                continue
            try:
                w_sub, _ = await self.animeschedule.timetable(air_type, iw.year, iw.week, tz)
                w_raw, _ = await self.animeschedule.timetable("raw", iw.year, iw.week, tz)
                window_pairs.append((w_sub or [], w_raw or []))
            except Exception:
                continue  # a missing neighbour week just narrows last/next

        self._assemble(
            result,
            sub_raw or [],
            raw_raw or [],
            window_pairs,
            source="animeschedule",
            fetched_at=sub_meta.fetched_at if sub_meta else None,
            stale=not (sub_meta.fresh if sub_meta else False),
        )

        # ---- metadata enrichment (AniList/MAL links, genres, studios) ----
        # Route-based join via AnimeSchedule's own /anime/{route} records, which
        # already carry the external IDs — no AniList GraphQL call needed.
        await self._apply_anime_details(result.shows)
        return result

    @staticmethod
    def _classify_cr(sub_raw: list[dict], raw_raw: list[dict]) -> list[EpisodeRelease]:
        """Normalize -> CR-filter -> attach sub/raw fallback confidence (pure)."""
        raw_index = {}
        for e in (_normalize_entry(x) for x in raw_raw):
            raw_index[_key(e)] = e
        cr = [e for e in (_normalize_entry(x) for x in sub_raw) if is_crunchyroll(e)]
        for e in cr:
            e.confidence = _classify(e, raw_index)
        return cr

    def _assemble(
        self,
        result: WeeklySchedule,
        sub_raw: list[dict],
        raw_raw: list[dict],
        window_pairs: list[tuple[list, list]],
        *,
        source: str,
        fetched_at,
        stale: bool,
    ) -> WeeklySchedule:
        """Shared pipeline used by both live and demo paths.

        The grid (`days`) reflects only the requested week; `shows` (last-released
        + next-scheduled per show) aggregate across the whole window so each show
        can show both a recent and an upcoming episode.
        """
        tz = result.timezone
        week_entries = self._classify_cr(sub_raw, raw_raw)

        result.freshness.append(Freshness(fetched_at=fetched_at, source=source, stale=stale))

        # ---- grid: weekday buckets (local tz), requested week only ----
        local = ZoneInfo(tz)
        for e in week_entries:
            if e.air_at is None:
                continue
            wd = e.air_at.astimezone(local).weekday()
            result.days.setdefault(wd, []).append(e)
        for wd in result.days:
            result.days[wd].sort(key=lambda x: x.air_at or datetime.max.replace(tzinfo=timezone.utc))

        # ---- shows: aggregate the window ----
        window_entries: list[EpisodeRelease] = []
        for w_sub, w_raw in (window_pairs or [(sub_raw, raw_raw)]):
            window_entries.extend(self._classify_cr(w_sub, w_raw))
        result.shows = self._build_shows(window_entries)

        if any(e.confidence == TimeConfidence.JP_FALLBACK for e in window_entries):
            result.warnings.append(
                "Some episodes show JP broadcast time (CR sub time unconfirmed)."
            )

        # ---- diagnostics when live data returned but nothing rendered ----
        if source != "sample" and not result.shows and not any(result.days.values()):
            result.diagnostics = _stream_census(sub_raw, week_entries)
            d = result.diagnostics
            result.warnings.append(
                f"DEBUG: {d['entry_count']} entries fetched, {len(week_entries)} matched a "
                f"'crunchyroll' stream."
            )
            result.warnings.append(f"DEBUG: stream keys seen = {d['stream_keys']}")
            result.warnings.append(f"DEBUG: sample entry fields = {d['sample_fields']}")
            result.warnings.append(
                f"DEBUG: streams shape={d['streams_shape']} sample={d['sample_streams']}"
            )
            result.warnings.append(f"DEBUG: sample EpisodeDate = {d['sample_date']!r}")
        return result

    def _demo_weekly(self, result: WeeklySchedule, reason: str | None = None) -> WeeklySchedule:
        """Render the full pipeline over sample data — no network, no token."""
        from .fixtures.demo_data import build_demo_timetables

        year, week, air_type = result.iso_year, result.iso_week, result.air_type
        sub_raw, raw_raw = build_demo_timetables(year, week, air_type)
        window_pairs = [
            build_demo_timetables(iw.year, iw.week, air_type)
            for iw in week_window(year, week, WINDOW_BEFORE, WINDOW_AFTER)
        ]
        self._assemble(
            result,
            sub_raw,
            raw_raw,
            window_pairs,
            source="sample",
            fetched_at=datetime.now(timezone.utc),
            stale=False,
        )
        msg = "SAMPLE DATA — not live Crunchyroll data."
        if reason:
            msg += f" ({reason})"
        result.warnings.insert(0, msg)
        return result

    def _build_shows(self, entries: list[EpisodeRelease]) -> list[Show]:
        by_route: dict[str, list[EpisodeRelease]] = {}
        for e in entries:
            by_route.setdefault(e.route, []).append(e)
        now = datetime.now(timezone.utc)
        shows: list[Show] = []
        for route, eps in by_route.items():
            timed = [e for e in eps if e.air_at]
            released = [e for e in timed if e.air_at <= now]
            upcoming = [e for e in timed if e.air_at > now]
            last_released = max(released, key=lambda x: x.air_at) if released else None
            next_scheduled = min(upcoming, key=lambda x: x.air_at) if upcoming else None
            if next_scheduled:
                # Future dates are projections.
                if next_scheduled.confidence == TimeConfidence.CONFIRMED_SUB:
                    next_scheduled.confidence = TimeConfidence.CONFIRMED_SUB
                elif next_scheduled.confidence == TimeConfidence.UNKNOWN:
                    next_scheduled.confidence = TimeConfidence.PROJECTED
            ref = last_released or next_scheduled or eps[0]
            title = ref.title
            english = next((e.english_title for e in eps if e.english_title), None)
            cr = next((e.streams.get("crunchyroll") for e in eps if e.streams.get("crunchyroll")), None)
            img_route = next((e.image_route for e in eps if e.image_route), None)
            cover = f"{self.settings.img_base}{img_route}" if img_route else None
            shows.append(
                Show(
                    route=route,
                    title=title,
                    english_title=english,
                    crunchyroll_url=cr,
                    cover_image_url=cover,
                    last_released=last_released,
                    next_scheduled=next_scheduled,
                )
            )
        shows.sort(key=lambda s: s.title.lower())
        return shows

    async def _apply_anime_details(self, shows: list[Show]) -> None:
        """Enrich shows with AniList/MAL links, genres and studios via the
        route-based `/anime/{route}` join.

        Best-effort and strictly time-boxed: per-show detail fetches run
        concurrently (bounded by a semaphore) and the whole pass is wrapped in a
        12s budget so it can never blow the endpoint's 30s ceiling. Any per-show
        failure is swallowed — the schedule still renders, just without links.
        """
        if not shows:
            return
        sem = asyncio.Semaphore(8)

        async def enrich(show: Show) -> None:
            if not show.route:
                return
            async with sem:
                try:
                    data, _ = await self.animeschedule.anime_detail(show.route)
                except Exception:
                    return  # graceful: links absent, schedule unaffected
            if not isinstance(data, dict):
                return
            self._merge_anime_detail(show, data)

        try:
            await asyncio.wait_for(
                asyncio.gather(*(enrich(s) for s in shows), return_exceptions=True),
                timeout=12,
            )
        except asyncio.TimeoutError:
            pass  # partial enrichment is fine; never block the response

    @staticmethod
    def _merge_anime_detail(show: Show, data: dict) -> None:
        websites = data.get("websites") if isinstance(data.get("websites"), dict) else {}
        anilist_raw = websites.get("aniList") or websites.get("anilist")
        mal_raw = websites.get("mal")
        if anilist_raw:
            show.anilist_url = _with_scheme(str(anilist_raw))
            m = re.search(r"/anime/(\d+)", show.anilist_url)
            if m:
                show.anilist_id = int(m.group(1))
        if mal_raw:
            show.mal_url = _with_scheme(str(mal_raw))
            m = re.search(r"/anime/(\d+)", show.mal_url)
            if m:
                show.mal_id = int(m.group(1))
        genres = data.get("genres")
        if isinstance(genres, list):
            show.genres = [g["name"] for g in genres if isinstance(g, dict) and g.get("name")][:5]
        studios = data.get("studios")
        if isinstance(studios, list):
            show.studios = [s["name"] for s in studios if isinstance(s, dict) and s.get("name")][:3]

    async def _enrich_only(self, result: WeeklySchedule, year: int) -> WeeklySchedule:
        """Pre-season / AnimeSchedule-down path: show projected premieres from
        AniList nextAiringEpisode (clearly marked as projections)."""
        season = _season_for_year_context(year, result.iso_week)
        try:
            media = await self.anilist.seasonal(season, year)
        except Exception as exc:
            result.warnings.append(f"AniList unavailable: {exc}")
            return result
        result.freshness.append(
            Freshness(fetched_at=datetime.now(timezone.utc), source="anilist", stale=False)
        )
        result.warnings.append(
            "Showing AniList projected premieres (JP broadcast time) — "
            "AnimeSchedule CR times unavailable."
        )
        for m in media:
            nxt = m.get("nextAiringEpisode")
            if not nxt:
                continue
            air = datetime.fromtimestamp(nxt["airingAt"], tz=timezone.utc)
            title = (m.get("title") or {}).get("english") or (m.get("title") or {}).get("romaji") or ""
            ep = EpisodeRelease(
                route=str(m.get("id")),
                title=title,
                episode_number=nxt.get("episode"),
                subtracted_episode_number=None,
                air_at=air,
                confidence=TimeConfidence.PROJECTED,
            )
            cover = m.get("coverImage") or {}
            result.shows.append(
                Show(
                    route=ep.route,
                    title=title,
                    anilist_id=m.get("id"),
                    mal_id=m.get("idMal"),
                    cover_image_url=cover.get("large") or cover.get("medium"),
                    crunchyroll_url=crunchyroll_url(m),
                    next_scheduled=ep,
                )
            )
        result.shows.sort(key=lambda s: (s.next_scheduled.air_at if s.next_scheduled else datetime.max.replace(tzinfo=timezone.utc)))
        return result


def _season_for_year_context(year: int, iso_week: int) -> str:
    """Map an ISO week to an anime season name for AniList.

    v1 targets Summer 2026; this keeps the seasonal query aligned with the week
    being viewed (roughly: weeks 27-39 -> SUMMER).
    """
    if 14 <= iso_week <= 26:
        return "SPRING"
    if 27 <= iso_week <= 39:
        return "SUMMER"
    if 40 <= iso_week <= 51:
        return "FALL"
    return "WINTER"
