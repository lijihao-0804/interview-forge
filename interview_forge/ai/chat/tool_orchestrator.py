"""Streaming model ↔ read-only tool orchestration for one chat turn."""
from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections import Counter
from collections.abc import Mapping
from contextlib import aclosing
from dataclasses import dataclass, field, replace
from typing import Any

from interview_forge.ai.chat import quote_selection
from interview_forge.ai.chat.final_tool_reply import visible_final_reply
from interview_forge.ai.chat.history_sources import HistorySource, cited_history_sources
from interview_forge.ai.chat.token_budget import DEFAULT_CHAT_TOKEN_BUDGET
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
    "工具调用上限已达到。直接用自然语言回答，不要再生成工具调用。只用已有资料。历史候选与问题"
    "说法不同但含义相符时也可作证，引用能支持答案的原文和消息编号。其余候选略过；依据不足就说明未能确认。"
)
_UNCONFIRMED_HISTORY = "本次查询未能确认你问的历史记录。"
_UNCONFIRMED_RESULT = "现有信息不足以确认答案。"
TOOL_LIMIT_ERROR_CODE = "tool_limit_reached"
TOOL_LIMIT_ERROR_MESSAGE = "本轮工具调用上限已达到"
CONTEXT_BUDGET_ERROR_CODE = "context_budget_exceeded"
CONTEXT_BUDGET_ERROR_MESSAGE = "当前对话上下文超出模型可处理范围，请缩短问题或开启新会话。"
REQUEST_ADMISSION_POLICY_VERSION = "request_admission_v2"
DEFAULT_RESERVED_OUTPUT_TOKENS = 1200
_DEEPSEEK_QUOTE_MAX_OUTPUT_TOKENS = 3072
_DEEPSEEK_RECOVERY_MAX_OUTPUT_TOKENS = 2048


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

    async def _final_answer_round(self, model, messages, *, context, round_index, recalled, pending):
        # Keep this bounded, tool-disabled round private until its answer text
        # can be distinguished from a provider-native tool invocation.
        async for _ in self._stream_round(model, messages, context=context, round_index=round_index):
            pass
        result = self._round_result
        answer, suppressed = visible_final_reply(result.text)
        if not answer.strip() and (suppressed or result.calls):
            # Nearest passages alone cannot establish relevance, even when all
            # were indexed. Never turn them into automatic quotes or citations.
            if pending:
                answer = "操作请求仍在等待你确认。"
            else:
                answer = _UNCONFIRMED_HISTORY if recalled else _UNCONFIRMED_RESULT
        return _RoundResult(answer, (), result.usage)

    async def _quote_answer_round(self, model, context, batches, round_index, *, partial, review=False,
                                 direct_selection=False):
        window, reserve = self._context_budget_inputs(context)
        deepseek = context.artifacts.get("deepseek_chat_completions") is True
        if deepseek:
            window = window or DEFAULT_CHAT_TOKEN_BUDGET.max_request_tokens
            input_tokens = min(quote_selection.MAX_INPUT_TOKENS, max(0, window - 1))
        else:
            input_tokens = max(0, window - reserve) if window else quote_selection.MAX_INPUT_TOKENS
        messages, items = await asyncio.to_thread(
            quote_selection.prepare, context, batches, input_tokens=input_tokens,
            result_tokens=self.policy.max_total_result_tokens, review=review, direct_selection=direct_selection,
        )
        if not messages:
            return _RoundResult(quote_selection.no_quote(context.current_query), (), {}), ()
        original_context, original_model = context, model
        binder = getattr(model, "bind", None)
        if callable(binder):
            output_limit = min(quote_selection.MAX_OUTPUT_TOKENS, max(1, reserve))
            module = type(model).__module__
            if module.startswith("langchain_google"):
                model = binder(generation_config={"max_output_tokens": output_limit})
            elif getattr(model, "use_responses_api", False):
                model = binder(max_output_tokens=output_limit)
            elif deepseek:
                # ChatOpenAI rewrites its max_tokens kwarg to max_completion_tokens.
                # DeepSeek's wire limit covers reasoning and the visible selection.
                prompt_tokens = estimate_json_tokens({"messages": messages, "tools": []})
                output_limit = min(_DEEPSEEK_QUOTE_MAX_OUTPUT_TOKENS, window - prompt_tokens)
                configured_limit = getattr(model, "max_tokens", None)
                if type(configured_limit) is int and configured_limit > 0:
                    output_limit = min(output_limit, configured_limit)
                    # Drop only the constructor default that ChatOpenAI rewrites.
                    # A shallow copy retains its configured clients and transport.
                    model = model.model_copy(update={"max_tokens": None})
                if direct_selection:
                    # Keep enough room to relate paraphrases to technical terms.
                    # The shorter positive-only schema reduces work in this retry.
                    output_limit = min(output_limit, _DEEPSEEK_RECOVERY_MAX_OUTPUT_TOKENS)
                model = model.bind(extra_body={
                    **(getattr(model, "extra_body", None) or {}),
                    "max_tokens": output_limit,
                    "thinking": {"type": "enabled"},
                    "reasoning_effort": "low",
                })
            else:
                model = binder(max_tokens=output_limit)
            # Admission and its trace use the wire cap for this round only.
            context = replace(context, artifacts={**context.artifacts, "reserved_output_tokens": output_limit})
        size = 0
        # The selection is private data. Do not stream the JSON to the client.
        async with aclosing(self._stream_round(model, messages, context=context, round_index=round_index)) as stream:
            async for item in stream:
                size += len(item["data"]["delta"])
                if size > quote_selection.MAX_OUTPUT_CHARS:
                    break
        result = self._round_result
        decision = "" if result.calls or size > quote_selection.MAX_OUTPUT_CHARS else result.text
        answer, refs = await asyncio.to_thread(
            quote_selection.render, context, decision, items, partial=partial, direct_selection=direct_selection,
        )
        # A capped stream can contain the start of a valid JSON object but
        # stop before closing it. Retry incomplete wire output as well as an
        # entirely empty selection, never a well-formed unsupported claim.
        exhausted = (deepseek and callable(binder) and not result.calls and size <= quote_selection.MAX_OUTPUT_CHARS
                     and result.usage.get("output_tokens", 0) >= output_limit
                     and result.usage.get("reasoning_tokens", 0) > 0
                     and not quote_selection.has_complete_decision(decision))
        if (not review and not refs and round_index < self.policy.max_rounds and
                (exhausted or quote_selection.review_after_rejection(context.current_query, decision, items, batches))):
            # Give a corroborated negative a different question, too. Repeating
            # the exhaustive classification can spend the next round explaining
            # every rejection before returning even one source.
            retry, refs = await self._quote_answer_round(
                original_model, original_context, batches, round_index + 1, partial=partial,
                review=True, direct_selection=True,
            )
            usage = Counter(result.usage)
            usage.update(retry.usage)
            return _RoundResult(retry.text, (), dict(usage)), refs
        return _RoundResult(answer, (), result.usage), refs

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
        quote_requested = quote_selection.requested(context.current_query)
        unconfirmed_quote = quote_selection.no_quote(context.current_query)
        conditional_identity = quote_selection.identity_required(context.current_query)

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
            if quote_requested:
                # Source IDs and quotations need the owner-scoped history read.
                self.last_result = ToolTurnResult(tooling_unavailable=True, visible_text_chars=len(unconfirmed_quote))
                yield _event("message.delta", {"delta": unconfirmed_quote})
                return
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
                if not quote_requested:
                    yield item
            result = self._round_result
            for key, value in result.usage.items():
                total_usage[key] = total_usage.get(key, 0) + value
            calls = list(result.calls)
            if quote_requested and not calls:
                recall_spec = self.registry.get("recall_chat_history")
                if (recall_spec and recall_spec.kind == ToolKind.READ and not recall_spec.requires_confirmation
                        and call_count < self.policy.max_calls_per_turn and recall_spec.name not in tool_names):
                    # The model can answer from a recent message without a tool.
                    # Reopen the bounded evidence path before exposing any quotation.
                    calls = [NormalizedToolCall(f"recall-request-{round_index + 1}", recall_spec.name,
                                                {"mode": "semantic", "query": context.current_query.strip()[:96]})]
                else:
                    result = _RoundResult(unconfirmed_quote, (), result.usage)
            if quote_requested and not conditional_identity and any(
                not (spec := self.registry.get(call.name)) or spec.kind != ToolKind.READ or spec.requires_confirmation
                for call in calls
            ):
                quote_requested = False
                if result.text:
                    yield _event("message.delta", {"delta": result.text})
            if not quote_requested or not calls:
                visible_text_parts.append(result.text)
                if quote_requested and result.text:
                    yield _event("message.delta", {"delta": result.text})
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
            else:
                call_count += len(calls)
                tool_names.extend(call.name for call in calls)
                async for item in self._execute_calls(calls=calls, context=context):
                    yield item
                results = list(self._call_results)
                if any(result.status in {"ok", "cache_hit", "confirmation_required"} for result in results):
                    has_valid_tool_activity = True
                if any(result.status == "confirmation_required" and result.action_id for result in results):
                    has_pending_confirmation = True
                total_result_tokens += self._append_tool_messages(
                    history, calls, results, sources_by_position=sources_by_position, recall_by_position=recall_by_position,
                )
                tool_run_ids.extend(result.run_id for result in results if result.run_id)
                recall_results = [r for r in results if r.tool_name == "recall_chat_history" and r.status in {"ok", "cache_hit"}]
                if quote_requested and recall_results:
                    supplement = quote_selection.semantic_supplement(context.current_query, calls, recall_results)
                    if (supplement and call_count < self.policy.max_calls_per_turn
                            and total_result_tokens < self.policy.max_total_result_tokens):
                        extra = NormalizedToolCall(f"recall-semantic-{call_count + 1}", "recall_chat_history",
                                                   {"mode": "semantic", "query": supplement})
                        history.append(_tool_call_message("", [extra]))
                        async for item in self._execute_calls(calls=[extra], context=context):
                            yield item
                        extra_results = self._call_results
                        call_count += 1
                        tool_names.append(extra.name)
                        tool_run_ids.extend(r.run_id for r in extra_results if r.run_id)
                        total_result_tokens += self._append_tool_messages(
                            history, [extra], extra_results, sources_by_position=sources_by_position,
                            recall_by_position=recall_by_position,
                        )
                        recall_results.extend(r for r in extra_results if r.status in {"ok", "cache_hit"})
                    # Rank from the actual tool evidence. A holder of a prompt
                    # or tool-run ID cannot inject an account/session selector.
                    batches = []
                    for r in reversed(recall_results):
                        if r.result and estimate_json_tokens(r.model_payload()) <= self.policy.max_total_result_tokens:
                            batches.append(r.result.data.get("items", []))
                    partial = any(r.result and (r.result.data.get("retrieval", {}).get("coverage_complete") is False
                                  or r.arguments.get("after_message_id") or r.arguments.get("before_message_id")
                                  or r.arguments.get("message_id")) for r in recall_results)
                    final, refs = await self._quote_answer_round(model, context, batches, round_index + 2, partial=partial)
                    for key, value in final.usage.items():
                        total_usage[key] = total_usage.get(key, 0) + value
                    if conditional_identity and has_pending_confirmation:
                        final = _RoundResult(final.text + "\n\n操作请求仍在等待你确认。", (), final.usage)
                    yield _event("message.delta", {"delta": final.text})
                    self.last_result = ToolTurnResult(usage=total_usage, tool_calls_count=call_count,
                        tool_names=tuple(dict.fromkeys(tool_names)), tool_run_ids=tuple(tool_run_ids),
                        visible_text_chars=len(final.text), has_valid_tool_activity=True,
                        has_pending_confirmation=has_pending_confirmation, history_sources=refs)
                    return
                if round_index + 1 < self.policy.max_rounds and total_result_tokens <= self.policy.max_total_result_tokens:
                    continue

            if quote_requested:
                # A blocked or failed read cannot be replaced by unverified model text.
                answer = unconfirmed_quote
                if conditional_identity and has_pending_confirmation:
                    answer += "\n\n操作请求仍在等待你确认。"
                self.last_result = ToolTurnResult(usage=total_usage, tool_calls_count=call_count,
                    tool_names=tuple(dict.fromkeys(tool_names)), tool_run_ids=tuple(tool_run_ids),
                    visible_text_chars=len(answer), has_valid_tool_activity=has_valid_tool_activity,
                    has_pending_confirmation=has_pending_confirmation)
                yield _event("message.delta", {"delta": answer})
                return
            final_messages = _with_tool_notice(history, TOOLS_DISABLED_NOTICE)
            final_result = await self._final_answer_round(
                model, final_messages, context=context, round_index=round_index + 2,
                recalled="recall_chat_history" in tool_names or any(call.name == "recall_chat_history" for call in calls),
                pending=has_pending_confirmation,
            )
            if final_result.text:
                visible_text_parts.append(final_result.text)
                yield _event("message.delta", {"delta": final_result.text})
            for key, value in final_result.usage.items():
                total_usage[key] = total_usage.get(key, 0) + value
            offset = len(final_messages) - len(history)
            self.last_result = ToolTurnResult(
                usage=total_usage,
                tool_calls_count=call_count,
                tool_names=tuple(dict.fromkeys(tool_names)),
                tool_run_ids=tuple(tool_run_ids),
                visible_text_chars=len("".join(visible_text_parts).strip()),
                has_valid_tool_activity=has_valid_tool_activity,
                has_pending_confirmation=has_pending_confirmation,
                library_sources=visible_library_sources(index_offset=offset),
                history_sources=visible_history_sources(final_result.text, offset),
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
