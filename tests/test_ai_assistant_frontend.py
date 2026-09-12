import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AiAssistantFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "assets" / "ai-assistant.js").read_text(encoding="utf-8")

    def test_current_turn_renders_safe_tool_states(self):
        self.assertIn('name === "tool.start"', self.source)
        self.assertIn('name === "tool.done"', self.source)
        self.assertIn('name === "tool.error"', self.source)
        self.assertIn("正在查询", self.source)
        self.assertIn("已获取", self.source)
        self.assertIn("payload.message", self.source)
        self.assertIn("get_weather: \"天气信息\"", self.source)
        self.assertIn("get_learning_context: \"学习情况\"", self.source)
        self.assertIn("get_problem: \"题目信息\"", self.source)
        self.assertIn('var toolName = String(payload.name || "");', self.source)
        self.assertIn("payload.display_name || toolLabels[toolName]", self.source)
        self.assertNotIn("toolLabels[name]", self.source)
        self.assertIn("node._toolStatus", self.source)

    def test_history_messages_do_not_replay_tool_status_and_heartbeat_is_ignored(self):
        self.assertIn("(payload.items || []).forEach(renderMessage)", self.source)
        self.assertIn("if (data)", self.source)
        self.assertNotIn("JSON.stringify(payload)", self.source)
        self.assertNotIn("payload.call_id", self.source.split("row.textContent", 1)[-1])

    def test_message_event_contract_remains_in_parser(self):
        for event_name in ("message.start", "message.delta", "message.done", 'name === "error"'):
            self.assertIn(event_name, self.source)

    def test_action_confirmation_ui_uses_safe_action_api_and_pending_reload(self):
        self.assertIn('name === "tool.confirmation_required"', self.source)
        self.assertIn("/api/chat/actions/", self.source)
        self.assertIn('decision === "confirm"', self.source)
        self.assertIn('decision === "cancel"', self.source)
        self.assertIn('"/" + decision', self.source)
        self.assertIn("/actions?status=pending", self.source)
        self.assertIn("确认", self.source)
        self.assertIn("取消", self.source)
        self.assertNotIn("action.arguments", self.source)


if __name__ == "__main__":
    unittest.main()
