"""Admin operations and safe operational projections."""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from interview_forge.ai.config import load_ai_config
from interview_forge.ai.tools.registry import build_default_tool_registry
from interview_forge.core.paths import DATA_DIR, PROJECT_ROOT
from interview_forge.core.runtime import server_runtime
from interview_forge.observability.metrics import started_at, uptime_seconds
from interview_forge.runtime.task_manager import task_manager
from interview_forge.services import admin_observability as observability
from interview_forge.services import auth
from interview_forge.services.leetcode import admin_list_sync_tasks


def _cutoff(window: str) -> str:
    return (datetime.now(timezone.utc) - observability.WINDOWS[observability.bounded_window(window)]).isoformat(timespec="seconds")


def _duration_ms(started: Any, finished: Any) -> int | None:
    try:
        a = datetime.fromisoformat(str(started)).astimezone(timezone.utc)
        b = datetime.fromisoformat(str(finished)).astimezone(timezone.utc)
        return max(0, int((b - a).total_seconds() * 1000))
    except (TypeError, ValueError):
        return None


def list_tasks(*, kind: str = "", status: str = "", username: str = "", limit: int = 100) -> dict[str, Any]:
    maximum = observability.bounded_limit(limit)
    items: list[dict[str, Any]] = []
    kinds = {kind} if kind in {"ai", "leetcode"} else {"ai", "leetcode"}
    if "ai" in kinds:
        for user, path in observability.iter_user_databases(username or None):
            if not path.is_file():
                continue
            try:
                with closing(server_runtime.connect(path)) as connection:
                    rows = connection.execute(
                        "SELECT task_id, status, created_at, started_at, finished_at, error_category "
                        "FROM ai_tasks ORDER BY created_at DESC LIMIT 500"
                    ).fetchall()
            except sqlite3.Error:
                continue
            for row in rows:
                if status and str(row["status"]) != status:
                    continue
                items.append({
                    "task_id": str(row["task_id"]), "kind": "ai", "username": str(user["username"]),
                    "status": str(row["status"]), "created_at": row["created_at"], "started_at": row["started_at"],
                    "finished_at": row["finished_at"], "duration_ms": _duration_ms(row["started_at"], row["finished_at"]),
                    "error_code": row["error_category"],
                })
    if "leetcode" in kinds:
        for row in admin_list_sync_tasks():
            if username and str(row.get("owner", "")) != username:
                continue
            row_status = "running" if row.get("running") else ("failed" if row.get("error_category") else "succeeded")
            if status and row_status != status:
                continue
            items.append({
                "task_id": str(row.get("task_id", "")), "kind": "leetcode", "username": str(row.get("owner", "")),
                "status": row_status, "created_at": row.get("created_at"), "started_at": row.get("started_at"),
                "finished_at": row.get("finished_at"), "duration_ms": _duration_ms(row.get("started_at"), row.get("finished_at")),
                "error_code": row.get("error_category"),
            })
    items.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return {"items": items[:maximum], "has_more": len(items) > maximum}


def list_actions(*, username: str = "", tool: str = "", status: str = "", window: str = "24h", limit: int = 100) -> dict[str, Any]:
    cutoff = _cutoff(window)
    items: list[dict[str, Any]] = []
    for user, path in observability.iter_user_databases(username or None):
        try:
            with closing(server_runtime.connect(path)) as connection:
                rows = connection.execute(
                    "SELECT tool_name, status, confirmation_text, created_at, decided_at, completed_at, error_code "
                    "FROM chat_action_requests WHERE created_at >= ? ORDER BY created_at DESC LIMIT 500", (cutoff,)
                ).fetchall()
        except sqlite3.Error:
            continue
        for row in rows:
            if tool and str(row["tool_name"]) != tool:
                continue
            if status and str(row["status"]) != status:
                continue
            items.append({"username": str(user["username"]), **dict(row)})
    maximum = observability.bounded_limit(limit)
    return {"items": items[:maximum], "has_more": len(items) > maximum, "window": observability.bounded_window(window)}


def _user_by_name(username: str) -> dict[str, Any]:
    for user in auth.list_users():
        if str(user.get("username")) == username:
            return user
    raise LookupError("用户不存在")


def user_detail(username: str) -> dict[str, Any]:
    user = _user_by_name(username)
    path = auth.user_db_path(username)
    learning = {"study_events": 0, "submissions": 0, "completed": 0, "marked": 0}
    ai = {"chat_sessions": 0, "messages": 0, "turns_7d": 0, "tokens_7d": 0, "tool_calls_7d": 0, "tool_errors_7d": 0, "action_counts": {}, "recent_error_categories": []}
    memory = {"total_active": 0, "total_superseded": 0, "by_kind": {}}
    if path.is_file():
        try:
            with closing(server_runtime.connect(path)) as connection:
                for key, sql in (
                    ("study_events", "SELECT COUNT(*) FROM study_events"),
                    ("submissions", "SELECT COUNT(*) FROM submissions"),
                    ("completed", "SELECT COUNT(*) FROM study_events WHERE action = 'complete'"),
                    ("marked", "SELECT COUNT(*) FROM problem_marks"),
                ):
                    try:
                        learning[key] = int(connection.execute(sql).fetchone()[0])
                    except sqlite3.Error:
                        pass
                ai["chat_sessions"] = int(connection.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0])
                ai["messages"] = int(connection.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0])
                cutoff = _cutoff("7d")
                trace_rows = connection.execute(
                    "SELECT input_tokens, output_tokens FROM ai_trace_events WHERE event_type = 'chat' AND finished_at >= ?", (cutoff,)
                ).fetchall()
                ai["turns_7d"] = len(trace_rows)
                ai["tokens_7d"] = sum(int(row["input_tokens"] or 0) + int(row["output_tokens"] or 0) for row in trace_rows)
                ai["tool_calls_7d"] = int(connection.execute("SELECT COUNT(*) FROM chat_tool_runs WHERE created_at >= ?", (cutoff,)).fetchone()[0])
                ai["tool_errors_7d"] = int(connection.execute("SELECT COUNT(*) FROM chat_tool_runs WHERE created_at >= ? AND status NOT IN ('ok','cache_hit','confirmation_required')", (cutoff,)).fetchone()[0])
                for row in connection.execute("SELECT status, COUNT(*) AS count FROM chat_action_requests GROUP BY status"):
                    ai["action_counts"][str(row["status"])] = int(row["count"])
                ai["recent_error_categories"] = [str(row[0]) for row in connection.execute(
                    "SELECT DISTINCT error_code FROM ai_trace_events WHERE error_code IS NOT NULL AND finished_at >= ? LIMIT 10", (cutoff,)
                )]
                memory["total_active"] = int(connection.execute("SELECT COUNT(*) FROM user_memories WHERE status = 'active'").fetchone()[0])
                memory["total_superseded"] = int(connection.execute("SELECT COUNT(*) FROM user_memories WHERE status = 'superseded'").fetchone()[0])
                for row in connection.execute("SELECT kind, COUNT(*) AS count FROM user_memories GROUP BY kind"):
                    memory["by_kind"][str(row["kind"])] = int(row["count"])
        except sqlite3.Error:
            pass
    return {
        "account": {key: user.get(key) for key in ("username", "nickname", "role", "is_active", "created_at", "last_login", "db_bytes")},
        "learning": learning, "ai": ai, "memory": memory,
    }


def memory_summary(*, username: str = "") -> dict[str, Any]:
    active = superseded = recent = 0
    by_kind: dict[str, int] = {}
    by_source: dict[str, int] = {}
    cutoff = _cutoff("7d")
    for _, path in observability.iter_user_databases(username or None):
        try:
            with closing(server_runtime.connect(path)) as connection:
                active += int(connection.execute("SELECT COUNT(*) FROM user_memories WHERE status = 'active'").fetchone()[0])
                superseded += int(connection.execute("SELECT COUNT(*) FROM user_memories WHERE status = 'superseded'").fetchone()[0])
                recent += int(connection.execute("SELECT COUNT(*) FROM user_memories WHERE created_at >= ?", (cutoff,)).fetchone()[0])
                for row in connection.execute("SELECT kind, COUNT(*) AS count FROM user_memories GROUP BY kind"):
                    by_kind[str(row["kind"])] = by_kind.get(str(row["kind"]), 0) + int(row["count"])
                for row in connection.execute("SELECT source_type, COUNT(*) AS count FROM user_memories GROUP BY source_type"):
                    by_source[str(row["source_type"])] = by_source.get(str(row["source_type"]), 0) + int(row["count"])
        except sqlite3.Error:
            continue
    return {"active": active, "superseded": superseded, "by_kind": by_kind, "by_source": by_source, "recent_write_count_7d": recent}


def _project_size() -> int:
    total = 0
    try:
        for path in DATA_DIR.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
    except OSError:
        pass
    return total


def system_info() -> dict[str, Any]:
    config = load_ai_config()
    registry = build_default_tool_registry()
    specs = registry.list_specs()
    disk = shutil.disk_usage(PROJECT_ROOT)
    return {
        "version_sha": observability.version_sha(), "started_at": started_at(), "uptime_seconds": uptime_seconds(),
        "python_version": sys.version.split()[0],
        "fastapi_version": _package_version("fastapi"), "uvicorn_version": _package_version("uvicorn"),
        "registered_tools": len(specs), "registered_action_tools": sum(1 for spec in specs if str(spec.kind) == "ToolKind.ACTION" or getattr(spec.kind, "value", "") == "action"),
        "task_backends": list(task_manager.kinds()),
        "ai": {"enabled": config.enabled, "configured": config.configured, "provider": config.provider, "model": config.model},
        "storage": {"project_data_bytes": _project_size(), "disk_total": disk.total, "disk_used": disk.used, "disk_free": disk.free},
    }


def _package_version(name: str) -> str:
    try:
        module = __import__(name)
        return str(getattr(module, "__version__", "unknown"))
    except Exception:
        return "unavailable"


def diagnostics() -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    def add(name: str, status: str, message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})
    add("application", "ok", "FastAPI application is importable")
    try:
        with closing(auth.connect_auth()):
            pass
        add("auth_database", "ok", "readable")
    except Exception:
        add("auth_database", "failed", "not readable")
    users = list(auth.list_users())
    readable = 0
    for user, path in observability.iter_user_databases():
        if path.is_file():
            try:
                with closing(server_runtime.connect(path)) as connection:
                    connection.execute("SELECT 1").fetchone()
                readable += 1
            except sqlite3.Error:
                pass
    add("user_databases", "ok" if readable == len(users) else "warning", f"{readable}/{len(users)} readable")
    log_dir = observability.log_paths()[0].parent
    add("log_directory", "ok" if os.access(log_dir, os.W_OK) or not log_dir.exists() else "warning", "writable" if os.access(log_dir, os.W_OK) else "not writable")
    disk = shutil.disk_usage(PROJECT_ROOT)
    add("disk_free", "ok" if disk.free > 100 * 1024 * 1024 else "warning", str(disk.free))
    config = load_ai_config()
    add("ai_config", "ok" if config.enabled and config.configured else "warning", "enabled and configured" if config.enabled and config.configured else "disabled or incomplete")
    try:
        registry = build_default_tool_registry()
        add("tool_registry", "ok", f"{len(registry.list_specs())} tools")
    except Exception:
        add("tool_registry", "failed", "unavailable")
    add("task_backends", "ok", ", ".join(task_manager.kinds()) or "none")
    add("sqlite_schema", "ok" if readable else "warning", "available" if readable else "no readable user database")
    statuses = {item["status"] for item in checks}
    overall = "failed" if "failed" in statuses else ("warning" if "warning" in statuses else "ok")
    return {"status": overall, "checks": checks}


__all__ = ["diagnostics", "list_actions", "list_tasks", "memory_summary", "system_info", "user_detail"]
