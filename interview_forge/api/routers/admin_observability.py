"""Admin-only observability HTTP boundary."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from interview_forge.api.support import error_response, json_response, require_admin, service_error
from interview_forge.services import admin_observability as service

router = APIRouter()


def _call(request: Request, operation):
    _, denied = require_admin(request)
    if denied is not None:
        return denied
    try:
        return json_response(operation())
    except BaseException as exc:
        return service_error(exc) or error_response("服务暂时不可用", 500)


@router.get("/api/admin/logs")
def admin_logs(
    request: Request,
    level: str = Query(default="", max_length=32),
    module: str = Query(default="", max_length=96),
    event: str = Query(default="", max_length=128),
    request_id: str = Query(default="", max_length=128),
    limit: int = Query(default=100, ge=1, le=500),
):
    return _call(request, lambda: service.list_logs(level=level, module=module, event=event, request_id=request_id, limit=limit))


@router.get("/api/admin/overview")
def admin_overview(request: Request):
    return _call(request, service.overview)


@router.get("/api/admin/ai/usage")
def admin_ai_usage(
    request: Request,
    window: str = Query(default="24h", max_length=8),
    username: str = Query(default="", max_length=32),
    model: str = Query(default="", max_length=128),
):
    return _call(request, lambda: service.ai_usage(window=window, username=username, model=model))


@router.get("/api/admin/ai/traces")
def admin_ai_traces(
    request: Request,
    username: str = Query(default="", max_length=32),
    status: str = Query(default="", max_length=32),
    model: str = Query(default="", max_length=128),
    window: str = Query(default="24h", max_length=8),
    limit: int = Query(default=100, ge=1, le=500),
):
    return _call(request, lambda: service.list_traces(username=username, status=status, model=model, window=window, limit=limit))


@router.get("/api/admin/ai/traces/{trace_id}")
def admin_trace_detail(request: Request, trace_id: str, username: str = Query(default="", max_length=32)):
    def operation():
        payload = service.trace_detail(trace_id, username=username)
        if payload is None:
            raise LookupError("分析记录不存在")
        return payload
    return _call(request, operation)


__all__ = ["router"]
