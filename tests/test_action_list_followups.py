"""Regression checks for the 2026-09-28 follow-up UX items."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ActionListFollowupTests(unittest.TestCase):
    def test_solution_progress_has_lazy_ac_history_and_safe_date_rendering(self):
        builder = (ROOT / "scripts" / "build" / "build_html_site.py").read_text(encoding="utf-8")
        script = (ROOT / "assets" / "solution-progress.js").read_text(encoding="utf-8")
        self.assertIn('id="solutionProgressHistoryButton"', builder)
        self.assertIn('id="solutionProgressHistory"', builder)
        self.assertIn('fetch("/api/submissions?problem_id="', script)
        self.assertIn('item.status === "ac"', script)
        self.assertIn("InterviewForgeTime.formatDateTime(item.submitted_at)", script)
        self.assertIn("if (response.status === 401) { redirectToLogin(); return; }", script)
        self.assertIn("class=\"solution-progress-help\"", builder)
        self.assertIn("FSRS 记忆模型根据本次评分动态计算", builder)

    def test_solution_arrow_navigation_is_global_but_does_not_steal_controls(self):
        builder = (ROOT / "scripts" / "build" / "build_html_site.py").read_text(encoding="utf-8")
        self.assertIn('document.addEventListener("keydown", function (event)', builder)
        self.assertIn('target.closest("input, textarea, select, button, a, [contenteditable=\'true\']")', builder)

    def test_reader_sticky_bar_and_h2_h3_toc_are_generated(self):
        builder = (ROOT / "scripts" / "build" / "build_library.py").read_text(encoding="utf-8")
        self.assertIn('id="readerSticky"', builder)
        self.assertIn("new IntersectionObserver(function(entries){bar.hidden=entries[0].isIntersecting}", builder)
        self.assertIn("re.findall(r'<h([23]) id=", builder)
        self.assertIn(".reader-sticky[hidden]{display:none}", builder)

    def test_streak_message_reflects_today_round_count(self):
        template = (ROOT / "tools" / "templates" / "dashboard.tpl").read_text(encoding="utf-8")
        self.assertIn('id="streakMessage"', template)
        self.assertIn("Number(summary.today_rounds||0)>0", template)
        self.assertIn("今天还没完成一轮，先从一道题开始", template)


if __name__ == "__main__":
    unittest.main()
