"""Small mock-only API for the Sprint 1 track map scaffold."""
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.mock_tracks import (
    DataStatus,
    ErrorResponse,
    SourceType,
    TrackListResponse,
    TrackSnapshot,
    get_track,
    list_tracks,
)


app = FastAPI(
    title="AIT3040 Mock Track API",
    version="0.1.0",
    description="Deterministic simulated TrackSnapshot data for map development; no inference or risk results.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "VESSEL_NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
    details = {"path": request.url.path} if exc.status_code == 404 else None
    body = ErrorResponse(error_code=code, message=str(exc.detail), details=details)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    body = ErrorResponse(
        error_code="INVALID_REQUEST",
        message="The request does not match the mock track API parameters.",
        details={"errors": exc.errors()},
    )
    return JSONResponse(status_code=422, content=body.model_dump(mode="json"))


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "mock-track-api"}


@app.get(
    "/api/v1/mock/tracks",
    response_model=TrackListResponse,
    tags=["mock-tracks"],
    summary="List deterministic mock TrackSnapshot objects",
)
def read_tracks(
    source_type: SourceType | None = Query(default=None),
    data_status: DataStatus | None = Query(default=None),
) -> TrackListResponse:
    tracks = list_tracks(source_type)
    if data_status is not None:
        tracks = [track for track in tracks if track.data_status == data_status]
    return TrackListResponse(items=tracks, total=len(tracks))


@app.get(
    "/api/v1/mock/tracks/{vessel_id}",
    response_model=TrackSnapshot,
    responses={404: {"model": ErrorResponse}},
    tags=["mock-tracks"],
    summary="Get one mock track and its as-of history",
)
def read_track(vessel_id: str) -> TrackSnapshot:
    track = get_track(vessel_id)
    if track is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Unknown mock vessel: {vessel_id}")
    return track
