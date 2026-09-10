"""Configuration and capability-independent helpers for the AI coach.

This module contains only the existing process-environment configuration
boundary.  It intentionally keeps optional provider imports out of startup;
``ai_coach`` re-exports the public symbols for the legacy import path.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class AIConfig:
    enabled: bool
    provider: str
    model: str
    base_url: str
    api_key: str
    wire_api: str
    actor_authorization: str
    reasoning_effort: str
    thinking_enabled: bool
    request_timeout_seconds: float
    max_concurrent_requests: int
    daily_limit_per_user: int
    beta_users: str

    @property
    def configured(self) -> bool:
        return bool(
            self.provider in {"openai", "openai-compatible"}
            and self.model
            and self.api_key
        )


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


def load_ai_config(daily_limit: int = 3) -> AIConfig:
    """Read AI configuration only from the current process environment."""
    return AIConfig(
        enabled=_env_bool("AI_ENABLED", False),
        provider=os.environ.get("AI_PROVIDER", "").strip().lower(),
        model=os.environ.get("AI_MODEL", "").strip(),
        base_url=os.environ.get("AI_BASE_URL", "").strip(),
        api_key=os.environ.get("AI_API_KEY", ""),
        wire_api=os.environ.get("AI_WIRE_API", "chat_completions").strip().lower(),
        actor_authorization=os.environ.get("AI_ACTOR_AUTHORIZATION", "").strip(),
        reasoning_effort=os.environ.get("AI_REASONING_EFFORT", "").strip().lower(),
        thinking_enabled=_env_bool("AI_THINKING_ENABLED", False),
        request_timeout_seconds=_env_float(
            "AI_REQUEST_TIMEOUT_SECONDS", 45.0, 1.0, 120.0
        ),
        max_concurrent_requests=_env_int(
            "AI_MAX_CONCURRENT_REQUESTS", 2, 1, 8
        ),
        daily_limit_per_user=daily_limit,
        beta_users=os.environ.get("AI_BETA_USERS", "").strip(),
    )


def _beta_allows(beta_users: str, username: str) -> bool:
    values = {
        item.strip().lower()
        for item in re.split(r"[,;\s]+", beta_users)
        if item.strip()
    }
    if values.intersection({"*", "all", "everyone", "__all__"}):
        return True
    return bool(username and username.strip().lower() in values)


def _dependencies_available() -> bool:
    """Check optional packages without importing them during normal startup."""
    try:
        return all(
            importlib.util.find_spec(name) is not None
            for name in ("pydantic", "langchain_core", "langchain_openai")
        )
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def model_key(
    config: AIConfig | None = None,
    *,
    daily_limit: int = 3,
    loader: Callable[[int], AIConfig] | None = None,
) -> str:
    """Return a non-sensitive, stable model identifier for task deduplication."""
    if config is None:
        config = (loader or load_ai_config)(daily_limit)
    model_digest = hashlib.sha256(config.model.encode("utf-8")).hexdigest()[:16]
    endpoint_digest = (
        hashlib.sha256(config.base_url.encode("utf-8")).hexdigest()[:12]
        if config.base_url
        else "default"
    )
    provider = (
        config.provider
        if config.provider in {"openai", "openai-compatible"}
        else "unknown"
    )
    return f"{provider}:model-{model_digest}:endpoint-{endpoint_digest}"
