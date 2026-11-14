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
        self.assertIn("你的消息 #1", answer)
        self.assertIn("助手的消息 #2", answer)
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
        self.ctx.current_query = "我最初的约定有两种说法，忘了指哪次。请给原话。"
        earliest_ambiguous, refs = quotes.render(self.ctx, picked, [self.a, self.b])
        self.assertIn("无法唯一确定", earliest_ambiguous)
        self.assertEqual([r["message_id"] for r in refs], [1, 2])

    def test_verified_attribution_distinguishes_the_writer_and_quoted_speaker(self):
        cue = "这些是领队给我的提醒，我把她当时的原话记了下来。"
        line = "换乘时，我会在站台尽头集合。"
        content = cue + "\n" + line
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE chat_messages SET content=? WHERE id=2", (content,))
            db.commit()
        self.ctx.current_query = "上次助手记录的领队提醒，原话是什么？"
        _, items = quotes.prepare(self.ctx, [[{**self.b, "excerpt": content}]], input_tokens=4096, result_tokens=3500)

        def choose(attribution):
            return json.dumps({"status": "match", "quotes": [{"message_id": 2, "quote": line, "attribution": attribution}]})

        answer, refs = quotes.render(self.ctx, choose(cue), items)
        self.assertIn("助手的消息 #2", answer)
        self.assertIn(cue, answer)
        self.assertNotIn("助手当时说", answer)
        self.assertEqual(len(refs), 1)
        ref, = refs
        self.assertEqual(read_source(self.db, "s", 2, ref["offset"], ref["length"], ref["sha256"])["excerpt"], line)
        self.ctx.current_query += "只摘提醒那句。"
        brief, refs = quotes.render(self.ctx, choose(cue), items)
        self.assertNotIn(cue, brief)
        self.assertIn(line, brief)
        # A missing, ungrounded, or forged attribution must never be presented as a speaker's name.
        self.assertEqual(quotes.render(self.ctx, choose("医生亲自说的"), items), (quotes.NO_QUOTE, ()))
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE chat_messages SET content=? WHERE id=2", (content.replace("她当时的原话", "我自己的猜测"),))
            db.commit()
        self.assertEqual(quotes.render(self.ctx, choose(cue), items), (quotes.NO_QUOTE, ()))

    def test_uncertain_request_displays_the_verified_alternatives_and_only_claims_what_was_found(self):
        self.ctx.current_query = "关于出发安排我忘了是哪次。能否唯一确定？给原话和消息编号。"
        for status in ("match", "ambiguous"):
            answer, refs = quotes.render(self.ctx, decision(status, (2, self.two), (1, self.one)), [self.b, self.a])
            self.assertIn("无法唯一确定", answer)
            self.assertEqual([ref["message_id"] for ref in refs], [1, 2])
        only_one, refs = quotes.render(self.ctx, decision("match", (1, self.one)), [self.a])
        self.assertEqual([ref["message_id"] for ref in refs], [1])
        self.assertIn("只核实到这一处", only_one)

    def test_two_wide_rankings_are_interleaved_and_duplicate_ranges_consume_no_slots(self):
        self.ctx.user_message_id = 300
        batches = []
        with closing(sqlite3.connect(self.db)) as db:
            for base in (100, 200):
                batch = []
                for index in range(8):
                    mid = base + index
                    line = f"安排 {mid}。"
                    db.execute("INSERT INTO chat_messages(id, session_id, role, content, created_at) VALUES (?, 's', 'user', ?, 'now')",
                               (mid, line))
                    batch.append(dict(message_id=mid, role="user", offset=0, excerpt=line))
                batches.append(batch)
            db.commit()
        batches[1].insert(0, batches[0][0])
        _, items = quotes.prepare(self.ctx, batches, input_tokens=4096, result_tokens=3500)
        ids = [item["message_id"] for item in items]
        self.assertEqual(len(ids), 16)
        self.assertLess(ids.index(200), ids.index(102))
        self.assertIn(105, ids)
        self.assertIn(205, ids)

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

    def test_narrow_semantic_read_gets_one_scoped_full_request_lookup(self):
        self.ctx.current_query = "之前聊过火车和轮船，请给我关于周六直达列车的整句和编号。"
        narrow = {"id": "initial", "name": "recall_chat_history", "args": {"mode": "semantic", "query": "周六"}}
        answer = decision("match", (1, "我定的是周六早晨的直达车，晚班车只作备选。"))
        model = JudgeModel([[FakeChunk(tool_calls=[narrow])], [FakeChunk(answer)]])
        engine = ToolOrchestrator()
        with patch.dict(os.environ, {"AI_HISTORY_EMBEDDING_DIR": ""}):
            asyncio.run(_collect(engine, model, self.ctx))
        with closing(sqlite3.connect(self.db)) as db:
            audit = [json.loads(row[0]) for row in db.execute("SELECT arguments_json FROM chat_tool_runs ORDER BY rowid")]
        self.assertEqual([a["query"] for a in audit], ["周六", self.ctx.current_query])
        self.assertEqual(engine.last_result.tool_calls_count, 2)
        self.assertEqual(model.calls, 2)
        self.assertEqual([ref["message_id"] for ref in engine.last_result.history_sources], [1])

    def test_unverified_free_answer_gets_an_audited_lookup_or_clean_no_source_reply(self):
        unverified = "张三说这是第一条，见 #999。"
        self.ctx.current_query = "之前说周六早晨的直达车，晚班车只作备选。原话？"
        model = JudgeModel([[FakeChunk(unverified)], [FakeChunk(decision("match", (1, self.one)))]])
        engine = ToolOrchestrator()
        with patch.dict(os.environ, {"AI_HISTORY_EMBEDDING_DIR": ""}):
            events = asyncio.run(_collect(engine, model, self.ctx))
        self.assertEqual([e["event"] for e in events], ["tool.start", "tool.done", "message.delta"])
        self.assertNotIn(unverified, str(events))
        self.assertEqual(engine.last_result.tool_calls_count, 1)
        self.assertEqual(len(engine.last_result.tool_run_ids), 1)
        self.assertEqual([r["message_id"] for r in engine.last_result.history_sources], [1])
        model = JudgeModel([[FakeChunk(unverified)]], bind=False)
        unavailable = ToolOrchestrator()
        events = asyncio.run(_collect(unavailable, model, self.ctx))
        self.assertEqual(events, [{"event": "message.delta", "data": {"delta": quotes.NO_QUOTE}}])
        self.assertTrue(unavailable.last_result.tooling_unavailable)
        self.assertEqual(unavailable.last_result.history_sources, ())

    def test_only_explicit_history_source_requests_are_routed(self):
        for text in ("给我消息ID和原文", "我之前写的那句话，请逐字引用。", "Quote my original message, with its ID.",
                     "之前提过合唱的安排，请把整句和编号给我。", "上次助手记下了向导的发言，能原样抄给我吗？",
                     "From our conversation, please copy the full sentence about the spare key."):
            self.assertTrue(quotes.requested(text), text)
        for text in ("请解释消息队列", "比较这两篇论文的原文", "引用这首诗的原句", "今天的复习计划是什么？",
                     "请找昨天的原话，顺便帮我标记这道题", "我之前说过什么？", "之前学的整句语法要怎么分析？",
                     "把之前那条计划移到下周。"):
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
