"""The only module allowed to know LangChain tool-call wire shapes."""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from interview_forge.ai.tools.contracts import ToolSpec


class ToolingUnavailableError(RuntimeError):
    """The configured ChatModel does not expose LangChain tool binding."""


def tool_spec_schema(spec: ToolSpec) -> dict[str, object]:
    """Convert a domain ToolSpec to the OpenAI-compatible function schema."""
    parameters = spec.args_model.model_json_schema()
    if isinstance(parameters, dict):
        parameters = dict(parameters)
        parameters.setdefault("type", "object")
        parameters["additionalProperties"] = False
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": parameters,
        },
    }


def bind_tools(model: Any, specs: Sequence[ToolSpec]) -> Any:
    binder = getattr(model, "bind_tools", None)
    if not callable(binder):
        raise ToolingUnavailableError("model does not support bind_tools")
    try:
        return binder([tool_spec_schema(spec) for spec in specs])
    except (AttributeError, TypeError, ValueError) as exc:
        raise ToolingUnavailableError("model tool binding is unavailable") from exc


@dataclass(frozen=True)
class NormalizedToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"__invalid_json_arguments__": True}
        return dict(decoded) if isinstance(decoded, Mapping) else {"__invalid_arguments__": True}
    return {"__invalid_arguments__": True}


def normalize_tool_calls(message: Any) -> list[NormalizedToolCall]:
    """Normalize complete AIMessage tool calls without exposing provider details."""
    raw_calls = _value(message, "tool_calls", ()) or ()
    result: list[NormalizedToolCall] = []
    for index, raw in enumerate(raw_calls):
        name = str(_value(raw, "name", ""))
        if not name:
            continue
        call_id = str(_value(raw, "id", "") or f"tool-call-{index}")
        args = _value(raw, "args", _value(raw, "arguments", {}))
        result.append(NormalizedToolCall(call_id, name, _arguments(args)))
    return result


def visible_text(message: Any) -> str:
    """Extract only visible answer text; reasoning/tool chunks are dropped."""
    content = _value(message, "content", "")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        item_type = str(_value(item, "type", "text"))
        if item_type not in {"text", "output_text"}:
            continue
        text = _value(item, "text", "")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


@dataclass
class ToolCallAccumulator:
    """Aggregate LangChain AIMessageChunk tool_call_chunks by stable index/id."""

    _calls: dict[str, dict[str, Any]] = field(default_factory=dict)
    _order: list[str] = field(default_factory=list)

    def add(self, chunk: Any) -> None:
        raw_chunks = _value(chunk, "tool_call_chunks", ()) or ()
        if raw_chunks:
            for index, raw in enumerate(raw_chunks):
                raw_id = _value(raw, "id")
                raw_index = _value(raw, "index")
                # LangChain may emit the id only on the first chunk and keep
                # only index on later argument chunks.  Index is therefore
                # the primary stream key; the provider id remains payload.
                if raw_index is not None:
                    key = f"index:{raw_index}"
                elif raw_id:
                    key = f"id:{raw_id}"
                else:
                    key = f"position:{index}"
                if key not in self._calls:
                    self._calls[key] = {"id": str(raw_id or ""), "name": "", "args": ""}
                    self._order.append(key)
                state = self._calls[key]
                if raw_id:
                    state["id"] = str(raw_id)
                name = _value(raw, "name")
                if name:
                    state["name"] = str(name)
                args = _value(raw, "args", "")
                if isinstance(args, Mapping):
                    state["args"] = dict(args)
                elif args:
                    state["args"] = str(state.get("args", "")) + str(args)
            return
        for call in normalize_tool_calls(chunk):
            key = call.call_id
            if key not in self._calls:
                self._calls[key] = {"id": key, "name": call.name, "args": call.arguments}
                self._order.append(key)
            else:
                self._calls[key]["name"] = call.name
                self._calls[key]["args"] = call.arguments

    def finish(self) -> list[NormalizedToolCall]:
        result: list[NormalizedToolCall] = []
        for index, key in enumerate(self._order):
            state = self._calls[key]
            if not state.get("name"):
                continue
            result.append(
                NormalizedToolCall(
                    str(state.get("id") or f"tool-call-{index}"),
                    str(state["name"]),
                    _arguments(state.get("args", {})),
                )
            )
        return result


__all__ = [
    "NormalizedToolCall",
    "ToolCallAccumulator",
    "ToolingUnavailableError",
    "bind_tools",
    "normalize_tool_calls",
    "tool_spec_schema",
    "visible_text",
]
