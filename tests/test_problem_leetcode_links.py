import unittest
from pathlib import Path
import sys
import re

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from tools.build_hot100 import LEETCODE_BASE, LEETCODE_SLUGS, PROBLEMS, problem_filename
from scripts.build.build_hot100 import (
    extract_original_sections,
    normalize_original_body,
    split_problem_statement,
)


class ProblemLeetCodeLinkTests(unittest.TestCase):
    def test_split_problem_statement_removes_repeated_statement_sections(self):
        clean = """### 题目与约束
题面和约束。

### 思路推导
先建立不变量。

### 题目与约束
重复题面，不应再次出现在解法中。

### Java 实现
实现代码。
"""
        statement, rest = split_problem_statement(clean)

        self.assertEqual(statement, "题面和约束。")
        self.assertEqual(rest.count("### 题目与约束"), 0)
        self.assertIn("### 思路推导", rest)
        self.assertIn("### Java 实现", rest)

    def test_problem_statement_is_unique_and_before_derivation(self):
        for problem in PROBLEMS:
            stem = problem_filename(problem)
            md_path = ROOT / "books" / "hot100" / "03-题解" / str(problem["folder"]) / stem
            markdown = md_path.read_text(encoding="utf-8")
            headings = list(re.finditer(r"(?m)^##\s+题目与约束\s*$", markdown))
            self.assertEqual(len(headings), 1, md_path.name)
            derivation = re.search(r"(?m)^##\s+(?:完整推导|解法\s+)", markdown)
            self.assertIsNotNone(derivation, md_path.name)
            self.assertLess(headings[0].start(), derivation.start(), md_path.name)

            html_path = md_path.with_suffix(".html")
            soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
            html_headings = [
                heading
                for heading in soup.find_all(["h2", "h3"])
                if heading.get_text(" ", strip=True) == "题目与约束"
            ]
            self.assertEqual(len(html_headings), 1, html_path.name)

    def test_examples_and_images_survive_statement_deduplication(self):
        expected_examples = {105: 2, 124: 2, 236: 3, 437: 2, 994: 3}
        source_sections = extract_original_sections()

        for pid, example_count in expected_examples.items():
            problem = next(item for item in PROBLEMS if int(item["id"]) == pid)
            md_path = ROOT / "books" / "hot100" / "03-题解" / str(problem["folder"]) / problem_filename(problem)
            markdown = md_path.read_text(encoding="utf-8")
            statement_start = markdown.index("## 题目与约束")
            statement_end = markdown.index("## 核心不变量", statement_start)
            statement = markdown[statement_start:statement_end]
            example_heading = r"(?m)^\s*(?:[-*]\s+)?\*\*示例\s+\d+：?\*\*"
            self.assertEqual(len(re.findall(example_heading, statement)), example_count, md_path.name)

            images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", statement)
            self.assertTrue(images, md_path.name)
            for image in images:
                self.assertTrue((ROOT / "assets" / "leetcode" / Path(image).name).is_file(), image)

            source_variants = source_sections[pid]
            self.assertTrue(source_variants, f"missing source for {pid}")
            source_statement, _ = split_problem_statement(normalize_original_body(source_variants[0][1]))
            self.assertEqual(len(re.findall(example_heading, source_statement)), example_count, f"source {pid}")

            soup = BeautifulSoup(md_path.with_suffix(".html").read_text(encoding="utf-8"), "html.parser")
            heading = next(h for h in soup.find_all("h2") if h.get_text(" ", strip=True) == "题目与约束")
            section_nodes = []
            sibling = heading.find_next_sibling()
            while sibling and not (sibling.name == "h2" and sibling.get_text(" ", strip=True) == "核心不变量"):
                section_nodes.append(sibling)
                sibling = sibling.find_next_sibling()
            rendered_statement = " ".join(node.get_text(" ", strip=True) for node in section_nodes)
            self.assertEqual(len(re.findall(r"示例\s+\d+[:：]", rendered_statement)), example_count, md_path.name)
            self.assertTrue(any(node.find("img") for node in section_nodes), md_path.with_suffix(".html").name)

        tree_pages = {
            105: "leftSize = inRoot - inStart",
            124: "向上汇报一条支路",
            236: "左右都有结果",
        }
        for pid, explanation in tree_pages.items():
            problem = next(item for item in PROBLEMS if int(item["id"]) == pid)
            md_path = ROOT / "books" / "hot100" / "03-题解" / str(problem["folder"]) / problem_filename(problem)
            self.assertIn(explanation, md_path.read_text(encoding="utf-8"), md_path.name)

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
