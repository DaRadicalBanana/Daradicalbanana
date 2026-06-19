# CLAUDE.md — crunchyroll-schedule

Personal web app showing when currently-airing **Crunchyroll** anime episodes
release, in the user's local timezone (default `America/New_York`). Lives in this
subdirectory; the repo root is an unrelated YouTube-transcript project — ignore it.

**Active branch:** `claude/anime-release-schedule-xzwrr7` (all work happens here).
**Live:** deployed on Render (Starter instance) at
`https://crunchyroll-schedule.onrender.com`, validated on real data.
**Status:** ~59 offline tests, CI green. See `HANDOFF.md` for session history,
the in-flight next task, and the full backlog.

## Data strategy (decided — see ../RESEARCH_REPORT.md; do not relitigate)
- **AnimeSchedule.net v3** (`https://animeschedule.net/api/v3`) = timing authority
  for CR sub/dub release times. Auth: app Bearer token in env `ANIMESCHEDULE_TOKEN`
  (secret only; never hardcode/log/commit). Rate limit ~120/min.
- **AniList GraphQL** (`https://graphql.anilist.co`, no key) = enrichment/fallback;
  its `airingAt` is *Japanese broadcast* time, never shown as a CR time.
- Never scrape Crunchyroll or hit its internal API.
- When AnimeSchedule's `sub` time equals the `raw` time, it fell back to JP
  broadcast time → label "JP broadcast time (CR sub time unconfirmed)". Future
  episodes are projections. Always show data freshness; never blank — degrade to
  cache, then to clearly-labelled SAMPLE DATA.

## CONFIRMED live API shapes (verified against production — trust these)
**Timetable** `GET /timetables/{raw|sub|dub|all}?year&week&tz` → **list** of
entries, fields **lowerCamelCase**:
`airType, airingStatus, delayedFrom, delayedUntil, donghua, english, episodeDate,
episodeNumber, episodes, imageVersionRoute, lengthMin, mediaTypes[{name,route}],
native, romaji, route, status, streams, title`.
- `streams` is a **LIST** of `{platform, name, url}` (URLs may lack a scheme).
- dates like `2026-06-15T10:00:00-04:00`; null datetimes = `0001-01-01T00:00:00Z`.

**Anime** `GET /anime?streams=crunchyroll&page=N` → object
`{page, totalAmount, anime:[...]}`. `GET /anime/{route}` → single record (HTTP 200).
A record has `route`, `id` (AnimeSchedule's own, NOT AniList), `title`, `names`,
`imageVersionRoute`, `jpnTime/subTime/dubTime`, `genres[{name,route}]`,
`studios[{name,route}]`, and **`websites`**:
`{official, mal:"myanimelist.net/anime/<ID>/..", aniList:"anilist.co/anime/<ID>/..",
anidb, kitsu, animePlanet, streams:[...]}` — external IDs are embedded in URL
strings (no integer fields). Join timetable↔anime by **`route`**.

## Architecture (current)
- `config.py` — `Settings` from env: `animeschedule_token`, `timezone`,
  `rate_per_min`, ttls, `cache_dir`, `demo_mode` (auto-on when no token),
  `debug_enabled` (APP_DEBUG), `img_base`.
- `parsing.py` — `pick()` (casing-tolerant: handles lowerCamel AND Pascal),
  `parse_dt()` (maps `0001-01-01`/year≤1 → None), `normalize_streams()`
  (list|dict → `{platform: url}`, adds https), `detect_casing()`.
- `clients/animeschedule.py` — async httpx; `timetable()`, `anime_by_anilist_ids()`,
  `anime_probe()`; rate-limited, 429 backoff, file-cached, serve-stale. (Add
  `anime_detail(route)` for the next task.)
- `clients/anilist.py` — seasonal GraphQL (used by pre-season `_enrich_only`).
- `service.py` — `ScheduleService`:
  - `weekly(year,week,air_type)` → `WeeklySchedule` (grid `days` = requested week;
    `shows` aggregate weeks w-1..w+2 for last+next). Demo path returns early.
  - `schedule_view(range_kind,anchor,air_type)` → `ScheduleView` (Daily/Weekly/
    Monthly, date-grouped `groups`; clamps anchor to ±`PAGING_WINDOW_DAYS`=400,
    sets `has_prev/has_next`).
  - `upcoming_releases(days,air_type)` → flat list for the calendar feed.
  - `_classify_cr` (CR filter + sub/raw→`TimeConfidence`), `_build_shows`
    (last/next + cover from imageVersionRoute), `_apply_anilist` (title-based —
    TO BE REPLACED, see HANDOFF), `_enrich_only` (pre-season projections),
    `_stream_census` (debug).
- `models.py` — normalized dataclasses: `EpisodeRelease` (route, title,
  english_title, episode_number, total_episodes, media_type, air_at, confidence,
  length_min, airing_status, streams, image_route, cover_image_url), `Show`,
  `DayGroup`, `ScheduleView`, `WeeklySchedule`, `Freshness`, `TimeConfidence`.
  `to_jsonable()` serializes for the API.
- `isoweek.py` — `current_iso_week`, `iso_week_for/of`, `week_offset`,
  `week_window` (ISO week-numbering year via `%G/%V`; year-boundary safe).
- `throttle.py` — `IPRateLimiter` (in-memory fixed window), `client_ip` (XFF-aware).
- `ics.py` — `build_ics_events(releases,...)` (used by feed); `build_ics(schedule)`
  (legacy, still tested).
- `main.py` — FastAPI. Routes: `/` (HTML, cache-busted `?v=<mtime>`, no-cache),
  `/api/health`, `/api/schedule`, `/api/releases`, `/api/calendar.ics`,
  `/api/debug` (404 unless APP_DEBUG), `/static`. One middleware applies per-IP
  rate limit on `/api/*` + security headers (CSP/nosniff/DENY/Referrer/Permissions/
  HSTS). Endpoints wrap service calls in `asyncio.wait_for(30s)`.
- `static/` — vanilla JS UI: views **Schedule** (Daily/Weekly/Monthly dropdown,
  opens to today) and **Shows**; Sub/Dub toggle; search + ★ favorites (filter both
  views, scope the calendar feed); badges premiere/delayed/JP; "Ep N/total",
  runtime+type; responsive/PWA. Image fallbacks wired in JS (no inline handlers —
  strict CSP). `index.html` references `app.js?v=__V__` / `style.css?v=__V__`.
- `scripts/serve.py` (LAN + QR), `scripts/verify_step2.py` (live shape check).

## Conventions
- Upstream JSON never reaches the UI raw — normalize through `models.py`.
- Casing-tolerant + shape-tolerant parsing; degrade gracefully, never blank.
- Strict CSP: no inline `<script>` or inline event handlers (`onerror=` etc.);
  wire DOM behavior in `app.js`. `img-src` allowlists img.animeschedule.net +
  *.anilist.co — new external image hosts must be added there.
- Token is header-only; `/api/health` exposes only a boolean. The user has
  explicitly declined to regenerate the token — do NOT suggest regenerating it.

## Dev / test / CI
- Tests: `pytest -q` (offline; no token/network; ~59 tests). On macOS use a venv
  (`python3 -m venv .venv && source .venv/bin/activate`) — system pip is blocked.
- Run: `python scripts/serve.py` (demo if no token) or set `ANIMESCHEDULE_TOKEN`
  + `APP_DEMO=0` for live.
- CI `.github/workflows/cr-schedule.yml`: `test` (pytest) + `security`
  (`pip-audit --strict`) + `secret-scan` (gitleaks). Render auto-deploys every
  push to the branch (zero-downtime on Starter).

## GOTCHAS (real footguns hit this session)
- **git path after `cd`:** Bash keeps its working dir between calls. If a prior
  command `cd`'d into `crunchyroll-schedule/`, then `git add crunchyroll-schedule/x`
  doubles the path and silently stages nothing. **Commit from the repo root**, or
  use paths relative to the current dir. Always check `git status`/push output.
- **Ephemeral container:** idle reclaim kills background monitors and wipes
  `/tmp`. Long-running loops pause; resume when the user prompts.
- **Render:** `render.yaml` is blueprint-managed → instance type comes from
  `plan:` (currently `starter`), not the dashboard. autoDeploy is ON.
- **Cache-busting matters:** never let new HTML pair with stale `app.js` — the
  `?v=` token + `Cache-Control: no-cache` on `/` handle this. (A stale app.js once
  caused a permanent "Loading…" with zero `/api` calls.)

## Autonomous "loop" protocol (if asked to run/resume a recurring improvement loop)
State in `/tmp` (recreate on a fresh container): `loop_mode` (features|security),
`loop_interval` (seconds, e.g. 600), `loop_next_due` (epoch). Mechanism: a
`Monitor` runs a bash one-liner that sleeps `min(next_due-now, 1500)` then prints
`RUN DUE` or `HEARTBEAT`. On `RUN DUE`: implement ONE small tested improvement →
`pytest` green → commit (from repo root!) → push → set `loop_next_due=now+interval`
→ re-arm a fresh Monitor. Container caps monitor lifetime under ~30min, so chain
short heartbeats rather than one long sleep. Keep commits small and individually
reviewable; stop and check in at genuine diminishing returns rather than churn.
