"""Compare five revised lessons with independent small oracles or interface invariants."""
from itertools import product
from math import prod
from random import Random

from scripts.check.check_hot200_acm_examples import FENCE, ROOT, ListNode, sections


def lesson(number):
    path = ROOT / f"books/hot200-extra/solutions/{number}.md"
    namespace = {"ListNode": ListNode}
    source = FENCE.search(sections(path.read_text(encoding="utf-8-sig"))["Python"])[2]
    exec(compile(source, str(path), "exec"), namespace)
    return namespace


def test_flatten_cursor_skips_empty_rows_without_copying_the_input():
    class Rows(list):
        def __iter__(self):
            raise AssertionError("constructing the cursor should not traverse the input")

    cursor = lesson(251)["Vector2D"](Rows([[], [], [3], [], [4, 5], []]))
    for value in (3, 4, 5):
        assert cursor.hasNext() and cursor.hasNext()
        assert cursor.next() == value
    assert not cursor.hasNext()


def test_factorizations_are_complete_unique_and_sorted_internally():
    solver = lesson(254)["Solution"]()
    for n in range(2, 81):
        def enumerate_products(prefix=()):
            current = prod(prefix)
            if current == n:
                if len(prefix) >= 2:
                    yield prefix
                return
            for factor in range(prefix[-1] if prefix else 2, n // current + 1):
                if n % (current * factor) == 0:
                    yield from enumerate_products(prefix + (factor,))

        assert sorted(map(tuple, solver.getFactors(n))) == sorted(enumerate_products())


def test_rolling_fence_count_matches_exhaustive_colorings():
    solver = lesson(276)["Solution"]()
    for n, colors in product(range(1, 7), range(1, 5)):
        expected = sum(all(not (row[i] == row[i + 1] == row[i + 2]) for i in range(n - 2))
                       for row in product(range(colors), repeat=n))
        assert solver.numWays(n, colors) == expected


def test_sparse_multiplication_matches_dense_oracle_including_cancellation():
    solver = lesson(311)["Solution"]()
    rng = Random(311)
    for m, k, n in product(range(1, 5), repeat=3):
        def matrix(rows, columns):
            return [[rng.choice((0, 0, 0, -3, 1, 2)) for _ in range(columns)] for _ in range(rows)]

        a, b = matrix(m, k), matrix(k, n)
        expected = [[sum(x * y for x, y in zip(row, col)) for col in zip(*b)] for row in a]
        assert solver.multiply(a, b) == expected


def test_plus_one_handles_carry_across_the_entire_list():
    solver = lesson(369)["Solution"]()
    for digits, expected in [([9] * 1500, [1] + [0] * 1500), ([2, 0, 9, 9], [2, 1, 0, 0]), ([0], [1])]:
        head = None
        for digit in reversed(digits):
            head = ListNode(digit, head)
        head = solver.plusOne(head)
        result = []
        while head and len(result) <= len(expected):
            result.append(head.val)
            head = head.next
        assert result == expected and head is None
