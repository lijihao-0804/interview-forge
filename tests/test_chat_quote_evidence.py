"""User-visible selection, complete sentences, and conditional speaker evidence."""
import asyncio
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from interview_forge.ai.chat import quote_selection as quotes
from interview_forge.ai.chat.history_sources import read_source
from interview_forge.ai.chat.tool_orchestrator import ToolOrchestrator
from interview_forge.ai.tools.contracts import ToolExecutionContext
from interview_forge.core.runtime import server_runtime
from tests.test_ai_tool_orchestrator import FakeChunk, ScriptedModel, _collect


class QuoteEvidenceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = Path(folder.name) / "owner.db"
        self.ctx = ToolExecutionContext(self.db, "lights", "t", 99, "之前收灯的办法，能证实谁说的才贴原话和消息编号。")
        with closing(server_runtime.connect(self.db)) as db:
            db.execute("INSERT INTO chat_sessions VALUES ('lights','owner','now','now')")
            db.commit()

    def records(self, *lines):
        with closing(sqlite3.connect(self.db)) as db:
            db.executemany("INSERT INTO chat_messages(id,session_id,role,content,created_at) VALUES (?,'lights','user',?,'now')",
                           enumerate(lines, 1))
            db.commit()
        return [dict(message_id=i, role="user", offset=0, excerpt=line) for i, line in enumerate(lines, 1)]

    def selected(self, checked, items, relation="match"):
        return quotes.render(self.ctx, json.dumps({"checks": checked, "relation": relation}, ensure_ascii=False), items)

    def test_conditional_request_routing(self):
        for query in (
            "之前记的那段话，能确认是谁说的才引用。",
            "之前记的那段话，身份不明就别贴引文。",
            "之前我想找那句。能确认是谁说的，我才要原句。",
            "以前谁讲过剪线？只有能查明发言人才引，否则告诉我没查到，顺便帮我标记这道题。",
            "Only quote the line if you can verify who said it. Then mark this exercise.",
            "Find the old recording. Unless you can identify its speaker, omit the citation.",
        ):
            with self.subTest(query=query):
                self.assertTrue(quotes.requested(query))
                self.assertTrue(quotes.identity_required(query))
        query = "我保留过录音。只摘亲口讲的那句，写清到底是谁说的，附编号。"
        self.assertTrue(quotes.requested(query))
        self.assertFalse(quotes.identity_required(query))
        self.assertFalse(quotes.requested("引用诗集里的半句，附编号。"))

    def test_positive_labels_restore_both_complete_records_and_readable_cards(self):
        rows = ["周三停演时，我收手灯会先包住电线。", "晚场暂停时，老师说先把灯架放倒。",
                "库房里也有备用手灯。"]
        self.records(*rows)
        self.ctx.current_query = "上次散场怎么收灯？我记不清哪天，想把原句和编号都翻出来。"
        calls = [{"id": str(n), "name": "recall_chat_history", "args": {"message_id": n}} for n in (3, 2, 1)]
        selected = {"relation": "parts", "checks": {"A": {"quote": rows[0], "context": "周三停演"},
                                                    "B": {"quote": "先把灯架放倒。", "context": "晚场暂停"}, "C": 0}}
        model = ScriptedModel([[FakeChunk(tool_calls=calls)], [FakeChunk(json.dumps(selected, ensure_ascii=False))]])
        engine = ToolOrchestrator()
        events = asyncio.run(_collect(engine, model, self.ctx))
        text, = [v["data"]["delta"] for v in events if v["event"] == "message.delta"]
        self.assertIn("周三停演", text)
        self.assertIn("晚场暂停", text)
        self.assertIn("无法唯一确定", text)
        self.assertNotIn("不同部分", text)
        self.assertNotIn("#3", text)
        self.assertEqual([p["message_id"] for p in engine.last_result.history_sources], [1, 2])
        for ref, expected in zip(engine.last_result.history_sources, rows, strict=False):
            self.assertIn(f"#{ref['message_id']}\n> {expected}", text)
            actual = read_source(self.db, "lights", ref["message_id"], ref["offset"], ref["length"], ref["sha256"])
            self.assertEqual(actual["excerpt"], expected)

    def test_wrong_speaker_and_cropped_attribution_cannot_authorize_quote(self):
        line = "先收灯。"
        records = self.records("当时老林对小夏说：“先收灯。”", "小夏转交老林说的原话：“先收灯。”",
                               "小夏说，老林说：“先收灯。”", "如果我没记错，也许是小夏说：“先收灯。”",
                               "小夏说：“先收灯。”后来才弄清是誊录时弄错了，发言人不详。")
        def answer(index, name, cue):
            checked = {chr(65 + n): 0 for n in range(len(records))}
            checked[chr(65 + index)] = {"quote": line, "speaker": name, "attribution": cue}
            return self.selected(checked, records)

        for i, name, cue in ((0, "小夏", "小夏说"), (1, "小夏", "小夏转交老林说的原话"),
                             (2, "小夏", "小夏说"), (3, "小夏", "小夏说"), (4, "小夏", "小夏说")):
            with self.subTest(i=i):
                text, refs = answer(i, name, cue)
                self.assertIn("谁说的", text)
                self.assertNotIn(line, text)
                self.assertNotIn("#", text)
                self.assertEqual(refs, ())
        for i in (0, 1, 2):
            with self.subTest(i=i):
                text, refs = answer(i, "老林", records[i]["excerpt"].split("：")[0])
                self.assertIn("老林", text)
                self.assertIn(line, text)
                self.assertEqual([p["message_id"] for p in refs], [i + 1])

    def test_condition_admits_verified_quote_in_record_with_another_anonymous_quote(self):
        private, verified = "先锁柜。", "取下电池。"
        rows = self.records(f"第一句没有署名：“{private}”后来小姜亲口说：“{verified}”",
                            f"“{private}”这句的发言人不详。当天小姜签了到。")
        choices = {"A": {"quote": verified, "speaker": "小姜", "attribution": "小姜亲口说"},
                   "B": {"quote": private, "speaker": "小姜", "attribution": "当天小姜签了到。"}}
        text, refs = self.selected(choices, rows, relation="alternatives")
        self.assertIn(verified, text)
        self.assertIn("小姜", text)
        self.assertNotIn(private, text)
        self.assertNotIn("#2", text)
        self.assertEqual([r["message_id"] for r in refs], [1])

    def test_indirect_report_keeps_uncertainty_that_model_left_out_of_its_attribution(self):
        items = self.records("可能是老林说先拿电池。", "晚场开门前，老林说先拿电池。")
        choice = {"quote": "先拿电池。", "speaker": "老林", "attribution": "老林说"}
        text, refs = self.selected({"A": choice, "B": choice}, items, relation="alternatives")
        self.assertNotIn("#1", text)
        self.assertIn(items[1]["excerpt"], text)
        self.assertEqual([r["message_id"] for r in refs], [2])

    def test_missing_or_uncertain_identity_suppresses_every_locator_including_old_format(self):
        line = "先裹住插头。"
        items = self.records(f"我记下一句：“{line}”是谁说的不清楚。交接簿上有小冯的签名。")
        for verdict in (1, {"quote": line}, {"quote": line, "attribution": "小冯的签名", "speaker": "小冯"}):
            result = self.selected({"A": verdict}, items)
            self.assertEqual(result, (quotes.no_quote(self.ctx.current_query), ()))
        legacy = {"status": "match", "quotes": [{"source": "A", "quote": line}]}
        self.assertEqual(quotes.render(self.ctx, json.dumps(legacy), items), (quotes.no_quote(self.ctx.current_query), ()))
        self.assertNotIn("#", result[0])
        self.assertNotIn(line, result[0])

    def test_recheck_requires_complete_semantic_rejection_and_distinct_high_ranked_lists(self):
        items = self.records("日班去北库。", "夜班去二楼。")
        ab = [items, items[::-1]]
        query = "之前我讲交班的原句是什么？"
        no_match = json.dumps({"checks": {"A": 0, "B": 0}, "relation": "match"})
        self.assertTrue(quotes.review_after_rejection(query, no_match, items, ab))
        for value in ({"checks": {"C": 0}}, {"checks": {"B": 0}}, {"checks": {"A": False, "B": False}},
                      {"checks": {"A": 0, "B": 0}, "relation": "alternatives"},
                      {"checks": {"A": 0, "B": 0}, "relation": "bogus"},
                      {"checks": {"A": 0, "B": 1}}, {"status": "none", "quotes": ["not empty"]}):
            self.assertFalse(quotes.review_after_rejection(query, json.dumps(value), items, ab), value)
        self.assertFalse(quotes.review_after_rejection(query, no_match, items, [items, items]))
        self.assertFalse(quotes.review_after_rejection(self.ctx.current_query, no_match, items, ab))
        self.assertTrue(quotes.has_complete_decision(no_match))
        self.assertFalse(quotes.has_complete_decision('{"checks":{"A":0,"B":'))

    def test_optional_paraphrases_do_not_override_valid_labels_and_quotations(self):
        first, second = "往左拔。", "用下层。"
        items = self.records(f"师傅说：“{first}”", f"队员解释：“{second}”")
        self.ctx.current_query = "当时怎么取灯？我记不清哪次，请给我可能的原话和编号。"
        choices = {"A": {"quote": first, "context": "最初值班", "speaker": "说法甲", "attribution": "甲所属的日班组"},
                   "B": {"quote": second, "context": "最后到场", "speaker": "队员", "attribution": "队员解释"}}
        answer, refs = self.selected(choices, items, "alternatives")
        self.assertEqual([r["message_id"] for r in refs], [1, 2])
        for text in (first, second, "队员", "无法唯一确定"):
            self.assertIn(text, answer)
        for text in ("最初值班", "说法甲", "日班组", "最后到场"):
            self.assertNotIn(text, answer)
        self.ctx.current_query = "之前记的原话，只有能确认是谁说的才引。"
        answer, refs = self.selected(choices, items, "alternatives")
        self.assertEqual([r["message_id"] for r in refs], [2])
        self.assertNotIn(first, answer)

        mixed = {"A": {"quote": items[1]["excerpt"], "context": "最像"}, "B": 0}
        answer, refs = self.selected(mixed, items)
        self.assertEqual(refs, ())
        self.assertNotIn(second, answer)

    def test_sentence_repair_keeps_only_target_sentence_and_direct_speech(self):
        self.ctx.current_query = "把收灯的原话和编号给我。"
        items = self.records("先听通知。闭场时，老栾说先拔插头。下次再说新灯。", "他补充：“我负责。先裹插头。”")
        text, refs = self.selected({"A": {"quote": "先拔插头。"}, "B": 0}, items)
        self.assertIn("闭场时，老栾说先拔插头。", text)
        self.assertNotIn("先听通知", text)
        self.assertNotIn("下次再说新灯", text)
        self.assertEqual(refs[0]["offset"], len("先听通知。"))
        text, refs = self.selected({"A": 0, "B": {"quote": "先裹插头。"}}, items)
        self.assertIn("先裹插头。", text)
        self.assertNotIn("我负责", text)
        self.assertEqual(len(refs), 1)
