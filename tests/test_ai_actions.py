import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from interview_forge.ai.actions.service import ActionService
from interview_forge.ai.actions.store import ActionRequestStore, ActionRequestError
from interview_forge.ai.chat.tool_orchestrator import ToolOrchestrator
from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolKind, ToolResult, ToolSpec
from interview_forge.ai.tools.langchain_adapter import NormalizedToolCall
from interview_forge.ai.tools.policy import ToolPolicy
from interview_forge.ai.tools.registry import ToolRegistry, build_default_tool_registry
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime


class SyncArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full: bool = False


class FakeChunk:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = list(tool_calls or [])
        self.tool_call_chunks = []
        self.usage_metadata = {}
        self.response_metadata = {}
        self.additional_kwargs = {}


class ScriptedModel:
    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.calls = 0
        self.seen = []

    def bind_tools(self, schemas):
        return self

    async def astream(self, messages):
        self.seen.append(messages)
        index = min(self.calls, len(self.rounds) - 1)
        self.calls += 1
        for chunk in self.rounds[index]:
            yield chunk


def _context(db: Path) -> ToolExecutionContext:
    return ToolExecutionContext(
        user_db=db, session_id="session", turn_id="turn", user_message_id=1,
        current_query="同步一下", artifacts={"username": "ActionUser"},
    )


async def _collect(orchestrator, model, context):
    return [item async for item in orchestrator.stream(
        model=model,
        messages=[{"role": "user", "content": "同步一下"}],
        context=context,
        fallback_stream_factory=lambda _model, _messages: _empty_stream(),
    )]


async def _empty_stream():
    if False:
        yield "", {}


class ActionToolTests(unittest.TestCase):
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

    def registry(self, calls):
        def handler(_context, args):
            calls.append(bool(args.full))
            return ToolResult({"task_id": "task-1", "status": "started", "full": bool(args.full)}, "已启动")

        return ToolRegistry([ToolSpec(
            name="sync_leetcode", display_name="同步 LeetCode", description="同步",
            args_model=SyncArgs, handler=handler, kind=ToolKind.ACTION,
            requires_confirmation=True,
            confirmation_builder=lambda args: "执行一次完整 LeetCode 历史同步" if args.full else "同步你的最新 LeetCode 学习记录",
        )])

    def test_action_call_creates_pending_confirmation_without_handler_execution(self):
        calls = []
        registry = self.registry(calls)
        model = ScriptedModel([
            [FakeChunk("我先请求确认", [{"id": "action-call", "name": "sync_leetcode", "args": {"full": False}}])],
            [FakeChunk("同步操作需要你的确认。")],
        ])
        events = asyncio.run(_collect(
            ToolOrchestrator(registry=registry), model, _context(self.db)
        ))
        self.assertEqual(calls, [])
        confirmation = next(item for item in events if item["event"] == "tool.confirmation_required")
        self.assertEqual(confirmation["data"]["name"], "sync_leetcode")
        self.assertEqual(confirmation["data"]["message"], "同步你的最新 LeetCode 学习记录")
        self.assertEqual(model.calls, 2)
        tool_message = next(item for item in model.seen[1] if item.get("role") == "tool")
        payload = json.loads(tool_message["content"])
        self.assertEqual(payload["error"]["code"], "confirmation_required")
        self.assertIn("action_id", payload)
        pending = ActionRequestStore().list_pending(user_db=self.db, session_id="session")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["arguments"], {"full": False})

    def test_confirm_executes_once_and_second_confirm_replays_safe_result(self):
        calls = []
        registry = self.registry(calls)
        action = ActionRequestStore().create(
            user_db=self.db, session_id="session", turn_id="turn", user_message_id=1,
            tool_name="sync_leetcode", arguments={"full": True}, confirmation_text="确认同步",
        )
        service = ActionService(registry=registry)
        first = asyncio.run(service.confirm(user_db=self.db, action_id=action["action_id"]))
        second = asyncio.run(service.confirm(user_db=self.db, action_id=action["action_id"]))
        self.assertTrue(first["ok"])
        self.assertEqual(first["status"], "succeeded")
        self.assertTrue(second["ok"])
        self.assertEqual(second["status"], "succeeded")
        self.assertEqual(calls, [True])
        row = ActionRequestStore().get(user_db=self.db, action_id=action["action_id"])
        self.assertEqual(row["status"], "succeeded")

    def test_cancel_and_expired_action_never_execute(self):
        calls = []
        registry = self.registry(calls)
        store = ActionRequestStore()
        cancelled = store.create(
            user_db=self.db, session_id="session", turn_id="turn", user_message_id=1,
            tool_name="sync_leetcode", arguments={"full": False}, confirmation_text="确认",
        )
        result = asyncio.run(ActionService(registry=registry).cancel(
            user_db=self.db, action_id=cancelled["action_id"]
        ))
        self.assertEqual(result["status"], "cancelled")
        with self.assertRaises(ActionRequestError):
            asyncio.run(ActionService(registry=registry).confirm(
                user_db=self.db, action_id=cancelled["action_id"]
            ))

        expired = store.create(
            user_db=self.db, session_id="session", turn_id="turn", user_message_id=1,
            tool_name="sync_leetcode", arguments={"full": False}, confirmation_text="确认",
        )
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "UPDATE chat_action_requests SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
                (expired["action_id"],),
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(ActionRequestError):
            asyncio.run(ActionService(registry=registry).confirm(
                user_db=self.db, action_id=expired["action_id"]
            ))
        self.assertEqual(calls, [])

    def test_confirm_uses_stored_arguments_and_other_user_db_cannot_access(self):
        calls = []
        registry = self.registry(calls)
        store = ActionRequestStore()
        action = store.create(
            user_db=self.db, session_id="session", turn_id="turn", user_message_id=1,
            tool_name="sync_leetcode", arguments={"full": False}, confirmation_text="确认",
        )
        other_db = Path(self.temp.name) / "other.db"
        with self.assertRaises(ActionRequestError) as caught:
            asyncio.run(ActionService(registry=registry).confirm(
                user_db=other_db, action_id=action["action_id"]
            ))
        self.assertEqual(caught.exception.status, 404)
        result = asyncio.run(ActionService(registry=registry).confirm(
            user_db=self.db, action_id=action["action_id"]
        ))
        self.assertTrue(result["ok"])
        self.assertEqual(calls, [False])

    def test_claim_is_exactly_once(self):
        store = ActionRequestStore()
        action = store.create(
            user_db=self.db, session_id="session", turn_id="turn", user_message_id=1,
            tool_name="sync_leetcode", arguments={"full": False}, confirmation_text="确认",
        )
        first = store.claim_pending(user_db=self.db, action_id=action["action_id"])
        second = store.claim_pending(user_db=self.db, action_id=action["action_id"])
        self.assertTrue(first["_claimed"])
        self.assertFalse(second["_claimed"])
        self.assertEqual(second["status"], "executing")

    def test_default_leetcode_action_missing_credentials_is_safe_failure(self):
        registry = build_default_tool_registry()
        action = ActionRequestStore().create(
            user_db=self.db, session_id="session", turn_id="turn", user_message_id=1,
            tool_name="sync_leetcode", arguments={"full": False}, confirmation_text="确认",
        )
        result = asyncio.run(ActionService(registry=registry).confirm(
            user_db=self.db, action_id=action["action_id"]
        ))
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["result"]["error"]["code"], "not_configured")


if __name__ == "__main__":
    unittest.main()
