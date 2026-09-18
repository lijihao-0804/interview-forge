import asyncio
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from interview_forge.ai.actions.service import ActionService
from interview_forge.ai.actions.store import ActionRequestStore
from interview_forge.ai.chat.recent_action_context import RecentActionContextProvider
from interview_forge.ai.tools.contracts import ToolExecutionContext
from interview_forge.ai.tools.langchain_adapter import NormalizedToolCall
from interview_forge.ai.tools.registry import build_default_tool_registry
from interview_forge.ai.tools.runtime import ToolRuntime
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime
from interview_forge.services import submissions


def _load_eval_module():
    path = Path(__file__).parents[1] / "scripts" / "check" / "ai_agent_eval.py"
    spec = importlib.util.spec_from_file_location("ai_agent_eval", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class M7ToolPackTests(unittest.TestCase):
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

    def context(self, session_id="session"):
        return ToolExecutionContext(
            user_db=self.db, session_id=session_id, turn_id="turn",
            user_message_id=1, current_query="test", artifacts={"username": "M7"},
        )

    def test_registry_contains_five_m7_tools_with_expected_kinds(self):
        registry = build_default_tool_registry()
        self.assertEqual(len(registry), 9)
        self.assertEqual(
            {spec.name for spec in registry.list_specs() if spec.kind.value == "read"},
            {"get_problem", "get_learning_context", "get_weather", "get_problem_progress", "get_review_queue"},
        )
        self.assertEqual(
            {spec.name for spec in registry.list_specs() if spec.kind.value == "action"},
            {"sync_leetcode", "mark_problem", "pin_problem_for_tomorrow", "set_daily_goal"},
        )
        self.assertTrue(all(spec.requires_confirmation for spec in registry.list_specs() if spec.kind.value == "action"))

    def test_progress_read_is_compact_and_uses_real_submission_data(self):
        submissions.record_submission(146, "wa", db_path=self.db)
        submissions.record_submission(146, "ac", db_path=self.db)
        from interview_forge.ai.tools.builtins.progress import GetProblemProgressArgs, get_problem_progress

        result = get_problem_progress(self.context(), GetProblemProgressArgs(problem_id=146))
        progress = result.data["problem"]
        self.assertEqual(progress["problem_id"], 146)
        self.assertEqual(progress["submits"], 2)
        self.assertEqual(progress["ac_submits"], 1)
        self.assertEqual(progress["last_status"], "ac")
        self.assertIn("next_due", progress)
        self.assertNotIn("password", str(result.data))

    def test_review_queue_uses_service_and_applies_limit(self):
        from interview_forge.ai.tools.builtins.review import GetReviewQueueArgs, get_review_queue

        daily = {
            "today": "2026-09-14",
            "problems": [
                {"id": 146, "title": "L", "due_date": "2026-09-13"},
                {"id": 1, "title": "T", "due_date": "2026-09-14"},
            ],
            "relearn": [],
        }
        with patch("interview_forge.ai.tools.builtins.review.study.daily_data", return_value=daily), \
             patch("interview_forge.ai.tools.builtins.review.study.problem_marks", return_value={"146": "weak"}):
            result = get_review_queue(self.context(), GetReviewQueueArgs(limit=1))
        self.assertEqual(result.data["overdue"], 1)
        self.assertEqual(result.data["due_today"], 1)
        self.assertEqual(result.data["total"], 2)
        self.assertEqual(len(result.data["items"]), 1)
        self.assertEqual(result.data["items"][0]["problem_id"], 146)

    def test_new_actions_require_confirmation_and_execute_once(self):
        registry = build_default_tool_registry()
        runtime = ToolRuntime(registry)
        cases = [
            ("mark_problem", {"problem_id": 146, "mark": "weak"}),
            ("pin_problem_for_tomorrow", {"problem_id": 146}),
            ("set_daily_goal", {"rounds": 5}),
        ]
        for index, (name, arguments) in enumerate(cases):
            context = self.context(session_id=f"s-{index}")
            result = asyncio.run(runtime.execute(
                call=NormalizedToolCall(f"call-{index}", name, arguments), context=context
            ))
            self.assertEqual(result.status, "confirmation_required")
            self.assertIsNotNone(result.action_id)
            service = ActionService(registry=registry)
            first = asyncio.run(service.confirm(user_db=self.db, action_id=str(result.action_id)))
            second = asyncio.run(service.confirm(user_db=self.db, action_id=str(result.action_id)))
            self.assertTrue(first["ok"], name)
            self.assertTrue(second["ok"], name)
            self.assertEqual(first["status"], "succeeded")
            self.assertEqual(second["status"], "succeeded")

    def test_recent_action_context_hides_arguments_ids_and_result_body(self):
        store = ActionRequestStore()
        action = store.create(
            user_db=self.db, session_id="recent", turn_id="t", user_message_id=1,
            tool_name="mark_problem", arguments={"problem_id": 146, "mark": "weak"},
            confirmation_text="确认",
        )
        store.claim_pending(user_db=self.db, action_id=action["action_id"])
        store.complete(
            user_db=self.db, action_id=action["action_id"], status="succeeded",
            error_code=None, result_meta={"secret": "do-not-show"},
        )
        block = RecentActionContextProvider().build(user_db=self.db, session_id="recent")
        self.assertIsNotNone(block)
        self.assertIn("题目标记", block.content)
        self.assertIn("已成功", block.content)
        self.assertNotIn("146", block.content)
        self.assertNotIn("do-not-show", block.content)
        self.assertNotIn(action["action_id"], block.content)

    def test_golden_fixture_deterministic_evaluation(self):
        evaluator = _load_eval_module()
        cases = evaluator.load_cases()
        self.assertGreaterEqual(len(cases), 40)
        result = evaluator.evaluate_cases(cases, build_default_tool_registry())
        self.assertEqual(result.failures, [])
        self.assertEqual(result.passed, result.total)


if __name__ == "__main__":
    unittest.main()
