"""Confirmation and exactly-once execution service for ACTION tools."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from interview_forge.ai.tools.contracts import ToolExecutionContext
from interview_forge.ai.tools.registry import ToolRegistry, build_default_tool_registry
from interview_forge.ai.tools.runtime import ToolRuntime

from .store import ActionRequestError, ActionRequestStore


class ActionService:
    def __init__(
        self,
        *,
        registry: ToolRegistry | None = None,
        store: ActionRequestStore | None = None,
    ) -> None:
        self.registry = registry or build_default_tool_registry()
        self.store = store or ActionRequestStore()

    async def confirm(self, *, user_db: Path | str, action_id: str) -> dict[str, Any]:
        path = Path(user_db)
        request = await asyncio.to_thread(self.store.claim_pending, user_db=path, action_id=action_id)
        if request is None:
            raise ActionRequestError("操作不存在", 404, "not_found")
        status = str(request["status"])
        if status == "expired":
            raise ActionRequestError("确认已过期", 410, "expired")
        if status == "cancelled":
            raise ActionRequestError("操作已取消", 409, "cancelled")
        if status == "succeeded":
            return {"ok": True, "action_id": action_id, "status": status, **request.get("result_meta", {})}
        if status == "failed":
            return {"ok": False, "action_id": action_id, "status": status, **request.get("result_meta", {})}
        if status != "executing":
            raise ActionRequestError("操作当前不可确认", 409, "invalid_status")
        if not request.get("_claimed"):
            raise ActionRequestError("操作正在执行，请稍后查看结果", 409, "in_progress")

        context = ToolExecutionContext(
            user_db=path,
            session_id=str(request["session_id"]),
            turn_id=str(request["turn_id"]),
            user_message_id=int(request.get("user_message_id") or 0),
            current_query="",
            artifacts={"username": path.parent.name},
        )
        runtime = ToolRuntime(self.registry)
        result = await runtime.execute_confirmed_action(action_request=request, context=context)
        payload = result.model_payload()
        final_status = "succeeded" if result.status in {"ok", "cache_hit"} else "failed"
        meta = {"result": payload, "display": result.display_text or ""}
        await asyncio.to_thread(
            self.store.complete,
            user_db=path,
            action_id=action_id,
            status=final_status,
            error_code=result.error_code,
            result_meta=meta,
        )
        return {
            "ok": final_status == "succeeded",
            "action_id": action_id,
            "status": final_status,
            "result": payload,
            "display": result.display_text or result.error_message or "操作已处理",
        }

    async def cancel(self, *, user_db: Path | str, action_id: str) -> dict[str, Any]:
        request = await asyncio.to_thread(self.store.cancel, user_db=Path(user_db), action_id=action_id)
        if request is None:
            raise ActionRequestError("操作不存在", 404, "not_found")
        status = str(request["status"])
        if status == "expired":
            raise ActionRequestError("确认已过期", 410, "expired")
        if status != "cancelled":
            raise ActionRequestError("操作已处理，不能取消", 409, "invalid_status")
        return {"ok": True, "action_id": action_id, "status": "cancelled"}


__all__ = ["ActionService"]
