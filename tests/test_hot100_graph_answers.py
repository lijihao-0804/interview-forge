import pytest

from scripts.check.hot100_graph_answers import compare_output


@pytest.mark.parametrize(("pid", "end", "expected"), [
    (20, "栈里还剩 ) ] } → false", True),
    (142, "两指针在 3 相会 → 这就是环的入口", 2),
    (394, '完成！解码结果 = "[a[c[c"', "accaccacc"),
])
def test_a_plausible_but_wrong_graphical_result_is_detected(pid, end, expected):
    actual, reference = compare_output(pid, 0, "默认", {"end": end, "state": ""})
    assert reference == expected
    assert actual != reference


@pytest.mark.parametrize(("pid", "end"), [
    (64, "完成！右下角 = 最小路径和 [object Object]"),
    (160, "pA=undefined 与 pB=undefined 相同 → 相交节点是 undefined"),
    (236, "完成！LCA(5, 4) = null"),
    (287, "重复数字 = nums[2] = 4"),
])
def test_placeholder_or_unresolved_return_cannot_pass(pid, end):
    with pytest.raises(ValueError):
        compare_output(pid, 0, "默认", {"end": end, "state": ""})


def test_pair_swap_uses_rendered_next_fields_even_when_the_caption_claims_success():
    result = {"end": "完成，结果 2 → 1 → 4 → 3 → 5。",
              "state": "dummy.next → 2\n1.next → 3\n2.next → 4\n3.next → 5\n4.next → 3\n5.next → null"}
    assert compare_output(24, 0, "默认", result) == ([2,4,3,5], [2,1,4,3,5])


def test_random_cases_recompute_the_oracle_from_the_visible_input():
    result = {"end": "the chart has no numeric result caption", "state": "",
              "inputBars": [0,4,0,3,3], "bars": [3,4,3,0,0]}
    assert compare_output(283, 0, "随机", result) == ([3,4,3,0,0], [4,3,3,0,0])
