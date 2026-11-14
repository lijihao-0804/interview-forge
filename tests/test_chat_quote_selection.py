import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from interview_forge.ai.chat import quote_selection as quotes
from interview_forge.ai.chat.history_sources import read_source
from interview_forge.ai.chat.tool_orchestrator import ToolOrchestrator
from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolKind, ToolSpec
from interview_forge.ai.tools.policy import ToolPolicy
from interview_forge.ai.tools.registry import build_default_tool_registry
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime
from tests.test_ai_tool_orchestrator import EmptyArgs, FakeChunk, ScriptedModel, _collect


def decision(status, *selected):
    return json.dumps({"status": status, "quotes": [{"message_id": mid, "quote": q} for mid, q in selected]},
                      ensure_ascii=False)


class JudgeModel(ScriptedModel):
    def bind(self, **kwargs):
        self.judge_options = kwargs
        return self


class ChatQuoteSelectionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = Path(folder.name) / "owner.db"
        provider, values = server_runtime._provider, dict(server_runtime._values)
        self.addCleanup(setattr, server_runtime, "_provider", provider)
        self.addCleanup(setattr, server_runtime, "_values", values)
        server_runtime.bind_provider(lambda: default_runtime)
        self.one = "🚂\r\n我定的是周六早晨的直达车，晚班车只作备选。"
        self.two = "后来改为周日傍晚乘船。"
        with closing(server_runtime.connect(self.db)) as db:
            db.executemany("INSERT INTO chat_sessions VALUES(?,'t','now','now')", [("s",), ("elsewhere",)])
            db.executemany("INSERT INTO chat_messages(id, session_id, role, content, created_at) VALUES (?,?,?,?,'now')", [
                (1,"s","user",self.one), (2,"s","assistant",self.two),
                (3,"elsewhere","user","other-session"), (7,"s","assistant","future"),
            ])
            db.commit()
        self.ctx = ToolExecutionContext(self.db, "s", "turn", 7, "我记得出发日变过，请对照给出原话和消息ID。")
        self.a = dict(message_id=1,role="user",offset=0,excerpt=self.one)
        self.b = dict(message_id=2,role="assistant",offset=0,excerpt=self.two)

    def test_selects_multiple_exact_ranges_chronologically_and_only_verified_cards(self):
        args = [{"message_id": 2}, {"message_id": 1}]
        first = FakeChunk("未经核对的自由回答。", tool_calls=[{"id": str(i), "name": "recall_chat_history", "args": a}
                         for i, a in enumerate(args)], usage={"input_tokens": 15})
        selected = [(2, self.two), (1, "我定的是周六早晨的直达车，晚班车只作备选。")]
        model = JudgeModel([[first], [FakeChunk(decision("match", *selected), usage={"input_tokens": 45, "output_tokens": 22})]])
        engine = ToolOrchestrator()
        events = asyncio.run(_collect(engine, model, self.ctx))
        deltas = [e["data"]["delta"] for e in events if e["event"] == "message.delta"]
        self.assertEqual(len(deltas), 1)
        answer, = deltas
        self.assertNotIn("未经核对", answer)
        self.assertNotIn("status", answer)
        self.assertIn("你当时说（消息 #1）", answer)
        self.assertIn("助手当时说（消息 #2）", answer)
        self.assertLess(answer.index("#1"), answer.index("#2"))
        self.assertEqual(engine.last_result.usage, {"input_tokens": 60, "output_tokens": 22})
        self.assertEqual(model.calls, 2)
        self.assertEqual(model.judge_options, {"max_tokens": quotes.MAX_OUTPUT_TOKENS})
        payload = json.loads(model.seen[-1][-1]["content"])
        self.assertEqual(payload["request"], self.ctx.current_query)
        self.assertEqual({p["message_id"] for p in payload["passages"]}, {1, 2})
        self.assertNotIn("future", str(payload))
        refs = engine.last_result.history_sources
        self.assertEqual([r["message_id"] for r in refs], [1,2])
        self.assertEqual(refs[0]["offset"], 3)
        self.assertEqual(read_source(self.db, "s", 1, refs[0]["offset"], refs[0]["length"], refs[0]["sha256"])["excerpt"], selected[1][1])

    def test_no_source_evidence_injection_or_cross_cutoff_leakage(self):
        forged = [self.a, {**self.a,"role":"assistant"}, {**self.a,"message_id":7,"role":"assistant","excerpt":"future"},
                  {**self.a,"message_id":3,"excerpt":"other-session"}, {**self.a,"excerpt":"changed"}]
        _, actual = quotes.prepare(self.ctx, [forged], input_tokens=4096, result_tokens=3500)
        self.assertEqual(actual, [self.a])
        for bad in [decision("match", (3,"other-session")), decision("match", (1,"转乘汽车")), decision("match", (True,self.one)),
                    decision("none", (1, self.one)), decision("ambiguous", (1, self.one)), "答案 #1", [],
                    json.dumps({"status":"match","quotes":[{"message_id":1,"quote":self.one,"role":"assistant"}]}),
                    decision("match", (1,self.one), (2,"future")), " " * (quotes.MAX_OUTPUT_CHARS + 1)]:
            with self.subTest(bad=str(bad)[:80]):
                self.assertEqual(quotes.render(self.ctx, bad, actual), (quotes.NO_QUOTE, ()))
        self.assertEqual(quotes.prepare(self.ctx, [[self.a]], input_tokens=2, result_tokens=3500), ([], []))
        self.assertEqual(quotes.prepare(self.ctx, [[self.a]], input_tokens=4096, result_tokens=1), ([], []))
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE chat_messages SET content=? WHERE id=1", (self.one.replace("只作", "改为"),))
            db.commit()
        self.assertEqual(quotes.render(self.ctx, decision("match",(1,"周六早晨")), actual), (quotes.NO_QUOTE, ()))

    def test_ambiguity_and_earliest_apply_user_scope(self):
        self.ctx.current_query = "将聊天里那句给我，可能有两种，请给原话。"
        picked = decision("ambiguous", (2,self.two), (1,self.one))
        answer, refs = quotes.render(self.ctx, picked, [self.a, self.b])
        self.assertIn("可能", answer)
        self.assertEqual([r["message_id"] for r in refs], [1, 2])
        self.ctx.current_query = "我最初的约定是什么？只要第一条原话。"
        earliest, refs = quotes.render(self.ctx, decision("match", (2,self.two), (1,self.one)), [self.a,self.b], partial=True)
        self.assertIn("尚无法确定", earliest)
        self.assertNotIn("#2", earliest)
        self.assertEqual([r["message_id"] for r in refs], [1])

    def test_guessing_a_literal_triggers_one_audited_semantic_supplement_then_selection(self):
        self.ctx.current_query = "之前那张周六早晨的直达车票是怎么说的？把原话和消息 ID 给我。"
        initial = {"id":"guess","name":"recall_chat_history","args":{"query":"unremembered phrase"}}
        model = JudgeModel([[FakeChunk(tool_calls=[initial])], [FakeChunk(decision("match",(1,"周六早晨的直达车")))]] )
        engine = ToolOrchestrator()
        with patch.dict(os.environ, {"AI_HISTORY_EMBEDDING_DIR":""}):
            events = asyncio.run(_collect(engine, model, self.ctx))
        self.assertEqual(model.calls, 2)
        self.assertEqual(engine.last_result.tool_calls_count, 2)
        self.assertEqual([e["event"] for e in events].count("tool.done"), 2)
        self.assertEqual([r["message_id"] for r in engine.last_result.history_sources], [1])
        with closing(sqlite3.connect(self.db)) as db:
            audit = [json.loads(row[0]) for row in db.execute("SELECT arguments_json FROM chat_tool_runs ORDER BY rowid")]
        self.assertEqual([a["mode"] for a in audit], ["literal", "semantic"])
        self.assertIn("周六早晨", audit[1]["query"])

        tight_engine = ToolOrchestrator(policy=ToolPolicy(max_calls_per_turn=1))
        tight_model = JudgeModel([[FakeChunk(tool_calls=[initial])]])
        events = asyncio.run(_collect(tight_engine, tight_model, self.ctx))
        self.assertEqual(tight_model.calls, 1)
        self.assertEqual(tight_engine.last_result.tool_calls_count, 1)
        self.assertEqual(events[-1]["data"]["delta"], quotes.NO_QUOTE)

    def test_only_explicit_history_source_requests_are_routed(self):
        for text in ("给我消息ID和原文", "我之前写的那句话，请逐字引用。", "Quote my original message, with its ID."):
            self.assertTrue(quotes.requested(text), text)
        for text in ("请解释消息队列", "比较这两篇论文的原文", "引用这首诗的原句", "今天的复习计划是什么？",
                     "请找昨天的原话，顺便帮我标记这道题", "我之前说过什么？"):
            self.assertFalse(quotes.requested(text), text)

    def test_a_turn_that_requests_an_action_keeps_normal_answer_and_preamble(self):
        registry = build_default_tool_registry()
        registry.register(ToolSpec("draft_action", "操作", "操作", EmptyArgs, lambda *_: {},
                                  kind=ToolKind.ACTION, requires_confirmation=True))
        calls = [{"id":"r","name":"recall_chat_history","args":{"message_id":1}},
                 {"id":"a","name":"draft_action","args":{}}]
        model = JudgeModel([[FakeChunk("我来核对。", tool_calls=calls)], [FakeChunk("等待确认。")]])
        engine = ToolOrchestrator(registry=registry)
        events = asyncio.run(_collect(engine, model, self.ctx))
        self.assertEqual(model.calls, 2)
        self.assertEqual([e["data"]["delta"] for e in events if e["event"] == "message.delta"], ["我来核对。", "等待确认。"])
        self.assertFalse(hasattr(model, "judge_options"))
