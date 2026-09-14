from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from interview_forge.ai.catalog import resolve_model_capabilities
from interview_forge.ai.config_store import AIConfigStore
from interview_forge.ai.providers.base import ProviderAdapter
from interview_forge.ai.providers.openai_compatible import OpenAICompatibleAdapter
from interview_forge.services import admin_ai_config
from interview_forge.ai.providers.base import ProviderProbeResult


class NoReasoningAdapter(ProviderAdapter):
    def capability_contract(self):
        return {
            "streaming": True, "tools": True, "structured_output": True,
            "reasoning": False, "reasoning_modes": ["auto"],
            "reasoning_efforts": [], "reasoning_budget": False,
        }


class ProviderCapabilityCatalogTests(unittest.TestCase):
    def test_deepseek_official_exact_models_are_catalogued(self):
        adapter = OpenAICompatibleAdapter().capability_contract()
        for model_id in ("deepseek-flash", "deepseek-v4-pro"):
            result = resolve_model_capabilities(
                capability_profile="deepseek_official", protocol="openai_chat", model_id=model_id,
                adapter_capabilities=adapter,
            )
            self.assertEqual(result.source, "official_catalog")
            self.assertTrue(result.capabilities["reasoning"])
            self.assertEqual(result.capabilities["reasoning_modes"], ["off", "auto", "effort"])
            self.assertEqual(result.capabilities["reasoning_efforts"], ["low", "high", "max"])

    def test_deepseek_alias_keeps_selected_id_and_exposes_canonical_model(self):
        result = resolve_model_capabilities(
            capability_profile="deepseek_official", protocol="openai_chat",
            model_id="deepseek-v4-flash-vision-exp",
            adapter_capabilities=OpenAICompatibleAdapter().capability_contract(),
        )
        self.assertEqual(result.source, "official_catalog")
        self.assertEqual(result.canonical_model, "deepseek-flash")
        self.assertTrue(result.capabilities["reasoning"])

    def test_unknown_model_is_available_but_conservative(self):
        result = resolve_model_capabilities(
            capability_profile="deepseek_official", protocol="openai_chat", model_id="deepseek-v5",
            adapter_capabilities=OpenAICompatibleAdapter().capability_contract(),
        )
        self.assertEqual(result.source, "unknown")
        self.assertFalse(result.capabilities["reasoning"])
        self.assertEqual(result.capabilities["reasoning_modes"], ["auto"])

    def test_generic_provider_does_not_inherit_vendor_catalog(self):
        generic = resolve_model_capabilities(
            capability_profile="generic_openai_compatible", protocol="openai_chat", model_id="deepseek-flash",
            adapter_capabilities=OpenAICompatibleAdapter().capability_contract(),
        )
        explicit = resolve_model_capabilities(
            capability_profile="deepseek_official", protocol="openai_chat", model_id="deepseek-flash",
            adapter_capabilities=OpenAICompatibleAdapter().capability_contract(),
        )
        self.assertEqual(generic.source, "unknown")
        self.assertFalse(generic.capabilities["reasoning"])
        self.assertEqual(explicit.source, "official_catalog")
        self.assertTrue(explicit.capabilities["reasoning"])

    def test_manual_override_wins_and_adapter_intersection_removes_unsupported_modes(self):
        manual = resolve_model_capabilities(
            capability_profile="deepseek_official", protocol="openai_chat", model_id="deepseek-flash",
            capability_source="manual", manual_capabilities={
                "streaming": True, "tools": True, "structured_output": True,
                "reasoning": True, "reasoning_modes": ["auto", "off", "effort"],
                "reasoning_efforts": ["high"], "reasoning_budget": False,
            }, adapter_capabilities=NoReasoningAdapter().capability_contract(),
        )
        self.assertEqual(manual.source, "manual")
        self.assertFalse(manual.capabilities["reasoning"])
        self.assertEqual(manual.capabilities["reasoning_modes"], ["auto"])

    def test_responses_adapter_does_not_expose_chat_budget_mode(self):
        result = resolve_model_capabilities(
            capability_profile="deepseek_official", protocol="openai_responses", model_id="deepseek-flash",
            adapter_capabilities=OpenAICompatibleAdapter("openai_responses").capability_contract(),
        )
        self.assertTrue(result.capabilities["reasoning"])
        self.assertNotIn("budget", result.capabilities["reasoning_modes"])
        self.assertFalse(result.capabilities["reasoning_budget"])

    def test_discovery_does_not_guess_or_overwrite_manual_capability(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "ai.db"
            with patch.dict(os.environ, {"INTERVIEW_FORGE_AI_CONFIG_KEY": "master", "INTERVIEW_FORGE_AI_CONFIG_DB": str(db)}, clear=False):
                store = AIConfigStore(db)
                provider = store.create_provider(name="Custom", vendor="custom", protocol="openai_chat", base_url="https://example.com", api_key="k")
                store.upsert_model(
                    provider_id=provider.id, model_id="deepseek-flash",
                    capabilities={"reasoning": True, "reasoning_modes": ["auto", "effort"], "reasoning_efforts": ["high"]},
                    capability_source="manual", capability_profile="generic_openai_compatible",
                )
                class Adapter:
                    def capability_contract(self):
                        return OpenAICompatibleAdapter().capability_contract()
                    def discover_models(self, **_kwargs):
                        return ProviderProbeResult(True, "ok", ("deepseek-flash", "new-model"))
                with patch.object(admin_ai_config, "get_provider_adapter", return_value=Adapter()):
                    result = admin_ai_config.discover_models(provider.id)
                by_id = {item["model_id"]: item for item in result["items"]}
                self.assertEqual(by_id["deepseek-flash"]["capability_source"], "manual")
                self.assertTrue(by_id["deepseek-flash"]["capabilities"]["reasoning"])
                self.assertEqual(by_id["new-model"]["capability_source"], "unknown")
                self.assertFalse(by_id["new-model"]["capabilities"]["reasoning"])

    def test_schema_migration_is_idempotent_and_preserves_old_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "old.db"
            import sqlite3
            connection = sqlite3.connect(db)
            connection.executescript("""
                CREATE TABLE ai_providers (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, vendor TEXT NOT NULL,
                    protocol TEXT NOT NULL, base_url TEXT NOT NULL, encrypted_secret TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1, models_path TEXT NOT NULL DEFAULT '/models',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    last_test_status TEXT, last_test_latency_ms REAL, last_test_at TEXT
                );
                CREATE TABLE ai_models (
                    id TEXT PRIMARY KEY, provider_id TEXT NOT NULL, model_id TEXT NOT NULL,
                    display_name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                    available INTEGER NOT NULL DEFAULT 1, capabilities_json TEXT NOT NULL DEFAULT '{}',
                    capability_source TEXT NOT NULL DEFAULT 'unknown', discovered_at TEXT, last_seen_at TEXT,
                    UNIQUE(provider_id, model_id)
                );
                CREATE TABLE ai_business_profiles (
                    business_key TEXT PRIMARY KEY, provider_id TEXT NOT NULL, model_id TEXT NOT NULL,
                    reasoning_mode TEXT NOT NULL DEFAULT 'auto', reasoning_effort TEXT,
                    reasoning_budget INTEGER, enabled INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
                );
            """)
            connection.execute(
                "INSERT INTO ai_providers(id,name,vendor,protocol,base_url,enabled,models_path,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                ("provider-1", "Old", "custom", "openai_chat", "https://example.com", 1, "/models", "now", "now"),
            )
            connection.execute(
                "INSERT INTO ai_models(id,provider_id,model_id,display_name,capabilities_json,capability_source,discovered_at,last_seen_at) VALUES (?,?,?,?,?,?,?,?)",
                ("model-1", "provider-1", "legacy-model", "Legacy", json.dumps({"reasoning": True}), "manual", "now", "now"),
            )
            connection.commit(); connection.close()
            with patch.dict(os.environ, {"INTERVIEW_FORGE_AI_CONFIG_KEY": "master"}, clear=False):
                first = AIConfigStore(db)
                second = AIConfigStore(db)
                connection = second.connect()
                try:
                    provider_columns = {row[1] for row in connection.execute("PRAGMA table_info(ai_providers)")}
                    model_columns = {row[1] for row in connection.execute("PRAGMA table_info(ai_models)")}
                finally:
                    connection.close()
            self.assertIn("capability_profile", provider_columns)
            self.assertTrue({"capability_profile", "canonical_model", "capability_verified_at", "capability_catalog_version"} <= model_columns)
            provider = second.get_provider("provider-1")
            model = second.list_models("provider-1")[0]
            self.assertEqual(provider.capability_profile, "generic_openai_compatible")
            self.assertEqual(model.capability_source, "manual")
            self.assertEqual(model.capabilities, {"reasoning": True})


if __name__ == "__main__":
    unittest.main()
