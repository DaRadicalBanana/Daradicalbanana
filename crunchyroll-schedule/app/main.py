"""FastAPI app: serves the weekly calendar UI and a JSON schedule endpoint.

Run locally:
    uvicorn app.main:app --reload
Then open http://127.0.0.1:8000
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .isoweek import current_iso_week
from .models import to_jsonable
from .service import ScheduleService

app = FastAPI(title="Crunchyroll Weekly Schedule", version="0.1.0")
_service = ScheduleService(settings)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "timezone": settings.timezone,
        "animeschedule_token_present": settings.has_token,
        "rate_per_min": settings.rate_per_min,
    }


@app.get("/api/schedule")
async def schedule(
    year: int | None = Query(default=None),
    week: int | None = Query(default=None),
) -> JSONResponse:
    if year is None or week is None:
        iw = current_iso_week(settings.timezone)
        year, week = iw.year, iw.week
    data = await _service.weekly(year, week)
    return JSONResponse(to_jsonable(data))


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
