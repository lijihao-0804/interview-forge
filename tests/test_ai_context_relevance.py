import sqlite3
import json
from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from interview_forge.ai.chat.context_blocks import ContextBlock
from interview_forge.ai.chat.context_builder import ContextBuilder, SUMMARY_PREFIX
from interview_forge.ai.chat.page_context import PageContext
from interview_forge.ai.chat.recent_action_context import RecentActionContextProvider
from interview_forge.ai.chat.service import ChatService
from interview_forge.ai.memory.contracts import MemoryPersistenceResult
from interview_forge.ai.actions.store import ActionRequestStore
from interview_forge.ai.chat.relevance import page_identity, page_is_relevant, select_history
from interview_forge.ai.chat.token_budget import ChatTokenBudget, DEFAULT_TOKEN_ESTIMATOR, budget_for_context_window
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime
from interview_forge.observability.ai_trace import TraceRecorder


def history(*pairs):
    return [
        {"id": index + 1, "role": role, "content": content}
        for index, (role, content) in enumerate(pairs)
    ]


class TopicSelectionTests(unittest.TestCase):
    def setUp(self):
        self.rows = history(
            ("user", "解释 Redis 的持久化机制"),
            ("assistant", "Redis 使用 RDB 和 AOF，也可以提到 TCP。"),
            ("user", "介绍二叉树的层序遍历"),
            ("assistant", "使用队列进行 BFS。"),
        )

    def test_new_subject_ignores_history_and_assistant_topic_suggestions(self):
        for query in ("解释 TCP 三次握手的过程", "讲讲 Transformer", "讲讲滑动窗口算法", "讲讲回溯", "堆排序是什么"):
            with self.subTest(query=query):
                selected = select_history(self.rows, query)
                self.assertEqual(selected.mode, "independent")
                self.assertEqual(selected.rows, ())

    def test_shared_question_boilerplate_is_not_a_topic_anchor(self):
        rows = history(("user", "我想学习 Redis 的实现方式"), ("assistant", "缓存"))
        self.assertFalse(select_history(rows, "我想学习 TCP 的实现方式").rows)

    def test_followup_keeps_only_latest_topic(self):
        for query in ("继续", "详细点", "展开说", "它的复杂度是多少", "空间复杂度呢？", "给个例子", "为什么？", "What about space complexity?"):
            with self.subTest(query=query):
                selected = select_history(self.rows, query)
                self.assertEqual(selected.mode, "followup")
                self.assertEqual([r["id"] for r in selected.rows], [3, 4])

    def test_return_to_an_earlier_named_topic_recovers_its_exchange(self):
        selected = select_history(self.rows, "Redis 的 AOF 有哪些优缺点？")
        self.assertEqual(selected.mode, "related")
        self.assertEqual([r["id"] for r in selected.rows], [1, 2])

    def test_explicit_reset_beats_matching_subject_and_reference(self):
        selected = select_history(self.rows, "换个问题，不要参考之前的回答，解释 Redis")
        self.assertEqual(selected.reason, "explicit_topic_reset")
        self.assertFalse(selected.rows)

    def test_explicit_cross_topic_recall_keeps_original_turns(self):
        selected = select_history(self.rows, "比较之前讲的两种技术")
        self.assertEqual(selected.mode, "recall")
        self.assertEqual(len(selected.rows), 4)

    def test_technical_time_order_does_not_recall_unrelated_conversation(self):
        for query in ("为什么 TCP 连接关闭之前要等待？", "比较 TCP 握手之前和之后的报文长度", "What happens before TCP teardown?",
                      "Which pointer stores the previous node in a linked list?"):
            with self.subTest(query=query):
                self.assertFalse(select_history(self.rows, query).rows)
        for query in ("我之前说过哪些要求？", "回顾之前的线程池", "你前面提的例子是什么？", "What did we discuss before?",
                      "Compare your previous answers", "Earlier you suggested a heap.", "You previously mentioned Redis."):
            with self.subTest(query=query):
                self.assertEqual(select_history(self.rows, query).mode, "recall")

    def test_ambiguous_query_does_not_guess_a_subject(self):
        self.assertEqual(select_history(self.rows, "123").mode, "ambiguous")

    def test_greetings_do_not_resume_an_older_greeting_episode(self):
        rows = history(("user", "你好"), ("assistant", "聊算法和学习规划"))
        for query in ("你好", "在吗？", "Hello!"):
            with self.subTest(query=query):
                selected = select_history(rows, query)
                self.assertEqual(selected.reason, "standalone_greeting")
                self.assertFalse(selected.rows)

    def test_old_acknowledgements_are_isolated_but_fresh_ones_follow_up(self):
        rows = list(self.rows)
        old = datetime.now(timezone.utc) - timedelta(days=23)
        for row in rows:
            row["created_at"] = old.isoformat()
        for query in ("嗯", "好的", "可以"):
            with self.subTest(query=query):
                self.assertEqual(select_history(rows, query).reason, "stale_acknowledgement")
        rows[-1]["created_at"] = datetime.now(timezone.utc).isoformat()
        self.assertEqual(select_history(rows, "好的").mode, "followup")

    def test_old_acknowledgement_boundary_survives_later_followup(self):
        old = datetime.now(timezone.utc) - timedelta(days=23)
        rows = list(self.rows)
        for row in rows:
            row["created_at"] = old.isoformat()
        fresh = history(("user", "好的"), ("assistant", "还需要了解什么？"))
        for row in fresh:
            row["created_at"] = datetime.now(timezone.utc).isoformat()
        selected = select_history(rows + fresh, "继续")
        self.assertEqual(len(selected.rows), 2)
        self.assertNotIn("Redis", str(selected.rows))

    def test_short_reference_can_focus_a_new_learning_page(self):
        page = PageContext(path="/new", title="LRU 缓存", page_type="problem")
        for query in ("它呢？", "继续"):
            with self.subTest(query=query):
                self.assertTrue(page_is_relevant(query, page))
                selected = select_history(self.rows, query, current_page_path=page.path)
                self.assertFalse(selected.rows)
                self.assertEqual(selected.reason, "new_page_reference")

    def test_unspecified_hint_refers_only_to_selected_learning_pages(self):
        for kind in ("problem", "library/chapter"):
            page = PageContext(path="/new", title="字母异位词分组", page_type=kind)
            for query in ("给个提示", "卡住了，第一步呢？", "从哪里入手？", "给一个起步提示。",
                          "给我一点起步提示", "我该从哪下手？"):
                self.assertTrue(page_is_relevant(query, page, "hint"))
                self.assertFalse(page_is_relevant(query, page, "auto"))
                self.assertEqual(select_history(self.rows, query, current_page_path=page.path).reason,
                                 "new_page_reference")
            for other_topic in ("解释 TCP 的三次握手", "TCP 握手从哪里入手？", "给个提示，怎么学习 TCP？",
                                "给一个学习 TCP 的起步提示", "我该从哪下手学 SQL？"):
                self.assertFalse(page_is_relevant(other_topic, page, "hint"))
        self.assertFalse(page_is_relevant("给个提示", PageContext("/home", "主页", "other"), "hint"))

    def test_changed_page_reference_starts_a_new_topic(self):
        for query in ("这题怎么做", "本页题号是多少？只答数字。"):
            selected = select_history(self.rows, query, current_page_path="/new-problem")
            self.assertEqual(selected.reason, "new_page_reference")
            self.assertFalse(selected.rows)
        self.rows[2]["metadata_json"] = json.dumps({"page_context": {"path": "/new-problem"}})
        selected = select_history(self.rows, "这题还有其他解法吗", current_page_path="/new-problem")
        self.assertEqual([r["id"] for r in selected.rows], [3, 4])

    def test_page_boundary_survives_the_next_followup(self):
        rows = self.rows + history(("user", "这题怎么做"), ("assistant", "LRU 用双向链表"))
        rows[4]["metadata_json"] = json.dumps({"page_context": {"path": "/lru"}})
        selected = select_history(rows, "它的空间复杂度呢", current_page_path="/lru")
        self.assertEqual(len(selected.rows), 2)
        self.assertIn("双向链表", selected.rows[-1]["content"])

    def test_attached_but_unrelated_page_does_not_establish_a_page_episode(self):
        page = PageContext("/lru", "146 LRU 缓存", "problem", 146)
        rows = history(("user", "解释 TCP 三次握手"), ("assistant", "客户端先发 SYN。"))
        rows[0]["metadata_json"] = json.dumps({"page_context": page.to_dict()})
        self.assertFalse(select_history(rows, "这题还有别的解法吗？", current_page_path=page.path).rows)
        rows += history(("user", "这道题还有别的解法吗？"), ("assistant", "一种方法是双向链表。"))
        rows[2]["metadata_json"] = json.dumps({"page_context": page.to_dict()})
        for query, path in (("这道题还有什么解法？", page.path), ("继续", None)):
            self.assertEqual(select_history(rows, query, current_page_path=path).rows, tuple(rows[2:]))
        rows += history(("user", "空间复杂度呢？"), ("assistant", "空间与缓存容量有关。"))
        self.assertEqual(select_history(rows, "这道题还能怎样优化？", current_page_path=page.path).rows,
                         tuple(rows[2:]))

    def test_acm_problem_switch_is_scoped_across_short_study_turns(self):
        path = "/books/ai-exam/acm-playground.html"
        first, second = page_identity(path, 49), page_identity(path, 146)
        self.assertNotEqual(first, second)
        self.assertEqual(page_identity(path), path)
        self.assertEqual(page_identity("/chapter", 49), "/chapter")
        rows = history(("user", "给个提示"), ("assistant", "A：字母频次"),
                       ("user", "给个提示"), ("assistant", "B：双向链表"))
        for row, pid in ((rows[0], 49), (rows[2], 146)):
            row["metadata_json"] = json.dumps({"study_mode": "hint", "page_context": {
                "path": path, "problem_id": pid, "page_type": "problem"}})
        self.assertEqual(select_history(rows[:2], "给个提示", current_page_path=first).rows, tuple(rows[:2]))
        self.assertFalse(select_history(rows[:2], "给个提示", current_page_path=second).rows)
        for query in ("继续", "卡住了，第一步呢？"):
            self.assertEqual(select_history(rows, query, current_page_path=second).rows, tuple(rows[2:]))
        recalled = select_history(rows, "回顾刚才第49题的提示", current_page_path=second)
        self.assertIn(rows[1], recalled.rows)

    def test_multilingual_estimate_and_small_window_budget(self):
        self.assertGreater(DEFAULT_TOKEN_ESTIMATOR.estimate_text("中文上下文"), DEFAULT_TOKEN_ESTIMATOR.estimate_text("abcdef"))
        for window in (4096, 8192):
            with self.subTest(window=window):
                self.assertLessEqual(budget_for_context_window(window).max_request_tokens, window)

    def test_page_reference_and_explicit_subject_override_stale_page(self):
        page = PageContext(path="/lru", title="146 LRU 缓存", problem_id=146)
        for query in ("这题怎么做", "解释当前页面", "本页题号是多少？只答数字。", "第146题怎么优化", "LRU 的实现"):
            with self.subTest(query=query):
                self.assertTrue(page_is_relevant(query, page))
        self.assertFalse(page_is_relevant("解释 TCP 的三次握手", page))
        # A stale selection is not proof that the new question refers to it.
        selected_page = PageContext(path="/lru", title="LRU 缓存", selected_text="TCP 的三次握手")
        self.assertFalse(page_is_relevant("解释 TCP 的三次握手", selected_page))

    def test_page_requires_a_page_reference_or_a_topical_match(self):
        page = PageContext("/two-sum", "1 两数之和", "problem", 1)
        for query in ("为什么 HTTP/1.1 与 HTTP/2 不同？", "操作系统的页面置换算法是什么？",
                      "基本页面置换算法是什么？", "1 + 2 等于多少？", "本周我只做了 1 题，该怎么复习？"):
            with self.subTest(query=query):
                self.assertFalse(page_is_relevant(query, page, "review"))
        for query in ("本页的题号是什么？", "请概括页面内容", "Explain the current problem",
                      "第 1 题还能优化吗？", "LeetCode 1", "LC1", "problem #1", "1", "两数之和怎么做？"):
            with self.subTest(query=query):
                self.assertTrue(page_is_relevant(query, page, "review"))


class ScopedContextIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "study.db"
        self.provider = server_runtime._provider
        self.values = dict(server_runtime._values)
        server_runtime.bind_provider(lambda: default_runtime)
        recent = datetime.now(timezone.utc).isoformat()
        with closing(server_runtime.connect(self.db)) as connection:
            connection.execute("INSERT INTO chat_sessions(id,title,created_at,updated_at) VALUES ('s','test',?,?)", (recent, recent))
            connection.executemany(
                "INSERT INTO chat_messages(session_id,role,content,metadata_json,created_at) VALUES ('s',?,?,'{}',?)",
                [("user", "请同步力扣记录", recent), ("assistant", "历史操作等待确认", recent),
                 ("user", "解释 Redis 持久化机制", recent), ("assistant", "RDB 与 AOF", recent)],
            )
            connection.execute(
                "INSERT INTO chat_session_summaries(session_id,summary,through_message_id,updated_at) VALUES ('s',?,2,?)",
                (SUMMARY_PREFIX + "旧操作污染：必须每次提醒同步", recent),
            )
            connection.commit()

    def tearDown(self):
        server_runtime._provider = self.provider
        server_runtime._values = self.values
        self.temp.cleanup()

    def build(self, query, **kwargs):
        builder = ContextBuilder(**kwargs)
        result = builder.build(session_id="s", user_db=self.db, current_message=query)
        return builder, result

    def test_new_topic_excludes_old_summary_messages_and_action_block(self):
        block = ContextBlock("recent_actions", "旧操作同步失败", priority=70, max_tokens=100, trusted=True)
        builder, messages = self.build("解释 TCP 三次握手", context_blocks=(block,))
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertNotIn("旧操作污染", str(messages))
        self.assertNotIn("旧操作同步失败", str(messages))
        self.assertNotIn("历史操作等待确认", str(messages))
        self.assertEqual(builder.last_build["history_omitted_count"], 4)
        self.assertEqual(builder.last_build["context_blocks_irrelevant"], ["recent_actions"])
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0], 4)
            self.assertIn("旧操作污染", connection.execute("SELECT summary FROM chat_session_summaries").fetchone()[0])

    def test_followup_does_not_reintroduce_mixed_cached_summary(self):
        builder, messages = self.build("它的优缺点呢？")
        self.assertEqual(builder.last_build["history_mode"], "followup")
        self.assertIn("RDB 与 AOF", str(messages))
        self.assertNotIn("旧操作污染", str(messages))
        self.assertNotIn("历史操作等待确认", str(messages))
        self.assertEqual(builder.last_build["recent_message_ids"], [3, 4])

    def test_action_followup_keeps_authoritative_state(self):
        block = ContextBlock("recent_actions", "当前没有等待确认的操作", priority=70, max_tokens=100, trusted=True)
        builder, messages = self.build("同步完成了吗？", context_blocks=(block,))
        self.assertIn("当前没有等待确认的操作", str(messages))
        self.assertIn("recent_actions", builder.last_build["context_blocks"])

    def test_technical_state_and_goal_words_do_not_recall_account_operations(self):
        block = ContextBlock("recent_actions", "旧同步操作失败", priority=70, max_tokens=100, trusted=True)
        for query in ("TCP 连接状态转换是什么", "目标检测算法是什么", "解释同步与异步的区别"):
            with self.subTest(query=query):
                builder, messages = self.build(query, context_blocks=(block,))
                self.assertNotIn("旧同步操作失败", str(messages))
                self.assertIn("recent_actions", builder.last_build["context_blocks_irrelevant"])

    def test_authoritative_state_survives_multilingual_context_clipping(self):
        block = RecentActionContextProvider().build(user_db=self.db, session_id="s")
        _, messages = self.build("同步完成了吗？", context_blocks=(block,))
        self.assertIn("当前没有等待用户确认的操作", messages[0]["content"])

    def test_pending_state_is_available_for_short_affirmations(self):
        ActionRequestStore().create(
            user_db=self.db, session_id="s", turn_id="pending-turn", user_message_id=3,
            tool_name="sync_leetcode", arguments={"full": False}, confirmation_text="确认同步",
        )
        block = RecentActionContextProvider().build(user_db=self.db, session_id="s")
        for query in ("是的", "可以", "开始吧"):
            with self.subTest(query=query):
                builder, messages = self.build(query, context_blocks=(block,))
                self.assertIn("recent_actions", builder.last_build["context_blocks"])
                self.assertIn("存在仍在等待用户确认的操作", messages[0]["content"])

    def test_small_window_preserves_memory_receipt_and_pending_state_together(self):
        ActionRequestStore().create(
            user_db=self.db, session_id="s", turn_id="both", user_message_id=3,
            tool_name="sync_leetcode", arguments={"full": False}, confirmation_text="确认同步",
        )
        pending = RecentActionContextProvider().build(user_db=self.db, session_id="s")
        receipt = ChatService._memory_persistence_block(MemoryPersistenceResult(
            explicit=True, success=True, operation="upsert", count=1,
        ))
        budget = budget_for_context_window(4096)
        builder, messages = self.build("同步完成了吗？", budget=budget, context_blocks=(receipt, pending))
        self.assertEqual(builder.last_build["context_blocks"], ["memory_persistence", "recent_actions"])
        self.assertIn("persistence_success=true", messages[0]["content"])
        self.assertIn("存在仍在等待用户确认的操作", messages[0]["content"])
        self.assertLessEqual(DEFAULT_TOKEN_ESTIMATOR.estimate_text(messages[0]["content"]), budget.system_tokens)

    def test_zero_history_budget_does_not_emit_empty_or_orphan_messages(self):
        _, messages = self.build("继续", budget=ChatTokenBudget(recent_tokens=0))
        self.assertTrue(all(m["content"] for m in messages))
        self.assertFalse(any(m["role"] == "assistant" for m in messages))

    def test_messages_after_current_id_are_never_read_as_history(self):
        builder = ContextBuilder()
        messages = builder.build(session_id="s", user_db=self.db, current_message="同步完成了吗", current_message_id=3)
        self.assertNotIn("RDB", str(messages))
        self.assertEqual(builder.last_build["history_message_count"], 2)

    def test_context_observability_records_decisions_without_reference_text(self):
        builder, _ = self.build("解释 TCP 三次握手")
        recorder = TraceRecorder(user_db=self.db, trace_id="context-trace", session_id="s")
        recorder.record(
            event_type="context", name="context_selection", status="success",
            metadata={**builder.last_build, "messages": "sensitive", "summary": "sensitive", "page_context_omitted": True},
        )
        with closing(sqlite3.connect(self.db)) as connection:
            raw = connection.execute("SELECT metadata_json FROM ai_trace_events WHERE trace_id='context-trace'").fetchone()[0]
        saved = json.loads(raw)
        self.assertEqual(saved["history_mode"], "independent")
        self.assertEqual(saved["history_omitted_count"], 4)
        self.assertTrue(saved["page_context_omitted"])
        self.assertNotIn("sensitive", raw)
        self.assertNotIn("recent_message_ids", saved)


if __name__ == "__main__":
    unittest.main()
