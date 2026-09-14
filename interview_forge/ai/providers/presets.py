"""Central provider preset registry; business code consumes protocol metadata."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderPreset:
    key: str
    vendor: str
    display_name: str
    protocol: str
    default_base_url: str
    models_path: str = "/models"
    reasoning_adapter: str = "none"


_PRESETS = [
    ProviderPreset("openai", "openai", "OpenAI", "openai_responses", "https://api.openai.com/v1", reasoning_adapter="openai"),
    ProviderPreset("deepseek", "deepseek", "DeepSeek", "openai_chat", "https://api.deepseek.com", reasoning_adapter="deepseek"),
    ProviderPreset("openrouter", "openrouter", "OpenRouter", "openai_chat", "https://openrouter.ai/api/v1"),
    ProviderPreset("siliconflow", "siliconflow", "SiliconFlow", "openai_chat", "https://api.siliconflow.cn/v1"),
    ProviderPreset("kimi", "kimi", "Kimi", "openai_chat", "https://api.moonshot.cn/v1"),
    ProviderPreset("qwen-compatible", "qwen", "Qwen-compatible", "openai_chat", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ProviderPreset("glm-compatible", "glm", "GLM-compatible", "openai_chat", "https://open.bigmodel.cn/api/paas/v4"),
    ProviderPreset("new-api", "new-api", "New API", "openai_chat", "http://127.0.0.1:3000/v1"),
    ProviderPreset("sub2api", "sub2api", "Sub2API", "openai_chat", "http://127.0.0.1:3000/v1"),
    ProviderPreset("custom-openai-compatible", "custom", "Custom OpenAI-compatible", "openai_chat", ""),
    ProviderPreset("anthropic", "anthropic", "Anthropic", "anthropic_messages", "https://api.anthropic.com", models_path="/v1/models", reasoning_adapter="none"),
    ProviderPreset("gemini", "google", "Gemini", "gemini", "https://generativelanguage.googleapis.com", models_path="/v1beta/models", reasoning_adapter="none"),
]

PROVIDER_PRESETS = {item.key: item for item in _PRESETS}


def get_provider_preset(key: str) -> ProviderPreset | None:
    return PROVIDER_PRESETS.get(str(key or "").strip().lower())


__all__ = ["PROVIDER_PRESETS", "ProviderPreset", "get_provider_preset"]
