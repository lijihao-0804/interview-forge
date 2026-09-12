"""Small HTTP-boundary helpers shared by the real FastAPI routers.

This module deliberately contains no route table and no business rules.  It
only translates the established cookie/body/error conventions into FastAPI
responses so domain routers can call the existing services directly.
"""
from __future__ import annotations

import ipaddress
import json
import sqlite3
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from interview_forge.ai.errors import AIServiceError
from interview_forge.ai.actions.store import ActionRequestError
from interview_forge.analytics.learning_analytics import AnalyticsUnavailableError
from interview_forge.core.paths import DB_PATH
from interview_forge.services.auth import session_user, user_db_path
from interview_forge.services.leetcode import LeetCodeSyncError


@dataclass
class ApiError(Exception):
    message: str
    status: int = HTTPStatus.BAD_REQUEST
    headers: dict[str, str] | None = None


def json_response(payload: Any, status: int = HTTPStatus.OK, *, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(content=payload, status_code=status, headers=headers or {})


def error_response(message: str, status: int, *, headers: dict[str, str] | None = None, **extra: Any) -> JSONResponse:
    payload = {"error": message, **extra}
    return json_response(payload, status, headers=headers)


def current_user(request: Request):
    token = ""
    for part in request.headers.get("cookie", "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == "forge_session":
            token = value
            break
    try:
        return session_user(token)
    except sqlite3.Error:
        return None


def require_user(request: Request):
    user = current_user(request)
    if user is None:
        return None, error_response("未登录", HTTPStatus.UNAUTHORIZED)
    return user, None


def require_admin(request: Request):
    user, response = require_user(request)
    if response is not None:
        return None, response
    if str(user["role"]) != "admin":
        return None, error_response("需要管理员权限", HTTPStatus.FORBIDDEN)
    return user, None


def user_db(user: Any) -> Path:
    return user_db_path(str(user["username"]))


def invalidate_learning(db_path: Path) -> None:
    from interview_forge.analytics.cache import invalidate_learning_caches
    invalidate_learning_caches(db_path)


def invalidate_dashboard(db_path: Path) -> None:
    from interview_forge.services.study import _invalidate_dashboard_cache
    _invalidate_dashboard_cache(db_path)


async def read_json(request: Request, *, max_length: int = 4096) -> dict[str, Any]:
    """Match the legacy bounded JSON body contract without Pydantic coercion."""
    raw_length = request.headers.get("content-length", "0")
    try:
        length = int(raw_length)
    except (TypeError, ValueError) as exc:
        raise ApiError("请求大小不正确") from exc
    if length < 1 or length > max_length:
        raise ApiError("请求大小不正确")
    if request.headers.get("transfer-encoding"):
        raise ApiError("不支持的 Transfer-Encoding")
    raw = await request.body()
    if len(raw) != length:
        raise ApiError("请求大小不正确")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiError("请求参数不正确") from exc
    if not isinstance(value, dict):
        raise ApiError("请求参数不正确")
    return value


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else ""
    if peer in ("127.0.0.1", "::1"):
        for name in ("x-real-ip", "cf-connecting-ip"):
            value = (request.headers.get(name) or "").strip()
            try:
                return str(ipaddress.ip_address(value))
            except ValueError:
                pass
        for value in reversed((request.headers.get("x-forwarded-for") or "").split(",")):
            try:
                return str(ipaddress.ip_address(value.strip()))
            except ValueError:
                pass
    return peer


def session_cookie(request: Request, token: str, *, expire: bool = False) -> str:
    host = (request.headers.get("host") or "").split(":")[0].strip("[]").lower()
    is_local = (
        "." not in host or host == "::1" or host.startswith(("127.", "10.", "192.168.", "172.16.",
        "172.17.", "172.18.", "172.19.", "172.2", "172.30.", "172.31.")) or host.endswith(".local")
    )
    secure = "" if is_local else "; Secure"
    max_age = 0 if expire else 86400 * 30
    return f"forge_session={token}; Path=/; HttpOnly; SameSite=Lax{secure}; Max-Age={max_age}"


def service_error(exc: BaseException, *, write: bool = False) -> JSONResponse | None:
    if isinstance(exc, ActionRequestError):
        return error_response(exc.message, exc.status, error_category=exc.code)
    if isinstance(exc, ApiError):
        return error_response(exc.message, exc.status, headers=exc.headers)
    if isinstance(exc, LeetCodeSyncError):
        return error_response(exc.user_message, exc.status, error_category=exc.category)
    if isinstance(exc, AIServiceError):
        payload: dict[str, Any] = {"error": exc.user_message, "error_category": exc.category}
        if exc.fallback is not None:
            payload["fallback"] = exc.fallback
        if exc.details:
            payload.update(exc.details)
        return json_response(payload, exc.status)
    if isinstance(exc, AnalyticsUnavailableError):
        return error_response("学习分析暂时不可用，请稍后重试", HTTPStatus.SERVICE_UNAVAILABLE,
                              headers={"Retry-After": "1"}, retryable=True)
    if isinstance(exc, PermissionError):
        return error_response(str(exc), HTTPStatus.FORBIDDEN)
    if isinstance(exc, (KeyError, TypeError, ValueError, json.JSONDecodeError)):
        return error_response(str(exc), HTTPStatus.BAD_REQUEST)
    if isinstance(exc, sqlite3.Error):
        return error_response("数据库写入失败" if write else "数据库读取失败", HTTPStatus.INTERNAL_SERVER_ERROR)
    return None


async def guarded(request: Request, operation: Callable[[], Any], *, write: bool = False):
    """Run a synchronous service operation and preserve controlled error JSON."""
    try:
        return json_response(operation())
    except BaseException as exc:
        response = service_error(exc, write=write)
        if response is not None:
            return response
        return error_response("学习记录写入失败" if write else "服务暂时不可用", HTTPStatus.INTERNAL_SERVER_ERROR)
