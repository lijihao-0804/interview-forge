"""Check native ACM wire examples against the published curriculum and authenticated submission flow."""
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interview_forge.api.routers import practice
from interview_forge.services import native_acm
from scripts.build.hot100_acm import NESTED_UNORDERED, UNORDERED
from tests.test_python_hot100_curriculum import CURRICULUM, _test_namespace, _tree_level, _linked_values, _random_list_pairs

ROOT = Path(__file__).resolve().parents[1]
ROWS = json.loads((ROOT / "data/acm/hot100.json").read_text(encoding="utf-8"))


def reference(pid, args):
    item = CURRICULUM[pid]
    case = item["tests"][0]
    ns = _test_namespace(pid, item["code"])
    if case["kind"] == "design":
        operations, values = args
        obj = ns[operations[0]](*values[0])
        return [None] + [getattr(obj, name)(*a) for name, a in zip(operations[1:], values[1:])]
    link = ns["ListNode"].from_list
    tree = ns["TreeNode"].from_level
    if pid in {141, 142}:
        vals, pos = args
        args = [link(vals) if pos < 0 else ns["make_cycle"](vals, pos)]
    elif pid == 160:
        a, b, c = args
        args = list(ns["make_intersection"](a,b,len(a),len(b),c)[:2])
    elif pid == 236:
        root = tree(args[0])
        nodes = {}
        stack = [root]
        while stack:
            node = stack.pop()
            if node:
                nodes[node.val] = node
                stack.extend((node.left, node.right))
        args = [root, nodes[args[1]], nodes[args[2]]]
    elif pid in {2, 21}:
        args = [link(lst) for lst in args]
    elif pid in {19,24,25,148,206,234}:
        args[0] = link(args[0])
    elif pid == 23:
        args = [[link(lst or []) for lst in args[0]]]
    elif pid == 138:
        args = [ns["Node"].from_random(args[0])]
    elif pid in {94,98,101,102,104,114,124,199,226,230,437,543}:
        args[0] = tree(args[0])
    method = case["call"].split(".")[-1]
    result = getattr(ns["Solution"](), method)(*args)
    if pid in {31,48,73,75,114,189,283}:
        result = args[0]
    if pid == 142:
        node = args[0]
        for i in range(len(vals)):
            if node is result:
                return i
            node = node.next
        return -1
    if pid in {160,236}:
        return result.val if result else None
    if pid in {2,19,21,23,24,25,148,206}:
        return _linked_values(result)
    if pid in {105,108,114,226}:
        return _tree_level(result)
    if pid == 138:
        return _random_list_pairs(result)
    if pid in NESTED_UNORDERED:
        result = [sorted(row) for row in result]
    if pid in UNORDERED | NESTED_UNORDERED:
        result = sorted(result)
    return result


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_official_and_supplemental_examples(row):
    pid = int(row["id"].split("-")[1])
    assert any(case["source"] == "statement" for case in row["samples"])
    for case in row["samples"]:
        args = [json.loads(line) for line in case["input"].splitlines()]
        actual = reference(pid, args)
        assert native_acm.matches(json.dumps(actual), case["expected"], row["checker"]), case


def test_all_native_problem_contracts():
    ids = set()
    for name in ("hot100.json", "hot200-extra.json"):
        rows = json.loads((ROOT / "data/acm" / name).read_text(encoding="utf-8"))
        assert len(rows) == 100
        for row in rows:
            assert native_acm.problem(row["id"]) == row
            number = row["id"].split("-")[1]
            assert number not in ids
            ids.add(number)
            assert len(row["samples"]) >= 1 and row["case_note"]
            for sample in row["samples"]:
                assert native_acm.matches(sample["expected"], sample["expected"], row["checker"])
                assert len(sample["input"].encode()) <= practice._MAX_STDIN


def test_supplement_examples_against_published_solutions():
    from scripts.check.check_hot200_acm_examples import check

    check()


def test_status_lifecycle_and_isolation(tmp_path, monkeypatch):
    app = FastAPI()
    app.include_router(practice.router)
    client = TestClient(app)
    async def auth(request):
        return {"username": request.headers["X-User"]}, None
    monkeypatch.setattr(practice, "async_require_user", auth)
    monkeypatch.setattr(practice, "user_db", lambda u: tmp_path / (u["username"] + ".db"))
    url = "/api/practice/hot100/"
    alice = {"X-User":"alice"}
    bob = {"X-User":"bob"}
    def status(headers):
        return client.get(url + "status", headers=headers).json()["statuses"]
    def submit(code):
        return client.post(url + "submit", headers=alice, json={"id":"hot100-1", "language":"python",
                            "code":code, "accepted":True, "samples":[]})
    assert status(alice) == {}
    outputs = {s["input"]:s["expected"] for s in ROWS[0]["samples"]}
    def runner(payload):
        if payload["code"] == "unconfigured":
            return 503, {"error": "练习执行服务未配置"}
        if payload["code"] == "broken":
            return 500, {"status": "internal_error"}
        if payload["code"] == "busy":
            return 429, {}
        return 200, {"status":"ok", "stdout":outputs[payload["stdin"]] if payload["code"] == "correct" else "false"}
    monkeypatch.setattr(practice, "_call_runner", runner)
    for code, message in [("unconfigured", "未配置"), ("broken", "暂时不可用")]:
        response = submit(code)
        assert response.status_code == 503 and message in response.json()["error"]
        assert status(alice) == {}
    assert submit("busy").status_code == 429 and status(alice) == {}
    assert submit("wrong").json()["accepted"] is False
    assert status(alice) == {"1":"attempted"}
    assert submit("correct").json()["accepted"] is True
    assert status(alice) == {"1":"accepted"}
    assert submit("wrong").json()["accepted"] is False
    assert status(alice) == {"1":"accepted"} and status(bob) == {}
    history = url + "history/hot100-1"
    def records(headers):
        return client.get(history, headers=headers).json()["submissions"]
    rows = records(alice)
    assert [row["accepted"] for row in rows] == [False, True, False]
    assert all("code" not in row and row["submitted_at"].endswith("Z") for row in rows)
    accepted_id = rows[1]["id"]
    assert client.get(f"{history}/{accepted_id}", headers=alice).json()["code"] == "correct"
    assert not records(bob)
    assert client.get(f"{history}/{accepted_id}", headers=bob).status_code == 404
    assert client.get(url + f"history/hot100-49/{accepted_id}", headers=alice).status_code == 404
    for i in range(23):
        native_acm.save_submission(tmp_path / "alice.db", "hot100-1", "java", str(i), False)
    recent = records(alice)
    assert len(recent) == 20 and recent[0]["language"] == "java"
    assert [row["id"] for row in recent] == sorted((r["id"] for r in recent), reverse=True)
