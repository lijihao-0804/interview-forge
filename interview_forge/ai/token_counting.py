"""Deterministic token estimates shared by chat context and tool execution.

The estimator is intentionally tokenizer-free.  It is reproducible offline and
keeps the multilingual weighting used by the chat context builder, while JSON
helpers make tool calls, schemas, and result envelopes participate in the same
accounting rather than being hidden behind message ``content`` only.
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import is_dataclass
from enum import Enum
from typing import Any, Protocol


class TokenEstimator(Protocol):
    """Replaceable estimator contract used by chat and tool callers."""

    def estimate_text(self, text: str) -> int:
        ...

    def estimate_messages(self, messages: Sequence[Any]) -> int:
        ...


class ConservativeTokenEstimator:
    """Tokenizer-free estimate weighted for multilingual text.

    Chinese cannot use the Latin characters-per-token ratio.  This remains an
    estimate; provider token usage is the authoritative measurement.
    """

    name = "multilingual-character-fallback-v2"
    chars_per_token = 3

    def estimate_text(self, text: str) -> int:
        value = str(text or "")
        non_ascii = sum(ord(char) > 127 for char in value)
        return math.ceil(
            non_ascii * 1.5 + (len(value) - non_ascii) / self.chars_per_token
        )

    def estimate(self, text: str) -> int:
        """Compatibility with provider-neutral estimator protocols."""
        return self.estimate_text(text)

    def estimate_messages(self, messages: Sequence[Any]) -> int:
        # Four tokens cover the role/message envelope when a caller has already
        # supplied provider-neutral dictionaries. JSON fields such as tool_calls
        # and a tool observation's content remain in the counted value.
        return sum(
            estimate_json_tokens(message, estimator=self) + 4
            for message in messages
        )


DEFAULT_TOKEN_ESTIMATOR: TokenEstimator = ConservativeTokenEstimator()


def _json_safe(value: Any) -> Any:
    """Convert supported values to deterministic JSON without mutating them."""
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("JSON token counting requires finite numbers")
        return value
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise TypeError("JSON token counting requires string object keys")
            result[raw_key] = _json_safe(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_json_safe(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        )
    if is_dataclass(value) and not isinstance(value, type):
        from dataclasses import asdict

        return _json_safe(asdict(value))

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump(mode="json")
        except TypeError:
            dumped = model_dump()
        return _json_safe(dumped)

    model_json_schema = getattr(value, "model_json_schema", None)
    if callable(model_json_schema):
        return _json_safe(model_json_schema())

    raise TypeError(f"unsupported value for JSON token counting: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Return the stable JSON representation used for estimates and hashes."""
    return json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def estimate_text_tokens(text: str, estimator: Any = None) -> int:
    """Estimate text through a project or provider-neutral estimator."""
    counter = estimator or DEFAULT_TOKEN_ESTIMATOR
    method = getattr(counter, "estimate_text", None)
    if not callable(method):
        method = getattr(counter, "estimate", None)
    if not callable(method):
        raise TypeError("estimator must provide estimate_text(text) or estimate(text)")
    result = method(str(text or ""))
    if isinstance(result, bool) or not isinstance(result, int) or result < 0:
        raise ValueError("token estimator must return a non-negative integer")
    return result


def estimate_json_tokens(value: Any, estimator: Any = None) -> int:
    """Estimate one complete canonical JSON value, including all its fields."""
    return estimate_text_tokens(canonical_json(value), estimator=estimator)


def trim_text_to_tokens(text: str, max_tokens: int, estimator: Any = None) -> str:
    """Clip text by the configured estimator without scattering token math."""
    value = str(text or "")
    counter = estimator or DEFAULT_TOKEN_ESTIMATOR
    if max_tokens <= 0:
        return ""
    if estimate_text_tokens(value, counter) <= max_tokens:
        return value
    suffix = "…"
    suffix_cost = estimate_text_tokens(suffix, counter)
    if suffix_cost <= max_tokens:
        # Search against the complete candidate, not an independently rounded
        # character budget. This accounts for how multilingual character and
        # punctuation costs interact after the final ceil operation.
        low, high = 0, len(value)
        while low < high:
            middle = (low + high + 1) // 2
            if estimate_text_tokens(value[:middle] + suffix, counter) <= max_tokens:
                low = middle
            else:
                high = middle - 1
        clipped = value[:low].rstrip()
        if clipped:
            candidate = clipped + suffix
            if estimate_text_tokens(candidate, counter) <= max_tokens:
                return candidate
        # At a tiny budget, a truncation marker can still be the only content
        # that fits when no source prefix does.
        return suffix

    # No room for the marker itself: return the longest safe marker-free prefix.
    low, high = 0, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        if estimate_text_tokens(value[:middle], counter) <= max_tokens:
            low = middle
        else:
            high = middle - 1
    clipped = value[:low].rstrip()
    return clipped if estimate_text_tokens(clipped, counter) <= max_tokens else ""


__all__ = [
    "DEFAULT_TOKEN_ESTIMATOR",
    "ConservativeTokenEstimator",
    "TokenEstimator",
    "canonical_json",
    "estimate_json_tokens",
    "estimate_text_tokens",
    "trim_text_to_tokens",
]
