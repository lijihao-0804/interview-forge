"""Independent differential checks against the actual published Python code."""
from __future__ import annotations

import ast
import collections
import functools
import itertools
import math
import random
import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from interview_forge.core.problem_catalog import PROBLEMS
from tests.python_judge import judge_namespace

ROOT = Path(__file__).resolve().parents[1]


class ListNode:
    def __init__(self, val=0, next=None):
        self.val, self.next = val, next


class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val, self.left, self.right = val, left, right


@functools.cache
def implementation(problem_id):
    paths = list((ROOT / "books/hot100/03-题解").rglob(f"{problem_id:04d}-*.html"))
    assert len(paths) == 1
    soup = BeautifulSoup(paths[0].read_text(encoding="utf-8"), "html.parser")
    panel = soup.select_one('.language-panel[data-lang="python"]')
    assert panel is not None, f"No complete Python teaching panel published for {problem_id}"
    # Markdown's Pygments wrapper can lack a language attribute when a legacy
    # source has an unlabelled fence. The enclosing teaching panel is the
    # authoritative language scope used by the browser.
    blocks = [node.get_text() for node in panel.select('.codehilite pre')]
    candidates = [code for code in blocks if any(
        name in code for name in ("class Solution", "class LRUCache", "class Trie", "class MedianFinder", "class MinStack")
    )]
    assert candidates, f"No executable Python implementation published for {problem_id}"
    code = candidates[0]
    ast.parse(code)
    # The judge provides node types; every other dependency must be imported by
    # the published implementation itself. Broad pre-imports hid missing imports.
    namespace = judge_namespace()
    exec(compile(code, str(paths[0]), "exec"), namespace)  # noqa: S102 - trusted repository artifact under test
    return namespace


def solve(problem_id, method, *args):
    return getattr(implementation(problem_id)["Solution"](), method)(*args)


@pytest.mark.parametrize("problem_id", [int(problem["id"]) for problem in PROBLEMS])
def test_every_published_python_implementation_is_complete_and_loadable(problem_id):
    assert implementation(problem_id)
    path = next((ROOT / "books/hot100/03-题解").rglob(f"{problem_id:04d}-*.html"))
    article = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser").select_one("article")
    assert article is not None
    # Apply the renderer's Python visibility scopes to the actual publication.
    for node in article.select('[data-hide-in-language="python"]'):
        node.decompose()
    for node in article.select("[data-lang]"):
        if node.attrs is not None and node.get("data-lang") in {"java", "cpp", "go", "c"}:
            node.decompose()
    visible = article.get_text(" ", strip=True)
    assert not re.search(
        r"\b(?:HashMap|ArrayList|PriorityQueue|Collections)\b|charAt\(|java\.util|public\s+(?:static\s+)?class",
        visible,
    ), f"Legacy API leaked into Python teaching for {problem_id}"


def chain(values):
    head = None
    for value in reversed(values):
        head = ListNode(value, head)
    return head


def values(head):
    result, seen = [], set()
    while head is not None:
        assert id(head) not in seen, "Published implementation introduced a cycle"
        seen.add(id(head))
        result.append(head.val)
        head = head.next
    return result


@pytest.mark.parametrize("problem_id", [41, 128, 238, 239, 283, 300])
def test_array_solutions_against_small_exhaustive_oracles(problem_id):
    rng = random.Random(20261112 + problem_id)
    for _ in range(60):
        nums = [rng.randint(-4, 6) for _ in range(rng.randint(1, 9))]
        if problem_id == 41:
            expected = next(x for x in range(1, len(nums) + 2) if x not in nums)
            assert solve(41, "firstMissingPositive", nums[:]) == expected
        elif problem_id == 128:
            distinct = set(nums)
            expected = max((next((d for d in range(1, len(nums) + 1) if x + d not in distinct), len(nums))
                            for x in distinct), default=0)
            assert solve(128, "longestConsecutive", nums[:]) == expected
        elif problem_id == 238:
            expected = [math.prod(nums[:i] + nums[i + 1:]) for i in range(len(nums))]
            assert solve(238, "productExceptSelf", nums[:]) == expected
        elif problem_id == 239:
            k = rng.randint(1, len(nums))
            expected = [max(nums[i:i + k]) for i in range(len(nums) - k + 1)]
            assert solve(239, "maxSlidingWindow", nums[:], k) == expected
        elif problem_id == 283:
            data = nums[:]
            solve(283, "moveZeroes", data)
            assert data == [x for x in nums if x] + [0] * nums.count(0)
        elif problem_id == 300:
            expected = max(len(candidate) for size in range(len(nums) + 1)
                           for candidate in itertools.combinations(nums, size)
                           if all(a < b for a, b in itertools.pairwise(candidate)))
            assert solve(300, "lengthOfLIS", nums[:]) == expected


def test_order_statistics_and_median_with_duplicates_and_empty_side():
    rng = random.Random(442)
    for _ in range(80):
        nums = [rng.randint(-8, 8) for _ in range(rng.randint(1, 18))]
        k = rng.randint(1, len(nums))
        assert solve(215, "findKthLargest", nums[:], k) == sorted(nums, reverse=True)[k - 1]
        split = rng.randint(0, len(nums))
        a, b = sorted(nums[:split]), sorted(nums[split:])
        ordered = sorted(nums)
        expected = (ordered[(len(nums) - 1) // 2] + ordered[len(nums) // 2]) / 2
        assert solve(4, "findMedianSortedArrays", a, b) == expected


def test_group_signatures_and_frequency_buckets_preserve_counts():
    rng = random.Random(49347)
    for _ in range(80):
        words = ["".join(rng.choice("abcd") for _ in range(rng.randint(0, 7)))
                 for _ in range(rng.randint(1, 20))]
        groups = collections.defaultdict(list)
        for word in words:
            groups[tuple(sorted(word))].append(word)
        expected = sorted(sorted(group) for group in groups.values())
        actual = solve(49, "groupAnagrams", words)
        assert sorted(sorted(group) for group in actual) == expected

        nums = [rng.randint(-3, 3) for _ in range(rng.randint(1, 30))]
        counts = collections.Counter(nums)
        k = rng.randint(1, len(counts))
        selected = solve(347, "topKFrequent", nums, k)
        assert len(selected) == len(set(selected)) == k and set(selected) <= counts.keys()
        omitted = counts.keys() - set(selected)
        if omitted:
            assert min(counts[value] for value in selected) >= max(counts[value] for value in omitted)


def test_linked_list_implementations_on_duplicates_and_short_inputs():
    rng = random.Random(8234)
    for _ in range(60):
        nums = [rng.randint(-3, 3) for _ in range(rng.randint(0, 16))]
        assert values(solve(148, "sortList", chain(nums))) == sorted(nums)
        assert solve(234, "isPalindrome", chain(nums)) == (nums == nums[::-1])
        groups = [sorted(nums[::3]), sorted(nums[1::3]), sorted(nums[2::3])]
        assert values(solve(23, "mergeKLists", [chain(group) for group in groups])) == sorted(nums)


def test_published_stateful_classes_preserve_eviction_prefix_and_heap_invariants():
    cache = implementation(146)["LRUCache"](2)
    cache.put(1, 1)
    cache.put(2, 2)
    assert cache.get(1) == 1
    cache.put(3, 3)
    assert cache.get(2) == -1
    cache.put(1, 9)
    cache.put(4, 4)
    assert cache.get(3) == -1 and cache.get(1) == 9 and cache.get(4) == 4
    trie = implementation(208)["Trie"]()
    trie.insert("apple")
    assert trie.search("apple") and not trie.search("app") and trie.startsWith("app")
    trie.insert("app")
    assert trie.search("app")
    median = implementation(295)["MedianFinder"]()
    stream = [-4, 8, 8, -6, 0, 11, 2]
    for i, number in enumerate(stream, 1):
        median.addNum(number)
        ordered = sorted(stream[:i])
        assert median.findMedian() == (ordered[(i - 1) // 2] + ordered[i // 2]) / 2


def test_partition_and_valid_parentheses_against_exhaustive_oracles():
    rng = random.Random(41632)
    for _ in range(80):
        nums = [rng.randint(1, 12) for _ in range(rng.randint(1, 9))]
        total = sum(nums)
        expected = total % 2 == 0 and any(
            sum(part) == total // 2 for size in range(len(nums) + 1)
            for part in itertools.combinations(nums, size)
        )
        assert solve(416, "canPartition", nums) == expected
        text = "".join(rng.choice("()") for _ in range(rng.randint(0, 12)))
        best = 0
        for start in range(len(text)):
            balance = 0
            for end in range(start, len(text)):
                balance += 1 if text[end] == "(" else -1
                if balance < 0:
                    break
                if balance == 0:
                    best = max(best, end - start + 1)
        assert solve(32, "longestValidParentheses", text) == best


def test_tree_path_backtracking_and_in_place_flatten():
    def preorder(node):
        return [] if node is None else [node.val] + preorder(node.left) + preorder(node.right)

    def paths_from(node, target):
        if node is None:
            return 0
        return (node.val == target) + paths_from(node.left, target - node.val) + paths_from(node.right, target - node.val)

    def total_paths(node, target):
        return 0 if node is None else paths_from(node, target) + total_paths(node.left, target) + total_paths(node.right, target)

    rng = random.Random(437114)
    for _ in range(50):
        nodes = [TreeNode(rng.randint(-2, 2)) for _ in range(rng.randint(1, 14))]
        for index, node in enumerate(nodes):
            node.left = nodes[2 * index + 1] if 2 * index + 1 < len(nodes) else None
            node.right = nodes[2 * index + 2] if 2 * index + 2 < len(nodes) else None
        target = rng.randint(-4, 4)
        assert solve(437, "pathSum", nodes[0], target) == total_paths(nodes[0], target)
        expected = preorder(nodes[0])
        solve(114, "flatten", nodes[0])
        node, result, seen = nodes[0], [], set()
        while node:
            assert node.left is None and id(node) not in seen
            seen.add(id(node))
            result.append(node.val)
            node = node.right
        assert result == expected


def test_large_legal_inputs_do_not_exceed_standard_python_recursion_depth():
    assert solve(200, "numIslands", [["1"] * 40 for _ in range(40)]) == 1
    root = TreeNode(0)
    current = root
    for value in range(1, 1500):
        current.right = TreeNode(value)
        current = current.right
    assert solve(104, "maxDepth", root) == 1500
    assert solve(98, "isValidBST", root) is True
    assert solve(543, "diameterOfBinaryTree", root) == 1499
    assert solve(124, "maxPathSum", root) == sum(range(1500))
    ancestor = root
    for _ in range(1200):
        ancestor = ancestor.right
    assert solve(236, "lowestCommonAncestor", root, ancestor, current) is ancestor

    restored = solve(105, "buildTree", list(range(1500)), list(range(1500)))
    for value in range(1500):
        assert restored is not None and restored.val == value and restored.left is None
        restored = restored.right
    assert restored is None

    path_root = TreeNode(1)
    node = path_root
    for _ in range(999):
        node.right = TreeNode(1)
        node = node.right
    assert solve(437, "pathSum", path_root, 3) == 998

