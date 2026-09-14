from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from interview_forge.ai.config import load_ai_config
from interview_forge.ai.config_store import (
    AIConfigStore, AISecretUnavailable, BusinessProfile, validate_base_url,
)
from interview_forge.ai.providers.openai_compatible import OpenAICompatibleAdapter, models_url
from interview_forge.ai.resolver import resolve_ai_runtime
from interview_forge.api.app import app


class _Response:
    status_code = 200
    content = b'{"data":[{"id":"model-a"},{"id":"model-b"}]}'

    def json(self):
        return {"data": [{"id": "model-a"}, {"id": "model-b"}]}


class _Client:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def get(self, url): return _Response()


class AIConfigStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "ai_config.db"
        self.env = patch.dict(os.environ, {
            "INTERVIEW_FORGE_AI_CONFIG_KEY": "test-master-key",
            "INTERVIEW_FORGE_AI_CONFIG_DB": str(self.db),
        }, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_encrypted_secret_and_idempotent_schema(self):
        store = AIConfigStore(self.db)
        store.ensure_schema()
        provider = store.create_provider(name="Local", vendor="custom", protocol="openai_chat", base_url="https://example.com/v1", api_key="sk-real-secret")
        self.assertEqual(store.provider_secret(provider.id), "sk-real-secret")
        self.assertIn("sk-••••ret", provider.key_hint)
        self.assertNotIn("sk-real-secret", self.db.read_bytes().decode("latin1"))
        os.environ["INTERVIEW_FORGE_AI_CONFIG_KEY"] = "wrong-key"
        with self.assertRaises(AISecretUnavailable):
            store.provider_secret(provider.id)

    def test_models_discovery_upsert_and_disappearance(self):
        store = AIConfigStore(self.db)
        provider = store.create_provider(name="Local", vendor="custom", protocol="openai_chat", base_url="https://example.com/v1", api_key="k")
        with patch("httpx.Client", _Client):
            result = OpenAICompatibleAdapter().discover_models(base_url=provider.base_url, models_path=provider.models_path, api_key="k")
        self.assertEqual(result.model_ids, ("model-a", "model-b"))
        for value in result.model_ids: store.upsert_model(provider_id=provider.id, model_id=value, capability_source="discovered")
        store.mark_provider_models_unavailable(provider.id, {"model-a"})
        self.assertTrue(next(item for item in store.list_models(provider.id) if item.model_id == "model-a").available)
        self.assertFalse(next(item for item in store.list_models(provider.id) if item.model_id == "model-b").available)

    def test_profile_blocks_delete_and_resolver_uses_db_then_env(self):
        store = AIConfigStore(self.db)
        provider = store.create_provider(name="Local", vendor="custom", protocol="openai_chat", base_url="https://example.com/v1", api_key="k")
        store.upsert_model(provider_id=provider.id, model_id="m")
        store.save_profile(BusinessProfile("chat", provider.id, "m", "auto", None, None, True, ""))
        runtime = resolve_ai_runtime("chat", store=store)
        self.assertEqual(runtime.config_source, "db")
        with self.assertRaises(ValueError): store.delete_provider(provider.id)
        os.environ["INTERVIEW_FORGE_AI_CONFIG_DB"] = str(Path(self.temp.name) / "empty.db")
        with patch.dict(os.environ, {"AI_ENABLED": "1", "AI_PROVIDER": "openai-compatible", "AI_MODEL": "env-model", "AI_API_KEY": "env-key"}, clear=False):
            self.assertEqual(resolve_ai_runtime("chat").config_source, "env")

    def test_update_without_key_preserves_and_clear_is_explicit(self):
        store = AIConfigStore(self.db)
        provider = store.create_provider(name="Local", vendor="custom", protocol="openai_chat", base_url="https://example.com/v1", api_key="sk-original")
        store.update_provider(provider.id, name="Renamed")
        self.assertEqual(store.provider_secret(provider.id), "sk-original")
        store.update_provider(provider.id, clear_api_key=True)
        self.assertEqual(store.provider_secret(provider.id), "")

    def test_explicit_reasoning_requires_capability(self):
        store = AIConfigStore(self.db)
        provider = store.create_provider(name="Local", vendor="custom", protocol="openai_chat", base_url="https://example.com/v1", api_key="k")
        store.upsert_model(provider_id=provider.id, model_id="m")
        with self.assertRaises(ValueError):
            from interview_forge.services.admin_ai_config import save_profile
            save_profile("chat", {"provider_id": provider.id, "model_id": "m", "reasoning_mode": "effort", "reasoning_effort": "high"})

    def test_provider_url_and_protocol_helpers_are_bounded(self):
        self.assertEqual(models_url("https://example.com/v1"), "https://example.com/v1/models")
        with self.assertRaises(ValueError): validate_base_url("https://user:pass@example.com/v1")
        with self.assertRaises(ValueError): validate_base_url("file:///tmp/x")

    def test_admin_api_is_not_public(self):
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/admin/ai/providers").status_code, 401)


if __name__ == "__main__":
    unittest.main()
