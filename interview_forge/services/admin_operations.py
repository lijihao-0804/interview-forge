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
from interview_forge.ai.config_store import SUPPORTED_BUSINESS_KEYS
from interview_forge.ai.resolver import resolve_ai_runtime
from interview_forge.ai.tools.registry import build_default_tool_registry
from interview_forge.core.paths import DATA_DIR, PROJECT_ROOT
from interview_forge.core.runtime import server_runtime
from interview_forge.observability.metrics import started_at, uptime_seconds
from interview_forge.observability.system import runtime_metrics
from interview_forge.observability.store import request_metrics
from interview_forge.runtime.task_manager import task_manager
from interview_forge.services import admin_observability as observability
from interview_forge.services import auth
from interview_forge.services.leetcode import admin_list_sync_tasks


def _cutoff(window: str) -> str:
    return (datetime.now(timezone.utc) - observability.WINDOWS[observability.bounded_window(window)]).isoformat(timespec="seconds")


def _business_cutoff(window: str) -> str:
    """Cutoff for timestamps in the user's business database, in Beijing."""
    return (server_runtime.business_now() - observability.WINDOWS[observability.bounded_window(window)]).isoformat(timespec="seconds")


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
            row_status = "running" if row.get("running") else (
                "degraded" if row.get("partial") else ("failed" if row.get("error_category") else "succeeded")
            )
            if status and row_status != status:
                continue
            error_code = row.get("error_category")
            if row.get("partial"):
                error_code = "partial" + (f":{row['degraded_category']}" if row.get("degraded_category") else "")
            items.append({
                "task_id": str(row.get("task_id", "")), "kind": "leetcode", "username": str(row.get("owner", "")),
                "status": row_status, "created_at": row.get("created_at"), "started_at": row.get("started_at"),
                "finished_at": row.get("finished_at"), "duration_ms": _duration_ms(row.get("started_at"), row.get("finished_at")),
                "error_code": error_code, "partial": bool(row.get("partial")),
                "degraded_category": row.get("degraded_category"),
            })
    items.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    counts = {key: sum(1 for item in items if item["status"] == key) for key in ("queued", "running", "succeeded", "degraded", "failed", "cancelled")}
    return {"items": items[:maximum], "has_more": len(items) > maximum, "counts": counts}


def list_actions(*, username: str = "", tool: str = "", status: str = "", window: str = "24h", limit: int = 100) -> dict[str, Any]:
    cutoff = _business_cutoff(window)
    items: list[dict[str, Any]] = []
    for user, path in observability.iter_user_databases(username or None):
        try:
            with closing(server_runtime.connect(path)) as connection:
                rows = connection.execute(
                    "SELECT tool_name, status, confirmation_text, created_at, decided_at, completed_at, error_code "
                    "FROM chat_action_requests WHERE datetime(created_at) >= datetime(?) ORDER BY created_at DESC LIMIT 500", (cutoff,)
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
    items.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
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
                    ("marked", "SELECT COUNT(*) FROM marks"),
                ):
                    try:
                        learning[key] = int(connection.execute(sql).fetchone()[0])
                    except sqlite3.Error:
                        pass
                ai["chat_sessions"] = int(connection.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0])
                ai["messages"] = int(connection.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0])
                trace_cutoff = _cutoff("7d")
                business_cutoff = _business_cutoff("7d")
                trace_rows = connection.execute(
                    "SELECT input_tokens, output_tokens FROM ai_trace_events WHERE event_type = 'chat' AND finished_at >= ?", (trace_cutoff,)
                ).fetchall()
                ai["turns_7d"] = len(trace_rows)
                ai["tokens_7d"] = sum(int(row["input_tokens"] or 0) + int(row["output_tokens"] or 0) for row in trace_rows)
                ai["tool_calls_7d"] = int(connection.execute("SELECT COUNT(*) FROM chat_tool_runs WHERE datetime(created_at) >= datetime(?)", (business_cutoff,)).fetchone()[0])
                ai["tool_errors_7d"] = int(connection.execute("SELECT COUNT(*) FROM chat_tool_runs WHERE datetime(created_at) >= datetime(?) AND status NOT IN ('ok','cache_hit','confirmation_required')", (business_cutoff,)).fetchone()[0])
                for row in connection.execute("SELECT status, COUNT(*) AS count FROM chat_action_requests GROUP BY status"):
                    ai["action_counts"][str(row["status"])] = int(row["count"])
                ai["recent_error_categories"] = [str(row[0]) for row in connection.execute(
                    "SELECT DISTINCT error_code FROM ai_trace_events WHERE error_code IS NOT NULL AND finished_at >= ? LIMIT 10", (trace_cutoff,)
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
    cutoff = _business_cutoff("7d")
    for _, path in observability.iter_user_databases(username or None):
        try:
            with closing(server_runtime.connect(path)) as connection:
                active += int(connection.execute("SELECT COUNT(*) FROM user_memories WHERE status = 'active'").fetchone()[0])
                superseded += int(connection.execute("SELECT COUNT(*) FROM user_memories WHERE status = 'superseded'").fetchone()[0])
                recent += int(connection.execute("SELECT COUNT(*) FROM user_memories WHERE datetime(created_at) >= datetime(?)", (cutoff,)).fetchone()[0])
                for row in connection.execute("SELECT kind, COUNT(*) AS count FROM user_memories GROUP BY kind"):
                    by_kind[str(row["kind"])] = by_kind.get(str(row["kind"]), 0) + int(row["count"])
                for row in connection.execute("SELECT source_type, COUNT(*) AS count FROM user_memories GROUP BY source_type"):
                    by_source[str(row["source_type"])] = by_source.get(str(row["source_type"]), 0) + int(row["count"])
        except sqlite3.Error:
            continue
    return {"active": active, "superseded": superseded, "by_kind": by_kind, "by_source": by_source, "recent_write_count_7d": recent}


def governance_summary() -> dict[str, Any]:
    """Return aggregate-only feedback and invite-code health.

    This intentionally does not reuse the admin detail lists: the operations
    dashboard only needs counts and timestamps, not feedback text, contact
    details, invite codes, or user ids.
    """
    today = server_runtime.business_now().date().isoformat()
    feedback = {"total": 0, "open": 0, "resolved": 0, "last_created_at": None, "last_resolved_at": None}
    invites = {"total": 0, "unused": 0, "used": 0, "revoked": 0, "expired": 0}
    with closing(auth.connect_auth()) as connection:
        for row in connection.execute("SELECT status, COUNT(*) AS count FROM feedback GROUP BY status"):
            status = str(row["status"])
            if status in {"open", "resolved"}:
                feedback[status] = int(row["count"])
                feedback["total"] += int(row["count"])
        feedback["last_created_at"] = connection.execute("SELECT created_at FROM feedback ORDER BY id DESC LIMIT 1").fetchone()
        feedback["last_resolved_at"] = connection.execute("SELECT resolved_at FROM feedback WHERE resolved_at IS NOT NULL ORDER BY resolved_at DESC LIMIT 1").fetchone()
        feedback["last_created_at"] = feedback["last_created_at"][0] if feedback["last_created_at"] else None
        feedback["last_resolved_at"] = feedback["last_resolved_at"][0] if feedback["last_resolved_at"] else None
        for row in connection.execute("SELECT status, COUNT(*) AS count FROM invite_codes GROUP BY status"):
            status = str(row["status"])
            if status in {"unused", "used", "revoked"}:
                invites[status] = int(row["count"])
                invites["total"] += int(row["count"])
        invites["expired"] = int(connection.execute(
            "SELECT COUNT(*) FROM invite_codes WHERE status = 'unused' AND expires_at IS NOT NULL AND expires_at < ?", (today,)
        ).fetchone()[0])
    return {"feedback": feedback, "invites": invites}


def leetcode_health(*, window: str = "24h") -> dict[str, Any]:
    """Return safe operational health for retained process-local sync tasks.

    Submission counts and record contents are deliberately excluded. The
    current LeetCode task registry is process-local, so the response declares
    that scope instead of implying durable historical coverage.
    """
    selected = observability.bounded_window(window)
    cutoff = datetime.fromisoformat(_cutoff(selected))
    counts = {"running": 0, "succeeded": 0, "degraded": 0, "failed": 0}
    categories: dict[str, int] = {}
    events: list[dict[str, Any]] = []
    for row in admin_list_sync_tasks():
        timestamp = row.get("finished_at") or row.get("started_at") or row.get("created_at")
        try:
            parsed = datetime.fromisoformat(str(timestamp))
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None and parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if parsed is not None and parsed.astimezone(timezone.utc) < cutoff:
            continue
        if row.get("running"):
            status = "running"
        elif row.get("partial"):
            status = "degraded"
        elif row.get("error_category"):
            status = "failed"
        else:
            status = "succeeded"
        counts[status] += 1
        category = str(row.get("error_category") or row.get("degraded_category") or "")
        if category:
            categories[category] = categories.get(category, 0) + 1
        if status != "running":
            events.append({
                "status": status,
                "finished_at": row.get("finished_at"),
                "duration_ms": _duration_ms(row.get("started_at"), row.get("finished_at")),
                "error_category": category or None,
            })
    events.sort(key=lambda item: str(item.get("finished_at") or ""), reverse=True)
    def latest(status: str) -> dict[str, Any] | None:
        return next((item for item in events if item["status"] == status), None)
    return {
        "window": selected,
        "scope": "当前进程保留的同步任务",
        "counts": counts,
        "error_categories": categories,
        "last_success": latest("succeeded"),
        "last_failure": latest("failed"),
        "last_partial": latest("degraded"),
        "recent": events[:20],
    }


def _project_size() -> int:
    total = 0
    try:
        for path in DATA_DIR.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
    except OSError:
        pass
    return total


def _runtime_error_category(exc: BaseException) -> str:
    """Map resolver failures to a safe, non-sensitive diagnostic category."""
    message = str(exc)
    if "模型已停用" in message:
        return "model_disabled"
    if "模型当前不可用" in message:
        return "model_unavailable"
    if "模型不存在" in message:
        return "model_missing"
    if "Provider 未启用或不存在" in message:
        return "provider_unavailable"
    if "主密钥" in message or "API Key" in message:
        return "secret_unavailable"
    if "reasoning" in message.lower() or "推理" in message:
        return "reasoning_unsupported"
    return "runtime_unavailable"


def _runtime_projection(business_key: str) -> dict[str, Any]:
    """Return only the effective, non-sensitive runtime for one workload."""
    try:
        runtime = resolve_ai_runtime(business_key)
    except Exception as exc:
        return {
            "business_key": business_key,
            "status": "error",
            "source": "unknown",
            "error_category": _runtime_error_category(exc),
        }
    config = runtime.config
    configured = bool(config.enabled and config.configured)
    policy = runtime.reasoning_policy
    return {
        "business_key": business_key,
        "status": "ok" if configured else "unavailable",
        "source": str(runtime.config_source or "env"),
        "provider_id": runtime.provider_id,
        "provider_name": runtime.provider_name,
        "vendor": getattr(runtime, "vendor", None),
        "protocol": runtime.protocol,
        "model": runtime.model,
        "reasoning_mode": getattr(policy, "mode", None),
        "reasoning_effort": getattr(policy, "effort", None),
        "reasoning_budget": getattr(policy, "budget_tokens", None),
    }


def _legacy_fallback_projection() -> dict[str, Any]:
    """Describe ENV fallback separately from the effective business routes."""
    try:
        config = load_ai_config()
    except Exception as exc:
        return {
            "status": "error",
            "enabled": False,
            "configured": False,
            "error_category": _runtime_error_category(exc),
        }
    configured = bool(config.enabled and config.configured)
    return {
        "status": "ok" if configured else "unavailable",
        "enabled": bool(config.enabled),
        "configured": bool(config.configured),
        "provider": config.provider,
        "model": config.model,
        "source": "legacy_env",
    }


def _ai_runtime_snapshot() -> dict[str, Any]:
    routes = {
        business_key: _runtime_projection(business_key)
        for business_key in SUPPORTED_BUSINESS_KEYS
    }
    legacy = _legacy_fallback_projection()
    # This is deliberately derived from the effective resolver results. It is
    # not a second provider/profile selection path.
    managed_available = any(
        item.get("source") == "db" for item in routes.values()
    )
    return {
        "managed_config_available": managed_available,
        "routes": routes,
        "legacy_fallback": legacy,
    }


def system_info() -> dict[str, Any]:
    ai = _ai_runtime_snapshot()
    registry = build_default_tool_registry()
    specs = registry.list_specs()
    disk = shutil.disk_usage(PROJECT_ROOT)
    runtime = runtime_metrics()
    return {
        "version_sha": observability.version_sha(), "started_at": started_at(), "uptime_seconds": uptime_seconds(),
        "python_version": sys.version.split()[0],
        "fastapi_version": _package_version("fastapi"), "uvicorn_version": _package_version("uvicorn"),
        "registered_tools": len(specs), "registered_action_tools": sum(1 for spec in specs if str(spec.kind) == "ToolKind.ACTION" or getattr(spec.kind, "value", "") == "action"),
        "task_backends": list(task_manager.kinds()),
        "ai": ai | {
            # Keep the old scalar fields for API consumers during the
            # transition, but the admin UI no longer presents them as current.
            "enabled": ai["legacy_fallback"]["enabled"],
            "configured": ai["legacy_fallback"]["configured"],
            "provider": ai["legacy_fallback"].get("provider", ""),
            "model": ai["legacy_fallback"].get("model", ""),
        },
        "runtime_metrics": runtime,
        "governance": governance_summary(),
        "storage": {"project_data_bytes": _project_size(), "disk_total": disk.total, "disk_used": disk.used, "disk_free": disk.free, **runtime.get("storage", {})},
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
    if log_dir.exists():
        log_writable = os.access(log_dir, os.W_OK)
        log_message = "writable" if log_writable else "not writable"
    else:
        parent = log_dir.parent
        log_writable = parent.exists() and os.access(parent, os.W_OK)
        log_message = "will be created under writable parent" if log_writable else "parent not writable"
    add("log_directory", "ok" if log_writable else "warning", log_message)
    try:
        metrics = request_metrics("30d")
        add("observability_database", "ok", f"readable; {metrics.get('totals', {}).get('request_count', 0)} aggregated requests")
    except Exception:
        add("observability_database", "failed", "not readable")
    disk = shutil.disk_usage(PROJECT_ROOT)
    add("disk_free", "ok" if disk.free > 100 * 1024 * 1024 else "warning", str(disk.free))
    route_items = {
        business_key: _runtime_projection(business_key)
        for business_key in SUPPORTED_BUSINESS_KEYS
    }
    for business_key, item in route_items.items():
        if item["status"] == "ok":
            status, message = "ok", f"{item['source']} runtime resolved"
        elif item["status"] == "unavailable":
            status, message = "warning", "runtime is not configured"
        else:
            status, message = "failed", f"resolver error: {item['error_category']}"
        add(f"ai_route_{business_key}", status, message)
    legacy = _legacy_fallback_projection()
    managed_routes_ok = any(item["status"] == "ok" and item["source"] == "db" for item in route_items.values())
    if legacy["status"] == "ok":
        add("ai_legacy_fallback", "ok", "ENV fallback is enabled and configured")
    elif legacy["status"] == "error":
        add("ai_legacy_fallback", "failed", f"resolver error: {legacy['error_category']}")
    elif managed_routes_ok:
        add("ai_legacy_fallback", "warning", "ENV fallback is not configured; managed routes are active")
    else:
        add("ai_legacy_fallback", "warning", "ENV fallback is disabled or incomplete")
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


__all__ = ["diagnostics", "governance_summary", "leetcode_health", "list_actions", "list_tasks", "memory_summary", "system_info", "user_detail"]
