# Crunchyroll Episode Schedule (personal)

A web app that shows when currently-airing Crunchyroll anime episodes release,
in your local timezone (default `America/New_York`). It fills the gap that
Crunchyroll's own app leaves: there's no clear "when did this drop / when's the
next one."

It opens to **today's releases** and offers:

- **Daily / Weekly / Monthly** schedule, grouped by date (with a per-day count
  and "Today" highlight); prev/next paging.
- **Shows** view — each show's last-released and next-scheduled episode.
- **Sub / Dub** toggle (separate Crunchyroll dub timing).
- **Search** + **★ favorites** (filter both views; favorites scope the calendar
  feed too).
- Per-episode detail: **Ep N / total**, runtime + media type ("TV · 24m"),
  cover art, and badges for **premiere**, **delayed**, and
  **"JP broadcast time"** (when a true CR sub time is unconfirmed).
- An **iCalendar feed** of the next ~4 weeks to subscribe in your phone calendar.
- Always shows **data freshness**; future episodes are flagged as projections.

Personal/local use (or a tiny personal deploy). No accounts, no history.

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

With no `ANIMESCHEDULE_TOKEN` set, the app starts in **demo mode**: it renders the
schedule from sample data (clearly banner-labelled "SAMPLE DATA"), exercising the
real pipeline — CR filtering, sub→raw fallback flags, last/next, multi-episode
drops, delays. Force it on/off with `APP_DEMO=1` / `APP_DEMO=0`.

## Put it online (easiest for phone use)

To open the app on your phone anytime without leaving a computer running, deploy
it free to Render — see **[DEPLOY.md](DEPLOY.md)**. You connect this GitHub repo
in a few taps and get a permanent `https://…onrender.com` link.

## Open it on your phone (run locally)

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

The app serves an iCalendar feed of the **next ~4 weeks** of upcoming episodes at
**`/api/calendar.ics`**. Add it as a *subscribed* calendar (iOS: Calendar →
Add Account → Other → Add Subscribed Calendar → use
`http://<your-computer-ip>:8000/api/calendar.ics`) and episodes show up alongside
your normal events. Projected/JP-fallback episodes are marked in the event title.
Append `?air_type=dub` for dub timing, or `?routes=slug1,slug2` to limit the feed
to specific shows (the in-app Subscribe link auto-scopes to your favorites).

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

- Validated end-to-end on live Crunchyroll data (deployed on Render).
- **Live API shape (confirmed):** fields are **lowerCamelCase** (`episodeDate`,
  `episodeNumber`, `streams`, …) and `streams` is a **list** of
  `{platform, name, url}` objects (URLs may lack a scheme). The parser is
  casing-tolerant and `parsing.normalize_streams` handles the list shape; see
  `DATA_MODEL.md` and `SECURITY.md`.
- ~59 offline tests cover parsing, ISO weeks, the demo pipeline, the live-shape
  integration path, ICS, throttling, and security headers.
```
