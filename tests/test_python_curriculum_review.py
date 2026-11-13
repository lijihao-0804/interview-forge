import json
from pathlib import Path

from bs4 import BeautifulSoup

from scripts.build import build_html_site

ROOT = Path(__file__).resolve().parents[1]
PROBLEMS = json.loads((ROOT / "tools" / "python_hot100.json").read_text(encoding="utf-8"))[
    "problems"
]
TOPICS = json.loads(
    (ROOT / "tools" / "python_hot100_topics.json").read_text(encoding="utf-8")
)["categories"]


def _execute_python(source: str) -> dict[str, object]:
    namespace: dict[str, object] = {}
    exec(compile(source, "<python-curriculum>", "exec"), namespace)  # noqa: S102
    return namespace


def test_annotate_language_toc_accepts_additional_panel_classes():
    page = """
    <html><body>
      <aside class="toc"><a href="#python-topic">Python 模式</a></aside>
      <section class="language-panel python-topic-panel" data-lang="python">
        <h2 id="python-topic">Python 模式：哈希表</h2>
      </section>
    </body></html>
    """

    rendered = build_html_site.annotate_language_toc(page)
    anchor = BeautifulSoup(rendered, "html.parser").select_one('.toc a[href="#python-topic"]')

    assert anchor is not None
    assert anchor.get("data-lang-scope") == "true"
    assert anchor.get("data-lang") == "python"


def test_render_markdown_enables_language_runtime_for_additional_panel_classes(
    tmp_path: Path, monkeypatch
):
    source = tmp_path / "topic.md"
    output = tmp_path / "topic.html"
    source.write_text(
        """# 哈希表

<section class="language-panel python-topic-panel" data-lang="python" markdown="1">

## Python 模式：哈希表

正文

</section>
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(build_html_site, "output_for_markdown", lambda _source: output)
    monkeypatch.setattr(build_html_site, "render_visual_embed", lambda *_args: "")
    monkeypatch.setattr(build_html_site, "web_rel", lambda *_args: "asset")
    monkeypatch.setattr(build_html_site, "ROOT", tmp_path)

    build_html_site.render_markdown(source)
    rendered = output.read_text(encoding="utf-8")

    assert '<script id="forge-lang-bootstrap">' in rendered
    assert 'class="markdown-body hot100-solution"' in rendered
    assert 'data-active-language="java"' in rendered


def test_polish_visual_preserves_sync_js_backslashes_when_idempotent(tmp_path: Path):
    visual = tmp_path / "visual.html"
    visual.write_text(
        "<!doctype html><html><head><title>演示</title></head><body></body></html>",
        encoding="utf-8",
    )

    build_html_site.polish_visual(visual)
    build_html_site.polish_visual(visual)
    rendered = visual.read_text(encoding="utf-8")

    assert rendered.count('id="hot100-embed-bootstrap"') == 1
    assert rendered.count('id="hot100-theme-sync"') == 1
    assert rendered.count('id="hot100-language-sync"') == 1
    assert r".replace(/（\s*Java\s*）/gi" in rendered


def test_84_equal_heights_produce_the_full_rectangle_without_mutating_input():
    problem = PROBLEMS["84"]
    namespace = _execute_python(problem["code"])

    assert namespace["Solution"]().largestRectangleArea([2, 2]) == 4
    assert namespace["Solution"]().largestRectangleArea([2, 2, 2]) == 6
    heights = [0, 2, 2, 0]
    snapshot = heights[:]
    assert namespace["Solution"]().largestRectangleArea(heights) == 4
    assert heights == snapshot
    assert "等高" in problem["invariant"]
    assert "严格" in problem["invariant"]


def test_238_prefix_suffix_order_and_product_behavior():
    problem = PROBLEMS["238"]
    namespace = _execute_python(problem["code"])
    solution = namespace["Solution"]()

    assert solution.productExceptSelf([1, 2, 3, 4]) == [24, 12, 8, 6]
    assert solution.productExceptSelf([0, 1, 2]) == [2, 0, 0]
    assert solution.productExceptSelf([1, 2, 0, 4, 0]) == [0, 0, 0, 0, 0]
    assert "左侧" in problem["invariant"] and "右侧" in problem["invariant"]


def test_kadane_topic_template_handles_input_without_slicing():
    template = TOPICS["普通数组"]["template"]
    kadane = _execute_python(template)["kadane"]

    class RejectSliceList(list):
        def __getitem__(self, index):
            if isinstance(index, slice):
                raise TypeError("Kadane template must not allocate a sliced list")
            return super().__getitem__(index)

    assert kadane(RejectSliceList([-2, 1, -3, 4, -1, 2, 1, -5, 4])) == 6
    assert kadane(RejectSliceList([-5, -2, -9])) == -2


def test_tree_topic_template_returns_height_and_matching_metadata():
    topic = TOPICS["二叉树"]
    tree_height = _execute_python(topic["template"])["tree_height"]

    class TreeNode:
        def __init__(self, value, left=None, right=None):
            self.value = value
            self.left = left
            self.right = right

    root = TreeNode(1, TreeNode(2, TreeNode(4)), TreeNode(3))

    assert tree_height(root) == 3
    assert tree_height(None) == 0
    assert topic["template_name"] == "后序返回树高"
    assert all(hint["symbol"] != "nonlocal" for hint in topic["api_hints"])
