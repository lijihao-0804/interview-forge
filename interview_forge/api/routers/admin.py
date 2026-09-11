"""Administrator-only management routes."""
from __future__ import annotations

from fastapi import APIRouter, Request

from interview_forge.api.support import error_response, json_response, read_json, require_admin, service_error
from interview_forge.services.auth import (
    admin_reset_user_ai_quota, admin_set_user_ai_daily_limit, generate_invite_codes,
    list_invite_codes, list_users, reset_user_nickname, reset_user_password,
    revoke_invite_code, set_user_active, set_user_role,
)
from interview_forge.services.community import list_feedback, resolve_feedback

router = APIRouter()


def _handled(exc: BaseException, *, write: bool = False):
    return service_error(exc, write=write) or error_response("服务暂时不可用", 500)


@router.get("/api/admin/codes")
def codes(request: Request):
    user, denied = require_admin(request)
    if denied is not None:
        return denied
    try:
        return json_response({"items": list_invite_codes()})
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/admin/users")
def users(request: Request):
    user, denied = require_admin(request)
    if denied is not None:
        return denied
    try:
        return json_response({"items": list_users()})
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/admin/feedback")
def feedback_list(request: Request):
    user, denied = require_admin(request)
    if denied is not None:
        return denied
    try:
        return json_response({"items": list_feedback(request.query_params.get("status", ""))})
    except BaseException as exc:
        return _handled(exc)


async def _payload(request: Request):
    try:
        return await read_json(request)
    except BaseException:
        raise


@router.post("/api/admin/codes")
async def codes_create(request: Request):
    return await _admin_write(request, lambda p, u: {"codes": generate_invite_codes(int(p.get("count", 1)), int(p.get("days", 0) or 0), str(p.get("note", "")), int(u["id"]))})


@router.post("/api/admin/codes/revoke")
async def codes_revoke(request: Request):
    return await _admin_write(request, lambda p, u: revoke_invite_code(str(p.get("code", ""))))


@router.post("/api/admin/users/toggle")
async def user_toggle(request: Request):
    def operation(p, u):
        if not isinstance(p.get("active"), bool):
            raise ValueError("active 必须是布尔值")
        return set_user_active(str(p.get("username", "")), p["active"])
    return await _admin_write(request, operation)


@router.post("/api/admin/users/role")
async def user_role(request: Request):
    return await _admin_write(request, lambda p, u: set_user_role(str(p.get("username", "")), str(p.get("role", "")), str(u["username"])))


@router.post("/api/admin/users/nickname/reset")
async def user_nickname_reset(request: Request):
    return await _admin_write(request, lambda p, u: reset_user_nickname(str(p.get("username", "")), str(u["username"])))


@router.post("/api/admin/users/ai-quota/reset")
async def user_quota_reset(request: Request):
    def operation(p, u):
        if set(p) != {"username"}:
            raise ValueError("请求参数不正确")
        return admin_reset_user_ai_quota(str(p.get("username", "")), int(u["id"]))
    return await _admin_write(request, operation)


@router.post("/api/admin/users/ai-quota/limit")
async def user_quota_limit(request: Request):
    def operation(p, u):
        if set(p) != {"username", "limit"}:
            raise ValueError("请求参数不正确")
        return admin_set_user_ai_daily_limit(str(p.get("username", "")), p.get("limit"), int(u["id"]))
    return await _admin_write(request, operation)


@router.post("/api/admin/users/reset-password")
async def user_password_reset(request: Request):
    return await _admin_write(request, lambda p, u: reset_user_password(str(p.get("username", "")), str(p.get("new_password", ""))))


@router.post("/api/admin/feedback/resolve")
async def feedback_resolve(request: Request):
    def operation(p, u):
        if not isinstance(p.get("resolved"), bool):
            raise ValueError("resolved 必须是布尔值")
        return resolve_feedback(int(p.get("id", 0)), p["resolved"], str(p.get("note", "")))
    return await _admin_write(request, operation)


async def _admin_write(request: Request, operation):
    user, denied = require_admin(request)
    if denied is not None:
        return denied
    try:
        payload = await _payload(request)
        return json_response(operation(payload, user), 201)
    except BaseException as exc:
        return _handled(exc, write=True)
