"""Compact per-problem progress read tool."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolResult
from interview_forge.core.runtime import server_runtime
from interview_forge.services import study, submissions


class GetProblemProgressArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem_id: int = Field(gt=0)


def get_problem_progress(
    context: ToolExecutionContext, args: GetProblemProgressArgs
) -> ToolResult:
    problem = server_runtime.PROBLEM_BY_ID.get(int(args.problem_id))
    if problem is None:
        return ToolResult(
            {"found": False, "problem_id": int(args.problem_id)},
            "未找到这道题的学习记录",
        )

    summary = submissions.submission_summary(context.user_db)
    submission = dict(summary.get("problems", {}).get(int(args.problem_id), {}))
    review = dict(study.problem_review_state(context.user_db).get(int(args.problem_id), {}))
    rounds = int(review.get("rounds") or 0)
    completed_at = str(review.get("last_completed_at") or "")
    next_due = None
    if completed_at and rounds > 0:
        next_due = server_runtime.due_after(completed_at, rounds)

    payload = {
        "found": True,
        "problem": {
            "problem_id": int(args.problem_id),
            "title": str(problem.get("title") or ""),
            "mark": study.problem_marks(context.user_db).get(str(args.problem_id)),
            "rounds": rounds,
            "submits": int(submission.get("submits") or 0),
            "ac_submits": int(submission.get("ac_submits") or 0),
            "last_status": submission.get("last_status") or None,
            "last_submitted_at": submission.get("last_submitted_at") or None,
            "next_due": next_due,
        },
    }
    return ToolResult(payload, "已读取这道题的学习进度")


__all__ = ["GetProblemProgressArgs", "get_problem_progress"]
