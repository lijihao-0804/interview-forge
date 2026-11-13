"""Authenticated persistent AI chat routes."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import suppress
from pathlib import Path
from typing import Any

from anyio import CancelScope
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from interview_forge.ai.actions.service import ActionService
from interview_forge.ai.actions.store import ActionRequestStore
from interview_forge.ai.chat.diagnostics import turn_context
from interview_forge.ai.chat.page_context import PageContext
from interview_forge.ai.chat.service import (
    MAX_CHAT_BODY_BYTES,
    ChatService,
    claim_chat_session,
    normalize_message,
    release_chat_session,
)
from interview_forge.ai.quota import consume_chat_quota, refund_unstarted_chat
from interview_forge.api.support import (
    async_require_user,
    error_response,
    json_response,
    read_json,
    require_user,
    service_error,
    user_db,
)
from interview_forge.runtime.streaming import sse_events

router = APIRouter()
chat_service = ChatService()
action_service = ActionService(registry=chat_service.tool_registry, store=ActionRequestStore())


def _handled(exc: BaseException, *, write: bool = False):
    return service_error(exc, write=write) or error_response("服务暂时不可用", 500)


@router.post("/api/chat/sessions")
async def create_session(request: Request):
    user, denied = await async_require_user(request)
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


@router.get("/api/chat/sessions/{session_id}/turns/{turn_id}/context")
def context_details(request: Request, session_id: str, turn_id: str):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        result = turn_context(user_db(user), session_id, turn_id)
        if result is None:
            return error_response("该轮暂无上下文记录", 404)
        return json_response(result)
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/chat/memories")
def list_memories(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        return json_response({"items": chat_service.list_memories(user_db=user_db(user))})
    except BaseException as exc:
        return _handled(exc)


@router.delete("/api/chat/memories/{memory_id}")
def delete_memory(request: Request, memory_id: str):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        deleted = chat_service.delete_memory(user_db=user_db(user), memory_id=memory_id)
        if not deleted:
            return error_response("记忆不存在", 404)
        return json_response({"deleted": True})
    except BaseException as exc:
        return _handled(exc, write=True)


@router.get("/api/chat/sessions/{session_id}/actions")
def pending_actions(request: Request, session_id: str):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        db_path = user_db(user)
        if chat_service.get_session(user_db=db_path, session_id=session_id) is None:
            return error_response("会话不存在", 404)
        items = ActionRequestStore().list_pending(user_db=db_path, session_id=session_id)
        return json_response({"items": items})
    except BaseException as exc:
        return _handled(exc)


@router.post("/api/chat/actions/{action_id}/confirm")
async def confirm_action(request: Request, action_id: str):
    user, denied = await async_require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
        if payload:
            raise ValueError("确认请求不应包含工具参数")
        result = await action_service.confirm(user_db=user_db(user), action_id=action_id)
        return json_response(result)
    except asyncio.CancelledError:
        raise
    except BaseException as exc:
        return _handled(exc, write=True)


@router.post("/api/chat/actions/{action_id}/cancel")
async def cancel_action(request: Request, action_id: str):
    user, denied = await async_require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
        if payload:
            raise ValueError("取消请求不应包含工具参数")
        result = await action_service.cancel(user_db=user_db(user), action_id=action_id)
        return json_response(result)
    except BaseException as exc:
        return _handled(exc, write=True)


class _ChatAdmission:
    """Own the session and its provisional charge until the source records the user turn."""

    def __init__(self, db_path: Path, session_id: str):
        self.db_path = db_path
        self.session_id = session_id
        self.day_to_refund: str | None = None
        self.closed = False

    def charge(self, role: str) -> None:
        receipt = consume_chat_quota(self.db_path, role)
        if receipt is not None:
            self.day_to_refund = receipt["day_key"]

    async def acquire_quota(self, role: str) -> None:
        charge = asyncio.create_task(asyncio.to_thread(self.charge, role))
        try:
            await asyncio.shield(charge)
        except asyncio.CancelledError:
            # A cancelled await cannot interrupt SQLite. Finish settlement even
            # under Starlette's cancel scope or a second direct task cancellation.
            with CancelScope(shield=True):
                while not charge.done():
                    with suppress(asyncio.CancelledError, Exception):
                        await asyncio.shield(charge)
            if not charge.cancelled():
                charge.exception()
            raise

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            if self.day_to_refund is not None:
                refund_unstarted_chat(self.db_path, self.day_to_refund)
        finally:
            release_chat_session(self.db_path, self.session_id)

    async def observe(self, source: AsyncGenerator[dict[str, Any], None]) -> AsyncGenerator[dict[str, Any], None]:
        try:
            async for item in source:
                # ChatService yields this directly after inserting the user message,
                # before its first await. HTTP headers and heartbeat frames do not count.
                if item.get("event") == "message.start":
                    self.day_to_refund = None
                yield item
        finally:
            await source.aclose()


class _SessionStreamResponse(StreamingResponse):
    """The response owns the admission even if the connection closes before iteration."""

    def __init__(self, source, request, admission: _ChatAdmission):
        frames = sse_events(admission.observe(source), request=request)
        super().__init__(frames, media_type="text/event-stream", headers={
            "Cache-Control": "no-cache, no-transform", "Connection": "keep-alive", "X-Accel-Buffering": "no",
        })
        self.admission = admission

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                await self.body_iterator.aclose()
            finally:
                self.admission.close()


@router.post("/api/chat/sessions/{session_id}/stream")
async def stream_session(request: Request, session_id: str):
    user, denied = await async_require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request, max_length=MAX_CHAT_BODY_BYTES)
        if set(payload) - {"message", "page_context"} or "message" not in payload:
            raise ValueError("请求参数不正确")
        message = normalize_message(payload.get("message"))
        page_context = PageContext.from_payload(payload.get("page_context"))
        db_path = user_db(user)
        if chat_service.get_session(user_db=db_path, session_id=session_id) is None:
            return error_response("会话不存在", 404)
        # Resolve the runtime before charging: a disabled/unconfigured chat
        # request must not consume a user's daily budget.
        await asyncio.to_thread(chat_service.preflight)
        # Chat has its own atomic daily budget.  It intentionally does not
        # consume the one-click analysis quota; admins can tune the chat
        # budget with AI_CHAT_DAILY_LIMIT without changing analysis limits.
        # Acquire synchronously: cancelling an offloaded acquisition can lose
        # ownership after the thread has obtained the OS lock.
        if not claim_chat_session(db_path, session_id):
            return error_response("该会话正在生成，请先停止当前生成。", 409, error_category="chat_in_progress")
        admission = _ChatAdmission(db_path, session_id)
        try:
            role = str(dict(user).get("role", "user"))
            await admission.acquire_quota(role)
            source = chat_service.stream_reply(
                user_db=db_path, session_id=session_id, message=message, page_context=page_context,
                request_id=str(getattr(request.state, "request_id", "")), session_claimed_by_route=True,
            )
            return _SessionStreamResponse(source, request, admission)
        except BaseException:
            admission.close()
            raise
    except asyncio.CancelledError:
        raise
    except BaseException as exc:
        return _handled(exc, write=True)
