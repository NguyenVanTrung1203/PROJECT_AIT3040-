"""Process-local mock, replay, and optional synthetic inference API."""
from contextlib import asynccontextmanager
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
from backend.app.replay_api import build_default_replay_api, router as replay_router
from backend.app.runtime_http import RuntimeState, router as runtime_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.s5_runtime.start()
    try:
        yield
    finally:
        app.state.s5_runtime.close()


app = FastAPI(
    title="AIT3040 Track Data API",
    version="0.2.0",
    description="T04 mock tracks and Contract V1 Replay fixture endpoints; replay state is process-local and not production durable.",
    lifespan=lifespan,
)
app.state.s5_runtime = RuntimeState()
app.state.replay_api = app.state.s5_runtime.replay
app.include_router(replay_router)
app.include_router(runtime_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error_code" in exc.detail and "message" in exc.detail:
        body = ErrorResponse(error_code=exc.detail["error_code"],
                             message=exc.detail["message"],
                             details=exc.detail.get("details"))
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))
    code = "VESSEL_NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
    details = {"path": request.url.path} if exc.status_code == 404 else None
    body = ErrorResponse(error_code=code, message=str(exc.detail), details=details)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    body = ErrorResponse(
        error_code="INVALID_REQUEST",
        message="The request does not match the API contract.",
        details={"errors": [
            {key: error.get(key) for key in ("type", "loc", "msg")}
            for error in exc.errors()
        ]},
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
