"""Provider-neutral capability and reasoning policy validation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


REASONING_MODES = {"off", "auto", "effort", "budget"}
REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh", "max"}


@dataclass(frozen=True)
class ReasoningPolicy:
    mode: str = "auto"
    effort: str | None = None
    budget_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.effort is not None:
            object.__setattr__(self, "effort", str(self.effort).lower())
        if self.budget_tokens is not None:
            try:
                object.__setattr__(self, "budget_tokens", int(self.budget_tokens))
            except (TypeError, ValueError) as exc:
                raise ValueError("reasoning budget 必须是整数") from exc
        if self.mode not in REASONING_MODES:
            raise ValueError("不支持的 reasoning mode")
        if self.effort is not None and self.effort not in REASONING_EFFORTS:
            raise ValueError("不支持的 reasoning effort")
        if self.budget_tokens is not None and not 1 <= self.budget_tokens <= 200_000:
            raise ValueError("reasoning budget 超出范围")
        if self.mode == "effort" and not self.effort:
            raise ValueError("effort mode 需要指定 effort")
        if self.mode == "budget" and self.budget_tokens is None:
            raise ValueError("budget mode 需要指定 token budget")
        if self.mode != "effort" and self.effort is not None:
            raise ValueError("只有 effort mode 可以指定 reasoning effort")
        if self.mode != "budget" and self.budget_tokens is not None:
            raise ValueError("只有 budget mode 可以指定 token budget")


def validate_reasoning_policy(policy: ReasoningPolicy, capabilities: Mapping[str, Any] | None = None) -> None:
    caps = dict(capabilities or {})
    if policy.mode == "auto":
        return
    if caps.get("reasoning") is not True:
        raise ValueError("该模型不支持 reasoning")
    if policy.mode == "budget" and caps.get("reasoning_budget") is False:
        raise ValueError("该模型不支持 reasoning budget")
    if policy.mode == "effort":
        allowed = caps.get("reasoning_efforts")
        if isinstance(allowed, list) and policy.effort not in allowed:
            raise ValueError("该模型不支持所选 reasoning effort")


def capabilities_for_preset(*, protocol: str, reasoning_adapter: str = "none") -> dict[str, Any]:
    """Conservative defaults; adapters may opt into only known capabilities."""
    return {
        "streaming": protocol in {"openai_chat", "openai_responses"},
        "tools": protocol in {"openai_chat", "openai_responses"},
        "structured_output": protocol in {"openai_chat", "openai_responses"},
        "reasoning": reasoning_adapter in {"openai", "deepseek"},
        "reasoning_modes": ["auto", "off", "effort"] if reasoning_adapter in {"openai", "deepseek"} else ["auto"],
        "reasoning_efforts": ["minimal", "low", "medium", "high"] if reasoning_adapter == "openai" else [],
    }


__all__ = ["REASONING_EFFORTS", "REASONING_MODES", "ReasoningPolicy", "capabilities_for_preset", "validate_reasoning_policy"]
