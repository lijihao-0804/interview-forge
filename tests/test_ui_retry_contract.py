from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UiRetryContractTests(unittest.TestCase):
    def test_history_load_failure_has_one_actionable_retry(self):
        source = (ROOT / "pages" / "history.html").read_text(encoding="utf-8")
        self.assertIn("<script src=\"../assets/ui.js?v=1\"></script>", source)
        self.assertIn(
            "InterviewForgeUI.renderError(notice,'学习记录暂时无法加载，请检查网络后重试','重试',load)",
            source,
        )
        self.assertIn("等待学习记录加载", source)

    def test_leetcode_status_query_failure_can_be_retried_without_resubmitting_sync(self):
        source = (ROOT / "pages" / "leetcode-connect.html").read_text(encoding="utf-8")
        self.assertIn("function showStatusRetry(text,label,onRetry)", source)
        self.assertIn("showStatusRetry('暂时无法读取力扣凭证状态，请检查网络后重试','重试',loadStatus)", source)
        self.assertIn("<script src=\"../assets/ui.js?v=1\"></script>", source)

    def test_dashboard_has_muted_token_and_no_orphan_history_layout_rules(self):
        source = (ROOT / "tools" / "templates" / "dashboard.tpl").read_text(encoding="utf-8")
        self.assertIn(".muted{color:var(--muted)}", source)
        for selector in (".day-list", ".event-list", ".history h2", ".history h3", ".history-columns"):
            self.assertNotIn(selector, source)


if __name__ == "__main__":
    unittest.main()
