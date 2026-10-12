"""工具箱·健身房自动预约 API（仅管理员）。

排程模型见 services/gym.py：一个任务 = 目标日期 + 时段优先级；
到目标日 08:00 后由调度线程自动执行浏览器自动化（预约页不早于 08:00:20 打开）；
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


@router.post("/api/tools/gym/jobs/{job_id}/resolve")
async def resolve_gym_job_for_retry(job_id: int, request: Request):
    """只有管理员明确核对无有效/待支付订单后，才解除不确定任务的日期占用。"""
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
            gym.resolve_job_for_retry,
            job_id,
            str(user["username"]),
            payload.get("confirmed_no_order") is True,
        )
    except GymServiceError as exc:
        return error_response(str(exc), 400, error_category="invalid_job_state")
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc, write=True)
        return denied or error_response("核对任务失败", 500)
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


@router.get("/api/tools/gym/notify")
def gym_notify_status(request: Request):
    user, denied = require_admin(request)
    if denied is not None:
        return denied
    try:
        return json_response(gym.notify_status(str(user["username"])))
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc)
        return denied or error_response("读取通知配置失败", 500)


@router.post("/api/tools/gym/notify")
async def save_gym_notify(request: Request):
    """保存当前用户的收件邮箱（发件 SMTP 为全局配置，见 /api/admin/gym/smtp）。"""
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
            gym.set_notify_recipient,
            str(user["username"]),
            str(payload.get("notify_to", "")),
        )
    except GymServiceError as exc:
        return error_response(str(exc), 400, error_category="invalid_notify_config")
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc, write=True)
        return denied or error_response("保存通知配置失败", 500)
    return json_response({"notify": status})


@router.delete("/api/tools/gym/notify")
async def delete_gym_notify(request: Request):
    user, denied = await async_require_admin(request)
    if denied is not None:
        return denied
    try:
        status = await asyncio.to_thread(gym.delete_notify_recipient, str(user["username"]))
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc, write=True)
        return denied or error_response("删除通知配置失败", 500)
    return json_response({"notify": status})


@router.get("/api/admin/gym/smtp")
def gym_smtp_status(request: Request):
    user, denied = require_admin(request)
    if denied is not None:
        return denied
    try:
        return json_response(gym.smtp_config_status())
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc)
        return denied or error_response("读取发件配置失败", 500)


@router.post("/api/admin/gym/smtp")
async def save_gym_smtp(request: Request):
    """全局发件 SMTP 配置（管理后台，配置一次全站共用）。"""
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
            gym.save_smtp_config,
            str(payload.get("smtp_user", "")),
            str(payload.get("auth_code", "")),
            str(payload.get("smtp_host", "smtp.qq.com")),
            payload.get("smtp_port", 465),
        )
    except GymServiceError as exc:
        return error_response(str(exc), 400, error_category="invalid_smtp_config")
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc, write=True)
        return denied or error_response("保存发件配置失败", 500)
    return json_response({"smtp": status})


@router.delete("/api/admin/gym/smtp")
async def delete_gym_smtp(request: Request):
    user, denied = await async_require_admin(request)
    if denied is not None:
        return denied
    try:
        status = await asyncio.to_thread(gym.delete_smtp_config)
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc, write=True)
        return denied or error_response("删除发件配置失败", 500)
    return json_response({"smtp": status})


@router.post("/api/tools/gym/notify/test")
async def test_gym_notify(request: Request):
    user, denied = await async_require_admin(request)
    if denied is not None:
        return denied
    try:
        status = await asyncio.to_thread(gym.send_test_email, str(user["username"]))
    except GymServiceError as exc:
        return error_response(str(exc), 400, error_category="notify_send_failed")
    except Exception as exc:  # noqa: BLE001
        denied = service_error(exc)
        return denied or error_response("测试邮件发送失败", 502)
    return json_response({"notify": status})
