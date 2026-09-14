import unittest
import shutil
import subprocess
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
        self.assertIn("payload.display_name || row.dataset.label || toolLabels[toolName]", self.source)
        self.assertNotIn("toolLabels[name]", self.source)
        self.assertIn("node._toolStatus", self.source)

    def test_history_messages_do_not_replay_tool_status_and_heartbeat_is_ignored(self):
        self.assertIn("(payload.items || []).forEach(function (item) { renderMessage(item, fragment); });", self.source)
        self.assertIn("if (data)", self.source)
        self.assertNotIn("JSON.stringify(payload)", self.source)
        self.assertNotIn("payload.call_id", self.source.split("row.textContent", 1)[-1])

    def test_message_event_contract_remains_in_parser(self):
        for event_name in ("message.start", "message.delta", "message.done", 'name === "error"'):
            self.assertIn(event_name, self.source)

    def test_action_confirmation_ui_uses_safe_action_api_and_pending_reload(self):
        self.assertIn('name === "tool.confirmation_required"', self.source)
        self.assertIn("/api/chat/actions/", self.source)
        self.assertIn("actionTaskId", self.source)
        self.assertIn("/api/leetcode/sync/status?task_id=", self.source)
        self.assertIn("watchLeetCodeSync", self.source)
        self.assertIn("新增提交", self.source)
        self.assertIn("interviewforge:learning-data-updated", self.source)
        self.assertIn("actions.hidden = true", self.source)
        self.assertIn('decision === "confirm"', self.source)
        self.assertIn('decision === "cancel"', self.source)
        self.assertIn('"/" + decision', self.source)
        self.assertIn("/actions?status=pending", self.source)
        self.assertIn("确认", self.source)
        self.assertIn("取消", self.source)
        self.assertNotIn("action.arguments", self.source)

    def test_page_context_and_failed_turns_reload_persisted_history(self):
        self.assertIn("page_context", self.source)
        self.assertIn("currentPageContext", self.source)
        self.assertIn("reloadCurrentSession", self.source)
        self.assertIn("cancelRequested", self.source)
        self.assertIn("interviewforge:page-context", self.source)
        self.assertIn("interviewforge:request-page-context", self.source)

    def test_new_tool_labels_use_server_display_name(self):
        self.assertIn('var label = payload.display_name || row.dataset.label || toolLabels[toolName] || "工具";', self.source)
        self.assertIn('if (name === "tool.start") row.dataset.label = label;', self.source)

    def test_launcher_and_context_assets_exist(self):
        self.assertTrue((ROOT / "assets" / "ai-launcher.js").exists())
        self.assertTrue((ROOT / "assets" / "ai-launcher.css").exists())
        self.assertTrue((ROOT / "assets" / "ai-page-context.js").exists())
        page = (ROOT / "pages" / "ai-assistant.html").read_text(encoding="utf-8")
        self.assertIn("ai-assistant.css", page)
        self.assertIn("ai-page-context.js", page)

    def test_markdown_renderer_covers_gfm_blocks_and_safe_external_links(self):
        self.assertIn("markdown-table-wrap", self.source)
        self.assertIn("<thead><tr>", self.source)
        self.assertIn("<blockquote>", self.source)
        self.assertIn("target=\\\"_blank\\\" rel=\\\"noopener noreferrer\\\"", self.source)
        self.assertIn("javascript|data|vbscript", self.source)
        self.assertIn("esc(code.join", self.source)

    def test_embedded_layout_and_theme_sync_contracts_exist(self):
        css = (ROOT / "assets" / "ai-assistant.css").read_text(encoding="utf-8")
        launcher = (ROOT / "assets" / "ai-launcher.css").read_text(encoding="utf-8")
        theme = (ROOT / "assets" / "theme-toggle.js").read_text(encoding="utf-8")
        self.assertIn("100dvh", css)
        self.assertIn("top: 50%", launcher)
        self.assertIn("button.hidden = true", (ROOT / "assets" / "ai-launcher.js").read_text(encoding="utf-8"))
        self.assertIn('event.key === KEY', theme)
        self.assertIn('embedded', theme)

    def test_page_context_refresh_is_throttled_and_request_scoped(self):
        launcher = (ROOT / "assets" / "ai-launcher.js").read_text(encoding="utf-8")
        self.assertIn("requestAnimationFrame", launcher)
        self.assertIn("request_id", launcher)
        self.assertIn("requestFreshPageContext", self.source)
        self.assertIn("pageContextWaiters", self.source)

    def test_streaming_hot_path_uses_throttled_plain_text_preview(self):
        delta_block = self.source.split('else if (name === "message.delta"', 1)[1].split('else if (name === "tool.start"', 1)[0]
        self.assertIn("bubble._rawText", delta_block)
        self.assertIn("scheduleStreamRender(bubble)", delta_block)
        self.assertNotIn("markdown(", delta_block)
        self.assertNotIn("innerHTML", delta_block)
        self.assertNotIn("scrollBottom", delta_block)
        self.assertIn("STREAM_RENDER_INTERVAL = 100", self.source)
        self.assertIn("bubble._streamRenderTimer", self.source)
        self.assertIn("function finalizeAssistant", self.source)
        self.assertIn("bubble.classList.remove(\"streaming\")", self.source)

    def test_streaming_scroll_and_session_refresh_contract(self):
        css = (ROOT / "assets" / "ai-assistant.css").read_text(encoding="utf-8")
        self.assertIn(".bubble.streaming", css)
        self.assertIn("white-space:pre-wrap", css)
        self.assertIn("function scheduleScrollBottom", self.source)
        self.assertIn("AUTO_FOLLOW_THRESHOLD = 120", self.source)
        self.assertIn("messages.addEventListener(\"scroll\", updateAutoFollow", self.source)
        self.assertIn("function refreshSessionList", self.source)
        self.assertIn("await refreshSessionList();", self.source)
        self.assertNotIn("await loadSessions();", self.source)

    def test_streaming_performance_harness(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        result = subprocess.run(
            [node, str(ROOT / "tests" / "test_ai_assistant_streaming.js")],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        self.assertIn('"delta_count":1000', result.stdout)
        self.assertRegex(result.stdout, r'"render_count":(?:[1-9][0-9]?|1[0-4][0-9])')


if __name__ == "__main__":
    unittest.main()
