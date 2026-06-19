# HANDOFF — crunchyroll-schedule

Continuity doc for future sessions. Read `CLAUDE.md` first (architecture, confirmed
API shapes, gotchas, loop protocol). This file = current state, the in-flight next
task (with everything needed to do it), and the backlog.

## Current state (as of this handoff)
- Branch `claude/anime-release-schedule-xzwrr7`; latest commits include the
  `/anime`-shape docs, the `verify_step2.py` streams fix, and 8 feature + 7
  security runs. ~59 offline tests pass; CI green (test + pip-audit + gitleaks).
- Live on Render **Starter** (zero-downtime auto-deploy), validated on real
  Crunchyroll data. App opens to **today's releases**.
- The autonomous loop is **PAUSED** by user request. Do not resume it unless asked.
- Working tree clean; nothing half-applied.

## What's built
- **Views:** Schedule (Daily/Weekly/Monthly date-grouped, opens to today, prev/next,
  per-day counts, Today highlight) + Shows (last/next per show). Sub/Dub toggle.
- **Filtering:** search + ★ favorites across both views; favorites scope the
  calendar feed (`/api/calendar.ics?routes=…`).
- **Per-episode:** "Ep N / total", runtime + media type, cover thumbnails, badges
  for premiere / delayed / "JP broadcast time", relative times + countdowns.
- **Calendar feed:** next ~4 weeks of upcoming episodes (`upcoming_releases` +
  `build_ics_events`), `?air_type` and `?routes` supported.
- **Resilience/security:** demo mode, serve-stale cache, client+server timeouts,
  cache-busting, CSP+headers+HSTS, per-IP rate limiting, input clamping,
  dependency CVE scan, gitleaks. See `SECURITY.md`.

## IN-FLIGHT NEXT TASK — AniList/MAL metadata enrichment (route-based join)
Goal: replace the fragile **title-based** `_apply_anilist` with a reliable
**route-based** join, and add "Open on AniList / MyAnimeList" links (+ genres/
studios) to the Shows view. The `/anime` endpoint already carries the IDs, so
**no AniList GraphQL call is needed** for this.

Confirmed: `GET /api/v3/anime/{route}` → HTTP 200, a single dict containing
`websites` (with `aniList`/`mal` URL strings), `genres`, `studios`, etc. (See
CLAUDE.md "CONFIRMED live API shapes" and DATA_MODEL.md.)

### Implementation plan (precise)
1. **client** `AnimeScheduleClient.anime_detail(route)`:
   `await self._get(f"/anime/{route}", {}, cache_key=f"as:anime:detail:{route}",
   ttl=self.settings.seasonal_ttl)` → returns `(dict, meta)`.
2. **models** `Show`: add `anilist_url`, `mal_url` (str|None), `genres`,
   `studios` (list[str]).
3. **service** `_apply_anime_details(shows)`:
   - For each `show.route`, fetch `anime_detail` **concurrently** (bound with an
     `asyncio.Semaphore(~8)`), the whole thing wrapped in `asyncio.wait_for(~12s)`
     so it can never blow the endpoint's 30s budget; per-show failures are caught
     and skipped (best-effort, graceful).
   - Parse `data["websites"]`: `aniList`/`mal` → add `https://` scheme (reuse the
     scheme logic) → set `show.anilist_url`/`show.mal_url`; extract integer id via
     `re.search(r"/anime/(\d+)", url)` → `show.anilist_id`/`show.mal_id`.
   - `data["genres"]`/`["studios"]` → `[x["name"] …][:5]`/`[:3]`.
   - In `weekly()`, REPLACE `await self._apply_anilist(result, year)` with
     `await self._apply_anime_details(result.shows)`; then remove the now-unused
     `_apply_anilist` (keep `crunchyroll_url`/`anilist.seasonal` — still used by
     `_enrich_only`). Demo path is unaffected (returns before enrichment).
4. **frontend** `showRow`: add a links line ("AniList ↗ · MAL ↗", external,
   `rel="noopener"`, escaped) and a genres `.sub` line.
5. **tests** (`tests/test_integration_live.py`): the live harness `_live_service`
   must mock `svc.animeschedule.anime_detail` to return `({}, _meta())` by default
   (so existing live-path tests stay offline). Add one test overriding it with a
   record containing `websites`/`genres`/`studios` and assert the show gets
   `anilist_url`/`anilist_id`/`mal_url`/`mal_id`/`genres`.

### Risk notes
- Per-show calls are throttled (rate limiter, default 30/min). The Shows view can
  have many shows → cold-cache enrichment could be slow; the `wait_for(12s)` +
  cache (24h TTL) keep it safe and fast after warm-up. Failure = links absent,
  schedule still renders.
- A user already confirmed `/anime/{route}` returns 200 + `websites: True`.

## Backlog (after the enrichment)
- Minor UX polish: URL-shareable view state (`?view&range&at`), keyboard shortcuts.
- Optional: drop the title-based AniList path entirely once route-join covers it;
  keep AniList only for the pre-season `_enrich_only` premieres.
- Security (already comprehensive): tighten further only if it becomes multi-user.

## How to verify shapes again if needed
`/api/debug` (set `APP_DEBUG=1` in Render, hit it, set back to `0`) dumps the live
timetable shape, a parsed `cr_sample`, and the `/anime` shape. Or run
`scripts/verify_step2.py` locally with `ANIMESCHEDULE_TOKEN` set (macOS: use a venv).

## Operating notes for whoever continues
- Commit from the repo ROOT (see CLAUDE.md git gotcha). Small, tested commits.
- Don't suggest regenerating the AnimeSchedule token (user declined).
- Keep the honesty model: never present JP time as a confirmed CR time; always
  show freshness; never blank.
