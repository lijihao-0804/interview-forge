"""Admin-only AI provider/model/business routing API."""
from __future__ import annotations

from fastapi import APIRouter, Request

from interview_forge.api.support import async_require_admin, error_response, json_response, read_json, require_admin, service_error
from interview_forge.services import admin_ai_config as service

router = APIRouter()


def _call(request: Request, operation):
    _, denied = require_admin(request)
    if denied is not None: return denied
    try: return json_response(operation())
    except BaseException as exc: return service_error(exc) or error_response("AI 配置操作失败", 400)


async def _write(request: Request, operation):
    _, denied = await async_require_admin(request)
    if denied is not None: return denied
    try:
        payload = await read_json(request, max_length=16_384)
        return json_response(operation(payload))
    except BaseException as exc: return service_error(exc, write=True) or error_response("AI 配置操作失败", 400)


@router.get("/api/admin/ai/provider-presets")
def provider_presets(request: Request): return _call(request, service.provider_presets)

@router.get("/api/admin/ai/providers")
def providers(request: Request): return _call(request, service.providers)

@router.post("/api/admin/ai/providers")
async def create_provider(request: Request): return await _write(request, service.create_provider)

@router.put("/api/admin/ai/providers/{provider_id}")
async def update_provider(provider_id: str, request: Request): return await _write(request, lambda payload: service.update_provider(provider_id, payload))

@router.delete("/api/admin/ai/providers/{provider_id}")
def delete_provider(provider_id: str, request: Request): return _call(request, lambda: service.delete_provider(provider_id))

@router.post("/api/admin/ai/providers/{provider_id}/test")
def test_provider(provider_id: str, request: Request): return _call(request, lambda: service.test_provider(provider_id))

@router.post("/api/admin/ai/providers/{provider_id}/discover-models")
def discover_models(provider_id: str, request: Request): return _call(request, lambda: service.discover_models(provider_id))

@router.post("/api/admin/ai/providers/{provider_id}/models/{model_id}/test")
def test_model(provider_id: str, model_id: str, request: Request): return _call(request, lambda: service.test_model(provider_id, model_id))

@router.get("/api/admin/ai/providers/{provider_id}/models")
def provider_models(provider_id: str, request: Request): return _call(request, lambda: service.provider_models(provider_id))

@router.post("/api/admin/ai/providers/{provider_id}/models")
async def add_model(provider_id: str, request: Request): return await _write(request, lambda payload: service.add_model(provider_id, payload))

@router.put("/api/admin/ai/providers/{provider_id}/models/{model_id}")
async def update_model(provider_id: str, model_id: str, request: Request):
    return await _write(request, lambda payload: service.update_model(provider_id, model_id, payload))

@router.get("/api/admin/ai/business-profiles")
def profiles(request: Request): return _call(request, service.profiles)

@router.put("/api/admin/ai/business-profiles/{business_key}")
async def save_profile(business_key: str, request: Request): return await _write(request, lambda payload: service.save_profile(business_key, payload))


__all__ = ["router"]
