"""Authenticated persistent AI chat routes."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from interview_forge.ai.chat.service import ChatService, MAX_CHAT_BODY_BYTES, normalize_message
from interview_forge.api.support import error_response, json_response, read_json, require_user, service_error, user_db
from interview_forge.runtime.streaming import sse_events


router = APIRouter()
chat_service = ChatService()


def _handled(exc: BaseException, *, write: bool = False):
    return service_error(exc, write=write) or error_response("服务暂时不可用", 500)


@router.post("/api/chat/sessions")
async def create_session(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
        if payload:
            raise ValueError("请求参数不正确")
        return json_response(chat_service.create_session(user_db=user_db(user)), 201)
    except BaseException as exc:
        return _handled(exc, write=True)


@router.get("/api/chat/sessions")
def list_sessions(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        return json_response({"items": chat_service.list_sessions(user_db=user_db(user))})
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/chat/sessions/{session_id}/messages")
def list_messages(request: Request, session_id: str):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        db_path = user_db(user)
        session = chat_service.get_session(user_db=db_path, session_id=session_id)
        if session is None:
            return error_response("会话不存在", 404)
        return json_response({"session": session, "items": chat_service.list_messages(user_db=db_path, session_id=session_id)})
    except BaseException as exc:
        return _handled(exc)


@router.post("/api/chat/sessions/{session_id}/stream")
async def stream_session(request: Request, session_id: str):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request, max_length=MAX_CHAT_BODY_BYTES)
        if set(payload) != {"message"}:
            raise ValueError("请求参数不正确")
        message = normalize_message(payload.get("message"))
        db_path = user_db(user)
        if chat_service.get_session(user_db=db_path, session_id=session_id) is None:
            return error_response("会话不存在", 404)
        source = chat_service.stream_reply(user_db=db_path, session_id=session_id, message=message)
        return StreamingResponse(
            sse_events(source, request=request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except BaseException as exc:
        return _handled(exc, write=True)
