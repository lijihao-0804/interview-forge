"""Resolve a business AI workload from managed config, falling back to ENV."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import AIConfig, load_ai_config
from .config_store import AIConfigStore, AISecretUnavailable, BusinessProfile
from .policy import ReasoningPolicy


@dataclass(frozen=True)
class ResolvedAIRuntime:
    config: AIConfig
    provider_id: str | None
    provider_name: str
    model: str
    protocol: str
    secret: str
    reasoning_policy: ReasoningPolicy
    business_key: str
    config_source: str
    capabilities: dict[str, Any]


def resolve_ai_runtime(business_key: str, *, daily_limit: int = 3, store: AIConfigStore | None = None) -> ResolvedAIRuntime:
    store = store or AIConfigStore()
    profile = store.get_profile(business_key)
    if profile is not None and profile.enabled:
        provider = store.get_provider(profile.provider_id)
        if provider is None or not provider.enabled:
            raise AISecretUnavailable("AI Provider 未启用或不存在")
        secret = store.provider_secret(provider.id)
        model = next((item for item in store.list_models(provider.id) if item.model_id == profile.model_id), None)
        capabilities = model.capabilities if model else {}
        policy = ReasoningPolicy(profile.reasoning_mode, profile.reasoning_effort, profile.reasoning_budget)
        config = AIConfig(
            enabled=True, provider={"anthropic_messages": "anthropic", "gemini": "gemini"}.get(provider.protocol, "openai" if provider.protocol == "openai_responses" else "openai-compatible"),
            model=profile.model_id, base_url=provider.base_url, api_key=secret,
            wire_api={"openai_responses": "responses", "anthropic_messages": "anthropic_messages", "gemini": "gemini"}.get(provider.protocol, "chat_completions"),
            actor_authorization="", reasoning_effort=profile.reasoning_effort or "",
            thinking_enabled=profile.reasoning_mode not in {"off", "auto"},
            request_timeout_seconds=45.0, max_concurrent_requests=2,
            daily_limit_per_user=daily_limit, beta_users="*",
            reasoning_mode=profile.reasoning_mode, reasoning_budget=profile.reasoning_budget,
        )
        return ResolvedAIRuntime(config, provider.id, provider.name, model.model_id if model else profile.model_id, provider.protocol, secret, policy, business_key, "db", capabilities)
    config = load_ai_config(daily_limit)
    policy = ReasoningPolicy("effort", config.reasoning_effort) if config.reasoning_effort else ReasoningPolicy("auto")
    return ResolvedAIRuntime(config, None, config.provider, config.model, config.wire_api, config.api_key, policy, business_key, "env", {})


__all__ = ["ResolvedAIRuntime", "resolve_ai_runtime"]
