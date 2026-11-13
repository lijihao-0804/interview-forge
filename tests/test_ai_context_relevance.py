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
from interview_forge.ai.actions.store import ActionRequestStore
from interview_forge.ai.chat.relevance import page_is_relevant, select_history
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

    def test_changed_page_reference_starts_a_new_topic(self):
        selected = select_history(self.rows, "这题怎么做", current_page_path="/new-problem")
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

    def test_multilingual_estimate_and_small_window_budget(self):
        self.assertGreater(DEFAULT_TOKEN_ESTIMATOR.estimate_text("中文上下文"), DEFAULT_TOKEN_ESTIMATOR.estimate_text("abcdef"))
        for window in (4096, 8192):
            with self.subTest(window=window):
                self.assertLessEqual(budget_for_context_window(window).max_request_tokens, window)

    def test_page_reference_and_explicit_subject_override_stale_page(self):
        page = PageContext(path="/lru", title="146 LRU 缓存", problem_id=146)
        for query in ("这题怎么做", "解释当前页面", "第146题怎么优化", "LRU 的实现"):
            with self.subTest(query=query):
                self.assertTrue(page_is_relevant(query, page))
        self.assertFalse(page_is_relevant("解释 TCP 的三次握手", page))
        # A stale selection is not proof that the new question refers to it.
        selected_page = PageContext(path="/lru", title="LRU 缓存", selected_text="TCP 的三次握手")
        self.assertFalse(page_is_relevant("解释 TCP 的三次握手", selected_page))


class ScopedContextIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "study.db"
        self.provider = server_runtime._provider
        self.values = dict(server_runtime._values)
        server_runtime.bind_provider(lambda: default_runtime)
        with closing(server_runtime.connect(self.db)) as connection:
            connection.execute("INSERT INTO chat_sessions(id,title,created_at,updated_at) VALUES ('s','test','2026-11-13','2026-11-13')")
            connection.executemany(
                "INSERT INTO chat_messages(session_id,role,content,metadata_json,created_at) VALUES ('s',?,?,'{}','2026-11-13')",
                [("user", "请同步力扣记录"), ("assistant", "历史操作等待确认"),
                 ("user", "解释 Redis 持久化机制"), ("assistant", "RDB 与 AOF")],
            )
            connection.execute(
                "INSERT INTO chat_session_summaries(session_id,summary,through_message_id,updated_at) VALUES ('s',?,2,'2026-11-13')",
                (SUMMARY_PREFIX + "旧操作污染：必须每次提醒同步",),
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
