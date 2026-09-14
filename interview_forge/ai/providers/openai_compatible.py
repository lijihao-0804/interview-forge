"""Bounded, side-effect-free adapter for OpenAI-compatible /models endpoints."""
from __future__ import annotations

import json
import time
from urllib.parse import urljoin

import httpx

from .base import ProviderAdapter, ProviderProbeResult


MAX_RESPONSE_BYTES = 1_000_000
MAX_MODELS = 200


def models_url(base_url: str, models_path: str = "/models") -> str:
    base = str(base_url).rstrip("/") + "/"
    path = str(models_path or "/models").lstrip("/")
    return urljoin(base, path)


class OpenAICompatibleAdapter(ProviderAdapter):
    def discover_models(self, *, base_url: str, models_path: str, api_key: str, timeout: float = 8.0) -> ProviderProbeResult:
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout), follow_redirects=False, headers={"Authorization": f"Bearer {api_key}"} if api_key else {}) as client:
                response = client.get(models_url(base_url, models_path))
                latency = round((time.perf_counter() - started) * 1000, 2)
                if response.status_code in {401, 403}: return ProviderProbeResult(False, "authentication", latency_ms=latency)
                if response.status_code >= 400: return ProviderProbeResult(False, "http_error", latency_ms=latency)
                if len(response.content) > MAX_RESPONSE_BYTES: return ProviderProbeResult(False, "response_too_large", latency_ms=latency)
                payload = response.json()
        except httpx.TimeoutException:
            return ProviderProbeResult(False, "timeout", latency_ms=round((time.perf_counter() - started) * 1000, 2))
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
