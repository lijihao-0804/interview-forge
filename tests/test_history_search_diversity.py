"""Source selection checks using independent chat fixtures and the real tool entry."""
from __future__ import annotations

import os
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from interview_forge.ai import history_search
from interview_forge.ai.embedding_spec import EMBEDDING_DIMENSION
from interview_forge.ai.history_encoder import history_encoder
from interview_forge.ai.token_counting import estimate_json_tokens
from interview_forge.ai.tools.builtins.history import HISTORY_RESULT_TOKENS, RecallChatHistoryArgs, recall_chat_history
from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolExecutionResult
from interview_forge.db.ai_schema import AI_DB_SCHEMA


class ScoredEncoder:
    """Keep the passage and query path real while specifying the dense similarity."""

    def __init__(self, scores):
        self.scores_by_text = scores

    def encode(self, texts, *, query=False):
        return [
            struct.pack("<f", 1.0 if query else self.scores_by_text[text])
            + bytes(EMBEDDING_DIMENSION * 4 - 4) for text in texts
        ]

    def scores(self, query_vector, vectors):
        return [struct.unpack_from("<f", vector)[0] for vector in vectors]


class HistorySearchDiversityTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = Path(self.folder.name) / "learning.db"
        with closing(sqlite3.connect(self.db)) as db:
            db.executescript(AI_DB_SCHEMA)
            db.execute("INSERT INTO chat_sessions VALUES ('s', 'test', 'now', 'now')")
            db.commit()

    def add_messages(self, rows):
        with closing(sqlite3.connect(self.db)) as db:
            db.executemany(
                "INSERT INTO chat_messages(session_id, role, content, created_at) VALUES ('s', ?, ?, 'now')",
                rows,
            )
            db.commit()

    def recall(self, topic, request=None, *, oldest=False):
        context = ToolExecutionContext(self.db, "s", "turn", 100, request or topic)
        args = RecallChatHistoryArgs(query=topic, mode="semantic", oldest_first=oldest)
        return recall_chat_history(context, args).data["items"]

    def test_third_slot_yields_to_a_semantically_stronger_source(self):
        topic = "雨鞋保养"
        messages = [
            "雨鞋保养的选题登记完毕。",
            "雨鞋保养的稿件编号是七号。",
            "雨鞋保养的封面要用黄色。",
            "把胶靴上的泥冲洗干净，放在通风处阴干，避免阳光暴晒。",
        ]
        self.add_messages([("user", text) for text in messages])
        with patch.object(history_search, "history_encoder", return_value=ScoredEncoder(
                dict(zip(messages, [.89, .88, .87, .91], strict=True)))):
            actual = self.recall(topic, "之前说的养护胶靴办法是什么？")
            comparison = self.recall(topic, "请比较之前提过的说法")
        self.assertEqual([item["message_id"] for item in actual], [1, 2, 4])
        self.assertEqual(actual[2]["excerpt"], messages[3])
        self.assertEqual([item["message_id"] for item in comparison], [1, 2, 3])

    def test_dense_slot_requires_existing_quality_gate_and_keeps_hybrid_ties(self):
        topic = "摆渡班次"
        messages = [
            "摆渡班次的第一张登记单。", "摆渡班次的第二张登记单。",
            "摆渡班次的第三张登记单。", "摆渡的记录另行通知。",
        ]
        self.add_messages([("user", text) for text in messages])
        for numbers in ([.91, .90, .72, .73], [.91, .90, .88, .88]):
            with self.subTest(scores=numbers):
                with closing(sqlite3.connect(self.db)) as db:
                    db.execute("DELETE FROM chat_history_embeddings")
                    db.commit()
                with patch.object(history_search, "history_encoder", return_value=ScoredEncoder(
                        dict(zip(messages, numbers, strict=True)))):
                    current = self.recall(topic)
                    protected = self.recall(topic, "请对照之前的消息")
                self.assertEqual([x["message_id"] for x in protected], [1, 2, 3])
                self.assertEqual(current, protected)

    def test_identical_whole_messages_group_by_role_but_not_for_occurrences(self):
        duplicate = "交接清单只写了展柜钥匙这个栏目，下面还是空白。"
        source = "散场后把陈列柜的铜钥匙交到夜班值班台。"
        self.add_messages([("user", duplicate)] * 3 + [("assistant", duplicate), ("user", source)])
        encoder = ScoredEncoder({duplicate: .90, source: .89})
        topic = "展柜钥匙"
        with patch.object(history_search, "history_encoder", return_value=encoder):
            self.assertEqual([x["message_id"] for x in self.recall(topic)], [1, 4, 5])
            for prompt in ("两次的说法有什么不同？", "我一共发了几遍？", "把每条原话都列出来。",
                           "Compare the earlier versions.", "How many times was the note repeated?"):
                with self.subTest(request=prompt):
                    self.assertEqual([x["message_id"] for x in self.recall(topic, prompt)], [1, 2, 3])
            self.assertEqual([x["message_id"] for x in self.recall(topic, oldest=True)], [1, 2, 3])
            first = self.recall(topic, "只要最早的那条原话")
            self.assertEqual([x["message_id"] for x in first], [1])
            direct = history_search.search_history(self.db, "s", 100, "展柜钥匙重复几次")
            self.assertEqual([x["message_id"] for x in direct["items"]], [1, 2, 3])

    def test_near_matches_and_equal_windows_of_distinct_messages_remain_separate(self):
        prefix = "场地通知：苗木抵达后，请先填写入场手续。" * 19
        first = prefix + "货物停在南门。"
        second = prefix + "货物停在西门。"
        third = prefix + "货物停在北门。"
        self.add_messages([("user", text) for text in (first, second, third)])
        with patch.object(history_search, "history_encoder", return_value=None):
            actual = self.recall("苗木抵达")
        self.assertEqual([x["message_id"] for x in actual], [1, 2, 3])
        self.assertEqual(len({x["excerpt"] for x in actual}), 1)

    def test_quote_keeps_paraphrase_below_a_lone_literal_distractor(self):
        topic = "泊船处停用"
        messages = ["“泊船处停用”是报上的一个标题。", "渡口暂停靠岸，我改在上游的浮桥接人。",
                    "三楼的窗户要刷漆。"]
        self.add_messages([("user", text) for text in messages])
        scores = ScoredEncoder(dict(zip(messages, [.95, .88, .70], strict=True)))
        with patch.object(history_search, "history_encoder", return_value=scores):
            self.assertEqual([x["message_id"] for x in self.recall(topic)], [1])
            quote = self.recall(topic, "我当时提到码头关闭后的碰头地点。请给我原句。")
            self.assertEqual([x["message_id"] for x in quote], [1, 2])

    def test_quote_keeps_a_relevant_source_covering_a_new_query_term(self):
        topic = "盆栽 遮阴"
        first = "盆栽摆在台阶边。"
        variants = [f"花盆登记到了第{i}页。" for i in range(9)]
        second = "中午要遮阴，免得叶子晒蔫。"
        messages = [first, *variants, second]
        scores = {first: .94, second: .86, **dict.fromkeys(variants, .93)}
        self.add_messages([("user", m) for m in messages])
        with patch.object(history_search, "history_encoder", return_value=ScoredEncoder(scores)):
            items = self.recall(topic, "有哪些可用的办法？请贴原句和消息编号。")
        self.assertIn(len(messages), [x["message_id"] for x in items])
        self.assertLessEqual(len(items), 8)

    def test_focused_clause_can_retrieve_a_source_below_the_primary_quality_floor(self):
        broad = "route planning after dark"
        focus = "Where could we leave a spare torch"
        request = f"During a night walk, {focus}? I forgot the trail. Please quote the earlier messages."
        distractors = [f"The trail office recorded a booking in folder {i}." for i in range(9)]
        south = "We kept an extra lamp in the picnic shelter."
        north = "A backup flashlight sat under the bridge."
        self.add_messages([("user", m) for m in [*distractors, south, north]])
        # Even a focused lookup must ignore exact matches outside this turn's scope.
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO chat_sessions VALUES ('other','private','now','now')")
            db.executemany(
                "INSERT INTO chat_messages(id,session_id,role,content,created_at) VALUES (?,?,'user',?,'now')",
                [(99, "other", focus), (101, "s", focus)],
            )
            db.commit()

        class ByQueryEncoder(ScoredEncoder):
            query_batches = []
            documents = []

            def encode(self, texts, *, query=False):
                if query:
                    self.query_batches.append(list(texts))
                    return [s.encode() for s in texts]
                self.documents.extend(texts)
                return super().encode(texts)

            def scores(self, query_vector, vectors):
                primary = super().scores(query_vector, vectors)
                if query_vector == focus.encode():
                    return [.95 if n < .7 else (.94 if n > .935 else .70) for n in primary]
                return primary

        encoder = ByQueryEncoder({**dict.fromkeys(distractors, .92), south: .94, north: .60})
        with patch.object(history_search, "history_encoder", return_value=encoder):
            actual = self.recall(broad, request)
            ordinary = self.recall(broad)
        ids = {x["message_id"] for x in actual}
        self.assertTrue({10, 11} <= ids)
        self.assertNotIn(11, [x["message_id"] for x in ordinary])
        self.assertEqual(encoder.query_batches, [[broad], [focus], [broad]])
        self.assertCountEqual(encoder.documents, [*distractors, south, north])
        self.assertTrue(ids.isdisjoint({99, 101}))
        self.assertEqual(len(ids), len(actual))

    def test_focused_dense_alternative_gets_a_slot_when_one_role_crowds_lexical_hits(self):
        from hashlib import sha256

        def candidate(mid, role, word, dense):
            digest = sha256(str(mid).encode()).digest()
            return history_search.Candidate(mid, role, 0, 20, digest, frozenset([word]) if word else frozenset(),
                                            -1, dense)

        subject = candidate(30, "user", "handle", .88)
        variants = [candidate(i, "assistant", "", .92 - i * .001) for i in range(1, 9)]
        paraphrase = candidate(31, "user", "", .91)
        primary = [candidate(i, "user", "", .95) for i in range(50, 58)]
        scored = [(1.0, .8, subject)] + [(v.dense, 0, v) for v in [*variants, paraphrase]]
        focused = history_search._focused_candidates(scored, .86)
        visible = history_search._merge_quote_candidates(primary, focused)
        # With three searches the verifier may only admit the first five
        # results from each. Keep both main hits and the focused alternatives.
        self.assertEqual([c.message_id for c in visible[:5]], [50, 51, 30, 1, 31])
        self.assertEqual({c.message_id for c in visible}, {50, 51, 52, 53, 54, 30, 1, 31})

    def test_quote_makes_room_for_requested_writer_and_retains_both_roles(self):
        assistant = ["关于库房的备注 " + str(i) for i in range(9)]
        user = ["我在清点货架时记录了一件事 " + str(i) for i in range(7)]
        self.add_messages([("assistant", text) for text in assistant] + [("user", text) for text in user])
        scores = ScoredEncoder(dict(zip(assistant + user, [.93] * 9 + [.91] * 7, strict=True)))
        with patch.object(history_search, "history_encoder", return_value=scores):
            query = "物料点数"
            quote = self.recall(query, "我当时怎么记的？请逐字引用那条消息。")
            self.assertEqual(len(quote), 8)
            self.assertEqual([x["message_id"] for x in quote if x["role"] == "user"], [10, 11, 12, 13, 14])
            self.assertEqual([x["message_id"] for x in quote[:2]], [1, 2])
            reverse = self.recall(query, "你之前给我的建议写在哪条消息里？请给原句。")
            self.assertEqual(reverse[0]["message_id"], 1)
            self.assertIn("user", {x["role"] for x in reverse})
            two = self.recall(query, "我说过、你也说过。请分别引用消息里的两种原话。")
            self.assertEqual([x["message_id"] for x in two[:2]], [1, 2])
            self.assertEqual({x["role"] for x in two}, {"user", "assistant"})

    def test_ambiguous_quote_needs_distinct_answers_but_explicit_repeats_keep_ids(self):
        repeated = "场务确认签到本已收到。"
        choices = ["后备站点可以选旧车棚。", "后备站点也可选西侧水房。"]
        self.add_messages([("assistant", repeated)] * 12 + [("user", text) for text in choices])
        scores = ScoredEncoder({repeated: .92, choices[0]: .91, choices[1]: .90})
        with patch.object(history_search, "history_encoder", return_value=scores):
            choices_only = self.recall("集合的预备地点", "有两条备选说法，分别附原句和消息编号。")
            copies = self.recall("集合的预备地点", "这条原话出现过几次？请附消息编号。")
        self.assertEqual([x["message_id"] for x in choices_only], [1, 13, 14])
        self.assertTrue({1, 2, 3}.issubset(x["message_id"] for x in copies))

    def test_full_excerpts_fit_tool_budget_without_losing_later_short_source(self):
        long_rows = ["长" * 350 + str(i) for i in range(7)]
        long_rows[3] = "A" * 40 + long_rows[3][40:]
        short_row = "仓库南门上了红锁。"
        self.add_messages([("user", text) for text in long_rows + [short_row]])
        scores = {text[start:end]: .91 for text in long_rows for start, end in history_search._windows(text)}
        scores[short_row] = .90
        with patch.object(history_search, "history_encoder", return_value=ScoredEncoder(scores)):
            context = ToolExecutionContext(self.db, "s", "turn", 100, "请给之前写的原句和消息编号。")
            result = recall_chat_history(context, RecallChatHistoryArgs(query="接货地点", mode="semantic"))
        items = result.data["items"]
        self.assertLess(len(items), 8)
        self.assertIn(8, [item["message_id"] for item in items])
        self.assertTrue(all(len(x["excerpt"]) == 320 for x in items if x["message_id"] < 8))
        payload = ToolExecutionResult("recall_chat_history", "", "ok", result).model_payload()
        self.assertLessEqual(estimate_json_tokens(payload), HISTORY_RESULT_TOKENS)

    def test_quote_can_verify_distant_suggestions_in_one_message(self):
        rejected = "白釉样片可以淋水，这句话是采购者建议的。"
        accepted = "我的安排是把白釉样片装进防潮袋。"
        source = rejected + "本批陶坯将于月底验收，暂存于木架上。" * 58 + accepted
        self.add_messages([("user", source), ("user", source)])
        windows = (source[start:end] for start, end in history_search._windows(source))
        scores = {w: .94 if rejected in w else (.90 if accepted in w else .67) for w in windows}
        with patch.object(history_search, "history_encoder", return_value=ScoredEncoder(scores)):
            actual = self.recall("样品如何避免返潮", "我当时对保管样品是什么安排？请给原句。")
        self.assertEqual([item["message_id"] for item in actual], [1, 1])
        self.assertIn(rejected, actual[0]["excerpt"])
        self.assertIn(accepted, actual[1]["excerpt"])
        for item in actual:
            self.assertEqual(item["excerpt"], source[item["offset"]:item["offset"] + len(item["excerpt"])])

    def test_reserving_one_slot_can_displace_a_distinct_literal_source(self):
        topic = "十号展台"
        messages = ["十号展台的付款截止日期是周四。", "十号展台的登记押金是两百元。",
                    "十号展台的集合时间是八点。", "隔壁展位的集合时间也是八点。"]
        self.add_messages([("user", text) for text in messages])
        with patch.object(history_search, "history_encoder", return_value=ScoredEncoder(
                dict(zip(messages, [.94, .93, .91, .95], strict=True)))):
            self.assertEqual([x["message_id"] for x in self.recall(topic)], [1, 2, 4])
            self.assertEqual([x["message_id"] for x in self.recall(topic, "请列出所有展台通知")], [1, 2, 3])

    @unittest.skipUnless(os.environ.get("AI_HISTORY_EMBEDDING_DIR"), "optional local history model")
    def test_real_windscreen_paraphrase_survives_keyword_distractors(self):
        self.assertIsNotNone(history_encoder())
        topic = "山上麦克风拾进了风的声音"
        messages = [
            "给录音笔套上毛绒防风罩，避开气流直吹，可以让山顶的采访音轨听得清楚。",
            "山上麦克风是摄影组借给我们的设备。",
            "山上麦克风的保管登记交给现场导演了。",
            "山上麦克风回收之后记得签字。",
            "我把日落的照片收藏起来了。",
        ]
        self.add_messages([("user", text) for text in messages])
        hybrid = self.recall(topic, "请比较所有关于录音设备的留言。")
        ordinary = self.recall(topic, "我之前是怎么处理山里采访的噪声的？")
        self.assertEqual([x["message_id"] for x in hybrid][:2], [x["message_id"] for x in ordinary][:2])
        self.assertNotIn(1, [x["message_id"] for x in hybrid])
        self.assertIn(1, [x["message_id"] for x in ordinary])
