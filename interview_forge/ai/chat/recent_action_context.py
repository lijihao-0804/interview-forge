"""Safe recent-action context for the bounded chat assistant."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from interview_forge.ai.actions.store import ActionRequestStore
from interview_forge.ai.chat.context_blocks import ContextBlock


_TOOL_LABELS = {
    "sync_leetcode": "LeetCode 同步",
    "mark_problem": "题目标记",
    "pin_problem_for_tomorrow": "明日学习计划",
    "set_daily_goal": "每日学习目标",
}
_STATUS_LABELS = {
    "executing": "执行中",
    "succeeded": "已成功",
    "failed": "失败",
    "cancelled": "已取消",
}


class RecentActionContextProvider:
    """Expose only a tiny status summary, never action arguments or results."""

    def build(
        self, *, user_db: Path | str, session_id: str, limit: int = 4
    ) -> ContextBlock | None:
        try:
            rows = ActionRequestStore().list_recent(
                user_db=user_db, session_id=session_id, limit=limit
            )
        except Exception:
            # Recent action context is optional; a stale action table must not
            # make normal chat unavailable.
            return None
        if not rows:
            return None

        lines = []
        for row in rows:
            tool = _TOOL_LABELS.get(str(row.get("tool_name")), "已请求操作")
            status = _STATUS_LABELS.get(str(row.get("status")), "状态未知")
            lines.append(f"- {tool}：{status}")
        content = (
            "以下是当前会话最近操作的服务端状态，仅用于回答用户追问；"
            "不要暴露操作 ID、参数、凭据或内部结果，也不要据此重复执行操作。\n"
            + "\n".join(lines)
        )
        return ContextBlock(
            key="recent_actions",
            content=content,
            priority=70,
            max_tokens=350,
            trusted=True,
        )


__all__ = ["RecentActionContextProvider"]
