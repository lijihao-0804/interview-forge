"""Community search, chat and public feedback routes."""
from __future__ import annotations

from fastapi import APIRouter, Request

from interview_forge.api.support import error_response, json_response, read_json, require_admin, require_user, service_error, user_db
from interview_forge.services.community import (
    chat_delete, chat_has_older, chat_messages_after, chat_messages_before, chat_rate_limit_ok,
    chat_rate_limit_record, chat_send, search_index_server,
)

router = APIRouter()


def _handled(exc: BaseException, *, write: bool = False):
    return service_error(exc, write=write) or error_response("服务暂时不可用", 500)


@router.get("/api/search")
def search(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        return json_response({"items": search_index_server(request.query_params.get("q", ""))})
    except (OSError, ValueError, TypeError):
        return error_response("搜索索引不可用", 500)


@router.get("/api/chat/messages")
def chat_messages(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    params = request.query_params
    if "after" in params and "before" in params:
        return error_response("after 与 before 不能同时使用", 400)
    try:
        limit = max(1, min(int(params.get("limit", "50")), 100))
    except ValueError:
        return error_response("limit 必须是整数", 400)
    try:
        if "before" in params:
            before = int(params["before"])
            if before <= 0:
                return error_response("before 必须大于 0", 400)
            items, has_older = chat_messages_before(before, limit)
            return json_response({"items": items, "has_older": has_older})
        after = int(params.get("after", "-1"))
        items = chat_messages_after(after, limit)
        oldest_id = int(items[0]["id"]) if items else None
        return json_response({"items": items, "has_older": chat_has_older(oldest_id) if after < 0 else None})
    except ValueError as exc:
        return error_response(str(exc), 400)
    except BaseException as exc:
        return _handled(exc)


@router.post("/api/chat/send")
async def chat_send_route(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
        if not chat_rate_limit_ok(int(user["id"])):
            raise ValueError("发言太快了，休息一下再发")
        chat_rate_limit_record(int(user["id"]))
        result = chat_send(int(user["id"]), str(user["username"]), str(payload.get("content", "")))
        return json_response(result, 201)
    except BaseException as exc:
        return _handled(exc, write=True)


@router.post("/api/admin/chat/delete")
async def chat_delete_route(request: Request):
    user, denied = require_admin(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
        return json_response(chat_delete(int(payload.get("id", 0))), 201)
    except BaseException as exc:
        return _handled(exc, write=True)
