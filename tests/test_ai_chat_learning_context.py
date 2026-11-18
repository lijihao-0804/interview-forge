import asyncio
import json
import tempfile
import unittest
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
    def test_review_mode_only_uses_relevant_learning_records(self):
        provider = LearningContextProvider()
        with patch.object(provider, "_build_selection", side_effect=lambda **kw: kw["selection"]):
            def select(query, page_id=None):
                return provider.build(user_db=Path("unused"), query=query, study_mode="review", page_problem_id=page_id)

            self.assertEqual(select("第146题", 1)["target_problem_id"], 146)
            self.assertEqual(select("146", 1)["target_problem_id"], 146)
            self.assertEqual(select("今天刷了 3 题，想复习第 146 道题")["target_problem_id"], 146)
            self.assertEqual(select("重做146题")["target_problem_id"], 146)
            for query in ("本周我只做了 1 题，该怎么复习？", "每天复习 3 题合适吗？", "今天完成了 3 道题", "复习前 3 题"):
                self.assertIsNone(select(query), query)
            self.assertEqual(select("这题呢", 1)["target_problem_id"], 1)
            self.assertEqual(select("今天做什么", 1)["task"], "today_plan")
            self.assertEqual(select("复盘一下最近的学习情况")["task"], "learning_diagnosis")
            self.assertEqual(select("最近哪些题值得再做？")["task"], "today_plan")
            self.assertIsNone(select("解释 TCP 慢启动"))

    def test_mode_blocks_fit_system_slot_and_compact_code_keeps_output(self):
        from interview_forge.ai.chat.context_builder import ContextBuilder
        from interview_forge.ai.chat.study_modes import study_blocks

        for mode in ("hint", "review", "code"):
            blocks = study_blocks(mode, None)
            builder = ContextBuilder(context_blocks=blocks)
            system, data, admitted, rejected = builder._contextual_content()
            self.assertEqual((admitted, rejected, data), (["study_mode"], [], ""))
            self.assertLessEqual(builder.estimator.estimate_text(system), builder.budget.system_tokens)
        snapshot = "编辑器头部" + "代码" * 3500 + "运行结果尾部"
        block = study_blocks("code", snapshot)[-1]
        compact = block.fit(500, builder.estimator)
        self.assertIn("编辑器头部", compact)
        self.assertIn("运行结果尾部", compact)
        self.assertLessEqual(builder.estimator.estimate_text(compact), 500)

    def test_small_window_keeps_mode_pending_confirmation_and_write_receipt(self):
        from interview_forge.ai.chat.context_builder import ContextBuilder
        from interview_forge.ai.chat.recent_action_context import RecentActionContextProvider
        from interview_forge.ai.chat.study_modes import study_blocks
        from interview_forge.ai.chat.token_budget import budget_for_context_window
        from interview_forge.ai.memory.contracts import MemoryPersistenceResult

        with patch("interview_forge.ai.chat.recent_action_context.ActionRequestStore") as store:
            pending = {"tool_name": "mark_problem", "created_at": "2026-01-02T04:00:00Z"}
            store.return_value.list_pending.return_value = [pending] * 4
            store.return_value.list_recent.return_value = []
            action = RecentActionContextProvider().build(user_db="unused", session_id="test")
        receipt = ChatService._memory_persistence_block(MemoryPersistenceResult(True, True, "upsert", 1))
        for mode in ("hint", "review", "code"):
            blocks = [receipt, action, *study_blocks(mode, None)]
            builder = ContextBuilder(context_blocks=blocks, budget=budget_for_context_window(4096))
            system, _, admitted, rejected = builder._contextual_content()
            self.assertCountEqual(admitted, ["memory_persistence", "recent_actions", "study_mode"])
            self.assertFalse(rejected)
            self.assertIn("存在仍在等待用户确认的操作", system)
            self.assertIn("persistence_success=true", system)
            if mode == "code":
                self.assertIn("本轮未附练习快照", system)
            self.assertLessEqual(builder.estimator.estimate_text(system), builder.budget.system_tokens)

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

    def test_compiler_failure_degrades_and_logs_only_safe_category(self):
        provider = LearningContextProvider()
        with patch(
            "interview_forge.ai.chat.learning_context.analytics_cached",
            side_effect=RuntimeError("password=should-not-be-logged"),
        ), patch(
            "interview_forge.ai.chat.learning_context.debug_ai_event"
        ) as telemetry:
            result = provider.build(user_db=Path("alice.db"), query="最近状态")

        self.assertFalse(result["available"])
        telemetry.assert_called_once_with(
            "chat_learning_context_failed",
            task="learning_diagnosis",
            error_type="RuntimeError",
        )
        serialized = json.dumps(telemetry.call_args.kwargs, ensure_ascii=False)
        self.assertNotIn("password", serialized)
        self.assertNotIn("should-not-be-logged", serialized)

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

    def test_budget_keeps_ranked_items_before_duplicate_problem_views(self):
        context = _compiled_context("today_plan")
        context["facts"].reverse()  # A module ranked ahead of a problem.
        full = project_learning_context_for_chat(context)
        expected = {**full, "related_problem_facts": []}
        limit = len(json.dumps(expected, ensure_ascii=False, separators=(",", ":")))
        compact = project_learning_context_for_chat(context, max_chars=limit)
        self.assertEqual(compact["selected_facts"], full["selected_facts"])
        self.assertEqual(compact["signals"], full["signals"])

    def test_unavailable_route_remains_explicit_with_no_digest(self):
        context = _compiled_context("learning_route")
        del context["diagnostic_digest"]
        with patch("interview_forge.ai.chat.learning_context.analytics_cached"), patch(
            "interview_forge.ai.chat.learning_context.compile_learning_context", return_value=context
        ):
            result = LearningContextProvider().build_for_task(user_db=Path("unused.db"), task="learning_route")
        self.assertFalse(result["available"])
        self.assertEqual(result["projection"]["diagnostic_digest"]["overview"]["availability"], "unavailable")

    def test_good_source_quality_cannot_mask_failed_compilation(self):
        with patch("interview_forge.ai.chat.learning_context.analytics_cached",
                   return_value={"data_quality": {"status": "ok"}}), patch(
            "interview_forge.ai.chat.learning_context.compile_learning_context", side_effect=ValueError()
        ):
            result = LearningContextProvider().build_for_task(user_db=Path("unused.db"), task="today_plan")
        self.assertFalse(result["available"])
        self.assertEqual(result["projection"]["data_quality"]["status"], "unavailable")


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
        context_message = next(item for item in captured if "ContextBlock:learning" in item["content"])
        self.assertEqual(context_message["role"], "user")
        self.assertIn("weak_problem_count", context_message["content"])
        self.assertNotIn("最近状态", context_message["content"])
        self.assertNotIn("ContextBlock:learning", captured[0]["content"])
        self.assertEqual(captured[-1], {"role": "user", "content": "最近状态"})


async def _collect(iterator):
    return [item async for item in iterator]


if __name__ == "__main__":
    unittest.main()
