"""Read-only learning context tool backed by the existing compiler."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from interview_forge.ai.chat.learning_context import LearningContextProvider
from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolResult


class GetLearningContextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: Literal["learning_diagnosis", "today_plan", "learning_route", "problem_review"]
    problem_id: int | None = None

    @model_validator(mode="after")
    def require_problem_for_review(self) -> "GetLearningContextArgs":
        if self.task == "problem_review" and (self.problem_id is None or self.problem_id <= 0):
            raise ValueError("problem_review 需要有效题号")
        return self


def _tool_result(value: dict[str, object], *, reused: bool = False) -> ToolResult:
    projection = value.get("projection")
    data = {
        "available": bool(value.get("available")),
        "task": value.get("task"),
        "problem_id": value.get("target_problem_id"),
        "projection": projection if isinstance(projection, dict) else {},
        "data_quality": value.get("data_quality", {}),
        "reused_preloaded": reused,
    }
    return ToolResult(data, "已获取学习数据" if value.get("available") else "学习数据暂不可用")


def get_learning_context(context: ToolExecutionContext, args: GetLearningContextArgs) -> ToolResult:
    preloaded = context.artifacts.get("learning_context")
    if isinstance(preloaded, dict):
        if (
            preloaded.get("task") == args.task
            and preloaded.get("target_problem_id") == args.problem_id
        ):
            return _tool_result(preloaded, reused=True)
    value = LearningContextProvider().build_for_task(
        user_db=context.user_db,
        task=args.task,
        problem_id=args.problem_id,
    )
    return _tool_result(value)


__all__ = ["GetLearningContextArgs", "get_learning_context"]
