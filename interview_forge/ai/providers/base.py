"""Provider management adapter contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderProbeResult:
    ok: bool
    category: str
    model_ids: tuple[str, ...] = ()
    latency_ms: float | None = None


class ProviderAdapter:
    def discover_models(self, *, base_url: str, models_path: str, api_key: str, timeout: float = 8.0) -> ProviderProbeResult:
        raise NotImplementedError


__all__ = ["ProviderAdapter", "ProviderProbeResult"]
