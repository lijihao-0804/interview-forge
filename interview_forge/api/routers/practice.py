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
    async_require_user, error_response, json_response, read_json,
)
from interview_forge.observability.logging import log_event

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
        with urllib.request.urlopen(request, timeout=15) as response:
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
