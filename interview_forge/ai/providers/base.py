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
    ttft_ms: float | None = None
    streaming: bool = False


class ProviderAdapter:
    def capability_contract(self) -> dict[str, Any]:
        """Capabilities this adapter can express on its wire protocol."""
        return {
            "streaming": False,
            "tools": False,
            "structured_output": False,
            "reasoning": False,
            "reasoning_modes": ["auto"],
            "reasoning_efforts": [],
            "reasoning_budget": False,
        }

    def discover_models(self, *, base_url: str, models_path: str, api_key: str, timeout: float = 8.0) -> ProviderProbeResult:
        raise NotImplementedError

    def test_connection(self, *, base_url: str, models_path: str, api_key: str, timeout: float = 8.0) -> ProviderProbeResult:
        """Run the protocol's least-invasive connection check."""
        return self.discover_models(
            base_url=base_url, models_path=models_path, api_key=api_key, timeout=timeout
        )

    def test_model(self, *, base_url: str, model_id: str, api_key: str, timeout: float = 12.0) -> ProviderProbeResult:
        """Run a minimal, explicit generation probe for one model."""
        return ProviderProbeResult(False, "not_supported")

    def make_chat_model(self, config: Any, *, thinking_mode: str | None = None) -> Any:
        raise NotImplementedError

    def apply_reasoning(self, config: Any, policy: Any = None, *, thinking_mode: str | None = None) -> dict[str, Any]:
        """Translate a provider-neutral policy into protocol kwargs."""
        return {}


__all__ = ["ProviderAdapter", "ProviderProbeResult"]
