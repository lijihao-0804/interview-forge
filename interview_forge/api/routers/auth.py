"""Authentication, profile and session routes backed by services."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import Response

from interview_forge.api.support import (
    async_require_user, client_ip, current_user,
    error_response, json_response, read_json, require_user, service_error, session_cookie,
)
from interview_forge.core.rate_limit import (
    login_rate_limit_clear, login_rate_limit_fail, login_rate_limit_ok,
)
from interview_forge.services.auth import (
    auth_login, change_own_password, create_session, destroy_session,
)
from interview_forge.services.community import (
    feedback_rate_limit_ok, feedback_rate_limit_record, get_avatar, get_profile,
    set_profile, submit_feedback,
)
from interview_forge.services.registration import register_with_email_code, send_registration_code

router = APIRouter()


def _cookie(request: Request) -> str:
    for part in request.headers.get("cookie", "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == "forge_session":
            return value
    return ""


def _handled(exc: BaseException, *, write: bool = False):
    return service_error(exc, write=write) or error_response("服务暂时不可用", 500)


@router.get("/api/me")
def me(request: Request):
    user = current_user(request)
    if user is None:
        return error_response("未登录", 401)
    return json_response({
        "username": str(user["username"]),
        "nickname": str(user["nickname"]),
        "lang": str(user["lang"]),
        "role": str(user["role"]),
    })


@router.post("/api/login")
async def login(request: Request):
    try:
        payload = await read_json(request)
        ip = client_ip(request)
        if not login_rate_limit_ok(ip):
            raise ValueError("尝试次数过多，请 10 分钟后再试")
        try:
            user = await asyncio.to_thread(
                auth_login, str(payload.get("username", "")).strip(), str(payload.get("password", ""))
            )
        except ValueError:
            login_rate_limit_fail(ip)
            raise
        login_rate_limit_clear(ip)
        token = await asyncio.to_thread(create_session, int(user["id"]))
        response = json_response({"ok": True, "username": str(user["username"]), "role": str(user["role"])}, 201)
        response.headers["set-cookie"] = session_cookie(request, token)
        return response
    except BaseException as exc:
        return _handled(exc, write=True)


@router.post("/api/register/send-code")
async def register_send_code(request: Request):
    try:
        payload = await read_json(request)
        result = await asyncio.to_thread(
            send_registration_code,
            payload.get("email", ""),
            client_ip(request),
        )
        return json_response(result)
    except BaseException as exc:
        return _handled(exc, write=True)


@router.post("/api/register")
async def register(request: Request):
    try:
        payload = await read_json(request)
        user = await asyncio.to_thread(
            register_with_email_code,
            payload.get("email", ""),
            payload.get("username", ""),
            payload.get("password", ""),
            payload.get("code", ""),
            client_ip(request),
        )
        token = await asyncio.to_thread(create_session, int(user["id"]))
        response = json_response({"ok": True, "username": str(user["username"]), "role": str(user["role"])}, 201)
        response.headers["set-cookie"] = session_cookie(request, token)
        return response
    except BaseException as exc:
        return _handled(exc, write=True)


@router.post("/api/logout")
async def logout(request: Request):
    user, denied = await async_require_user(request)
    if denied is not None:
        return denied
    try:
        await read_json(request)
        token = _cookie(request)
        if token:
            await asyncio.to_thread(destroy_session, token)
        response = json_response({"ok": True}, 201)
        response.headers["set-cookie"] = session_cookie(request, "", expire=True)
        return response
    except BaseException as exc:
        return _handled(exc, write=True)


@router.get("/api/profile")
def profile_get(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        return json_response(get_profile(str(user["username"])))
    except BaseException as exc:
        return _handled(exc)


@router.post("/api/profile")
async def profile_set(request: Request):
    user, denied = await async_require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request, max_length=262144)
        result = await asyncio.to_thread(
            set_profile, str(user["username"]), payload.get("nickname") if "nickname" in payload else None,
            payload.get("avatar") if "avatar" in payload else None,
            payload.get("lang") if "lang" in payload else None,
        )
        return json_response(result, 201)
    except BaseException as exc:
        return _handled(exc, write=True)


@router.post("/api/password")
async def password(request: Request):
    user, denied = await async_require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
        result = await asyncio.to_thread(
            change_own_password, int(user["id"]), str(payload.get("old_password", "")),
            str(payload.get("new_password", "")), keep_token=_cookie(request),
        )
        return json_response(result, 201)
    except BaseException as exc:
        return _handled(exc, write=True)


@router.get("/api/avatar/{username}")
def avatar(request: Request, username: str):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        value = get_avatar(username)
        if value is None:
            return error_response("未设置头像", 404)
        mime, blob = value
        return Response(content=blob, media_type=mime, headers={"Cache-Control": "max-age=60"})
    except (ValueError, TypeError):
        return error_response("未设置头像", 404)


@router.post("/api/feedback")
async def feedback(request: Request):
    user, denied = await async_require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
        ip = client_ip(request)
        if not feedback_rate_limit_ok(ip):
            raise ValueError("提交过于频繁，请稍后再试")
        feedback_rate_limit_record(ip)
        result = await asyncio.to_thread(
            submit_feedback, str(payload.get("content", "")), str(payload.get("contact", "")),
            str(payload.get("page", "")), request.headers.get("user-agent", ""),
            str(user["username"]),
        )
        return json_response(result, 201)
    except BaseException as exc:
        return _handled(exc, write=True)
