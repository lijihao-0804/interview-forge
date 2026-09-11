"""Learning, review, dashboard, export and submission routes."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import Response

from interview_forge.ai.ai_coach import ai_capability, get_ai_quota
from interview_forge.api.support import error_response, invalidate_dashboard, invalidate_learning, json_response, require_user, service_error, user_db
from interview_forge.services.auth import effective_ai_daily_limit
from interview_forge.services.submissions import record_submission, submissions_for_problem
from interview_forge.services.study import (
    complete_content, complete_round, daily_data, dashboard_cached, export_data,
    export_database, get_settings, library_data, mock_exam, pin_plan, pick_problem,
    problem_marks, set_mark, set_setting, today_plan, weaklist,
)
from interview_forge.analytics.cache import analytics_cached

router = APIRouter()


def _handled(exc: BaseException, *, write: bool = False):
    return service_error(exc, write=write) or error_response("服务暂时不可用", 500)


def _user(request: Request):
    return require_user(request)


@router.get("/api/bootstrap")
def bootstrap(request: Request):
    user, denied = _user(request)
    if denied is not None:
        return denied
    try:
        db = user_db(user)
        limit = effective_ai_daily_limit(user)
        capability = ai_capability(str(user["username"]), str(user["role"]), limit)
        capability["quota"] = get_ai_quota(db, str(user["role"]), daily_limit=limit)
        return json_response({"dashboard": dashboard_cached(db), "daily": daily_data(db),
                              "settings": get_settings(db), "capabilities": {"ai_coach": capability}})
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/dashboard")
def dashboard(request: Request):
    user, denied = _user(request)
    if denied is not None:
        return denied
    try:
        return json_response(dashboard_cached(user_db(user)))
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/library")
def library(request: Request):
    user, denied = _user(request)
    if denied is not None:
        return denied
    try:
        return json_response(library_data(user_db(user)))
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/daily")
def daily(request: Request):
    user, denied = _user(request)
    if denied is not None:
        return denied
    try:
        return json_response(daily_data(user_db(user), module_id=request.query_params.get("module", "")))
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/settings")
def settings_get(request: Request):
    user, denied = _user(request)
    if denied is not None:
        return denied
    try:
        return json_response(get_settings(user_db(user)))
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/pick")
def pick(request: Request):
    user, denied = _user(request)
    if denied is not None:
        return denied
    try:
        return json_response(pick_problem(db_path=user_db(user), randomize=request.query_params.get("random") == "1",
                                          category=request.query_params.get("category", ""),
                                          difficulty=request.query_params.get("difficulty", "")))
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/mock")
def mock(request: Request):
    user, denied = _user(request)
    if denied is not None:
        return denied
    try:
        try:
            count = max(1, min(int(request.query_params.get("count", "10") or "10"), 50))
        except ValueError as exc:
            raise ValueError("count 必须是整数") from exc
        return json_response(mock_exam(count=count, category=request.query_params.get("category", ""),
                                       difficulty=request.query_params.get("difficulty", "")))
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/plan")
def plan(request: Request):
    user, denied = _user(request)
    if denied is not None:
        return denied
    try:
        try:
            count = max(1, min(int(request.query_params.get("count", "3") or "3"), 20))
        except ValueError as exc:
            raise ValueError("count 必须是整数") from exc
        return json_response(today_plan(user_db(user), count=count, randomize=request.query_params.get("random") == "1"))
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/weaklist")
def weak_list(request: Request):
    user, denied = _user(request)
    if denied is not None:
        return denied
    try:
        return json_response(weaklist(user_db(user)))
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/submissions")
def submissions(request: Request):
    user, denied = _user(request)
    if denied is not None:
        return denied
    try:
        try:
            problem_id = int(request.query_params.get("problem_id", ""))
        except ValueError as exc:
            raise ValueError("缺少合法 problem_id") from exc
        return json_response({"problem_id": problem_id, "items": submissions_for_problem(problem_id, db_path=user_db(user))})
    except BaseException as exc:
        return _handled(exc)


@router.get("/api/export")
def export(request: Request):
    user, denied = _user(request)
    if denied is not None:
        return denied
    db = user_db(user)
    kind = request.query_params.get("kind", "")
    if kind == "db":
        try:
            body = export_database(db)
            return Response(content=body, media_type="application/octet-stream",
                            headers={"Content-Disposition": 'attachment; filename="hot100-study.db"', "Cache-Control": "no-store"})
        except BaseException as exc:
            return _handled(exc, write=True)
    try:
        content_type, filename, data = export_data(kind, db)
        ascii_name = {"anki": "hot100-anki.csv", "weak": "hot100-weak.md", "records": "hot100-records.json"}.get(kind, "export.txt")
        disposition = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
        return Response(content=data.encode("utf-8"), media_type=content_type, headers={"Content-Disposition": disposition, "Cache-Control": "no-store"})
    except BaseException as exc:
        return _handled(exc)


@router.post("/api/complete")
async def complete(request: Request):
    return await _write_json(request, lambda p, db: complete_round(int(p["problem_id"]), db))


@router.post("/api/content/complete")
async def content_complete(request: Request):
    return await _write_json(request, lambda p, db: complete_content(str(p["module_id"]), str(p["content_id"]), db))


@router.post("/api/mark")
async def mark(request: Request):
    return await _write_json(request, lambda p, db: set_mark(str(p["target_type"]), str(p["target_id"]), str(p.get("mark", "")), db))


@router.post("/api/settings")
async def settings_set(request: Request):
    return await _write_json(request, lambda p, db: set_setting(str(p.get("key", "")), str(p.get("value", "")), db))


@router.post("/api/submit")
async def submit(request: Request):
    def operation(p, db):
        return record_submission(problem_id=int(p["problem_id"]), status=str(p["status"]), lang=str(p.get("lang", "")),
                                 runtime_ms=p.get("runtime_ms"), memory_kb=p.get("memory_kb"),
                                 source=str(p.get("source", "manual")), db_path=db)
    return await _write_json(request, operation)


@router.post("/api/plan/pin")
async def plan_pin(request: Request):
    def operation(p, db):
        pid = int(p.get("problem_id", 0))
        return pin_plan(pid, db)
    return await _write_json(request, operation)


async def _write_json(request: Request, operation):
    from interview_forge.api.support import read_json
    user, denied = _user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
        result = operation(payload, user_db(user))
        invalidate_learning(user_db(user))
        return json_response(result, 201)
    except BaseException as exc:
        return _handled(exc, write=True)
