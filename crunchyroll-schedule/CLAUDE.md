# CLAUDE.md — crunchyroll-schedule

Personal, local web app: a weekly calendar of Crunchyroll episode releases
(each show's last-released + next-scheduled episode) in the user's local
timezone (default America/New_York). Lives in this subdirectory; the rest of the
repo is an unrelated project.

## Data strategy (decided; see RESEARCH_REPORT.md in repo root — do not relitigate)
- **AnimeSchedule.net v3** = timing authority (CR sub/dub times). Auth: app
  Bearer token in env `ANIMESCHEDULE_TOKEN` (secret only, never hardcoded).
- **AniList GraphQL** = enrichment/fallback (seasonal list, cover art, IDs,
  nextAiringEpisode = *Japanese broadcast* time, never shown as a CR time).
- Do **not** scrape Crunchyroll or hit its internal API.
- When AnimeSchedule's `sub` time falls back to the raw/JP time, label it
  "JP broadcast time (CR sub time unconfirmed)". Future episodes are projections.

## Architecture
- `app/config.py` — env settings; `demo_mode` (auto-on when no token).
- `app/parsing.py` — casing-tolerant `pick()` (API is most likely PascalCase;
  see DATA_MODEL.md) + `parse_dt()` mapping the `0001-01-01` sentinel to None.
- `app/clients/{animeschedule,anilist}.py` — async httpx, rate-limited + 429
  backoff, file-cached with serve-stale.
- `app/service.py` — the pipeline. Grid (`days`) = requested week only; Shows
  (`shows`) aggregate weeks w-1..w+2 (WINDOW_BEFORE/AFTER) so each show shows
  last+next. `_classify_cr` does CR-filter + sub/raw fallback classification.
- `app/fixtures/demo_data.py` — PascalCase sample timetables for demo mode.
- `app/main.py` — FastAPI: `/`, `/api/schedule`, `/api/health`, `/static`.
- `app/static/` — vanilla JS UI (Week + Shows views, responsive/PWA).
- `scripts/serve.py` — LAN server + QR for opening on a phone.
- `scripts/verify_step2.py` — live API-shape verification (needs token+egress).

## Conventions
- Keep upstream JSON shapes out of the UI; everything crosses through
  `app/models.py` normalized dataclasses with explicit `TimeConfidence`.
- Always surface data freshness and treat AnimeSchedule as a no-SLA dependency
  (cache, degrade, never blank — fall back to sample data).

## Dev
- Tests: `pytest -q` (offline; no network/token needed).
- Run: `python scripts/serve.py` (demo mode) or set `ANIMESCHEDULE_TOKEN` +
  `APP_DEMO=0` for live.
- CI: `.github/workflows/cr-schedule.yml` runs pytest on push.
