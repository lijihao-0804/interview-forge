import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict

from interview_forge.ai.chat import tool_orchestrator as orchestrator_module
from interview_forge.ai.chat.tool_orchestrator import ToolOrchestrator
from interview_forge.ai.errors import AIServiceError
from interview_forge.ai.token_counting import estimate_json_tokens
from interview_forge.ai.tools.contracts import (
    ToolExecutionContext,
    ToolKind,
    ToolResult,
    ToolSpec,
)
from interview_forge.ai.tools.policy import ToolPolicy
from interview_forge.ai.tools.registry import ToolRegistry
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime

ADMISSION_METADATA_KEYS = {
    "context_budget_policy_version",
    "request_fingerprint",
    "original_prompt_tokens",
    "admitted_prompt_tokens",
    "masked_tool_result_count",
    "tool_result_tokens_saved",
    "budget_rejected_tool_result_count",
    "omitted_exchange_count",
    "context_window",
    "reserved_output_tokens",
    "stop_reason",
}


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValueArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


class FakeChunk:
    def __init__(self, content="", tool_calls=None, usage=None):
        self.content = content
        self.tool_calls = list(tool_calls or [])
        self.tool_call_chunks = []
        self.usage_metadata = usage or {}
        self.response_metadata = {}
        self.additional_kwargs = {}


class ScriptedModel:
    def __init__(self, rounds, *, bind=True):
        self.rounds = list(rounds)
        self.bind_enabled = bind
        self.calls = 0
        self.seen = []
        self.tool_schemas = None

    def bind_tools(self, schemas):
        if not self.bind_enabled:
            raise AttributeError("no bind_tools")
        self.tool_schemas = list(schemas)
        return self

    async def astream(self, messages):
        self.seen.append(list(messages))
        index = min(self.calls, len(self.rounds) - 1)
        self.calls += 1
        for chunk in self.rounds[index]:
            await asyncio.sleep(0)
            yield chunk


class TraceSpy:
    def __init__(self):
        self.records = []

    def record(self, **kwargs):
        self.records.append(kwargs)

    def record_llm_round(self, **_kwargs):
        return None


def _context(path: Path, *, artifacts=None, query="当前问题必须保留"):
    return ToolExecutionContext(
        user_db=path,
        session_id="session",
        turn_id="turn",
        user_message_id=1,
        current_query=query,
        artifacts=dict(artifacts or {}),
    )


async def _collect(orchestrator, model, context, messages=None, fallback=None):
    return [
        item async for item in orchestrator.stream(
            model=model,
            messages=list(messages or [{"role": "user", "content": context.current_query}]),
            context=context,
            fallback_stream_factory=fallback or (lambda _model, _messages: _empty_stream()),
        )
    ]


async def _empty_stream():
    if False:
        yield "", {}


class AgentRuntimeGovernanceTests(unittest.IsolatedAsyncioTestCase):
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

    def test_explicit_empty_registry_keeps_tools_disabled(self):
        model = ScriptedModel([
            [FakeChunk("", [{
                "id": "default-call",
                "name": "get_problem",
                "args": {"problem_id": 146},
            }])],
            [FakeChunk("工具未启用")],
        ])

        with patch(
            "interview_forge.ai.tools.builtins.problem.get_problem",
            return_value=ToolResult({"found": True}),
        ) as default_handler:
            orchestrator = ToolOrchestrator(registry=ToolRegistry())
            events = asyncio.run(_collect(orchestrator, model, _context(self.db)))

        self.assertEqual(model.tool_schemas, [])
        errors = [item for item in events if item["event"] == "tool.error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["data"]["code"], "unknown_tool")
        default_handler.assert_not_called()
        self.assertEqual(events[-1]["data"]["delta"], "工具未启用")

    def test_omitted_registry_still_binds_and_executes_default_catalog(self):
        model = ScriptedModel([
            [FakeChunk("", [{
                "id": "default-call",
                "name": "get_problem",
                "args": {"problem_id": 146},
            }])],
            [FakeChunk("已查询默认工具")],
        ])

        with patch(
            "interview_forge.ai.tools.builtins.problem.get_problem",
            return_value=ToolResult({"found": True}),
        ) as default_handler:
            orchestrator = ToolOrchestrator()
            events = asyncio.run(_collect(orchestrator, model, _context(self.db)))

        schema_names = [item["function"]["name"] for item in model.tool_schemas]
        self.assertIn("get_problem", schema_names)
        default_handler.assert_called_once()
        self.assertIn("tool.done", [item["event"] for item in events])
        self.assertEqual(events[-1]["data"]["delta"], "已查询默认工具")

    def test_bound_rounds_admit_tool_schemas_and_disabled_final_has_none(self):
        def reader(_context, _args):
            return {"value": "ok"}

        registry = ToolRegistry([ToolSpec("read", "读取", "读取", ValueArgs, reader)])
        model = ScriptedModel([
            [FakeChunk("", [{"id": "call-1", "name": "read", "args": {"value": "one"}}])],
            [FakeChunk("", [{"id": "call-2", "name": "read", "args": {"value": "two"}}])],
            [FakeChunk("最终回答")],
        ])
        trace = TraceSpy()
        observed = []
        real_admit = orchestrator_module.admit_request

        def observing_admit(messages, **kwargs):
            observed.append({"messages": list(messages), **kwargs})
            return real_admit(messages, **kwargs)

        context = _context(
            self.db,
            artifacts={"model_context_window": 4096, "reserved_output_tokens": 321},
        )
        orchestrator = ToolOrchestrator(
            registry=registry,
            policy=ToolPolicy(max_rounds=2),
            trace_recorder=trace,
        )
        with patch.object(orchestrator_module, "admit_request", side_effect=observing_admit):
            events = asyncio.run(_collect(orchestrator, model, context))

        self.assertEqual(events[-1]["event"], "message.delta")
        self.assertEqual(len(observed), 3)
        schema_names = [
            item["function"]["name"] for item in observed[0]["tool_schemas"]
        ]
        self.assertEqual(schema_names, ["read"])
        self.assertEqual(
            [item["function"]["name"] for item in observed[1]["tool_schemas"]],
            ["read"],
        )
        self.assertEqual(observed[2]["tool_schemas"], ())
        self.assertTrue(all(item["context_window"] == 4096 for item in observed))
        self.assertTrue(all(item["reserved_output_tokens"] == 321 for item in observed))

        admission_records = [
            item for item in trace.records
            if item.get("name") == "request_admission"
        ]
        self.assertEqual(
            [item["status"] for item in admission_records],
            ["success", "success", "success"],
        )
        self.assertEqual(set(admission_records[0]["metadata"]), ADMISSION_METADATA_KEYS)

    def test_context_overflow_raises_safe_error_without_provider_call(self):
        model = ScriptedModel([[FakeChunk("不应被调用")]])
        trace = TraceSpy()
        observed = []
        real_admit = orchestrator_module.admit_request

        def observing_admit(messages, **kwargs):
            observed.append(list(messages))
            return real_admit(messages, **kwargs)

        context = _context(
            self.db,
            artifacts={"model_context_window": 100, "reserved_output_tokens": 101},
        )
        orchestrator = ToolOrchestrator(
            registry=ToolRegistry(),
            trace_recorder=trace,
        )

        with patch.object(orchestrator_module, "admit_request", side_effect=observing_admit):
            with self.assertRaises(AIServiceError) as raised:
                asyncio.run(_collect(orchestrator, model, context))

        self.assertEqual(raised.exception.category, "context_budget_exceeded")
        self.assertEqual(model.calls, 0)
        self.assertEqual(observed[0][-1]["content"], "当前问题必须保留")
        failed = [
            item for item in trace.records
            if item.get("name") == "request_admission"
        ]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["status"], "failed")
        self.assertEqual(failed[0]["error_code"], "context_budget_exceeded")
        self.assertEqual(set(failed[0]["metadata"]), ADMISSION_METADATA_KEYS)
        self.assertNotIn("当前问题必须保留", json.dumps(failed, ensure_ascii=False))

    def test_cumulative_result_limit_prefers_fresh_evidence_in_final_without_tools(self):
        def reader(_context, args):
            source = {"title": args.value, "module_title": "网络", "url": f"/library/{args.value}.html"}
            return ToolResult({"items": [{**source, "snippet": args.value * 250}]}, library_sources=(source,))

        registry = ToolRegistry([ToolSpec("lookup", "检索", "检索", ValueArgs, reader)])
        # Some providers reuse call IDs in successive exchanges. Source
        # attribution still follows the exact result position handed to the LLM.
        model = ScriptedModel([
            [FakeChunk("", [{"id": "same", "name": "lookup", "args": {"value": "A"}}])],
            [FakeChunk("", [{"id": "same", "name": "lookup", "args": {"value": "B"}}])],
            [FakeChunk("已根据最后一份资料作答")],
        ])
        context = _context(self.db)
        one_read = reader(context, ValueArgs(value="A"))
        result_limit = estimate_json_tokens({"ok": True, "tool": "lookup", "data": one_read.data})
        trace = TraceSpy()
        orchestrator = ToolOrchestrator(registry=registry, policy=ToolPolicy(max_total_result_tokens=result_limit),
                                        trace_recorder=trace)
        messages = [{"role": "system", "content": "服务端教学规则"}, {"role": "user", "content": context.current_query}]
        events = asyncio.run(_collect(orchestrator, model, context, messages=messages))

        self.assertEqual(model.calls, 3)
        self.assertEqual(events[-1]["data"]["delta"], "已根据最后一份资料作答")
        self.assertIn("A" * 250, model.seen[1][-1]["content"])
        final = model.seen[-1]
        self.assertEqual([index for index, item in enumerate(final) if item["role"] == "system"], [0])
        self.assertIn(messages[0]["content"], final[0]["content"])
        self.assertIn(orchestrator_module.TOOLS_DISABLED_NOTICE, final[0]["content"])
        self.assertEqual(final[-1]["role"], "tool")
        self.assertEqual(model.seen[0][0], messages[0])
        observations = [json.loads(message["content"]) for message in final if message["role"] == "tool"]
        self.assertEqual(observations[0], {"omitted": "earlier_read_result"})
        self.assertEqual(observations[1]["data"]["items"][0]["snippet"], "B" * 250)
        self.assertEqual([s["url"] for s in orchestrator.last_result.library_sources], ["/library/B.html"])
        metadata = trace.records[-1]["metadata"]
        self.assertEqual((metadata["masked_tool_result_count"], metadata["budget_rejected_tool_result_count"]), (1, 0))
        self.assertEqual(metadata["original_prompt_tokens"] - metadata["admitted_prompt_tokens"],
                         metadata["tool_result_tokens_saved"])

    def test_rereading_masked_data_restores_the_cached_payload_and_source(self):
        executions = []

        def reader(_context, args):
            executions.append(args.value)
            source = {"url": f"/library/{args.value}.html", "title": args.value, "module_title": "网络"}
            return ToolResult({"items": [{**source, "snippet": args.value * 800}]}, library_sources=(source,))

        registry = ToolRegistry([ToolSpec("read", "读取", "查阅资料", ValueArgs, reader)])
        model = ScriptedModel([
            [FakeChunk("", [{"id": "first", "name": "read", "args": {"value": "A"}}])],
            [FakeChunk("", [{"id": "second", "name": "read", "args": {"value": "B"}}])],
            [FakeChunk("", [{"id": "again", "name": "read", "args": {"value": "A"}}])],
            [FakeChunk("按照两次读取的结论回答。")],
        ])
        context = _context(self.db, artifacts={"model_context_window": 780, "reserved_output_tokens": 50})
        trace = TraceSpy()
        orchestrator = ToolOrchestrator(registry=registry, trace_recorder=trace)
        asyncio.run(_collect(orchestrator, model, context))

        self.assertEqual(executions, ["A", "B"])
        self.assertEqual(model.calls, 4)
        third = {item["tool_call_id"]: json.loads(item["content"]) for item in model.seen[2] if item["role"] == "tool"}
        self.assertEqual(third["first"], {"omitted": "earlier_read_result"})
        self.assertEqual(third["second"]["data"]["items"][0]["snippet"], "B" * 800)
        final = {item["tool_call_id"]: json.loads(item["content"]) for item in model.seen[-1] if item["role"] == "tool"}
        self.assertEqual(final["again"]["data"]["items"][0]["snippet"], "A" * 800)
        visible_urls = [value["data"]["items"][0]["url"] for value in final.values() if "data" in value]
        self.assertEqual([source["url"] for source in orchestrator.last_result.library_sources], visible_urls)
        self.assertEqual([event["metadata"]["masked_tool_result_count"] for event in trace.records[:3]], [0, 0, 1])

    def test_tooling_fallback_admits_once_without_tool_schemas(self):
        def reader(_context, _args):
            return {"value": "unused"}

        model = ScriptedModel([], bind=False)
        observed = []
        fallback_called = False
        real_admit = orchestrator_module.admit_request

        def observing_admit(messages, **kwargs):
            observed.append({"messages": list(messages), **kwargs})
            return real_admit(messages, **kwargs)

        async def fallback(_model, fallback_messages):
            nonlocal fallback_called
            fallback_called = True
            self.assertEqual([index for index, item in enumerate(fallback_messages) if item["role"] == "system"], [0])
            self.assertIn(orchestrator_module.TOOLING_UNAVAILABLE_NOTICE, fallback_messages[0]["content"])
            self.assertIn("服务端教学规则", fallback_messages[0]["content"])
            yield "普通回答", {}

        orchestrator = ToolOrchestrator(
            registry=ToolRegistry([ToolSpec("read", "读取", "读取", EmptyArgs, reader)])
        )
        context = _context(self.db)
        messages = [{"role": "system", "content": "服务端教学规则"}, {"role": "user", "content": context.current_query}]
        with patch.object(orchestrator_module, "admit_request", side_effect=observing_admit):
            events = asyncio.run(_collect(orchestrator, model, context, messages=messages, fallback=fallback))

        self.assertTrue(fallback_called)
        self.assertEqual(model.calls, 0)
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["tool_schemas"], ())
        self.assertEqual(events[-1]["data"]["delta"], "普通回答")

    async def test_cancelled_read_batch_awaits_all_tasks_and_leaves_other_work(self):
        started = 0
        cancelled = 0
        all_started = asyncio.Event()
        all_cancelled = asyncio.Event()

        async def reader(_context, _args):
            nonlocal started, cancelled
            started += 1
            if started == 2:
                all_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled += 1
                if cancelled == 2:
                    all_cancelled.set()
                raise

        registry = ToolRegistry([
            ToolSpec("read_a", "读取 A", "读取 A", EmptyArgs, reader),
            ToolSpec("read_b", "读取 B", "读取 B", EmptyArgs, reader),
        ])
        model = ScriptedModel([
            [FakeChunk("", [
                {"id": "a", "name": "read_a", "args": {}},
                {"id": "b", "name": "read_b", "args": {}},
            ])],
        ])
        orchestrator = ToolOrchestrator(registry=registry)
        stream = orchestrator.stream(
            model=model,
            messages=[{"role": "user", "content": "并发读取"}],
            context=_context(self.db),
            fallback_stream_factory=lambda _model, _messages: _empty_stream(),
        )
        unrelated = asyncio.create_task(asyncio.sleep(30))
        consumer = None
        try:
            self.assertEqual((await anext(stream))["event"], "tool.start")
            self.assertEqual((await anext(stream))["event"], "tool.start")
            consumer = asyncio.create_task(anext(stream))
            await asyncio.wait_for(all_started.wait(), timeout=1)
            consumer.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await consumer
            await asyncio.wait_for(all_cancelled.wait(), timeout=1)
            self.assertFalse(unrelated.done())
        finally:
            if consumer is not None and not consumer.done():
                consumer.cancel()
                await asyncio.gather(consumer, return_exceptions=True)
            await stream.aclose()
            unrelated.cancel()
            await asyncio.gather(unrelated, return_exceptions=True)

        self.assertEqual(started, 2)
        self.assertEqual(cancelled, 2)

    def test_read_task_failure_cancels_and_awaits_siblings(self):
        sibling_started = asyncio.Event()
        sibling_cancelled = asyncio.Event()

        class FailingRuntime:
            async def execute(self, *, call, context):
                if call.name == "boom":
                    await sibling_started.wait()
                    raise RuntimeError("boom")
                sibling_started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    sibling_cancelled.set()
                    raise

        registry = ToolRegistry([
            ToolSpec("boom", "失败", "失败", EmptyArgs, lambda _c, _a: {}),
            ToolSpec("sibling", "邻接", "邻接", EmptyArgs, lambda _c, _a: {}),
        ])
        model = ScriptedModel([
            [FakeChunk("", [
                {"id": "boom", "name": "boom", "args": {}},
                {"id": "sibling", "name": "sibling", "args": {}},
            ])],
        ])
        orchestrator = ToolOrchestrator(registry=registry)
        orchestrator.runtime = FailingRuntime()

        with self.assertRaises(RuntimeError):
            asyncio.run(_collect(orchestrator, model, _context(self.db)))
        self.assertTrue(sibling_cancelled.is_set())

    def test_actions_only_create_serial_pending_confirmations(self):
        handler_calls = []

        def action_handler(_context, args):
            handler_calls.append(args.value)
            return {"executed": True}

        registry = ToolRegistry([
            ToolSpec(
                "action_a", "动作 A", "动作 A", ValueArgs, action_handler,
                kind=ToolKind.ACTION, requires_confirmation=True,
            ),
            ToolSpec(
                "action_b", "动作 B", "动作 B", ValueArgs, action_handler,
                kind=ToolKind.ACTION, requires_confirmation=True,
            ),
        ])
        model = ScriptedModel([
            [FakeChunk("", [
                {"id": "a", "name": "action_a", "args": {"value": "a"}},
                {"id": "b", "name": "action_b", "args": {"value": "b"}},
            ])],
            [FakeChunk("等待确认")],
        ])
        orchestrator = ToolOrchestrator(registry=registry)
        events = asyncio.run(_collect(orchestrator, model, _context(self.db)))

        action_events = [
            (item["event"], item["data"].get("call_id"))
            for item in events
            if item["event"] in {"tool.start", "tool.confirmation_required"}
        ]
        self.assertEqual(action_events, [
            ("tool.start", "a"),
            ("tool.confirmation_required", "a"),
            ("tool.start", "b"),
            ("tool.confirmation_required", "b"),
        ])
        self.assertEqual(handler_calls, [])
        self.assertTrue(orchestrator.last_result.has_pending_confirmation)


if __name__ == "__main__":
    unittest.main()
