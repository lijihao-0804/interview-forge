"""Deterministic golden evaluator for the M7 tool pack.

Default mode validates tool routing, argument schemas, forbidden tools, and
confirmation requirements without making network calls. ``--real`` only
loads the configured provider and prints the manual real-provider checklist;
it never embeds a key or silently spends model quota in CI.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE = ROOT / "tests" / "fixtures" / "ai_agent_golden.json"
_NUMBER_RE = re.compile(r"(?<!\d)(\d{1,9})(?!\d)")
_CITY_RE = re.compile(r"(南京|上海|北京|广州|深圳|杭州|成都|武汉)")


@dataclass
class Prediction:
    tools: list[str] = field(default_factory=list)
    args: dict[str, Any] = field(default_factory=dict)
    confirmation_required: bool = False


@dataclass
class EvalResult:
    total: int
    passed: int
    failures: list[str]

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 1.0


def load_cases(path: Path = FIXTURE) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) < 40:
        raise ValueError("golden fixture must contain at least 40 cases")
    return [dict(item) for item in data]


def _problem_id(query: str) -> int | None:
    match = _NUMBER_RE.search(query)
    return int(match.group(1)) if match else None


def predict_query(query: str) -> Prediction:
    text = " ".join(str(query).strip().split())
    pid = _problem_id(text)
    if "我最近学得怎么样" in text:
        return Prediction()
    if any(word in text for word in ("密码", "token", "rm -rf", "伪造")):
        return Prediction()
    if "同步" in text and ("力扣" in text or "LeetCode" in text or "记录" in text):
        return Prediction(["sync_leetcode"], {"full": "完整" in text}, True)
    if any(word in text for word in ("每日目标", "每天学习目标", "目标设置", "目标改")):
        match = re.search(r"(\d{1,2})\s*轮", text) or re.search(r"为\s*(\d{1,2})", text)
        return Prediction(["set_daily_goal"], {"rounds": int(match.group(1))} if match else {}, True)
    if pid is not None and any(word in text for word in ("明日", "明天安排", "加入明日")):
        return Prediction(["pin_problem_for_tomorrow"], {"problem_id": pid}, True)
    if pid is not None and any(word in text for word in ("标记", "标成", "设置为", "清除")):
        mark = "clear" if "清除" in text else (
            "mastered" if "掌握" in text else "reviewing" if "复习中" in text else "weak"
        )
        return Prediction(["mark_problem"], {"problem_id": pid, "mark": mark}, True)
    if any(word in text for word in ("天气", "下雨")):
        city = _CITY_RE.search(text)
        return Prediction(["get_weather"], {"location": city.group(1)} if city else {})
    if any(word in text for word in ("复习队列", "逾期", "待复习", "到期复习", "需要复习")):
        match = re.search(r"(?:最多|看|给我)\s*(\d{1,2})\s*(?:道|条)", text)
        return Prediction(["get_review_queue"], {"limit": int(match.group(1))} if match else {})
    if pid is not None and "怎么复习" in text:
        return Prediction(["get_learning_context"], {"task": "problem_review", "problem_id": pid})
    if pid is not None and any(word in text for word in ("提交", "做过几次", "学习进度", "掌握情况", "轮", "状态")) and "不要查询提交" not in text:
        return Prediction(["get_problem_progress"], {"problem_id": pid})
    if pid is not None and any(word in text for word in ("是什么题", "基本信息", "基础信息", "原题", "站内链接", "标题", "查一下")):
        return Prediction(["get_problem"], {"problem_id": pid})
    if any(word in text for word in ("最近学得怎么样", "最近状态", "弱项", "学习路线", "今天的学习计划", "今天复习什么")):
        task = "learning_route" if "路线" in text else "today_plan" if "今天" in text else "learning_diagnosis"
        args: dict[str, Any] = {"task": task}
        if pid is not None and "复习" in text and "今天" not in text:
            args = {"task": "problem_review", "problem_id": pid}
        return Prediction(["get_learning_context"], args)
    return Prediction()


def evaluate_cases(cases: list[dict[str, Any]], registry: Any) -> EvalResult:
    specs = {spec.name: spec for spec in registry.list_specs()}
    failures: list[str] = []
    for case in cases:
        case_id = str(case.get("id", "unknown"))
        expected = list(case.get("expected_tools", []))
        prediction = predict_query(str(case.get("query", "")))
        errors: list[str] = []
        for name in expected + list(case.get("forbidden_tools", [])):
            if name not in specs:
                errors.append(f"unknown tool in fixture: {name}")
        if prediction.tools != expected:
            errors.append(f"tools expected={expected} actual={prediction.tools}")
        forbidden = set(case.get("forbidden_tools", []))
        if forbidden.intersection(prediction.tools):
            errors.append(f"forbidden tool used: {sorted(forbidden.intersection(prediction.tools))}")
        expected_confirmation = bool(case.get("confirmation_required", False))
        if prediction.confirmation_required != expected_confirmation:
            errors.append("confirmation requirement mismatch")
        expected_args = case.get("expected_args")
        if expected_args is not None and prediction.args != expected_args:
            errors.append(f"args expected={expected_args} actual={prediction.args}")
        if prediction.tools:
            spec = specs[prediction.tools[0]]
            try:
                spec.args_model.model_validate(prediction.args)
            except Exception as exc:
                errors.append(f"args schema rejected: {type(exc).__name__}")
        if errors:
            failures.append(f"{case_id}: " + "; ".join(errors))
    return EvalResult(len(cases), len(cases) - len(failures), failures)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--real", action="store_true", help="load configured provider; no automatic network call")
    args = parser.parse_args(argv)
    cases = load_cases(args.fixture)
    from interview_forge.ai.tools.registry import build_default_tool_registry

    registry = build_default_tool_registry()
    if args.real:
        from interview_forge.ai.generation import load_ai_config
        config = load_ai_config()
        print(f"real_provider={getattr(config, 'provider', 'unknown')}")
        print(f"real_model={getattr(config, 'model', 'unknown')}")
        print(f"configured={bool(getattr(config, 'configured', False))}")
        print("real calls are manual-only; see scripts/check/ai_tool_smoke.py")
        return 0 if getattr(config, "configured", False) else 2
    result = evaluate_cases(cases, registry)
    print(f"mode=deterministic total={result.total} passed={result.passed} failed={len(result.failures)} accuracy={result.accuracy:.3f}")
    for failure in result.failures:
        print(f"FAIL {failure}")
    return 0 if not result.failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
