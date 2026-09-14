"""Bounded, side-effect-free adapter for OpenAI-compatible /models endpoints."""
from __future__ import annotations

import json
import time
from urllib.parse import urljoin

import httpx

from interview_forge.ai.config_store import AIConfigError
from .base import ProviderAdapter, ProviderProbeResult
from .network import PinnedHTTPTransport


MAX_RESPONSE_BYTES = 1_000_000
MAX_MODELS = 200


def _read_limited(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        remaining = MAX_RESPONSE_BYTES + 1 - size
        if remaining <= 0:
            break
        data = bytes(chunk[:remaining])
        chunks.append(data)
        size += len(data)
        if size > MAX_RESPONSE_BYTES:
            break
    return b"".join(chunks)


def models_url(base_url: str, models_path: str = "/models") -> str:
    base = str(base_url).rstrip("/") + "/"
    path = str(models_path or "/models").lstrip("/")
    return urljoin(base, path)


class OpenAICompatibleAdapter(ProviderAdapter):
    def __init__(self, protocol: str | None = None):
        self.protocol = str(protocol or "openai_chat").strip().lower()

    def capability_contract(self):
        is_responses = self.protocol == "openai_responses"
        return {
            "streaming": True,
            "tools": True,
            "structured_output": True,
            # This is the adapter's wire capability, not a claim about every
            # model behind an OpenAI-compatible endpoint. The catalog/manual
            # model capability still has to opt reasoning in.
            "reasoning": True,
            "reasoning_modes": ["off", "auto", "effort"] if is_responses else ["off", "auto", "effort", "budget"],
            "reasoning_efforts": ["minimal", "low", "medium", "high", "xhigh", "max"],
            "reasoning_budget": not is_responses,
        }

    def apply_reasoning(self, config, policy=None, *, thinking_mode=None):
        mode = getattr(policy, "mode", None) or getattr(config, "reasoning_mode", "auto")
        effort = getattr(policy, "effort", None) or getattr(config, "reasoning_effort", "")
        budget = getattr(policy, "budget_tokens", None)
        if budget is None:
            budget = getattr(config, "reasoning_budget", None)
        if mode == "auto" and thinking_mode is None and not getattr(config, "thinking_enabled", False):
            return {}
        if mode == "off" or (mode == "auto" and thinking_mode == "disabled"):
            if str(getattr(config, "provider", "")).strip().lower() == "openai" and config.wire_api == "responses":
                return {"reasoning_effort": "none"}
            return {"extra_body": {"thinking": {"type": "disabled"}}}
        if mode == "budget" and budget is not None:
            return {"extra_body": {"thinking": {"type": "enabled", "budget_tokens": int(budget)}}}
        if mode == "effort" and effort:
            if config.wire_api == "responses":
                return {"reasoning_effort": effort}
            return {
                "reasoning_effort": effort,
                "extra_body": {"thinking": {"type": "enabled"}},
            }
        effective = thinking_mode
        if effective is None and getattr(config, "thinking_enabled", False):
            effective = "enabled"
        if effective is not None:
            return {"extra_body": {"thinking": {"type": effective}}}
        return {}

    def make_chat_model(self, config, *, thinking_mode=None):
        try:
            from langchain_openai import ChatOpenAI
        except (ImportError, ModuleNotFoundError) as exc:
            from interview_forge.ai.errors import AIServiceError
            raise AIServiceError("not_configured", "AI 分析依赖尚未安装。") from exc
        from interview_forge.ai.providers.chat_model import build_chat_model_kwargs
        kwargs = build_chat_model_kwargs(config, thinking_mode=thinking_mode)
        if config.wire_api not in {"anthropic_messages", "gemini"}:
            kwargs["stream_usage"] = True
        try:
            return ChatOpenAI(**kwargs)
        except Exception as exc:
            from interview_forge.ai.errors import AIServiceError
            raise AIServiceError("not_configured", "AI 服务配置不可用。") from exc

    def discover_models(self, *, base_url: str, models_path: str, api_key: str, timeout: float = 8.0) -> ProviderProbeResult:
        started = time.perf_counter()
        try:
            transport = PinnedHTTPTransport(base_url)
            with httpx.Client(timeout=httpx.Timeout(timeout), follow_redirects=False, trust_env=False, transport=transport, headers={"Authorization": f"Bearer {api_key}"} if api_key else {}) as client:
                url = models_url(base_url, models_path)
                if hasattr(client, "stream"):
                    with client.stream("GET", url) as response:
                        status_code = response.status_code
                        content = _read_limited(response)
                else:  # small compatibility seam for old test doubles
                    response = client.get(url)
                    status_code = response.status_code
                    content = response.content
                latency = round((time.perf_counter() - started) * 1000, 2)
                if status_code in {401, 403}: return ProviderProbeResult(False, "authentication", latency_ms=latency)
                if status_code >= 400: return ProviderProbeResult(False, "http_error", latency_ms=latency)
                if len(content) > MAX_RESPONSE_BYTES: return ProviderProbeResult(False, "response_too_large", latency_ms=latency)
                payload = json.loads(content.decode("utf-8"))
        except httpx.TimeoutException:
            return ProviderProbeResult(False, "timeout", latency_ms=round((time.perf_counter() - started) * 1000, 2))
        except AIConfigError:
            return ProviderProbeResult(False, "unsafe_network_target", latency_ms=round((time.perf_counter() - started) * 1000, 2))
        except (httpx.HTTPError, ValueError, json.JSONDecodeError):
            return ProviderProbeResult(False, "network_or_invalid_response", latency_ms=round((time.perf_counter() - started) * 1000, 2))
        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list): return ProviderProbeResult(False, "invalid_response", latency_ms=round((time.perf_counter() - started) * 1000, 2))
        model_ids = []
        for item in items[:MAX_MODELS]:
            value = item.get("id") if isinstance(item, dict) else None
            if isinstance(value, str) and 0 < len(value.strip()) <= 160 and all(ord(ch) >= 32 for ch in value):
                model_ids.append(value.strip())
        if not model_ids: return ProviderProbeResult(False, "no_valid_models", latency_ms=round((time.perf_counter() - started) * 1000, 2))
        return ProviderProbeResult(True, "ok", tuple(dict.fromkeys(model_ids)), latency_ms=round((time.perf_counter() - started) * 1000, 2))


__all__ = ["MAX_MODELS", "MAX_RESPONSE_BYTES", "OpenAICompatibleAdapter", "models_url"]
