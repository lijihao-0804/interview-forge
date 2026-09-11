"""Read-only learning analytics and deterministic context routes."""
from __future__ import annotations

from fastapi import APIRouter, Request

from interview_forge.ai.ai_coach import AIServiceError, ai_capability, get_ai_quota, get_ai_task, get_recent_ai_tasks, submit_ai_feedback
from interview_forge.analytics.cache import analytics_cached
from interview_forge.analytics.context_compiler import compile_learning_context
from interview_forge.analytics.learning_analytics import AnalyticsUnavailableError
from interview_forge.api.support import error_response, json_response, read_json, require_user, service_error, user_db
from interview_forge.core.runtime import server_runtime
from interview_forge.runtime.task_manager import task_manager
from interview_forge.services.auth import effective_ai_daily_limit

router = APIRouter()


def _handled(exc: BaseException):
    return service_error(exc) or error_response("服务暂时不可用", 500)


@router.get("/api/coach/analytics")
def analytics(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        return json_response(analytics_cached(user_db(user)))
    except AnalyticsUnavailableError:
        return error_response("学习分析暂时不可用，请稍后重试", 503, headers={"Retry-After": "1"}, retryable=True)
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/coach/capability")
def capability(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        limit = effective_ai_daily_limit(user)
        value = ai_capability(str(user["username"]), str(user["role"]), limit)
        value["quota"] = get_ai_quota(user_db(user), str(user["role"]), daily_limit=limit)
        return json_response({"ai_coach": value})
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/coach/insights/recent")
def recent(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        return json_response(get_recent_ai_tasks(user_db(user), str(user["username"]), str(user["role"]), effective_ai_daily_limit(user)))
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/coach/tasks/{task_id}")
def task(request: Request, task_id: str):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        value = get_ai_task(user_db(user), task_id, str(user["role"]), effective_ai_daily_limit(user))
        if value is None:
            return error_response("任务不存在或已过期", 404)
        return json_response(value)
    except BaseException as exc:
        return _handled(exc)


@router.post("/api/coach/context")
async def context(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
        allowed = {"task", "user_request", "target_problem_id", "profile", "budget_tier"}
        if any(key not in allowed for key in payload):
            raise ValueError("请求参数不正确")
        value = compile_learning_context(
            analytics_cached(user_db(user)), task=payload.get("task"), user_request=payload.get("user_request", ""),
            target_problem_id=payload.get("target_problem_id"), profile=payload.get("profile"), budget_tier=payload.get("budget_tier"),
        )
        return json_response(value, 201)
    except BaseException as exc:
        return _handled(exc)


@router.post("/api/coach/analyze")
async def analyze(request: Request):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
        if payload:
            raise ValueError("请求参数不正确")
        context = compile_learning_context(analytics_cached(user_db(user)), task="learning_diagnosis", budget_tier="small")
        result = task_manager.submit("ai", user_db(user), context, str(user["username"]), str(user["role"]), effective_ai_daily_limit(user))
        return json_response(result, 201)
    except BaseException as exc:
        return _handled(exc)


@router.post("/api/coach/tasks/{task_id}/cancel")
async def cancel(request: Request, task_id: str):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
        if payload:
            raise ValueError("请求参数不正确")
        value = task_manager.cancel("ai", user_db(user), task_id, str(user["role"]), effective_ai_daily_limit(user))
        return json_response(value, 201)
    except BaseException as exc:
        return _handled(exc, write=True)


@router.post("/api/coach/insights/{insight_id}/feedback")
async def feedback(request: Request, insight_id: str):
    user, denied = require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
        if set(payload) != {"helpful"} or not isinstance(payload.get("helpful"), bool):
            raise ValueError("反馈参数不正确")
        return json_response(submit_ai_feedback(user_db(user), insight_id, payload["helpful"]), 201)
    except BaseException as exc:
        return _handled(exc, write=True)
