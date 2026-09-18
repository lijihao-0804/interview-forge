"""Safe recent-action context for the bounded chat assistant."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from interview_forge.ai.actions.store import ActionRequestStore
from interview_forge.ai.chat.context_blocks import ContextBlock
from interview_forge.core.runtime import server_runtime


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
_BACKGROUND_STATUS_LABELS = {
    "running": "同步中",
    "succeeded": "已完成",
    "partial": "部分完成",
    "failed": "失败",
}
_ERROR_LABELS = {
    "provider_blocked": "上游拦截，请同时更新 LEETCODE_SESSION 与 csrftoken 后重试",
    "session_invalid": "会话失效，请同时更新 LEETCODE_SESSION 与 csrftoken 后重试",
    "provider_rate_limited": "上游限流",
    "provider_unavailable": "上游不可用",
    "network_error": "网络错误",
}


def _format_action_time(value: Any) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=server_runtime.BUSINESS_TZ)
        else:
            parsed = parsed.astimezone(server_runtime.BUSINESS_TZ)
        return parsed.strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OverflowError):
        return "时间未知"


def _action_status(row: dict[str, Any]) -> str:
    """Render background sync state without overstating action acceptance."""
    tool_name = str(row.get("tool_name") or "")
    if tool_name != "sync_leetcode":
        return _STATUS_LABELS.get(str(row.get("status")), "状态未知")

    result_meta = row.get("result_meta")
    background = result_meta.get("background") if isinstance(result_meta, dict) else None
    if isinstance(background, dict):
        status = str(background.get("status") or "")
        label = _BACKGROUND_STATUS_LABELS.get(status)
        if label:
            category = _ERROR_LABELS.get(str(background.get("error_category") or ""))
            if category:
                return f"{label}（{category}）"
            return label

    # Legacy rows only recorded that the confirmation handler accepted and
    # launched a task.  They must not be presented as completed syncs.
    if str(row.get("status")) == "succeeded":
        return "已发起（最终状态未知）"
    return _STATUS_LABELS.get(str(row.get("status")), "状态未知")


class RecentActionContextProvider:
    """Expose authoritative action state without arguments, secrets, or results."""

    def build(
        self, *, user_db: Path | str, session_id: str, limit: int = 4
    ) -> ContextBlock | None:
        try:
            store = ActionRequestStore()
            pending_rows = store.list_pending(
                user_db=user_db, session_id=session_id
            )
            rows = store.list_recent(
                user_db=user_db, session_id=session_id, limit=limit
            )
        except Exception:
            # Recent action context is optional; a stale action table must not
            # make normal chat unavailable.
            return None
        bounded_limit = min(max(int(limit), 1), 10)
        lines = [
            "当前确认状态："
            + (
                "存在仍在等待用户确认的操作。"
                if pending_rows
                else "当前没有等待用户确认的操作。"
            )
        ]
        if pending_rows:
            lines.append("待确认操作：")
            for row in pending_rows[:bounded_limit]:
                tool = _TOOL_LABELS.get(str(row.get("tool_name")), "已请求操作")
                timestamp = _format_action_time(row.get("created_at"))
                lines.append(f"- {tool}（发起于 {timestamp}）：等待确认")

        if rows:
            lines.append("最近已处理或执行中的操作：")
        for row in rows:
            tool = _TOOL_LABELS.get(str(row.get("tool_name")), "已请求操作")
            status = _action_status(row)
            timestamp = _format_action_time(
                row.get("created_at") or row.get("decided_at") or row.get("completed_at")
            )
            lines.append(f"- {tool}（发起于 {timestamp}）：{status}")
        content = (
            "以下是当前会话操作的服务端实时状态，仅用于回答用户追问；时间均为北京时间。"
            "本状态优先于历史聊天文字，当前是否等待确认必须以本状态为准。"
            "如果本状态写着“当前没有等待用户确认的操作”，不得声称仍有待确认按钮或待确认操作；"
            "历史助手消息中的“等待确认”不能覆盖这个实时状态。"
            "对于后台同步，只有明确标记为“已完成”才代表数据同步完成；“已发起”或“最终状态未知”不能当作成功。"
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
