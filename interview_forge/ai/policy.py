"""Provider-neutral capability and reasoning policy validation."""
from __future__ import annotations

from dataclasses import dataclass
import re
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
    allowed_modes = caps.get("reasoning_modes")
    if isinstance(allowed_modes, list) and policy.mode not in allowed_modes:
        raise ValueError("该模型不支持所选 reasoning mode")
    if policy.mode == "off":
        if not isinstance(allowed_modes, list) or "off" not in allowed_modes:
            raise ValueError("该模型不支持关闭 reasoning")
        return
    if caps.get("reasoning") is not True:
        raise ValueError("该模型不支持 reasoning")
    if policy.mode == "budget" and caps.get("reasoning_budget") is not True:
        raise ValueError("该模型不支持 reasoning budget")
    if policy.mode == "effort":
        allowed = caps.get("reasoning_efforts")
        if isinstance(allowed, list) and policy.effort not in allowed:
            raise ValueError("该模型不支持所选 reasoning effort")


def capabilities_for_preset(*, protocol: str, reasoning_adapter: str = "none") -> dict[str, Any]:
    """Conservative defaults; adapters may opt into only known capabilities."""
    return {
        "streaming": protocol in {"openai_chat", "openai_responses", "anthropic_messages", "gemini"},
        "tools": protocol in {"openai_chat", "openai_responses", "anthropic_messages", "gemini"},
        "structured_output": protocol in {"openai_chat", "openai_responses"},
        "reasoning": reasoning_adapter in {"openai", "deepseek"},
        "reasoning_modes": ["auto", "off", "effort"] if reasoning_adapter in {"openai", "deepseek"} else ["auto"],
        "reasoning_efforts": ["minimal", "low", "medium", "high", "xhigh", "max"] if reasoning_adapter == "openai" else [],
        "reasoning_budget": False,
    }


def capabilities_for_model(*, vendor: str, protocol: str, model_id: str) -> dict[str, Any]:
    """Return conservative discovered capabilities for one known model family.

    Discovery itself only proves that a model appears in ``/models``.  It must
    not turn every model into a reasoning/tool-capable model.  The small
    registry below opts in only for model families whose request semantics are
    known by our adapters; administrators can still override the result.
    """
    caps = capabilities_for_preset(protocol=protocol, reasoning_adapter="none")
    caps.update({"reasoning": False, "reasoning_modes": ["auto"], "reasoning_efforts": []})
    vendor_key = str(vendor or "").strip().lower()
    model_key = str(model_id or "").strip().lower()
    if vendor_key == "openai" and re.match(r"^(gpt-5(?:\.\d+)?(?:[-_.].*)?|o[1-4](?:[-_.].*)?)$", model_key):
        caps["reasoning"] = True
        caps["reasoning_modes"] = ["auto", "off", "effort"]
        caps["reasoning_efforts"] = ["low", "medium", "high"] if model_key.startswith("o") else ["minimal", "low", "medium", "high"]
        if re.match(r"^gpt-5\.(?:[6-9]|\d{2,})", model_key) or "codex-max" in model_key:
            caps["reasoning_efforts"] += ["xhigh", "max"]
    elif vendor_key == "deepseek" and re.search(r"(?:reasoner|thinking|deepseek-r1|deepseek-v4)", model_key):
        caps["reasoning"] = True
        caps["reasoning_modes"] = ["auto", "off", "effort"]
        caps["reasoning_efforts"] = ["low", "medium", "high"]
    return caps


__all__ = ["REASONING_EFFORTS", "REASONING_MODES", "ReasoningPolicy", "capabilities_for_model", "capabilities_for_preset", "validate_reasoning_policy"]
