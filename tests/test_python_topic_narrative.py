from __future__ import annotations

import ast
from copy import deepcopy

from interview_forge.core.problem_catalog import PROBLEMS
from scripts.build.python_hot100 import (
    load_basics_curriculum,
    load_problem_curriculum,
    load_topic_curriculum,
    render_python_basic_panel,
    render_python_template_markdown,
    render_python_topic_panel,
    validate_basics_curriculum,
    validate_topic_curriculum,
)

TOPICS = load_topic_curriculum()
BASICS = load_basics_curriculum()
PROBLEMS_BY_ID = load_problem_curriculum()


def _namespace(source: str) -> dict[str, object]:
    namespace: dict[str, object] = {}
    exec(compile(source, "<python-template>", "exec"), namespace)  # noqa: S102
    return namespace


def test_topic_and_basic_narratives_pass_structural_validation() -> None:
    categories = list(dict.fromkeys(str(problem["category"]) for problem in PROBLEMS))

    assert len(TOPICS) == 17
    assert len(BASICS) == 5
    assert sum(len(item["problem_focus"]) for item in TOPICS.values()) == 100
    assert validate_topic_curriculum(TOPICS, categories, PROBLEMS_BY_ID) == []
    assert validate_basics_curriculum(BASICS) == []


def test_teaching_templates_use_ordinary_local_assignments() -> None:
    sources = [item["template"] for item in TOPICS.values()]
    sources.extend(item["template"] for item in BASICS.values())

    for source in sources:
        tree = ast.parse(source)
        assert not [node for node in ast.walk(tree) if isinstance(node, ast.AnnAssign)]
        assert not [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(isinstance(item, ast.Global) for item in node.body)
        ]


def test_every_topic_template_executes_a_representative_case() -> None:
    namespace = _namespace(TOPICS["哈希表"]["template"])
    assert namespace["two_sum"]([2, 7, 11, 15], 9) == [0, 1]
    assert namespace["two_sum"]([3, 3], 6) == [0, 1]

    namespace = _namespace(TOPICS["双指针"]["template"])
    assert namespace["max_area"]([1, 8, 6, 2, 5, 4, 8, 3, 7]) == 49

    namespace = _namespace(TOPICS["滑动窗口"]["template"])
    assert namespace["length_of_longest_substring"]("abcabcbb") == 3
    assert namespace["length_of_longest_substring"]("abba") == 2
    assert namespace["length_of_longest_substring"]("") == 0

    namespace = _namespace(TOPICS["子串"]["template"])
    assert namespace["subarray_sum"]([1, 1, 1], 2) == 2
    assert namespace["subarray_sum"]([1, -1, 0], 0) == 3

    namespace = _namespace(TOPICS["普通数组"]["template"])
    assert namespace["kadane"]([-2, 1, -3, 4, -1, 2, 1, -5, 4]) == 6
    assert namespace["kadane"]([-5, -2, -9]) == -2

    namespace = _namespace(TOPICS["矩阵"]["template"])
    assert namespace["spiral"]([[1, 2, 3], [4, 5, 6], [7, 8, 9]]) == [
        1,
        2,
        3,
        6,
        9,
        8,
        7,
        4,
        5,
    ]
    assert namespace["spiral"]([]) == []

    class ListNode:
        def __init__(self, value: int, next_node=None):
            self.val = value
            self.next = next_node

    third = ListNode(3)
    second = ListNode(2, third)
    first = ListNode(1, second)
    namespace = _namespace(TOPICS["链表"]["template"])
    head = namespace["reverse_list"](first)
    assert [head.val, head.next.val, head.next.next.val] == [3, 2, 1]
    assert head.next.next.next is None
    assert namespace["reverse_list"](None) is None

    class TreeNode:
        def __init__(self, value: int, left=None, right=None):
            self.val = value
            self.left = left
            self.right = right

    root = TreeNode(1)
    current = root
    for value in range(2, 2501):
        current.left = TreeNode(value)
        current = current.left
    namespace = _namespace(TOPICS["二叉树"]["template"])
    assert namespace["tree_height"](root) == 2500
    assert namespace["tree_height"](None) == 0

    namespace = _namespace(TOPICS["图论"]["template"])
    grid = [["1", "1", "0"], ["0", "1", "0"], ["1", "0", "1"]]
    assert namespace["count_islands"](grid) == 3

    namespace = _namespace(TOPICS["回溯"]["template"])
    assert namespace["subsets"]([1, 2]) == [[], [1], [1, 2], [2]]

    namespace = _namespace(TOPICS["二分查找"]["template"])
    lower_bound = namespace["lower_bound"]
    assert lower_bound([1, 3, 5, 7], 4) == 2
    assert lower_bound([1, 2, 2, 2, 3], 2) == 1
    assert lower_bound([1, 3], 4) == 2

    namespace = _namespace(TOPICS["栈"]["template"])
    assert namespace["daily_temperatures"]([73, 74, 75, 71, 69, 72, 76, 73]) == [
        1,
        1,
        4,
        2,
        1,
        1,
        0,
        0,
    ]

    namespace = _namespace(TOPICS["堆"]["template"])
    assert namespace["top_k_frequent"]([1, 1, 1, 2, 2, 3], 2) == [1, 2]

    namespace = _namespace(TOPICS["贪心"]["template"])
    assert namespace["max_profit"]([7, 1, 5, 3, 6, 4]) == 5
    assert namespace["max_profit"]([7, 6, 4, 3, 1]) == 0

    namespace = _namespace(TOPICS["动态规划"]["template"])
    assert namespace["can_partition"]([1, 5, 11, 5]) is True
    assert namespace["can_partition"]([1, 2, 5]) is False

    namespace = _namespace(TOPICS["多维动态规划"]["template"])
    assert namespace["min_path_sum"]([[1, 3, 1], [1, 5, 1], [4, 2, 1]]) == 7

    namespace = _namespace(TOPICS["技巧"]["template"])
    colors = [2, 0, 2, 1, 1, 0]
    assert namespace["sort_colors"](colors) is None
    assert colors == [0, 0, 1, 1, 2, 2]


def test_every_basic_template_executes_a_representative_case() -> None:
    namespace = _namespace(BASICS["01-Java刷题速查.md"]["template"])
    assert namespace["Solution"]().first_positive([0, -1, 3]) == 3
    assert namespace["Solution"]().first_positive([0, -1]) == -1

    namespace = _namespace(BASICS["02-Java数组.md"]["template"])
    values = [0, 1, 0, 3, 12]
    assert namespace["compact_nonzero"](values) is None
    assert values == [1, 3, 12, 0, 0]

    namespace = _namespace(BASICS["03-Java字符串.md"]["template"])
    signature = namespace["frequency_signature"]
    assert signature("eat") == signature("tea") == signature("ate")

    namespace = _namespace(BASICS["04-Java集合.md"]["template"])
    assert namespace["top_k_frequent"]([1, 1, 1, 2, 2, 3], 2) == [1, 2]

    namespace = _namespace(BASICS["05-排序算法.md"]["template"])
    assert namespace["sorted_search"]([3, 1, 2], 2) is True
    assert namespace["sorted_search"]([3, 1, 2], 4) is False


def test_topic_renderer_uses_authored_narrative_and_curriculum_table_values() -> None:
    topic = deepcopy(TOPICS["哈希表"])
    curriculum = deepcopy(PROBLEMS_BY_ID)
    curriculum[1]["method"] = "TABLE-METHOD"
    curriculum[1]["time"] = "TABLE-TIME"
    curriculum[1]["space"] = "TABLE-SPACE"

    rendered = render_python_topic_panel("哈希表", topic, curriculum)

    assert "先问“当前元素想查谁”" in rendered
    assert "TABLE-METHOD" in rendered
    assert "TABLE-TIME" in rendered
    assert "TABLE-SPACE" in rendered
    assert "必写模板" not in rendered
    assert "不变量与推导" not in rendered
    assert "下笔顺序" not in rendered
    assert "Python API 提示" not in rendered


def test_template_catalog_marks_sources_and_boundaries_for_all_topics() -> None:
    rendered = render_python_template_markdown(TOPICS)

    assert rendered.count("```python") == 17
    assert "每一段都要先重述变量与不变量" not in rendered
    for category, item in TOPICS.items():
        assert f"### {category}：" in rendered
        assert f"> 参考来源：{item['template_source']}" in rendered
        assert item["template_note"] in rendered


def test_approved_focus_rows_and_required_python_facts_stay_explicit() -> None:
    focus = {
        int(row["id"]): row["focus"]
        for item in TOPICS.values()
        for row in item["problem_focus"]
    }
    assert "排序" in focus[49] and "计数法只作扩展" in focus[49]
    assert "last" in focus[3] and "max" in focus[3]
    assert all(step in focus[206] for step in ("保存", "反转", "推进"))
    assert "非递增" in focus[739]

    quick_reference = BASICS["01-Java刷题速查.md"]
    truth_text = quick_reference["teaching_markdown"]
    assert '| `"0"` | `True` |' in truth_text
    assert '| `""` | `False` |' in truth_text
    assert "判题环境中提供 `ListNode`" in truth_text
    assert "右侧的 `b`、`a`" in truth_text
    assert "先整体求右侧表达式" in quick_reference["concepts"][2]["body"]

    collections = BASICS["04-Java集合.md"]
    heap_text = "\n".join(
        (collections["teaching_markdown"], collections["explanation_markdown"])
    )
    assert "Python 3.12 / CPython" in heap_text
    assert "需要最大堆时可存入负值" in heap_text

    sorting = BASICS["05-排序算法.md"]
    sort_text = "\n".join(
        (
            sorting["summary"],
            sorting["teaching_markdown"],
            sorting["explanation_markdown"],
        )
    )
    assert "不能保证额外空间 O(1)" in sort_text
    assert "最坏可分配 O(n) 临时缓冲" in sorting["concepts"][2]["body"]


def test_basic_renderer_uses_concrete_authored_sections() -> None:
    rendered = render_python_basic_panel(BASICS["05-排序算法.md"])

    assert "一个列表既有返回值也有原地操作" in rendered
    assert "排序后二分查找" in rendered
    assert "Python API 与写法" not in rendered
    assert "常用操作" in rendered


def test_all_topic_and_basic_panels_render_authored_content_and_catalog_values() -> None:
    rendered_problem_rows = 0
    for category, item in TOPICS.items():
        rendered = render_python_topic_panel(category, item, PROBLEMS_BY_ID)

        assert f"## Python 模式：{category}" in rendered
        assert item["teaching_markdown"] in rendered
        assert item["template_name"] in rendered
        assert item["template"] in rendered
        assert item["template_source"] in rendered
        assert item["template_note"] in rendered
        assert item["explanation_markdown"] in rendered
        assert rendered.count("```python") == 1
        assert rendered.count("| **") == len(item["problem_focus"])
        for row in item["problem_focus"]:
            problem_id = int(row["id"])
            curriculum = PROBLEMS_BY_ID[problem_id]
            assert f"{problem_id}. {row['title']}" in rendered
            assert str(curriculum["method"]) in rendered
            assert str(curriculum["time"]) in rendered
            assert str(curriculum["space"]) in rendered
            assert row["focus"] in rendered
        assert "必写模板" not in rendered
        assert "不变量与推导" not in rendered
        assert "选择理由" not in rendered
        assert "下笔顺序" not in rendered
        rendered_problem_rows += len(item["problem_focus"])

    assert rendered_problem_rows == 100

    for name, item in BASICS.items():
        rendered = render_python_basic_panel(item)

        assert item["title"] in rendered
        assert item["summary"] in rendered
        assert item["teaching_markdown"] in rendered
        assert item["template_name"] in rendered
        assert item["template"] in rendered
        assert item["explanation_markdown"] in rendered
        assert "### 可运行示例" in rendered
        for hint in item["api_hints"]:
            assert hint["symbol"] in rendered
            assert hint["syntax"] in rendered
            assert hint["use"] in rendered
        assert "Python API 与写法" not in rendered
