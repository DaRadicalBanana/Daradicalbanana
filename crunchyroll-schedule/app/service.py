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

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .cache import FileCache
from .clients.anilist import AniListClient, crunchyroll_url
from .clients.animeschedule import AnimeScheduleClient
from .config import Settings
from .isoweek import current_iso_week
from .models import (
    EpisodeRelease,
    Freshness,
    Show,
    TimeConfidence,
    WeeklySchedule,
)
from .parsing import parse_dt, pick
from .ratelimit import RateLimiter


def _normalize_entry(raw: dict) -> EpisodeRelease:
    streams = pick(raw, "streams", default={}) or {}
    return EpisodeRelease(
        route=pick(raw, "route", default="") or "",
        title=pick(raw, "title", "english", default="") or "",
        episode_number=_as_int(pick(raw, "episodeNumber")),
        subtracted_episode_number=_as_int(pick(raw, "subtractedEpisodeNumber")),
        air_at=parse_dt(pick(raw, "episodeDate")),
        confidence=TimeConfidence.UNKNOWN,  # set later
        length_min=_as_int(pick(raw, "lengthMin")),
        airing_status=pick(raw, "airingStatus", "status"),
        delayed_from=parse_dt(pick(raw, "delayedFrom")),
        delayed_until=parse_dt(pick(raw, "delayedUntil")),
        streams=streams if isinstance(streams, dict) else {},
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

    async def weekly(self, year: int, week: int) -> WeeklySchedule:
        tz = self.settings.timezone
        result = WeeklySchedule(iso_year=year, iso_week=week, timezone=tz)
        cw = current_iso_week(tz)
        result.is_current_week = (cw.year == year and cw.week == week)

        if self.settings.demo_mode:
            return self._demo_weekly(result)

        # ---- AnimeSchedule sub + raw ----
        try:
            sub_raw, sub_meta = await self.animeschedule.timetable("sub", year, week, tz)
            raw_raw, _ = await self.animeschedule.timetable("raw", year, week, tz)
        except Exception as exc:  # auth/egress/availability
            result.warnings.append(f"AnimeSchedule unavailable: {exc}")
            result.freshness.append(Freshness(None, "animeschedule", stale=True, note=str(exc)))
            await self._enrich_only(result, year)
            if not result.shows:
                # Never show a blank app: fall back to clearly-labelled samples.
                return self._demo_weekly(result, reason="live data unavailable")
            return result

        self._assemble(
            result,
            sub_raw or [],
            raw_raw or [],
            source="animeschedule",
            fetched_at=sub_meta.fetched_at if sub_meta else None,
            stale=not (sub_meta.fresh if sub_meta else False),
        )

        # ---- AniList enrichment (cover art + projected premieres) ----
        await self._apply_anilist(result, year)
        return result

    def _assemble(
        self,
        result: WeeklySchedule,
        sub_raw: list[dict],
        raw_raw: list[dict],
        *,
        source: str,
        fetched_at,
        stale: bool,
    ) -> WeeklySchedule:
        """Shared pipeline: normalize -> CR-filter -> classify -> group -> shows.

        Used by both the live path and demo mode so they behave identically.
        """
        tz = result.timezone
        sub_entries = [_normalize_entry(e) for e in sub_raw]
        raw_entries = [_normalize_entry(e) for e in raw_raw]
        raw_index = {_key(e): e for e in raw_entries}

        cr_entries = [e for e in sub_entries if is_crunchyroll(e)]
        for e in cr_entries:
            e.confidence = _classify(e, raw_index)

        result.freshness.append(Freshness(fetched_at=fetched_at, source=source, stale=stale))
        if any(e.confidence == TimeConfidence.JP_FALLBACK for e in cr_entries):
            result.warnings.append(
                "Some episodes show JP broadcast time (CR sub time unconfirmed)."
            )

        # ---- group into weekday buckets (local tz) ----
        local = ZoneInfo(tz)
        for e in cr_entries:
            if e.air_at is None:
                continue
            wd = e.air_at.astimezone(local).weekday()
            result.days.setdefault(wd, []).append(e)
        for wd in result.days:
            result.days[wd].sort(key=lambda x: x.air_at or datetime.max.replace(tzinfo=timezone.utc))

        # ---- per-show last/next ----
        result.shows = self._build_shows(cr_entries)
        return result

    def _demo_weekly(self, result: WeeklySchedule, reason: str | None = None) -> WeeklySchedule:
        """Render the full pipeline over sample data — no network, no token."""
        from .fixtures.demo_data import build_demo_timetables

        sub_raw, raw_raw = build_demo_timetables(result.iso_year, result.iso_week)
        self._assemble(
            result,
            sub_raw,
            raw_raw,
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
            title = (last_released or next_scheduled or eps[0]).title
            cr = next((e.streams.get("crunchyroll") for e in eps if e.streams.get("crunchyroll")), None)
            shows.append(
                Show(
                    route=route,
                    title=title,
                    crunchyroll_url=cr,
                    last_released=last_released,
                    next_scheduled=next_scheduled,
                )
            )
        shows.sort(key=lambda s: s.title.lower())
        return shows

    async def _apply_anilist(self, result: WeeklySchedule, year: int) -> None:
        season = _season_for_year_context(year, result.iso_week)
        try:
            media = await self.anilist.seasonal(season, year)
        except Exception as exc:
            result.warnings.append(f"AniList enrichment unavailable: {exc}")
            result.freshness.append(Freshness(None, "anilist", stale=True, note=str(exc)))
            return
        result.freshness.append(
            Freshness(fetched_at=datetime.now(timezone.utc), source="anilist", stale=False)
        )
        # Match by title (best-effort without the AnimeSchedule anilist-id join,
        # which needs the network). The id-based join lives in
        # AnimeScheduleClient.anime_by_anilist_ids and is wired in once egress
        # to animeschedule.net is allowed.
        by_title: dict[str, dict] = {}
        for m in media:
            for t in (m.get("title") or {}).values():
                if t:
                    by_title[t.lower()] = m
        for show in result.shows:
            m = by_title.get(show.title.lower())
            if not m:
                continue
            show.anilist_id = m.get("id")
            show.mal_id = m.get("idMal")
            cover = m.get("coverImage") or {}
            show.cover_image_url = cover.get("large") or cover.get("medium")
            show.crunchyroll_url = show.crunchyroll_url or crunchyroll_url(m)

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
