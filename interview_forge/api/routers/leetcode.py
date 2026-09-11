"""LeetCode credentials, status and synchronization routes."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from interview_forge.api.support import error_response, invalidate_dashboard, invalidate_learning, json_response, read_json, require_user, service_error, user_db
from interview_forge.services.leetcode import (
    LeetCodeSyncError, clear_credentials, get_credentials, lc_status_cached, lc_status_invalidate,
    leetcode_status, leetcode_sync_async, set_credentials,
)
from interview_forge.runtime.task_manager import task_manager

router = APIRouter()


def _handled(exc: BaseException):
    return service_error(exc, write=True) or error_response("服务暂时不可用", 500)


@router.get("/api/leetcode/status")
def status(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        db = user_db(user)
        credentials = get_credentials(db)
        checked = lc_status_cached(db, credentials, force=request.query_params.get("refresh") == "1")
        return json_response({"credentials_saved": bool(credentials.get("leetcode_session")), **checked})
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/leetcode/sync/status")
def sync_status(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    task_id = request.query_params.get("task_id", "")
    if not task_id:
        return error_response("缺少 task_id", 400)
    try:
        result = task_manager.query("leetcode", task_id, owner=str(user["username"]))
        if result is None:
            return error_response("任务不存在或已过期", 404)
        return json_response(result)
    except BaseException as exc:
        return _handled(exc)


@router.post("/api/leetcode/connect")
async def connect(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
        db = user_db(user)
        set_credentials({"leetcode_session": str(payload.get("leetcode_session", "")),
                         "leetcode_csrf": str(payload.get("leetcode_csrf", ""))}, db)
        lc_status_invalidate(db)
        invalidate_dashboard(db)
        checked = await asyncio.to_thread(leetcode_status, get_credentials(db))
        return json_response({"saved": True, **checked}, 201)
    except BaseException as exc:
        return _handled(exc)


@router.post("/api/leetcode/sync")
async def sync(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
        full = str(payload.get("full", "0")) in ("1", "true", "True")
        db = user_db(user)
        credentials = get_credentials(db)
        if not credentials.get("leetcode_session"):
            raise LeetCodeSyncError("not_configured", "请先前往力扣连接页面填写 LEETCODE_SESSION", 409)
        if payload.get("async") in (1, True, "1", "true", "True"):
            task_id = task_manager.submit("leetcode", credentials, full, owner=str(user["username"]), db_path=db)
            return json_response({"ok": True, "task_id": task_id}, 201)
        result = {"ok": True, **await leetcode_sync_async(credentials, db_path=db, full=full)}
        invalidate_learning(db)
        return json_response(result, 201)
    except BaseException as exc:
        return _handled(exc)


@router.post("/api/leetcode/clear")
async def clear(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        db = user_db(user)
        clear_credentials(db)
        lc_status_invalidate(db)
        invalidate_dashboard(db)
        return json_response({"cleared": True}, 201)
    except BaseException as exc:
        return _handled(exc)
