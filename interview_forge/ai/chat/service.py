"""Persistent, cancellation-aware streaming chat service."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import uuid
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import closing
from pathlib import Path
from typing import Any

from interview_forge.ai import ai_coach
from interview_forge.ai.config import AIConfig
from interview_forge.ai.errors import AIServiceError
from interview_forge.ai.provider import stream_chat_chunks
from interview_forge.ai.telemetry import debug_ai_event
from interview_forge.ai.chat.context_builder import ContextBuilder
from interview_forge.core.runtime import server_runtime


MAX_CHAT_MESSAGE_CHARS = 12_000
MAX_CHAT_BODY_BYTES = 20_000
MAX_CHAT_TITLE_CHARS = 64
MAX_SESSION_ID_CHARS = 128
DEFAULT_SESSION_TITLE = "新会话"

_ACTIVE_SESSIONS: set[tuple[str, str]] = set()
_ACTIVE_SESSIONS_LOCK = threading.Lock()
_ACTIVE_MODEL_CALLS = 0
_ACTIVE_MODEL_CALLS_LOCK = threading.Lock()


def _now() -> str:
    return str(server_runtime.now_iso())


def _db_path(value: Path | str) -> Path:
    return Path(value)


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        decoded = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(decoded) if isinstance(decoded, Mapping) else {}


def _session_payload(row: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "title": str(row["title"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _message_payload(row: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "session_id": str(row["session_id"]),
        "role": str(row["role"]),
        "content": str(row["content"]),
        "metadata": _metadata(row["metadata_json"]),
        "created_at": str(row["created_at"]),
    }


def normalize_message(message: Any) -> str:
    if not isinstance(message, str):
        raise ValueError("message 必须是文本")
    value = message.strip()
    if not value:
        raise ValueError("消息不能为空")
    if len(value) > MAX_CHAT_MESSAGE_CHARS:
        raise ValueError(f"消息不能超过 {MAX_CHAT_MESSAGE_CHARS} 个字符")
    return value


def _title_from_message(message: str) -> str:
    compact = " ".join(message.split())
    if len(compact) <= MAX_CHAT_TITLE_CHARS:
        return compact
    return compact[: MAX_CHAT_TITLE_CHARS - 3].rstrip() + "..."


def _event(name: str, data: Mapping[str, Any]) -> dict[str, Any]:
    return {"event": name, "data": dict(data)}


def _safe_provider_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, AIServiceError):
        return str(exc.category), str(exc.user_message)
    try:
        classified = ai_coach._classify_provider_exception(exc)
        return str(classified.category), str(classified.user_message)
    except Exception:
        return "provider_error", "AI 服务暂时不可用，请稍后重试。"


def _usage_payload(usage: Mapping[str, Any], *, estimated_input_tokens: int | None = None) -> dict[str, Any]:
    normalized = {
        key: int(value)
        for key, value in usage.items()
        if key in {"input_tokens", "output_tokens", "reasoning_tokens"}
        and isinstance(value, (int, float))
        and value >= 0
    }
    payload = {"status": "available", "estimated": False, **normalized} if normalized else {
        "status": "unavailable", "estimated": False,
    }
    if estimated_input_tokens is not None and "input_tokens" not in payload:
        payload["estimated_input_tokens"] = int(estimated_input_tokens)
        payload["estimated"] = True
    return payload


def _claim_session(db_path: Path, session_id: str) -> bool:
    key = (str(db_path.resolve()), session_id)
    with _ACTIVE_SESSIONS_LOCK:
        if key in _ACTIVE_SESSIONS:
            return False
        _ACTIVE_SESSIONS.add(key)
    return True


def _release_session(db_path: Path, session_id: str) -> None:
    key = (str(db_path.resolve()), session_id)
    with _ACTIVE_SESSIONS_LOCK:
        _ACTIVE_SESSIONS.discard(key)


def _try_claim_model(config: AIConfig) -> bool:
    global _ACTIVE_MODEL_CALLS
    limit = max(1, int(config.max_concurrent_requests))
    with _ACTIVE_MODEL_CALLS_LOCK:
        if _ACTIVE_MODEL_CALLS >= limit:
            return False
        _ACTIVE_MODEL_CALLS += 1
    return True


def _release_model() -> None:
    global _ACTIVE_MODEL_CALLS
    with _ACTIVE_MODEL_CALLS_LOCK:
        _ACTIVE_MODEL_CALLS = max(0, _ACTIVE_MODEL_CALLS - 1)


class ChatService:
    """Own chat persistence and provider streaming for one authenticated DB."""

    def __init__(
        self,
        *,
        config_loader: Callable[[], AIConfig] | None = None,
        model_factory: Callable[[AIConfig], Any] | None = None,
        stream_factory: Callable[[Any, list[Any]], AsyncIterator[tuple[str, dict[str, int]]]] = stream_chat_chunks,
    ) -> None:
        self.config_loader = config_loader or ai_coach.load_ai_config
        self.model_factory = model_factory or (lambda config: ai_coach._make_chat_model(config))
        self.stream_factory = stream_factory

    @staticmethod
    def create_session(*, user_db: Path | str) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        timestamp = _now()
        with closing(server_runtime.connect(_db_path(user_db))) as connection:
            connection.execute(
                "INSERT INTO chat_sessions(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, DEFAULT_SESSION_TITLE, timestamp, timestamp),
            )
            connection.commit()
        return {"id": session_id, "title": DEFAULT_SESSION_TITLE, "created_at": timestamp, "updated_at": timestamp}

    @staticmethod
    def list_sessions(*, user_db: Path | str) -> list[dict[str, Any]]:
        with closing(server_runtime.connect(_db_path(user_db))) as connection:
            rows = connection.execute(
                "SELECT id, title, created_at, updated_at FROM chat_sessions "
                "ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        return [_session_payload(row) for row in rows]

    @staticmethod
    def get_session(*, user_db: Path | str, session_id: str) -> dict[str, Any] | None:
        if not isinstance(session_id, str) or not session_id or len(session_id) > MAX_SESSION_ID_CHARS:
            return None
        with closing(server_runtime.connect(_db_path(user_db))) as connection:
            row = connection.execute(
                "SELECT id, title, created_at, updated_at FROM chat_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return _session_payload(row) if row is not None else None

    @staticmethod
    def list_messages(*, user_db: Path | str, session_id: str) -> list[dict[str, Any]]:
        with closing(server_runtime.connect(_db_path(user_db))) as connection:
            rows = connection.execute(
                "SELECT id, session_id, role, content, metadata_json, created_at "
                "FROM chat_messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return [_message_payload(row) for row in rows]

    @staticmethod
    def _save_user_message(*, user_db: Path, session_id: str, content: str) -> int:
        timestamp = _now()
        with closing(server_runtime.connect(user_db)) as connection:
            session = connection.execute(
                "SELECT title FROM chat_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if session is None:
                raise LookupError("会话不存在")
            count = int(connection.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE session_id = ?", (session_id,)
            ).fetchone()[0])
            cursor = connection.execute(
                "INSERT INTO chat_messages(session_id, role, content, metadata_json, created_at) "
                "VALUES (?, 'user', ?, '{}', ?)",
                (session_id, content, timestamp),
            )
            title = _title_from_message(content) if count == 0 else str(session["title"])
            connection.execute(
                "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title, timestamp, session_id),
            )
            connection.commit()
            return int(cursor.lastrowid)

    @staticmethod
    def _save_assistant_message(
        *, user_db: Path, session_id: str, content: str, stream_message_id: str, usage: Mapping[str, Any]
    ) -> int:
        timestamp = _now()
        metadata = json.dumps(
            {"stream_message_id": stream_message_id, "usage": dict(usage)},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with closing(server_runtime.connect(user_db)) as connection:
            cursor = connection.execute(
                "INSERT INTO chat_messages(session_id, role, content, metadata_json, created_at) "
                "VALUES (?, 'assistant', ?, ?, ?)",
                (session_id, content, metadata, timestamp),
            )
            connection.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                (timestamp, session_id),
            )
            connection.commit()
            return int(cursor.lastrowid)

    async def stream_reply(
        self, *, user_db: Path | str, session_id: str, message: str
    ) -> AsyncIterator[dict[str, Any]]:
        """Persist the user turn, stream the provider, then persist success only."""
        try:
            clean_message = normalize_message(message)
        except ValueError as exc:
            yield _event("error", {"code": "invalid_message", "message": str(exc)})
            return
        path = _db_path(user_db)
        if not _claim_session(path, session_id):
            yield _event("error", {"code": "chat_in_progress", "message": "该会话正在生成，请先停止当前生成。"})
            return
        provider_stream: AsyncIterator[tuple[str, dict[str, int]]] | None = None
        model_claimed = False
        stream_message_id = uuid.uuid4().hex
        answer_parts: list[str] = []
        usage: dict[str, int] = {}
        try:
            try:
                self._save_user_message(user_db=path, session_id=session_id, content=clean_message)
            except LookupError:
                yield _event("error", {"code": "session_not_found", "message": "会话不存在。"})
                return
            yield _event("message.start", {"message_id": stream_message_id})
            try:
                config = self.config_loader()
                if not config.enabled:
                    raise AIServiceError("disabled", "AI 聊天暂未启用，请稍后重试。")
                if not config.configured:
                    raise AIServiceError("not_configured", "AI 聊天尚未完成配置，请稍后重试。")
                if not _try_claim_model(config):
                    yield _event("error", {"code": "busy", "message": "AI 当前请求较多，请稍后重试。"})
                    return
                model_claimed = True
                context_builder = ContextBuilder()
                messages = await asyncio.to_thread(
                    context_builder.build,
                    user_db=path,
                    session_id=session_id,
                    current_message=clean_message,
                )
                estimated_prompt_tokens = int(context_builder.last_build.get("estimated_prompt_tokens", 0))
                debug_ai_event(
                    "chat_stream_started",
                    session_id=session_id,
                    message_id=stream_message_id,
                    input_tokens_estimated=estimated_prompt_tokens,
                    summary_present=context_builder.last_build.get("summary_present", False),
                )
                model = await asyncio.to_thread(self.model_factory, config)
                provider_stream = self.stream_factory(model, messages)
                async for delta, chunk_usage in provider_stream:
                    if chunk_usage:
                        usage.update(chunk_usage)
                    if not delta:
                        continue
                    answer_parts.append(delta)
                    yield _event("message.delta", {"delta": delta})
                usage_payload = _usage_payload(usage, estimated_input_tokens=estimated_prompt_tokens)
                self._save_assistant_message(
                    user_db=path,
                    session_id=session_id,
                    content="".join(answer_parts),
                    stream_message_id=stream_message_id,
                    usage=usage_payload,
                )
                debug_ai_event(
                    "chat_stream_completed",
                    session_id=session_id,
                    message_id=stream_message_id,
                    usage_status=usage_payload["status"],
                    input_tokens=usage_payload.get("input_tokens"),
                    output_tokens=usage_payload.get("output_tokens"),
                )
                yield _event("message.done", {"message_id": stream_message_id, "usage": usage_payload})
            except asyncio.CancelledError:
                debug_ai_event("chat_stream_cancelled", session_id=session_id, message_id=stream_message_id)
                raise
            except BaseException as exc:
                code, safe_message = _safe_provider_error(exc)
                debug_ai_event("chat_stream_failed", session_id=session_id, message_id=stream_message_id, code=code)
                yield _event("error", {"code": code, "message": safe_message})
        finally:
            if provider_stream is not None:
                close = getattr(provider_stream, "aclose", None)
                if callable(close):
                    try:
                        await close()
                    except Exception:
                        pass
            if model_claimed:
                _release_model()
            _release_session(path, session_id)


__all__ = [
    "ChatService",
    "DEFAULT_SESSION_TITLE",
    "MAX_CHAT_BODY_BYTES",
    "MAX_CHAT_MESSAGE_CHARS",
    "MAX_CHAT_TITLE_CHARS",
    "normalize_message",
]
