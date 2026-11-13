"""Persistent, cancellation-aware streaming chat service."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from interview_forge.ai.config import AIConfig
from interview_forge.ai.errors import AIServiceError
from interview_forge.ai.generation import (
    classify_provider_exception,
    load_ai_config,
    make_chat_model,
)
from interview_forge.ai.resolver import resolve_ai_runtime
from interview_forge.ai.telemetry import debug_ai_event
from interview_forge.ai.chat.context_builder import (
    CONTEXT_BUDGET_POLICY_VERSION,
    ContextBuilder,
)
from interview_forge.ai.chat.context_blocks import ContextBlock
from interview_forge.ai.chat.learning_context import LearningContextProvider, learning_projection_block
from interview_forge.ai.chat.page_context import PageContext, PageContextProvider
from interview_forge.ai.chat.recent_action_context import RecentActionContextProvider
from interview_forge.ai.chat.request_ledger import (
    DEFAULT_SESSION_TITLE,
    RequestAttempt,
    _ACTIVE_SESSIONS as _ACTIVE_SESSIONS,
    _ACTIVE_SESSIONS_LOCK as _ACTIVE_SESSIONS_LOCK,
    claim_chat_session,
    delete_failed_user,
    release_chat_session,
)
from interview_forge.ai.chat.relevance import POLICY_VERSION, page_is_relevant
from interview_forge.ai.chat.tool_orchestrator import ToolOrchestrator
from interview_forge.ai.chat.token_budget import DEFAULT_CHAT_TOKEN_BUDGET, budget_for_context_window
from interview_forge.ai.memory import (
    MemoryContextBuilder,
    MemoryExtractor,
    MemoryPersistenceResult,
    MemoryStore,
    is_explicit_memory_request,
)
from interview_forge.ai.provider import stream_chat_chunks
from interview_forge.ai.memory.extractor import extraction_budget
from interview_forge.ai.token_counting import StructuredRequestBudget, canonical_json, generation_reserve
from interview_forge.ai.tasks import _release_model_slot, _try_claim_model_slot
from interview_forge.core.runtime import server_runtime
from interview_forge.ai.tools.policy import ToolPolicy
from interview_forge.ai.tools.registry import ToolRegistry, build_default_tool_registry
from interview_forge.ai.tools.contracts import LibrarySource, ToolExecutionContext
from interview_forge.observability.ai_trace import TraceRecorder, utc_now_iso


MAX_CHAT_MESSAGE_CHARS = 12_000
MAX_CHAT_BODY_BYTES = 20_000
MAX_CHAT_TITLE_CHARS = 64
MAX_SESSION_ID_CHARS = 128
CHAT_PROMPT_POLICY_VERSION = "chat-prompt-policy-v2"
CONFIG_FINGERPRINT_SCHEMA_VERSION = 2

_FINGERPRINT_CAPABILITY_KEYS = (
    "streaming",
    "tools",
    "structured_output",
    "reasoning",
    "reasoning_modes",
    "reasoning_efforts",
    "reasoning_budget",
    "context_window",
)

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
        classified = classify_provider_exception(exc)
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


def _try_claim_model(config: AIConfig) -> bool:
    return _try_claim_model_slot(config.max_concurrent_requests)


def _release_model() -> None:
    _release_model_slot()


def _runtime_config_fingerprint(
    config: AIConfig,
    runtime: Any,
    *,
    context_budget: Any,
    tool_policy: ToolPolicy,
    tool_schemas: Any,
    system_prompt: str,
    prompt_estimator: Any,
    tool_schema_status: str = "available",
) -> str:
    """Return identity for the versioned, non-sensitive runtime whitelist.

    The payload deliberately has no endpoint URL, credentials, headers,
    cookies, database identity, request text or prepared messages.  A managed
    provider record is represented by its provider id, vendor and capability
    versions.  ENV-only configuration explicitly records that endpoint
    identity is not covered.
    """
    provider_id = getattr(runtime, "provider_id", None)
    provider_id = str(provider_id) if provider_id else None
    vendor = getattr(runtime, "vendor", None)
    canonical_model = getattr(runtime, "canonical_model", None)
    capability_catalog_version = getattr(
        runtime, "capability_catalog_version", None
    )
    reasoning_policy = getattr(runtime, "reasoning_policy", None)
    capabilities = getattr(runtime, "capabilities", {})
    capabilities = capabilities if isinstance(capabilities, Mapping) else {}
    selected_capabilities = {
        key: capabilities.get(key) for key in _FINGERPRINT_CAPABILITY_KEYS
    }
    estimator_name = str(
        getattr(prompt_estimator, "name", type(prompt_estimator).__name__)
    )
    estimator_identity = {
        "name": estimator_name,
        "type": (
            f"{type(prompt_estimator).__module__}."
            f"{type(prompt_estimator).__qualname__}"
        ),
        "version": getattr(prompt_estimator, "version", None),
        "chars_per_token": getattr(prompt_estimator, "chars_per_token", None),
    }
    payload = {
        "schema_version": CONFIG_FINGERPRINT_SCHEMA_VERSION,
        "endpoint_identity": {
            "included": False,
            "binding_coverage": (
                "managed_provider_record"
                if provider_id
                else "env_provider_id_unavailable"
            ),
        },
        "provider_binding": {
            "config_source": str(
                getattr(runtime, "config_source", "env") or "env"
            ),
            "provider_id": provider_id,
            "vendor": str(vendor) if vendor else None,
            "provider_selector": str(config.provider or ""),
            "model": str(config.model or ""),
            "canonical_model": (
                str(canonical_model) if canonical_model else None
            ),
            "wire_api": str(config.wire_api or ""),
            "capability_source": (
                str(getattr(runtime, "capability_source", "unknown"))
            ),
            "capability_profile": (
                str(getattr(runtime, "capability_profile", ""))
            ),
            "capability_catalog_version": (
                str(capability_catalog_version)
                if capability_catalog_version else None
            ),
        },
        "reasoning": {
            "mode": str(
                getattr(reasoning_policy, "mode", config.reasoning_mode) or ""
            ),
            "effort": getattr(
                reasoning_policy, "effort", config.reasoning_effort or None
            ),
            "budget_tokens": getattr(
                reasoning_policy, "budget_tokens", config.reasoning_budget
            ),
            "thinking_enabled": bool(config.thinking_enabled),
            "configured_effort": str(config.reasoning_effort or ""),
            "configured_mode": str(config.reasoning_mode or ""),
            "configured_budget": config.reasoning_budget,
        },
        "model_capabilities": selected_capabilities,
        "prompt_identity": {
            "policy_version": CHAT_PROMPT_POLICY_VERSION,
            "system_prompt_sha256": hashlib.sha256(
                str(system_prompt).encode("utf-8")
            ).hexdigest(),
            "estimator": estimator_identity,
        },
        "policies": {
            "relevance": POLICY_VERSION,
            "context_budget": CONTEXT_BUDGET_POLICY_VERSION,
        },
        "context_budget": asdict(context_budget),
        "tooling": {
            "policy": asdict(tool_policy),
            "schema_status": str(tool_schema_status),
            "schema_sha256": hashlib.sha256(
                canonical_json(tool_schemas).encode("utf-8")
            ).hexdigest(),
        },
    }
    return hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()


class ChatService:
    """Own chat persistence and provider streaming for one authenticated DB."""

    def __init__(
        self,
        *,
        config_loader: Callable[[], AIConfig] | None = None,
        runtime_loader: Callable[[str], Any] | None = None,
        model_factory: Callable[[AIConfig], Any] | None = None,
        stream_factory: Callable[[Any, list[Any]], AsyncIterator[tuple[str, dict[str, int]]]] = stream_chat_chunks,
        tool_registry: ToolRegistry | None = None,
        tool_policy: ToolPolicy | None = None,
        memory_extractor: MemoryExtractor | None = None,
    ) -> None:
        self.config_loader = config_loader or load_ai_config
        self.runtime_loader = runtime_loader if runtime_loader is not None else (None if config_loader is not None else resolve_ai_runtime)
        self.model_factory = model_factory or make_chat_model
        self.stream_factory = stream_factory
        self.tool_registry = (
            build_default_tool_registry()
            if tool_registry is None else tool_registry
        )
        self.tool_policy = tool_policy or ToolPolicy()
        self.memory_extractor = memory_extractor or MemoryExtractor()
        self._background_memory_tasks: set[asyncio.Task[Any]] = set()

    def preflight(self) -> AIConfig:
        """Validate the selected chat runtime before charging the daily quota."""
        runtime = self.runtime_loader("chat") if self.runtime_loader is not None else None
        config = runtime.config if runtime is not None else self.config_loader()
        if not config.enabled:
            raise AIServiceError("disabled", "AI 聊天暂未启用，请稍后重试。")
        if not config.configured:
            raise AIServiceError("not_configured", "AI 聊天尚未完成配置，请稍后重试。")
        return config

    def _schedule_inferred_memory(
        self,
        *,
        user_db: Path,
        session_id: str,
        message_id: int,
        message: str,
        model: Any,
        trace_recorder: TraceRecorder | None = None,
        fallback_budget: StructuredRequestBudget | None = None,
    ) -> None:
        task = asyncio.create_task(asyncio.to_thread(
            self._process_memory,
            user_db=user_db,
            session_id=session_id,
            message_id=message_id,
            message=message,
            model=model,
            trace_recorder=trace_recorder,
            fallback_budget=fallback_budget,
        ))
        self._background_memory_tasks.add(task)
        task.add_done_callback(self._background_memory_tasks.discard)

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
    def list_memories(*, user_db: Path | str) -> list[dict[str, Any]]:
        return [item.api_payload() for item in MemoryStore().list_active(user_db=user_db)]

    @staticmethod
    def delete_memory(*, user_db: Path | str, memory_id: str) -> bool:
        return MemoryStore().delete(user_db=user_db, memory_id=memory_id)

    def _process_memory(
        self,
        *,
        user_db: Path,
        session_id: str,
        message_id: int,
        message: str,
        model: Any,
        trace_recorder: TraceRecorder | None = None,
        fallback_budget: StructuredRequestBudget | None = None,
    ) -> None:
        if not MemoryExtractor.can_extract(message):
            return
        try:
            memory_model = model
            budget = fallback_budget
            if self.runtime_loader is not None:
                try:
                    memory_runtime = self.runtime_loader("memory_extraction")
                    memory_model = self.model_factory(memory_runtime.config)
                    budget = extraction_budget(runtime=memory_runtime)
                except Exception as exc:
                    debug_ai_event("chat_memory_runtime_unavailable", error_type=type(exc).__name__)
                    if trace_recorder is not None:
                        trace_recorder.record(
                            event_type="memory",
                            name="memory_runtime_fallback",
                            status="fallback",
                            metadata={
                                "requested_business": "memory_extraction",
                                "fallback": True,
                                "fallback_reason": type(exc).__name__,
                                "fallback_provider": trace_recorder.provider,
                                "fallback_model": trace_recorder.model,
                            },
                        )
            candidates = self._extract_memory(message, model=memory_model, budget=budget)
            store = MemoryStore()
            for candidate in candidates:
                store.save_candidate(
                    user_db=user_db,
                    candidate=candidate,
                    source_session_id=session_id,
                    source_message_id=message_id,
                )
        except Exception as exc:  # memory is a non-critical enhancement
            debug_ai_event(
                "chat_memory_failed",
                error_type=type(exc).__name__,
                explicit_hint="记住" in message or "忘记" in message,
            )

    def _extract_memory(
        self, message: str, *, model: Any, budget: StructuredRequestBudget | None,
    ):
        if isinstance(self.memory_extractor, MemoryExtractor):
            return self.memory_extractor.extract(message, model=model, budget=budget)
        # Injected legacy extractors expose only the message/model protocol.
        return self.memory_extractor.extract(message, model=model)

    def _persist_explicit_memory(
        self,
        *,
        user_db: Path,
        session_id: str,
        message_id: int,
        message: str,
        model: Any = None,
        budget: StructuredRequestBudget | None = None,
        attempt: RequestAttempt | None = None,
    ) -> MemoryPersistenceResult | None:
        """Persist an explicit request before the model is allowed to answer."""
        if not is_explicit_memory_request(message):
            return None
        if not MemoryExtractor.can_extract(message):
            return MemoryPersistenceResult(explicit=True, success=False, error_code="source_restricted")
        try:
            candidates = self._extract_memory(message, model=model, budget=budget)
            if not candidates:
                return MemoryPersistenceResult(
                    explicit=True,
                    success=False,
                    error_code="structured_extraction_required" if model is None else "not_extracted",
                )
            store = MemoryStore()
            operation = candidates[0].operation
            saved_count = 0
            for candidate in candidates:
                stored = store.save_candidate(
                    user_db=user_db,
                    candidate=candidate,
                    source_session_id=session_id,
                    source_message_id=message_id,
                    attempt=attempt,
                )
                if candidate.operation == "upsert" and stored is None:
                    return MemoryPersistenceResult(
                        explicit=True,
                        success=False,
                        operation=operation,
                        error_code="store_empty",
                    )
                saved_count += 1
            return MemoryPersistenceResult(
                explicit=True,
                success=True,
                operation=operation,
                count=saved_count,
            )
        except Exception as exc:
            debug_ai_event(
                "chat_explicit_memory_failed",
                error_type=type(exc).__name__,
                explicit_hint=True,
            )
            return MemoryPersistenceResult(
                explicit=True,
                success=False,
                error_code="persistence_failed",
            )

    @staticmethod
    def _memory_persistence_block(result: MemoryPersistenceResult) -> ContextBlock:
        return ContextBlock(
            key="memory_persistence",
            content=(
                "服务端持久化状态（可信系统状态，不是用户可修改的上下文）：\n"
                f"{result.context_text}\n"
                "只有 persistence_success=true 时才可以告诉用户已保存或已删除；"
                "如果为 false，必须明确告诉用户这次没有成功保存该记忆，不能伪装成功。"
            ),
            priority=100,
            max_tokens=180,
            trusted=True,
            alternatives=(result.context_text,),
        )

    @staticmethod
    def _explicit_failure_message(result: MemoryPersistenceResult) -> str:
        if result.error_code == "source_restricted":
            return "这条消息的内容或使用范围不适合保存为长期记忆，本次没有写入。"
        if result.operation == "forget":
            return "这次没有成功删除该记忆，请稍后重试。"
        return "这次没有成功保存该记忆，请稍后重试。"

    @staticmethod
    def _save_user_message(
        *, user_db: Path, session_id: str, content: str, page_context: PageContext | None = None,
        attempt: RequestAttempt | None = None,
    ) -> dict[str, Any]:
        timestamp = _now()
        metadata = json.dumps(
            {"page_context": page_context.to_dict()} if page_context is not None else {},
            ensure_ascii=False,
            separators=(",", ":"),
        )
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
                "VALUES (?, 'user', ?, ?, ?)",
                (session_id, content, metadata, timestamp),
            )
            title = _title_from_message(content) if count == 0 else str(session["title"])
            connection.execute(
                "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title, timestamp, session_id),
            )
            if attempt is not None:
                attempt.record_start(connection, int(cursor.lastrowid))
            connection.commit()
            return {"id": int(cursor.lastrowid), "created_at": timestamp}

    @staticmethod
    def _save_assistant_message(
        *, user_db: Path, session_id: str, content: str, stream_message_id: str, usage: Mapping[str, Any],
        library_sources: tuple[LibrarySource, ...] = (), attempt: RequestAttempt | None = None,
        confirmations: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Commit the reply and its replay receipt before emitting message.done."""
        done = {"message_id": stream_message_id, "usage": dict(usage)}
        metadata = {"stream_message_id": stream_message_id, "usage": dict(usage)}
        assistant_id = None
        with closing(server_runtime.connect(user_db)) as connection:
            if content.strip():
                timestamp = _now()
                done["created_at"] = timestamp
                if library_sources:
                    done["library_sources"] = metadata["library_sources"] = list(library_sources)
                cursor = connection.execute(
                    "INSERT INTO chat_messages(session_id, role, content, metadata_json, created_at) "
                    "VALUES (?, 'assistant', ?, ?, ?)",
                    (session_id, content.strip(), json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), timestamp),
                )
                assistant_id = int(cursor.lastrowid)
                connection.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (timestamp, session_id))
            if attempt is not None:
                attempt.complete(connection, assistant_id, done, confirmations or [], content)
            connection.commit()
        return done

    async def stream_reply(
        self,
        *,
        user_db: Path | str,
        session_id: str,
        message: str,
        page_context: PageContext | Mapping[str, Any] | None = None,
        request_id: str = "",
        session_claimed_by_route: bool = False,
        attempt: RequestAttempt | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Persist the user turn, stream the provider, then persist success only."""
        try:
            clean_message = normalize_message(message)
            normalized_page_context = (
                page_context
                if isinstance(page_context, PageContext)
                else PageContext.from_payload(page_context)
            )
        except ValueError as exc:
            yield _event("error", {"code": "invalid_message", "message": str(exc)})
            return
        path = _db_path(user_db)
        if not session_claimed_by_route and not claim_chat_session(path, session_id):
            yield _event("error", {"code": "chat_in_progress", "message": "该会话正在生成，请先停止当前生成。"})
            return
        model_claimed = False
        claims_released = False
        current_message_id: int | None = None
        user_created_at: str | None = None
        assistant_saved = False
        durable_turn_state = False
        stream_message_id = attempt.turn_id if attempt is not None else uuid.uuid4().hex
        answer_parts: list[str] = []
        confirmations: list[dict] = []
        usage: dict[str, int] = {}
        ttft_ms: float | None = None
        trace_recorder: TraceRecorder | None = None
        turn_started = time.perf_counter()
        turn_started_at = utc_now_iso()

        async def record_chat_trace(
            *, status: str, usage: Mapping[str, Any], error_code: str | None = None,
        ) -> None:
            """Persist telemetry off the event loop and never affect Chat."""
            if trace_recorder is None:
                return
            try:
                await asyncio.to_thread(
                    trace_recorder.record_chat,
                    status=status,
                    duration_ms=(time.perf_counter() - turn_started) * 1000,
                    usage=dict(usage),
                    error_code=error_code,
                    started_at=turn_started_at,
                    finished_at=utc_now_iso(),
                    ttft_ms=ttft_ms,
                )
            except Exception:
                # Telemetry must remain best-effort, including on a slow or
                # temporarily locked per-user SQLite database.
                return

        def release_claims() -> None:
            nonlocal model_claimed, claims_released
            if claims_released:
                return
            if model_claimed:
                _release_model()
                model_claimed = False
            if not session_claimed_by_route:
                release_chat_session(path, session_id)
            claims_released = True

        try:
            try:
                saved_user = self._save_user_message(
                    user_db=path,
                    session_id=session_id,
                    content=clean_message,
                    page_context=normalized_page_context,
                    attempt=attempt,
                )
                current_message_id = int(saved_user["id"])
                user_created_at = str(saved_user["created_at"])
            except LookupError:
                yield _event("error", {"code": "session_not_found", "message": "会话不存在。"})
                return
            start_payload = {"message_id": stream_message_id}
            if user_created_at:
                start_payload["created_at"] = user_created_at
            yield _event("message.start", start_payload)
            try:
                runtime = self.runtime_loader("chat") if self.runtime_loader is not None else None
                config = runtime.config if runtime is not None else self.config_loader()
                if not config.enabled:
                    raise AIServiceError("disabled", "AI 聊天暂未启用，请稍后重试。")
                if not config.configured:
                    raise AIServiceError("not_configured", "AI 聊天尚未完成配置，请稍后重试。")
                trace_recorder = TraceRecorder(
                    user_db=path,
                    trace_id=stream_message_id,
                    session_id=session_id,
                    request_id=request_id,
                    provider=config.provider,
                    model=config.model,
                    provider_id=getattr(runtime, "provider_id", None) if runtime is not None else None,
                    provider_name=getattr(runtime, "provider_name", "") if runtime is not None else "",
                    business_key="chat",
                    reasoning_mode=getattr(getattr(runtime, "reasoning_policy", None), "mode", "") if runtime is not None else "",
                    reasoning_effort=getattr(getattr(runtime, "reasoning_policy", None), "effort", None) if runtime is not None else None,
                    config_source=getattr(runtime, "config_source", "env") if runtime is not None else "env",
                )
                if not _try_claim_model(config):
                    yield _event("error", {"code": "busy", "message": "AI 当前请求较多，请稍后重试。"})
                    return
                model_claimed = True
                model = None
                explicit_result = await asyncio.to_thread(
                    self._persist_explicit_memory,
                    user_db=path,
                    session_id=session_id,
                    message_id=current_message_id,
                    message=clean_message,
                    model=None,
                    attempt=attempt,
                )
                if explicit_result is not None and explicit_result.error_code == "structured_extraction_required":
                    try:
                        extraction_runtime = runtime
                        if self.runtime_loader is not None:
                            extraction_runtime = await asyncio.to_thread(self.runtime_loader, "memory_extraction")
                        extraction_config = extraction_runtime.config if extraction_runtime is not None else config
                        extraction_model = await asyncio.to_thread(self.model_factory, extraction_config)
                        explicit_result = await asyncio.to_thread(
                            self._persist_explicit_memory,
                            user_db=path,
                            session_id=session_id,
                            message_id=current_message_id,
                            message=clean_message,
                            model=extraction_model,
                            budget=extraction_budget(runtime=extraction_runtime, config=extraction_config),
                            attempt=attempt,
                        )
                    except Exception:
                        explicit_result = MemoryPersistenceResult(
                            explicit=True,
                            success=False,
                            error_code="model_unavailable",
                        )
                if explicit_result is not None and explicit_result.success:
                    # The memory row is durable even if the later model turn
                    # fails, so its source user message must not be rolled back.
                    durable_turn_state = True
                if model is None and (explicit_result is None or explicit_result.success):
                    model = await asyncio.to_thread(self.model_factory, config)
                learning_context = await asyncio.to_thread(
                    LearningContextProvider().build,
                    user_db=path,
                    query=clean_message,
                )
                context_blocks: list[ContextBlock] = []
                if explicit_result is not None:
                    context_blocks.append(self._memory_persistence_block(explicit_result))
                memory_block = await asyncio.to_thread(
                    MemoryContextBuilder().build,
                    user_db=path,
                    query=clean_message,
                )
                if memory_block is not None:
                    context_blocks.append(memory_block)
                recent_action_block = await asyncio.to_thread(
                    RecentActionContextProvider().build,
                    user_db=path,
                    session_id=session_id,
                )
                if recent_action_block is not None:
                    context_blocks.append(recent_action_block)
                page_context_block = (
                    PageContextProvider().build(normalized_page_context)
                    if page_is_relevant(clean_message, normalized_page_context) else None
                )
                if page_context_block is not None:
                    context_blocks.append(page_context_block)
                learning_task = None
                if learning_context:
                    learning_task = learning_context.get("task")
                    projection = learning_context.get("projection")
                    context_blocks.append(learning_projection_block(projection))
                model_context_window = (
                    (getattr(runtime, "capabilities", {}) or {}).get("context_window")
                    if runtime is not None else None
                )
                reserve = generation_reserve(config, DEFAULT_CHAT_TOKEN_BUDGET.output_tokens)
                context_budget = budget_for_context_window(
                    model_context_window, replace(DEFAULT_CHAT_TOKEN_BUDGET, output_tokens=reserve),
                )
                try:
                    tool_schemas = self.tool_registry.model_schemas()
                    tool_schema_status = "available"
                except Exception:
                    # Orchestration already owns the no-tools fallback. Identity
                    # construction must not turn a schema issue into a new chat
                    # failure before that boundary is reached.
                    tool_schemas = []
                    tool_schema_status = "unavailable"
                context_builder = ContextBuilder(
                    budget=context_budget, context_blocks=context_blocks,
                    current_page_path=normalized_page_context.path
                    if normalized_page_context is not None and page_context_block is not None else None,
                )
                config_fingerprint = _runtime_config_fingerprint(
                    config,
                    runtime,
                    context_budget=context_budget,
                    tool_policy=self.tool_policy,
                    tool_schemas=tool_schemas,
                    system_prompt=context_builder.system_prompt,
                    prompt_estimator=context_builder.estimator,
                    tool_schema_status=tool_schema_status,
                )
                messages = await asyncio.to_thread(
                    context_builder.build,
                    user_db=path,
                    session_id=session_id,
                    current_message=clean_message,
                    current_message_id=current_message_id,
                )
                estimated_prompt_tokens = int(context_builder.last_build.get("estimated_prompt_tokens", 0))
                debug_ai_event(
                    "chat_stream_started",
                    session_id=session_id,
                    message_id=stream_message_id,
                    input_tokens_estimated=estimated_prompt_tokens,
                    summary_present=context_builder.last_build.get("summary_present", False),
                    learning_task=learning_task,
                    relevance_policy=context_builder.last_build.get("relevance_policy"),
                    history_mode=context_builder.last_build.get("history_mode"),
                    history_reason=context_builder.last_build.get("history_reason"),
                    history_selected_count=context_builder.last_build.get("history_selected_count"),
                    history_omitted_count=context_builder.last_build.get("history_omitted_count"),
                    context_blocks=context_builder.last_build.get("context_blocks"),
                    context_blocks_irrelevant=context_builder.last_build.get("context_blocks_irrelevant"),
                    prepared_context_hash=context_builder.last_build.get("prepared_context_hash"),
                    config_fingerprint=config_fingerprint,
                    context_budget_policy_version=context_builder.last_build.get(
                        "context_budget_policy_version"
                    ),
                    context_window=model_context_window,
                    reserved_output_tokens=context_budget.output_tokens,
                    endpoint_identity_included=False,
                    provider_binding_source=(
                        "managed_provider_record"
                        if getattr(runtime, "provider_id", None)
                        else "env_provider_id_unavailable"
                    ),
                )
                if trace_recorder is not None:
                    # Only selection metadata passes the recorder allowlist;
                    # no message, summary, memory or page text is persisted.
                    await asyncio.to_thread(
                        trace_recorder.record,
                        event_type="context", name="context_selection", status="success",
                        metadata={
                            **context_builder.last_build,
                            "config_fingerprint": config_fingerprint,
                            "context_window": model_context_window,
                            "reserved_output_tokens": context_budget.output_tokens,
                            "page_context_omitted": normalized_page_context is not None and page_context_block is None,
                        },
                    )
                if explicit_result is not None and not explicit_result.success:
                    answer = self._explicit_failure_message(explicit_result)
                    answer_parts.append(answer)
                    yield _event("message.delta", {"delta": answer})
                    usage_payload = _usage_payload({}, estimated_input_tokens=estimated_prompt_tokens)
                    usage_payload.update({
                        "tool_calls_count": 0,
                        "tool_names": [],
                        "tool_run_ids": [],
                        "tooling_unavailable": False,
                    })
                    done_payload = self._save_assistant_message(
                        user_db=path,
                        session_id=session_id,
                        content=answer,
                        stream_message_id=stream_message_id,
                        usage=usage_payload,
                        attempt=attempt,
                    )
                    assistant_saved = True
                    await record_chat_trace(
                        status="failed", usage=usage_payload,
                        error_code=explicit_result.error_code,
                    )
                    release_claims()
                    yield _event("message.done", done_payload)
                    return
                tool_context = ToolExecutionContext(
                    user_db=path,
                    session_id=session_id,
                    turn_id=stream_message_id,
                    user_message_id=current_message_id,
                    current_query=clean_message,
                    artifacts={
                        "learning_context": learning_context,
                        "username": path.parent.name,
                        "model_context_window": model_context_window,
                        "reserved_output_tokens": context_budget.output_tokens,
                        "chat_request_attempt": attempt,
                    },
                )
                orchestrator = ToolOrchestrator(
                    registry=self.tool_registry,
                    policy=self.tool_policy,
                    trace_recorder=trace_recorder,
                )
                async for item in orchestrator.stream(
                    model=model,
                    messages=messages,
                    context=tool_context,
                    fallback_stream_factory=self.stream_factory,
                ):
                    if item.get("event") == "message.delta":
                        delta = str(item.get("data", {}).get("delta", ""))
                        if delta:
                            if ttft_ms is None:
                                ttft_ms = (time.perf_counter() - turn_started) * 1000
                            answer_parts.append(delta)
                    elif item.get("event") == "tool.confirmation_required":
                        # A pending ACTION references this user turn.  Keep
                        # the source message if a later model round fails.
                        durable_turn_state = True
                        confirmations.append(item)
                    yield item
                turn_result = orchestrator.last_result
                usage.update(turn_result.usage)
                usage_payload = _usage_payload(usage, estimated_input_tokens=estimated_prompt_tokens)
                usage_payload.update({
                    "tool_calls_count": turn_result.tool_calls_count,
                    "tool_names": list(turn_result.tool_names),
                    "tool_run_ids": list(turn_result.tool_run_ids),
                    "tooling_unavailable": turn_result.tooling_unavailable,
                })
                answer = "".join(answer_parts)
                if not answer.strip() and not turn_result.has_pending_confirmation:
                    await record_chat_trace(
                        status="failed", usage=usage_payload,
                        error_code="empty_response",
                    )
                    yield _event(
                        "error",
                        {
                            "code": "empty_response",
                            "message": "AI 没有返回有效内容，请重试。",
                        },
                    )
                    return
                done_payload = self._save_assistant_message(
                    user_db=path, session_id=session_id, content=answer, stream_message_id=stream_message_id,
                    usage=usage_payload, library_sources=turn_result.library_sources,
                    attempt=attempt, confirmations=confirmations,
                )
                assistant_saved = bool(answer.strip())
                debug_ai_event(
                    "chat_stream_completed",
                    session_id=session_id,
                    message_id=stream_message_id,
                    usage_status=usage_payload["status"],
                    input_tokens=usage_payload.get("input_tokens"),
                    output_tokens=usage_payload.get("output_tokens"),
                )
                await record_chat_trace(status="success", usage=usage_payload)
                release_claims()
                if explicit_result is None:
                    self._schedule_inferred_memory(
                        user_db=path,
                        session_id=session_id,
                        message_id=current_message_id,
                        message=clean_message,
                        model=model,
                        trace_recorder=trace_recorder,
                        fallback_budget=extraction_budget(runtime=runtime, config=config),
                    )
                yield _event("message.done", done_payload)
            except asyncio.CancelledError:
                debug_ai_event("chat_stream_cancelled", session_id=session_id, message_id=stream_message_id)
                raise
            except GeneratorExit:
                raise
            except Exception as exc:
                code, safe_message = _safe_provider_error(exc)
                debug_ai_event("chat_stream_failed", session_id=session_id, message_id=stream_message_id, code=code)
                if trace_recorder is not None:
                    await record_chat_trace(status="failed", usage=usage, error_code=code)
                yield _event("error", {"code": code, "message": safe_message})
        finally:
            if attempt is None and current_message_id is not None and not assistant_saved and not durable_turn_state:
                try:
                    with closing(server_runtime.connect(path)) as conn:
                        delete_failed_user(conn, session_id, current_message_id)
                        conn.commit()
                except Exception as exc:
                    debug_ai_event(
                        "chat_failed_user_cleanup_error",
                        error_type=type(exc).__name__,
                    )
            release_claims()


__all__ = [
    "ChatService",
    "DEFAULT_SESSION_TITLE",
    "MAX_CHAT_BODY_BYTES",
    "MAX_CHAT_MESSAGE_CHARS",
    "MAX_CHAT_TITLE_CHARS",
    "normalize_message",
]
