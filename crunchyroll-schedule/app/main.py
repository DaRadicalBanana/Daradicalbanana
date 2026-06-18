"""FastAPI app: serves the weekly calendar UI and a JSON schedule endpoint.

Run locally:
    uvicorn app.main:app --reload
Then open http://127.0.0.1:8000
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import settings
from .ics import build_ics
from .isoweek import current_iso_week
from .models import to_jsonable
from .service import ScheduleService, _stream_census

app = FastAPI(title="Crunchyroll Weekly Schedule", version="0.1.0")
_service = ScheduleService(settings)

STATIC_DIR = Path(__file__).resolve().parent / "static"


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
    year: int | None = Query(default=None),
    week: int | None = Query(default=None),
    air_type: str = Query(default="sub"),
) -> JSONResponse:
    if year is None or week is None:
        iw = current_iso_week(settings.timezone)
        year, week = iw.year, iw.week
    data = await _service.weekly(year, week, air_type)
    # Short client cache so a phone refreshing / re-focusing doesn't hammer the
    # backend; the app also auto-refreshes every 5 min.
    return JSONResponse(to_jsonable(data), headers={"Cache-Control": "private, max-age=60"})


@app.get("/api/debug")
async def debug(air_type: str = Query(default="sub")) -> JSONResponse:
    """Raw look at the live timetable response (no secrets) to diagnose parsing.
    Returns the first sub/raw entries verbatim plus a stream-key census."""
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
        out["sub_sample_entry"] = sub_raw[0] if sub_raw else None
        out["response_is_list"] = isinstance(sub_raw, list)
        out["census"] = _stream_census(sub_raw, [])
        out["fetched_at"] = meta.fetched_at.isoformat() if meta and meta.fetched_at else None
    except Exception as exc:  # surface the failure rather than 500
        out["error"] = f"{type(exc).__name__}: {exc}"
    return JSONResponse(out)


@app.get("/api/calendar.ics")
async def calendar_ics(
    routes: str | None = Query(default=None),
    air_type: str = Query(default="sub"),
) -> Response:
    """iCalendar feed of each show's next episode — subscribe in your phone's
    calendar (use the http(s) URL as a subscription/'webcal' feed).

    Optional `routes` (comma-separated show routes) limits the feed, e.g. to your
    favorites. `air_type` selects sub or dub timing.
    """
    iw = current_iso_week(settings.timezone)
    data = await _service.weekly(iw.year, iw.week, air_type)
    route_filter = {r for r in routes.split(",") if r} if routes else None
    calname = f"Crunchyroll Schedule ({data.air_type})"
    body = build_ics(data, calname=calname, routes=route_filter)
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="crunchyroll-schedule.ics"',
            "Cache-Control": "private, max-age=300",
        },
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
