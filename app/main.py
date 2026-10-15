from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.forbidden import FORBIDDEN_PATH_FRAGMENTS
from app.logging_util import configure_logging
from app.models import AnalysisResponse, DataSourceKind, RankingMode
from app.service import analyze_payload, select_client
from app.stations import search_stations

logger = configure_logging()

STATIC = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="IRCTC Train Seat Intelligence Engine", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "read_only": True,
        "booking_disabled": True,
        "forbidden_path_fragments": list(FORBIDDEN_PATH_FRAGMENTS),
    }


@app.get("/api/stations")
def stations(q: str = Query("", max_length=40), limit: int = Query(12, ge=1, le=25)) -> dict:
    matches = search_stations(q, limit=limit)
    return {"query": q.strip(), "results": matches}


def _error_payload(message: str) -> dict:
    return AnalysisResponse(
        ok=False,
        data_source=DataSourceKind.live,
        freshness_label="request failed",
        ranking_mode=RankingMode.segments,
        errors=[message],
    ).model_dump()


@app.exception_handler(Exception)
async def unhandled_error(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error: %s", exc)
    return JSONResponse(_error_payload(f"Analyse failed: {exc}"))


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if not request.url.path.startswith("/api/"):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    if exc.status_code == 404:
        return JSONResponse({"ok": False, "errors": ["Not found"]}, status_code=404)
    return JSONResponse(_error_payload(str(exc.detail)), status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return await request_validation_exception_handler(request, exc)


@app.post("/api/analyze", response_model=AnalysisResponse)
def analyze(payload: dict) -> AnalysisResponse:
    try:
        return analyze_payload(payload)
    except Exception as exc:
        logger.exception("analyze failed: %s", exc)
        return AnalysisResponse(
            ok=False,
            data_source=DataSourceKind.live,
            freshness_label="request failed",
            ranking_mode=RankingMode.segments,
            errors=[f"Analyse failed: {exc}"],
        )


def run() -> None:
    uvicorn.run("app.main:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    select_client()
    run()
