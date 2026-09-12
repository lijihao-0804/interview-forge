import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from interview_forge.ai.chat.context_builder import ContextBuilder
from interview_forge.ai.chat.service import ChatService
from interview_forge.ai.memory import MemoryExtractor, MemoryPolicy, MemoryStore, memory_worthy
from interview_forge.ai.memory.extractor import _deterministic_candidate
from interview_forge.api.app import app
from interview_forge.api.routers import chat as chat_router
from interview_forge.ai.config import AIConfig
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime
from interview_forge.services.auth import create_session, create_user


class FakeChunk:
    def __init__(self, content=""):
        self.content = content
        self.tool_calls = []
        self.tool_call_chunks = []
        self.usage_metadata = {}
        self.response_metadata = {}
        self.additional_kwargs = {}


class FakeModel:
    async def astream(self, messages):
        yield FakeChunk("收到")


class CapturingFakeModel(FakeModel):
    def __init__(self):
        self.messages = None

    async def astream(self, messages):
        self.messages = messages
        async for chunk in super().astream(messages):
            yield chunk


class StructuredExtractorModel:
    def __init__(self):
        self.calls = 0

    def with_structured_output(self, _schema):
        return self

    def invoke(self, _messages):
        self.calls += 1
        return {
            "candidates": [{
                "operation": "upsert",
                "kind": "preference",
                "canonical_key": "preference.project_context",
                "value": {"text": "结合我的项目背景并优先指出风险"},
                "display_text": "结合我的项目背景并优先指出风险",
                "explicit": True,
                "confidence": 0.95,
                "importance": 4,
            }]
        }


def _collect(iterator):
    return asyncio.run(_collect_async(iterator))


async def _collect_async(iterator):
    return [item async for item in iterator]


class MemoryDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "user.db"
        self.old_provider = server_runtime._provider
        self.old_values = dict(server_runtime._values)
        server_runtime.bind_provider(lambda: default_runtime)

    def tearDown(self):
        server_runtime._provider = self.old_provider
        server_runtime._values = self.old_values
        self.temp.cleanup()

    def candidate(self, text):
        value = _deterministic_candidate(text)
        self.assertIsNotNone(value)
        accepted = MemoryPolicy().accept(value)
        self.assertIsNotNone(accepted)
        return accepted

    def test_explicit_memory_is_active_and_new_fact_supersedes_old(self):
        store = MemoryStore()
        first = store.save_candidate(
            user_db=self.db, candidate=self.candidate("记住我喜欢先讲思路"),
            source_session_id="s1", source_message_id=1,
        )
        second = store.save_candidate(
            user_db=self.db, candidate=self.candidate("记住我喜欢先讲直觉"),
            source_session_id="s2", source_message_id=2,
        )
        self.assertNotEqual(first.id, second.id)
        active = store.list_active(user_db=self.db)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].display_text, "我喜欢先讲直觉")
        connection = sqlite3.connect(self.db)
        try:
            statuses = connection.execute(
                "SELECT status FROM user_memories ORDER BY created_at"
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual([row[0] for row in statuses], ["superseded", "active"])

    def test_different_preferences_keep_separate_active_keys(self):
        store = MemoryStore()
        first = self.candidate("记住我喜欢先讲思路")
        second = self.candidate("记住我喜欢用 Python")
        store.save_candidate(user_db=self.db, candidate=first, source_session_id="s", source_message_id=1)
        store.save_candidate(user_db=self.db, candidate=second, source_session_id="s", source_message_id=2)
        active = store.list_active(user_db=self.db)
        self.assertEqual({item.canonical_key for item in active}, {
            "preference.explanation_order", "preference.programming_language"
        })

    def test_complex_worthy_message_uses_structured_extractor_and_normal_chat_skips_it(self):
        model = StructuredExtractorModel()
        message = "请记住我希望以后结合我正在维护的项目来解释问题，并优先指出风险"
        candidates = MemoryExtractor().extract(message, model=model)
        self.assertEqual(model.calls, 1)
        self.assertEqual(candidates[0].canonical_key, "preference.project_context")
        self.assertEqual(MemoryExtractor().extract("今天有点困", model=model), [])
        self.assertEqual(model.calls, 1)

    def test_forget_deletes_content_and_secrets_never_enter_store(self):
        store = MemoryStore()
        store.save_candidate(
            user_db=self.db, candidate=self.candidate("记住我喜欢先讲思路"),
            source_session_id="s", source_message_id=1,
        )
        forget = MemoryPolicy().accept(_deterministic_candidate("忘记这个偏好"))
        self.assertIsNotNone(forget)
        store.save_candidate(user_db=self.db, candidate=forget, source_session_id="s", source_message_id=2)
        self.assertEqual(store.list_active(user_db=self.db), [])
        secret = _deterministic_candidate("记住我的 LEETCODE_SESSION 是 abc")
        self.assertIsNone(secret)
        self.assertFalse(MemoryExtractor().extract("记住我的 token 是 abc"))

    def test_gate_ignores_short_lived_status_and_retrieval_is_relevant_and_bounded(self):
        self.assertFalse(memory_worthy("今天有点困"))
        store = MemoryStore()
        for index in range(8):
            candidate = self.candidate(f"记住我喜欢先讲思路 {index}")
            store.save_candidate(
                user_db=self.db, candidate=candidate,
                source_session_id="s", source_message_id=index,
            )
        from interview_forge.ai.memory.retriever import MemoryRetriever
        result = MemoryRetriever(store).retrieve(
            user_db=self.db, query="请讲讲算法思路", max_items=6, max_tokens=20
        )
        self.assertLessEqual(len(result), 6)
        self.assertLessEqual(sum(max(1, len(item.display_text) // 3) for item in result), 20)

    def test_cross_session_context_and_learning_block_order(self):
        store = MemoryStore()
        store.save_candidate(
            user_db=self.db, candidate=self.candidate("记住我喜欢先讲思路"),
            source_session_id="session-a", source_message_id=3,
        )
        from interview_forge.ai.memory import MemoryContextBuilder
        memory_block = MemoryContextBuilder().build(user_db=self.db, query="算法思路")
        self.assertIsNotNone(memory_block)
        messages = ContextBuilder(context_blocks=[memory_block]).build(
            user_db=self.db, session_id="missing-session", current_message="讲解算法"
        )
        self.assertIn("先讲思路", messages[0]["content"])
        self.assertIn("不可信上下文", messages[0]["content"])

    def test_memory_failure_does_not_fail_chat(self):
        class BrokenExtractor:
            def extract(self, *args, **kwargs):
                raise RuntimeError("secret provider detail")

        config = AIConfig(
            enabled=True, provider="openai-compatible", model="test", base_url="https://example.invalid",
            api_key="test-key", wire_api="chat_completions", actor_authorization="", reasoning_effort="",
            thinking_enabled=False, request_timeout_seconds=10, max_concurrent_requests=2,
            daily_limit_per_user=3, beta_users="*",
        )
        service = ChatService(
            config_loader=lambda: config, model_factory=lambda _config: FakeModel(),
            memory_extractor=BrokenExtractor(),
            stream_factory=lambda _model, _messages: _fallback(),
        )
        session = service.create_session(user_db=self.db)
        events = _collect(service.stream_reply(
            user_db=self.db, session_id=session["id"], message="我的目标是提升算法能力"
        ))
        self.assertEqual([item["event"] for item in events], ["message.start", "message.delta", "message.done"])
        self.assertIn("收到", events[1]["data"]["delta"])

    def test_explicit_memory_save_happens_before_answer(self):
        config = AIConfig(
            enabled=True, provider="openai-compatible", model="test", base_url="https://example.invalid",
            api_key="test-key", wire_api="chat_completions", actor_authorization="", reasoning_effort="",
            thinking_enabled=False, request_timeout_seconds=10, max_concurrent_requests=2,
            daily_limit_per_user=3, beta_users="*",
        )
        model = CapturingFakeModel()
        service = ChatService(config_loader=lambda: config, model_factory=lambda _config: model)
        session = service.create_session(user_db=self.db)
        events = _collect(service.stream_reply(
            user_db=self.db, session_id=session["id"], message="记住我以后解释算法先讲思路"
        ))
        self.assertIn("收到", events[1]["data"]["delta"])
        active = MemoryStore().list_active(user_db=self.db)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].canonical_key, "preference.explanation_order")
        system_content = model.messages[0]["content"]
        self.assertIn("ContextBlock:memory_persistence", system_content)
        self.assertIn("persistence_success=true", system_content)

    def test_explicit_memory_failure_cannot_claim_saved(self):
        class BrokenExtractor:
            def extract(self, *args, **kwargs):
                raise RuntimeError("provider failed")

        config = AIConfig(
            enabled=True, provider="openai-compatible", model="test", base_url="https://example.invalid",
            api_key="test-key", wire_api="chat_completions", actor_authorization="", reasoning_effort="",
            thinking_enabled=False, request_timeout_seconds=10, max_concurrent_requests=2,
            daily_limit_per_user=3, beta_users="*",
        )
        service = ChatService(
            config_loader=lambda: config, model_factory=lambda _config: FakeModel(),
            memory_extractor=BrokenExtractor(),
        )
        session = service.create_session(user_db=self.db)
        events = _collect(service.stream_reply(
            user_db=self.db, session_id=session["id"], message="记住我以后解释算法先讲思路"
        ))
        answer = events[1]["data"]["delta"]
        self.assertIn("没有成功保存", answer)
        self.assertNotIn("已记住", answer)

    def test_explicit_forget_is_persisted_before_answer(self):
        store = MemoryStore()
        store.save_candidate(
            user_db=self.db, candidate=self.candidate("记住我喜欢先讲思路"),
            source_session_id="old", source_message_id=1,
        )
        config = AIConfig(
            enabled=True, provider="openai-compatible", model="test", base_url="https://example.invalid",
            api_key="test-key", wire_api="chat_completions", actor_authorization="", reasoning_effort="",
            thinking_enabled=False, request_timeout_seconds=10, max_concurrent_requests=2,
            daily_limit_per_user=3, beta_users="*",
        )
        service = ChatService(config_loader=lambda: config, model_factory=lambda _config: FakeModel())
        session = service.create_session(user_db=self.db)
        events = _collect(service.stream_reply(
            user_db=self.db, session_id=session["id"], message="忘记这个偏好"
        ))
        self.assertIn("收到", events[1]["data"]["delta"])
        self.assertEqual(MemoryStore().list_active(user_db=self.db), [])


async def _fallback():
    yield "收到", {}


class MemoryApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.auth_db = root / "auth.db"
        self.users_dir = root / "users"
        self.users_dir.mkdir()
        self.old_provider = server_runtime._provider
        self.old_values = dict(server_runtime._values)
        self.old_auth_ready = default_runtime._AUTH_READY
        self.old_last_purge = default_runtime._LAST_SESSION_PURGE
        default_runtime._AUTH_READY = False
        default_runtime._LAST_SESSION_PURGE = 0.0
        default_runtime.AUTH_DB_PATH = self.auth_db
        default_runtime.USERS_DIR = self.users_dir
        server_runtime.bind_provider(lambda: default_runtime)
        user = create_user("MemoryApiUser", "password-1")
        token = create_session(int(user["id"]))
        store = MemoryStore()
        self.db = self.users_dir / "MemoryApiUser" / "hot100-study.db"
        store.save_candidate(
            user_db=self.db, candidate=MemoryPolicy().accept(_deterministic_candidate("记住我喜欢先讲思路")),
            source_session_id="s", source_message_id=1,
        )
        self.client = TestClient(app)
        self.client.cookies.set("forge_session", token)

    def tearDown(self):
        self.client.close()
        default_runtime._AUTH_READY = self.old_auth_ready
        default_runtime._LAST_SESSION_PURGE = self.old_last_purge
        server_runtime._provider = self.old_provider
        server_runtime._values = self.old_values
        self.temp.cleanup()

    def test_memory_api_is_current_user_scoped_and_deletable(self):
        response = self.client.get("/api/chat/memories")
        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["source_type"], "explicit")
        deleted = self.client.delete(f"/api/chat/memories/{item['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/chat/memories").json()["items"], [])


if __name__ == "__main__":
    unittest.main()
