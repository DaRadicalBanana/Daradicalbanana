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

## Quick start (zero config — runs in demo mode)

```bash
cd crunchyroll-schedule
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

With no `ANIMESCHEDULE_TOKEN` set, the app starts in **demo mode**: it renders a
full weekly calendar from sample data (clearly banner-labelled "SAMPLE DATA"),
exercising the real pipeline — CR filtering, sub→raw fallback flags, last/next,
multi-episode drops, delays. Force it on/off with `APP_DEMO=1` / `APP_DEMO=0`.

## Open it on your phone

Run this on your computer (e.g. your Mac) with your phone on the **same Wi-Fi**:

```bash
cd crunchyroll-schedule
pip install -r requirements.txt
python scripts/serve.py
```

It prints a URL like `http://192.168.1.42:8000` **and a scannable QR code** —
point your phone camera at it and tap the link. The UI is fully responsive
(single-column agenda on phones) and you can "Add to Home Screen" for an app-like
icon (it ships a web manifest + iOS meta tags).

- First run, macOS may ask to *allow incoming connections* — click **Allow**.
- Different port: `PORT=9000 python scripts/serve.py`.
- **Off your home Wi-Fi?** Plain LAN won't reach it. Run a quick tunnel instead:
  install `cloudflared` and `cloudflared tunnel --url http://localhost:8000` —
  it prints a public `https://…trycloudflare.com` URL you can open anywhere (no
  account needed). Use sparingly; it's a public URL while running.

### Subscribe in your phone's calendar

The app serves an iCalendar feed of each show's next episode at
**`/api/calendar.ics`**. Add it as a *subscribed* calendar (iOS: Calendar →
Add Account → Other → Add Subscribed Calendar → use
`http://<your-computer-ip>:8000/api/calendar.ics`) and upcoming episodes show up
alongside your normal events. Projected/JP-fallback episodes are marked in the
event title.

### Going live

```bash
cp .env.example .env          # then set ANIMESCHEDULE_TOKEN
APP_DEMO=0 uvicorn app.main:app --reload
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

- Steps 1 (strategy + critique) and 3 (model + scaffold) are done; the app runs
  end to end in demo mode with no token or network.
- Step 2 (live verification): the live call is blocked in the sandbox (egress +
  no token), so `scripts/verify_step2.py` is ready to run when those exist. From
  the cited wrapper source I did resolve the casing question — the live API is
  almost certainly **PascalCase** (see `DATA_MODEL.md`); fixtures match and the
  parser handles both regardless.
```
