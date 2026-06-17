# Step 3 — Data model & scaffold (proposal + implementation)

This documents the scaffold built in this directory. Because you turned on auto
mode ("continue without me"), I implemented the proposal rather than only
describing it. Nothing here re-litigates the report's data-source decisions.

## Stack

- **Python 3.11+ / FastAPI + uvicorn** — backend + JSON API.
- **httpx (async)** — upstream calls with rate limiting and 429 backoff.
- **Vanilla HTML/CSS/JS** static frontend — no build step; personal/local use.
- **File-based JSON cache** — no database (v1 has no history/accounts).
- Timezone via stdlib `zoneinfo` (`America/New_York`).

Rationale: a personal, local, single-user app with timezone-heavy logic and
two-API orchestration. No need for a DB, a framework frontend, or a build
pipeline. Everything runs with `uvicorn app.main:app`.

## File layout

```
crunchyroll-schedule/
  app/
    config.py        # env-loaded settings (token from env ONLY)
    isoweek.py       # ISO week-numbering year/week (handles year boundary)
    parsing.py       # casing-tolerant pick(), null-sentinel parse_dt()
    models.py        # normalized EpisodeRelease / Show / WeeklySchedule + TimeConfidence
    ratelimit.py     # token bucket (designed to the lower 30/min) + 429 backoff
    cache.py         # file TTL cache w/ fetched_at + serve-stale
    clients/
      animeschedule.py  # timing authority: /timetables, /anime
      anilist.py        # enrichment: seasonal list, cover art, nextAiringEpisode
    service.py       # join, sub->raw fallback detection, last/next, projections
    main.py          # FastAPI routes + static mount
    static/          # index.html, app.js, style.css (weekly calendar UI)
  scripts/
    verify_step2.py  # the live Step 2 verification (run when egress+token exist)
  tests/             # parsing + isoweek unit tests (run offline)
  .env.example       # ANIMESCHEDULE_TOKEN, APP_TIMEZONE, TTLs
```

## Env var names

| Name | Purpose | Default |
|------|---------|---------|
| `ANIMESCHEDULE_TOKEN` | AnimeSchedule app Bearer token (**secret**) | — (required) |
| `APP_TIMEZONE` | IANA tz for rendering | `America/New_York` |
| `APP_RATE_PER_MIN` | global request budget | `30` (the lower upstream limit) |
| `APP_TIMETABLE_TTL` | timetable cache TTL (s) | `21600` (6h) |
| `APP_SEASONAL_TTL` | seasonal/metadata cache TTL (s) | `86400` (24h) |
| `APP_CACHE_DIR` | cache location | `./.cache` |

## Caching & resilience

- Every upstream payload is cached to `.cache/<hash>.json` with `fetched_at_ts`.
- Fresh-within-TTL → served from cache (no upstream hit).
- Upstream failure (egress, 5xx, timeout) → **serve last good cache marked
  `stale`**; the UI shows a per-source freshness line. AnimeSchedule is treated
  as a no-SLA dependency.
- Rate limiter is a shared token bucket sized to `APP_RATE_PER_MIN` (default 30,
  the AniList degraded limit), with exponential backoff honoring `Retry-After` /
  `X-RateLimit-Reset` on 429.

## Timing confidence (the honesty model)

`TimeConfidence` is attached to every `EpisodeRelease`:

- `confirmed_sub` — AnimeSchedule `sub` time differs from the same episode's
  `raw` time ⇒ a real CR sub time.
- `jp_fallback` — `sub` time **equals** `raw` time ⇒ AnimeSchedule fell back to
  the JP broadcast time. UI labels it **"JP broadcast time (CR sub time
  unconfirmed)"**.
- `projected` — future episode with no confirmed sub time (incl. AniList
  `nextAiringEpisode` premieres in the pre-season path).
- `unknown` — no usable time.

**Open verification (Step 2, blocked):** the `jp_fallback` detection assumes the
`sub` and `raw` timetables expose matching `(route, episodeNumber)` keys and
identical timestamps when a fallback occurs. This is a heuristic until confirmed
against live data — see "Blocked" below.

## Join strategy

- **AnimeSchedule `Streams` map is the arbiter** of "is this on Crunchyroll"
  (AniList's `externalLinks` is user-curated and only a weak secondary hint).
- Production join is **by AniList ID** via `AnimeScheduleClient.anime_by_anilist_ids`
  (the `/anime?anilist-ids=` filter). The current offline build also has a
  title-based fallback match for enrichment; the ID join activates once egress to
  animeschedule.net is allowed.

## Pre-season behavior (your choice: "show projected premieres")

Today (2026-06-17) is still Spring 2026. When the AnimeSchedule CR timetable is
empty/unavailable for the viewed week, `_enrich_only()` renders AniList
`nextAiringEpisode` premieres for the season, every card marked `projected` and
explicitly noted as JP broadcast time — never shown as a confirmed CR drop.

## Field casing finding (Step 2, partial — from source, not live)

I couldn't make the live call, but I read the two community wrappers the report
cites. Both deserialize the timetable with **PascalCase** JSON keys
(`EpisodeDate`, `Streams`, `Route`, `EpisodeNumber`, …):

- `er-azh/go-animeschedule` — Go struct tags `json:"EpisodeDate"` etc. Go's
  default unmarshalling requires the tag to match the wire format exactly, so the
  live API almost certainly emits PascalCase.
- `MolotovCherry/anime-schedule-rs` — Rust wrapper, consistent with the same.

This contradicts the official docs' "nearly always lowerCamelCase" claim.
**Conclusion: treat PascalCase as the most likely live shape**, but keep the
casing-tolerant `pick()` so we're correct either way. Sample fixtures are written
in PascalCase to match. A live run of `verify_step2.py` is still the final word.

## Demo / sample mode (so the app always runs)

Because a token isn't available, the app defaults to **demo mode** (auto-on when
`ANIMESCHEDULE_TOKEN` is unset; force with `APP_DEMO=1`/`0`). Demo mode renders
`app/fixtures/demo_data.py` through the *exact same* pipeline as live data —
PascalCase parsing, CR filtering, sub→raw fallback detection, last/next,
multi-episode drops, delays, the null-datetime sentinel — so it both demonstrates
the UI and exercises the real code path. Every demo view is labelled **"SAMPLE
DATA"** (banner + freshness source `sample`). In live mode, if upstream fails and
there's no cache, the app falls back to sample data rather than showing a blank
calendar.

## Blocked: Step 2 live verification

The sandbox's network egress allowlist returns
`403 host_not_allowed` for **both** `animeschedule.net` and
`graphql.anilist.co`, and `ANIMESCHEDULE_TOKEN` is unset. So the live
verification of field casing, the null-datetime sentinel, and fallback
detectability **could not be run here**. To unblock:

1. Add `animeschedule.net` and `graphql.anilist.co` to the environment's network
   egress settings.
2. Set `ANIMESCHEDULE_TOKEN` as an environment secret.
3. Run `python scripts/verify_step2.py` — it prints the live casing,
   sentinel counts, and sub-vs-raw fallback breakdown for review.

Until then the code is deliberately defensive: `parsing.pick()` accepts both
casings and `parse_dt()` maps the zero sentinel to `None`, so it will work
whichever way the live API actually behaves.
