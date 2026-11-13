"""Per-request context admission before any chat model invocation.

This is a deliberately small project-local adaptation of AgentHub's context
budget guarantees. System instructions, the current user task, tool definitions
and tool call/result pairs stay intact. Under pressure the request view can hide
stale read observations and omit older complete turns. Source history stays intact.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from interview_forge.ai.chat.token_budget import DEFAULT_CHAT_TOKEN_BUDGET
from interview_forge.ai.token_counting import (
    canonical_json,
    estimate_json_tokens,
)

REASON_FITS = "fits"
REASON_HISTORY_OMITTED = "history_omitted"
REASON_TOOL_RESULTS_REDUCED = "tool_results_reduced"
REASON_MANDATORY_OVERFLOW = "mandatory_context_exceeds_budget"
REASON_RESERVED_OUTPUT = "reserved_output_exceeds_context_window"
TOOL_RESULT_BUDGET_ERROR_CODE = "tool_result_budget_exceeded"
TOOL_RESULT_BUDGET_ERROR_MESSAGE = "该工具结果因本轮上下文预算限制未完整提供"
_MASKED_READ_CONTENT = '{"omitted":"earlier_read_result"}'

_SYSTEM_ROLES = frozenset({"system", "developer"})
_ROLE_ALIASES = {
    "human": "user",
    "ai": "assistant",
    "bot": "assistant",
}
_SUPPORTED_LANGCHAIN_TYPES = frozenset(
    {"system", "human", "ai", "tool", "function", "chat"}
)


@dataclass(frozen=True, slots=True)
class RequestAdmission:
    """The provider-facing messages and the outcome of one budget decision."""

    messages: list[dict[str, Any]]
    estimated_prompt_tokens: int
    omitted_exchange_count: int
    fits: bool
    reason: str
    request_fingerprint: str
    original_prompt_tokens: int
    masked_tool_result_count: int
    budget_rejected_tool_result_count: int
    tool_result_tokens_saved: int
    # Positions in the original input distinguish repeated provider call IDs.
    visible_tool_message_indices: frozenset[int]


def _role_name(value: Any) -> str:
    role = str(value or "").strip().lower()
    if not role:
        raise ValueError("message role must be non-empty")
    return _ROLE_ALIASES.get(role, role)


def _json_value(value: Any) -> Any:
    """Round-trip through the canonical representation to avoid aliasing."""
    return json.loads(canonical_json(value))


def _normalize_tool_calls(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, Mapping)):
        raise TypeError("tool_calls must be a sequence")
    try:
        calls = list(value)
    except TypeError:
        raise TypeError("tool_calls must be a sequence") from None
    if not calls:
        return []
    normalized = _json_value(calls)
    if not isinstance(normalized, list) or any(not isinstance(call, Mapping) for call in normalized):
        raise ValueError("each tool call must be an object")
    return normalized


def _normalize_message(message: Any) -> dict[str, Any]:
    """Convert current dict/LangChain messages to provider-neutral wire dicts."""
    if isinstance(message, Mapping):
        raw_role = message.get("role", message.get("type"))
        role = _role_name(raw_role)
        result: dict[str, Any] = {"role": role}
        if "content" in message:
            result["content"] = _json_value(message["content"])
        else:
            result["content"] = ""
        name = message.get("name")
        if name is not None:
            result["name"] = _json_value(name)
        if role == "tool":
            tool_call_id = message.get("tool_call_id", message.get("call_id"))
            if tool_call_id is None or not str(tool_call_id):
                raise ValueError("tool message must have tool_call_id")
            result["tool_call_id"] = _json_value(tool_call_id)
        tool_calls = _normalize_tool_calls(message.get("tool_calls"))
        if tool_calls:
            result["tool_calls"] = tool_calls
        if "function_call" in message:
            result["function_call"] = _json_value(message["function_call"])
        return result

    message_type = str(getattr(message, "type", "") or "").lower()
    if message_type not in _SUPPORTED_LANGCHAIN_TYPES:
        raise TypeError(
            "messages must be dicts or supported LangChain message objects; "
            f"got {type(message).__name__}"
        )
    if not hasattr(message, "content"):
        raise TypeError(f"LangChain {type(message).__name__} message has no content")

    if message_type == "chat":
        role = _role_name(getattr(message, "role", ""))
    else:
        role = _role_name(message_type)
    result = {"role": role, "content": _json_value(message.content)}
    name = getattr(message, "name", None)
    if name is not None:
        result["name"] = _json_value(name)
    if role == "tool":
        tool_call_id = getattr(message, "tool_call_id", None)
        if tool_call_id is None or not str(tool_call_id):
            raise ValueError("tool message must have tool_call_id")
        result["tool_call_id"] = _json_value(tool_call_id)

    tool_calls = _normalize_tool_calls(getattr(message, "tool_calls", None))
    additional_kwargs = getattr(message, "additional_kwargs", None)
    if not tool_calls and isinstance(additional_kwargs, Mapping):
        tool_calls = _normalize_tool_calls(additional_kwargs.get("tool_calls"))
        function_call = additional_kwargs.get("function_call")
        if function_call is not None:
            result["function_call"] = _json_value(function_call)
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


def _normalize_messages(messages: Any) -> list[dict[str, Any]]:
    if isinstance(messages, (str, bytes, Mapping)):
        raise TypeError("messages must be a sequence")
    try:
        values = list(messages)
    except TypeError:
        raise TypeError("messages must be a sequence") from None
    return [_normalize_message(message) for message in values]


def _normalize_tool_schemas(tool_schemas: Any) -> list[Any]:
    if tool_schemas is None:
        return []
    if isinstance(tool_schemas, (str, bytes, Mapping)):
        values = [tool_schemas]
    else:
        try:
            values = list(tool_schemas)
        except TypeError:
            values = [tool_schemas]
    return [_json_value(value) for value in values]


def _call_id(call: Mapping[str, Any]) -> str:
    value = call.get("id", call.get("tool_call_id", call.get("call_id")))
    if value is None or not str(value):
        raise ValueError("assistant tool call must have an id")
    return str(value)


def _tool_exchanges(messages: Sequence[Mapping[str, Any]]) -> list[dict[int, str]]:
    """Validate pairs and associate each result position with its called tool."""
    exchanges: list[dict[int, str]] = []
    pending: dict[str, str] = {}
    for index, message in enumerate(messages):
        role = str(message["role"])
        if role == "tool":
            call_id = str(message["tool_call_id"])
            if call_id not in pending:
                raise ValueError(f"orphan tool message: {call_id}")
            exchanges[-1][index] = pending.pop(call_id)
            continue
        if pending:
            raise ValueError("incomplete assistant/tool exchange")
        if role == "assistant" and message.get("tool_calls"):
            exchanges.append({})
            for call in message["tool_calls"]:
                call_id = _call_id(call)
                if call_id in pending:
                    raise ValueError("assistant tool call ids must be unique")
                function = call.get("function")
                name = call.get("name") or (function.get("name") if isinstance(function, Mapping) else None)
                pending[call_id] = name if isinstance(name, str) else ""
    if pending:
        raise ValueError("incomplete assistant/tool exchange")
    return exchanges


def _request_payload(
    messages: Sequence[Mapping[str, Any]],
    tool_schemas: Sequence[Any],
) -> dict[str, Any]:
    return {"messages": list(messages), "tools": list(tool_schemas)}


def _estimate_request(
    messages: Sequence[Mapping[str, Any]],
    tool_schemas: Sequence[Any],
    estimator: Any,
) -> int:
    return estimate_json_tokens(
        _request_payload(messages, tool_schemas),
        estimator=estimator,
    )


def _read_result_costs(
    messages: Sequence[Mapping[str, Any]],
    exchange: Mapping[int, str],
    read_tools: Collection[str],
    estimator: Any,
) -> dict[int, int]:
    """Only the runtime's successful READ envelope is eligible for reduction."""
    costs = {}
    for index, name in exchange.items():
        content = messages[index]["content"]
        if name not in read_tools or not isinstance(content, str):
            continue
        try:
            payload = json.loads(content)
        except ValueError:
            continue
        if (
            isinstance(payload, dict) and payload.keys() == {"ok", "tool", "data"}
            and payload["ok"] is True and payload["tool"] == name and isinstance(payload["data"], dict)
        ):
            costs[index] = estimate_json_tokens(payload, estimator)
    return costs


def _reduce_tool_results(
    messages: list[dict[str, Any]],
    exchanges: list[dict[int, str]],
    *,
    current_start: int | None,
    read_tools: Collection[str],
    schemas: Sequence[Any],
    estimator: Any,
    original_tokens: int,
    available_prompt_tokens: int,
    max_tool_result_tokens: int | None,
) -> tuple[set[int], set[int]]:
    """Edit the provider view before evicting any turns. Keep the newest batch whole
    for prompt pressure and enforce the separate hard cap on this turn's raw results.
    """
    masked: set[int] = set()
    rejected: set[int] = set()
    if not exchanges or not read_tools or current_start is None:
        return masked, rejected
    batches = [_read_result_costs(messages, exchange, read_tools, estimator) for exchange in exchanges]
    result_tokens = sum(cost for batch in batches for index, cost in batch.items() if index > current_start)
    prompt_tokens = original_tokens
    # Leave some headroom for the next call. There is no proactive eviction of
    # turns or of the last parallel batch if earlier reads cannot free this much.
    pressure_threshold = available_prompt_tokens * 9 // 10
    # The last successful read batch stays visible even when the next batch is
    # entirely blocked, awaiting confirmation, unknown, or failed.
    last_read_batch = max((number for number, batch in enumerate(batches) if batch), default=-1)
    for number in range(last_read_batch):
        exchange, batch = exchanges[number], batches[number]
        if len(batch) != len(exchange):
            continue
        for index, cost in batch.items():
            needs_quota = (
                index > current_start and max_tool_result_tokens is not None
                and result_tokens > max_tool_result_tokens
            )
            if prompt_tokens <= pressure_threshold and not needs_quota:
                continue
            message = messages[index]
            smaller = {**message, "content": _MASKED_READ_CONTENT}
            # Don't replace a short observation by a more expensive marker.
            if estimate_json_tokens(smaller, estimator) >= estimate_json_tokens(message, estimator):
                continue
            messages[index] = smaller
            masked.add(index)
            if index > current_start:
                result_tokens -= cost
            prompt_tokens = _estimate_request(messages, schemas, estimator)

    # Preserve the previous within-batch ordering when one fresh batch by
    # itself exceeds the tool result cap. Older mixed/error batches stay intact.
    if max_tool_result_tokens is not None and result_tokens > max_tool_result_tokens:
        latest = {i: cost for i, cost in batches[-1].items() if i > current_start}
        used = result_tokens - sum(latest.values())
        for index, cost in latest.items():
            if used + cost <= max_tool_result_tokens:
                used += cost
                continue
            messages[index] = {**messages[index], "content": canonical_json({
                "ok": False, "tool": exchanges[-1][index],
                "error": {"code": TOOL_RESULT_BUDGET_ERROR_CODE, "message": TOOL_RESULT_BUDGET_ERROR_MESSAGE},
            })}
            rejected.add(index)
    return masked, rejected


def _ordered_selection(
    messages: Sequence[Mapping[str, Any]],
    selected_indices: set[int],
) -> list[dict[str, Any]]:
    return [dict(message) for index, message in enumerate(messages) if index in selected_indices]


def _history_exchange_groups(
    messages: Sequence[Mapping[str, Any]],
    evictable_indices: Sequence[int],
) -> list[list[int]]:
    """Split old history at user boundaries so each turn is all-or-nothing."""
    groups: list[list[int]] = []
    current: list[int] = []
    for index in evictable_indices:
        if messages[index]["role"] == "user" and current:
            groups.append(current)
            current = []
        current.append(index)
    if current:
        groups.append(current)
    return groups


def admit_request(
    messages: Any,
    *,
    tool_schemas: Any = (),
    context_window: Any = None,
    reserved_output_tokens: int = 1200,
    estimator: Any = None,
    read_tools: Collection[str] = (),
    max_tool_result_tokens: int | None = None,
) -> RequestAdmission:
    """Build one provider request without modifying the caller's source history."""
    if (
        isinstance(reserved_output_tokens, bool)
        or not isinstance(reserved_output_tokens, int)
        or reserved_output_tokens < 0
    ):
        raise ValueError("reserved_output_tokens must be a non-negative integer")
    if max_tool_result_tokens is not None and (
        isinstance(max_tool_result_tokens, bool)
        or not isinstance(max_tool_result_tokens, int)
        or max_tool_result_tokens < 0
    ):
        raise ValueError("max_tool_result_tokens must be a non-negative integer")

    normalized = _normalize_messages(messages)
    schemas = _normalize_tool_schemas(tool_schemas)
    exchanges = _tool_exchanges(normalized)
    original_tokens = _estimate_request(normalized, schemas, estimator)
    view = normalized.copy()

    try:
        window = int(context_window) if context_window is not None else 0
    except (TypeError, ValueError):
        window = 0
    known_window = window > 0
    if known_window:
        available_prompt_tokens = max(0, window - reserved_output_tokens)
    else:
        available_prompt_tokens = min(
            DEFAULT_CHAT_TOKEN_BUDGET.max_prompt_tokens,
            max(0, DEFAULT_CHAT_TOKEN_BUDGET.max_request_tokens - reserved_output_tokens),
        )

    user_indices = [
        index for index, message in enumerate(normalized)
        if message["role"] == "user"
    ]
    if user_indices:
        current_start = user_indices[-1]
        mandatory_indices = {
            index for index, message in enumerate(normalized)
            if message["role"] in _SYSTEM_ROLES or index >= current_start
        }
    else:
        # Without a user anchor there is no safe history boundary. Preserve the
        # complete input and let the budget decision be explicit.
        current_start = None
        mandatory_indices = set(range(len(normalized)))

    masked, rejected = _reduce_tool_results(
        view, exchanges, current_start=current_start, read_tools=read_tools, schemas=schemas,
        estimator=estimator, original_tokens=original_tokens, available_prompt_tokens=available_prompt_tokens,
        max_tool_result_tokens=max_tool_result_tokens,
    )
    evictable_indices = [
        index for index in range(len(normalized))
        if index not in mandatory_indices
    ]
    groups = _history_exchange_groups(normalized, evictable_indices)
    view_tokens = _estimate_request(view, schemas, estimator) if masked or rejected else original_tokens
    if view_tokens <= available_prompt_tokens:
        mandatory_indices = set(range(len(view)))
        mandatory_tokens = view_tokens
    else:
        mandatory_tokens = _estimate_request(_ordered_selection(view, mandatory_indices), schemas, estimator)
    fits = mandatory_tokens <= available_prompt_tokens
    if fits and view_tokens > available_prompt_tokens:
        for group in reversed(groups):
            candidate_indices = mandatory_indices | set(group)
            candidate_messages = _ordered_selection(view, candidate_indices)
            candidate_tokens = _estimate_request(candidate_messages, schemas, estimator)
            if candidate_tokens > available_prompt_tokens:
                break
            mandatory_indices = candidate_indices
            mandatory_tokens = candidate_tokens

    admitted = _ordered_selection(view, mandatory_indices)
    omitted = sum(1 for group in groups if not set(group).issubset(mandatory_indices))
    visible_masked = masked & mandatory_indices
    visible_rejected = rejected & mandatory_indices
    if not fits:
        reason = (
            REASON_RESERVED_OUTPUT
            if known_window and reserved_output_tokens >= window
            else REASON_MANDATORY_OVERFLOW
        )
    elif omitted:
        reason = REASON_HISTORY_OMITTED
    elif visible_masked or visible_rejected:
        reason = REASON_TOOL_RESULTS_REDUCED
    else:
        reason = REASON_FITS

    payload = _request_payload(admitted, schemas)
    fingerprint = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    original_selected_tokens = mandatory_tokens
    if visible_masked or visible_rejected:
        original_selected_tokens = _estimate_request(_ordered_selection(normalized, mandatory_indices), schemas, estimator)
    return RequestAdmission(
        messages=admitted,
        estimated_prompt_tokens=mandatory_tokens,
        omitted_exchange_count=omitted,
        fits=fits,
        reason=reason,
        request_fingerprint=fingerprint,
        original_prompt_tokens=original_tokens,
        masked_tool_result_count=len(visible_masked),
        budget_rejected_tool_result_count=len(visible_rejected),
        tool_result_tokens_saved=max(0, original_selected_tokens - mandatory_tokens),
        visible_tool_message_indices=frozenset(
            i for exchange in exchanges for i in exchange
            if i in mandatory_indices and i not in masked and i not in rejected
        ),
    )


__all__ = [
    "REASON_FITS",
    "REASON_HISTORY_OMITTED",
    "REASON_MANDATORY_OVERFLOW",
    "REASON_RESERVED_OUTPUT",
    "REASON_TOOL_RESULTS_REDUCED",
    "RequestAdmission",
    "admit_request",
    "estimate_json_tokens",
]
