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

    def _mark_cancelled_if_executing(self, *, user_db: Path, action_id: str) -> None:
        request = self.store.get(user_db=user_db, action_id=action_id)
        if request is not None and str(request.get("status")) == "executing":
            self.store.complete(
                user_db=user_db,
                action_id=action_id,
                status="failed",
                error_code="cancelled",
                result_meta={"error": {"code": "cancelled", "message": "操作已取消。"}},
            )

    async def _recover_cancelled_confirmation(self, *, user_db: Path, action_id: str) -> None:
        try:
            await asyncio.shield(asyncio.to_thread(
                self._mark_cancelled_if_executing,
                user_db=user_db,
                action_id=action_id,
            ))
        except Exception:
            # The original cancellation must still propagate; telemetry/error
            # handling for an unavailable database belongs to the caller.
            return

    async def confirm(self, *, user_db: Path | str, action_id: str) -> dict[str, Any]:
        path = Path(user_db)
        claim_task = asyncio.create_task(asyncio.to_thread(
            self.store.claim_pending,
            user_db=path,
            action_id=action_id,
        ))
        try:
            request = await asyncio.shield(claim_task)
        except asyncio.CancelledError:
            # Only the caller that acquired the claim may settle it.
            try:
                request = await asyncio.shield(claim_task)
            except Exception:
                request = None
            if request and request.get("_claimed"):
                await self._recover_cancelled_confirmation(user_db=path, action_id=action_id)
            raise
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

        # The learner has confirmed. Finish the operation and commit its receipt
        # even if the HTTP client disconnects after the handler starts.
        execution = asyncio.create_task(self._execute_claimed(path, action_id, request))
        try:
            return await asyncio.shield(execution)
        except asyncio.CancelledError:
            await asyncio.shield(execution)
            raise

    async def _execute_claimed(self, path: Path, action_id: str, request: dict[str, Any]) -> dict[str, Any]:
        context = ToolExecutionContext(
            user_db=path,
            session_id=str(request["session_id"]),
            turn_id=str(request["turn_id"]),
            user_message_id=int(request.get("user_message_id") or 0),
            current_query="",
            artifacts={"username": path.parent.name},
        )
        runtime = ToolRuntime(self.registry)
        try:
            result = await runtime.execute_confirmed_action(action_request=request, context=context)
            payload = result.model_payload()
            final_status = "succeeded" if result.status in {"ok", "cache_hit"} else "failed"
            meta = {"result": payload, "display": result.display_text or result.error_message or "操作已处理"}
            await asyncio.to_thread(
                self.store.complete,
                user_db=path,
                action_id=action_id,
                status=final_status,
                error_code=result.error_code,
                result_meta=meta,
            )
        except asyncio.CancelledError:
            # The executor itself was stopped (for example during shutdown).
            await self._recover_cancelled_confirmation(user_db=path, action_id=action_id)
            raise
        return {
            "ok": final_status == "succeeded",
            "action_id": action_id,
            "status": final_status,
            **meta,
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
