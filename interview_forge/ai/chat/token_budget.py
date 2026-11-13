"""Chat budget slots plus compatibility exports for unified estimation."""
from __future__ import annotations

from dataclasses import dataclass

from interview_forge.ai.token_counting import (
    DEFAULT_TOKEN_ESTIMATOR,
    ConservativeTokenEstimator,
    TokenEstimator,
    estimate_json_tokens,
    trim_text_to_tokens,
)


@dataclass(frozen=True)
class ChatTokenBudget:
    """Prompt slots; output is reserved separately from context slots."""

    summary_tokens: int = 1_200
    recent_tokens: int = 3_700
    system_tokens: int = 2_000
    untrusted_context_tokens: int = 1_800
    current_tokens: int = 800
    output_tokens: int = 1_200
    message_overhead_tokens: int = 4

    @property
    def context_tokens(self) -> int:
        return (
            self.summary_tokens + self.recent_tokens + self.system_tokens
            + self.untrusted_context_tokens + self.current_tokens
        )

    @property
    def max_prompt_tokens(self) -> int:
        return self.context_tokens + self.message_overhead_tokens * 4

    @property
    def max_request_tokens(self) -> int:
        return self.max_prompt_tokens + self.output_tokens


def budget_for_context_window(
    context_window: int | None,
    base: ChatTokenBudget | None = None,
) -> ChatTokenBudget:
    """Fit the configured prompt slots under a provider model's window.

    Unknown windows retain the historical budget.  For a known smaller model
    we reduce the flexible recent/context slots first and keep the system and
    current-user slots usable, so the caller gets a bounded request instead
    of a provider-side opaque context-length error.
    """
    base = base or ChatTokenBudget()
    try:
        window = int(context_window) if context_window is not None else 0
    except (TypeError, ValueError):
        window = 0
    if window <= 0 or base.max_request_tokens <= window:
        return base
    fixed = base.system_tokens + base.current_tokens + base.output_tokens + base.message_overhead_tokens * 4
    flexible = max(0, window - fixed)
    flexible_total = base.untrusted_context_tokens + base.recent_tokens + base.summary_tokens
    scale = min(1.0, flexible / max(1, flexible_total))
    untrusted = int(base.untrusted_context_tokens * scale)
    recent = int(base.recent_tokens * scale)
    summary = int(base.summary_tokens * scale)
    return ChatTokenBudget(
        summary_tokens=summary,
        recent_tokens=recent,
        system_tokens=base.system_tokens,
        untrusted_context_tokens=untrusted,
        current_tokens=base.current_tokens,
        output_tokens=base.output_tokens,
        message_overhead_tokens=base.message_overhead_tokens,
    )


DEFAULT_CHAT_TOKEN_BUDGET = ChatTokenBudget()


__all__ = [
    "DEFAULT_CHAT_TOKEN_BUDGET",
    "DEFAULT_TOKEN_ESTIMATOR",
    "ChatTokenBudget",
    "ConservativeTokenEstimator",
    "TokenEstimator",
    "budget_for_context_window",
    "estimate_json_tokens",
    "trim_text_to_tokens",
]
