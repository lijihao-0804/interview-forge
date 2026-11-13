"""Per-request context admission before any chat model invocation.

This is a deliberately small project-local adaptation of AgentHub's context
budget guarantees: system instructions, the current user task, tool definitions,
and complete tool exchanges are atomic; older complete user turns are the only
conversation history eligible for eviction.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from interview_forge.ai.chat.token_budget import DEFAULT_CHAT_TOKEN_BUDGET
from interview_forge.ai.token_counting import (
    canonical_json,
    estimate_json_tokens,
)

REASON_FITS = "fits"
REASON_HISTORY_OMITTED = "history_omitted"
REASON_MANDATORY_OVERFLOW = "mandatory_context_exceeds_budget"
REASON_RESERVED_OUTPUT = "reserved_output_exceeds_context_window"

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


def _validate_tool_exchanges(messages: Sequence[Mapping[str, Any]]) -> None:
    """Reject orphan or incomplete tool exchanges before any eviction."""
    pending: set[str] = set()
    for message in messages:
        role = str(message["role"])
        if role == "tool":
            call_id = str(message["tool_call_id"])
            if call_id not in pending:
                raise ValueError(f"orphan tool message: {call_id}")
            pending.remove(call_id)
            continue
        if pending:
            raise ValueError("incomplete assistant/tool exchange")
        if role == "assistant" and message.get("tool_calls"):
            call_ids = [_call_id(call) for call in message["tool_calls"]]
            if len(call_ids) != len(set(call_ids)):
                raise ValueError("assistant tool call ids must be unique")
            pending.update(call_ids)
    if pending:
        raise ValueError("incomplete assistant/tool exchange")


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
) -> RequestAdmission:
    """Admit one model request without mutating or partially truncating it."""
    if (
        isinstance(reserved_output_tokens, bool)
        or not isinstance(reserved_output_tokens, int)
        or reserved_output_tokens < 0
    ):
        raise ValueError("reserved_output_tokens must be a non-negative integer")

    normalized = _normalize_messages(messages)
    schemas = _normalize_tool_schemas(tool_schemas)
    _validate_tool_exchanges(normalized)

    try:
        window = int(context_window) if context_window is not None else 0
    except (TypeError, ValueError):
        window = 0
    known_window = window > 0
    if known_window:
        available_prompt_tokens = max(0, window - reserved_output_tokens)
    else:
        available_prompt_tokens = DEFAULT_CHAT_TOKEN_BUDGET.max_prompt_tokens

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
        mandatory_indices = set(range(len(normalized)))

    evictable_indices = [
        index for index in range(len(normalized))
        if index not in mandatory_indices
    ]
    groups = _history_exchange_groups(normalized, evictable_indices)
    mandatory_messages = _ordered_selection(normalized, mandatory_indices)
    mandatory_tokens = _estimate_request(mandatory_messages, schemas, estimator)

    reason = REASON_FITS
    fits = mandatory_tokens <= available_prompt_tokens
    if fits:
        for group in reversed(groups):
            candidate_indices = mandatory_indices | set(group)
            candidate_messages = _ordered_selection(normalized, candidate_indices)
            candidate_tokens = _estimate_request(candidate_messages, schemas, estimator)
            if candidate_tokens > available_prompt_tokens:
                break
            mandatory_indices = candidate_indices
            mandatory_tokens = candidate_tokens
    else:
        reason = (
            REASON_RESERVED_OUTPUT
            if known_window and reserved_output_tokens >= window
            else REASON_MANDATORY_OVERFLOW
        )

    admitted = _ordered_selection(normalized, mandatory_indices)
    omitted = sum(1 for group in groups if not set(group).issubset(mandatory_indices))
    if fits and omitted:
        reason = REASON_HISTORY_OMITTED

    payload = _request_payload(admitted, schemas)
    estimated_prompt_tokens = estimate_json_tokens(payload, estimator=estimator)
    fingerprint = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return RequestAdmission(
        messages=admitted,
        estimated_prompt_tokens=estimated_prompt_tokens,
        omitted_exchange_count=omitted,
        fits=fits,
        reason=reason,
        request_fingerprint=fingerprint,
    )


__all__ = [
    "REASON_FITS",
    "REASON_HISTORY_OMITTED",
    "REASON_MANDATORY_OVERFLOW",
    "REASON_RESERVED_OUTPUT",
    "RequestAdmission",
    "admit_request",
    "estimate_json_tokens",
]
