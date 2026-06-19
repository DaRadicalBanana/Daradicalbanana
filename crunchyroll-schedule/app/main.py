"""FastAPI app: serves the weekly calendar UI and a JSON schedule endpoint.

Run locally:
    uvicorn app.main:app --reload
Then open http://127.0.0.1:8000
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import settings
from .ics import build_ics_events
from .isoweek import current_iso_week
from .models import to_jsonable
from .service import ScheduleService, _normalize_entry, _stream_census, is_crunchyroll
from .throttle import IPRateLimiter, client_ip

app = FastAPI(title="Crunchyroll Weekly Schedule", version="0.1.0")
_service = ScheduleService(settings)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Content-Security-Policy: same-origin scripts/styles (no inline JS), no framing.
# img-src is restricted to the specific cover-art hosts (kept in sync with the
# configured AnimeSchedule image base) instead of a blanket https:.
def _host(url: str) -> str:
    from urllib.parse import urlparse

    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else ""


_IMG_HOSTS = " ".join(h for h in (_host(settings.img_base), "https://*.anilist.co") if h)
_CSP = (
    "default-src 'self'; "
    f"img-src 'self' data: {_IMG_HOSTS}; "
    "style-src 'self'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)


_api_limiter = IPRateLimiter(limit=int(os.getenv("APP_RATELIMIT_PER_MIN", "120")), window=60.0)


def _apply_security_headers(resp):
    resp.headers.setdefault("Content-Security-Policy", _CSP)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    # Render terminates TLS; tell browsers to stick to HTTPS.
    resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


@app.middleware("http")
async def security_headers(request, call_next):
    # Per-IP rate limit on the API surface (abuse/DoS protection).
    if request.url.path.startswith("/api/"):
        allowed, retry = _api_limiter.check(client_ip(request))
        if not allowed:
            resp = JSONResponse(
                {"error": "rate limited"}, status_code=429, headers={"Retry-After": str(retry)}
            )
            return _apply_security_headers(resp)
    return _apply_security_headers(await call_next(request))


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "timezone": settings.timezone,
        "animeschedule_token_present": settings.has_token,
        "demo_mode": settings.demo_mode,
        "rate_per_min": settings.rate_per_min,
    }


@app.get("/api/schedule")
async def schedule(
    year: int | None = Query(default=None, ge=2000, le=2100),
    week: int | None = Query(default=None, ge=1, le=53),
    air_type: str = Query(default="sub"),
) -> JSONResponse:
    if year is None or week is None:
        iw = current_iso_week(settings.timezone)
        year, week = iw.year, iw.week
    try:
        data = await asyncio.wait_for(_service.weekly(year, week, air_type), timeout=30)
    except asyncio.TimeoutError:
        return JSONResponse({"error": "upstream timeout"}, status_code=503)
    # Short client cache so a phone refreshing / re-focusing doesn't hammer the
    # backend; the app also auto-refreshes every 5 min.
    return JSONResponse(to_jsonable(data), headers={"Cache-Control": "private, max-age=60"})


@app.get("/api/releases")
async def releases(
    range: str = Query(default="daily"),
    anchor: str | None = Query(default=None),
    air_type: str = Query(default="sub"),
) -> JSONResponse:
    """Daily / Weekly / Monthly schedule of releases grouped by date.
    `anchor` (YYYY-MM-DD) defaults to today in the app timezone."""
    from datetime import date as _date
    from zoneinfo import ZoneInfo

    try:
        anc = _date.fromisoformat(anchor) if anchor else None
    except ValueError:
        anc = None
    if anc is None:
        anc = datetime.now(ZoneInfo(settings.timezone)).date()
    # schedule_view clamps the anchor to its navigable window (single source of
    # truth) and reports has_prev/has_next.
    try:
        data = await asyncio.wait_for(_service.schedule_view(range, anc, air_type), timeout=30)
    except asyncio.TimeoutError:
        return JSONResponse({"error": "upstream timeout"}, status_code=503)
    return JSONResponse(to_jsonable(data), headers={"Cache-Control": "private, max-age=60"})


@app.get("/api/debug")
async def debug(air_type: str = Query(default="sub")) -> JSONResponse:
    """Raw look at the live timetable response (no secrets) to diagnose parsing.
    Disabled by default; set APP_DEBUG=1 to enable (exposes upstream internals)."""
    if not settings.debug_enabled:
        raise HTTPException(status_code=404)
    iw = current_iso_week(settings.timezone)
    out: dict = {
        "week": [iw.year, iw.week],
        "tz": settings.timezone,
        "demo_mode": settings.demo_mode,
        "token_present": settings.has_token,
    }
    try:
        sub_raw, meta = await _service.animeschedule.timetable(air_type, iw.year, iw.week, settings.timezone)
        sub_raw = sub_raw or []
        out["sub_entry_count"] = len(sub_raw)
        out["response_is_list"] = isinstance(sub_raw, list)
        out["census"] = _stream_census(sub_raw, [])
        out["fetched_at"] = meta.fetched_at.isoformat() if meta and meta.fetched_at else None

        # Parsed result: the real pipeline applied to live data. cr_match_count > 0
        # is the live "it works" signal.
        cr = [e for e in (_normalize_entry(x) for x in sub_raw) if is_crunchyroll(e)]
        out["cr_match_count"] = len(cr)
        out["cr_sample"] = (
            {
                "route": cr[0].route,
                "title": cr[0].title,
                "episode": cr[0].episode_number,
                "air_at_utc": cr[0].air_at.isoformat() if cr[0].air_at else None,
                "crunchyroll_url": cr[0].streams.get("crunchyroll"),
            }
            if cr
            else None
        )
    except Exception as exc:  # surface the failure rather than 500
        out["error"] = f"{type(exc).__name__}: {exc}"

    # /anime response shape (to design the AniList ID join without guessing)
    try:
        adata, _ = await _service.animeschedule.anime_probe()
        out["anime_response_type"] = type(adata).__name__
        if isinstance(adata, list):
            out["anime_count"] = len(adata)
            out["anime_sample"] = adata[0] if adata else None
        elif isinstance(adata, dict):
            out["anime_top_keys"] = sorted(adata.keys())
            for k in ("anime", "page", "results", "data"):
                v = adata.get(k)
                if isinstance(v, list) and v:
                    out["anime_list_key"] = k
                    out["anime_sample"] = v[0]
                    break
    except Exception as exc:
        out["anime_error"] = f"{type(exc).__name__}: {exc}"

    return JSONResponse(out)


@app.get("/api/calendar.ics")
async def calendar_ics(
    routes: str | None = Query(default=None),
    air_type: str = Query(default="sub"),
) -> Response:
    """iCalendar feed of upcoming Crunchyroll episodes (next ~4 weeks) — subscribe
    in your phone's calendar (use the http(s) URL as a subscription/'webcal' feed).

    Optional `routes` (comma-separated show routes) limits the feed, e.g. to your
    favorites. `air_type` selects sub or dub timing.
    """
    norm_air = "dub" if air_type == "dub" else "sub"
    releases = await _service.upcoming_releases(28, norm_air)
    route_filter = {r for r in routes.split(",") if r} if routes else None
    calname = f"Crunchyroll Schedule ({norm_air})"
    body = build_ics_events(releases, calname=calname, routes=route_filter)
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="crunchyroll-schedule.ics"',
            "Cache-Control": "private, max-age=300",
        },
    )


@app.get("/")
async def index() -> HTMLResponse:
    # Serve index.html with a per-deploy cache-busting token so the browser never
    # pairs a fresh HTML with a stale app.js/style.css. The token is the newest
    # mtime of those assets; index.html itself is always revalidated (no-cache).
    html = (STATIC_DIR / "index.html").read_text()
    try:
        v = int(max(
            (STATIC_DIR / "app.js").stat().st_mtime,
            (STATIC_DIR / "style.css").stat().st_mtime,
        ))
    except OSError:
        v = 0
    html = html.replace("__V__", str(v))
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
