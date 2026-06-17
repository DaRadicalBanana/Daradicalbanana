# Crunchyroll Weekly Episode Schedule (personal)

A local web app that shows, as a weekly calendar, when each currently-airing
Crunchyroll anime's **last episode released** and **next episode is scheduled**,
in your local timezone (default `America/New_York`). It fills the gap that
Crunchyroll's own app leaves: there's no clear "when did this drop / when's the
next one."

Scope for v1: currently-airing **Summer 2026** shows on Crunchyroll, weekly
calendar, local-timezone times, personal/local use. No notifications, no
history, no accounts.

## Data sources (see `../RESEARCH_REPORT.md` for the decision record)

- **AnimeSchedule.net v3** — the timing authority (CR sub/dub release times).
  Auth: a free **app Bearer token** in `ANIMESCHEDULE_TOKEN` (env secret only).
- **AniList GraphQL** — enrichment/fallback: seasonal list, cover art, IDs,
  `nextAiringEpisode` (Japanese broadcast time — never shown as a CR time).
- Crunchyroll itself is **not** scraped or API-hit (ToS + JS-rendered SPA).

When AnimeSchedule's sub timetable falls back to the raw/JP broadcast time, the
episode is flagged **"JP broadcast time (CR sub time unconfirmed)"**. Future
episodes are rendered as **projections**. Every view shows **data freshness**.

## Quick start

```bash
cd crunchyroll-schedule
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then set ANIMESCHEDULE_TOKEN
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

## Verify the upstream contract (Step 2)

Before trusting the model, confirm the live API shape (field casing,
null-datetime sentinel, sub-vs-raw fallback detectability):

```bash
ANIMESCHEDULE_TOKEN=... python scripts/verify_step2.py
```

> Requires network egress to `animeschedule.net` (and `graphql.anilist.co` for
> enrichment). In the Claude Code web sandbox these hosts must be added to the
> environment's egress allowlist first — see `DATA_MODEL.md` → "Blocked".

## Tests (offline)

```bash
pip install pytest
pytest -q
```

Covers casing-tolerant parsing, the `0001-01-01` null sentinel, and ISO
week-numbering (including the year-boundary case).

## Status

- Steps 1 (strategy restatement + critique) and 3 (model + scaffold) are done.
- Step 2 (live verification) is implemented as `scripts/verify_step2.py` but
  **could not be run** here: the sandbox blocks egress to both APIs and no token
  is set. Run it once those are available.
```
