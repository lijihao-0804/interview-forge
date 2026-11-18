"""Authenticated practice-code execution endpoint.

The web process never executes user code and never receives Docker/bwrap
privileges.  It forwards a fixed JSON payload to a loopback-only runner
service; the runner is the only component that invokes the sandbox.
"""
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, Request

from interview_forge.api.support import (
    ApiError, async_require_user, error_response, json_response, read_json, user_db,
)
from interview_forge.observability.logging import log_event

from interview_forge.services import native_acm

router = APIRouter()

_MAX_CODE = 64 * 1024
_MAX_STDIN = 16 * 1024
_RUNNER_URL = os.environ.get("PRACTICE_RUNNER_URL", "http://127.0.0.1:8877").rstrip("/")


def _runner_token() -> str:
    value = os.environ.get("PRACTICE_RUNNER_TOKEN", "").strip()
    if value:
        return value
    try:
        from pathlib import Path
        return Path("/etc/interview-forge/practice-runner.token").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _call_runner(payload: dict) -> tuple[int, dict]:
    token = _runner_token()
    if not token:
        return 503, {"error": "练习执行服务未配置"}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{_RUNNER_URL}/run",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Practice-Token": token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            parsed = json.loads(response.read().decode("utf-8"))
            return int(response.status), parsed if isinstance(parsed, dict) else {"error": "执行服务返回格式异常"}
    except urllib.error.HTTPError as exc:
        try:
            parsed = json.loads(exc.read().decode("utf-8"))
        except Exception:
            parsed = {"error": "执行服务暂时不可用"}
        return int(exc.code), parsed if isinstance(parsed, dict) else {"error": "执行服务暂时不可用"}
    except Exception:
        return 503, {"error": "练习执行服务暂时不可用"}


@router.post("/api/practice/run")
async def practice_run(request: Request):
    user, denied = await async_require_user(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request, max_length=120 * 1024)
        language = str(payload.get("language", "")).strip().lower()
        code = payload.get("code")
        stdin_text = payload.get("stdin", "")
        if language not in {"python", "java"}:
            return error_response("只支持 Python 和 Java", 400)
        if not isinstance(code, str) or not isinstance(stdin_text, str):
            return error_response("code 和 stdin 必须是字符串", 400)
        if len(code.encode("utf-8")) > _MAX_CODE:
            return error_response("代码不能超过 64 KiB", 400)
        if len(stdin_text.encode("utf-8")) > _MAX_STDIN:
            return error_response("输入不能超过 16 KiB", 400)

        status_code, result = await asyncio.to_thread(
            _call_runner, {"language": language, "code": code, "stdin": stdin_text}
        )
        # Do not log source code, stdin or stdout.
        log_event(
            "practice_run",
            module="api.practice",
            username=str(user["username"])[:64],
            language=language,
            code_bytes=len(code.encode("utf-8")),
            stdin_bytes=len(stdin_text.encode("utf-8")),
            status=result.get("status", "unknown"),
            http_status=status_code,
        )
        if status_code == 429:
            return json_response(result, 429)
        if status_code != 200:
            return error_response("练习执行服务暂时不可用", 503)
        return json_response(result)
    except BaseException as exc:
        status = getattr(exc, "status", None)
        if isinstance(exc, (ValueError, TypeError, json.JSONDecodeError)):
            return error_response("请求参数不正确", 400)
        if status == 400:
            return error_response(str(exc), 400)
        return error_response("练习执行失败", 500)

@router.get("/api/practice/hot100/status")
async def hot100_status(request: Request):
    user, denied = await async_require_user(request)
    if denied is not None:
        return denied
    values = await asyncio.to_thread(native_acm.statuses, user_db(user))
    return json_response({"statuses": values, "username": user["username"]}, headers={"Cache-Control": "private, no-store"})


@router.get("/api/practice/hot100/problem/{key}")
def native_problem(key: str):
    item = native_acm.problem(key)
    return json_response(item) if item else error_response("题目不存在", 404)


@router.post("/api/practice/hot100/submit")
async def hot100_submit(request: Request):
    user, denied = await async_require_user(request)
    if denied is not None:
        return denied
    try:
        data = await read_json(request, max_length=120 * 1024)
    except (ApiError, ValueError) as exc:
        return error_response(str(exc), 400)
    key, language, code = data.get("id"), data.get("language"), data.get("code")
    if not isinstance(key, str) or not isinstance(language, str) or language not in {"python", "java"}:
        return error_response("题目或语言无效", 400)
    if not isinstance(code, str) or not code.strip() or len(code.encode("utf-8")) > _MAX_CODE:
        return error_response("请提交 64 KiB 以内的代码", 400)
    item = native_acm.problem(key)
    if not item or not item["samples"]:
        return error_response("题目不存在", 404)
    results = []
    for sample in item["samples"]:
        http, result = await asyncio.to_thread(_call_runner, {"language": language, "code": code, "stdin": sample["input"]})
        status = result.get("status")
        if http != 200 or status not in {"ok", "runtime_error", "compile_error", "timeout", "output_limit"}:
            if http == 429:
                return error_response("执行服务繁忙，请稍后重新提交。此次未记入练习状态。", 429)
            if result.get("error") == "练习执行服务未配置":
                return error_response("练习执行服务未配置，此次未记入练习状态。", 503)
            return error_response("练习执行服务暂时不可用，此次未记入练习状态。", 503)
        stdout = result.get("stdout", "")
        if result.get("output_truncated"):
            verdict = "output_limit"
        elif status == "ok":
            verdict = "pass" if native_acm.matches(stdout, sample["expected"], item["checker"]) else "fail"
        else:
            verdict = status
        results.append({"verdict": verdict, "stdout": stdout, "stderr": result.get("stderr", "")})
        if verdict != "pass":
            break
    accepted = len(results) == len(item["samples"]) and all(entry["verdict"] == "pass" for entry in results)
    await asyncio.to_thread(native_acm.save_submission, user_db(user), key, language, code, accepted)
    return json_response({"accepted": accepted, "results": results})


@router.get("/api/practice/hot100/history/{key}")
async def native_history(request: Request, key: str):
    user, denied = await async_require_user(request)
    if denied is not None:
        return denied
    if not native_acm.problem(key):
        return error_response("题目不存在", 404)
    rows = await asyncio.to_thread(native_acm.submission_history, user_db(user), key)
    return json_response({"username": user["username"], "submissions": rows},
                         headers={"Cache-Control": "private, no-store"})


@router.get("/api/practice/hot100/history/{key}/{submission_id}")
async def native_submission_code(request: Request, key: str, submission_id: int):
    user, denied = await async_require_user(request)
    if denied is not None:
        return denied
    if not native_acm.problem(key) or not (0 < submission_id < 2**63):
        return error_response("提交记录不存在", 404)
    code = await asyncio.to_thread(native_acm.submission_code, user_db(user), key, submission_id)
    if code is None:
        return error_response("提交记录不存在", 404)
    return json_response({"username": user["username"], "code": code}, headers={"Cache-Control": "private, no-store"})
