"""工具箱·健身房自动预约：每用户加密凭据 + 排程持久化 + 到点执行调度。

设计要点
========
* 站点只支持约当天，名额在当天 08:00 放出；因此“任选日期”的语义是
  预排一个任务，调度线程在目标日 08:00 后执行浏览器自动化
  （gym_automation，子进程，Playwright 真机操作）；执行器不早于 08:00:20 进入预约流程。
* 每用户凭据：用户在前端输入南大账号密码，Fernet 加密（scrypt KDF，
  主密钥取 INTERVIEW_FORGE_GYM_KEY 环境变量，缺省时自动生成本机密钥文件
  data/gym-secret.key）后存入本模块数据库，按用户隔离。任务执行时以
  创建者的凭据经 stdin 传给子进程，不落在命令行/日志里。
* 取消语义：只取消本工具的自动排程，绝不调用南大的任何取消接口。
* 执行器跟随后端所在机器：本机跑就是本机浏览器；未来部署到 VPS 时，
  在那台机器安装依赖与 Chromium（见 requirements-tools.txt）即可。
* 多 worker 安全：SQLite 原子抢占（UPDATE ... WHERE status='pending'）
  + runtime.shared.mutex 进程间互斥，保证一个任务只被一个 worker 执行。
* 无第三方调度依赖：app lifespan 里启停一条 daemon 线程，每 30s 扫描。
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from interview_forge.core.paths import DATA_DIR, GYM_DB_PATH, GYM_LOG_DIR, ROOT
from interview_forge.runtime.shared import mutex

log = logging.getLogger(__name__)

SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")
# 站点名额 08:00 放出；任务到 08:00 才启动，执行器在 08:00:20 前等待后再进预约流程。
RUN_EARLIEST = (8, 0)
# 执行器无空位时每 5 分钟复查，避免高频重新加载场馆页面。
JOB_SUBPROCESS_TIMEOUT_SECONDS = 35 * 60
JOB_RUNNING_STALE_GRACE_SECONDS = 5 * 60
JOB_MAX_ATTEMPTS = 3
# 重试间隔递增：放号后十来分钟站点都处在过载状态（2026-10-15 两个任务的三次尝试全
# 落在 08:00~08:12 区间，全部倒在页面导航超时），固定 5 分钟会让最后一次尝试也撞在
# 高峰里；第二档 10 分钟把最后一次推到站点缓过来之后。
JOB_RETRY_DELAYS_SECONDS = (5 * 60, 10 * 60)
MAX_SLOTS_PER_JOB = 6
SUPPORTED_VENUES = frozenset({"129", "162"})
SLOT_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d$")
_KDF_SALT = b"interview-forge-gym-credentials-v1"
SECRET_KEY_PATH = DATA_DIR / "gym-secret.key"

JOB_STATUSES = ("pending", "running", "succeeded", "no_slot", "ambiguous", "failed", "cancelled")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gym_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_date TEXT NOT NULL,
    slots TEXT NOT NULL,
    venue TEXT NOT NULL DEFAULT '129',
    status TEXT NOT NULL DEFAULT 'pending',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    result TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_gym_jobs_date_status ON gym_jobs (target_date, status);
CREATE TABLE IF NOT EXISTS gym_credentials (
    username TEXT PRIMARY KEY,
    account_encrypted TEXT NOT NULL,
    password_encrypted TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gym_notify_config (
    username TEXT PRIMARY KEY,
    smtp_host TEXT NOT NULL DEFAULT 'smtp.qq.com',
    smtp_port INTEGER NOT NULL DEFAULT 465,
    smtp_user TEXT NOT NULL,
    auth_code_encrypted TEXT NOT NULL,
    notify_to TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gym_smtp_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    smtp_host TEXT NOT NULL DEFAULT 'smtp.qq.com',
    smtp_port INTEGER NOT NULL DEFAULT 465,
    smtp_user TEXT NOT NULL,
    auth_code_encrypted TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    GYM_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(GYM_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.executescript(_SCHEMA)
    # 一次性迁移：旧的按用户 SMTP 配置 → 全局发件配置。
    # 只认 auth_code 非空的遗留行（纯收件占位行不该触发迁移）；
    # delete_smtp_config 会同步清空遗留行，避免每次连接都被复活。
    conn.execute(
        "INSERT INTO gym_smtp_config (id, smtp_host, smtp_port, smtp_user,"
        " auth_code_encrypted, updated_at)"
        " SELECT 1, smtp_host, smtp_port, smtp_user, auth_code_encrypted, updated_at"
        " FROM gym_notify_config"
        " WHERE auth_code_encrypted != ''"
        " AND NOT EXISTS (SELECT 1 FROM gym_smtp_config)"
        " ORDER BY updated_at DESC LIMIT 1"
    )
    conn.commit()
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    job = dict(row)
    try:
        job["slots"] = json.loads(job.get("slots") or "[]")
    except (TypeError, ValueError):
        job["slots"] = []
    try:
        job["result"] = json.loads(job.get("result") or "{}")
    except (TypeError, ValueError):
        job["result"] = {}
    return job


# ------------------------------------------------------------- 凭据（每用户加密）

def _fernet() -> Fernet:
    """主密钥：环境变量 INTERVIEW_FORGE_GYM_KEY（Fernet key 或任意口令，口令走
    scrypt KDF）；未设置时使用首次自动生成的本机密钥文件 data/gym-secret.key。"""
    raw = os.environ.get("INTERVIEW_FORGE_GYM_KEY", "").strip()
    if not raw:
        SECRET_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not SECRET_KEY_PATH.exists():
            key = Fernet.generate_key()
            SECRET_KEY_PATH.write_bytes(key)
            try:
                os.chmod(SECRET_KEY_PATH, 0o600)
            except OSError:  # noqa: BLE001
                pass
            log.info("已生成健身房凭据本机密钥文件 %s", SECRET_KEY_PATH)
        raw = SECRET_KEY_PATH.read_text(encoding="utf-8").strip()
    try:
        return Fernet(raw.encode("ascii"))
    except Exception:
        digest = hashlib.scrypt(
            raw.encode("utf-8"), salt=_KDF_SALT, n=1 << 14, r=8, p=1, dklen=32)
        return Fernet(base64.urlsafe_b64encode(digest))


def save_credentials(username: str, account: str, password: str,
                     verify: bool = True) -> dict:
    """保存南大凭据。默认先做一次真实登录验证（含滑块），密码错误直接拒绝，
    避免到预约那一步才发现。验证基础设施异常时降级为保存+警告。"""
    account = str(account or "").strip()
    password = str(password or "")
    if not re.fullmatch(r"[A-Za-z0-9]{6,20}", account):
        raise GymServiceError("账号应为 6-20 位数字或字母（学号/工号）")
    if len(password) < 6 or len(password) > 64:
        raise GymServiceError("密码长度应为 6-64 位")
    verification = {"status": "skipped", "detail": "未执行"}
    if verify:
        verification = verify_credentials(account, password)
        if verification.get("status") == "bad_credentials":
            raise GymServiceError(f"南大账号或密码不正确，已拒绝保存（{verification.get('detail', '')}）")
        if verification.get("status") == "captcha_failed":
            raise GymServiceError("登录滑块验证未通过，请稍后重试保存")
    cipher = _fernet()
    enc_account = cipher.encrypt(account.encode("utf-8")).decode("ascii")
    enc_password = cipher.encrypt(password.encode("utf-8")).decode("ascii")
    with mutex("gym", "write", timeout=10):
        conn = connect()
        try:
            conn.execute(
                "INSERT INTO gym_credentials (username, account_encrypted,"
                " password_encrypted, updated_at) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(username) DO UPDATE SET account_encrypted=excluded.account_encrypted,"
                " password_encrypted=excluded.password_encrypted, updated_at=excluded.updated_at",
                (username, enc_account, enc_password, _now()),
            )
            conn.commit()
        finally:
            conn.close()
    status = credentials_status(username)
    status["verification"] = verification
    return status


def _load_credentials_decrypted(username: str) -> tuple[str, str]:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM gym_credentials WHERE username = ?", (username,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise GymServiceError("尚未配置南大账号密码，请先在工具箱中保存凭据")
    cipher = _fernet()
    try:
        account = cipher.decrypt(row["account_encrypted"].encode("ascii")).decode("utf-8")
        password = cipher.decrypt(row["password_encrypted"].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise GymServiceError("凭据解密失败：主密钥与加密时不一致（检查 INTERVIEW_FORGE_GYM_KEY"
                              " 或 data/gym-secret.key 是否被更换）") from exc
    return account, password


def credentials_status(username: str) -> dict:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT account_encrypted, updated_at FROM gym_credentials WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"configured": False, "account_masked": "", "updated_at": ""}
    cipher = _fernet()
    try:
        account = cipher.decrypt(row["account_encrypted"].encode("ascii")).decode("utf-8")
    except InvalidToken:  # noqa: BLE001
        account = ""
    masked = account[:3] + "****" + account[-2:] if len(account) > 5 else "****"
    return {"configured": True, "account_masked": masked, "updated_at": row["updated_at"]}


def delete_credentials(username: str) -> dict:
    with mutex("gym", "write", timeout=10):
        conn = connect()
        try:
            conn.execute("DELETE FROM gym_credentials WHERE username = ?", (username,))
            conn.commit()
        finally:
            conn.close()
    return {"configured": False, "account_masked": "", "updated_at": ""}


# ------------------------------------------------------------- 通知（全局发件 + 每人收件）

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def save_smtp_config(smtp_user: str, auth_code: str,
                     smtp_host: str = "smtp.qq.com", smtp_port: int = 465) -> dict:
    """全局发件 SMTP 配置（管理后台配置一次，全站共用）。授权码 Fernet 加密。"""
    smtp_user = str(smtp_user or "").strip()
    auth_code = str(auth_code or "").strip()
    smtp_host = str(smtp_host or "").strip() or "smtp.qq.com"
    try:
        smtp_port = int(smtp_port)
    except (TypeError, ValueError) as exc:
        raise GymServiceError("SMTP 端口应为数字") from exc
    if not _EMAIL_PATTERN.fullmatch(smtp_user):
        raise GymServiceError("发件邮箱格式不正确")
    if not 8 <= len(auth_code) <= 32:
        raise GymServiceError("SMTP 授权码应为 8-32 位（QQ 邮箱为 16 位授权码，不是 QQ 密码）")
    if not 1 <= smtp_port <= 65535:
        raise GymServiceError("SMTP 端口不合法")
    enc_code = _fernet().encrypt(auth_code.encode("utf-8")).decode("ascii")
    with mutex("gym", "write", timeout=10):
        conn = connect()
        try:
            conn.execute(
                "INSERT INTO gym_smtp_config (id, smtp_host, smtp_port, smtp_user,"
                " auth_code_encrypted, updated_at) VALUES (1, ?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET smtp_host=excluded.smtp_host,"
                " smtp_port=excluded.smtp_port, smtp_user=excluded.smtp_user,"
                " auth_code_encrypted=excluded.auth_code_encrypted, updated_at=excluded.updated_at",
                (smtp_host, smtp_port, smtp_user, enc_code, _now()),
            )
            conn.commit()
        finally:
            conn.close()
    return smtp_config_status()


def smtp_config_status() -> dict:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT smtp_host, smtp_port, smtp_user, updated_at FROM gym_smtp_config WHERE id = 1"
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"configured": False}
    return {"configured": True, "smtp_host": row["smtp_host"], "smtp_port": row["smtp_port"],
            "smtp_user": row["smtp_user"], "updated_at": row["updated_at"]}


def delete_smtp_config() -> dict:
    with mutex("gym", "write", timeout=10):
        conn = connect()
        try:
            conn.execute("DELETE FROM gym_smtp_config WHERE id = 1")
            # 同步清空遗留按用户行里的发件字段，防止 connect() 迁移把配置复活
            conn.execute(
                "UPDATE gym_notify_config SET smtp_user='', auth_code_encrypted=''"
            )
            conn.commit()
        finally:
            conn.close()
    return {"configured": False}


def set_notify_recipient(username: str, notify_to: str) -> dict:
    """每用户收件邮箱（谁的任务通知发给谁）。"""
    notify_to = str(notify_to or "").strip()
    if not _EMAIL_PATTERN.fullmatch(notify_to):
        raise GymServiceError("收件邮箱格式不正确")
    with mutex("gym", "write", timeout=10):
        conn = connect()
        try:
            # gym_notify_config 的 smtp_* 列是旧按用户配置的遗留结构（NOT NULL），
            # 新模型下发件信息在 gym_smtp_config 全局表，这里仅以空串占位。
            conn.execute(
                "INSERT INTO gym_notify_config (username, smtp_host, smtp_port, smtp_user,"
                " auth_code_encrypted, notify_to, updated_at)"
                " VALUES (?, 'smtp.qq.com', 465, '', '', ?, ?)"
                " ON CONFLICT(username) DO UPDATE SET notify_to=excluded.notify_to,"
                " updated_at=excluded.updated_at",
                (username, notify_to, _now()),
            )
            conn.commit()
        finally:
            conn.close()
    return notify_status(username)


def notify_status(username: str) -> dict:
    smtp = smtp_config_status()
    conn = connect()
    try:
        row = conn.execute(
            "SELECT notify_to, updated_at FROM gym_notify_config WHERE username = ?",
            (username,)).fetchone()
    finally:
        conn.close()
    recipient = row["notify_to"] if row else ""
    return {"smtp": smtp, "recipient": recipient,
            "configured": bool(smtp.get("configured") and recipient)}


def delete_notify_recipient(username: str) -> dict:
    with mutex("gym", "write", timeout=10):
        conn = connect()
        try:
            conn.execute("DELETE FROM gym_notify_config WHERE username = ?", (username,))
            conn.commit()
        finally:
            conn.close()
    return notify_status(username)


def send_mail(
    username: str,
    subject: str,
    body: str,
) -> None:
    """用全局发件配置给该用户的收件邮箱发邮件；未配置/失败抛 GymServiceError。"""
    import smtplib
    from email.header import Header
    from email.mime.text import MIMEText

    smtp = smtp_config_status()
    if not smtp.get("configured"):
        raise GymServiceError("发件 SMTP 尚未在管理后台配置")
    conn = connect()
    try:
        row = conn.execute(
            "SELECT notify_to FROM gym_notify_config WHERE username = ?", (username,)).fetchone()
    finally:
        conn.close()
    recipient = (row["notify_to"] if row else "") or smtp["smtp_user"]  # 未设收件人时发给发件箱自己
    conn = connect()
    try:
        enc = conn.execute(
            "SELECT auth_code_encrypted FROM gym_smtp_config WHERE id = 1").fetchone()
    finally:
        conn.close()
    try:
        auth_code = _fernet().decrypt(enc["auth_code_encrypted"].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise GymServiceError("通知凭据解密失败：主密钥与加密时不一致") from exc
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = str(smtp["smtp_user"])
    msg["To"] = recipient
    msg["Subject"] = Header(subject, "utf-8")
    if int(smtp["smtp_port"]) == 465:
        server = smtplib.SMTP_SSL(str(smtp["smtp_host"]), int(smtp["smtp_port"]), timeout=15)
    else:
        server = smtplib.SMTP(str(smtp["smtp_host"]), int(smtp["smtp_port"]), timeout=15)
        try:
            server.starttls()
        except smtplib.SMTPException:  # noqa: BLE001
            pass
    try:
        server.login(str(smtp["smtp_user"]), auth_code)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass


def send_test_email(username: str) -> dict:
    send_mail(
        username,
        "【InterviewForge】健身房预约邮件预览（测试）",
        _job_result_email_preview(),
    )
    return notify_status(username)


_EMAIL_SLOT_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d\s*[-—–]\s*(?:[01]\d|2[0-3]):[0-5]\d")


def _email_date(value: object) -> str:
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return str(value or "日期未识别")
    weekdays = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
    return f"{parsed:%Y年%m月%d日}（{weekdays[parsed.weekday()]}）"


def _email_slots(values: object) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        return []
    slots = []
    for value in values:
        match = _EMAIL_SLOT_RE.search(str(value))
        if match:
            slot = re.sub(r"\s+", "", match.group(0)).replace("—", "-").replace("–", "-")
            if slot not in slots:
                slots.append(slot)
    return slots


def _gym_email_story(status: str, result: dict) -> tuple[str, str, str, str]:
    """Turn scheduler/executor states into a friendly summary and a safe next step.

    Never put raw exception text, provider responses, or internal status codes in user mail.
    """
    detail = str(result.get("last_attempt_detail") or result.get("detail") or "")
    compact = re.sub(r"\s+", "", detail)
    existing = _email_slots(result.get("existing_bookings"))
    if not existing and any(marker in compact for marker in (
        "当天已存在有效预约", "当天已有有效预约", "每天只能预约", "已预约过", "已有预约",
    )):
        existing = _email_slots(detail)
    pending = _email_slots(result.get("pending_orders"))
    if not pending and any(marker in detail for marker in ("待支付", "未支付订单", "未支付成功")):
        pending = _email_slots(detail)

    if status == "succeeded":
        slot = str(result.get("actual_slot") or "").strip()
        if not _EMAIL_SLOT_RE.fullmatch(slot):
            discovered_slots = _email_slots(detail)
            slot = discovered_slots[0] if discovered_slots else ""
        slot_line = f"已确认时段：{slot}" if _EMAIL_SLOT_RE.fullmatch(slot) else ""
        return (
            "预约成功啦 🎉",
            "好消息！系统已经在南大场馆订单记录中核实到一条有效预约。",
            slot_line,
            "可以按计划前往场馆；如需再次确认，南大订单页面显示的状态为准。",
        )

    if status == "no_slot":
        return (
            "这次暂时没抢到空位",
            "系统在放号后反复检查了你选择的时段，约半小时内都没有等到可预约名额。",
            "本次没有确认生成预约。",
            "可以换一个日期，或下次多选几个备选时段，提高遇到空位的机会。",
        )

    if status == "ambiguous" and any(marker in detail for marker in ("待支付", "未支付订单", "未支付成功")):
        booked = "、".join(pending) if pending else "订单页显示的时段"
        return (
            "发现待确认订单，需要你看一眼",
            f"场馆已经生成了 {booked} 的订单，但目前没有确认它已完成支付。为避免重复下单，系统没有继续提交。",
            "待支付订单可能会在约 5 分钟后自动取消。",
            "请先打开南大场馆订单页查看状态；确认这笔订单已取消或失效后，再决定是否重新预约。",
        )

    if status == "ambiguous" and "金额" in detail and any(
        marker in detail for marker in ("无法确认", "无法识别", "不能确认")
    ):
        return (
            "支付前需要核对金额",
            "最终确认页没有提供可可靠识别的金额信息，系统没有点击支付。",
            "订单可能仍在待支付状态，请先查看南大订单页和金额。",
            "确认订单已取消/失效且没有其他待处理订单后，再解除任务并重新预约。",
        )

    if result.get("needs_manual_check") or "任务执行期间服务中断" in detail:
        return (
            "任务中断，预约结果待核",
            "服务在预约流程中中断，无法判断提交或支付是否已经生效；系统没有自动重跑。",
            "请先核对南大订单，避免重复预约或重复支付。",
            "确认没有有效预约和待支付订单后，再回工具箱点“核对后允许重试”。",
        )

    if status == "ambiguous":
        return (
            "预约结果还不能确认",
            "自动流程没有拿到足以判断成功或失败的订单记录，所以我们不会把它说成已预约成功。",
            "为避免重复下单，本次没有自动重试。",
            "请先到南大场馆订单页核对目标日期和时段；确认没有订单后，再回工具箱点“核对后允许重试”。",
        )

    if existing or any(marker in compact for marker in (
        "当天已存在有效预约", "当天已有有效预约", "每天只能预约", "已预约过", "已有预约",
    )):
        booked = "、".join(existing) if existing else "当天已有时段（请查看南大订单页）"
        return (
            "当天已经有预约，本次已避免重复提交",
            f"我们发现当天已有有效预约：{booked}。按照防重复规则，系统立即停止了本次任务，没有再尝试其他时段。",
            "这表示已有预约被保留，并不代表它被取消或修改。",
            "如果这正是你要的时段，不需要再操作；若不是，请先到南大订单页核实已有预约，再决定后续安排。",
        )

    if "金额" in detail and any(marker in detail for marker in (
        "非 0", "非0", "数值冲突", "无法识别", "无法确认",
    )):
        amount = re.search(r"(?:订单)?金额(?:为|是)\s*([0-9]+(?:\.[0-9]+)?)\s*元", detail)
        amount_note = f"（页面显示 {amount.group(1)} 元）" if amount else ""
        return (
            "金额需要确认，系统已安全停止",
            f"预约页面的金额不是明确的 0 元{amount_note}，或金额信息彼此不一致。为了避免意外扣费，系统没有继续支付。",
            "本次没有由自动流程完成支付。",
            "请先检查南大订单页面显示的金额；只有确认订单为 0 元后，再重新尝试。",
        )

    if "滑块验证未通过" in detail or "验证码" in detail:
        return (
            "验证步骤没有通过，预约未完成",
            "场馆要求完成页面验证，但这次验证没有顺利通过。它不一定代表账号或密码错误。",
            "系统没有确认到预约成功。",
            "稍后可以重新尝试；如果连续遇到同样情况，请先手动登录南大场馆确认账号状态。",
        )

    if any(marker in detail for marker in ("账号或密码不正确", "登录后站点始终未就绪", "登录失败")):
        return (
            "登录环节没有完成",
            "自动预约未能顺利进入场馆页面，因此没有确认到预约结果。",
            "请检查工具箱里保存的南大账号信息，以及账号是否仍可正常登录。",
            "更新凭据后再重新创建任务；如果手动登录也失败，请联系学校场馆平台处理。",
        )

    if "场次页未渲染" in detail or "未渲染出时段" in detail:
        return (
            "预约页面暂时没有正常加载",
            "场馆的日期或时段列表这次没有完整显示，系统无法可靠判断空位，也没有继续盲目提交。",
            "如果已经自动重试多次仍未成功，任务会停止，不会无限运行。",
            "可以稍后重新发起；若页面持续异常，请先手动打开场馆页面确认服务是否正常。",
        )

    if "超时" in detail or "timeout" in detail.lower():
        return (
            "场馆响应较慢，任务没有完成",
            "等待场馆页面返回结果时超出了安全等待时间，系统因此停止了本次流程。",
            "目前不能据此判断预约成功，请先核对订单记录。",
            "确认订单页没有生成待处理订单后，再稍后重试，避免重复提交。",
        )

    if "订单确认页未打开" in detail or "未到达订单确认页" in detail:
        return (
            "场馆没有返回明确的预约确认",
            "提交后没有进入订单确认页面，订单记录也未能证明预约已经成功。",
            "系统没有把这次尝试记作成功。",
            "请先查看南大订单页；如果没有待支付或有效订单，再重新发起预约。",
        )

    return (
        "预约没有完成，需要检查一下",
        "自动预约流程中遇到了无法安全判断的情况。为避免重复下单或误报成功，系统已经停止。",
        "请先到南大订单页确认目标日期是否已有有效或待支付订单。",
        "确认没有未处理订单后，可以稍后重新创建任务；如果问题重复出现，请把工具箱里的任务记录发给管理员。",
    )


def _job_result_email_preview() -> str:
    """Manual test-email content: preview all result narratives without running jobs."""
    examples = (
        ("成功示例", "succeeded", {"actual_slot": "17:00-18:00"}),
        ("当天已有预约（防重复）", "failed", {
            "existing_bookings": ["17:00-18:00"],
            "detail": "当天已存在有效预约（17:00-18:00），本次任务已停止，未尝试其他时段。",
        }),
        ("所选时段没有空位", "no_slot", {"detail": "多次查询均无空位"}),
        ("发现待支付订单", "ambiguous", {
            "detail": "当天存在未支付订单，避免重复下单，请人工确认：17:00-18:00",
        }),
        ("金额异常，安全停止", "failed", {
            "detail": "订单金额为 10.0 元（非 0），按安全规则停止",
        }),
        ("页面验证未通过", "failed", {"detail": "滑块验证未通过"}),
        ("账号登录未完成", "failed", {"detail": "登录后站点始终未就绪"}),
        ("预约页面加载失败且重试耗尽", "failed", {
            "retry_exhausted": True,
            "attempt": JOB_MAX_ATTEMPTS,
            "detail": "已连续尝试 3 次，停止自动重试。",
            "last_attempt_detail": "异常：场次页未渲染出时段表格/日期条",
        }),
        ("订单结果暂时无法核实", "ambiguous", {
            "detail": "订单页未找到匹配的已支付记录，请人工核对",
        }),
    )
    lines = [
        "你好！这是一封手动触发的邮件文案预览 👋",
        "",
        "下面列出预约助手可能发送的结果类型。全部是模拟示例，不会创建预约，也不代表真实任务失败。",
        "",
        f"示例日期：{_email_date('2026-10-18')} · 场馆：南大健身房（一层）",
        "示例时段：17:00-18:00、18:00-19:00",
        "",
        "─" * 32,
    ]
    for label, status, result in examples:
        title, summary, note, next_step = _gym_email_story(status, result)
        lines.extend((
            "",
            f"【{label}】",
            title,
            summary,
        ))
        if note:
            lines.append(note)
        if result.get("retry_exhausted"):
            lines.append(f"自动重试：已尝试 {result['attempt']} 次，暂时停止继续重试。")
        lines.extend((f"建议：{next_step}", "", "─" * 32))
    lines.extend(("", "这封预览由你手动触发；真实预约通知仍只发送到工具箱中配置的收件邮箱。"))
    return "\n".join(lines)


def notify_job_result(job: dict, status: str, result: dict) -> None:
    """Send a readable, actionable result mail without exposing executor internals."""
    title, summary, note, next_step = _gym_email_story(status, result)
    slots = _email_slots(job.get("slots"))
    actual_slot = str(result.get("actual_slot") or "").strip()
    venue = {"129": "南大健身房（一层）", "162": "南大健身房（负一层）"}.get(
        str(job.get("venue") or "129"), "南大健身房")
    retry_note = ""
    if result.get("retry_exhausted"):
        attempts = result.get("attempt", JOB_MAX_ATTEMPTS)
        retry_note = f"\n自动重试：已尝试 {attempts} 次，暂时停止继续重试。"
    slot_lines = []
    if slots:
        slot_lines.append(f"你选择的时段：{'、'.join(slots)}")
    if actual_slot and _EMAIL_SLOT_RE.fullmatch(actual_slot):
        label = "已确认预约时段" if status == "succeeded" else "本次处理时段"
        if not any(actual_slot in line for line in slot_lines):
            slot_lines.append(f"{label}：{actual_slot}")
    if note:
        slot_lines.append(note)
    subject_label = {
        "succeeded": "预约成功 🎉",
        "no_slot": "暂时没有空位",
        "ambiguous": "需要确认订单状态",
        "failed": title,
    }.get(status, "预约任务结果")
    body = (
        "你好，预约结果回来啦 👋\n\n"
        f"{title}\n{summary}\n\n"
        f"📅 预约日期：{_email_date(job.get('target_date'))}\n"
        f"🏟️ 场馆：{venue}\n"
        + ("\n".join(slot_lines) + "\n" if slot_lines else "")
        + retry_note
        + f"\n接下来：{next_step}\n\n"
        f"任务编号：#{job.get('id', '—')}（可在 InterviewForge 工具箱查看记录）\n"
        "预约状态以南大场馆订单页面为准。\n\n"
        "祝你锻炼顺利！\nInterviewForge 健身房预约助手"
    )
    try:
        send_mail(
            str(job["created_by"]),
            f"【InterviewForge】健身房预约：{subject_label}｜{_email_date(job.get('target_date'))}",
            body,
        )
        log.info("任务 #%s 结果邮件已发送至 %s", job["id"], job["created_by"])
    except GymServiceError as exc:
        log.info("任务 #%s 未发送邮件：%s", job["id"], exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("任务 #%s 邮件发送失败：%s", job["id"], exc)


def tools_python() -> str:
    """执行工具箱子进程用哪个解释器。

    工具箱依赖（playwright/ddddocr/paddle）和站点服务依赖是两套清单：线上把两者装在
    同一个 .venv 里，所以默认用当前解释器就够。若部署时把工具箱单独放在一个环境里
    （本机就是这样：服务跑全局 Python，工具箱在 .venv-tools），则优先用它——
    先看 GYM_TOOLS_PYTHON，再看仓库下的 .venv-tools。
    """
    override = os.environ.get("GYM_TOOLS_PYTHON", "").strip()
    if override:
        return override
    for relative in ("Scripts/python.exe", "bin/python"):
        candidate = ROOT / ".venv-tools" / relative
        if candidate.exists():
            return str(candidate)
    return sys.executable


def verify_credentials(account: str, password: str) -> dict:
    """真实验证南大凭据：子进程跑一次登录（含滑块）。返回 {status, detail}。

    status: ok / bad_credentials / captcha_failed / error。"""
    import time as _time
    run_dir = GYM_LOG_DIR / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(_time.time() * 1000)
    result_path = run_dir / f"cred-check-{stamp}.json"
    log_path = run_dir / f"cred-check-{stamp}.log"
    cmd = [tools_python(), "-m", "interview_forge.services.gym_automation",
           "--check-login", "--json-result", str(result_path), "--credentials-stdin"]
    if os.environ.get("GYM_HEADLESS", "").strip() == "1":
        cmd.append("--headless")
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    with log_path.open("w", encoding="utf-8") as log_file:
        subprocess.run(
            cmd, cwd=ROOT, env=env, stdout=log_file, stderr=subprocess.STDOUT,
            timeout=180, input=json.dumps({"account": account, "password": password}).encode("utf-8"),
        )
    if result_path.exists():
        try:
            return json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {"status": "error", "detail": "验证进程无输出"}


# ------------------------------------------------------------- CRUD（给路由层）

class GymServiceError(Exception):
    """用户可见的排程错误（参数非法/状态不允许）。"""


def create_job(target_date: str, slots: list[str], created_by: str, venue: str = "129") -> dict:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target_date or ""):
        raise GymServiceError("日期格式应为 YYYY-MM-DD")
    try:
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise GymServiceError("日期不存在") from exc
    today = datetime.now(SHANGHAI).date()
    if date_obj < today:
        raise GymServiceError("不能预约过去的日期")
    if date_obj > today + timedelta(days=60):
        raise GymServiceError("最多预排 60 天以内")
    cleaned: list[str] = []
    for s in slots or []:
        s = str(s).strip()
        if not s:
            continue
        if not SLOT_PATTERN.fullmatch(s):
            raise GymServiceError(f"时段格式应为 HH:MM-HH:MM：{s}")
        start, end = s.split("-")
        if start >= end:
            raise GymServiceError(f"时段结束时间必须晚于开始时间：{s}")
        if s not in cleaned:
            cleaned.append(s)
    if not cleaned:
        cleaned = ["17:00-18:00", "16:00-17:00"]
    if len(cleaned) > MAX_SLOTS_PER_JOB:
        raise GymServiceError(f"时段优先级最多 {MAX_SLOTS_PER_JOB} 个")
    venue = str(venue or "129").strip() or "129"
    if venue not in SUPPORTED_VENUES:
        raise GymServiceError("请选择支持的一楼或负一楼健身房")
    if not credentials_status(created_by)["configured"]:
        raise GymServiceError("请先在工具箱中保存南大账号密码，再创建自动预约")

    with mutex("gym", "write", timeout=10):
        conn = connect()
        try:
            dup = conn.execute(
                "SELECT id, status FROM gym_jobs WHERE target_date = ? AND venue = ? "
                "AND created_by = ? AND status IN ('pending','running','ambiguous')",
                (target_date, venue, created_by),
            ).fetchone()
            if dup:
                if dup["status"] == "ambiguous":
                    raise GymServiceError(
                        f"你已有 {target_date} 的结果待核任务（#{dup['id']}）。"
                        "请先核对南大订单，并确认没有有效或待支付订单后再重新排程。"
                    )
                raise GymServiceError(f"你已有 {target_date} 的待执行自动预约任务（#{dup['id']}）")
            cur = conn.execute(
                "INSERT INTO gym_jobs (target_date, slots, venue, status, created_by,"
                " created_at, updated_at, result) VALUES (?, ?, ?, 'pending', ?, ?, ?, '{}')",
                (target_date, json.dumps(cleaned, ensure_ascii=False), venue,
                 created_by, _now(), _now()),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM gym_jobs WHERE id = ?", (cur.lastrowid,)).fetchone()
            return _row_to_dict(row)
        finally:
            conn.close()


def list_jobs(limit: int = 100, created_by: str | None = None) -> list[dict]:
    """任务列表。传 created_by 时只返回该用户自己的任务——用户之间互不可见。"""
    conn = connect()
    try:
        if created_by is None:
            rows = conn.execute(
                "SELECT * FROM gym_jobs ORDER BY target_date DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM gym_jobs WHERE created_by = ?"
                " ORDER BY target_date DESC, id DESC LIMIT ?", (created_by, limit)
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def cancel_job(job_id: int, username: str) -> dict:
    """取消自动排程：仅允许取消 pending；不触达南大的任何预约/订单。"""
    with mutex("gym", "write", timeout=10):
        conn = connect()
        try:
            row = conn.execute("SELECT * FROM gym_jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise GymServiceError(f"任务 #{job_id} 不存在")
            if row["created_by"] != username:
                raise GymServiceError(f"任务 #{job_id} 不属于当前用户，无法取消")
            if row["status"] != "pending":
                raise GymServiceError(f"任务 #{job_id} 状态为 {row['status']}，不能取消")
            conn.execute(
                "UPDATE gym_jobs SET status='cancelled', updated_at=?,"
                " result=json_insert(result, '$.cancelled_by', ?) WHERE id=?",
                (_now(), username, job_id),
            )
            conn.commit()
            fresh = conn.execute("SELECT * FROM gym_jobs WHERE id = ?", (job_id,)).fetchone()
            return _row_to_dict(fresh)
        finally:
            conn.close()


def resolve_job_for_retry(job_id: int, username: str, confirmed_no_order: bool) -> dict:
    """管理员核对南大订单明确无有效/待支付订单后，解除 ambiguous 日期占用。"""
    if confirmed_no_order is not True:
        raise GymServiceError("请先核对南大订单，并明确确认没有有效或待支付订单")
    with mutex("gym", "write", timeout=10):
        conn = connect()
        try:
            row = conn.execute("SELECT * FROM gym_jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise GymServiceError(f"任务 #{job_id} 不存在")
            if row["created_by"] != username:
                raise GymServiceError(f"任务 #{job_id} 不属于当前用户，无法核对")
            if row["status"] != "ambiguous":
                raise GymServiceError(f"任务 #{job_id} 状态为 {row['status']}，无需结果核对")
            result = _row_to_dict(row).get("result") or {}
            result["previous_detail"] = result.get("detail", "")
            result["detail"] = (
                f"管理员 {username} 已核对南大订单，确认没有有效或待支付订单。"
                f"原任务情况：{result['previous_detail']}"
            )
            result["resolved_by"] = username
            result["resolved_at"] = _now()
            result["needs_manual_check"] = False
            cur = conn.execute(
                "UPDATE gym_jobs SET status='failed', updated_at=?, result=? "
                "WHERE id=? AND status='ambiguous'",
                (_now(), json.dumps(result, ensure_ascii=False), job_id),
            )
            if cur.rowcount != 1:
                raise GymServiceError(f"任务 #{job_id} 状态已变化，请刷新后重试")
            conn.commit()
            fresh = conn.execute("SELECT * FROM gym_jobs WHERE id = ?", (job_id,)).fetchone()
            return _row_to_dict(fresh)
        finally:
            conn.close()


# ------------------------------------------------------------- 环境自检（给 UI）

def environment_check() -> dict:
    """执行器环境自检：依赖、Chromium、凭据。供工具页状态卡展示。"""
    check: dict = {"ok": False, "items": []}

    def add(name: str, ok: bool, detail: str = ""):
        check["items"].append({"name": name, "ok": ok, "detail": detail})

    for mod, name in (("playwright", "Playwright"), ("ddddocr", "ddddocr")):
        try:
            __import__(mod)
            add(name, True)
        except Exception as exc:  # noqa: BLE001
            add(name, False, str(exc)[:120])
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            path = p.chromium.executable_path
            ok = Path(path).exists()
            add("Chromium", ok, path if ok else "未安装，执行 python -m playwright install chromium")
    except Exception as exc:  # noqa: BLE001
        add("Chromium", False, str(exc)[:120])
    required_ok = all(i["ok"] for i in check["items"])
    try:
        from interview_forge.services.gym_automation import deepseek_key

        add("DeepSeek 认字凭据", bool(deepseek_key()),
            "可选，仅 legacy 策略使用；默认候选分数匹配不调用 API")
    except Exception:  # noqa: BLE001
        add("DeepSeek 认字凭据", False, "")
    check["ok"] = required_ok
    return check


# ------------------------------------------------------------- 调度线程

_scheduler_stop = threading.Event()
_scheduler_thread: threading.Thread | None = None


def _claim_due_jobs(today_iso: str) -> list[dict]:
    """原子领取今天到点的 pending 任务（08:00 之后），多 worker 下只领一次。
    已错过日期的 pending 任务标记失败并同样发通知。"""
    _recover_stale_running_jobs()
    hh, mm = RUN_EARLIEST
    now = datetime.now(SHANGHAI)
    if (now.hour, now.minute) < (hh, mm):
        return []
    claimed: list[dict] = []
    expired: list[dict] = []
    with mutex("gym", "scheduler", timeout=15):
        conn = connect()
        try:
            rows = conn.execute(
                # 先建先跑：按创建时间领取，串行执行时顺序就是排队顺序。
                "SELECT * FROM gym_jobs WHERE status='pending' ORDER BY created_at, id"
            ).fetchall()
            for row in rows:
                if row["target_date"] < today_iso:
                    conn.execute(
                        "UPDATE gym_jobs SET status='failed', updated_at=?,"
                        " result=? WHERE id=? AND status='pending'",
                        (_now(), json.dumps({"detail": "已错过执行日期（当天未运行）"}, ensure_ascii=False), row["id"]),
                    )
                    expired.append(_row_to_dict(row))
                    continue
                if row["target_date"] != today_iso:
                    continue
                result = _row_to_dict(row).get("result") or {}
                if not _retry_is_due(result, now):
                    continue
                cur = conn.execute(
                    "UPDATE gym_jobs SET status='running', updated_at=?"
                    " WHERE id=? AND status='pending'",
                    (_now(), row["id"]),
                )
                if cur.rowcount == 1:
                    claimed.append(_row_to_dict(row))
            conn.commit()
        finally:
            conn.close()
    for row in expired:
        notify_job_result(row, "failed", {"detail": "已错过执行日期（当天站点未运行），自动预约已失效"})
    return claimed


def _recover_stale_running_jobs(now: datetime | None = None) -> int:
    """把执行进程中断后遗留的 running 任务转为 ambiguous，绝不盲目重跑。

    子进程的硬超时为 35 分钟；再留 5 分钟收尾余量。任务结果未知时必须由
    用户核对南大订单，不能重新预约，以免进程退出前已经完成提交/支付。
    """
    now = now or datetime.now(SHANGHAI)
    cutoff = now - timedelta(
        seconds=JOB_SUBPROCESS_TIMEOUT_SECONDS + JOB_RUNNING_STALE_GRACE_SECONDS
    )
    recovered: list[dict] = []
    with mutex("gym", "scheduler", timeout=15):
        conn = connect()
        try:
            rows = conn.execute(
                "SELECT * FROM gym_jobs WHERE status='running' AND updated_at <= ?",
                (cutoff.isoformat(timespec="seconds"),),
            ).fetchall()
            for row in rows:
                result = {
                    "detail": (
                        "任务执行期间服务中断，无法确认是否已提交预约或完成支付。"
                        "系统已停止自动重试，请先核对南大订单。"
                    ),
                    "needs_manual_check": True,
                    "recovered_from_running": True,
                    "interrupted_at": now.isoformat(timespec="seconds"),
                }
                cur = conn.execute(
                    "UPDATE gym_jobs SET status='ambiguous', updated_at=?, result=? "
                    "WHERE id=? AND status='running' AND updated_at=?",
                    (now.isoformat(timespec="seconds"),
                     json.dumps(result, ensure_ascii=False), row["id"], row["updated_at"]),
                )
                if cur.rowcount == 1:
                    recovered.append(_row_to_dict(row))
            conn.commit()
        finally:
            conn.close()
    for old_row in recovered:
        notify_job_result(old_row, "ambiguous", {
            "detail": (
                "任务执行期间服务中断，无法确认是否已提交预约或完成支付。"
                "系统已停止自动重试，请先核对南大订单。"
            ),
            "needs_manual_check": True,
        })
    return len(recovered)


def _finish_job(job_id: int, status: str, result: dict) -> None:
    conn = connect()
    try:
        conn.execute(
            "UPDATE gym_jobs SET status=?, updated_at=?, result=? WHERE id=?",
            (status, _now(), json.dumps(result, ensure_ascii=False), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def _retry_is_due(result: dict, now: datetime) -> bool:
    retry_after = result.get("retry_after")
    if not retry_after:
        return True
    try:
        retry_at = datetime.fromisoformat(str(retry_after))
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=SHANGHAI)
        return retry_at <= now
    except ValueError:
        return True


def _defer_transient_retry(job: dict, status: str, result: dict) -> bool:
    """瞬时故障延迟重试；只有执行器明确标记可重试且结果确定未下单才进入队列。"""
    if status != "failed" or result.get("retryable") is not True:
        return False
    previous = job.get("result") or {}
    try:
        attempt = max(1, int(previous.get("attempt", 1)))
    except (TypeError, ValueError):
        attempt = 1
    result["last_attempt_detail"] = result.get("detail", "")
    result["attempt"] = attempt
    if attempt >= JOB_MAX_ATTEMPTS:
        result["retryable"] = False
        result["retry_exhausted"] = True
        result["detail"] = (f"已连续尝试 {JOB_MAX_ATTEMPTS} 次，停止自动重试。"
                            f"最后结果：{result.get('detail', '')}")
        return False

    delay = JOB_RETRY_DELAYS_SECONDS[min(attempt - 1, len(JOB_RETRY_DELAYS_SECONDS) - 1)]
    retry_at = datetime.now(SHANGHAI) + timedelta(seconds=delay)
    result["attempt"] = attempt + 1
    result["retry_after"] = retry_at.isoformat(timespec="seconds")
    result["detail"] = (f"第 {attempt} 次遇到可恢复故障，将于 {retry_at:%H:%M} 自动重试。"
                        f"最近结果：{result.get('last_attempt_detail', '')}")
    _finish_job(int(job["id"]), "pending", result)
    log.warning("任务 #%s 第 %d 次失败，将于 %s 重试",
                job["id"], attempt, retry_at.isoformat(timespec="minutes"))
    return True


def _run_job_subprocess(job: dict) -> tuple[str, dict]:
    """子进程执行一次预约自动化，返回 (状态, 结果)。

    凭据经 stdin 传入（JSON），不落在命令行参数、环境变量或日志里。
    """
    run_dir = GYM_LOG_DIR / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / f"job-{job['id']}.json"
    attempt = (job.get("result") or {}).get("attempt", 1)
    log_path = run_dir / f"job-{job['id']}-attempt-{attempt}.log"
    # 同一任务会重试；删除上轮结果文件，避免本次进程尚未写结果时误读旧 JSON。
    result_path.unlink(missing_ok=True)
    account, password = _load_credentials_decrypted(str(job["created_by"]))
    stdin_payload = json.dumps({"account": account, "password": password}, ensure_ascii=False)
    cmd = [
        tools_python(), "-m", "interview_forge.services.gym_automation",
        "--venue", str(job.get("venue") or "129"),
        "--date", str(job["target_date"]),
        "--slots", ",".join(job["slots"]),
        "--json-result", str(result_path),
        "--credentials-stdin",
    ]
    if os.environ.get("GYM_HEADLESS", "").strip() == "1":
        cmd.append("--headless")
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    log.info("执行任务 #%s（创建者 %s）", job["id"], job["created_by"])
    with log_path.open("w", encoding="utf-8") as log_file:
        proc = subprocess.run(
            cmd, cwd=ROOT, env=env, stdout=log_file,
            stderr=subprocess.STDOUT, timeout=JOB_SUBPROCESS_TIMEOUT_SECONDS,
            input=stdin_payload.encode("utf-8"),
        )
    result = {"detail": f"退出码 {proc.returncode}"}
    if result_path.exists():
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    status_by_code = {0: "succeeded", 2: "no_slot", 3: "ambiguous"}
    status = status_by_code.get(proc.returncode, "failed")
    if result.get("status") in {"succeeded", "no_slot", "ambiguous", "failed"}:
        status = result["status"]
    return status, result


def _run_due_jobs(today_iso: str) -> int:
    """领取到点的任务并逐个执行；返回本轮执行了几个。调用方须持有执行锁。"""
    executed = 0
    for job in _claim_due_jobs(today_iso):
        executed += 1
        log.info("执行自动预约任务 #%s（%s %s）", job["id"], job["target_date"], job["slots"])
        try:
            status, result = _run_job_subprocess(job)
        except subprocess.TimeoutExpired:
            timeout_minutes = JOB_SUBPROCESS_TIMEOUT_SECONDS // 60
            status, result = "failed", {"detail": f"执行超时（{timeout_minutes} 分钟）"}
        except Exception as exc:  # noqa: BLE001
            status, result = "failed", {"detail": f"执行异常：{exc}"}
        if _defer_transient_retry(job, status, result):
            continue
        _finish_job(job["id"], status, result)
        notify_job_result(job, status, result)
        log.info("任务 #%s 完成：%s %s", job["id"], status, result.get("detail", "")[:120])
    return executed


def _run_scheduled_batch(today_iso: str) -> int:
    """串行跑一轮到点任务；已有任务在执行时返回 -1（本轮跳过）。

    预约子进程彼此串行：多个 worker 共用一把跨进程执行锁，同一时刻只允许一个任务
    在跑。几个任务同时登录、同时加载场馆页会把站点拖慢到 8 秒页面超时——2026-10-14
    三个用户的任务同时在 08:00 出发，前两次尝试全部因此失败。任务按创建时间领取，
    先建先跑；拿不到锁的 worker 直接跳过本轮，下一轮再试。
    """
    acquired = False
    try:
        with mutex("gym", "executor", timeout=0.1):
            acquired = True
            return _run_due_jobs(today_iso)
    except TimeoutError:
        if acquired:            # 锁已拿到，是执行过程自身超时，交给外层记录
            raise
        log.info("已有预约任务在执行，本轮跳过")
        return -1


def _scheduler_loop() -> None:
    log.info("健身房预约调度线程已启动")
    while not _scheduler_stop.is_set():
        try:
            today_iso = datetime.now(SHANGHAI).date().isoformat()
            _run_scheduled_batch(today_iso)
        except Exception:  # noqa: BLE001
            log.exception("调度循环异常")
        _scheduler_stop.wait(30)
    log.info("健身房预约调度线程已停止")


def start_gym_scheduler() -> None:
    """在 FastAPI lifespan 启动时调用；幂等。"""
    global _scheduler_thread
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return
    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop, name="gym-scheduler", daemon=True)
    _scheduler_thread.start()


def stop_gym_scheduler() -> None:
    _scheduler_stop.set()
