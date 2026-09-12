import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolKind, ToolResult, ToolSpec
from interview_forge.ai.tools.langchain_adapter import NormalizedToolCall, tool_spec_schema
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


if __name__ == "__main__":
    unittest.main()
