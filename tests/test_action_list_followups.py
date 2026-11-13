"""Regression checks for the 2026-09-28 follow-up UX items."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ActionListFollowupTests(unittest.TestCase):
    def test_solution_progress_is_not_a_floating_overlay(self):
        css = (ROOT / "assets" / "solution-progress.css").read_text(encoding="utf-8")
        builder = (ROOT / "scripts" / "build" / "build_html_site.py").read_text(encoding="utf-8")
        self.assertNotRegex(css, r"\.solution-progress\s*\{[^}]*position\s*:\s*(?:sticky|fixed)")
        self.assertNotRegex(css, r"\.solution-progress\s*\{[^}]*z-index\s*:")
        self.assertIn('"?v=20261009-static"', builder)

    def test_solution_progress_has_lazy_ac_history_and_safe_date_rendering(self):
        builder = (ROOT / "scripts" / "build" / "build_html_site.py").read_text(encoding="utf-8")
        script = (ROOT / "assets" / "solution-progress.js").read_text(encoding="utf-8")
        self.assertIn('id="solutionProgressHistoryButton"', builder)
        self.assertIn('id="solutionProgressHistory"', builder)
        self.assertIn(
            'protectedFetch("/api/submissions?problem_id=" + encodeURIComponent(problemId)',
            script,
        )
        self.assertIn('historyButton.addEventListener("click", function () {', script)
        self.assertIn('if (!expanded) loadSubmissionHistory();', script)
        self.assertIn('item.status === "ac"', script)
        self.assertIn("InterviewForgeTime.formatDateTime(item.submitted_at)", script)
        self.assertIn('auth.handleUnauthorized("记录本题学习进度")', script)
        self.assertNotIn("redirectToLogin();", script)
        self.assertIn("class=\"solution-progress-help\"", builder)
        self.assertIn("FSRS 记忆模型根据本次评分动态计算", builder)

    def test_solution_arrow_navigation_is_global_but_does_not_steal_controls(self):
        builder = (ROOT / "scripts" / "build" / "build_html_site.py").read_text(encoding="utf-8")
        self.assertIn('document.addEventListener("keydown", function (event)', builder)
        self.assertIn('target.closest("input, textarea, select, button, a, [contenteditable=\'true\']")', builder)

    def test_reader_sticky_bar_stays_removed_by_design(self):
        # a331fcfb（"remove floating bookshelf chapter status"）刻意移除了悬浮
        # 阅读进度条及其小目录：这里反向断言，防止构建回退时悄悄复活。
        # 注意：章节页 on-page 目录的 re.findall(r'<h([23]) id=…'）是另一处
        # 正当用途（otp 高亮），不在禁止之列。
        builder = (ROOT / "scripts" / "build" / "build_library.py").read_text(encoding="utf-8")
        self.assertNotIn('id="readerSticky"', builder)
        self.assertNotIn("bar.hidden=entries[0].isIntersecting", builder)
        self.assertNotIn(".reader-sticky[hidden]{display:none}", builder)
        self.assertIn("otp_items = re.findall(r'<h([23]) id=", builder)

    def test_streak_message_reflects_today_round_count(self):
        template = (ROOT / "tools" / "templates" / "dashboard.tpl").read_text(encoding="utf-8")
        self.assertIn('id="streakMessage"', template)
        self.assertIn("Number(summary.today_rounds||0)>0", template)
        self.assertIn("今天还没完成一轮，先从一道题开始", template)


if __name__ == "__main__":
    unittest.main()
