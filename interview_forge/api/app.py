"""FastAPI + Uvicorn application assembly.

All current API and Web Root paths are registered by domain routers.  The
former StudyHandler adapter remains importable for legacy unit tests and an
explicit fallback command, but is intentionally not included in this app.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
import time
import uuid

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response

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
from interview_forge.api.routers.admin_observability import router as admin_observability_router
from interview_forge.api.routers.admin_operations import router as admin_operations_router
from interview_forge.api.routers.admin_ai_config import router as admin_ai_config_router
from interview_forge.core.async_http import AsyncHttpClient
from interview_forge.runtime.task_manager import task_manager

# Import only the lightweight task facades so their existing backends register
# once.  Optional provider SDKs remain lazy and are not imported here.
from interview_forge.services import leetcode as _leetcode_service  # noqa: F401
from interview_forge.ai import tasks as _ai_tasks  # noqa: F401
from interview_forge.observability.logging import log_event
from interview_forge.observability.store import enqueue_request, start_metrics_writer, stop_metrics_writer


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Keep startup/shutdown explicit without eagerly importing optional AI SDKs
    # or opening a production database connection during module import.
    client = AsyncHttpClient()
    await client.start()
    start_metrics_writer()
    app.state.http_client = client
    app.state.task_manager = task_manager
    try:
        yield
    finally:
        stop_metrics_writer()
        await client.close()


app = FastAPI(
    title="InterviewForge API",
    version="2",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


def _same_origin_request(request) -> bool:
    """Reject cross-site state-changing requests without breaking CLI clients."""
    origin = (request.headers.get("origin") or "").strip()
    if not origin:
        return True
    host = (request.headers.get("host") or "").strip()
    allowed = {
        "http://localhost", "http://127.0.0.1", "http://localhost:8765", "http://127.0.0.1:8765",
        f"http://{host}", f"https://{host}",
    }
    return origin in allowed

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
    request.state.request_id = request_id
    origin = request.headers.get("origin", "")
    cors_origins = {"http://localhost", "http://127.0.0.1", "http://localhost:8765", "http://127.0.0.1:8765"}
    try:
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
        elif request.method in {"POST", "PUT", "PATCH", "DELETE"} and not _same_origin_request(request):
            response = JSONResponse({"error": "跨站请求被拒绝"}, status_code=403)
        else:
            response = await call_next(request)
    except Exception as exc:
        # Exception handlers may turn this into a 500 response later, but the
        # request event must still exist even when the router never returned.
        log_event(
            "api_request",
            module="api",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=500,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            error_type=type(exc).__name__,
        )
        enqueue_request(
            route=getattr(request.scope.get("route"), "path", ""),
            path=request.url.path,
            method=request.method,
            status=500,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        raise
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    response.headers.setdefault(
        "Content-Security-Policy-Report-Only",
        "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; "
        "font-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'self'; form-action 'self'",
    )
    session_token = getattr(request.state, "session_token", "")
    if session_token:
        from interview_forge.api.support import session_cookie
        response.headers["Set-Cookie"] = session_cookie(request, session_token)
    if origin in cors_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRFToken"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    log_event(
        "api_request",
        module="api",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        elapsed_ms=elapsed,
    )
    enqueue_request(
        route=getattr(request.scope.get("route"), "path", ""),
        path=request.url.path,
        method=request.method,
        status=response.status_code,
        elapsed_ms=elapsed,
    )
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
app.include_router(admin_observability_router)
app.include_router(admin_operations_router)
app.include_router(admin_ai_config_router)
app.include_router(static_router)
