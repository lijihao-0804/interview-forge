"""Read-only problem lookup over the canonical Hot100 catalog."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolResult
from interview_forge.core.problem_catalog import LEETCODE_BASE
from interview_forge.core.runtime import server_runtime
from interview_forge.services import hot200, native_acm


class GetProblemArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_id: int | None = None
    query: str | None = None

    @model_validator(mode="after")
    def require_lookup(self) -> "GetProblemArgs":
        if self.problem_id is None and not (self.query or "").strip():
            raise ValueError("problem_id 或 query 至少需要一个")
        if self.query is not None and len(self.query.strip()) > 120:
            raise ValueError("query 过长")
        return self


def _problem_urls(problem: dict[str, Any]) -> tuple[str, str]:
    filename = server_runtime.problem_filename(problem)
    local_url = (
        f"books/hot100/03-题解/{problem['folder']}/"
        f"{Path(filename).with_suffix('.html').name}"
    )
    slug = server_runtime.LEETCODE_SLUGS.get(int(problem["id"]))
    leetcode_url = LEETCODE_BASE.format(slug=slug) if slug else ""
    return local_url, leetcode_url


def _summary(problem: dict[str, Any]) -> dict[str, Any]:
    if "note" in problem:
        local_url = problem["note"]
        leetcode_url = f"https://leetcode.cn/problems/{problem['slug']}/"
    else:
        local_url, leetcode_url = _problem_urls(problem)
    return {
        "problem_id": int(problem["id"]),
        "title": str(problem["title"])[:160],
        "topic": str(problem.get("category", ""))[:80],
        "difficulty": str(problem.get("difficulty", ""))[:32],
        "local_url": local_url,
        "leetcode_url": leetcode_url,
    }


def _matched_problem(problem: dict[str, Any]) -> ToolResult:
    detail = _summary(problem)
    detail["study_notes"] = {
        key: str(problem[key])[:240]
        for key in ("method", "invariant", "time", "space")
        if problem.get(key)
    }
    if "note" in problem:
        detail["study_notes"] = hot200.study_notes(problem["id"])
    return ToolResult({"found": True, "problem": detail}, "已获取题目与解题要点")


def get_problem(_context: ToolExecutionContext, args: GetProblemArgs) -> ToolResult:
    catalog = {**server_runtime.PROBLEM_BY_ID, **hot200.catalog()}
    if args.problem_id is not None:
        problem = catalog.get(int(args.problem_id))
        if problem is None:
            return ToolResult({"found": False, "candidates": []}, "未找到对应题目")
        return _matched_problem(problem)

    query = " ".join((args.query or "").strip().split())
    if query.isdigit():
        problem = catalog.get(int(query))
        if problem is not None:
            return _matched_problem(problem)
    normalized = query.casefold()
    matches = []
    for problem in catalog.values():
        if normalized == str(problem.get("title", "")).casefold():
            return _matched_problem(problem)
        searchable = " ".join(
            str(problem.get(key, ""))
            for key in ("id", "title", "category", "method")
        ).casefold()
        if normalized and normalized in searchable and len(matches) < 5:
            matches.append(_summary(problem))
    return (
        ToolResult({"found": bool(matches), "candidates": matches}, "已获取题目候选")
        if matches
        else ToolResult({"found": False, "candidates": []}, "未找到匹配题目")
    )


class GetAcmExamplesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem_id: int = Field(gt=0, le=999999)
    start_index: int = Field(default=1, ge=1, le=999999, description="样例序号，从 1 开始")
    count: int = Field(default=1, ge=1, le=2)


def get_acm_examples(_context: ToolExecutionContext, args: GetAcmExamplesArgs) -> ToolResult:
    prefix = "hot200" if args.problem_id in hot200.catalog() else "hot100"
    exercise = native_acm.problem(f"{prefix}-{args.problem_id}")
    if exercise is None:
        return ToolResult({"found": False, "problem_id": args.problem_id}, "未找到站内 ACM 题目")
    samples = exercise["samples"]
    examples = []
    for index in range(args.start_index, min(len(samples) + 1, args.start_index + args.count)):
        sample = samples[index - 1]
        item = {"index": index, "name": sample["name"], "source": sample["source"]}
        if sample.get("source_url"):
            item["source_url"] = sample["source_url"]
        for field in ("input", "expected"):
            value = sample[field]
            item[field] = value[:240]
            if len(value) > 240:
                item[field + "_truncated"] = True
        examples.append(item)
    next_index = args.start_index + len(examples)
    return ToolResult({
        "found": True, "problem_id": args.problem_id, "title": exercise["title"],
        "contract": exercise["case_note"], "checker": exercise["checker"], "examples": examples,
        "total": len(samples), "next_index": next_index if next_index <= len(samples) else None,
    }, "已读取公开判题样例" if examples else "样例序号超出范围")


__all__ = ["GetProblemArgs", "get_problem", "GetAcmExamplesArgs", "get_acm_examples"]
