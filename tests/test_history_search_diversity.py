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
from interview_forge.ai.tools.builtins.history import RecallChatHistoryArgs, recall_chat_history
from interview_forge.ai.tools.contracts import ToolExecutionContext
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
