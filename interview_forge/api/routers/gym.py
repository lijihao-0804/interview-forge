"""工具箱·健身房自动预约 API（仅管理员）。

排程模型见 services/gym.py：一个任务 = 目标日期 + 时段优先级；
到目标日 07:58 后由调度线程自动执行浏览器自动化；
取消只删除自动排程，不触达南大的订单。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from interview_forge.api.support import (
    async_require_admin,
    error_response,
    json_response,
    read_json,
    require_admin,
    service_error,
)
from interview_forge.services import gym
from interview_forge.services.gym import GymServiceError

router = APIRouter()


@router.get("/api/tools/gym/jobs")
def list_gym_jobs(request: Request):
    user, denied = require_admin(request)
    if denied is not None:
        return denied
    try:
        # 同步 handler 运行于线程池，直接调用阻塞的 SQLite 读取即可
        return json_response({"items": gym.list_jobs()})
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc)
        return denied or error_response("读取任务失败", 500)


@router.post("/api/tools/gym/jobs")
async def create_gym_job(request: Request):
    user, denied = await async_require_admin(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc)
        return denied or error_response("请求体无效", 400)
    try:
        job = await asyncio.to_thread(
            gym.create_job,
            str(payload.get("target_date", "")),
            list(payload.get("slots") or []),
            str(user["username"]),
            str(payload.get("venue", "129")),
        )
    except GymServiceError as exc:
        return error_response(str(exc), 400, error_category="invalid_job")
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc, write=True)
        return denied or error_response("创建任务失败", 500)
    return json_response({"job": job})


@router.delete("/api/tools/gym/jobs/{job_id}")
async def cancel_gym_job(job_id: int, request: Request):
    user, denied = await async_require_admin(request)
    if denied is not None:
        return denied
    try:
        job = await asyncio.to_thread(gym.cancel_job, job_id, str(user["username"]))
    except GymServiceError as exc:
        return error_response(str(exc), 400, error_category="invalid_job_state")
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc, write=True)
        return denied or error_response("取消任务失败", 500)
    return json_response({"job": job})


@router.get("/api/tools/gym/status")
def gym_environment_status(request: Request):
    user, denied = require_admin(request)
    if denied is not None:
        return denied
    try:
        env = gym.environment_check()
        creds = gym.credentials_status(str(user["username"]))
        return json_response({"environment": env, "credentials": creds})
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc)
        return denied or error_response("环境自检失败", 500)


@router.get("/api/tools/gym/credentials")
def gym_credentials_status(request: Request):
    user, denied = require_admin(request)
    if denied is not None:
        return denied
    try:
        return json_response(gym.credentials_status(str(user["username"])))
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc)
        return denied or error_response("读取凭据状态失败", 500)


@router.post("/api/tools/gym/credentials")
async def save_gym_credentials(request: Request):
    user, denied = await async_require_admin(request)
    if denied is not None:
        return denied
    try:
        payload = await read_json(request)
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc)
        return denied or error_response("请求体无效", 400)
    try:
        status = await asyncio.to_thread(
            gym.save_credentials,
            str(user["username"]),
            str(payload.get("account", "")),
            str(payload.get("password", "")),
        )
    except GymServiceError as exc:
        return error_response(str(exc), 400, error_category="invalid_credentials")
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc, write=True)
        return denied or error_response("保存凭据失败", 500)
    return json_response({"credentials": status})


@router.delete("/api/tools/gym/credentials")
async def delete_gym_credentials(request: Request):
    user, denied = await async_require_admin(request)
    if denied is not None:
        return denied
    try:
        status = await asyncio.to_thread(gym.delete_credentials, str(user["username"]))
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc, write=True)
        return denied or error_response("删除凭据失败", 500)
    return json_response({"credentials": status})
