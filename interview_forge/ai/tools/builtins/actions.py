"""Confirmed action tools backed by existing domain services."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolHandlerError, ToolResult
from interview_forge.services import study
from interview_forge.services.leetcode import get_credentials, start_leetcode_sync_task


class SyncLeetCodeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full: bool = False


def sync_leetcode_confirmation(args: SyncLeetCodeArgs) -> str:
    if args.full:
        return "执行一次完整 LeetCode 历史同步"
    return "同步你的最新 LeetCode 学习记录"


def sync_leetcode(context: ToolExecutionContext, args: SyncLeetCodeArgs) -> ToolResult:
    credentials = get_credentials(context.user_db)
    if not credentials.get("leetcode_session"):
        raise ToolHandlerError("not_configured", "请先前往力扣连接页面填写 LEETCODE_SESSION")
    owner = str(context.artifacts.get("username") or context.user_db.parent.name)
    task_id = start_leetcode_sync_task(
        credentials, bool(args.full), owner=owner, db_path=context.user_db
    )
    return ToolResult(
        {"task_id": task_id, "status": "started", "full": bool(args.full)},
        "LeetCode 同步任务已启动",
    )


class MarkProblemArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem_id: int = Field(gt=0)
    mark: Literal["mastered", "reviewing", "weak", "clear"]


_MARK_LABELS = {
    "mastered": "已掌握",
    "reviewing": "复习中",
    "weak": "薄弱",
    "clear": "清除标记",
}


def mark_problem_confirmation(args: MarkProblemArgs) -> str:
    return f"将题目 {args.problem_id} 标记为“{_MARK_LABELS[args.mark]}”"


def mark_problem(context: ToolExecutionContext, args: MarkProblemArgs) -> ToolResult:
    result = study.set_mark(
        "problem", str(args.problem_id), "" if args.mark == "clear" else args.mark,
        context.user_db,
    )
    return ToolResult({"ok": True, "problem_id": args.problem_id, "mark": result["mark"]}, "题目标记已更新")


class PinProblemForTomorrowArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem_id: int = Field(gt=0)


def pin_problem_for_tomorrow_confirmation(args: PinProblemForTomorrowArgs) -> str:
    return f"把题目 {args.problem_id} 加入明日学习计划"


def pin_problem_for_tomorrow(
    context: ToolExecutionContext, args: PinProblemForTomorrowArgs
) -> ToolResult:
    result = study.pin_problem_for_tomorrow(args.problem_id, context.user_db)
    return ToolResult(dict(result), "题目已加入明日学习计划")


class SetDailyGoalArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rounds: int = Field(ge=1, le=50)


def set_daily_goal_confirmation(args: SetDailyGoalArgs) -> str:
    return f"把每日学习目标设置为 {args.rounds} 轮"


def set_daily_goal(context: ToolExecutionContext, args: SetDailyGoalArgs) -> ToolResult:
    result = study.set_setting("daily_goal_rounds", str(args.rounds), context.user_db)
    return ToolResult(dict(result), "每日学习目标已更新")


__all__ = [
    "MarkProblemArgs", "mark_problem", "mark_problem_confirmation",
    "PinProblemForTomorrowArgs", "pin_problem_for_tomorrow",
    "pin_problem_for_tomorrow_confirmation", "SetDailyGoalArgs", "set_daily_goal",
    "set_daily_goal_confirmation", "SyncLeetCodeArgs", "sync_leetcode",
    "sync_leetcode_confirmation",
]
