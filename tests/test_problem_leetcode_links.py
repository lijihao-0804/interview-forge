import unittest
from pathlib import Path
import sys

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from tools.build_hot100 import LEETCODE_BASE, LEETCODE_SLUGS, PROBLEMS, problem_filename


class ProblemLeetCodeLinkTests(unittest.TestCase):
    def test_every_problem_reuses_its_own_safe_url_before_solution_and_at_end(self):
        for problem in PROBLEMS:
            pid = int(problem["id"])
            slug = LEETCODE_SLUGS.get(pid)
            if not slug:
                continue
            expected = LEETCODE_BASE.format(slug=slug)
            stem = problem_filename(problem)
            md_path = ROOT / "books" / "hot100" / "03-题解" / str(problem["folder"]) / stem
            html_path = md_path.with_suffix(".html")
            markdown = md_path.read_text(encoding="utf-8")
            self.assertEqual(markdown.count(f"]({expected})"), 2, md_path.name)
            statement_start = markdown.index("## 题目与约束")
            invariant_start = markdown.index("## 核心不变量", statement_start)
            self.assertIn(f"]({expected})", markdown[statement_start:invariant_start])

            soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
            links = [link for link in soup.find_all("a", href=expected)]
            self.assertEqual(len(links), 2, html_path.name)
            for link in links:
                self.assertEqual(link.get("target"), "_blank")
                self.assertIn("noopener", link.get("rel", []))
                self.assertIn("noreferrer", link.get("rel", []))

    def test_announcement_uses_existing_versioned_modal_without_internal_details(self):
        page = (ROOT / "cockpit.html").read_text(encoding="utf-8")
        self.assertIn('var KEY = "forge-ann-seen"', page)
        self.assertIn('var VERSION = "2026-09-08-ai-learning-analysis-launch"', page)
        self.assertIn("全新 AI 学习分析上线", page)
        self.assertIn("动态分析进度", page)
        self.assertIn("分析百分比与当前处理阶段", page)
        self.assertIn("每日 3 次", page)
        self.assertIn("题目与约束", page)
        modal = page[page.index('<div class="ann-mask"'):]
        for internal in ("SQLite", "API", "benchmark", "埋点", "数据库"):
            self.assertNotIn(internal, modal)


if __name__ == "__main__":
    unittest.main()
