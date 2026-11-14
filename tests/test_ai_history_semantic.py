"""Source integrity, index lifecycle and real CPU encoder integration."""
from __future__ import annotations

import asyncio
import os
import sqlite3
import struct
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from interview_forge.ai import history_search
from interview_forge.ai.history_encoder import history_encoder
from interview_forge.ai.tools.builtins.history import RecallChatHistoryArgs, recall_chat_history
from interview_forge.ai.tools.contracts import ToolExecutionContext
from interview_forge.ai.tools.langchain_adapter import NormalizedToolCall
from interview_forge.ai.tools.registry import build_default_tool_registry
from interview_forge.ai.tools.runtime import ToolRuntime
from interview_forge.db.ai_schema import AI_DB_SCHEMA


class CountingEncoder:
    """Constant vectors isolate SQLite/cache behaviour from model accuracy."""
    def __init__(self):
        self.documents = []
        self.on_batch = None

    def encode(self, texts, *, query=False):
        if not query:
            self.documents.extend(texts)
            if self.on_batch:
                self.on_batch()
        return [struct.pack("<384f", 1, *([0] * 383))] * len(texts)

    def scores(self, _, vectors):
        return [1.0] * len(vectors)


class HistorySearchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "account.db"
        self.encoder = CountingEncoder()

    def seed(self, rows, path=None):
        with closing(sqlite3.connect(path or self.path)) as db:
            db.executescript(AI_DB_SCHEMA)
            db.executemany("INSERT OR IGNORE INTO chat_sessions VALUES (?, 'session', 'now', 'now')",
                           [(session,) for session in {r[1] for r in rows}])
            db.executemany("INSERT INTO chat_messages(id,session_id,role,content,created_at) VALUES(?,?,? ,?,'now')", rows)
            db.commit()

    def search(self, query, cutoff=3, *, current="请回顾", **kwargs):
        ctx = ToolExecutionContext(self.path, "s", "t", cutoff, current)
        return recall_chat_history(ctx, RecallChatHistoryArgs(query=query, mode="semantic", **kwargs)).data

    def test_eligibility_is_checked_before_embedding_and_again_before_returning(self):
        self.seed([(1, "other", "user", "hidden-session"), (2, "s", "user", "visible"),
                   (3, "s", "assistant", "hidden-future")])
        self.seed([(2, "s", "user", "hidden-account")], self.path.with_name("other.db"))
        with patch.object(history_search, "history_encoder", return_value=self.encoder):
            data = self.search("visible")
            self.assertEqual(self.encoder.documents, ["visible"])
            self.assertEqual(data["items"], [dict(message_id=2, role="user", offset=0, excerpt="visible")])
            self.assertEqual(data["retrieval"]["kind"], "hybrid")
            self.assertTrue(data["retrieval"]["coverage_complete"])
            self.search("same account warm query")
            self.assertEqual(self.encoder.documents, ["visible"])
        with closing(sqlite3.connect(self.path)) as db:
            ids = db.execute("SELECT message_id FROM chat_history_embeddings").fetchall()
            self.assertEqual(ids, [(2,)])

    def test_content_edit_move_and_deletion_invalidate_vectors_with_foreign_keys_off(self):
        self.seed([(1, "s", "user", "old"), (2, "other", "user", "untouched")])
        with patch.object(history_search, "history_encoder", return_value=self.encoder):
            self.search("old")
            with closing(sqlite3.connect(self.path)) as db:
                db.execute("UPDATE chat_messages SET content='new' WHERE id=1")
                db.commit()
                self.assertEqual(db.execute("SELECT count(*) FROM chat_history_embeddings").fetchone()[0], 0)
                self.assertEqual(self.search("new")["items"][0]["excerpt"], "new")
                db.execute("UPDATE chat_messages SET session_id='other' WHERE id=1")
                db.commit()
                self.assertEqual(self.search("new")["items"], [])
                db.execute("UPDATE chat_messages SET session_id='s' WHERE id=1")
                db.commit()
                self.search("new")
                db.execute("DELETE FROM chat_messages WHERE id=1")
                db.commit()
                self.assertEqual(db.execute("SELECT count(*) FROM chat_history_embeddings").fetchone()[0], 0)
        self.assertEqual(self.encoder.documents, ["old", "new", "new"])

    def test_concurrent_deletion_during_inference_neither_leaks_nor_resurrects(self):
        self.seed([(1, "s", "assistant", "private disappeared note")])

        def delete_in_another_connection():
            with closing(sqlite3.connect(self.path, timeout=0.2)) as db:
                db.execute("DELETE FROM chat_messages WHERE id=1")
                db.commit()

        self.encoder.on_batch = delete_in_another_connection
        with patch.object(history_search, "history_encoder", return_value=self.encoder):
            self.assertEqual(self.search("disappeared")["items"], [])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM chat_history_embeddings").fetchone()[0], 0)

    def test_identical_tool_call_in_one_turn_rechecks_deletions(self):
        self.seed([(1, "s", "user", "disappeared source")])
        runtime = ToolRuntime(build_default_tool_registry())
        context = ToolExecutionContext(self.path, "s", "t", 3, "older message")
        call = NormalizedToolCall(call_id="a", name="recall_chat_history", arguments={"query": "source", "mode": "semantic"})
        with patch.object(runtime, "_audit"), patch.object(history_search, "history_encoder", return_value=self.encoder):
            before = asyncio.run(runtime.execute(call=call, context=context))
            self.assertEqual(before.result.data["items"][0]["message_id"], 1)
            with closing(sqlite3.connect(self.path)) as db:
                db.execute("DELETE FROM chat_messages WHERE id=1")
                db.commit()
            after = asyncio.run(runtime.execute(call=call, context=context))
            self.assertEqual(after.status, "ok")
            self.assertEqual(after.result.data["items"], [])

    def test_offline_backfill_uses_same_index_and_is_idempotent(self):
        self.seed([(1, "s", "user", "today"), (2, "s", "assistant", "tomorrow"), (3, "other", "user", "hidden")])
        with patch.object(history_search, "history_encoder", return_value=self.encoder):
            first = history_search.backfill_session(self.path, "s")
            self.assertEqual((first["passages"], first["new_vectors"]), (2, 2))
            self.assertEqual(history_search.backfill_session(self.path, "s")["new_vectors"], 0)
            self.assertEqual(self.search("today")["items"][0]["message_id"], 1)
            self.assertEqual(self.encoder.documents, ["today", "tomorrow"])
            with closing(sqlite3.connect(self.path)) as db:
                db.execute("UPDATE chat_messages SET content='changed'")
                db.commit()
                def delete_during_backfill():
                    db.execute("DELETE FROM chat_messages WHERE id=1")
                    db.commit()
                self.encoder.on_batch = delete_during_backfill
                raced = history_search.backfill_session(self.path, "s")
                self.assertEqual((raced["passages"], raced["new_vectors"]), (2, 1))

    def test_concurrent_cold_searches_share_published_work(self):
        self.seed([(i, "s", "user", f"unique document {i}") for i in range(1, 33)])
        with patch.object(history_search, "history_encoder", return_value=self.encoder):
            with ThreadPoolExecutor(max_workers=2) as pool:
                barrier = threading.Barrier(2)

                def at_once():
                    barrier.wait(timeout=3)
                    return self.search("unique document 2", cutoff=33)

                results = [pool.submit(at_once) for _ in range(2)]
                self.assertEqual(results[0].result(timeout=5), results[1].result(timeout=5))
        self.assertEqual(len(self.encoder.documents), 32)
        self.assertEqual(len(set(self.encoder.documents)), 32)

    def test_lexical_fallback_and_partial_interruption_report_coverage(self):
        self.seed([(i, "s", "user", "fish" if i == 1 else f"noise {i}") for i in range(1, 36)])
        with patch.object(history_search, "history_encoder", return_value=None):
            data = self.search("fish", cutoff=36)
            self.assertEqual([i["message_id"] for i in data["items"]], [1])
            self.assertEqual(data["retrieval"]["kind"], "lexical")
            self.assertEqual(data["retrieval"]["embedded_passages"], 0)
        with patch.object(history_search, "history_encoder", return_value=self.encoder):
            with patch.object(history_search, "_SOFT_SECONDS", 0):
                partial = self.search("fish", cutoff=36)
                self.assertEqual(partial["items"][0]["excerpt"], "fish")
                self.assertFalse(partial["retrieval"]["coverage_complete"])
            completed = self.search("fish", cutoff=36)
            self.assertTrue(completed["retrieval"]["coverage_complete"])
            self.assertEqual(completed["retrieval"]["embedded_passages"], 35)

    def test_earliest_chooses_chronological_supported_match_and_literal_stays_literal(self):
        self.seed([(1, "s", "user", "最初的用水安排。"), (2, "s", "assistant", "修订的用水安排。")])
        with patch.object(history_search, "history_encoder", return_value=None):
            earliest = self.search("用水安排", current="我最初的约定是什么？")
            self.assertEqual([i["message_id"] for i in earliest["items"]], [1])
        for args in ({"message_id": 1}, {"query": "x", "before_message_id": 2},
                     {"query": "x", "after_message_id": 1, "oldest_first": True},
                     {"query": "x", "offset": 1}, {"query": "x", "path": "injected"}):
            with self.subTest(args=args), self.assertRaises(ValidationError):
                RecallChatHistoryArgs(mode="semantic", **args)

    @unittest.skipUnless(os.environ.get("AI_HISTORY_EMBEDDING_DIR"), "provision the pinned E5 assets for CPU integration")
    def test_real_multilingual_model_finds_old_middle_in_a_thousand_message_session(self):
        self.assertIsNotNone(history_encoder(), "configured model must load for the real semantic check")
        sentence = "动物医院约在周四傍晚，带猫咪去打加强针。"
        content = "🌿\r\n蔬菜要按重量结算，换包装时请保留收据。\n" * 100
        content += sentence + "\n"
        content += "每份报价都需要重新核对税率和发票地址。\n" * 100
        self.seed([(1, "s", "user", content)] +
                  [(i, "s", "assistant", "Keep one measuring spoon next to the kettle.") for i in range(2, 1061)])
        data = self.search("When did I arrange a vet appointment for my pet's booster vaccination?", cutoff=1061)
        self.assertTrue(data["retrieval"]["coverage_complete"])
        self.assertEqual(data["retrieval"]["kind"], "hybrid")
        self.assertGreater(data["retrieval"]["embedded_passages"], 1060)
        item = data["items"][0]
        self.assertEqual(item["message_id"], 1)
        self.assertGreater(item["offset"], 1000)
        self.assertIn(sentence, item["excerpt"])
        self.assertEqual(item["excerpt"], content[item["offset"]:item["next_offset"]])
