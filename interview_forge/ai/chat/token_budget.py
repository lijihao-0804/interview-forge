"""Centralized token estimation and bounded chat-context budgets."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol, Sequence


class TokenEstimator(Protocol):
    """Replaceable estimator contract used by ContextBuilder."""

    def estimate_text(self, text: str) -> int:
        ...

    def estimate_messages(self, messages: Sequence[dict[str, Any]]) -> int:
        ...


@dataclass(frozen=True)
class ChatTokenBudget:
    """Prompt slots; output is reserved separately from context slots."""

    summary_tokens: int = 1_200
    recent_tokens: int = 5_000
    system_tokens: int = 700
    current_tokens: int = 800
    output_tokens: int = 1_200
    message_overhead_tokens: int = 4

    @property
    def context_tokens(self) -> int:
        return self.summary_tokens + self.recent_tokens + self.system_tokens + self.current_tokens

    @property
    def max_prompt_tokens(self) -> int:
        return self.context_tokens + self.message_overhead_tokens * 4

    @property
    def max_request_tokens(self) -> int:
        return self.max_prompt_tokens + self.output_tokens


DEFAULT_CHAT_TOKEN_BUDGET = ChatTokenBudget()


class ConservativeTokenEstimator:
    """Tokenizer-free fallback that intentionally overestimates text size."""

    name = "conservative-character-fallback"
    chars_per_token = 3

    def estimate_text(self, text: str) -> int:
        value = str(text or "")
        return max(1, math.ceil(len(value) / self.chars_per_token)) if value else 0

    def estimate_messages(self, messages: Sequence[dict[str, Any]]) -> int:
        total = 0
        for message in messages:
            total += self.estimate_text(str(message.get("content", "")))
            total += 4
        return total


DEFAULT_TOKEN_ESTIMATOR: TokenEstimator = ConservativeTokenEstimator()


def trim_text_to_tokens(text: str, max_tokens: int, estimator: TokenEstimator) -> str:
    """Clip text by the configured estimator without scattering token math."""
    value = str(text or "")
    if max_tokens <= 0:
        return ""
    if estimator.estimate_text(value) <= max_tokens:
        return value
    suffix = "…"
    content_budget = max(1, max_tokens - estimator.estimate_text(suffix))
    low, high = 0, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        if estimator.estimate_text(value[:middle]) <= content_budget:
            low = middle
        else:
            high = middle - 1
    clipped = value[:low].rstrip()
    return clipped + suffix if clipped else ""


__all__ = [
    "ChatTokenBudget",
    "DEFAULT_CHAT_TOKEN_BUDGET",
    "DEFAULT_TOKEN_ESTIMATOR",
    "ConservativeTokenEstimator",
    "TokenEstimator",
    "trim_text_to_tokens",
]
