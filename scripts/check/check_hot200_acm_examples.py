"""Check the supplemental ACM fixtures against this repository's published Python solutions."""

import json
import math
from pathlib import Path

from scripts.build.build_hot200_extra import FENCE, sections
from scripts.check.native_acm_python import Interval, ListNode, Node, Point, run_reference

ROOT = Path(__file__).resolve().parents[2]


def catalog_with_teaching_edges():
    catalog = json.loads((ROOT / "data/acm/hot200-extra.json").read_bytes())
    by_id = {row["id"]: row for row in catalog}
    for case in json.loads(
        (ROOT / "tests/fixtures/hot200_teaching_edges.json").read_bytes()
    ):
        by_id[f"hot200-{case['problem_id']}"]["samples"].append(
            {
                "name": case["name"],
                "input": "\n".join(json.dumps(arg) for arg in case["args"]),
                "expected": json.dumps(case["expected"]),
            }
        )
    return catalog


def check():
    catalog = catalog_with_teaching_edges()
    expected_ids = {
        p["id"] for p in json.loads((ROOT / "data/hot200-extra.json").read_bytes())
    }
    assert len(catalog) == len(expected_ids) == 100
    assert {entry["id"] for entry in catalog} == {
        f"hot200-{pid}" for pid in expected_ids
    }
    failed = []
    count = 0
    for entry in catalog:
        pid = int(entry["id"].split("-")[1])
        path = ROOT / f"books/hot200-extra/solutions/{pid}.md"
        code = FENCE.search(sections(path.read_text(encoding="utf-8-sig"))["Python"])[2]
        env = {
            "Node": Node,
            "TreeNode": Node,
            "ListNode": ListNode,
            "Point": Point,
            "Interval": Interval,
        }
        exec(compile(code, str(path), "exec"), env)  # noqa: S102 -- trusted published reference
        for sample in entry["samples"]:
            count += 1
            args = [json.loads(line) for line in sample["input"].splitlines()]
            want = json.loads(sample["expected"])
            try:
                actual = run_reference(pid, env, args)
                good = (
                    math.isclose(actual, want, abs_tol=1e-6)
                    if pid == 774
                    else actual == want
                )
                assert good, (actual, want)
            except Exception as error:  # noqa: BLE001 -- report every failing fixture together
                failed.append((pid, sample["name"], repr(error)))
    if failed:
        raise AssertionError(failed)
    print(f"{len(catalog)} supplemental problems, {count} reference outputs verified")


if __name__ == "__main__":
    check()
