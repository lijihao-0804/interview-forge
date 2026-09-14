"""Lazy native provider adapters.

Optional SDKs are imported only when an administrator routes a workload to
the corresponding native protocol. Their absence never prevents base-site or
OpenAI-compatible startup.
"""
from __future__ import annotations

from typing import Any

from interview_forge.ai.config import AIConfig
from interview_forge.ai.errors import AIServiceError


def make_native_chat_model(config: AIConfig) -> Any:
    try:
        if config.wire_api == "anthropic_messages":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=config.model, api_key=config.api_key, timeout=config.request_timeout_seconds, max_retries=0)
        if config.wire_api == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=config.model, google_api_key=config.api_key, timeout=config.request_timeout_seconds, max_retries=0)
    except (ImportError, ModuleNotFoundError) as exc:
        raise AIServiceError("not_configured", "该 Native AI Provider 的依赖尚未安装。") from exc
    raise AIServiceError("not_configured", "不支持的 Native AI Protocol。")


__all__ = ["make_native_chat_model"]
