import sqlite3
import tempfile
import unittest
from pathlib import Path

from interview_forge.ai.chat.context_blocks import ContextBlock
from interview_forge.ai.chat.context_builder import ContextBuilder, SUMMARY_PREFIX
from interview_forge.ai.chat.token_budget import (
    ChatTokenBudget,
    DEFAULT_CHAT_TOKEN_BUDGET,
    DEFAULT_TOKEN_ESTIMATOR,
)
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime


class ChatContextBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "hot100-study.db"
        self.old_provider = server_runtime._provider
        self.old_values = dict(server_runtime._values)
        server_runtime.bind_provider(lambda: default_runtime)
        self.session_id = "context-session"
        connection = server_runtime.connect(self.db)
        try:
            now = "2026-09-12T10:00:00+08:00"
            connection.execute(
                "INSERT INTO chat_sessions(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (self.session_id, "上下文测试", now, now),
            )
            connection.commit()
        finally:
            connection.close()

    def tearDown(self):
        server_runtime._provider = self.old_provider
        server_runtime._values = self.old_values
        self.temp.cleanup()

    def add_messages(self, rows):
        connection = server_runtime.connect(self.db)
        try:
            for role, content in rows:
                connection.execute(
                    "INSERT INTO chat_messages(session_id, role, content, metadata_json, created_at) "
                    "VALUES (?, ?, ?, '{}', ?)",
                    (self.session_id, role, content, "2026-09-12T10:00:00+08:00"),
                )
            connection.commit()
        finally:
            connection.close()

    def summary_row(self):
        connection = sqlite3.connect(self.db)
        try:
            return connection.execute(
                "SELECT summary, through_message_id FROM chat_session_summaries WHERE session_id = ?",
                (self.session_id,),
            ).fetchone()
        finally:
            connection.close()

    def test_short_history_has_no_summary_and_current_is_once(self):
        self.add_messages([("user", "短问题"), ("assistant", "短回答")])
        messages = ContextBuilder().build(
            session_id=self.session_id, current_message="当前问题", user_db=self.db
        )
        self.assertEqual([item["role"] for item in messages], ["system", "user", "assistant", "user"])
        self.assertEqual(sum(item["content"] == "当前问题" for item in messages), 1)
        self.assertIsNone(self.summary_row())

    def test_context_block_priority_admits_learning_before_memory(self):
        builder = ContextBuilder(
            system_prompt="system",
            budget=ChatTokenBudget(
                summary_tokens=20,
                recent_tokens=20,
                system_tokens=42,
                current_tokens=20,
                output_tokens=20,
            ),
            context_blocks=(
                ContextBlock("memory", "memory-low-priority " * 20, priority=80, max_tokens=80),
                ContextBlock("learning", "learning-high-priority " * 20, priority=90, max_tokens=80),
            ),
        )
        messages = builder.build(
            session_id=self.session_id,
            current_message="当前问题",
            user_db=self.db,
        )
        self.assertIn("ContextBlock:learning", messages[0]["content"])
        self.assertNotIn("ContextBlock:memory", messages[0]["content"])
        self.assertEqual(builder.last_build["context_blocks"], ["learning"])

    def test_repeated_current_content_keeps_earlier_turns(self):
        self.add_messages([
            ("user", "继续"),
            ("assistant", "第一次继续后的回答"),
            ("user", "继续"),
        ])
        connection = sqlite3.connect(self.db)
        try:
            current_id = connection.execute(
                "SELECT id FROM chat_messages WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                (self.session_id,),
            ).fetchone()[0]
        finally:
            connection.close()

        messages = ContextBuilder().build(
            session_id=self.session_id,
            current_message="继续",
            current_message_id=int(current_id),
            user_db=self.db,
        )
        self.assertEqual(sum(item["content"] == "继续" for item in messages), 2)
        self.assertEqual(messages[-1], {"role": "user", "content": "继续"})

    def test_summary_does_not_skip_middle_message(self):
        marker = "middle-marker-must-survive"
        self.add_messages([
            ("user", "summary-row-0"),
            ("user", "summary-row-1"),
            ("user", marker),
            ("user", "summary-row-3"),
            ("user", "summary-row-4"),
            ("user", "summary-row-5"),
        ])
        builder = ContextBuilder(
            budget=ChatTokenBudget(
                summary_tokens=600,
                recent_tokens=20,
                system_tokens=50,
                current_tokens=20,
                output_tokens=20,
            )
        )
        builder.build(
            session_id=self.session_id,
            current_message="当前问题",
            user_db=self.db,
        )
        summary, through = self.summary_row()
        self.assertIn(marker, summary)
        self.assertGreater(int(through), 0)

    def test_long_history_creates_incremental_summary_and_excludes_recent(self):
        rows = []
        for index in range(12):
            marker = f"old-marker-{index}" if index < 8 else f"recent-marker-{index}"
            rows.extend([
                ("user", marker + " 用户上下文 " + ("u" * 1800)),
                ("assistant", marker + " 助手结论 " + ("a" * 1800)),
            ])
        self.add_messages(rows)
        builder = ContextBuilder()
        messages = builder.build(
            session_id=self.session_id, current_message="当前问题", user_db=self.db
        )
        row = self.summary_row()
        self.assertIsNotNone(row)
        summary, through = row
        self.assertTrue(summary.startswith(SUMMARY_PREFIX))
        self.assertGreater(int(through), 0)
        self.assertIn("old-marker-0", summary)
        self.assertNotIn("recent-marker-11", summary)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "system")
        self.assertEqual(messages[-1], {"role": "user", "content": "当前问题"})
        self.assertEqual(sum(item["content"] == "当前问题" for item in messages), 1)
        self.assertLessEqual(builder.last_build["estimated_prompt_tokens"], DEFAULT_CHAT_TOKEN_BUDGET.max_prompt_tokens)
        self.assertLessEqual(DEFAULT_TOKEN_ESTIMATOR.estimate_text(summary), DEFAULT_CHAT_TOKEN_BUDGET.summary_tokens)
        self.assertLessEqual(
            sum(DEFAULT_TOKEN_ESTIMATOR.estimate_messages([item]) for item in messages if item["role"] != "system" or item is not messages[1]),
            DEFAULT_CHAT_TOKEN_BUDGET.recent_tokens + DEFAULT_CHAT_TOKEN_BUDGET.current_tokens + 8,
        )

    def test_summary_survives_new_builder_and_only_new_old_rows_are_appended(self):
        self.add_messages([("user", "目标一" + "x" * 800), ("assistant", "结论一" + "y" * 800)] * 12)
        first = ContextBuilder()
        first.build(session_id=self.session_id, current_message="问题 A", user_db=self.db)
        first_row = self.summary_row()
        self.assertIsNotNone(first_row)
        first_summary, first_through = first_row

        self.add_messages([("user", "新增目标二" + "z" * 1800), ("assistant", "新增结论二" + "w" * 1800)] * 8)
        second = ContextBuilder()
        second.build(session_id=self.session_id, current_message="问题 B", user_db=self.db)
        second_summary, second_through = self.summary_row()
        self.assertGreaterEqual(int(second_through), int(first_through))
        self.assertIn("新增目标二", second_summary)
        self.assertIn("目标一", second_summary)
        self.assertNotEqual(first_summary, second_summary)


if __name__ == "__main__":
    unittest.main()
