"""Central limits for one model turn's tool execution."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolPolicy:
    max_rounds: int = 3
    max_calls_per_turn: int = 6
    max_parallel_read_tools: int = 3
    max_total_result_tokens: int = 3500
    max_identical_calls: int = 2

    def __post_init__(self) -> None:
        if any(
            value <= 0
            for value in (
                self.max_rounds,
                self.max_calls_per_turn,
                self.max_parallel_read_tools,
                self.max_total_result_tokens,
                self.max_identical_calls,
            )
        ):
            raise ValueError("tool policy limits must be positive")
