"""Stable bounded seams for contextual data supplied to ChatContextBuilder."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBlock:
    key: str
    content: str
    priority: int
    max_tokens: int
    trusted: bool = False


__all__ = ["ContextBlock"]
