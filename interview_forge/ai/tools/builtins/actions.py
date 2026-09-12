"""Confirmed action tools backed by existing domain services."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolHandlerError, ToolResult
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


__all__ = ["SyncLeetCodeArgs", "sync_leetcode", "sync_leetcode_confirmation"]
