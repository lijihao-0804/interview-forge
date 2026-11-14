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
from interview_forge.ai.chat.history_sources import read_source
from interview_forge.ai.chat.page_context import PageContext
from interview_forge.ai.chat.request_ledger import (
    RequestAttempt, check_identity, payload_hash, public_status, read_request, reconcile_owned_session,
    reconcile_session, replay, validate_request_id,
)
from interview_forge.ai.chat.service import (
    MAX_CHAT_BODY_BYTES,
    ChatService,
    claim_chat_session,
    normalize_message,
    release_chat_session,
)
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


@router.get("/api/chat/sessions/{session_id}/messages/{message_id}/excerpt")
def history_excerpt(request: Request, session_id: str, message_id: int, offset: int, length: int, sha256: str):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    excerpt = read_source(user_db(user), session_id, message_id, offset, length, sha256)
    headers = {"Cache-Control": "private, no-store"}
    if excerpt is None:
        return error_response("这段原文已无法核对。", 404, headers=headers)
    return json_response(excerpt, headers=headers)


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
    """Own the lease through any offloaded reservation and response cleanup."""

    def __init__(self, db_path: Path, attempt: RequestAttempt):
        self.db_path = db_path
        self.attempt = attempt
        self.reserved = False
        self.closed = False

    def charge(self, fingerprint: str, role: str) -> None:
        self.attempt.reserve(self.db_path, fingerprint, role)
        self.reserved = True

    async def acquire_quota(self, fingerprint: str, role: str) -> None:
        charge = asyncio.create_task(asyncio.to_thread(self.charge, fingerprint, role))
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
            if self.reserved:
                reconcile_owned_session(self.db_path, self.attempt.session_id, closing_attempt=self.attempt)
        finally:
            release_chat_session(self.db_path, self.attempt.session_id)


class _SessionStreamResponse(StreamingResponse):
    """The response owns the admission even if the connection closes before iteration."""

    def __init__(self, source, request, admission: _ChatAdmission | None = None):
        frames = sse_events(source, request=request)
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
                if self.admission is not None:
                    self.admission.close()


def _prior_response(request: Request, db_path: Path, row, fingerprint: str):
    if row is None:
        return None
    check_identity(row, fingerprint)
    if row["status"] == "completed":
        frames = replay(db_path, row)

        async def source() -> AsyncGenerator[dict[str, Any], None]:
            for frame in frames:
                yield frame

        return _SessionStreamResponse(source(), request)
    if row["status"] == "interrupted":
        return json_response({"error": "回复中断。该轮已记录操作或记忆，可在会话中查看。",
                              **public_status(row)}, 409)
    return None


@router.get("/api/chat/sessions/{session_id}/requests/{client_request_id}")
def request_status(request: Request, session_id: str, client_request_id: str):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        key = validate_request_id(client_request_id)
        db_path = user_db(user)
        row = read_request(db_path, session_id, key)
        if row is None:
            return error_response("请求记录不存在", 404, error_category="chat_request_not_found",
                                  headers={"Cache-Control": "no-store"})
        if row["status"] in {"reserved", "started"}:
            # A live generator owns the OS lease even before the first SSE.
            # Only a reader that acquires that lease may repair the account.
            reconcile_session(db_path, session_id)
            row = read_request(db_path, session_id, key)
        return json_response(public_status(row), headers={"Cache-Control": "no-store"})
    except Exception as exc:
        return _handled(exc)


@router.post("/api/chat/sessions/{session_id}/stream")
async def stream_session(request: Request, session_id: str):
    user, denied = await async_require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request, max_length=MAX_CHAT_BODY_BYTES)
        if set(payload) - {"message", "page_context", "client_request_id"} or "message" not in payload:
            raise ValueError("请求参数不正确")
        message = normalize_message(payload.get("message"))
        page_context = PageContext.from_payload(payload.get("page_context"))
        key = validate_request_id(payload["client_request_id"]) if "client_request_id" in payload else None
        fingerprint = payload_hash(message, page_context.to_dict() if page_context else None)
        db_path = user_db(user)
        if chat_service.get_session(user_db=db_path, session_id=session_id) is None:
            return error_response("会话不存在", 404)
        if key is not None:
            prior = _prior_response(request, db_path, read_request(db_path, session_id, key), fingerprint)
            if prior is not None:
                return prior
        # Acquire synchronously: cancelling an offloaded acquisition can lose
        # ownership after the thread has obtained the OS lock.
        if not claim_chat_session(db_path, session_id):
            return error_response("该会话正在生成，请先停止当前生成。", 409, error_category="chat_in_progress")
        attempt = RequestAttempt.new(session_id, key)
        admission = _ChatAdmission(db_path, attempt)
        try:
            reconcile_owned_session(db_path, session_id)
            if key is not None:
                prior = _prior_response(request, db_path, read_request(db_path, session_id, key), fingerprint)
                if prior is not None:
                    admission.close()
                    return prior
            # Only a genuinely new attempt needs a provider or a quota debit.
            await asyncio.to_thread(chat_service.preflight)
            role = str(dict(user).get("role", "user"))
            await admission.acquire_quota(fingerprint, role)
            source = chat_service.stream_reply(
                user_db=db_path, session_id=session_id, message=message, page_context=page_context,
                request_id=str(getattr(request.state, "request_id", "")), session_claimed_by_route=True,
                attempt=attempt,
            )
            return _SessionStreamResponse(source, request, admission)
        except BaseException:
            admission.close()
            raise
    except asyncio.CancelledError:
        raise
    except BaseException as exc:
        return _handled(exc, write=True)
