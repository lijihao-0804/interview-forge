"""Provider presets and safe management adapters."""

from .presets import PROVIDER_PRESETS, ProviderPreset, get_provider_preset
from .base import ProviderAdapter
from .native import AnthropicAdapter, GeminiAdapter
from .openai_compatible import OpenAICompatibleAdapter


def get_provider_adapter(protocol: str) -> ProviderAdapter:
    value = str(protocol or "").strip().lower()
    if value in {"openai_chat", "openai_responses", "chat_completions", "responses"}:
        normalized = {"chat_completions": "openai_chat", "responses": "openai_responses"}.get(value, value)
        return OpenAICompatibleAdapter(normalized)
    if value == "anthropic_messages":
        return AnthropicAdapter()
    if value == "gemini":
        return GeminiAdapter()
    raise ValueError("不支持的 Provider Protocol")

__all__ = ["PROVIDER_PRESETS", "ProviderPreset", "ProviderAdapter", "OpenAICompatibleAdapter", "AnthropicAdapter", "GeminiAdapter", "get_provider_adapter", "get_provider_preset"]
