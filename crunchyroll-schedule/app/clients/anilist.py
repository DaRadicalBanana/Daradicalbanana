"""AniList GraphQL client — enrichment/fallback only.

Supplies the Summer 2026 seasonal list, cover art, IDs, and nextAiringEpisode.
IMPORTANT: airingAt is the *Japanese broadcast* instant, never the Crunchyroll
drop. It is used only for projected premieres and as a sanity check — never
presented as a confirmed CR time.
"""
from __future__ import annotations

import httpx

from ..cache import FileCache
from ..config import ANILIST_BASE, Settings
from ..ratelimit import RateLimiter, retry_after_seconds

SEASONAL_QUERY = """
query ($season: MediaSeason, $year: Int, $page: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage currentPage }
    media(season: $season, seasonYear: $year, type: ANIME, sort: POPULARITY_DESC) {
      id
      idMal
      title { romaji english }
      coverImage { large medium }
      externalLinks { url site type }
      nextAiringEpisode { episode airingAt timeUntilAiring }
    }
  }
}
"""


class AniListClient:
    def __init__(self, settings: Settings, cache: FileCache, limiter: RateLimiter):
        self.settings = settings
        self.cache = cache
        self.limiter = limiter

    async def seasonal(self, season: str, year: int) -> list[dict]:
        key = f"anilist:seasonal:{season}:{year}"
        cached = self.cache.get(key, self.settings.seasonal_ttl)
        if cached and cached.fresh:
            return cached.data

        media: list[dict] = []
        page = 1
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                while True:
                    data = await self._post(
                        client,
                        {"season": season, "year": year, "page": page},
                    )
                    block = data["data"]["Page"]
                    media.extend(block["media"])
                    if not block["pageInfo"]["hasNextPage"]:
                        break
                    page += 1
        except httpx.HTTPError:
            if cached:
                return cached.data  # serve stale
            raise
        self.cache.set(key, media)
        return media

    async def _post(self, client: httpx.AsyncClient, variables: dict) -> dict:
        import asyncio

        for attempt in range(5):
            await self.limiter.acquire()
            resp = await client.post(
                ANILIST_BASE,
                json={"query": SEASONAL_QUERY, "variables": variables},
                headers={"Accept": "application/json", "User-Agent": "cr-weekly-schedule/0.1"},
            )
            if resp.status_code == 429:
                await asyncio.sleep(retry_after_seconds(dict(resp.headers), attempt))
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError("AniList: exhausted retries on 429")


def crunchyroll_url(media: dict) -> str | None:
    for link in media.get("externalLinks") or []:
        if (link.get("site") or "").lower() == "crunchyroll":
            return link.get("url")
    return None
