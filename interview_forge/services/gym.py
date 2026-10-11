"""工具箱·健身房自动预约：每用户加密凭据 + 排程持久化 + 到点执行调度。

设计要点
========
* 站点只支持约当天，名额在当天 08:00 放出；因此“任选日期”的语义是
  预排一个任务，调度线程在目标日 07:58 后自动执行浏览器自动化
  （gym_automation，子进程，Playwright 真机操作）。
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from interview_forge.core.paths import DATA_DIR, GYM_DB_PATH, GYM_LOG_DIR, ROOT
from interview_forge.runtime.shared import mutex

log = logging.getLogger(__name__)

SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")
# 站点名额 08:00 放出，略提前启动以完成登录/滑块等前置步骤
RUN_EARLIEST = (7, 58)
JOB_SUBPROCESS_TIMEOUT_SECONDS = 25 * 60
MAX_SLOTS_PER_JOB = 6
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


def save_credentials(username: str, account: str, password: str) -> dict:
    account = str(account or "").strip()
    password = str(password or "")
    if not re.fullmatch(r"[A-Za-z0-9]{6,20}", account):
        raise GymServiceError("账号应为 6-20 位数字或字母（学号/工号）")
    if len(password) < 6 or len(password) > 64:
        raise GymServiceError("密码长度应为 6-64 位")
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
    return credentials_status(username)


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
        if s not in cleaned:
            cleaned.append(s)
    if not cleaned:
        cleaned = ["17:00-18:00", "16:00-17:00"]
    if len(cleaned) > MAX_SLOTS_PER_JOB:
        raise GymServiceError(f"时段优先级最多 {MAX_SLOTS_PER_JOB} 个")
    venue = str(venue or "129").strip() or "129"
    if not venue.isdigit():
        raise GymServiceError("场馆 id 应为数字")
    if not credentials_status(created_by)["configured"]:
        raise GymServiceError("请先在工具箱中保存南大账号密码，再创建自动预约")

    with mutex("gym", "write", timeout=10):
        conn = connect()
        try:
            dup = conn.execute(
                "SELECT id FROM gym_jobs WHERE target_date = ? AND status IN ('pending','running')",
                (target_date,),
            ).fetchone()
            if dup:
                raise GymServiceError(f"{target_date} 已有待执行的自动预约任务（#{dup['id']}）")
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


def list_jobs(limit: int = 100) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM gym_jobs ORDER BY target_date DESC, id DESC LIMIT ?", (limit,)
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
    try:
        import interview_forge.services.gym_automation as auto

        cred = auto.credentials_file()
        add("凭据文件", cred.exists(), str(cred))
    except Exception as exc:  # noqa: BLE001
        add("凭据文件", False, str(exc)[:120])
    try:
        from interview_forge.services.gym_automation import deepseek_key

        add("DeepSeek 认字凭据", bool(deepseek_key()), "未配置时验证码仅靠本地识别")
    except Exception:  # noqa: BLE001
        add("DeepSeek 认字凭据", False, "")
    check["ok"] = all(i["ok"] for i in check["items"])
    return check


# ------------------------------------------------------------- 调度线程

_scheduler_stop = threading.Event()
_scheduler_thread: threading.Thread | None = None


def _claim_due_jobs(today_iso: str) -> list[dict]:
    """原子领取今天到点的 pending 任务（07:58 之后），多 worker 下只领一次。"""
    hh, mm = RUN_EARLIEST
    now = datetime.now(SHANGHAI)
    if (now.hour, now.minute) < (hh, mm):
        return []
    claimed: list[dict] = []
    with mutex("gym", "scheduler", timeout=15):
        conn = connect()
        try:
            rows = conn.execute(
                "SELECT * FROM gym_jobs WHERE status='pending' ORDER BY id"
            ).fetchall()
            for row in rows:
                if row["target_date"] < today_iso:
                    conn.execute(
                        "UPDATE gym_jobs SET status='failed', updated_at=?,"
                        " result=? WHERE id=? AND status='pending'",
                        (_now(), json.dumps({"detail": "已错过执行日期"}, ensure_ascii=False), row["id"]),
                    )
                    continue
                if row["target_date"] != today_iso:
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
    return claimed


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


def _run_job_subprocess(job: dict) -> tuple[str, dict]:
    """子进程执行一次预约自动化，返回 (状态, 结果)。

    凭据经 stdin 传入（JSON），不落在命令行参数、环境变量或日志里。
    """
    run_dir = GYM_LOG_DIR / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / f"job-{job['id']}.json"
    log_path = run_dir / f"job-{job['id']}.log"
    account, password = _load_credentials_decrypted(str(job["created_by"]))
    stdin_payload = json.dumps({"account": account, "password": password}, ensure_ascii=False)
    cmd = [
        sys.executable, "-m", "interview_forge.services.gym_automation",
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


def _scheduler_loop() -> None:
    log.info("健身房预约调度线程已启动")
    while not _scheduler_stop.is_set():
        try:
            today_iso = datetime.now(SHANGHAI).date().isoformat()
            for job in _claim_due_jobs(today_iso):
                log.info("执行自动预约任务 #%s（%s %s）",
                         job["id"], job["target_date"], job["slots"])
                try:
                    status, result = _run_job_subprocess(job)
                except subprocess.TimeoutExpired:
                    status, result = "failed", {"detail": "执行超时（25 分钟）"}
                except Exception as exc:  # noqa: BLE001
                    status, result = "failed", {"detail": f"执行异常：{exc}"}
                _finish_job(job["id"], status, result)
                log.info("任务 #%s 完成：%s %s", job["id"], status,
                         result.get("detail", "")[:120])
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
