"""Stable bounded seams for contextual data supplied to ChatContextBuilder."""
from __future__ import annotations

from dataclasses import dataclass

from interview_forge.ai.token_counting import TokenEstimator, trim_text_to_tokens


@dataclass(frozen=True)
class ContextBlock:
    key: str
    content: str
    priority: int
    max_tokens: int
    trusted: bool = False

    # Smaller, self-contained alternatives in descending detail. In particular
    # an alternative can omit a whole record, never half of a JSON object.
    alternatives: tuple[str, ...] | None = None

    def fit(self, limit: int, estimator: TokenEstimator) -> str:
        if self.alternatives is None:
            return trim_text_to_tokens(self.content, limit, estimator)
        for candidate in (self.content, *self.alternatives):
            if candidate and estimator.estimate_text(candidate) <= limit:
                return candidate
        return ""


__all__ = ["ContextBlock"]
