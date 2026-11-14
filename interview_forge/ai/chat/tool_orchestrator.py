"""Streaming model ↔ read-only tool orchestration for one chat turn."""
from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from interview_forge.ai.chat.history_sources import HistorySource, cited_history_sources
from interview_forge.ai.chat.request_budget import (
    RequestAdmission,
    admit_request,
    estimate_json_tokens,
)
from interview_forge.ai.errors import AIServiceError
from interview_forge.ai.provider import _usage_from
from interview_forge.ai.telemetry import debug_ai_event
from interview_forge.ai.tools.contracts import (
    LibrarySource,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolKind,
)
from interview_forge.ai.tools.langchain_adapter import (
    NormalizedToolCall,
    ToolCallAccumulator,
    ToolingUnavailableError,
    bind_tools,
    tool_spec_schema,
    visible_text,
)
from interview_forge.ai.tools.policy import ToolPolicy
from interview_forge.ai.tools.registry import ToolRegistry, build_default_tool_registry
from interview_forge.ai.tools.runtime import ToolRuntime
from interview_forge.observability.ai_trace import TraceRecorder, utc_now_iso

TOOLING_UNAVAILABLE_NOTICE = (
    "当前工具能力不可用。需要站内书架检索、实时或用户特定数据时，请明确说明无法获取，"
    "不得自行猜测，也不要伪造工具结果。"
)
TOOLS_DISABLED_NOTICE = (
    "工具调用上限已达到。不要再请求工具；仅根据已有上下文与已经返回的工具结果回答，"
    "明确说明无法确认的信息。"
)
TOOL_LIMIT_ERROR_CODE = "tool_limit_reached"
TOOL_LIMIT_ERROR_MESSAGE = "本轮工具调用上限已达到"
CONTEXT_BUDGET_ERROR_CODE = "context_budget_exceeded"
CONTEXT_BUDGET_ERROR_MESSAGE = "当前对话上下文超出模型可处理范围，请缩短问题或开启新会话。"
REQUEST_ADMISSION_POLICY_VERSION = "request_admission_v2"
DEFAULT_RESERVED_OUTPUT_TOKENS = 1200


@dataclass(frozen=True)
class ToolTurnResult:
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls_count: int = 0
    tool_names: tuple[str, ...] = ()
    tool_run_ids: tuple[str, ...] = ()
    tooling_unavailable: bool = False
    visible_text_chars: int = 0
    has_valid_tool_activity: bool = False
    has_pending_confirmation: bool = False
    library_sources: tuple[LibrarySource, ...] = ()
    history_sources: tuple[HistorySource, ...] = ()

    @property
    def is_valid_turn(self) -> bool:
        """A successful turn must expose text or a pending confirmation."""
        return self.visible_text_chars > 0 or self.has_pending_confirmation


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


def _with_tool_notice(messages: list[Any], notice: str) -> list[Any]:
    """Put a server notice alongside the initial system instruction for all providers."""
    first = messages[0] if messages else None
    if isinstance(first, Mapping) and first.get("role") == "system" and isinstance(first.get("content"), str):
        return [{**first, "content": first["content"] + "\n\n" + notice}, *messages[1:]]
    return [{"role": "system", "content": notice}, *messages]


class ToolOrchestrator:
    """Own all model/tool rounds while keeping ChatService provider-agnostic."""

    def __init__(
        self,
        *,
        registry: ToolRegistry | None = None,
        policy: ToolPolicy | None = None,
        trace_recorder: TraceRecorder | None = None,
    ) -> None:
        self.registry = registry if registry is not None else build_default_tool_registry()
        self.policy = policy or ToolPolicy()
        self.runtime = ToolRuntime(self.registry)
        self.trace_recorder = trace_recorder
        self.last_result = ToolTurnResult()
        self._round_result = _RoundResult("", (), {})
        self._call_results: list[ToolExecutionResult] = []
        self._confirmation_action_ids: set[str] = set()
        self._visible_tool_message_indices: frozenset[int] = frozenset()

    @staticmethod
    def _context_budget_inputs(context: ToolExecutionContext) -> tuple[int | None, int]:
        artifacts = context.artifacts if isinstance(context.artifacts, Mapping) else {}
        raw_window = artifacts.get("model_context_window")
        context_window = (
            raw_window
            if isinstance(raw_window, int) and not isinstance(raw_window, bool) and raw_window > 0
            else None
        )
        raw_reserved = artifacts.get("reserved_output_tokens")
        reserved_output_tokens = (
            raw_reserved
            if isinstance(raw_reserved, int)
            and not isinstance(raw_reserved, bool)
            and raw_reserved >= 0
            else DEFAULT_RESERVED_OUTPUT_TOKENS
        )
        return context_window, reserved_output_tokens

    async def _record_request_admission(
        self,
        admission: RequestAdmission,
        *,
        context_window: int | None,
        reserved_output_tokens: int,
        round_index: int,
        fits: bool,
    ) -> None:
        if self.trace_recorder is None:
            return
        metadata = {
            "context_budget_policy_version": REQUEST_ADMISSION_POLICY_VERSION,
            "request_fingerprint": admission.request_fingerprint,
            "original_prompt_tokens": admission.original_prompt_tokens,
            "admitted_prompt_tokens": admission.estimated_prompt_tokens,
            "omitted_exchange_count": admission.omitted_exchange_count,
            "masked_tool_result_count": admission.masked_tool_result_count,
            "tool_result_tokens_saved": admission.tool_result_tokens_saved,
            "budget_rejected_tool_result_count": admission.budget_rejected_tool_result_count,
            "context_window": context_window,
            "reserved_output_tokens": reserved_output_tokens,
            "stop_reason": admission.reason,
        }
        try:
            await asyncio.to_thread(
                self.trace_recorder.record,
                event_type="context",
                name="request_admission",
                status="success" if fits else "failed",
                round_index=round_index,
                error_code=None if fits else CONTEXT_BUDGET_ERROR_CODE,
                metadata=metadata,
            )
        except Exception as exc:  # noqa: BLE001 - trace failures cannot block model calls
            # Admission telemetry is observability only. It must not change
            # whether a request reaches the provider.
            debug_ai_event(
                "request_admission_trace_failed",
                error_type=type(exc).__name__,
            )

    async def _admit_model_request(
        self,
        messages: list[Any],
        *,
        tool_schemas: tuple[dict[str, object], ...],
        context: ToolExecutionContext,
        round_index: int,
    ) -> list[Any]:
        context_window, reserved_output_tokens = self._context_budget_inputs(context)
        admission = admit_request(
            messages,
            tool_schemas=tool_schemas,
            context_window=context_window,
            reserved_output_tokens=reserved_output_tokens,
            read_tools={
                spec.name for spec in self.registry.list_specs()
                if spec.kind == ToolKind.READ and not spec.requires_confirmation
            },
            max_tool_result_tokens=self.policy.max_total_result_tokens,
        )
        await self._record_request_admission(
            admission,
            context_window=context_window,
            reserved_output_tokens=reserved_output_tokens,
            round_index=round_index,
            fits=bool(admission.fits),
        )
        if not admission.fits:
            raise AIServiceError(CONTEXT_BUDGET_ERROR_CODE, CONTEXT_BUDGET_ERROR_MESSAGE)
        self._visible_tool_message_indices = admission.visible_tool_message_indices
        return list(admission.messages)

    async def _stream_round(
        self,
        model: Any,
        messages: list[Any],
        *,
        context: ToolExecutionContext,
        tool_schemas: tuple[dict[str, object], ...] = (),
        round_index: int = 0,
    ):
        admitted_messages = await self._admit_model_request(
            messages,
            tool_schemas=tool_schemas,
            context=context,
            round_index=round_index,
        )
        text_parts: list[str] = []
        accumulator = ToolCallAccumulator()
        round_usage: dict[str, int] = {}
        iterator: Any = None
        started = time.perf_counter()
        started_at = utc_now_iso()
        status = "success"
        error_code = None
        try:
            astream = getattr(model, "astream", None)
            if callable(astream):
                iterator = astream(admitted_messages)
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
                iterator = iter(stream(admitted_messages))
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
        except BaseException as exc:
            status = "failed"
            error_code = type(exc).__name__
            raise
        finally:
            close = getattr(iterator, "aclose", None)
            if callable(close):
                try:
                    await close()
                except (Exception, GeneratorExit):
                    pass
            else:
                close = getattr(iterator, "close", None)
                if callable(close):
                    try:
                        await asyncio.to_thread(close)
                    except (Exception, GeneratorExit):
                        pass
            self._round_result = _RoundResult(
                "".join(text_parts), tuple(accumulator.finish()), round_usage
            )
            if self.trace_recorder is not None:
                try:
                    await asyncio.to_thread(
                        self.trace_recorder.record_llm_round,
                        round_index=round_index,
                        status=status,
                        duration_ms=(time.perf_counter() - started) * 1000,
                        usage=round_usage,
                        error_code=error_code,
                        started_at=started_at,
                        finished_at=utc_now_iso(),
                    )
                except Exception:
                    # Trace persistence is observability only and must never
                    # change the model/tool contract.
                    pass

    async def _execute_calls(
        self,
        *,
        calls: list[NormalizedToolCall],
        context: ToolExecutionContext,
    ):
        results: list[ToolExecutionResult | None] = [None] * len(calls)
        max_parallel = max(1, self.policy.max_parallel_read_tools)
        start = 0
        while start < len(calls):
            first_spec = self.registry.get(calls[start].name)
            read_batch = bool(
                first_spec
                and first_spec.kind == ToolKind.READ
                and not first_spec.requires_confirmation
            )
            if read_batch:
                batch = []
                while start + len(batch) < len(calls) and len(batch) < max_parallel:
                    candidate = calls[start + len(batch)]
                    candidate_spec = self.registry.get(candidate.name)
                    if not candidate_spec or candidate_spec.kind != ToolKind.READ or candidate_spec.requires_confirmation:
                        break
                    batch.append(candidate)
            else:
                batch = [calls[start]]
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
            try:
                batch_results = await asyncio.gather(*tasks)
            except BaseException:
                # A cancelled consumer, a closed stream, or one failing task
                # must not leave sibling READ work running in the background.
                # Cancellation stops async work; it cannot interrupt a Python
                # thread that has already started a synchronous handler.
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            for offset, result in enumerate(batch_results):
                results[start + offset] = result
                result_spec = self.registry.get(result.tool_name)
                if result.status in {"ok", "cache_hit"}:
                    yield _event(
                        "tool.done",
                        {
                            "call_id": result.call_id,
                            "name": result.tool_name,
                            "status": "ok",
                            "display_name": result_spec.display_name if result_spec else "工具",
                            "display": result.display_text or "已获取信息",
                        },
                    )
                elif result.status == "confirmation_required" and result.action_id:
                    spec = self.registry.get(result.tool_name)
                    if result.action_id not in self._confirmation_action_ids:
                        self._confirmation_action_ids.add(result.action_id)
                        yield _event(
                            "tool.confirmation_required",
                            {
                                "action_id": result.action_id,
                                "call_id": result.call_id,
                                "name": result.tool_name,
                                "display_name": result_spec.display_name if result_spec else "需要确认的操作",
                                "message": result.confirmation_text or "是否执行该操作？",
                                "expires_at": result.expires_at or "",
                            },
                        )
                else:
                    yield _event(
                        "tool.error",
                        {
                            "call_id": result.call_id,
                            "name": result.tool_name,
                            "code": result.error_code or "tool_error",
                            "display_name": result_spec.display_name if result_spec else "工具",
                            "message": result.error_message or "工具暂时不可用",
                        },
                    )
            start += len(batch)
        self._call_results = [result for result in results if result is not None]

    @staticmethod
    def _append_tool_messages(
        messages: list[Any],
        calls: list[NormalizedToolCall],
        results: list[ToolExecutionResult],
        *,
        sources_by_position: dict[int, tuple[LibrarySource, ...]],
        recall_by_position: dict[int, list[dict]] | None = None,
        blocked: bool = False,
    ) -> int:
        """Keep bounded runtime results in the turn. Admission controls each model's view."""
        by_call_id = {result.call_id: result for result in results}
        result_tokens = 0
        for call in calls:
            result = by_call_id.get(call.call_id)
            if blocked:
                payload = {
                    "ok": False,
                    "tool": call.name,
                    "error": {
                        "code": TOOL_LIMIT_ERROR_CODE,
                        "message": TOOL_LIMIT_ERROR_MESSAGE,
                    },
                }
            elif result is None:
                payload = {
                    "ok": False,
                    "tool": call.name,
                    "error": {"code": "tool_error", "message": "工具暂时不可用"},
                }
            else:
                payload = result.model_payload()
                if payload.get("ok") is True and result.result is not None:
                    result_tokens += estimate_json_tokens(payload)
                    if result.result.library_sources:
                        sources_by_position[len(messages)] = result.result.library_sources
                    if recall_by_position is not None and call.name == "recall_chat_history":
                        recall_by_position[len(messages)] = result.result.data.get("items", [])
            messages.append({
                "role": "tool",
                "tool_call_id": call.call_id,
                "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            })
        return result_tokens

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
        sources_by_position: dict[int, tuple[LibrarySource, ...]] = {}
        recall_by_position: dict[int, list[dict]] = {}
        identical_calls: Counter[str] = Counter()
        visible_text_parts: list[str] = []
        has_valid_tool_activity = False
        has_pending_confirmation = False
        history = list(messages)

        def visible_library_sources(*, index_offset: int = 0) -> tuple[LibrarySource, ...]:
            sources = {}
            for position, items in sources_by_position.items():
                if position + index_offset in self._visible_tool_message_indices:
                    for item in items:
                        sources.setdefault(item["url"], item)
            return tuple(sources.values())

        def visible_history_sources(answer: str, index_offset: int = 0) -> tuple[HistorySource, ...]:
            items = [item for position, batch in recall_by_position.items()
                     if position + index_offset in self._visible_tool_message_indices for item in batch]
            return cited_history_sources(answer, items)

        try:
            tool_schemas = tuple(
                tool_spec_schema(spec) for spec in self.registry.list_specs()
            )
            bound_model = bind_tools(model, self.registry.list_specs())
        except (ToolingUnavailableError, ImportError, AttributeError, TypeError, ValueError):
            debug_ai_event("chat_tooling_unavailable", session_id=context.session_id)
            fallback_messages = _with_tool_notice(history, TOOLING_UNAVAILABLE_NOTICE)
            admitted_fallback_messages = await self._admit_model_request(
                fallback_messages,
                tool_schemas=(),
                context=context,
                round_index=1,
            )
            fallback = fallback_stream_factory(model, admitted_fallback_messages)
            if inspect.isawaitable(fallback):
                fallback = await fallback
            try:
                async for delta, usage in fallback:
                    _merge_usage(total_usage, usage)
                    if delta:
                        visible_text_parts.append(delta)
                        yield _event("message.delta", {"delta": delta})
            finally:
                close = getattr(fallback, "aclose", None)
                if callable(close):
                    await close()
            self.last_result = ToolTurnResult(
                usage=total_usage,
                tooling_unavailable=True,
                visible_text_chars=len("".join(visible_text_parts).strip()),
            )
            return

        for round_index in range(self.policy.max_rounds):
            async for item in self._stream_round(
                bound_model,
                history,
                context=context,
                tool_schemas=tool_schemas,
                round_index=round_index + 1,
            ):
                yield item
            result = self._round_result
            visible_text_parts.append(result.text)
            for key, value in result.usage.items():
                total_usage[key] = total_usage.get(key, 0) + value
            calls = list(result.calls)
            history.append(_tool_call_message(result.text, calls))
            if not calls:
                self.last_result = ToolTurnResult(
                    usage=total_usage,
                    tool_calls_count=call_count,
                    tool_names=tuple(dict.fromkeys(tool_names)),
                    tool_run_ids=tuple(tool_run_ids),
                    visible_text_chars=len("".join(visible_text_parts).strip()),
                    has_valid_tool_activity=has_valid_tool_activity,
                    has_pending_confirmation=has_pending_confirmation,
                    library_sources=visible_library_sources(),
                    history_sources=visible_history_sources(result.text),
                )
                return

            blocked = call_count + len(calls) > self.policy.max_calls_per_turn
            for call in calls:
                signature = self._canonical_call_signature(call)
                identical_calls[signature] += 1
                if identical_calls[signature] > self.policy.max_identical_calls:
                    blocked = True
            if blocked:
                # The provider contract requires one tool result for every
                # assistant tool call.  These calls are deliberately not sent
                # to ToolRuntime: they are represented by safe synthetic
                # results so the final model call remains well-formed.
                for call in calls:
                    yield _event(
                        "tool.error",
                        {
                            "call_id": call.call_id,
                            "name": call.name,
                            "code": TOOL_LIMIT_ERROR_CODE,
                            "display_name": self.registry.get(call.name).display_name if self.registry.get(call.name) else "工具",
                            "message": TOOL_LIMIT_ERROR_MESSAGE,
                        },
                    )
                self._append_tool_messages(history, calls, [], sources_by_position=sources_by_position, blocked=True)
                final_messages = _with_tool_notice(history, TOOLS_DISABLED_NOTICE)
                async for item in self._stream_round(
                    model,
                    final_messages,
                    context=context,
                    tool_schemas=(),
                    round_index=round_index + 2,
                ):
                    yield item
                final_result = self._round_result
                visible_text_parts.append(final_result.text)
                for key, value in final_result.usage.items():
                    total_usage[key] = total_usage.get(key, 0) + value
                self.last_result = ToolTurnResult(
                    usage=total_usage,
                    tool_calls_count=call_count,
                    tool_names=tuple(dict.fromkeys(tool_names)),
                    tool_run_ids=tuple(tool_run_ids),
                    visible_text_chars=len("".join(visible_text_parts).strip()),
                    has_valid_tool_activity=has_valid_tool_activity,
                    has_pending_confirmation=has_pending_confirmation,
                    library_sources=visible_library_sources(index_offset=len(final_messages) - len(history)),
                    history_sources=visible_history_sources(final_result.text, len(final_messages) - len(history)),
                )
                return

            call_count += len(calls)
            for call in calls:
                tool_names.append(call.name)
            async for item in self._execute_calls(calls=calls, context=context):
                yield item
            results = list(self._call_results)
            if any(result.status in {"ok", "cache_hit", "confirmation_required"} for result in results):
                has_valid_tool_activity = True
            if any(
                result.status == "confirmation_required" and bool(result.action_id)
                for result in results
            ):
                has_pending_confirmation = True
            total_result_tokens += self._append_tool_messages(
                history, calls, results, sources_by_position=sources_by_position, recall_by_position=recall_by_position,
            )
            for result in results:
                if result.run_id:
                    tool_run_ids.append(result.run_id)
            if round_index + 1 >= self.policy.max_rounds or total_result_tokens > self.policy.max_total_result_tokens:
                final_messages = _with_tool_notice(history, TOOLS_DISABLED_NOTICE)
                async for item in self._stream_round(
                    model,
                    final_messages,
                    context=context,
                    tool_schemas=(),
                    round_index=round_index + 2,
                ):
                    yield item
                final_result = self._round_result
                visible_text_parts.append(final_result.text)
                for key, value in final_result.usage.items():
                    total_usage[key] = total_usage.get(key, 0) + value
                self.last_result = ToolTurnResult(
                    usage=total_usage,
                    tool_calls_count=call_count,
                    tool_names=tuple(dict.fromkeys(tool_names)),
                    tool_run_ids=tuple(tool_run_ids),
                    visible_text_chars=len("".join(visible_text_parts).strip()),
                    has_valid_tool_activity=has_valid_tool_activity,
                    has_pending_confirmation=has_pending_confirmation,
                    library_sources=visible_library_sources(index_offset=len(final_messages) - len(history)),
                    history_sources=visible_history_sources(final_result.text, len(final_messages) - len(history)),
                )
                return

    def _canonical_call_signature(self, call: NormalizedToolCall) -> str:
        """Build duplicate-call identity from server-normalized arguments."""
        spec = self.registry.get(call.name)
        if spec is not None:
            try:
                _, arguments = self.runtime._validated_args(spec, call.arguments)
            except (AttributeError, TypeError, ValueError):
                pass
            else:
                canonical = json.dumps(
                    arguments,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                return f"{call.name}:{canonical}"
        raw = json.dumps(
            call.arguments,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return f"{call.name}:unvalidated:{raw}"


__all__ = ["TOOLING_UNAVAILABLE_NOTICE", "TOOLS_DISABLED_NOTICE", "ToolOrchestrator", "ToolTurnResult"]
