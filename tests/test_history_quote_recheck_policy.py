"""The extra model call should never replenish a depleted turn or show either raw decision."""
import asyncio
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from interview_forge.ai.chat import quote_selection as quotes
from interview_forge.ai.chat.tool_orchestrator import ToolOrchestrator
from interview_forge.ai.tools.contracts import ToolExecutionContext
from interview_forge.ai.tools.policy import ToolPolicy
from tests.test_ai_tool_orchestrator import FakeChunk, ScriptedModel


class QuoteRecheckBudgetTests(unittest.TestCase):
    def test_last_permitted_model_round_returns_checked_abstention_and_actual_usage(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "messages.db"
            with closing(sqlite3.connect(source)) as conn, conn:
                conn.execute("CREATE TABLE chat_messages(id,session_id,role,content)")
                conn.execute("INSERT INTO chat_messages VALUES(1,'s','user','每周三核对订单。')")
            ctx = ToolExecutionContext(source, "s", "turn", 2, "之前约定核对订单是哪一天？请附原话和编号。")
            item = dict(message_id=1, role="user", offset=0, excerpt="每周三核对订单。")
            denied = json.dumps({"status": "none", "quotes": []})
            model = ScriptedModel([[FakeChunk(denied, usage={"input_tokens": 15, "output_tokens": 8})]])
            engine = ToolOrchestrator(policy=ToolPolicy(max_rounds=2))
            with patch.object(quotes, "review_after_rejection", return_value=True):
                answer, refs = asyncio.run(engine._quote_answer_round(model, ctx, [[item]], 2, partial=False))
            self.assertEqual(model.calls, 1)
            self.assertEqual(refs, ())
            self.assertEqual(answer.text, quotes.NO_QUOTE)
            self.assertEqual(answer.usage, {"input_tokens": 15, "output_tokens": 8})
