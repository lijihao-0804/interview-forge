"""Streaming model ↔ read-only tool orchestration for one chat turn."""
from __future__ import annotations

import asyncio
import inspect
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from interview_forge.ai.provider import _usage_from
from interview_forge.ai.telemetry import debug_ai_event
from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolExecutionResult, ToolKind
from interview_forge.ai.tools.langchain_adapter import (
    NormalizedToolCall,
    ToolCallAccumulator,
    ToolingUnavailableError,
    bind_tools,
    visible_text,
)
from interview_forge.ai.tools.policy import ToolPolicy
from interview_forge.ai.tools.registry import ToolRegistry, build_default_tool_registry
from interview_forge.ai.tools.runtime import ToolRuntime


TOOLING_UNAVAILABLE_NOTICE = (
    "当前工具能力不可用。需要实时或用户特定数据时，请明确说明无法获取，"
    "不得自行猜测，也不要伪造工具结果。"
)
TOOLS_DISABLED_NOTICE = (
    "工具调用上限已达到。不要再请求工具；仅根据已有上下文与已经返回的工具结果回答，"
    "明确说明无法确认的信息。"
)


@dataclass(frozen=True)
class ToolTurnResult:
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls_count: int = 0
    tool_names: tuple[str, ...] = ()
    tool_run_ids: tuple[str, ...] = ()
    tooling_unavailable: bool = False


@dataclass(frozen=True)
class _RoundResult:
    text: str
    calls: tuple[NormalizedToolCall, ...]
    usage: dict[str, int]


def _event(name: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"event": name, "data": data}


def _merge_usage(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        if isinstance(value, (int, float)) and value >= 0:
            target[key] = int(value)


def _tool_call_message(text: str, calls: list[NormalizedToolCall]) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = [
            {"id": call.call_id, "name": call.name, "args": call.arguments}
            for call in calls
        ]
    return message


class ToolOrchestrator:
    """Own all model/tool rounds while keeping ChatService provider-agnostic."""

    def __init__(
        self,
        *,
        registry: ToolRegistry | None = None,
        policy: ToolPolicy | None = None,
    ) -> None:
        self.registry = registry or build_default_tool_registry()
        self.policy = policy or ToolPolicy()
        self.runtime = ToolRuntime(self.registry)
        self.last_result = ToolTurnResult()
        self._round_result = _RoundResult("", (), {})
        self._call_results: list[ToolExecutionResult] = []

    async def _stream_round(self, model: Any, messages: list[Any]):
        text_parts: list[str] = []
        accumulator = ToolCallAccumulator()
        round_usage: dict[str, int] = {}
        iterator: Any = None
        try:
            astream = getattr(model, "astream", None)
            if callable(astream):
                iterator = astream(messages)
                if inspect.isawaitable(iterator):
                    iterator = await iterator
                async for chunk in iterator:
                    text = visible_text(chunk)
                    if text:
                        text_parts.append(text)
                        yield _event("message.delta", {"delta": text})
                    accumulator.add(chunk)
                    _merge_usage(round_usage, _usage_from(chunk))
            else:
                stream = getattr(model, "stream", None)
                if not callable(stream):
                    raise TypeError("chat model does not support streaming")
                iterator = iter(stream(messages))
                sentinel = object()

                def next_chunk() -> Any:
                    try:
                        return next(iterator)
                    except StopIteration:
                        return sentinel

                while True:
                    chunk = await asyncio.to_thread(next_chunk)
                    if chunk is sentinel:
                        break
                    text = visible_text(chunk)
                    if text:
                        text_parts.append(text)
                        yield _event("message.delta", {"delta": text})
                    accumulator.add(chunk)
                    _merge_usage(round_usage, _usage_from(chunk))
        finally:
            close = getattr(iterator, "aclose", None)
            if callable(close):
                await close()
            else:
                close = getattr(iterator, "close", None)
                if callable(close):
                    await asyncio.to_thread(close)
            self._round_result = _RoundResult(
                "".join(text_parts), tuple(accumulator.finish()), round_usage
            )

    async def _execute_calls(
        self,
        *,
        calls: list[NormalizedToolCall],
        context: ToolExecutionContext,
    ):
        results: list[ToolExecutionResult | None] = [None] * len(calls)
        max_parallel = max(1, self.policy.max_parallel_read_tools)
        for start in range(0, len(calls), max_parallel):
            batch = calls[start : start + max_parallel]
            for call in batch:
                spec = self.registry.get(call.name)
                yield _event(
                    "tool.start",
                    {
                        "call_id": call.call_id,
                        "name": call.name,
                        "display_name": spec.display_name if spec else "工具",
                    },
                )
            tasks = [
                asyncio.create_task(self.runtime.execute(call=call, context=context))
                for call in batch
            ]
            batch_results = await asyncio.gather(*tasks)
            for offset, result in enumerate(batch_results):
                results[start + offset] = result
                if result.status in {"ok", "cache_hit"}:
                    yield _event(
                        "tool.done",
                        {
                            "call_id": result.call_id,
                            "name": result.tool_name,
                            "status": "ok",
                            "display": result.display_text or "已获取信息",
                        },
                    )
                else:
                    yield _event(
                        "tool.error",
                        {
                            "call_id": result.call_id,
                            "name": result.tool_name,
                            "code": result.error_code or "tool_error",
                            "message": result.error_message or "工具暂时不可用",
                        },
                    )
        self._call_results = [result for result in results if result is not None]

    @staticmethod
    def _append_tool_messages(
        messages: list[Any],
        calls: list[NormalizedToolCall],
        results: list[ToolExecutionResult],
    ) -> None:
        by_call_id = {result.call_id: result for result in results}
        for call in calls:
            result = by_call_id.get(call.call_id)
            payload = result.model_payload() if result is not None else {
                "ok": False,
                "tool": call.name,
                "error": {"code": "tool_error", "message": "工具暂时不可用"},
            }
            messages.append({
                "role": "tool",
                "tool_call_id": call.call_id,
                "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            })

    async def stream(
        self,
        *,
        model: Any,
        messages: list[Any],
        context: ToolExecutionContext,
        fallback_stream_factory: Any,
    ):
        """Yield existing message/tool events; final metadata is in last_result."""
        total_usage: dict[str, int] = {}
        tool_names: list[str] = []
        tool_run_ids: list[str] = []
        call_count = 0
        total_result_tokens = 0
        identical_calls: Counter[str] = Counter()
        history = list(messages)
        try:
            bound_model = bind_tools(model, self.registry.list_specs())
        except (ToolingUnavailableError, ImportError, AttributeError, TypeError, ValueError):
            debug_ai_event("chat_tooling_unavailable", session_id=context.session_id)
            if history and isinstance(history[0], dict) and history[0].get("role") == "system":
                fallback_messages = [
                    history[0],
                    {"role": "system", "content": TOOLING_UNAVAILABLE_NOTICE},
                    *history[1:],
                ]
            else:
                fallback_messages = [
                    {"role": "system", "content": TOOLING_UNAVAILABLE_NOTICE},
                    *history,
                ]
            fallback = fallback_stream_factory(model, fallback_messages)
            if inspect.isawaitable(fallback):
                fallback = await fallback
            try:
                async for delta, usage in fallback:
                    _merge_usage(total_usage, usage)
                    if delta:
                        yield _event("message.delta", {"delta": delta})
            finally:
                close = getattr(fallback, "aclose", None)
                if callable(close):
                    await close()
            self.last_result = ToolTurnResult(total_usage, 0, (), (), True)
            return

        for round_index in range(self.policy.max_rounds):
            async for item in self._stream_round(bound_model, history):
                yield item
            result = self._round_result
            for key, value in result.usage.items():
                total_usage[key] = total_usage.get(key, 0) + value
            calls = list(result.calls)
            history.append(_tool_call_message(result.text, calls))
            if not calls:
                self.last_result = ToolTurnResult(
                    total_usage, call_count, tuple(dict.fromkeys(tool_names)),
                    tuple(tool_run_ids), False,
                )
                return

            blocked = call_count + len(calls) > self.policy.max_calls_per_turn
            for call in calls:
                signature = f"{call.name}:{json.dumps(call.arguments, ensure_ascii=False, sort_keys=True)}"
                identical_calls[signature] += 1
                if identical_calls[signature] > self.policy.max_identical_calls:
                    blocked = True
            if blocked:
                history.append({"role": "system", "content": TOOLS_DISABLED_NOTICE})
                async for item in self._stream_round(model, history):
                    yield item
                final_result = self._round_result
                for key, value in final_result.usage.items():
                    total_usage[key] = total_usage.get(key, 0) + value
                self.last_result = ToolTurnResult(
                    total_usage, call_count, tuple(dict.fromkeys(tool_names)),
                    tuple(tool_run_ids), False,
                )
                return

            call_count += len(calls)
            for call in calls:
                tool_names.append(call.name)
            async for item in self._execute_calls(calls=calls, context=context):
                yield item
            results = list(self._call_results)
            self._append_tool_messages(history, calls, results)
            for result in results:
                if result.run_id:
                    tool_run_ids.append(result.run_id)
                if result.result is not None:
                    serialized = json.dumps(
                        result.result.data, ensure_ascii=False, separators=(",", ":")
                    )
                    total_result_tokens += max(1, (len(serialized) + 2) // 3)
            if round_index + 1 >= self.policy.max_rounds or total_result_tokens > self.policy.max_total_result_tokens:
                history.append({"role": "system", "content": TOOLS_DISABLED_NOTICE})
                async for item in self._stream_round(model, history):
                    yield item
                final_result = self._round_result
                for key, value in final_result.usage.items():
                    total_usage[key] = total_usage.get(key, 0) + value
                self.last_result = ToolTurnResult(
                    total_usage, call_count, tuple(dict.fromkeys(tool_names)),
                    tuple(tool_run_ids), False,
                )
                return


__all__ = ["TOOLING_UNAVAILABLE_NOTICE", "TOOLS_DISABLED_NOTICE", "ToolOrchestrator", "ToolTurnResult"]
