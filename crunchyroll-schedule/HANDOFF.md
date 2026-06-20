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

## DONE — AniList/MAL metadata enrichment (route-based join)
The fragile **title-based** `_apply_anilist` has been **replaced** by a
**route-based** join. The Shows view now shows "AniList ↗ · MAL ↗" links and a
genres line; `Show` carries `anilist_url/mal_url/anilist_id/mal_id/genres/studios`.
No AniList GraphQL call is involved — the IDs come straight from AnimeSchedule's
own `/anime/{route}` `websites` URL strings.

What landed:
- **client** `AnimeScheduleClient.anime_detail(route)` (cached `seasonal_ttl`).
- **models** `Show` gained `anilist_url`, `mal_url`, `genres`, `studios`.
- **service** `_apply_anime_details(shows)` + `_merge_anime_detail(show, data)`:
  per-show detail fetched **concurrently** (`asyncio.Semaphore(8)`), whole pass
  wrapped in `asyncio.wait_for(12s)` (can't blow the 30s endpoint budget),
  per-show failures swallowed (links absent, schedule still renders). Parses
  `websites.aniList/mal` (scheme-fixed via `parsing._with_scheme`), pulls integer
  IDs with `re.search(r"/anime/(\d+)", …)`, and `genres[:5]`/`studios[:3]`.
  `weekly()` now calls `_apply_anime_details(result.shows)`. `_apply_anilist` is
  removed; `_enrich_only` still uses `anilist.seasonal`/`crunchyroll_url`. Demo
  path returns before enrichment, so it's unaffected.
- **frontend** `showRow` adds a `.links` line (external, `rel="noopener"`,
  escaped) and a genres `.sub` line; `.show .links` styled in `style.css`.
- **tests** `tests/test_integration_live.py`: `_live_service` mocks
  `anime_detail` → `({}, _meta())` by default; `test_live_path_anime_detail_enrichment`
  overrides it and asserts the IDs/URLs/genres/studios land. **60 tests pass.**

Follow-up worth considering: surface `studios` in the UI too (currently parsed
and stored but only genres are rendered); add an `img-src` entry only if AniList
cover art is ever reintroduced (this join no longer overrides covers).

## Backlog
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
