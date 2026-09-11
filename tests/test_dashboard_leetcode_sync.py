import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "tools" / "templates" / "dashboard.tpl"
INDEX = ROOT / "index.html"


class DashboardLeetcodeSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = TEMPLATE.read_text(encoding="utf-8")
        cls.index = INDEX.read_text(encoding="utf-8")

    def test_navigation_styles_and_safe_connect_link(self):
        for page in (self.template, self.index):
            nav = re.search(r'<nav class="dashboard-nav".*?</nav>', page, re.S)
            self.assertIsNotNone(nav)
            markup = nav.group(0)
            self.assertRegex(
                markup,
                r'<a href="pages/leetcode-connect\.html" target="_blank" '
                r'rel="noopener noreferrer">力扣连接</a>',
            )
            self.assertIn(
                '<button class="lc-button" id="leetcodeSyncBtn" type="button">一键同步</button>',
                markup,
            )
            self.assertNotRegex(markup, r'<a class="lc-button"[^>]*>力扣连接</a>')

    def test_incremental_request_loading_guard_and_refresh(self):
        script = self.template
        self.assertEqual(script.count("leetcodeSyncRequest('/api/leetcode/sync',{"), 1)
        self.assertIn("body:JSON.stringify({full:false,async:true})", script)
        self.assertIn("if(leetcodeSyncInFlight)return;", script)
        self.assertIn("leetcodeSyncBtn.disabled=busy", script)
        self.assertIn("busy?'同步中…':'一键同步'", script)
        self.assertIn("finally{\n    setLeetcodeSyncBusy(false);", script)
        self.assertIn("await refresh();", script)

    def test_success_and_failure_paths_are_explicit_and_safe(self):
        script = self.template
        self.assertIn("请先前往力扣连接页面填写 LEETCODE_SESSION。", script)
        self.assertIn("LEETCODE_SESSION 已过期或无效", script)
        self.assertIn("同步暂时失败，请检查网络后重试", script)
        self.assertIn("同步成功。本次处理 ${seen} 条提交，新增 ${added} 条记录。", script)
        self.assertIn("category==='not_configured'", script)
        self.assertIn("category==='session_invalid'", script)
        self.assertNotIn("${task.error}", script)

    def test_modal_accessibility_and_native_new_tab_action(self):
        for page in (self.template, self.index):
            self.assertIn('role="dialog" aria-modal="true"', page)
            self.assertIn('aria-labelledby="leetcodeSyncTitle"', page)
            self.assertIn('aria-describedby="leetcodeSyncMessage"', page)
            link = re.search(r'<a id="leetcodeSyncConnect"[^>]*>', page)
            self.assertIsNotNone(link)
            self.assertIn('href="pages/leetcode-connect.html"', link.group(0))
            self.assertIn('target="_blank"', link.group(0))
            self.assertIn('rel="noopener noreferrer"', link.group(0))
            self.assertIn('hidden', link.group(0))
        self.assertIn("event.key==='Escape'", self.template)
        self.assertIn("event.target===leetcodeSyncModal", self.template)
        self.assertIn("event.key!=='Tab'", self.template)
        self.assertIn("leetcodeSyncClose.focus()", self.template)

    def test_generated_index_contains_the_source_feature_contract(self):
        markers = (
            'id="leetcodeSyncBtn"',
            'id="leetcodeSyncModal"',
            "function runLeetcodeIncrementalSync()",
            "body:JSON.stringify({full:false,async:true})",
            "function leetcodeSyncSummary(data)",
        )
        for marker in markers:
            self.assertIn(marker, self.template)
            self.assertIn(marker, self.index)


if __name__ == "__main__":
    unittest.main()
