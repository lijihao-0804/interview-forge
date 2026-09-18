"""Admin-only operational projections."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from interview_forge.api.support import error_response, json_response, require_admin, service_error
from interview_forge.services import admin_operations as service

router = APIRouter()


def _call(request: Request, operation):
    _, denied = require_admin(request)
    if denied is not None:
        return denied
    try:
        return json_response(operation())
    except BaseException as exc:
        return service_error(exc) or error_response("服务暂时不可用", 500)


@router.get("/api/admin/tasks")
def admin_tasks(request: Request, kind: str = Query(default="", max_length=16), status: str = Query(default="", max_length=32), username: str = Query(default="", max_length=32), limit: int = Query(default=100, ge=1, le=500)):
    return _call(request, lambda: service.list_tasks(kind=kind, status=status, username=username, limit=limit))


@router.get("/api/admin/actions")
def admin_actions(request: Request, username: str = Query(default="", max_length=32), tool: str = Query(default="", max_length=96), status: str = Query(default="", max_length=32), window: str = Query(default="24h", max_length=8), limit: int = Query(default=100, ge=1, le=500)):
    return _call(request, lambda: service.list_actions(username=username, tool=tool, status=status, window=window, limit=limit))


@router.get("/api/admin/metrics/leetcode")
def admin_leetcode_health(request: Request, window: str = Query(default="24h", max_length=8)):
    return _call(request, lambda: service.leetcode_health(window=window))


@router.get("/api/admin/users/{username}/detail")
def admin_user_detail(request: Request, username: str):
    return _call(request, lambda: service.user_detail(username))


@router.get("/api/admin/memory/summary")
def admin_memory_summary(request: Request, username: str = Query(default="", max_length=32)):
    return _call(request, lambda: service.memory_summary(username=username))


@router.get("/api/admin/system/info")
def admin_system_info(request: Request):
    return _call(request, service.system_info)


@router.post("/api/admin/system/diagnostics")
def admin_diagnostics(request: Request):
    return _call(request, service.diagnostics)


__all__ = ["router"]
