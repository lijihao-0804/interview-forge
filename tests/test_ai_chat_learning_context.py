import asyncio
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from interview_forge.ai.chat.learning_context import (
    LearningContextProvider,
    select_learning_task,
)
from interview_forge.ai.chat.service import ChatService
from interview_forge.ai.config import AIConfig
from interview_forge.ai.context_projection import project_learning_context_for_chat
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime


def _compiled_context(task="learning_diagnosis"):
    return {
        "context_schema_version": "context-v1",
        "task": task,
        "user_request": "不应进入聊天 projection 的原始查询",
        "profile": {"learning_goal": "掌握算法基础", "available_minutes": 30},
        "summary": {"availability": "unavailable"} if task == "learning_route" else {"active_days": {"7d": 2}},
        "diagnostic_digest": {
            "version": "diagnostic-digest-v2",
            "overview": {"weak_problem_count": 2},
            "review_backlog": {"total": 2},
            "coverage": {"source_data_missing": {"tables": []}},
            "representative_cases": [{"ref": "p1", "case_type": "repeat_wa", "title": "题目"}],
            "anomalies": [{"type": "stale", "example_refs": ["p1"]}],
        },
        "facts": [
            {
                "entity_type": "problem",
                "problem_id": 146,
                "title": "哈希题",
                "difficulty": "中等",
                "wa_count": {"30d": 3},
                "metric_ids": {"wa": "metric:secret"},
            },
            {
                "entity_type": "module",
                "module_id": "module-secret",
                "title": "模块",
                "module_due_count": 1,
            },
        ],
        "signals": [
            {
                "signal_id": "signal:secret",
                "signal_type": "repeat_wa",
                "entity_type": "problem",
                "problem_id": 146,
                "severity": "high",
                "confidence": "high",
                "evidence_ids": ["evidence:secret"],
            }
        ],
        "evidence": [{"evidence_id": "evidence:secret", "facts": {"password": "no"}}],
        "trace_map": {"p1": {"semantic_fact": {"title": "内部"}}},
        "data_quality": {"status": "attention", "reason_codes": ["no_learning_data"]},
        "data_as_of": "2026-09-12T10:00:00+08:00",
    }


class LearningContextSelectorTests(unittest.TestCase):
    def test_selector_is_explicit_and_normal_chat_is_none(self):
        self.assertIsNone(select_learning_task("你好"))
        self.assertIsNone(select_learning_task("解释TCP"))
        self.assertEqual(select_learning_task("今天复习什么"), {"task": "today_plan", "budget_tier": "small"})
        self.assertEqual(select_learning_task("最近学得怎么样"), {"task": "learning_diagnosis", "budget_tier": "medium"})
        self.assertEqual(select_learning_task("学习路线"), {"task": "learning_route", "budget_tier": "medium"})
        self.assertEqual(
            select_learning_task("146题为什么错"),
            {"task": "problem_review", "target_problem_id": 146, "budget_tier": "medium"},
        )

    def test_normal_chat_does_not_call_analytics_or_compiler(self):
        provider = LearningContextProvider()
        with patch("interview_forge.ai.chat.learning_context.analytics_cached") as analytics, patch(
            "interview_forge.ai.chat.learning_context.compile_learning_context"
        ) as compiler:
            self.assertIsNone(provider.build(user_db=Path("unused.db"), query="你好"))
        analytics.assert_not_called()
        compiler.assert_not_called()

    def test_learning_selectors_call_compiler_without_repeating_query(self):
        provider = LearningContextProvider()
        compiled = _compiled_context()
        with patch(
            "interview_forge.ai.chat.learning_context.analytics_cached",
            return_value={"data_quality": {"status": "ok"}},
        ), patch(
            "interview_forge.ai.chat.learning_context.compile_learning_context",
            return_value=compiled,
        ) as compiler:
            diagnosis = provider.build(user_db=Path("alice.db"), query="最近状态")
            today = provider.build(user_db=Path("alice.db"), query="今天做什么")
            review = provider.build(user_db=Path("alice.db"), query="146题掌握情况")

        self.assertEqual(diagnosis["task"], "learning_diagnosis")
        self.assertEqual(today["task"], "today_plan")
        self.assertEqual(review["target_problem_id"], 146)
        calls = compiler.call_args_list
        self.assertEqual([call.kwargs["budget_tier"] for call in calls], ["medium", "small", "medium"])
        self.assertTrue(all(call.kwargs["user_request"] == "" for call in calls))
        self.assertNotIn("最近状态", json.dumps(diagnosis["projection"], ensure_ascii=False))

    def test_chat_projection_is_bounded_and_keeps_quality_without_trace_material(self):
        context = _compiled_context()
        context["facts"] = context["facts"] * 20
        context["signals"] = context["signals"] * 20
        projection = project_learning_context_for_chat(context, max_chars=900)
        serialized = json.dumps(projection, ensure_ascii=False, separators=(",", ":"))
        self.assertLessEqual(len(serialized), 900)
        self.assertEqual(projection["data_quality"]["status"], "attention")
        self.assertTrue(projection["related_problem_facts"] or projection["data_quality"])
        for forbidden in ("trace_map", "evidence", "metric:", "signal_id", "evidence_ids"):
            self.assertNotIn(forbidden, serialized)


class ChatLearningContextIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.old_provider = server_runtime._provider
        self.old_values = dict(server_runtime._values)
        self.old_auth_ready = default_runtime._AUTH_READY
        self.old_last_purge = default_runtime._LAST_SESSION_PURGE
        default_runtime._AUTH_READY = False
        default_runtime._LAST_SESSION_PURGE = 0.0
        default_runtime.AUTH_DB_PATH = root / "auth.db"
        default_runtime.USERS_DIR = root / "users"
        default_runtime.USERS_DIR.mkdir()
        server_runtime.bind_provider(lambda: default_runtime)
        self.db = default_runtime.USERS_DIR / "Alice" / "hot100-study.db"
        self.db.parent.mkdir()

    def tearDown(self):
        default_runtime._AUTH_READY = self.old_auth_ready
        default_runtime._LAST_SESSION_PURGE = self.old_last_purge
        server_runtime._provider = self.old_provider
        server_runtime._values = self.old_values
        self.temp.cleanup()

    def test_compiled_learning_projection_enters_final_chat_context(self):
        captured: list[dict[str, str]] = []

        async def stream_factory(_model, messages):
            captured.extend(messages)
            yield "回答", {}

        fake_provider = Mock()
        fake_provider.build.return_value = {
            "task": "learning_diagnosis",
            "projection": {
                "llm_context_version": "learning-chat-context-v1",
                "task": "learning_diagnosis",
                "diagnostic_digest": {"overview": {"weak_problem_count": 2}},
                "selected_facts": [{"entity_type": "problem", "problem_id": 146}],
                "data_quality": {"status": "ok"},
            },
        }
        config = AIConfig(
            enabled=True,
            provider="openai-compatible",
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="test-key",
            wire_api="chat_completions",
            actor_authorization="",
            reasoning_effort="",
            thinking_enabled=False,
            request_timeout_seconds=45.0,
            max_concurrent_requests=2,
            daily_limit_per_user=3,
            beta_users="*",
        )
        service = ChatService(
            config_loader=lambda: config,
            model_factory=lambda _config: object(),
            stream_factory=stream_factory,
        )
        session = service.create_session(user_db=self.db)
        with patch("interview_forge.ai.chat.service.LearningContextProvider", return_value=fake_provider):
            events = asyncio.run(
                _collect(
                    service.stream_reply(
                        user_db=self.db,
                        session_id=session["id"],
                        message="最近状态",
                    )
                )
            )
        self.assertEqual([event["event"] for event in events], ["message.start", "message.delta", "message.done"])
        self.assertIn("Learning Context", captured[0]["content"])
        self.assertIn("weak_problem_count", captured[0]["content"])
        self.assertNotIn("最近状态", captured[0]["content"])
        self.assertEqual(captured[-1], {"role": "user", "content": "最近状态"})


async def _collect(iterator):
    return [item async for item in iterator]


if __name__ == "__main__":
    unittest.main()
