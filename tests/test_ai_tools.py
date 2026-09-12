import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolKind, ToolResult, ToolSpec
from interview_forge.ai.tools.langchain_adapter import (
    NormalizedToolCall,
    ToolCallAccumulator,
    tool_spec_schema,
)
from interview_forge.ai.tools.registry import ToolRegistry
from interview_forge.ai.tools.runtime import ToolRuntime
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


def _context(path: Path) -> ToolExecutionContext:
    return ToolExecutionContext(
        user_db=path, session_id="session", turn_id="turn", user_message_id=1,
        current_query="test",
    )


class ToolInfrastructureTests(unittest.TestCase):
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

    def test_duplicate_registry_and_schema_boundary(self):
        spec = ToolSpec("read_value", "读取值", "读取一个值", Args, lambda _c, _a: {"ok": True})
        registry = ToolRegistry([spec])
        with self.assertRaises(ValueError):
            registry.register(spec)
        schema = tool_spec_schema(spec)
        self.assertNotIn("user_id", json.dumps(schema))
        self.assertNotIn("db_path", json.dumps(schema))
        self.assertFalse(schema["function"]["parameters"]["additionalProperties"])

    def test_streaming_tool_chunks_keep_id_and_index_in_one_call(self):
        accumulator = ToolCallAccumulator()
        accumulator.add(type("Chunk", (), {"tool_call_chunks": [{
            "id": "call-weather",
            "index": 0,
            "name": "get_weather",
            "args": '{"location":',
        }]})())
        accumulator.add(type("Chunk", (), {"tool_call_chunks": [{
            "id": None,
            "index": 0,
            "name": None,
            "args": '"南京"}',
        }]})())
        calls = accumulator.finish()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].call_id, "call-weather")
        self.assertEqual(calls[0].name, "get_weather")
        self.assertEqual(calls[0].arguments, {"location": "南京"})

    def test_unknown_tool_invalid_extra_timeout_exception_and_large_result(self):
        async def slow(_context, _args):
            await asyncio.sleep(0.05)

        def broken(_context, _args):
            raise RuntimeError("password=secret")

        def huge(_context, _args):
            return {"value": "x" * 100}

        registry = ToolRegistry([
            ToolSpec("slow", "慢", "慢", Args, slow, timeout_seconds=0.005),
            ToolSpec("broken", "坏", "坏", Args, broken),
            ToolSpec("huge", "大", "大", Args, huge, max_result_tokens=2),
        ])
        runtime = ToolRuntime(registry)

        async def exercise():
            ctx = _context(self.db)
            unknown = await runtime.execute(
                call=NormalizedToolCall("u", "missing", {}), context=ctx
            )
            invalid = await runtime.execute(
                call=NormalizedToolCall("i", "slow", {"value": "x", "shell": "rm -rf /"}), context=ctx
            )
            timeout = await runtime.execute(
                call=NormalizedToolCall("t", "slow", {"value": "x"}), context=ctx
            )
            error = await runtime.execute(
                call=NormalizedToolCall("e", "broken", {"value": "x"}), context=ctx
            )
            large = await runtime.execute(
                call=NormalizedToolCall("l", "huge", {"value": "x"}), context=ctx
            )
            return unknown, invalid, timeout, error, large

        unknown, invalid, timeout, error, large = asyncio.run(exercise())
        self.assertEqual(unknown.error_code, "unknown_tool")
        self.assertEqual(invalid.error_code, "invalid_arguments")
        self.assertEqual(timeout.error_code, "timeout")
        self.assertEqual(error.error_code, "tool_error")
        self.assertNotIn("password", json.dumps(error.model_payload(), ensure_ascii=False))
        self.assertEqual(large.error_code, "result_too_large")

    def test_read_cache_and_action_confirmation_audit(self):
        calls = []

        def read(_context, args):
            calls.append(args.value)
            return ToolResult({"value": args.value}, display_text="已读取")

        registry = ToolRegistry([
            ToolSpec("read", "读", "读", Args, read),
            ToolSpec("action", "动作", "动作", Args, read, kind=ToolKind.ACTION, requires_confirmation=True),
        ])
        runtime = ToolRuntime(registry)

        async def exercise():
            ctx = _context(self.db)
            first = await runtime.execute(
                call=NormalizedToolCall("a", "read", {"value": "same"}), context=ctx
            )
            second = await runtime.execute(
                call=NormalizedToolCall("b", "read", {"value": "same"}), context=ctx
            )
            action = await runtime.execute(
                call=NormalizedToolCall("c", "action", {"value": "same"}), context=ctx
            )
            return first, second, action

        first, second, action = asyncio.run(exercise())
        self.assertEqual(calls, ["same"])
        self.assertEqual(first.status, "ok")
        self.assertTrue(second.cache_hit)
        self.assertEqual(action.status, "confirmation_required")
        connection = server_runtime.connect(self.db)
        try:
            rows = connection.execute(
                "SELECT status, result_meta_json FROM chat_tool_runs ORDER BY created_at, id"
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual(sorted(row[0] for row in rows), ["cache_hit", "confirmation_required", "success"])
        self.assertTrue(any(row[0] == "cache_hit" and '"cache_hit":true' in row[1] for row in rows))

    def test_default_read_tools_problem_learning_weather_and_no_cross_user_db(self):
        from unittest.mock import patch

        from interview_forge.ai.tools.builtins.learning import GetLearningContextArgs, get_learning_context
        from interview_forge.ai.tools.builtins.problem import GetProblemArgs, get_problem
        from interview_forge.ai.tools.builtins.weather import GetWeatherArgs, get_weather
        from interview_forge.ai.tools.registry import build_default_tool_registry

        registry = build_default_tool_registry()
        self.assertEqual({spec.name for spec in registry.list_specs()}, {
            "get_problem", "get_learning_context", "get_weather", "sync_leetcode"
        })
        ctx = _context(self.db)
        problem = get_problem(ctx, GetProblemArgs(problem_id=146))
        self.assertTrue(problem.data["found"])
        self.assertEqual(problem.data["problem"]["problem_id"], 146)
        missing = get_problem(ctx, GetProblemArgs(problem_id=999999))
        self.assertFalse(missing.data["found"])

        with patch(
            "interview_forge.ai.tools.builtins.learning.LearningContextProvider.build_for_task",
            return_value={"task": "learning_diagnosis", "available": True,
                          "projection": {"task": "learning_diagnosis"}, "data_quality": {}},
        ) as compiler:
            learning = get_learning_context(
                ctx, GetLearningContextArgs(task="learning_diagnosis")
            )
        self.assertTrue(learning.data["available"])
        compiler.assert_called_once()
        preloaded_context = _context(self.db,)
        preloaded_context.artifacts["learning_context"] = {
            "task": "learning_diagnosis", "target_problem_id": None,
            "available": True, "projection": {"task": "learning_diagnosis"},
            "data_quality": {},
        }
        with patch(
            "interview_forge.ai.tools.builtins.learning.LearningContextProvider.build_for_task"
        ) as duplicate_compiler:
            reused = get_learning_context(
                preloaded_context, GetLearningContextArgs(task="learning_diagnosis")
            )
        duplicate_compiler.assert_not_called()
        self.assertTrue(reused.data["reused_preloaded"])
        with self.assertRaises(Exception):
            GetLearningContextArgs(task="problem_review")

        weather_payload = {
            "location": {"display_name": "南京", "mode": "default"},
            "current": {"temperature": 24, "apparent_temperature": 25, "description": "晴", "icon": "☀️"},
            "daily": {"temperature_max": 28, "temperature_min": 22, "precipitation_probability_max": 0},
            "updated_at": "now", "stale": False,
        }
        with patch("interview_forge.ai.tools.builtins.weather.weather_for_user", return_value=weather_payload):
            weather = get_weather(ctx, GetWeatherArgs())
        self.assertEqual(weather.data["location"]["display_name"], "南京")
        with patch("interview_forge.ai.tools.builtins.weather.weather_for_location", return_value=weather_payload) as city_weather:
            get_weather(ctx, GetWeatherArgs(location="上海"))
        city_weather.assert_called_once_with("上海")

        other = ToolExecutionContext(
            user_db=Path("other-user") / "hot100-study.db", session_id="s", turn_id="t",
            user_message_id=1, current_query="x",
        )
        with patch("interview_forge.ai.tools.builtins.weather.weather_for_user", return_value=weather_payload) as weather_call:
            get_weather(other, GetWeatherArgs())
        self.assertEqual(weather_call.call_args.args[0], "other-user")


if __name__ == "__main__":
    unittest.main()
