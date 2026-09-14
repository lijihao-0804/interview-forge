"""Authoritative model capability resolution.

Availability comes from a Provider's ``/models`` endpoint.  Capabilities come
from a versioned, reviewed manifest, a provider-declared capability payload,
or an explicit administrator override.  Model names are never interpreted by
heuristic rules here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


_MANIFEST_DIR = Path(__file__).with_name("manifests")
_CAPABILITY_KEYS = (
    "streaming",
    "tools",
    "structured_output",
    "reasoning",
    "reasoning_modes",
    "reasoning_efforts",
    "reasoning_budget",
)
_REASONING_MODES = ("off", "auto", "effort", "budget")


CAPABILITY_PROFILES: dict[str, dict[str, str]] = {
    "openai_official": {
        "display_name": "OpenAI Official",
        "description": "OpenAI 官方能力目录；只对目录中明确登记的模型生效。",
    },
    "deepseek_official": {
        "display_name": "DeepSeek Official",
        "description": "DeepSeek 官方能力目录；仅适用于完整透传官方参数的 Provider。",
    },
    "anthropic_official": {
        "display_name": "Anthropic Official",
        "description": "Anthropic 官方能力目录；只对目录中明确登记的模型生效。",
    },
    "gemini_official": {
        "display_name": "Gemini Official",
        "description": "Gemini 官方能力目录；只对目录中明确登记的模型生效。",
    },
    "generic_openai_compatible": {
        "display_name": "Generic OpenAI Compatible",
        "description": "兼容协议基线；不会继承任何厂商的特殊能力。",
    },
    "manual": {
        "display_name": "Manual",
        "description": "不使用官方目录，能力仅来自管理员明确覆盖。",
    },
}


@dataclass(frozen=True)
class CapabilityResolution:
    capabilities: dict[str, Any]
    source: str
    profile: str
    canonical_model: str | None = None
    verified_at: str | None = None
    catalog_version: str | None = None
    status: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "capabilities": dict(self.capabilities),
            "capability_source": self.source,
            "capability_profile": self.profile,
            "canonical_model": self.canonical_model,
            "capability_verified_at": self.verified_at,
            "capability_catalog_version": self.catalog_version,
            "status": self.status,
        }


def get_capability_profiles() -> list[dict[str, str]]:
    return [
        {"key": key, **value}
        for key, value in CAPABILITY_PROFILES.items()
    ]


def _load_manifest(profile: str) -> dict[str, Any]:
    path = _MANIFEST_DIR / f"{profile}.json"
    if not path.is_file():
        return {"profile": profile, "models": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"profile": profile, "models": {}}
    return payload if isinstance(payload, dict) else {"profile": profile, "models": {}}


def _protocol_baseline(protocol: str) -> dict[str, Any]:
    """Conservative baseline shared with the protocol adapters."""
    value = str(protocol or "").strip().lower()
    if value in {"openai_chat", "openai_responses"}:
        return {
            "streaming": True,
            "tools": True,
            "structured_output": True,
            "reasoning": False,
            "reasoning_modes": ["auto"],
            "reasoning_efforts": [],
            "reasoning_budget": False,
        }
    if value == "anthropic_messages":
        return {
            "streaming": True,
            "tools": True,
            "structured_output": False,
            "reasoning": False,
            "reasoning_modes": ["auto"],
            "reasoning_efforts": [],
            "reasoning_budget": False,
        }
    if value == "gemini":
        return {
            "streaming": True,
            "tools": True,
            "structured_output": True,
            "reasoning": False,
            "reasoning_modes": ["auto"],
            "reasoning_efforts": [],
            "reasoning_budget": False,
        }
    return {
        "streaming": False,
        "tools": False,
        "structured_output": False,
        "reasoning": False,
        "reasoning_modes": ["auto"],
        "reasoning_efforts": [],
        "reasoning_budget": False,
    }


def protocol_capabilities(protocol: str) -> dict[str, Any]:
    """Return the conservative capability baseline for a wire protocol."""
    return _protocol_baseline(protocol)


def _normalize_capabilities(value: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(value or {})
    result = _protocol_baseline("")
    for key in _CAPABILITY_KEYS:
        if key in raw:
            result[key] = raw[key]
    result["streaming"] = bool(result["streaming"])
    result["tools"] = bool(result["tools"])
    result["structured_output"] = bool(result["structured_output"])
    result["reasoning"] = bool(result["reasoning"])
    modes = result.get("reasoning_modes")
    result["reasoning_modes"] = [item for item in _REASONING_MODES if isinstance(modes, list) and item in modes]
    if "auto" not in result["reasoning_modes"]:
        result["reasoning_modes"].insert(0, "auto")
    efforts = result.get("reasoning_efforts")
    result["reasoning_efforts"] = list(dict.fromkeys(item for item in efforts if isinstance(item, str))) if isinstance(efforts, list) else []
    result["reasoning_budget"] = bool(result["reasoning_budget"])
    if not result["reasoning"]:
        result["reasoning_modes"] = ["auto"]
        result["reasoning_efforts"] = []
        result["reasoning_budget"] = False
    return result


def _intersect(model_caps: Mapping[str, Any], protocol_caps: Mapping[str, Any]) -> dict[str, Any]:
    result = _normalize_capabilities(model_caps)
    protocol = _normalize_capabilities(protocol_caps)
    for key in ("streaming", "tools", "structured_output"):
        result[key] = bool(result[key] and protocol[key])
    result["reasoning"] = bool(result["reasoning"] and protocol["reasoning"])
    result["reasoning_modes"] = [mode for mode in result["reasoning_modes"] if mode in protocol["reasoning_modes"]]
    if "auto" not in result["reasoning_modes"]:
        result["reasoning_modes"].insert(0, "auto")
    result["reasoning_efforts"] = [effort for effort in result["reasoning_efforts"] if effort in protocol["reasoning_efforts"]]
    result["reasoning_budget"] = bool(result["reasoning_budget"] and protocol["reasoning_budget"])
    if not result["reasoning"]:
        result["reasoning_modes"] = ["auto"]
        result["reasoning_efforts"] = []
        result["reasoning_budget"] = False
    return result


def resolve_model_capabilities(
    *,
    capability_profile: str,
    protocol: str,
    model_id: str,
    manual_capabilities: Mapping[str, Any] | None = None,
    capability_source: str | None = None,
    provider_capabilities: Mapping[str, Any] | None = None,
    adapter_capabilities: Mapping[str, Any] | None = None,
) -> CapabilityResolution:
    """Resolve one model using explicit source precedence.

    Manual override > provider-declared capability > official exact catalog >
    protocol baseline > conservative unknown.  ``adapter_capabilities`` is
    intersected last so a model cannot claim a mode the wire adapter cannot
    express.
    """
    profile = str(capability_profile or "generic_openai_compatible").strip().lower()
    adapter = _normalize_capabilities(adapter_capabilities or _protocol_baseline(protocol))
    if capability_source == "manual" and manual_capabilities is not None:
        resolved = _intersect(manual_capabilities, adapter)
        return CapabilityResolution(resolved, "manual", profile)
    if capability_source == "provider" and provider_capabilities is not None:
        resolved = _intersect(provider_capabilities, adapter)
        return CapabilityResolution(resolved, "provider", profile)

    manifest = _load_manifest(profile)
    models = manifest.get("models") if isinstance(manifest.get("models"), dict) else {}
    entry = models.get(str(model_id))
    if isinstance(entry, dict):
        canonical = entry.get("canonical_model")
        canonical_entry = models.get(canonical) if canonical else None
        source_caps = entry.get("capabilities") if isinstance(entry.get("capabilities"), dict) else None
        if source_caps is None and isinstance(canonical_entry, dict):
            source_caps = canonical_entry.get("capabilities") if isinstance(canonical_entry.get("capabilities"), dict) else None
        protocol_caps = None
        by_protocol = entry.get("protocols")
        if isinstance(by_protocol, dict) and isinstance(by_protocol.get(protocol), dict):
            protocol_caps = by_protocol[protocol]
        if protocol_caps is None and isinstance(canonical_entry, dict):
            canonical_protocols = canonical_entry.get("protocols")
            if isinstance(canonical_protocols, dict) and isinstance(canonical_protocols.get(protocol), dict):
                protocol_caps = canonical_protocols[protocol]
        if source_caps is not None:
            resolved = _intersect(protocol_caps or source_caps, adapter)
            return CapabilityResolution(
                resolved,
                "official_catalog",
                profile,
                str(canonical) if canonical else None,
                str(manifest.get("verified_at") or "") or None,
                str(manifest.get("catalog_version") or "") or None,
                str(entry.get("status") or "") or None,
            )

    # Unknown model: retain protocol baseline for known transport features,
    # but never infer explicit reasoning support.
    return CapabilityResolution(_intersect(_protocol_baseline(protocol), adapter), "unknown", profile)


__all__ = ["CAPABILITY_PROFILES", "CapabilityResolution", "get_capability_profiles", "protocol_capabilities", "resolve_model_capabilities"]
