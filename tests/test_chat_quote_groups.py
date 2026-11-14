"""Independent evidence groups for bounded quote selection."""
import asyncio
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from interview_forge.ai.chat import quote_selection
from interview_forge.ai.chat.history_sources import read_source
from interview_forge.ai.chat.tool_orchestrator import ToolOrchestrator
from interview_forge.ai.tools.contracts import ToolExecutionContext
from interview_forge.core.runtime import server_runtime
from tests.test_ai_tool_orchestrator import FakeChunk, ScriptedModel, _collect


class QuoteGroupTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = Path(folder.name) / "local.db"
        self.ctx = ToolExecutionContext(self.db, "s", "t", 99, "之前说的卸货入口是哪儿？请附原话。")
        rows = ["送货安排尚未报备，入口由别人决定。", "送货时，工作日请走南门。",
                "送货时，休息日请走北门。"]
        with closing(server_runtime.connect(self.db)) as db:
            db.execute("INSERT INTO chat_sessions VALUES ('s','account','now','now')")
            db.executemany("INSERT INTO chat_messages(session_id,role,content,created_at) VALUES ('s','user',?,'now')",
                           ((text,) for text in rows))
            db.commit()
        self.items = [dict(message_id=i, role="user", offset=0, excerpt=text)
                      for i, text in enumerate(rows, 1)]

    def select(self, status, *positions):
        return json.dumps({"status": status, "quotes": [
            {"source": chr(ord("A") + pos - 1), "quote": self.items[pos - 1]["excerpt"]} for pos in positions
        ]}, ensure_ascii=False)

    def test_singular_question_with_unspecified_condition_preserves_each_answer(self):
        # Newest tool observations are admitted first; source cards render chronologically.
        calls = [{"id": str(i), "name": "recall_chat_history", "args": {"message_id": i}}
                 for i in (3, 2, 1)]
        first = FakeChunk(tool_calls=calls)
        model = ScriptedModel([[first], [FakeChunk(self.select("ambiguous", 3, 2))]])
        engine = ToolOrchestrator()
        asyncio.run(_collect(engine, model, self.ctx))
        self.assertEqual(model.calls, 2)
        bill = json.loads(model.seen[-1][-1]["content"])["passages"]
        self.assertEqual([p["source"] for p in bill], ["A", "B", "C"])
        self.assertEqual([p["excerpt"] for p in bill], [p["excerpt"] for p in self.items])
        refs = engine.last_result.history_sources
        self.assertEqual([r["message_id"] for r in refs], [2, 3])
        for r in refs:
            text = read_source(self.db, "s", r["message_id"], r["offset"], r["length"], r["sha256"])["excerpt"]
            self.assertEqual(text, self.items[r["message_id"] - 1]["excerpt"])
        answer, _ = quote_selection.render(self.ctx, self.select("ambiguous", 2, 3), self.items)
        self.assertIn("无法唯一确定", answer)

    def test_one_answer_and_corresponding_repeats_need_just_one_source(self):
        self.ctx.current_query = "给我之前关于工作日送货的原话。"
        text, refs = quote_selection.render(self.ctx, self.select("match", 2), self.items)
        self.assertNotIn("无法唯一确定", text)
        self.assertEqual([r["message_id"] for r in refs], [2])
        with closing(sqlite3.connect(self.db)) as db:
            duplicate = self.items[1]["excerpt"]
            db.execute("UPDATE chat_messages SET content=? WHERE id=3", (duplicate,))
            db.commit()
        self.items[2]["excerpt"] = duplicate
        text, refs = quote_selection.render(self.ctx, self.select("match", 2), self.items)
        self.assertEqual([r["message_id"] for r in refs], [2])
        self.assertNotIn("#3", text)

    def test_complementary_facts_in_separate_messages_complete_the_request(self):
        rows = ["仓门没检修，我只在旁边等。", "卸货前，我先核对车单。", "货物入库后，我再合上门闩。"]
        with closing(sqlite3.connect(self.db)) as db:
            db.executemany("UPDATE chat_messages SET content=? WHERE id=?", ((text, n) for n, text in enumerate(rows, 1)))
            db.commit()
        for item, text in zip(self.items, rows, strict=True):
            item["excerpt"] = text
        self.ctx.current_query = "把我写过的卸货前准备和完工手续完整引用给我。"
        answer, refs = quote_selection.render(
            self.ctx, self.select("parts", 3, 2), self.items,
        )
        self.assertEqual([r["message_id"] for r in refs], [2, 3])
        self.assertIn(rows[1], answer)
        self.assertIn(rows[2], answer)
        self.assertNotIn("无法唯一确定", answer)
        partial, refs = quote_selection.render(
            self.ctx, self.select("parts", 2), self.items,
        )
        self.assertEqual([r["message_id"] for r in refs], [2])
        self.assertIn("只核实到其中这一部分", partial)

    def test_earliest_only_wins_over_multiple_groups_and_partial_scan_is_visible(self):
        self.ctx.current_query = "这些安排最早的消息呢？我不确定是哪条，只要最早的原话。"
        answer, refs = quote_selection.render(
            self.ctx, self.select("ambiguous", 3, 2), self.items, partial=True,
        )
        self.assertEqual([r["message_id"] for r in refs], [2])
        self.assertIn("尚无法确定它是最早一条", answer)
        self.assertNotIn("无法唯一确定", answer)

    def test_mistyped_label_recovers_whole_unique_passage_only(self):
        def result(label, quote):
            payload = json.dumps({"status": "match", "quotes": [{"source": label, "quote": quote}]})
            return quote_selection.render(self.ctx, payload, self.items)

        source = self.items[1]["excerpt"]
        for label in ("B", " b ", "A"):
            _, refs = result(label, source)
            self.assertEqual([r["message_id"] for r in refs], [2])
        self.assertEqual(result("A", "工作日请走南门"), (quote_selection.NO_QUOTE, ()))
        self.assertEqual(result("A", "没有出现在任何原文里。"), (quote_selection.NO_QUOTE, ()))
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE chat_messages SET content=? WHERE id=3", (source,))
            db.commit()
        self.items[2]["excerpt"] = source
        self.assertEqual(result("A", source), (quote_selection.NO_QUOTE, ()))

    def test_checked_ids_survive_extra_model_commentary_or_partial_group_array(self):
        first, second = self.items[1]["excerpt"], self.items[2]["excerpt"]
        value = {"groups": [1], "relation": "alternatives", "determination": "另外还有一条 #900。",
                 "quotes": [{"group": 1, "passage": 1, "message_id": 2, "quote": first},
                            {"group": 2, "passage": 3, "message_id": 3, "quote": second}]}
        answer, refs = quote_selection.render(self.ctx, json.dumps(value), self.items)
        self.assertEqual([r["message_id"] for r in refs], [2, 3])
        self.assertIn("无法唯一确定", answer)
        self.assertNotIn("900", answer)
        # A real ID binds the quote to that record, even if a different
        # numbered source would have been an exact match.
        value["quotes"][0]["message_id"] = 1
        self.assertEqual(quote_selection.render(self.ctx, json.dumps(value), self.items), (quote_selection.NO_QUOTE, ()))
        value = {"groups": [0, 0, 0], "quotes": []}
        self.assertEqual(quote_selection.render(self.ctx, json.dumps(value), self.items), (quote_selection.NO_QUOTE, ()))

    def test_attribution_that_only_repeats_the_verified_id_is_not_speaker_evidence(self):
        def cite(attribution):
            payload = self.select("ambiguous", 2, 3)
            value = json.loads(payload)
            value["quotes"][0]["attribution"] = attribution
            return quote_selection.render(self.ctx, json.dumps(value), self.items)

        answer, refs = cite("message_id 2")
        self.assertEqual([r["message_id"] for r in refs], [2, 3])
        self.assertNotIn("message_id", answer)
        self.assertNotIn("同条消息交代的出处", answer)
        for invalid in ("message_id 3", "message_id 2 是门卫说的", "我的合伙人说", "作者是 #2"):
            self.assertEqual(cite(invalid), (quote_selection.NO_QUOTE, ()))
        self.ctx.current_query = "这段原话是谁说的？把不同说法的出处也引用给我。"
        self.assertEqual(cite("message_id 2"), (quote_selection.NO_QUOTE, ()))
