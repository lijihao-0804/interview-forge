from __future__ import annotations

import os
import json
import sqlite3
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from interview_forge.ai.config import AIConfig, model_key
from interview_forge.ai.config_store import AIConfigError, AIConfigStore, BusinessProfile, validate_base_url, validate_network_target
from interview_forge.ai.catalog import resolve_model_capabilities
from interview_forge.ai.errors import AIServiceError
from interview_forge.ai.policy import ReasoningPolicy
from interview_forge.ai.providers.base import ProviderProbeResult
from interview_forge.ai.providers import get_provider_adapter
from interview_forge.ai.providers.native import AnthropicAdapter, GeminiAdapter
from interview_forge.ai.providers.openai_compatible import OpenAICompatibleAdapter
from interview_forge.ai.providers.chat_model import build_chat_model_kwargs
from interview_forge.ai.resolver import resolve_ai_runtime
from interview_forge.ai.chat.service import ChatService
from interview_forge.ai.memory.contracts import MemoryCandidate
from interview_forge.observability.ai_trace import TraceRecorder


def _config(*, provider: str, wire_api: str, model: str = "m", base_url: str = "https://example.com/v1", **kwargs) -> AIConfig:
    values = dict(
        enabled=True, provider=provider, model=model, base_url=base_url, api_key="secret",
        wire_api=wire_api, actor_authorization="", reasoning_effort="", thinking_enabled=False,
        request_timeout_seconds=8, max_concurrent_requests=1, daily_limit_per_user=3,
        beta_users="*",
    )
    values.update(kwargs)
    return AIConfig(**values)


class ProviderV1HardeningTests(unittest.TestCase):
    def test_model_key_includes_provider_protocol_model_and_endpoint_without_secret(self):
        openai = _config(provider="openai", wire_api="responses")
        anthropic = _config(provider="anthropic", wire_api="anthropic_messages")
        gemini = _config(provider="gemini", wire_api="gemini")
        self.assertNotIn("unknown", model_key(anthropic))
        self.assertNotEqual(model_key(openai), model_key(anthropic))
        self.assertNotEqual(model_key(anthropic), model_key(gemini))
        self.assertEqual(model_key(openai), model_key(_config(provider="openai", wire_api="responses")))
        self.assertNotIn("secret", model_key(openai))

    def test_learning_task_creation_uses_managed_profile_when_env_is_disabled(self):
        from interview_forge.ai import ai_coach
        from tests.test_ai_coach import context_for

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "user.db"
            config_db = root / "ai.db"
            with patch.dict(os.environ, {
                "INTERVIEW_FORGE_AI_CONFIG_KEY": "master",
                "INTERVIEW_FORGE_AI_CONFIG_DB": str(config_db),
                "AI_ENABLED": "0",
                "AI_BETA_USERS": "alice",
            }, clear=False):
                store = AIConfigStore(config_db)
                provider = store.create_provider(name="Managed", vendor="custom", protocol="openai_chat", base_url="https://example.com", api_key="k")
                store.upsert_model(provider_id=provider.id, model_id="managed-model")
                store.save_profile(BusinessProfile("learning_analysis", provider.id, "managed-model", "auto", None, None, True, ""))
                with patch.object(ai_coach, "_ensure_workers", return_value=None), patch.object(ai_coach._AI_QUEUE, "put_nowait", return_value=None):
                    task = ai_coach.create_ai_task(db, context_for(), "alice", "user")
                connection = sqlite3.connect(db)
                try:
                    row = connection.execute("SELECT model_key FROM ai_tasks WHERE task_id = ?", (task["task_id"],)).fetchone()
                finally:
                    connection.close()
                self.assertTrue(row and row[0].startswith("openai-compatible:chat_completions:model-"))

    def test_adapter_registry_dispatches_each_protocol(self):
        self.assertIsInstance(get_provider_adapter("openai_chat"), OpenAICompatibleAdapter)
        self.assertIsInstance(get_provider_adapter("openai_responses"), OpenAICompatibleAdapter)
        self.assertIsInstance(get_provider_adapter("anthropic_messages"), AnthropicAdapter)
        self.assertIsInstance(get_provider_adapter("gemini"), GeminiAdapter)

    def test_native_discovery_uses_native_payload_shape(self):
        class Response:
            def __init__(self, payload):
                self.payload = payload
                self.status_code = 200
                self.content = json.dumps(payload).encode("utf-8")

            def json(self):
                return self.payload

        class Client:
            payload = {"data": [{"id": "claude-test"}]}

            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            def __enter__(self): return self
            def __exit__(self, *args): return False
            def get(self, url, **kwargs): return Response(self.payload)

        pinned = ("example.com", ((socket.AF_INET, ("127.0.0.1", 443)),))
        with patch("interview_forge.ai.providers.network.resolve_network_target", return_value=pinned), patch("interview_forge.ai.providers.native.httpx.Client", Client):
            result = AnthropicAdapter().discover_models(base_url="https://example.com", models_path="/v1/models", api_key="k")
        self.assertEqual(result.category, "ok")
        self.assertEqual(result.model_ids, ("claude-test",))

        Client.payload = {"models": [{"name": "models/gemini-test"}]}
        with patch("interview_forge.ai.providers.network.resolve_network_target", return_value=pinned), patch("interview_forge.ai.providers.native.httpx.Client", Client):
            result = GeminiAdapter().discover_models(base_url="https://example.com", models_path="/v1beta/models", api_key="k")
        self.assertEqual(result.model_ids, ("gemini-test",))

    def test_native_missing_dependency_is_safe_and_custom_gemini_url_is_not_ignored(self):
        config = _config(provider="anthropic", wire_api="anthropic_messages")
        with patch.dict("sys.modules", {"langchain_anthropic": None}):
            with self.assertRaises(AIServiceError) as raised:
                AnthropicAdapter().make_chat_model(config)
        self.assertEqual(raised.exception.category, "not_configured")
        with self.assertRaises(AIServiceError):
            GeminiAdapter().make_chat_model(_config(provider="gemini", wire_api="gemini", base_url="https://custom.example"))

    def test_openai_compatible_model_probe_measures_streaming_ttft_without_exposing_body(self):
        class Response:
            status_code = 200

            def __enter__(self): return self
            def __exit__(self, *args): return False
            def iter_lines(self):
                yield b'data: {"choices":[{"delta":{"content":"OK"}}]}'
                yield b"data: [DONE]"

        class Client:
            def __init__(self, *args, **kwargs): self.kwargs = kwargs
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def stream(self, method, url, **kwargs):
                self.method, self.url, self.request_kwargs = method, url, kwargs
                type(self).last_method = method
                type(self).last_url = url
                type(self).last_request_kwargs = kwargs
                return Response()

        pinned = ("example.com", ((socket.AF_INET, ("127.0.0.1", 443)),))
        with patch("interview_forge.ai.providers.network.resolve_network_target", return_value=pinned), patch("interview_forge.ai.providers.openai_compatible.httpx.Client", Client):
            result = OpenAICompatibleAdapter("openai_chat").test_model(
                base_url="https://example.com/v1", model_id="test-model", api_key="secret"
            )
        self.assertEqual(Client.last_method, "POST")
        self.assertEqual(Client.last_url, "https://example.com/v1/chat/completions")
        self.assertEqual(Client.last_request_kwargs["json"]["max_tokens"], 64)
        self.assertTrue(result.ok)
        self.assertEqual(result.category, "ok")
        self.assertTrue(result.streaming)
        self.assertIsNotNone(result.ttft_ms)
        self.assertIsNotNone(result.latency_ms)

    def test_model_test_result_is_persisted_separately_from_capabilities(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "ai.db"
            with patch.dict(os.environ, {"INTERVIEW_FORGE_AI_CONFIG_KEY": "master", "INTERVIEW_FORGE_AI_CONFIG_DB": str(db)}, clear=False):
                store = AIConfigStore(db)
                provider = store.create_provider(name="Managed", vendor="custom", protocol="openai_chat", base_url="https://example.com", api_key="k")
                store.upsert_model(provider_id=provider.id, model_id="test-model", capabilities={"tools": False})
                class Adapter:
                    def test_model(self, **_kwargs):
                        return ProviderProbeResult(True, "ok", latency_ms=42.0, ttft_ms=11.0, streaming=True)
                from interview_forge.services import admin_ai_config
                with patch.object(admin_ai_config, "get_provider_adapter", return_value=Adapter()):
                    result = admin_ai_config.test_model(provider.id, "test-model")
                item = next(item for item in store.list_models(provider.id) if item.model_id == "test-model")
                self.assertTrue(result["ok"])
                self.assertEqual(result["status"], "passed")
                self.assertEqual(item.last_test_status, "passed")
                self.assertEqual(item.last_test_ttft_ms, 11.0)
                self.assertEqual(item.capabilities, {"tools": False})

    def test_reasoning_is_translated_or_rejected_explicitly(self):
        effort = _config(provider="openai", wire_api="responses", reasoning_mode="effort", reasoning_effort="high")
        self.assertEqual(build_chat_model_kwargs(effort)["reasoning_effort"], "high")
        disabled = _config(provider="openai", wire_api="responses", reasoning_mode="off")
        disabled_kwargs = build_chat_model_kwargs(disabled)
        self.assertEqual(disabled_kwargs["reasoning_effort"], "none")
        self.assertNotIn("extra_body", disabled_kwargs)
        budget = _config(provider="openai-compatible", wire_api="chat_completions", reasoning_mode="budget", reasoning_budget=512)
        self.assertEqual(build_chat_model_kwargs(budget)["extra_body"]["thinking"]["budget_tokens"], 512)
        native = _config(provider="anthropic", wire_api="anthropic_messages")
        self.assertEqual(AnthropicAdapter().apply_reasoning(native, ReasoningPolicy("auto")), {})
        with self.assertRaises(AIServiceError):
            AnthropicAdapter().apply_reasoning(native, ReasoningPolicy("effort", "high"))

    def test_discovery_does_not_guess_capabilities_and_preserves_manual_override(self):
        with tempfile.TemporaryDirectory() as directory:
            config_db = Path(directory) / "ai.db"
            with patch.dict(os.environ, {
                "INTERVIEW_FORGE_AI_CONFIG_KEY": "master",
                "INTERVIEW_FORGE_AI_CONFIG_DB": str(config_db),
            }, clear=False):
                store = AIConfigStore(config_db)
                provider = store.create_provider(
                    name="OpenAI", vendor="openai", protocol="openai_responses",
                    base_url="https://example.com/v1", api_key="k",
                )

                class Adapter:
                    def discover_models(self, **_kwargs):
                        return ProviderProbeResult(True, "ok", ("gpt-5.6-luna", "vendor-model"))

                from interview_forge.services import admin_ai_config
                with patch.object(admin_ai_config, "get_provider_adapter", return_value=Adapter()):
                    result = admin_ai_config.discover_models(provider.id)
                by_id = {item["model_id"]: item for item in result["items"]}
                self.assertFalse(by_id["gpt-5.6-luna"]["capabilities"]["reasoning"])
                self.assertFalse(by_id["vendor-model"]["capabilities"]["reasoning"])
                store.update_model(
                    provider_id=provider.id,
                    model_id="gpt-5.6-luna",
                    capabilities={"manual": True, "reasoning": False},
                )
                with patch.object(admin_ai_config, "get_provider_adapter", return_value=Adapter()):
                    admin_ai_config.discover_models(provider.id)
                item = next(item for item in store.list_models(provider.id) if item.model_id == "gpt-5.6-luna")
                self.assertEqual(item.capabilities, {"manual": True, "reasoning": False})

    def test_gemini_custom_base_url_is_rejected_at_create_and_update(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"INTERVIEW_FORGE_AI_CONFIG_KEY": "master"}, clear=False):
                store = AIConfigStore(Path(directory) / "ai.db")
                with self.assertRaises(AIConfigError):
                    store.create_provider(
                        name="Gemini", vendor="google", protocol="gemini",
                        base_url="https://custom.example", api_key="k",
                    )
                provider = store.create_provider(
                    name="Gemini", vendor="google", protocol="gemini",
                    base_url="https://generativelanguage.googleapis.com", api_key="k",
                )
                with self.assertRaises(AIConfigError):
                    store.update_provider(provider.id, base_url="https://custom.example")

    def test_pinned_transport_resolves_once_and_keeps_validated_endpoints(self):
        from interview_forge.ai.providers.network import PinnedHTTPTransport

        records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.10", 443))]
        with patch("interview_forge.ai.config_store.socket.getaddrinfo", return_value=records) as resolver:
            transport = PinnedHTTPTransport("https://provider.example/v1")
            try:
                backend = transport._pool._network_backend
                self.assertEqual(resolver.call_count, 1)
                self.assertEqual(backend.endpoints, ((socket.AF_INET, ("203.0.113.10", 443)),))
            finally:
                transport.close()

    def test_capability_registry_is_conservative_for_unknown_models(self):
        known = resolve_model_capabilities(
            capability_profile="deepseek_official", protocol="openai_chat", model_id="deepseek-flash",
            adapter_capabilities=OpenAICompatibleAdapter().capability_contract(),
        )
        unknown = resolve_model_capabilities(
            capability_profile="deepseek_official", protocol="openai_chat", model_id="vendor-custom-model",
            adapter_capabilities=OpenAICompatibleAdapter().capability_contract(),
        )
        self.assertTrue(known.capabilities["reasoning"])
        self.assertIn("high", known.capabilities["reasoning_efforts"])
        self.assertFalse(unknown.capabilities["reasoning"])
        self.assertEqual(unknown.capabilities["reasoning_modes"], ["auto"])
        self.assertEqual(unknown.source, "unknown")

    def test_resolver_rejects_disabled_or_unavailable_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {"INTERVIEW_FORGE_AI_CONFIG_KEY": "master", "INTERVIEW_FORGE_AI_CONFIG_DB": str(root / "ai.db")}, clear=False):
                store = AIConfigStore(root / "ai.db")
                provider = store.create_provider(name="Local", vendor="custom", protocol="openai_chat", base_url="https://example.com", api_key="k")
                store.upsert_model(provider_id=provider.id, model_id="m")
                store.save_profile(BusinessProfile("chat", provider.id, "m", "auto", None, None, True, ""))
                store.update_model(provider_id=provider.id, model_id="m", enabled=False)
                with self.assertRaises(AIConfigError): resolve_ai_runtime("chat", store=store)
                store.update_model(provider_id=provider.id, model_id="m", enabled=True)
                store.mark_provider_models_unavailable(provider.id, set())
                with self.assertRaises(AIConfigError): resolve_ai_runtime("chat", store=store)

    def test_ssrf_checks_block_unsafe_literal_and_dns_targets_but_allow_private(self):
        with self.assertRaises(AIConfigError): validate_base_url("http://169.254.169.254/latest")
        with self.assertRaises(AIConfigError): validate_base_url("http://0.0.0.0:8080")
        with patch("interview_forge.ai.config_store.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.10.10", 443))]):
            with self.assertRaises(AIConfigError): validate_network_target("https://metadata.example")
        with patch("interview_forge.ai.config_store.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 443))]):
            validate_network_target("http://internal.example")

    def test_memory_runtime_fallback_is_visible_in_safe_trace_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "user.db"

            class Extractor:
                def extract(self, message, *, model):
                    return [MemoryCandidate(
                        operation="upsert", kind="preference", canonical_key="preference.order",
                        value={"text": "先讲思路"}, display_text="先讲思路", explicit=False,
                        confidence=0.8, importance=2,
                    )]

            service = ChatService(
                runtime_loader=lambda _business: (_ for _ in ()).throw(RuntimeError("missing")),
                model_factory=lambda config: object(),
                memory_extractor=Extractor(),
            )
            trace = TraceRecorder(user_db=db, trace_id="trace-memory", provider="openai", model="chat-model")
            service._process_memory(
                user_db=db, session_id="s", message_id=1,
                message="我喜欢先讲思路", model=object(), trace_recorder=trace,
            )
            connection = sqlite3.connect(db)
            try:
                row = connection.execute(
                    "SELECT metadata_json FROM ai_trace_events WHERE trace_id = ?",
                    ("trace-memory",),
                ).fetchone()
            finally:
                connection.close()
            metadata = json.loads(row[0])
            self.assertTrue(metadata["fallback"])
            self.assertEqual(metadata["requested_business"], "memory_extraction")
            self.assertEqual(metadata["fallback_provider"], "openai")
            self.assertNotIn("我喜欢", json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
