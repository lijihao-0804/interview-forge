import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import interview_forge.ai.chat.service as chat_service_module
from interview_forge.ai.chat.context_builder import ContextBuilder
from interview_forge.ai.chat.service import ChatService
from interview_forge.ai.config import AIConfig
from interview_forge.ai.memory import (
    MemoryExtractor,
    MemoryPolicy,
    MemoryStore,
    memory_worthy,
)
from interview_forge.ai.memory.extractor import _deterministic_candidate
from interview_forge.api.app import app
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
        customary = self.candidate("通常我喜欢用 Python，但是刷题用 Java")
        self.assertEqual(customary.display_text, "通常我喜欢用 Python，但是刷题用 Java")

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

    def test_full_source_limits_secret_and_tail_opt_out_before_extraction(self):
        model = StructuredExtractorModel()
        extractor = MemoryExtractor()
        for message in [
            "记住我喜欢用 Python。" + "额外背景。" * 80 + "但这次不要保存到长期记忆。",
            "这次我偏好 Java，只在本次对话使用。",
            "请记住我喜欢先讲思路。" + "额外背景。" * 70 + "密码是占位文本。",
            "以后用 Python 回答：" + "项目范围。" * 70 + "唯一例外是线上讲解不用 Python。",
        ]:
            with self.subTest(message=message[-35:]):
                self.assertEqual(extractor.extract(message, model=model), [])
        self.assertEqual(model.calls, 0)

    def test_structured_extractor_preserves_qualified_wording_and_enforces_delete_intent(self):
        class ParaphrasingModel(StructuredExtractorModel):
            def invoke(self, messages):
                self.source = messages[-1][1]
                value = super().invoke(messages)
                value["candidates"][0].update(
                    display_text="优先讲项目风险", value={"text": "优先讲项目风险"},
                    canonical_key="preference.project_context",
                )
                return value

        model = ParaphrasingModel()
        message = "以后我希望优先讲项目风险，不过讲架构设计时不要这样做。"
        saved = MemoryExtractor().extract(message, model=model)
        self.assertEqual(model.source, message)
        self.assertEqual(saved[0].display_text, message)
        self.assertEqual(saved[0].value, {"text": message})
        self.assertFalse(saved[0].explicit)
        # The model calls this an upsert even though the actual request was to forget.
        self.assertEqual(MemoryExtractor().extract("请忘记我讨论项目背景的偏好", model=model), [])

    def test_memory_business_window_governs_explicit_and_background_calls(self):
        from dataclasses import replace

        chat = AIConfig(
            enabled=True, provider="openai-compatible", model="chat", base_url="https://example.invalid",
            api_key="test-key", wire_api="chat_completions", actor_authorization="", reasoning_effort="",
            thinking_enabled=False, request_timeout_seconds=10, max_concurrent_requests=2,
            daily_limit_per_user=3, beta_users="*",
        )
        configs = {
            "chat": SimpleNamespace(config=chat, capabilities={"context_window": 16_384}),
            "memory_extraction": SimpleNamespace(
                config=replace(chat, model="memory"), capabilities={"context_window": 580},
            ),
        }
        extractor_model = StructuredExtractorModel()
        service = ChatService(
            runtime_loader=configs.__getitem__,
            model_factory=lambda c: extractor_model if c.model == "memory" else FakeModel(),
        )
        session = service.create_session(user_db=self.db)
        async def chat_and_wait():
            explicit = await _collect_async(service.stream_reply(
                user_db=self.db, session_id=session["id"],
                message="请记住我希望日后从正在做的项目出发解释业务风险。",
            ))
            self.assertIn("没有成功保存", explicit[1]["data"]["delta"])
            await _collect_async(service.stream_reply(
                user_db=self.db, session_id=session["id"], message="以后我希望从正在做的项目解释业务风险。",
            ))
            await asyncio.gather(*service._background_memory_tasks)
        asyncio.run(chat_and_wait())
        self.assertEqual(extractor_model.calls, 0)
        self.assertEqual(MemoryStore().list_active(user_db=self.db), [])

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

    def test_retrieval_skips_irrelevant_high_importance_memory_but_keeps_stable_preference(self):
        from interview_forge.ai.memory.retriever import MemoryRetriever

        store = MemoryStore()
        store.save_candidate(
            user_db=self.db, candidate=self.candidate("记住我的长期目标是算法工程"),
            source_session_id="old-topic", source_message_id=1,
        )
        store.save_candidate(
            user_db=self.db, candidate=self.candidate("记住我喜欢先讲思路"),
            source_session_id="preference", source_message_id=2,
        )

        # A preference about explanation order applies to an explanation
        # request, while an unrelated high-importance career goal does not.
        result = MemoryRetriever(store).retrieve(
            user_db=self.db, query="请解释 HTTP/2 的多路复用"
        )
        self.assertEqual(
            {item.canonical_key for item in result}, {"preference.explanation_order"}
        )

        related = MemoryRetriever(store).retrieve(
            user_db=self.db, query="算法工程岗位面试应该怎么准备"
        )
        self.assertIn("goal.target_role", {item.canonical_key for item in related})

    def test_unrelated_high_importance_memory_does_not_create_context_block(self):
        from interview_forge.ai.memory import MemoryContextBuilder, MemoryRetriever

        store = MemoryStore()
        store.save_candidate(
            user_db=self.db, candidate=self.candidate("记住我的长期目标是算法工程"),
            source_session_id="old-topic", source_message_id=1,
        )
        self.assertIsNone(
            MemoryContextBuilder(retriever=MemoryRetriever(store)).build(
                user_db=self.db, query="为什么 TCP 关闭需要四次挥手"
            )
        )

    def test_personal_goal_and_time_limit_do_not_attach_to_generic_technical_words(self):
        from interview_forge.ai.memory import MemoryRetriever

        store = MemoryStore()
        for text in ("记住我的长期目标是算法工程", "记住我每天只有30分钟学习时间"):
            store.save_candidate(
                user_db=self.db, candidate=self.candidate(text),
                source_session_id="old-topic", source_message_id=1,
            )
        for query in ("算法复杂度是什么", "TCP 的 TIME_WAIT 持续多久", "解释向量的方向", "为什么缓存30分钟"):
            with self.subTest(query=query):
                self.assertEqual(MemoryRetriever(store).retrieve(user_db=self.db, query=query), [])

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
        context_message = next(item for item in messages if "ContextBlock:memory" in item["content"])
        self.assertEqual(context_message["role"], "user")
        self.assertIn("先讲思路", context_message["content"])
        self.assertIn("不可信上下文", context_message["content"])

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
        self.assertEqual(
            [item["role"] for item in ChatService.list_messages(user_db=self.db, session_id=session["id"])],
            ["user", "assistant"],
        )

    def test_chat_releases_session_and_model_slots_before_done(self):
        config = AIConfig(
            enabled=True, provider="openai-compatible", model="test", base_url="https://example.invalid",
            api_key="test-key", wire_api="chat_completions", actor_authorization="", reasoning_effort="",
            thinking_enabled=False, request_timeout_seconds=10, max_concurrent_requests=2,
            daily_limit_per_user=3, beta_users="*",
        )
        service = ChatService(config_loader=lambda: config, model_factory=lambda _config: FakeModel())
        service._process_memory = lambda **_kwargs: __import__("time").sleep(0.2)
        session = service.create_session(user_db=self.db)

        async def consume_until_done():
            async for item in service.stream_reply(
                user_db=self.db, session_id=session["id"], message="我的目标是提升算法能力"
            ):
                if item["event"] == "message.done":
                    with chat_service_module._ACTIVE_SESSIONS_LOCK:
                        self.assertFalse(chat_service_module._ACTIVE_SESSIONS)
                    with chat_service_module._ACTIVE_MODEL_CALLS_LOCK:
                        self.assertEqual(chat_service_module._ACTIVE_MODEL_CALLS, 0)
                    break

        asyncio.run(consume_until_done())

    def test_memory_words_in_normal_questions_do_not_trigger_explicit_persistence(self):
        from interview_forge.ai.memory.extractor import is_explicit_memory_request

        for message in (
            "为什么人会忘记东西？",
            "解释一下缓存为什么会忘记之前的数据",
            "不要忘了顺便讲一下时间复杂度",
        ):
            self.assertFalse(is_explicit_memory_request(message))

        keep = _deterministic_candidate("不要忘记我喜欢 Python")
        self.assertIsNotNone(keep)
        self.assertEqual(keep.operation, "upsert")
        self.assertEqual(keep.canonical_key, "preference.programming_language")
        forget = _deterministic_candidate("不要再记住我喜欢 Python")
        self.assertIsNotNone(forget)
        self.assertEqual(forget.operation, "forget")

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

    def test_durable_explicit_memory_keeps_source_turn_when_model_fails(self):
        class FailingBoundModel(FakeModel):
            def bind_tools(self, _schemas):
                return self

            async def astream(self, _messages):
                raise RuntimeError("provider failed after memory save")
                yield  # pragma: no cover

        config = AIConfig(
            enabled=True, provider="openai-compatible", model="test", base_url="https://example.invalid",
            api_key="test-key", wire_api="chat_completions", actor_authorization="", reasoning_effort="",
            thinking_enabled=False, request_timeout_seconds=10, max_concurrent_requests=2,
            daily_limit_per_user=3, beta_users="*",
        )
        service = ChatService(
            config_loader=lambda: config,
            model_factory=lambda _config: FailingBoundModel(),
        )
        session = service.create_session(user_db=self.db)
        events = _collect(service.stream_reply(
            user_db=self.db, session_id=session["id"], message="记住我喜欢 Python"
        ))
        self.assertEqual(events[-1]["event"], "error")
        history = ChatService.list_messages(user_db=self.db, session_id=session["id"])
        active = MemoryStore().list_active(user_db=self.db)
        self.assertEqual([item["role"] for item in history], ["user"])
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].source_message_id, history[0]["id"])

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
