"""AI quota and per-user AI database helpers.

This module owns the existing quota window, reservation and consumption
semantics.  The AI coach facade re-exports these symbols for compatibility.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from interview_forge.ai.errors import AIServiceError
from interview_forge.db.ai_schema import ensure_ai_schema

_SCHEMA_DONE: set[str] = set()
_SCHEMA_LOCK = threading.Lock()

AI_DAILY_LIMIT = 3
try:
    AI_CHAT_DAILY_LIMIT = max(0, min(int(os.environ.get("AI_CHAT_DAILY_LIMIT", "30")), 100))
except (TypeError, ValueError):
    AI_CHAT_DAILY_LIMIT = 30
AI_QUOTA_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _validated_daily_limit(daily_limit: int | None) -> int:
    value = AI_DAILY_LIMIT if daily_limit is None else daily_limit
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise ValueError("每日 AI 分析上限必须是 0~100 的整数")
    return value

def _now_iso() -> str:
    # Quota rows are displayed and reset in the application's business
    # timezone, independent of the VPS host timezone.
    return datetime.now(timezone.utc).astimezone(AI_QUOTA_TIMEZONE).isoformat(timespec="seconds")


def _today_iso() -> str:
    return datetime.now(timezone.utc).astimezone(AI_QUOTA_TIMEZONE).date().isoformat()


def _quota_window(now: datetime | None = None) -> tuple[str, str]:
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    local = instant.astimezone(AI_QUOTA_TIMEZONE)
    reset_local = datetime.combine(
        local.date() + timedelta(days=1), datetime.min.time(), tzinfo=AI_QUOTA_TIMEZONE
    )
    return local.date().isoformat(), reset_local.isoformat(timespec="seconds")


def _quota_from_connection(
    connection: sqlite3.Connection,
    *,
    role: str = "user",
    daily_limit: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    day_key, reset_at = _quota_window(now)
    if role == "admin":
        return {"limit": None, "used": 0, "remaining": None, "reset_at": reset_at}
    limit = _validated_daily_limit(daily_limit)
    row = connection.execute(
        "SELECT used, reserved, reset_offset FROM ai_daily_quota WHERE day_key = ?", (day_key,)
    ).fetchone()
    used = int(row["used"]) if row is not None else 0
    reserved = int(row["reserved"]) if row is not None else 0
    reset_offset = int(row["reset_offset"]) if row is not None else 0
    chargeable_used = max(0, used - reset_offset)
    return {
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - chargeable_used - reserved),
        "reset_at": reset_at,
    }


def get_ai_quota(
    db_path: Path, role: str = "user", *, daily_limit: int | None = None,
    now: datetime | None = None
) -> dict[str, Any]:
    if not Path(db_path).is_file():
        day_key, reset_at = _quota_window(now)
        if role == "admin":
            return {"limit": None, "used": 0, "remaining": None, "reset_at": reset_at}
        limit = _validated_daily_limit(daily_limit)
        return {"limit": limit, "used": 0, "remaining": limit, "reset_at": reset_at}
    with closing(_open_ai_db(db_path)) as connection:
        return _quota_from_connection(connection, role=role, daily_limit=daily_limit, now=now)


def consume_chat_quota(
    db_path: Path,
    role: str = "user",
    *,
    daily_limit: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Atomically count one chat request without sharing analysis quota rows."""
    if role == "admin":
        return None
    limit = AI_CHAT_DAILY_LIMIT if daily_limit is None else _validated_daily_limit(daily_limit)
    day_key, reset_at = _quota_window(now)
    with closing(_open_ai_db(db_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT OR IGNORE INTO ai_chat_daily_quota(day_key, used, updated_at) VALUES (?, 0, ?)",
            (day_key, _now_iso()),
        )
        cursor = connection.execute(
            "UPDATE ai_chat_daily_quota SET used = used + 1, updated_at = ? "
            "WHERE day_key = ? AND used < ?",
            (_now_iso(), day_key, limit),
        )
        row = connection.execute(
            "SELECT used FROM ai_chat_daily_quota WHERE day_key = ?", (day_key,)
        ).fetchone()
        if cursor.rowcount != 1:
            connection.rollback()
            quota = {
                "limit": limit,
                "used": int(row["used"] if row is not None else 0),
                "remaining": 0,
                "reset_at": reset_at,
            }
            raise AIServiceError(
                "chat_quota", "今日 AI 对话次数已用完，请明天再试。",
                status=HTTPStatus.TOO_MANY_REQUESTS, details={"quota": quota},
            )
        connection.commit()
        used = int(row["used"] if row is not None else 0)
    return {"limit": limit, "used": used, "remaining": max(0, limit - used), "reset_at": reset_at}


def _reserve_ai_quota(
    connection: sqlite3.Connection, task_id: str, *, daily_limit: int | None = None,
    now: datetime | None = None
) -> dict[str, Any]:
    limit = _validated_daily_limit(daily_limit)
    day_key, _ = _quota_window(now)
    connection.execute(
        "INSERT OR IGNORE INTO ai_daily_quota(day_key, used, reserved, updated_at) VALUES (?, 0, 0, ?)",
        (day_key, _now_iso()),
    )
    cursor = connection.execute(
        """UPDATE ai_daily_quota SET reserved = reserved + 1, updated_at = ?
           WHERE day_key = ? AND MAX(0, used - reset_offset) + reserved < ?""",
        (_now_iso(), day_key, limit),
    )
    if cursor.rowcount != 1:
        quota = _quota_from_connection(connection, daily_limit=limit, now=now)
        raise AIServiceError(
            "quota", "今天的一键分析次数已用完，请明天再试。",
            status=HTTPStatus.TOO_MANY_REQUESTS, details={"quota": quota},
        )
    connection.execute(
        "UPDATE ai_tasks SET quota_day = ?, quota_state = 'reserved', quota_limit = ? WHERE task_id = ?",
        (day_key, limit, task_id),
    )
    return _quota_from_connection(connection, daily_limit=limit, now=now)


def _release_ai_quota_reservation(connection: sqlite3.Connection, task_id: str) -> None:
    row = connection.execute(
        "SELECT quota_day, quota_state FROM ai_tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    if row is None or str(row["quota_state"]) != "reserved":
        return
    connection.execute(
        "UPDATE ai_daily_quota SET reserved = MAX(0, reserved - 1), updated_at = ? WHERE day_key = ?",
        (_now_iso(), row["quota_day"]),
    )
    connection.execute(
        "UPDATE ai_tasks SET quota_state = 'released' WHERE task_id = ? AND quota_state = 'reserved'",
        (task_id,),
    )


def _consume_ai_quota(connection: sqlite3.Connection, task_id: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT quota_day, quota_state, quota_limit FROM ai_tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    if row is None or str(row["quota_state"]) != "reserved":
        return _quota_from_connection(connection)
    limit = _validated_daily_limit(row["quota_limit"])
    current_day, _ = _quota_window()
    reserved_day = str(row["quota_day"] or "")
    if reserved_day:
        connection.execute(
            "UPDATE ai_daily_quota SET reserved = MAX(0, reserved - 1), updated_at = ? WHERE day_key = ?",
            (_now_iso(), reserved_day),
        )
    connection.execute(
        "INSERT OR IGNORE INTO ai_daily_quota(day_key, used, reserved, updated_at) VALUES (?, 0, 0, ?)",
        (current_day, _now_iso()),
    )
    cursor = connection.execute(
        "UPDATE ai_daily_quota SET used = used + 1, updated_at = ? "
        "WHERE day_key = ? AND MAX(0, used - reset_offset) < ?",
        (_now_iso(), current_day, limit),
    )
    if cursor.rowcount != 1:
        connection.execute(
            "UPDATE ai_tasks SET quota_state = 'released', quota_day = ? WHERE task_id = ?",
            (current_day, task_id),
        )
        raise AIServiceError(
            "quota", "今天的一键分析次数已用完，请明天再试。",
            status=HTTPStatus.TOO_MANY_REQUESTS,
            details={"quota": _quota_from_connection(connection, daily_limit=limit)},
        )
    connection.execute(
        "UPDATE ai_tasks SET quota_state = 'consumed', quota_day = ? WHERE task_id = ?",
        (current_day, task_id),
    )
    return _quota_from_connection(connection, daily_limit=limit)


def reset_ai_quota(
    db_path: Path, *, daily_limit: int | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Restore today's allowance without rewriting the factual used counter."""
    day_key, _ = _quota_window(now)
    with closing(_open_ai_db(db_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        before = _quota_from_connection(connection, daily_limit=daily_limit, now=now)
        before_row = connection.execute(
            "SELECT reset_offset FROM ai_daily_quota WHERE day_key = ?", (day_key,)
        ).fetchone()
        connection.execute(
            """INSERT INTO ai_daily_quota(day_key, used, reserved, reset_offset, updated_at)
               VALUES (?, 0, 0, 0, ?)
               ON CONFLICT(day_key) DO UPDATE SET
                   reset_offset = ai_daily_quota.used,
                   updated_at = excluded.updated_at""",
            (day_key, _now_iso()),
        )
        connection.execute("COMMIT")
    return {
        "before_used": before["used"],
        "before_reset_offset": int(before_row["reset_offset"]) if before_row else 0,
        "before_row_exists": before_row is not None,
        "quota": get_ai_quota(db_path, daily_limit=daily_limit, now=now),
    }


def restore_ai_quota(
    db_path: Path, *, before_reset_offset: int = 0, before_row_exists: bool = True,
    now: datetime | None = None,
) -> None:
    """Best-effort compensation when the cross-database audit write fails."""
    day_key, _ = _quota_window(now)
    with closing(_open_ai_db(db_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if before_row_exists:
            connection.execute(
                "UPDATE ai_daily_quota SET reset_offset = ?, updated_at = ? WHERE day_key = ?",
                (max(0, int(before_reset_offset)), _now_iso(), day_key),
            )
        else:
            connection.execute(
                "DELETE FROM ai_daily_quota WHERE day_key = ? AND used = 0 AND reserved = 0 AND reset_offset = 0",
                (day_key,),
            )
        connection.execute("COMMIT")


def _open_ai_db(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    schema_key = str(db_path.resolve())
    if schema_key not in _SCHEMA_DONE:
        with _SCHEMA_LOCK:
            if schema_key not in _SCHEMA_DONE:
                ensure_ai_schema(connection)
                _SCHEMA_DONE.add(schema_key)
    return connection
