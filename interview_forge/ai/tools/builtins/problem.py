"""Read-only problem lookup over the canonical Hot100 catalog."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolResult
from interview_forge.core.problem_catalog import LEETCODE_BASE
from interview_forge.core.runtime import server_runtime


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
    local_url, leetcode_url = _problem_urls(problem)
    return {
        "problem_id": int(problem["id"]),
        "title": str(problem["title"])[:160],
        "topic": str(problem.get("category", ""))[:80],
        "difficulty": str(problem.get("difficulty", ""))[:32],
        "local_url": local_url,
        "leetcode_url": leetcode_url,
    }


def get_problem(_context: ToolExecutionContext, args: GetProblemArgs) -> ToolResult:
    catalog = server_runtime.PROBLEM_BY_ID
    if args.problem_id is not None:
        problem = catalog.get(int(args.problem_id))
        if problem is None:
            return ToolResult({"found": False, "candidates": []}, "未找到对应题目")
        return ToolResult({"found": True, "problem": _summary(problem)}, "已获取题目信息")

    query = " ".join((args.query or "").strip().split())
    if query.isdigit():
        problem = catalog.get(int(query))
        if problem is not None:
            return ToolResult({"found": True, "problem": _summary(problem)}, "已获取题目信息")
    normalized = query.casefold()
    matches = []
    for problem in catalog.values():
        searchable = " ".join(
            str(problem.get(key, ""))
            for key in ("id", "title", "category", "method")
        ).casefold()
        if normalized and normalized in searchable:
            matches.append(_summary(problem))
        if len(matches) >= 5:
            break
    return (
        ToolResult({"found": bool(matches), "candidates": matches}, "已获取题目候选")
        if matches
        else ToolResult({"found": False, "candidates": []}, "未找到匹配题目")
    )


__all__ = ["GetProblemArgs", "get_problem"]
