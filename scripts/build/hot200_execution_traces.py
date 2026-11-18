"""Record the published solutions on their checked ACM inputs for the static demos.

Run locally with python -m scripts.build.hot200_execution_traces. No code is
evaluated by the site or browser. A trace is published only after output verification.
"""
import itertools
import dis
import json
import math
import os
import random
import sys
from collections import deque
from pathlib import Path
from types import ModuleType

from scripts.check.check_hot200_acm_examples import (
    FENCE, ROOT, Interval, ListNode, Node, Point, run_reference, sections,
)


def snapshot(value, depth=0):
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 7) if math.isfinite(value) else str(value)
    if isinstance(value, str):
        return value[:75] + ("…" if len(value) > 75 else "")
    if depth >= 2:
        if isinstance(value, (list, tuple, set, dict, deque)):
            return f"{type(value).__name__}({len(value)})"
        if hasattr(value, "val") and isinstance(value.val, (str, int, float)):
            return f"{type(value).__name__}({value.val})"
        return type(value).__name__
    if isinstance(value, dict):
        return {str(snapshot(k, depth + 1)): snapshot(v, depth + 1)
                for k, v in itertools.islice(value.items(), 8)} | ({"…": len(value)} if len(value) > 8 else {})
    if isinstance(value, (set, frozenset)):
        items = sorted((snapshot(item, depth + 1) for item in value), key=str)
        return {"$set": items[:32], "$size": len(items)}
    if isinstance(value, (list, tuple, deque)):
        if len(value) <= 32:
            return [snapshot(item, depth + 1) for item in value]
        indices = [*range(8), *range(len(value) - 4, len(value))]
        return {"长度": len(value), **{f"[{i}]": snapshot(value[i], depth + 1) for i in indices}}
    attrs = {k: snapshot(v, depth + 1) for k, v in vars(value).items()
             if not callable(v) and v is not None} if hasattr(value, "__dict__") else {}
    return attrs or type(value).__name__


def capture(path, sample, run):
    states = []

    def trace(frame, event, arg):
        if frame.f_code.co_filename != str(path):
            return None
        if event in ("line", "return") and frame.f_code.co_flags & 1 and not frame.f_code.co_name.startswith("<"):
            values = {k: snapshot(v) for k, v in frame.f_locals.items()
                      if not callable(v) and not isinstance(v, ModuleType)}
            returning = event == "return"
            if returning:
                yielded = dis.opname[frame.f_code.co_code[frame.f_lasti]] == "YIELD_VALUE"
                values["产出" if yielded else "返回"] = snapshot(arg)
                returning = not yielded
            states.append([frame.f_lineno, frame.f_code.co_name, values, returning])
        return trace

    previous = sys.gettrace()
    random_state = random.getstate()
    try:
        random.seed(0)
        sys.settrace(trace)
        actual = run()
    finally:
        sys.settrace(previous)
        random.setstate(random_state)
    # Keep exact positions visible when long loops are sampled.
    count = len(states)
    if not count:
        raise ValueError(f"{path}: empty execution")
    indices = sorted({round(i * (count - 1) / 19) for i in range(20)})
    return {"label": sample["name"], "input": sample["input"].strip(), "output": actual, "count": count,
            "steps": [[i + 1, *states[i]] for i in indices]}


def supplement(pid, path, code, sample):
    env = dict(Node=Node, TreeNode=Node, ListNode=ListNode, Point=Point, Interval=Interval)
    exec(compile(code, str(path), "exec"), env)
    args = [json.loads(line) for line in sample["input"].splitlines()]
    case = capture(path, sample, lambda: run_reference(pid, env, args))
    actual, want = case["output"], json.loads(sample["expected"])
    if not (math.isclose(actual, want, abs_tol=1e-6) if pid == 774 else actual == want):
        raise ValueError(f"LC {pid}: {sample['name']} returned {actual!r}, expected {want!r}")
    return case


def publish(target, content):
    if "--check" in sys.argv:
        if target.read_text(encoding="utf-8") != content:
            raise ValueError(f"{target}: regenerate the published execution")
    else:
        target.write_text(content, encoding="utf-8")


def publish_problem(folder, pid, title, code, cases):
    lines = code.splitlines()
    used = {step[1] for case in cases for step in case["steps"]}
    payload = {"id": pid, "title": title, "lines": {i: lines[i - 1].strip() for i in sorted(used)}, "cases": cases}
    content = "window.Hot200Execution=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    publish(folder / f"{pid}.js", content)


def main():
    if os.environ.get("PYTHONHASHSEED") != "0":
        import subprocess
        return subprocess.call([sys.executable, "-m", "scripts.build.hot200_execution_traces", *sys.argv[1:]],
                               env={**os.environ, "PYTHONHASHSEED": "0"})
    folder = ROOT / "books/hot200-extra/executions"
    folder.mkdir(exist_ok=True)
    entries = json.loads((ROOT / "data/acm/hot200-extra.json").read_bytes())
    for entry in entries:
        pid = int(entry["id"].split("-")[1])
        path = ROOT / f"books/hot200-extra/solutions/{pid}.md"
        code = FENCE.search(sections(path.read_text(encoding="utf-8-sig"))["Python"])[2]
        cases = [supplement(pid, path, code, sample) for sample in entry["samples"]]
        publish_problem(folder, pid, entry["title"], code, cases)
    from scripts.build.hot100_acm import CURRICULUM, _run_test, public_case
    from scripts.build.build_html_site import VISUAL_EMBEDS
    folder = ROOT / "books/hot100/executions"
    folder.mkdir(exist_ok=True)
    original_cases = 0
    public_outputs = {
        int(row["id"].split("-")[1]): {
            sample["input"].strip(): json.loads(sample["expected"]) for sample in row["samples"]
        } for row in json.loads((ROOT / "data/acm/hot100.json").read_bytes())
    }
    for pid, item in CURRICULUM.items():
        cases = []
        for test in item["tests"]:
            _, sample = public_case(pid, test, item["code"])
            # Deep-chain stress tests remain in the curriculum suite. A phone
            # viewport needs readable examples, including small edge cases.
            if max(len(sample["input"]), len(sample["expected"])) > 650:
                continue
            def checked_output():
                _run_test(pid, test)
                return json.loads(sample["expected"])
            case = capture(f"<python-hot100-{pid}>", sample, checked_output)
            outputs = public_outputs[pid]
            if case["input"] in outputs and case["output"] != outputs[case["input"]]:
                raise ValueError(f"LC {pid}: {case['label']} conflicts with another output for this input")
            outputs[case["input"]] = case["output"]
            cases.append(case)
        if not cases:
            raise ValueError(f"LC {pid}: no readable execution examples")
        original_cases += len(cases)
        publish_problem(folder, pid, item["title"], item["code"], cases)
    routes = {"/".join([file, query.get("mode", ""), query.get("panel", "")]): int(Path(source).name[:4])
              for source, (file, query) in VISUAL_EMBEDS.items() if "/03-题解/" in source}
    if len(routes) != len(CURRICULUM):
        raise ValueError("Every original problem must have a distinct visual route")
    publish(folder / "routes.js", "window.Hot100ExecutionRoutes=" +
            json.dumps(routes, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + ";\n")
    print(f"{len(entries) + len(CURRICULUM)} algorithms, "
          f"{sum(len(e['samples']) for e in entries) + original_cases} checked input traces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
