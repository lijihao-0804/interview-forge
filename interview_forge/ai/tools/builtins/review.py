"""Compact review queue read tool backed by the study service."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolResult
from interview_forge.services import study


class GetReviewQueueArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=10, ge=1, le=30)


def get_review_queue(context: ToolExecutionContext, args: GetReviewQueueArgs) -> ToolResult:
    daily = study.daily_data(context.user_db)
    today = str(daily.get("today") or date.today().isoformat())
    marks = study.problem_marks(context.user_db)
    items: list[dict[str, object]] = []
    relearn_ids = {int(item["id"]) for item in daily.get("relearn", [])}

    for raw in [*daily.get("problems", []), *daily.get("relearn", [])]:
        item = dict(raw)
        due_date = str(item.get("due_date") or today)
        status = "overdue" if due_date < today else "due_today"
        items.append({
            "problem_id": int(item["id"]),
            "title": str(item.get("title") or ""),
            "status": status,
            "reason": "relearn" if int(item["id"]) in relearn_ids else "review_due",
            "due_date": due_date,
            "mark": marks.get(str(item["id"])),
        })

    items.sort(key=lambda item: (str(item["due_date"]), int(item["problem_id"])))
    overdue = sum(1 for item in items if item["status"] == "overdue")
    due_today = sum(1 for item in items if item["status"] == "due_today")
    payload = {
        "date": today,
        "overdue": overdue,
        "due_today": due_today,
        "total": len(items),
        "items": items[: int(args.limit)],
    }
    return ToolResult(payload, "已读取复习队列")


__all__ = ["GetReviewQueueArgs", "get_review_queue"]
