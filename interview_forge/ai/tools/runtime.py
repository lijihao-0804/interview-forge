"""The single server-owned execution boundary for all assistant tools."""
from __future__ import annotations

import asyncio
import inspect
import json
import math
import sqlite3
import time
import uuid
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from interview_forge.ai.telemetry import debug_ai_event
from interview_forge.ai.tools.contracts import (
    ToolExecutionContext,
    ToolExecutionResult,
    ToolKind,
    ToolResult,
)
from interview_forge.ai.tools.langchain_adapter import NormalizedToolCall
from interview_forge.ai.tools.registry import ToolRegistry
from interview_forge.core.runtime import server_runtime


_ERROR_MESSAGES = {
    "unknown_tool": "该工具不可用。",
    "invalid_arguments": "工具参数不符合要求。",
    "confirmation_required": "该操作需要用户确认。",
    "timeout": "工具响应超时。",
    "tool_error": "工具暂时不可用。",
    "result_too_large": "工具返回结果过大。",
    "cancelled": "工具调用已取消。",
}


def _now() -> str:
    return str(server_runtime.now_iso())


def _estimate_tokens(value: str) -> int:
    return max(1, math.ceil(len(value) / 3)) if value else 0


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


class ToolRuntime:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    @staticmethod
    def _validated_args(spec: Any, raw: Any) -> tuple[BaseModel, dict[str, Any]]:
        if not isinstance(raw, Mapping):
            raise ValueError("arguments must be an object")
        fields = getattr(spec.args_model, "model_fields", {})
        unknown = set(raw) - set(fields)
        if unknown:
            raise ValueError("unknown arguments")
        parsed = spec.args_model.model_validate(dict(raw))
        dumped = parsed.model_dump(mode="json", exclude_none=True)
        return parsed, dict(dumped)

    async def _invoke(self, spec: Any, context: ToolExecutionContext, args: BaseModel) -> Any:
        handler = spec.handler
        if inspect.iscoroutinefunction(handler):
            return await handler(context, args)
        result = await asyncio.to_thread(handler, context, args)
        if inspect.isawaitable(result):
            return await result
        return result

    def _audit(
        self,
        *,
        context: ToolExecutionContext,
        run_id: str,
        call: NormalizedToolCall,
        kind: ToolKind,
        arguments: Mapping[str, Any],
        status: str,
        duration_ms: int,
        error_code: str | None = None,
        cache_hit: bool = False,
        result_chars: int = 0,
        result_tokens_estimated: int = 0,
    ) -> None:
        metadata = {
            "cache_hit": bool(cache_hit),
            "result_chars": int(result_chars),
            "result_tokens_estimated": int(result_tokens_estimated),
        }
        try:
            with closing(server_runtime.connect(Path(context.user_db))) as connection:
                connection.execute(
                    """INSERT INTO chat_tool_runs(
                        id, session_id, turn_id, user_message_id, tool_name,
                        tool_kind, arguments_json, status, duration_ms, error_code,
                        result_meta_json, created_at, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run_id,
                        context.session_id,
                        context.turn_id,
                        context.user_message_id,
                        call.name,
                        kind.value,
                        _safe_json(dict(arguments)),
                        status,
                        duration_ms,
                        error_code,
                        _safe_json(metadata),
                        _now(),
                        _now(),
                    ),
                )
                connection.commit()
        except (OSError, sqlite3.Error, TypeError, ValueError):
            # Tool execution must not fail because optional audit persistence
            # is temporarily unavailable.
            return

    def _failure(
        self,
        *,
        context: ToolExecutionContext,
        call: NormalizedToolCall,
        kind: ToolKind,
        run_id: str,
        status: str,
        code: str,
        started: float,
        arguments: Mapping[str, Any] = (),
    ) -> ToolExecutionResult:
        duration_ms = round((time.perf_counter() - started) * 1000)
        self._audit(
            context=context,
            run_id=run_id,
            call=call,
            kind=kind,
            arguments=dict(arguments) if isinstance(arguments, Mapping) else {},
            status=status,
            duration_ms=duration_ms,
            error_code=code,
        )
        return ToolExecutionResult(
            tool_name=call.name,
            call_id=call.call_id,
            status=status,
            error_code=code,
            error_message=_ERROR_MESSAGES.get(code, _ERROR_MESSAGES["tool_error"]),
            run_id=run_id,
            duration_ms=duration_ms,
            arguments=dict(arguments) if isinstance(arguments, Mapping) else {},
        )

    async def execute(
        self,
        *,
        call: NormalizedToolCall,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        started = time.perf_counter()
        run_id = uuid.uuid4().hex
        spec = self.registry.get(call.name)
        if spec is None:
            return self._failure(
                context=context, call=call, kind=ToolKind.READ, run_id=run_id,
                status="error", code="unknown_tool", started=started,
            )
        try:
            args_model, arguments = self._validated_args(spec, call.arguments)
        except (ValidationError, TypeError, ValueError, AttributeError):
            return self._failure(
                context=context, call=call, kind=spec.kind, run_id=run_id,
                status="error", code="invalid_arguments", started=started,
            )

        canonical_args = _safe_json(arguments)
        cache_key = f"{spec.name}:{canonical_args}"
        if spec.kind == ToolKind.READ and cache_key in context.cache:
            result = context.cache[cache_key]
            duration_ms = round((time.perf_counter() - started) * 1000)
            self._audit(
                context=context, run_id=run_id, call=call, kind=spec.kind,
                arguments=arguments, status="cache_hit", duration_ms=duration_ms,
                cache_hit=True,
                result_chars=len(_safe_json(result.data)),
                result_tokens_estimated=_estimate_tokens(_safe_json(result.data)),
            )
            return ToolExecutionResult(
                tool_name=call.name, call_id=call.call_id, status="cache_hit",
                result=result, cache_hit=True, run_id=run_id,
                duration_ms=duration_ms, arguments=arguments,
            )

        if spec.kind == ToolKind.ACTION or spec.requires_confirmation:
            return self._failure(
                context=context, call=call, kind=spec.kind, run_id=run_id,
                status="confirmation_required", code="confirmation_required",
                started=started, arguments=arguments,
            )

        try:
            raw_result = await asyncio.wait_for(
                self._invoke(spec, context, args_model), timeout=spec.timeout_seconds
            )
            result = raw_result if isinstance(raw_result, ToolResult) else ToolResult(dict(raw_result))
            serialized = _safe_json(result.data)
            result_tokens = _estimate_tokens(serialized)
            if result_tokens > spec.max_result_tokens:
                return self._failure(
                    context=context, call=call, kind=spec.kind, run_id=run_id,
                    status="error", code="result_too_large", started=started,
                    arguments=arguments,
                )
        except asyncio.TimeoutError:
            return self._failure(
                context=context, call=call, kind=spec.kind, run_id=run_id,
                status="timeout", code="timeout", started=started,
                arguments=arguments,
            )
        except asyncio.CancelledError:
            result = self._failure(
                context=context, call=call, kind=spec.kind, run_id=run_id,
                status="cancelled", code="cancelled", started=started,
                arguments=arguments,
            )
            raise
        except Exception:
            return self._failure(
                context=context, call=call, kind=spec.kind, run_id=run_id,
                status="error", code="tool_error", started=started,
                arguments=arguments,
            )

        if spec.kind == ToolKind.READ:
            context.cache[cache_key] = result
        duration_ms = round((time.perf_counter() - started) * 1000)
        self._audit(
            context=context, run_id=run_id, call=call, kind=spec.kind,
            arguments=arguments, status="success", duration_ms=duration_ms,
            result_chars=len(serialized), result_tokens_estimated=result_tokens,
        )
        debug_ai_event(
            "chat_tool_completed", tool_name=call.name, tool_kind=spec.kind.value,
            status="success", duration_ms=duration_ms, cache_hit=False,
            result_chars=len(serialized), result_tokens_estimated=result_tokens,
        )
        return ToolExecutionResult(
            tool_name=call.name, call_id=call.call_id, status="ok", result=result,
            run_id=run_id, duration_ms=duration_ms, arguments=arguments,
        )


__all__ = ["ToolRuntime"]
