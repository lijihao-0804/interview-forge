"""FastAPI + Uvicorn application assembly.

All current API and Web Root paths are registered by domain routers.  The
former StudyHandler adapter remains importable for legacy unit tests and an
explicit fallback command, but is intentionally not included in this app.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import json
import logging
import time
import uuid

from fastapi import FastAPI
from fastapi.responses import Response

from interview_forge.api.routers.health import router as health_router
from interview_forge.api.routers.auth import router as auth_router
from interview_forge.api.routers.admin import router as admin_router
from interview_forge.api.routers.analytics import router as analytics_router
from interview_forge.api.routers.community import router as community_router
from interview_forge.api.routers.leetcode import router as leetcode_router
from interview_forge.api.routers.study import router as study_router
from interview_forge.api.routers.weather import router as weather_router
from interview_forge.api.routers.static import router as static_router
from interview_forge.api.routers.chat import router as chat_router
from interview_forge.core.async_http import AsyncHttpClient
from interview_forge.runtime.task_manager import task_manager

# Import only the lightweight task facades so their existing backends register
# once.  Optional provider SDKs remain lazy and are not imported here.
from interview_forge.services import leetcode as _leetcode_service  # noqa: F401
from interview_forge.ai import tasks as _ai_tasks  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Keep startup/shutdown explicit without eagerly importing optional AI SDKs
    # or opening a production database connection during module import.
    client = AsyncHttpClient()
    await client.start()
    app.state.http_client = client
    app.state.task_manager = task_manager
    try:
        yield
    finally:
        await client.close()


app = FastAPI(
    title="InterviewForge API",
    version="2",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

_logger = logging.getLogger("interview_forge.api")


@app.middleware("http")
async def request_observability(request, call_next):
    """Add a bounded request id and structured, credential-free access log."""
    supplied = (request.headers.get("X-Request-ID") or "").strip()
    request_id = (
        supplied[:96]
        if supplied and all(ch.isalnum() or ch in "-_." for ch in supplied)
        else uuid.uuid4().hex
    )
    started = time.perf_counter()
    origin = request.headers.get("origin", "")
    cors_origins = {"http://localhost", "http://127.0.0.1", "http://localhost:8765", "http://127.0.0.1:8765"}
    if request.method == "OPTIONS":
        if origin in cors_origins:
            response = Response(status_code=204, headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Headers": "Content-Type, X-CSRFToken",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Max-Age": "3600",
            })
        else:
            response = Response(status_code=405)
    else:
        response = await call_next(request)
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    if origin in cors_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRFToken"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    _logger.info(json.dumps({
        "event": "api_request",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "elapsed_ms": elapsed,
    }, ensure_ascii=False, separators=(",", ":")))
    return response


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(study_router)
app.include_router(leetcode_router)
app.include_router(analytics_router)
app.include_router(community_router)
app.include_router(weather_router)
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(static_router)
