"""AnimeSchedule.net v3 client — the timing authority.

Covers the two endpoints v1 needs:
  GET /timetables/{airType}?year=&week=&tz=   (airType in raw|sub|dub|all)
  GET /anime?anilist-ids=&streams=crunchyroll (for joining + metadata)

Auth is a single application Bearer token from the environment. The timetable
array is returned raw (list of dicts) so the service layer can do casing-tolerant
normalization and the sub-vs-raw fallback diff.
"""
from __future__ import annotations

import httpx

from ..cache import CacheEntry, FileCache
from ..config import ANIMESCHEDULE_BASE, Settings
from ..ratelimit import RateLimiter, retry_after_seconds


class AnimeScheduleError(RuntimeError):
    pass


class AnimeScheduleAuthError(AnimeScheduleError):
    pass


class AnimeScheduleClient:
    def __init__(self, settings: Settings, cache: FileCache, limiter: RateLimiter):
        self.settings = settings
        self.cache = cache
        self.limiter = limiter

    def _headers(self) -> dict[str, str]:
        if not self.settings.has_token:
            raise AnimeScheduleAuthError(
                "ANIMESCHEDULE_TOKEN is not set. Add it as an environment secret."
            )
        return {
            "Authorization": f"Bearer {self.settings.animeschedule_token}",
            "Accept": "application/json",
            "User-Agent": "cr-weekly-schedule/0.1 (personal)",
        }

    async def _get(self, path: str, params: dict, *, cache_key: str, ttl: int) -> tuple[list | dict, CacheEntry | None]:
        """GET with cache + rate limit + 429 backoff; serve-stale on failure."""
        cached = self.cache.get(cache_key, ttl)
        if cached and cached.fresh:
            return cached.data, cached

        url = f"{ANIMESCHEDULE_BASE}{path}"
        last_exc: Exception | None = None
        async with httpx.AsyncClient(timeout=30) as client:
            for attempt in range(5):
                await self.limiter.acquire()
                try:
                    resp = await client.get(url, params=params, headers=self._headers())
                except httpx.HTTPError as exc:  # network / egress failures
                    last_exc = exc
                    break
                if resp.status_code == 429:
                    import asyncio

                    await asyncio.sleep(retry_after_seconds(dict(resp.headers), attempt))
                    continue
                if resp.status_code in (401, 403):
                    raise AnimeScheduleAuthError(
                        f"{resp.status_code} from AnimeSchedule (token invalid or egress blocked): "
                        f"{resp.text[:200]}"
                    )
                if resp.status_code >= 400:
                    last_exc = AnimeScheduleError(f"{resp.status_code}: {resp.text[:200]}")
                    break
                data = resp.json()
                self.cache.set(cache_key, data)
                return data, self.cache.get(cache_key, ttl)

        # Upstream failed: degrade to stale cache if we have any.
        if cached:
            return cached.data, cached
        raise AnimeScheduleError(f"AnimeSchedule unavailable and no cache: {last_exc}")

    async def timetable(self, air_type: str, year: int, week: int, tz: str):
        assert air_type in {"raw", "sub", "dub", "all"}
        params = {"year": year, "week": week, "tz": tz}
        key = f"as:timetable:{air_type}:{year}:{week}:{tz}"
        return await self._get(
            f"/timetables/{air_type}", params, cache_key=key, ttl=self.settings.timetable_ttl
        )

    async def anime_by_anilist_ids(self, anilist_ids: list[int]):
        params = {"anilist-ids": ",".join(str(i) for i in anilist_ids), "streams": "crunchyroll"}
        key = f"as:anime:anilist:{','.join(map(str, sorted(anilist_ids)))}"
        return await self._get("/anime", params, cache_key=key, ttl=self.settings.seasonal_ttl)

    async def anime_probe(self):
        """Fetch a small /anime sample to inspect its response shape (debug only)."""
        return await self._get(
            "/anime", {"streams": "crunchyroll"}, cache_key="as:anime:probe", ttl=self.settings.seasonal_ttl
        )

    async def anime_detail(self, route: str):
        """Fetch a single show's metadata record (`GET /anime/{route}`).

        Returns the show detail dict (with `websites`, `genres`, `studios`, etc.),
        which carries the AniList/MAL IDs embedded in `websites` URL strings — so
        the metadata join needs no AniList GraphQL call. Cached for `seasonal_ttl`.
        """
        return await self._get(
            f"/anime/{route}", {}, cache_key=f"as:anime:detail:{route}", ttl=self.settings.seasonal_ttl
        )
