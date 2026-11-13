import asyncio
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from pydantic import ValidationError

from interview_forge.ai.chat.tool_orchestrator import ToolOrchestrator
from interview_forge.ai.tools.builtins.history import (
    RecallChatHistoryArgs,
    recall_chat_history,
)
from interview_forge.ai.tools.contracts import ToolExecutionContext
from interview_forge.ai.tools.registry import build_default_tool_registry
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime
from interview_forge.observability.ai_trace import TraceRecorder
from tests.test_ai_tool_orchestrator import FakeChunk, ScriptedModel, _collect


class ChatRecallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "owner.db"
        provider, values = server_runtime._provider, dict(server_runtime._values)
        self.addCleanup(setattr, server_runtime, "_provider", provider)
        self.addCleanup(setattr, server_runtime, "_values", values)
        server_runtime.bind_provider(lambda: default_runtime)

    @staticmethod
    def seed(path, rows):
        with closing(server_runtime.connect(path)) as db:
            db.executemany(
                "INSERT OR IGNORE INTO chat_sessions(id,title,created_at,updated_at) VALUES (?,?,?,?)",
                [(s, s, "2026-01-01", "2026-01-01") for s in {r[1] for r in rows}],
            )
            db.executemany(
                "INSERT INTO chat_messages(id,session_id,role,content,created_at) VALUES (?,?,?,?, '2026-01-01')",
                rows,
            )
            db.commit()

    def context(self, boundary):
        return ToolExecutionContext(self.db, "active", "turn", boundary, "请回顾之前的原话")

    def test_exact_and_keyword_reads_share_account_session_and_turn_boundary(self):
        self.seed(self.db, [
            (1, "active", "user", "anchor: 先查这条"),
            (2, "another", "assistant", "anchor: 其他会话的内容"),
            (3, "active", "assistant", "anchor: 只引用原文"),
            (4, "active", "user", "anchor: 当前问题"),
            (5, "active", "assistant", "anchor: 并发产生的后续消息"),
        ])
        self.seed(self.db.with_name("other.db"), [(1, "active", "user", "anchor: 同名会话但不同用户")])
        ctx = self.context(4)
        keyword = recall_chat_history(ctx, RecallChatHistoryArgs(query="AnChOr", before_message_id=9999))
        self.assertEqual([item["message_id"] for item in keyword.data["items"]], [3, 1])
        self.assertEqual(keyword.data["items"][-1]["excerpt"], "anchor: 先查这条")
        self.assertNotIn("同名会话", str(keyword.data))
        for hidden in (2, 4, 5, 99):
            self.assertEqual(recall_chat_history(ctx, RecallChatHistoryArgs(message_id=hidden)).data, {"items": []})

    def test_excerpts_cover_exact_original_match_and_can_resume_long_messages(self):
        text = "前段落。\n" * 140 + "```js\n// LRU[*]%_ 例\n```" + "\n  后段落。" * 100
        self.seed(self.db, [(1, "active", "assistant", text)])
        ctx = self.context(2)
        item, = recall_chat_history(ctx, RecallChatHistoryArgs(query="lru[*]%_", message_id=1)).data["items"]
        self.assertIn("// LRU[*]%_ 例", item["excerpt"])
        self.assertGreater(item["offset"], 500)
        self.assertEqual(item["excerpt"], text[item["offset"]:item["next_offset"]])
        at = item["next_offset"]
        page, = recall_chat_history(ctx, RecallChatHistoryArgs(message_id=1, offset=at)).data["items"]
        self.assertEqual(page["excerpt"], text[at:at + len(page["excerpt"])])
        self.assertEqual(recall_chat_history(ctx, RecallChatHistoryArgs(message_id=1, offset=len(text))).data["items"], [])
        self.assertEqual(recall_chat_history(ctx, RecallChatHistoryArgs(query="LRU.*例")).data["items"], [])

    def test_keyword_pages_remain_bounded_and_reach_old_source_without_repeating_ids(self):
        self.seed(self.db, [
            (i, "active", "user", "早先胶水" if i < 6 else "无关近况") for i in range(1, 270)
        ])
        ctx = self.context(270)
        oldest = recall_chat_history(ctx, RecallChatHistoryArgs(message_id=1)).data["items"]
        self.assertEqual([item["message_id"] for item in oldest], [1])
        page = recall_chat_history(ctx, RecallChatHistoryArgs(query="胶水")).data
        self.assertEqual(page["items"], [])
        self.assertGreater(page["next_before_message_id"], 5)
        page = recall_chat_history(ctx, RecallChatHistoryArgs(query="胶水", before_message_id=page["next_before_message_id"])).data
        self.assertEqual([item["message_id"] for item in page["items"]], [5, 4, 3])
        last = recall_chat_history(ctx, RecallChatHistoryArgs(query="胶水", before_message_id=page["next_before_message_id"])).data
        self.assertEqual([item["message_id"] for item in last["items"]], [2, 1])
        self.assertNotIn("next_before_message_id", last)

    def test_oldest_first_finds_initial_agreement_in_one_call_and_respects_turn_scope(self):
        agreement = "最初约定：每周只复习两道题。"
        rows = [(1, "other", "user", "最初约定属于另一个会话"), (2, "active", "user", agreement)]
        rows.extend((i, "active", "assistant", "普通练习") for i in range(3, 1303))
        rows.extend([(1303, "active", "user", "最初约定：当前提问"), (1304, "active", "assistant", "最初约定：将来的回答")])
        self.seed(self.db, rows)
        self.seed(self.db.with_name("other.db"), [(2, "active", "user", "最初约定属于另一个账号")])
        ctx = self.context(1303)
        default = recall_chat_history(ctx, RecallChatHistoryArgs(query="最初约定")).data
        self.assertEqual(default, {"items": [], "next_before_message_id": 1047})
        early = recall_chat_history(ctx, RecallChatHistoryArgs(query="最初约定", oldest_first=True)).data
        self.assertEqual(early["items"], [{"message_id": 2, "role": "user", "offset": 0, "excerpt": agreement}])
        self.assertEqual(early["next_after_message_id"], 257)
        for cursor in (1302, 1303, 1304, 2**63 - 1):
            with self.subTest(cursor=cursor):
                args = RecallChatHistoryArgs(query="最初约定", oldest_first=True, after_message_id=cursor)
                self.assertEqual(recall_chat_history(ctx, args).data, {"items": []})

    def test_both_orders_page_without_repeating_or_skipping_source_messages(self):
        ids = [2, 257, 258, 259, 260, 514, 515, 516, 520]
        self.seed(self.db, [(i, "active", "user", "命中" if i in ids else "其他") for i in range(1, 522)])
        ctx = self.context(522)
        for oldest_first, cursor_field in [(False, "before_message_id"), (True, "after_message_id")]:
            with self.subTest(oldest_first=oldest_first):
                found = []
                cursor = None
                for _ in range(8):
                    args = RecallChatHistoryArgs(query="命中", oldest_first=oldest_first, **{cursor_field: cursor})
                    page = recall_chat_history(ctx, args).data
                    self.assertLessEqual(len(page["items"]), 3)
                    found.extend(item["message_id"] for item in page["items"])
                    next_cursor = page.get("next_" + cursor_field)
                    if next_cursor is None:
                        break
                    if cursor is not None:
                        self.assertTrue(next_cursor > cursor if oldest_first else next_cursor < cursor)
                    cursor = next_cursor
                else:
                    self.fail("page cursor did not reach the end of visible history")
                self.assertEqual(found, ids if oldest_first else list(reversed(ids)))

    def test_selector_validation_excludes_other_storage_and_unbounded_parameters(self):
        invalid = [
            {}, {"query": "   "}, {"query": "a" * 97}, {"query": 1}, {"message_id": True},
            {"message_id": 2**63}, {"message_id": 0}, {"message_id": 1, "offset": -1},
            {"query": "x", "offset": 1}, {"message_id": 1, "before_message_id": 20},
            {"query": "x", "oldest_first": "true"}, {"query": "x", "after_message_id": 2},
            {"query": "x", "oldest_first": True, "before_message_id": 2},
            {"query": "x", "oldest_first": True, "after_message_id": 2, "before_message_id": 3},
            {"message_id": 1, "after_message_id": 2}, {"message_id": 1, "oldest_first": True},
            {"query": "x", "session_id": "other"}, {"query": "x", "user_db": "other.db"},
            {"message_id": 1, "user_id": 2}, {"message_id": 1, "path": "other.db"},
        ]
        for arguments in invalid:
            with self.subTest(arguments=arguments), self.assertRaises(ValidationError):
                RecallChatHistoryArgs.model_validate(arguments)

    def test_orchestrator_sends_excerpt_to_model_and_only_status_to_events_and_traces(self):
        source = "仅模型本次需要的原话 RECALLED-TEXT"
        self.seed(self.db, [(1, "active", "assistant", source)])
        trace = TraceRecorder(user_db=self.db, trace_id="recall", session_id="active")
        engine = ToolOrchestrator(registry=build_default_tool_registry(), trace_recorder=trace)
        model = ScriptedModel([
            [FakeChunk(tool_calls=[{"id": "r", "name": "recall_chat_history", "args": {"message_id": 1}}])],
            [FakeChunk("已核对。")],
        ])
        events = asyncio.run(_collect(engine, model, self.context(2)))
        self.assertEqual([event["event"] for event in events], ["tool.start", "tool.done", "message.delta"])
        observations = [json.loads(m["content"]) for m in model.seen[-1] if m.get("role") == "tool"]
        self.assertEqual(observations[0]["data"]["items"][0]["excerpt"], source)
        with closing(sqlite3.connect(self.db)) as db:
            audit = db.execute("SELECT arguments_json, result_meta_json FROM chat_tool_runs").fetchall()
            traces = db.execute("SELECT metadata_json FROM ai_trace_events").fetchall()
        self.assertTrue(audit and traces)
        self.assertNotIn(source, str(events) + str(audit) + str(traces))
