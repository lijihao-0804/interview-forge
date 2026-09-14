"""Lazy native provider adapters.

Optional SDKs are imported only when an administrator routes a workload to
the corresponding native protocol. Their absence never prevents base-site or
OpenAI-compatible startup.
"""
from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from interview_forge.ai.config import AIConfig
from interview_forge.ai.errors import AIServiceError
from interview_forge.ai.config_store import AIConfigError, validate_network_target
from .base import ProviderAdapter, ProviderProbeResult

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


def _bounded_models_response(status_code: int, content: bytes, *, key: str) -> tuple[bool, str, tuple[str, ...]]:
    if status_code in {401, 403}:
        return False, "authentication", ()
    if status_code >= 400:
        return False, "http_error", ()
    if len(content) > MAX_RESPONSE_BYTES:
        return False, "response_too_large", ()
    try:
        payload = json.loads(content.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return False, "invalid_response", ()
    values = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(values, list):
        return False, "invalid_response", ()
    result: list[str] = []
    for item in values[:MAX_MODELS]:
        value = item.get("id") if key == "data" and isinstance(item, dict) else item.get("name") if isinstance(item, dict) else None
        if isinstance(value, str):
            value = value.removeprefix("models/").strip()
            if 0 < len(value) <= 160 and all(ord(ch) >= 32 for ch in value):
                result.append(value)
    unique = tuple(dict.fromkeys(result))
    return (True, "ok", unique) if unique else (False, "no_valid_models", ())


class _NativeHTTPAdapter(ProviderAdapter):
    default_path = "/models"
    payload_key = "data"
    headers: dict[str, str] = {}

    def _request(self, *, base_url: str, models_path: str, api_key: str, timeout: float) -> ProviderProbeResult:
        started = time.perf_counter()
        url = urljoin(str(base_url).rstrip("/") + "/", str(models_path or self.default_path).lstrip("/"))
        try:
            validate_network_target(base_url)
            request_headers = dict(self.headers)
            if self.__class__.__name__ == "AnthropicAdapter" and api_key:
                request_headers["x-api-key"] = api_key
            params = {"key": api_key} if self.__class__.__name__ == "GeminiAdapter" and api_key else None
            with httpx.Client(timeout=httpx.Timeout(timeout), follow_redirects=False, headers=request_headers) as client:
                if hasattr(client, "stream"):
                    with client.stream("GET", url, params=params) as response:
                        status_code = response.status_code
                        content = _read_limited(response)
                else:
                    response = client.get(url, params=params)
                    status_code = response.status_code
                    content = response.content
            ok, category, model_ids = _bounded_models_response(status_code, content, key=self.payload_key)
            return ProviderProbeResult(ok, category, model_ids, round((time.perf_counter() - started) * 1000, 2))
        except AIConfigError:
            return ProviderProbeResult(False, "unsafe_network_target", latency_ms=round((time.perf_counter() - started) * 1000, 2))
        except httpx.TimeoutException:
            return ProviderProbeResult(False, "timeout", latency_ms=round((time.perf_counter() - started) * 1000, 2))
        except httpx.HTTPError:
            return ProviderProbeResult(False, "network_or_invalid_response", latency_ms=round((time.perf_counter() - started) * 1000, 2))

    def discover_models(self, *, base_url, models_path, api_key, timeout=8.0):
        return self._request(base_url=base_url, models_path=models_path, api_key=api_key, timeout=timeout)

    def test_connection(self, *, base_url, models_path, api_key, timeout=8.0):
        return self._request(base_url=base_url, models_path=models_path, api_key=api_key, timeout=timeout)

    def apply_reasoning(self, config, policy=None, *, thinking_mode=None):
        mode = getattr(policy, "mode", None) or getattr(config, "reasoning_mode", "auto")
        if mode != "auto" or thinking_mode is not None:
            raise AIServiceError("not_configured", "当前 Native Provider 不支持所选 reasoning 模式。")
        return {}


class AnthropicAdapter(_NativeHTTPAdapter):
    default_path = "/v1/models"
    payload_key = "data"
    headers = {"anthropic-version": "2023-06-01"}

    def make_chat_model(self, config, *, thinking_mode=None):
        try:
            from langchain_anthropic import ChatAnthropic
        except (ImportError, ModuleNotFoundError) as exc:
            raise AIServiceError("not_configured", "该 Native AI Provider 的依赖尚未安装。") from exc
        kwargs = {
            "model": config.model, "api_key": config.api_key,
            "timeout": config.request_timeout_seconds, "max_retries": 0,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        kwargs.update(self.apply_reasoning(config, thinking_mode=thinking_mode))
        try:
            return ChatAnthropic(**kwargs)
        except Exception as exc:
            raise AIServiceError("not_configured", "Anthropic Provider 配置不可用。") from exc


class GeminiAdapter(_NativeHTTPAdapter):
    default_path = "/v1beta/models"
    payload_key = "models"

    def make_chat_model(self, config, *, thinking_mode=None):
        default = "https://generativelanguage.googleapis.com"
        if config.base_url.rstrip("/") != default:
            raise AIServiceError("not_configured", "Gemini Native Provider 不支持当前自定义 Base URL。")
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except (ImportError, ModuleNotFoundError) as exc:
            raise AIServiceError("not_configured", "该 Native AI Provider 的依赖尚未安装。") from exc
        kwargs = {
            "model": config.model, "google_api_key": config.api_key,
            "timeout": config.request_timeout_seconds, "max_retries": 0,
        }
        kwargs.update(self.apply_reasoning(config, thinking_mode=thinking_mode))
        try:
            return ChatGoogleGenerativeAI(**kwargs)
        except Exception as exc:
            raise AIServiceError("not_configured", "Gemini Provider 配置不可用。") from exc


def make_native_chat_model(config: AIConfig) -> Any:
    return get_provider_adapter(config.wire_api).make_chat_model(config)


def get_provider_adapter(protocol: str) -> ProviderAdapter:
    value = str(protocol or "").strip().lower()
    if value in {"anthropic_messages", "anthropic"}:
        return AnthropicAdapter()
    if value == "gemini":
        return GeminiAdapter()
    raise AIServiceError("not_configured", "不支持的 Native AI Protocol。")


__all__ = ["AnthropicAdapter", "GeminiAdapter", "get_provider_adapter", "make_native_chat_model"]
