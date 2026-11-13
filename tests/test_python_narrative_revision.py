"""Protect the approved source attribution and explanatory publication contract."""
import ast

import markdown as markdown_library
import pytest
from bs4 import BeautifulSoup

from scripts.build.python_hot100 import load_problem_curriculum, render_python_problem_panel


CURRICULUM = load_problem_curriculum()


def test_authored_example_survives_markdown_rendering_and_keeps_one_submission():
    item = {
        "teaching_markdown": "### 思路推导\n\n拿到 `eat` → 排序成 `aet` → 放入对应抽屉。\n\n1. 建一个空字典。\n2. 同类单词追加到同一列表。",
        "explanation_markdown": "### 易错点\n\n`get(key, [])` 不会将默认列表存回字典。",
        "source": "原收录 A & B",
        "source_note": "沿用排序思路。\n变量和注释按本页整理。",
        "code": "class Solution:\n    def solve(self):\n        groups = {}\n        return groups",
        "time": "O(n)", "space": "O(n)", "complexity_reason": "每项访问一次。",
    }
    rendered = markdown_library.markdown(
        render_python_problem_panel(item), extensions=["extra", "sane_lists", "toc", "codehilite"]
    )
    soup = BeautifulSoup(rendered, "html.parser")
    panel = soup.select_one('section.language-panel[data-lang="python"]')
    assert panel is not None
    assert "拿到 eat → 排序成 aet" in " ".join(panel.get_text(" ").split())
    assert "原收录 A & B" in panel.get_text(" ")
    assert len(panel.select("pre")) == 1
    assert len(panel.select("ol li")) == 2


@pytest.mark.parametrize("problem_id", sorted(CURRICULUM))
def test_reviewed_narrative_and_sources_are_published_without_review_notes(problem_id):
    item = CURRICULUM[problem_id]
    markdown = render_python_problem_panel(item)
    assert item["teaching_markdown"].strip() in markdown
    assert item["explanation_markdown"].strip() in markdown
    assert "参考来源：" in markdown
    assert item["source"] in markdown
    assert "### 为什么选这个解" not in markdown
    assert "### 核心不变量" not in markdown
    assert "revision_notes" not in markdown
    assert "logs/python-narrative-revision" not in markdown
    assert len(item["revision_notes"]) > 0


@pytest.mark.parametrize("problem_id", sorted(CURRICULUM))
def test_submission_keeps_signatures_but_omits_local_type_boilerplate(problem_id):
    tree = ast.parse(CURRICULUM[problem_id]["code"])
    assert not any(isinstance(node, ast.AnnAssign) for node in ast.walk(tree))
    assert not any(isinstance(node, ast.ClassDef) and node.name in {"ListNode", "TreeNode"}
                   for node in ast.walk(tree))


def test_approved_anagram_sorting_example_and_python_api_warning_stay_together():
    item = CURRICULUM[49]
    assert 'sorted(' in item["code"]
    assert 'groups = {}' in item["code"]
    assert 'eat' in item["teaching_markdown"] and 'aet' in item["teaching_markdown"]
    assert '抽屉' in item["teaching_markdown"]
    assert 'get' in item["explanation_markdown"]
