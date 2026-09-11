"""Reusable async upstream client for network-bound service adapters.

SQLite and deterministic analytics remain synchronous.  This client is only
for external HTTP calls and is created once in the FastAPI lifespan; callers
must not create one per request.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class AsyncUpstreamError(RuntimeError):
    """Sanitized upstream failure; response bodies are never exposed."""


class AsyncHttpClient:
    def __init__(self, *, timeout: float = 8.0, user_agent: str = "InterviewForge/1.0") -> None:
        self.timeout = float(timeout)
        self.user_agent = user_agent
        self._client: Any = None

    async def start(self) -> "AsyncHttpClient":
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                follow_redirects=False,
            )
        return self

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        if self._client is None:
            await self.start()
        try:
            response = await self._client.get(url, params=dict(params or {}), headers=dict(headers or {}))
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - sanitize all upstream details
            raise AsyncUpstreamError("上游服务暂时不可用") from exc
        if not isinstance(payload, dict):
            raise AsyncUpstreamError("上游服务返回格式不正确")
        return payload

