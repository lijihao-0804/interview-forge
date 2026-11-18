"""Build stdin/stdout fixtures from the reviewed Hot 100 curriculum and verify reference results.

Run with python -m scripts.build.hot100_acm.
"""
import argparse
import inspect
import urllib.request
import re
from bs4 import BeautifulSoup
from interview_forge.core.problem_catalog import LEETCODE_SLUGS
import json
from pathlib import Path

from tests.test_python_hot100_curriculum import (
    CURRICULUM, _evaluate, _linked_values, _random_list_pairs, _run_test,
    _test_namespace, _tree_level,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/acm/hot100.json"
SPECIAL = {
    160: "依次输入链表 A 的独有前缀、链表 B 的独有前缀、两表的公共尾段。输出第一个公共节点的值，无交点输出 null。",
    141: "输入节点值数组和尾部连接的下标（无环为 -1）。输出是否有环。",
    142: "输入节点值数组和尾部连接的下标（无环为 -1）。输出环入口的下标，无环输出 -1。",
    236: "输入二叉树的层序数组、节点 p 的值、节点 q 的值。输出最近公共祖先的值。",
    138: "链表输入输出均为 [节点值,random指向下标] 的数组。空指针用 null。",
    108: "为统一树形，每段选择下中位数作为根。输出层序数组，省略末尾 null。",
    5: "并列时输出起点最靠左的最长回文子串。",
    114: "输出展开后的树的层序数组，省略末尾 null。",
}
UNORDERED = {1, 438, 17, 22, 46, 51, 131, 347}
NESTED_UNORDERED = {15, 39, 49, 78}


def encode(value, namespace):
    if isinstance(value, namespace["ListNode"]):
        return _linked_values(value)
    if isinstance(value, namespace["TreeNode"]):
        return _tree_level(value)
    if isinstance(value, namespace["Node"]):
        return _random_list_pairs(value)
    if isinstance(value, list):
        return [encode(x, namespace) for x in value]
    return value


def public_case(pid, case, code):
    namespace = _test_namespace(pid, code)
    for key, expr in case.get("bindings", {}).items():
        namespace[key] = _evaluate(expr, namespace)
    if case["kind"] == "design":
        args = [[op for op, _ in case["operations"]], [a for _, a in case["operations"]]]
        expected = case["expected"]
        names = ["操作名称数组", "对应的参数数组"]
    else:
        args = _evaluate("[" + case["args"] + "]", namespace)
        expected = _evaluate(case["expected"], namespace)
        names = list(inspect.signature(_evaluate(case["call"], namespace)).parameters)
        if pid in (141, 142):
            nodes, seen, node = [], {}, args[0]
            while node is not None and id(node) not in seen:
                seen[id(node)] = len(nodes)
                nodes.append(node.val)
                node = node.next
            pos = seen.get(id(node), -1)
            args = [nodes, pos]
            names = ["节点值数组", "pos"]
            if pid == 142:
                expected = pos
        elif pid == 160:
            shared = namespace["pair"][2]
            tails = _linked_values(shared)
            args = [_linked_values(head)[:len(_linked_values(head)) - len(tails)] for head in args] + [tails]
            names = ["A 前缀", "B 前缀", "公共尾段"]
            expected = shared.val if shared else None
        elif pid == 236:
            args = [_tree_level(args[0]), args[1].val, args[2].val]
            expected = expected.val
        elif pid == 234 and case.get('observe') == 'head':
            chain = _linked_values(args[0])
            expected = chain == chain[::-1]
        elif pid == 79:
            expected = expected[0]
        elif pid == 64 and case.get("observe") == "grid":
            # The curriculum checks that the argument was preserved. The public
            # result for that same input is the path sum returned by the method.
            expected = _evaluate(case["call"], namespace)(*args)
        elif pid == 138 and args[0] is None:
            args = [[]]
        if pid in (2,19,21,23,24,25,94,98,101,102,104,114,124,138,148,199,206,226,230,234,437,543):
            args = [[] if value is None else value for value in args]
        args = [encode(value, namespace) for value in args]
    if pid in NESTED_UNORDERED:
        expected = [sorted(row) for row in expected]
    if pid in UNORDERED | NESTED_UNORDERED:
        expected = sorted(expected)
    dump = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    stdin = "".join(dump(arg) + "\n" for arg in args)
    return names, {"name":case["name"], "input":stdin, "expected":dump(expected), "source":"supplemental"}


def official_examples(pid, question, arity):
    values = [json.loads(line) for line in question["exampleTestcases"].splitlines() if line.strip()]
    if pid == 160:
        arity = 5
    text = BeautifulSoup(question["content"], "html.parser").get_text(" ", strip=True)
    outputs = re.findall(r"\bOutput\s*:?\s*(.+?)(?=\s*(?:Explanation|Example \d|Constraints|Follow.up)|$)", text, re.S)
    examples = []
    for index, raw in enumerate(outputs):
        args = values[index * arity:(index + 1) * arity]
        if len(args) != arity:
            continue
        if pid == 160:
            val, left, right, a, b = args
            args, expected = [left[:a], right[:b], left[a:]], val if left[a:] else None
        elif pid == 142:
            expected = args[1]
        elif pid == 108:
            # The official output is one of multiple trees. The ACM contract uses lower midpoints.
            def tree(nums):
                if not nums:
                    return None
                mid = (len(nums)-1)//2
                return namespace["TreeNode"](nums[mid], tree(nums[:mid]), tree(nums[mid+1:]))
            namespace = _test_namespace(pid, CURRICULUM[pid]["code"])
            expected = _tree_level(tree(args[0]))
        else:
            try:
                expected, _ = json.JSONDecoder().raw_decode(raw.strip())
            except ValueError:
                continue
        if pid in NESTED_UNORDERED:
            expected = [sorted(row) for row in expected]
        if pid in UNORDERED | NESTED_UNORDERED:
            expected = sorted(expected)
        compact = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        examples.append({"name":f"力扣示例 {index + 1}", "input":"".join(compact(a) + "\n" for a in args),
                         "expected":compact(expected), "source":"statement",
                         "source_url":f"https://leetcode.cn/problems/{LEETCODE_SLUGS[pid]}/"})
    return examples

def fetch_official():
    questions = {}
    slugs = list(LEETCODE_SLUGS.items())
    for start in range(0, len(slugs), 5):
        fields = [f'q{pid}:question(titleSlug:"{slug}"){{exampleTestcases content}}'
                  for pid, slug in slugs[start:start+5]]
        body = json.dumps({"query": "query {" + " ".join(fields) + "}"}).encode()
        request = urllib.request.Request("https://leetcode.cn/graphql/", data=body,
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=20) as response:
            questions.update(json.load(response)["data"])
    return questions

def build(official=None):
    previous = {int(row["id"].split("-")[1]): [s for s in row["samples"] if s["source"] == "statement"] for row in json.loads(OUT.read_text(encoding="utf-8"))} if OUT.exists() and official is None else {}
    rows = []
    for pid, item in CURRICULUM.items():
        samples = []
        for case in item["tests"]:
            if len(samples) >= 3:
                break
            _run_test(pid, case)
            names, sample = public_case(pid, case, item["code"])
            if len(sample["input"].encode()) > 8192:
                continue
            if not any(existing["input"] == sample["input"] for existing in samples):
                samples.append(sample)
        if official is None:
            published = previous.get(pid, [])
        else:
            published = official_examples(pid, official[f"q{pid}"], len(samples[0]["input"].splitlines()))
        seen = {case["input"] for case in published}
        samples = published + [case for case in samples if case["input"] not in seen]
        note = "每行一个 JSON 参数，依次为 " + "、".join(names) + "。输出一行 JSON。"
        if pid in UNORDERED | NESTED_UNORDERED:
            note += "输出数组按数值或字典序升序排列。"
        if pid in NESTED_UNORDERED:
            note += "先对每个内层数组升序排序，再对外层排序。"
        if 94 <= pid and "root" in names:
            note += "二叉树用层序数组，缺失节点用 null，省略末尾 null。"
        solution = next((ROOT / "books/hot100/03-题解").rglob(f"{pid:04d}-*.html"))
        rows.append({"id":f"hot100-{pid}", "title":item["title"], "case_note":note + SPECIAL.get(pid, ""),
                     "solution_url":"/" + solution.relative_to(ROOT).as_posix(), "samples":samples,
                     "checker":{"mode":"json"}, "suite_version":1})
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-snapshot", type=Path, help="LeetCode GraphQL responses keyed by q<id>, fields exampleTestcases and content")
    parser.add_argument("--refresh-official", action="store_true", help="Update published examples from LeetCode CN")
    options = parser.parse_args()
    snapshot = options.official_snapshot
    official = json.loads(snapshot.read_text(encoding="utf-8")) if snapshot else None
    if options.refresh_official or (not OUT.exists() and official is None):
        official = fetch_official()
    rows = build(official)
    if len(rows) != 100 or not all(any(s["source"] == "statement" for s in row["samples"]) for row in rows):
        raise ValueError("Every Hot 100 problem must have a verified official example")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(len(rows), "problems,", sum(len(row["samples"]) for row in rows), "cases")
