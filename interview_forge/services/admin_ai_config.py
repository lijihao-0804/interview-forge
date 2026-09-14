"""Admin operations for managed AI provider/model/business configuration."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from interview_forge.ai.config_store import AIConfigStore, BusinessProfile, SUPPORTED_BUSINESS_KEYS, network_scope
from interview_forge.ai.policy import ReasoningPolicy, capabilities_for_model, capabilities_for_preset, validate_reasoning_policy
from interview_forge.ai.providers import PROVIDER_PRESETS, get_provider_adapter


def _store() -> AIConfigStore:
    return AIConfigStore()


def _provider(value: Any) -> dict[str, Any]:
    item = asdict(value)
    item["key_configured"] = bool(item.pop("key_configured", False))
    item["network_scope"] = network_scope(item.get("base_url", ""))
    return item


def provider_presets() -> dict[str, Any]:
    return {"items": [
        {**asdict(item), "capabilities": capabilities_for_preset(
            protocol=item.protocol, reasoning_adapter=item.reasoning_adapter
        )}
        for item in PROVIDER_PRESETS.values()
    ]}


def providers() -> dict[str, Any]:
    store = _store()
    return {"items": [_provider(item) for item in store.list_providers()]}


def create_provider(payload: Mapping[str, Any]) -> dict[str, Any]:
    store = _store()
    item = store.create_provider(
        name=str(payload.get("name", "")), vendor=str(payload.get("vendor", "")),
        protocol=str(payload.get("protocol", "")), base_url=str(payload.get("base_url", "")),
        api_key=str(payload.get("api_key", "")), enabled=bool(payload.get("enabled", True)),
        models_path=str(payload.get("models_path", "/models")),
    )
    return _provider(item)


def update_provider(provider_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"name", "vendor", "protocol", "base_url", "api_key", "clear_api_key", "enabled", "models_path"}
    unknown = set(payload) - allowed
    if unknown: raise ValueError("存在不支持的 Provider 字段")
    item = _store().update_provider(provider_id, **dict(payload))
    return _provider(item)


def delete_provider(provider_id: str) -> dict[str, Any]:
    _store().delete_provider(provider_id)
    return {"deleted": True}


def provider_models(provider_id: str) -> dict[str, Any]:
    store = _store()
    if store.get_provider(provider_id) is None: raise LookupError("Provider 不存在")
    return {"items": [asdict(item) for item in store.list_models(provider_id)]}


def add_model(provider_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if _store().get_provider(provider_id) is None: raise LookupError("Provider 不存在")
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict): capabilities = {}
    item = _store().upsert_model(provider_id=provider_id, model_id=str(payload.get("model_id", "")), display_name=str(payload.get("display_name", "")) or None, capabilities=capabilities, capability_source="manual", enabled=bool(payload.get("enabled", True)))
    return asdict(item)


def update_model(provider_id: str, model_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"enabled", "display_name", "capabilities"}
    unknown = set(payload) - allowed
    if unknown: raise ValueError("存在不支持的模型字段")
    capabilities = payload.get("capabilities")
    if capabilities is not None and not isinstance(capabilities, dict):
        raise ValueError("capabilities 必须是对象")
    item = _store().update_model(
        provider_id=provider_id,
        model_id=model_id,
        enabled=payload.get("enabled") if "enabled" in payload else None,
        display_name=payload.get("display_name") if "display_name" in payload else None,
        capabilities=capabilities,
    )
    return asdict(item)


def test_provider(provider_id: str) -> dict[str, Any]:
    store = _store(); provider = store.get_provider(provider_id)
    if provider is None: raise LookupError("Provider 不存在")
    secret = store.provider_secret(provider_id)
    result = get_provider_adapter(provider.protocol).test_connection(
        base_url=provider.base_url, models_path=provider.models_path,
        api_key=secret,
    )
    # Keep probe metadata non-sensitive and do not return upstream response body.
    from datetime import datetime, timezone
    with store.connect() as connection:
        connection.execute("UPDATE ai_providers SET last_test_status=?, last_test_latency_ms=?, last_test_at=? WHERE id=?", (result.category if not result.ok else "ok", result.latency_ms, datetime.now(timezone.utc).isoformat(timespec="milliseconds"), provider_id))
        connection.commit()
    return {"ok": result.ok, "category": result.category, "latency_ms": result.latency_ms}


def discover_models(provider_id: str) -> dict[str, Any]:
    store = _store(); provider = store.get_provider(provider_id)
    if provider is None: raise LookupError("Provider 不存在")
    result = get_provider_adapter(provider.protocol).discover_models(
        base_url=provider.base_url, models_path=provider.models_path,
        api_key=store.provider_secret(provider_id),
    )
    if not result.ok: return {"ok": False, "category": result.category, "items": []}
    provider = store.get_provider(provider_id)
    if provider is None: raise LookupError("Provider 不存在")
    for model_id in result.model_ids:
        store.upsert_model(
            provider_id=provider_id, model_id=model_id,
            capabilities=capabilities_for_model(vendor=provider.vendor, protocol=provider.protocol, model_id=model_id),
            capability_source="discovered",
        )
    store.mark_provider_models_unavailable(provider_id, set(result.model_ids))
    return {"ok": True, "category": "ok", "items": [asdict(item) for item in store.list_models(provider_id)]}


def profiles() -> dict[str, Any]:
    return {"items": [asdict(item) for item in _store().list_profiles()], "supported_business_keys": list(SUPPORTED_BUSINESS_KEYS)}


def save_profile(business_key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if business_key not in SUPPORTED_BUSINESS_KEYS: raise ValueError("不支持的业务类型")
    policy = ReasoningPolicy(str(payload.get("reasoning_mode", "auto")), payload.get("reasoning_effort"), payload.get("reasoning_budget"))
    store = _store(); provider_id = str(payload.get("provider_id", "")); model_id = str(payload.get("model_id", ""))
    model = next((item for item in store.list_models(provider_id) if item.model_id == model_id), None)
    if model is None:
        raise ValueError("模型不存在，请先手工添加或获取模型")
    if not model.enabled:
        raise ValueError("模型已停用，不能配置业务路由")
    if not model.available:
        raise ValueError("模型当前不可用，不能配置业务路由")
    validate_reasoning_policy(policy, model.capabilities if model else {})
    item = store.save_profile(BusinessProfile(business_key, provider_id, model_id, policy.mode, policy.effort, policy.budget_tokens, bool(payload.get("enabled", True)), ""))
    return asdict(item)


__all__ = ["add_model", "create_provider", "delete_provider", "discover_models", "profiles", "provider_models", "provider_presets", "providers", "save_profile", "test_provider", "update_model", "update_provider"]
