from __future__ import annotations

import ast
import itertools
import random
import re
from collections import deque
from typing import Any

import pytest

from interview_forge.core.problem_catalog import PROBLEMS
from scripts.build.python_hot100 import (
    load_basics_curriculum,
    load_problem_curriculum,
    load_topic_curriculum,
    validate_problem_curriculum,
    validate_topic_curriculum,
)
from tests.python_judge import judge_namespace

CURRICULUM = load_problem_curriculum()
TOPICS = load_topic_curriculum()
BASICS = load_basics_curriculum()


def _linked_values(head: Any) -> list[Any]:
    values: list[Any] = []
    seen: set[int] = set()
    while head is not None and id(head) not in seen:
        seen.add(id(head))
        values.append(head.val)
        head = head.next
    return values


def _tree_level(root: Any) -> list[Any]:
    if root is None:
        return []
    result: list[Any] = []
    queue = deque([root])
    while queue:
        node = queue.popleft()
        if node is None:
            result.append(None)
            continue
        result.append(node.val)
        queue.append(node.left)
        queue.append(node.right)
    while result and result[-1] is None:
        result.pop()
    return result


def _random_list_pairs(head: Any) -> list[list[Any]]:
    nodes: list[Any] = []
    node = head
    while node is not None:
        nodes.append(node)
        node = node.next
    positions = {id(node): index for index, node in enumerate(nodes)}
    return [
        [node.val, positions[id(node.random)] if node.random is not None else None]
        for node in nodes
    ]


def _attach_structure_helpers(namespace: dict[str, Any]) -> None:
    list_node = namespace.get("ListNode")
    if isinstance(list_node, type):
        @classmethod
        def from_list(cls: type, values: list[Any]) -> Any:
            dummy = cls()
            tail = dummy
            for value in values:
                tail.next = cls(value)
                tail = tail.next
            return dummy.next

        list_node.from_list = from_list

    tree_node = namespace.get("TreeNode")
    if isinstance(tree_node, type):
        @classmethod
        def from_level(cls: type, values: list[Any]) -> Any:
            if not values or values[0] is None:
                return None
            root = cls(values[0])
            queue = deque([root])
            index = 1
            while queue and index < len(values):
                node = queue.popleft()
                if index < len(values) and values[index] is not None:
                    node.left = cls(values[index])
                    queue.append(node.left)
                index += 1
                if index < len(values) and values[index] is not None:
                    node.right = cls(values[index])
                    queue.append(node.right)
                index += 1
            return root

        tree_node.from_level = from_level

    random_node = namespace.get("Node")
    if isinstance(random_node, type):
        @classmethod
        def from_random(cls: type, pairs: list[list[Any]]) -> Any:
            if not pairs:
                return None
            nodes = [cls(value) for value, _ in pairs]
            for index, (_, random_index) in enumerate(pairs):
                if index + 1 < len(nodes):
                    nodes[index].next = nodes[index + 1]
                if random_index is not None:
                    nodes[index].random = nodes[int(random_index)]
            return nodes[0]

        random_node.from_random = from_random


def _test_namespace(problem_id: int, code: str) -> dict[str, Any]:
    namespace: dict[str, Any] = {
        **judge_namespace(), "__name__": f"python_hot100_{problem_id}"
    }
    exec(  # noqa: S102 - trusted curriculum source under test
        compile(code, f"<python-hot100-{problem_id}>", "exec"), namespace
    )
    _attach_structure_helpers(namespace)

    def make_cycle(values: list[Any], position: int) -> Any:
        head = namespace["ListNode"].from_list(values)
        nodes = []
        node = head
        while node is not None:
            nodes.append(node)
            node = node.next
        if nodes:
            nodes[-1].next = nodes[position]
        return head

    def make_cycle_case(values: list[Any], position: int) -> tuple[Any, Any]:
        head = make_cycle(values, position)
        entry = head
        for _ in range(position):
            entry = entry.next
        return head, entry

    def make_intersection(
        left_values: list[Any],
        right_values: list[Any],
        left_skip: int,
        right_skip: int,
        shared_values: list[Any],
    ) -> tuple[Any, Any, Any]:
        node_type = namespace["ListNode"]
        shared = node_type.from_list(shared_values)
        left = node_type.from_list(left_values[:left_skip])
        right = node_type.from_list(right_values[:right_skip])
        if left is None:
            left = shared
        else:
            tail = left
            while tail.next is not None:
                tail = tail.next
            tail.next = shared
        if right is None:
            right = shared
        else:
            tail = right
            while tail.next is not None:
                tail = tail.next
            tail.next = shared
        return left, right, shared

    namespace.update(
        {
            "make_cycle": make_cycle,
            "make_cycle_case": make_cycle_case,
            "make_intersection": make_intersection,
        }
    )
    return namespace


def _evaluate(expression: str, namespace: dict[str, Any]) -> Any:
    # Lambdas created by a test binding resolve globals, not the eval locals.
    # Use the problem namespace as both scopes so deep-tree test expressions can
    # construct TreeNode instances without leaking test-only names into Problem code.
    namespace.setdefault("__builtins__", __builtins__)
    return eval(expression, namespace, namespace)


def _compare(actual: Any, expected: Any, mode: str) -> bool:
    if mode == "linked_values":
        return _linked_values(actual) == expected
    if mode == "tree_level":
        return _tree_level(actual) == expected
    if mode == "random_list":
        return _random_list_pairs(actual) == expected
    if mode == "same_node":
        return actual is expected
    if mode == "none":
        return actual is None
    return actual == expected


def _run_test(problem_id: int, test: dict[str, Any]) -> None:
    namespace = _test_namespace(problem_id, CURRICULUM[problem_id]["code"])
    for name, expression in test.get("bindings", {}).items():
        namespace[name] = _evaluate(expression, namespace)

    if test["kind"] == "design":
        operations = test["operations"]
        constructor, constructor_args = operations[0]
        instance = namespace[constructor](*constructor_args)
        actual: list[Any] = [None]
        for method_name, args in operations[1:]:
            actual.append(getattr(instance, method_name)(*args))
        assert actual == test["expected"]
        return

    callable_object = _evaluate(test["call"], namespace)
    args = _evaluate(f"[{test['args']}]", namespace)
    result = callable_object(*args)
    observe = test.get("observe", "result")
    activation = dict(namespace)
    activation.update({"result": result})
    observed = result if observe == "returned" else _evaluate(observe, activation)
    expected = _evaluate(test["expected"], namespace)
    assert _compare(observed, expected, test.get("compare", "equal"))


def _solution(problem_id: int) -> Any:
    return _test_namespace(problem_id, CURRICULUM[problem_id]["code"])["Solution"]()


def _contract_text(problem_id: int) -> str:
    item = CURRICULUM[problem_id]
    return re.sub(
        r"[\s·]+",
        "",
        " ".join(
            str(item[field])
            for field in ("method", "time", "space", "complexity_reason")
        ),
    ).casefold()


def _assert_contract(problem_id: int, *fragments: str) -> None:
    text = _contract_text(problem_id)
    missing = [
        fragment
        for fragment in fragments
        if re.sub(r"[\s·]+", "", fragment).casefold() not in text
    ]
    assert not missing, f"problem {problem_id} contract is missing {missing}: {text}"


def _imports(tree: ast.AST, module: str) -> bool:
    return any(
        isinstance(node, ast.Import)
        and any(alias.name.split(".")[0] == module for alias in node.names)
        or isinstance(node, ast.ImportFrom) and node.module == module
        for node in ast.walk(tree)
    )


def _has_self_recursion(tree: ast.AST) -> bool:
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
            if isinstance(call.func, ast.Name) and call.func.id == function.name:
                return True
            if (
                isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "self"
                and call.func.attr == function.name
            ):
                return True
    return False


def _nested_loop_count(tree: ast.AST) -> int:
    loop_types = (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp, ast.DictComp)
    count = 0
    for outer in (node for node in ast.walk(tree) if isinstance(node, loop_types)):
        for inner in (node for node in ast.walk(outer) if isinstance(node, loop_types)):
            if inner is not outer:
                count += 1
    return count


class _RejectSliceList(list):
    def __getitem__(self, index):
        if isinstance(index, slice):
            raise TypeError("this constant-space solution must not copy a list slice")
        return super().__getitem__(index)


def test_problem_curriculum_schema_and_catalog_coverage() -> None:
    errors = validate_problem_curriculum(CURRICULUM, list(PROBLEMS))
    assert errors == []
    assert set(CURRICULUM) == {int(problem["id"]) for problem in PROBLEMS}


def test_all_python_topics_and_basics_templates_compile() -> None:
    categories = list(dict.fromkeys(str(problem["category"]) for problem in PROBLEMS))
    assert len(categories) == 17
    assert validate_topic_curriculum(TOPICS, categories, CURRICULUM) == []
    assert set(BASICS) == {
        "01-Java刷题速查.md",
        "02-Java数组.md",
        "03-Java字符串.md",
        "04-Java集合.md",
        "05-排序算法.md",
    }
    for name, item in BASICS.items():
        assert item["title"] and item["summary"] and item["template_name"]
        assert len(item["concepts"]) >= 3
        assert len(item["api_hints"]) >= 2
        assert len(item["pitfalls"]) >= 2
        compile(item["template"], f"<python-basic-{name}>", "exec")


@pytest.mark.parametrize("problem_id", sorted(CURRICULUM))
def test_every_python_solution_compiles_and_passes_reviewed_cases(problem_id: int) -> None:
    item = CURRICULUM[problem_id]
    ast.parse(item["code"], filename=f"<python-hot100-{problem_id}-ast>")
    for test in item["tests"]:
        _run_test(problem_id, test)


@pytest.mark.parametrize("problem_id", sorted(CURRICULUM))
def test_python_code_has_no_visible_java_api_patterns(problem_id: int) -> None:
    code = CURRICULUM[problem_id]["code"]
    forbidden = (
        "public class",
        "public int",
        "new ArrayList",
        "new HashMap",
        "HashMap<",
        "PriorityQueue<",
        "Arrays.",
        "Integer.MAX_VALUE",
        "Math.",
        ".length",
    )
    assert not [pattern for pattern in forbidden if pattern in code]


def test_linked_list_merge_contracts_preserve_nodes_and_reported_costs() -> None:
    merge_tree = ast.parse(CURRICULUM[23]["code"])
    merge_method = str(CURRICULUM[23]["method"])
    assert "归并" in merge_method and ("两两" in merge_method or "分治" in merge_method)
    assert not _imports(merge_tree, "heapq")
    _assert_contract(23, "o(nlogk)", "o(k)")

    rng = random.Random(230148)
    for _ in range(30):
        groups = [
            sorted(rng.randint(-8, 8) for _ in range(rng.randint(0, 12)))
            for _ in range(rng.randint(0, 9))
        ]
        namespace = _test_namespace(23, CURRICULUM[23]["code"])
        node_type = namespace["ListNode"]
        lists = [node_type.from_list(group) if group else None for group in groups]
        source_nodes = []
        for head in lists:
            while head is not None:
                source_nodes.append(head)
                head = head.next
        result = namespace["Solution"]().mergeKLists(lists)
        assert _linked_values(result) == sorted(itertools.chain.from_iterable(groups))
        output_nodes = []
        while result is not None:
            output_nodes.append(result)
            result = result.next
        assert {id(node) for node in output_nodes} == {id(node) for node in source_nodes}

    merge_sort_tree = ast.parse(CURRICULUM[148]["code"])
    assert "归并" in str(CURRICULUM[148]["method"])
    assert _has_self_recursion(merge_sort_tree)
    _assert_contract(148, "o(nlogn)", "递归", "o(logn)")

    values = [4, 2, 1, 3, 2, -1, 0]
    namespace = _test_namespace(148, CURRICULUM[148]["code"])
    head = namespace["ListNode"].from_list(values)
    source_nodes = []
    node = head
    while node is not None:
        source_nodes.append(node)
        node = node.next
    sorted_head = namespace["Solution"]().sortList(head)
    assert _linked_values(sorted_head) == sorted(values)
    output_nodes = []
    node = sorted_head
    while node is not None:
        output_nodes.append(node)
        node = node.next
    assert {id(node) for node in output_nodes} == {id(node) for node in source_nodes}


def test_selection_and_lis_metadata_match_the_implemented_complexity() -> None:
    quickselect_tree = ast.parse(CURRICULUM[215]["code"])
    assert _imports(quickselect_tree, "random")
    assert not _imports(quickselect_tree, "heapq")
    assert "快速选择" in str(CURRICULUM[215]["method"])
    _assert_contract(215, "双指针", "平均o(n)", "最坏o(n²)", "o(1)")

    rng = random.Random(215)
    quickselect = _solution(215)
    for _ in range(80):
        values = [rng.randint(-8, 8) for _ in range(rng.randint(1, 30))]
        k = rng.randint(1, len(values))
        assert quickselect.findKthLargest(values[:], k) == sorted(values, reverse=True)[k - 1]

    lis = CURRICULUM[300]
    lis_tree = ast.parse(lis["code"])
    lis_time = re.sub(r"\s+", "", str(lis["time"])).casefold()
    if "o(n²)" in lis_time:
        assert "dp" in str(lis["method"]).casefold()
        assert _nested_loop_count(lis_tree) > 0
    else:
        assert "o(nlogn)" in lis_time
        assert _imports(lis_tree, "bisect")
    _assert_contract(300, "o(n)")
    lis_cases = (
        ([10, 9, 2, 5, 3, 7, 101, 18], 4),
        ([7, 7, 7], 1),
        ([-5, -2, -1], 3),
        ([3, -1, 4, 0, 2], 3),
        ([0], 1),
    )
    for values, expected in lis_cases:
        original = values[:]
        assert _solution(300).lengthOfLIS(values) == expected
        assert values == original


def test_frequency_and_sort_main_solutions_accept_equivalent_names() -> None:
    anagram = CURRICULUM[49]
    anagram_tree = ast.parse(anagram["code"])
    assert "排序" in str(anagram["method"])
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "sorted"
        for node in ast.walk(anagram_tree)
    )
    _assert_contract(49, "o(nklogk)", "o(nk)")

    rng = random.Random(49347)
    group_anagrams = _solution(49).groupAnagrams
    for _ in range(80):
        words = [
            "".join(rng.choice("abcd") for _ in range(rng.randint(0, 8)))
            for _ in range(rng.randint(1, 24))
        ]
        expected: dict[str, list[str]] = {}
        for word in words:
            expected.setdefault("".join(sorted(word)), []).append(word)
        actual = group_anagrams(words)
        assert sorted(map(sorted, actual)) == sorted(map(sorted, expected.values()))

    window = CURRICULUM[3]
    window_tree = ast.parse(window["code"])
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "max"
        for node in ast.walk(window_tree)
    )
    _assert_contract(3, "最近位置", "o(n)", "o(min(n,σ))")

    longest_substring = _solution(3).lengthOfLongestSubstring
    for length in range(9):
        for chars in itertools.product("ab", repeat=length):
            text = "".join(chars)
            expected = 0
            for left in range(length):
                seen: set[str] = set()
                for right in range(left, length):
                    if text[right] in seen:
                        break
                    seen.add(text[right])
                    expected = max(expected, right - left + 1)
            assert longest_substring(text) == expected


def test_string_dp_and_decode_contracts_are_executable_and_bounded() -> None:
    _assert_contract(139, "startswith", "w·lmax", "o(n+w)")
    word_break = _solution(139).wordBreak
    repeated = "a" * 500
    assert word_break(repeated, ["a", "aa"]) is True
    assert word_break("a" * 251 + "b", ["aa", "aaa"]) is False

    decode = CURRICULUM[394]
    decode_tree = ast.parse(decode["code"])
    assert "双栈" in str(decode["method"])
    assert not _has_self_recursion(decode_tree)
    decode_time = re.sub(r"[\s·]", "", str(decode["time"])).casefold()
    decode_space = re.sub(r"[\s·]", "", str(decode["space"])).casefold()
    assert "o(nl)" in decode_time
    assert "o(nl)" in decode_space
    for name in (
        "1500 层 count=1 不复制列表",
        "1500 层分支序列节点不二次扫描",
        "外层重复与内层单孩子长链",
    ):
        test = next(case for case in decode["tests"] if case["name"] == name)
        _run_test(394, test)

    top_k_tree = ast.parse(CURRICULUM[347]["code"])
    assert _imports(top_k_tree, "heapq")
    assert "小顶堆" in str(CURRICULUM[347]["method"])
    _assert_contract(347, "o(nlogk)", "o(n)")
    rng = random.Random(347)
    top_k_frequent = _solution(347).topKFrequent
    for _ in range(100):
        values = [rng.randint(-3, 4) for _ in range(rng.randint(1, 30))]
        counts = {value: values.count(value) for value in set(values)}
        k = rng.randint(1, len(counts))
        selected = top_k_frequent(values, k)
        omitted = counts.keys() - set(selected)
        assert len(selected) == len(set(selected)) == k
        assert not omitted or min(counts[value] for value in selected) >= max(
            counts[value] for value in omitted
        )


def test_python_complexity_notes_cover_real_string_sort_and_container_costs() -> None:
    space_notes = {
        15: "Timsort",
        39: "Timsort",
        56: "Timsort",
    }
    for problem_id, fragment in space_notes.items():
        item = CURRICULUM[problem_id]
        assert fragment in " ".join((item["space"], item["complexity_reason"]))

    assert "deque" in CURRICULUM[239]["method"] or "队列" in CURRICULUM[239]["method"]


def test_in_place_array_contracts_reject_copies_and_keep_python_edges() -> None:
    for problem_id in (53, 152):
        _assert_contract(problem_id, "o(n)", "o(1)")

    max_subarray = _solution(53).maxSubArray
    assert max_subarray(_RejectSliceList([-2, 1, -3, 4, -1, 2, 1, -5, 4])) == 6
    assert max_subarray(_RejectSliceList([-5, -2, -9])) == -2
    assert max_subarray(_RejectSliceList([0, 0, -1])) == 0

    max_product = _solution(152).maxProduct
    assert max_product(_RejectSliceList([2, 3, -2, 4])) == 6
    assert max_product(_RejectSliceList([-2, 3, -4])) == 24
    assert max_product(_RejectSliceList([0, -2, 0])) == 0
    assert max_product(_RejectSliceList([-2, 0, -1])) == 0

    _assert_contract(283, "o(n)", "o(1)")
    values = _RejectSliceList([0, 1, 0, 3, 12])
    assert _solution(283).moveZeroes(values) is None
    assert values == [1, 3, 12, 0, 0]
    values = _RejectSliceList([-1, 0, -2, 0])
    _solution(283).moveZeroes(values)
    assert values == [-1, -2, 0, 0]

    _assert_contract(75, "o(n)", "o(1)")
    for values, expected in (
        ([2, 0, 2, 1, 1, 0], [0, 0, 1, 1, 2, 2]),
        ([0, 1, 0], [0, 0, 1]),
        ([2, 2, 0], [0, 2, 2]),
    ):
        guarded = _RejectSliceList(values)
        assert _solution(75).sortColors(guarded) is None
        assert guarded == expected

    _assert_contract(31, "o(n)", "o(1)")
    for values, expected in (
        ([1, 2, 3], [1, 3, 2]),
        ([1, 3, 5, 4, 2], [1, 4, 2, 3, 5]),
        ([1, 1, 5], [1, 5, 1]),
        ([3, 2, 1], [1, 2, 3]),
        ([-3, -1, -2], [-2, -3, -1]),
    ):
        guarded = _RejectSliceList(values)
        assert _solution(31).nextPermutation(guarded) is None
        assert guarded == expected


def test_stack_and_partition_contracts_cover_the_reviewed_counterexamples() -> None:
    valid_parentheses = {
        "": True,
        "()": True,
        "{[]}": True,
        "(())": True,
        "(": False,
        "(]": False,
        "([)]": False,
        "[)": False,
        "]": False,
    }
    parentheses = _solution(20)
    for text, expected in valid_parentheses.items():
        assert parentheses.isValid(text) is expected

    _assert_contract(32, "o(n)", "o(n)")
    longest_valid = _solution(32).longestValidParentheses
    for length in range(10):
        for chars in itertools.product("()", repeat=length):
            text = "".join(chars)
            expected = 0
            for left in range(length):
                balance = 0
                for right in range(left, length):
                    balance += 1 if text[right] == "(" else -1
                    if balance < 0:
                        break
                    if balance == 0:
                        expected = max(expected, right - left + 1)
            assert longest_valid(text) == expected
    assert longest_valid("(()") == 2

    heights = [2, 2, 2]
    snapshot = heights[:]
    assert _solution(84).largestRectangleArea(heights) == 6
    assert heights == snapshot
    assert _solution(84).largestRectangleArea([0, 2, 2, 0]) == 4
    _assert_contract(84, "单调", "o(n)", "o(n)")

    _assert_contract(416, "o(n·target)", "o(target)")
    assert _solution(416).canPartition([1, 5, 11, 5]) is True
    assert _solution(416).canPartition([13, 1, 1, 1, 6, 2]) is False
    assert _solution(416).canPartition([1, 2, 5]) is False

    _assert_contract(322, "o(amount·coins)", "o(amount)")
    assert _solution(322).coinChange([2], 0) == 0
    assert _solution(322).coinChange([2], 1) == -1
    assert _solution(322).coinChange([1, 2, 5], 11) == 3

    _assert_contract(739, "非递增", "o(n)")
    assert "严格递减" not in str(CURRICULUM[739]["method"])
    daily_temperatures = _solution(739).dailyTemperatures
    assert daily_temperatures([70, 70, 71]) == [2, 1, 0]
    rng = random.Random(739)
    for _ in range(200):
        temperatures = [rng.randint(50, 80) for _ in range(rng.randint(1, 24))]
        expected = []
        for index, temperature in enumerate(temperatures):
            future = next(
                (
                    later - index
                    for later in range(index + 1, len(temperatures))
                    if temperatures[later] > temperature
                ),
                0,
            )
            expected.append(future)
        assert daily_temperatures(temperatures) == expected


def test_median_finder_and_heap_scope_match_python_runtime() -> None:
    _assert_contract(295, "addnumo(logn)", "findmediano(1)", "o(n)")
    narrative = "\n".join(
        (
            str(CURRICULUM[295]["teaching_markdown"]),
            str(CURRICULUM[295]["explanation_markdown"]),
        )
    )
    assert "Python 3.12" in narrative

    rng = random.Random(295)
    for _ in range(50):
        values = [rng.randint(-10, 10) for _ in range(rng.randint(1, 30))]
        namespace = _test_namespace(295, CURRICULUM[295]["code"])
        median_finder = namespace["MedianFinder"]()
        seeded = []
        for value in values:
            seeded.append(value)
            median_finder.addNum(value)
            ordered = sorted(seeded)
            middle = len(ordered) // 2
            expected = (
                float(ordered[middle])
                if len(ordered) % 2
                else (ordered[middle - 1] + ordered[middle]) / 2.0
            )
            assert median_finder.findMedian() == expected


def test_pointer_tree_and_trie_contracts_use_only_reported_auxiliary_state() -> None:
    _assert_contract(234, "o(n)", "o(1)")
    namespace = _test_namespace(234, CURRICULUM[234]["code"])
    for values, expected in (([1, 2, 2, 1], True), ([1, 2, 3, 2], False), ([1], True)):
        head = namespace["ListNode"].from_list(values)
        original_nodes = []
        node = head
        while node is not None:
            original_nodes.append(node)
            node = node.next
        assert namespace["Solution"]().isPalindrome(head) is expected
        assert _linked_values(head) == values
        node, restored_nodes = head, []
        while node is not None:
            restored_nodes.append(node)
            node = node.next
        assert {id(node) for node in restored_nodes} == {id(node) for node in original_nodes}

    _assert_contract(114, "o(n)", "o(1)")
    namespace = _test_namespace(114, CURRICULUM[114]["code"])
    root = namespace["TreeNode"].from_level([1, 2, 5, 3, 4, None, 6])
    source_nodes = []
    stack = [root]
    while stack:
        node = stack.pop()
        source_nodes.append(node)
        if node.right is not None:
            stack.append(node.right)
        if node.left is not None:
            stack.append(node.left)
    assert namespace["Solution"]().flatten(root) is None
    flattened_values = []
    flattened_nodes = []
    node = root
    while node is not None:
        assert node.left is None
        flattened_values.append(node.val)
        flattened_nodes.append(node)
        node = node.right
    assert flattened_values == [1, 2, 3, 4, 5, 6]
    assert {id(node) for node in flattened_nodes} == {id(node) for node in source_nodes}

    _assert_contract(41, "o(n)", "o(1)")
    for values, expected in (
        ([3, 4, -1, 1], 2),
        ([1, 1, 2], 3),
        ([1, 2, 0], 3),
        ([-2, -1], 1),
    ):
        assert _solution(41).firstMissingPositive(values[:]) == expected

    _assert_contract(208, "o(l)", "o(总字符数)")
    trie = _test_namespace(208, CURRICULUM[208]["code"])["Trie"]()
    trie.insert("apple")
    assert trie.search("apple") and not trie.search("app") and trie.startsWith("app")
    trie.insert("app")
    assert trie.search("app") and not trie.search("ap")

    _assert_contract(437, "o(n)", "o(h)")
    for name in ("多条向下路径", "目标不存在的路径", "1500 节点右链不递归"):
        case = next(test for test in CURRICULUM[437]["tests"] if test["name"] == name)
        _run_test(437, case)


def test_c_review_examples_keep_corrected_states() -> None:
    def narrative(problem_id: int) -> str:
        item = CURRICULUM[problem_id]
        return "\n".join((item["teaching_markdown"], item["explanation_markdown"]))

    lcs = narrative(1143)
    assert all(token in lcs for token in ("dp[3][2]", "dp[2][1] = 1", "更短前缀"))
    assert "`dp[3][3]` 对应 `\"abc\"` 与 `\"ace\"`" not in lcs

    histogram = narrative(84)
    assert all(token in histogram for token in ("[2, 2]", "较早等高柱", "真实 0 柱"))
    assert "所有真实柱子都会被弹出" not in histogram

    partition = narrative(416)
    assert all(
        token in partition
        for token in (
            "只遍历",
            "只能产生 11",
            "12、16、17 超过容量上限",
            "代码没有提前返回",
            "range 为空",
        )
    )
    assert "新增 11、12、16、17" not in partition

    assert '[\")\"]' in narrative(20)
    assert "max(11, 7 + 3) = max(11, 10) = 11" in narrative(198)
    assert all(token in narrative(31) for token in ("4 >= 2", "5 >= 4", "3 < 5"))

    longest_valid = narrative(32)
    assert all(token in longest_valid for token in ("(()", "2 - 0 = 2", "未匹配左括号"))
    assert "新的栈顶就是上一个断裂点" not in longest_valid

    colors = narrative(75)
    assert "left < index" in colors and "确认的 1 区" in colors
    coin_change = narrative(322)
    assert "inf + 1" in coin_change and "仍然是 `inf`" in coin_change
    assert "外层仍会遍历" in coin_change and "range(coin, 1)" in coin_change
    assert "Python 3.12" in narrative(295)
    temperature_hints = " ".join(
        str(hint["syntax"]) for hint in CURRICULUM[739]["api_hints"]
    )
    assert "for i, temperature in enumerate(temperatures)" in temperature_hints
    assert "stack.append(i)" in temperature_hints


def test_deep_input_main_solutions_do_not_use_python_recursion() -> None:
    expected_cases = {
        98: "1500 节点递增右链",
        104: "1500 节点右链",
        105: "1500 节点右链不递归",
        124: "1500 节点右链不递归",
        200: "40×40 全陆岛不触发递归限制",
        236: "1500 节点右链不递归",
        437: "1500 节点右链不递归",
        543: "1500 节点右链不递归",
    }
    for problem_id, case_name in expected_cases.items():
        item = CURRICULUM[problem_id]
        assert any(test["name"] == case_name for test in item["tests"])
        tree = ast.parse(item["code"])
        function_names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        recursive_calls = []
        for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
            for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
                if isinstance(call.func, ast.Name) and call.func.id == function.name:
                    recursive_calls.append(function.name)
                if (
                    isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "self"
                    and call.func.attr in function_names
                ):
                    recursive_calls.append(f"self.{call.func.attr}")
        assert recursive_calls == []
