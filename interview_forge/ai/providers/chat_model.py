"""Shared LangChain-compatible ChatModel construction options.

Business services only provide an AIConfig. Protocol-specific request options
are assembled here so future native adapters have one place to extend.
"""
from __future__ import annotations

from typing import Any

from interview_forge.ai.config import AIConfig


def build_chat_model_kwargs(config: AIConfig, *, thinking_mode: str | None = None) -> dict[str, Any]:
    if thinking_mode not in {None, "enabled", "disabled"}:
        raise ValueError("thinking_mode must be enabled, disabled, or None")
    kwargs: dict[str, Any] = {
        "model": config.model,
        "api_key": config.api_key,
        "timeout": config.request_timeout_seconds,
        "max_retries": 0,
    }
    if config.base_url:
        kwargs["base_url"] = config.base_url
    if config.wire_api == "responses":
        kwargs.update({"use_responses_api": True, "store": False, "output_version": "responses/v1"})
    if config.actor_authorization:
        kwargs["default_headers"] = {"x-openai-actor-authorization": config.actor_authorization}
    if config.reasoning_effort in {"low", "medium", "high"}:
        kwargs["reasoning_effort"] = config.reasoning_effort
    if config.reasoning_budget is not None:
        kwargs["extra_body"] = {"thinking": {"type": "enabled", "budget_tokens": int(config.reasoning_budget)}}
    effective_thinking_mode = thinking_mode
    if effective_thinking_mode is None and config.thinking_enabled:
        effective_thinking_mode = "enabled"
    if effective_thinking_mode is not None and config.reasoning_budget is None:
        kwargs["extra_body"] = {"thinking": {"type": effective_thinking_mode}}
    return kwargs


__all__ = ["build_chat_model_kwargs"]
