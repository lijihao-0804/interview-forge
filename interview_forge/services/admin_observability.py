"""Admin-only observability queries.

All aggregation and privacy filtering lives here; routers only validate the
small query surface and enforce authentication.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from interview_forge.ai.config import load_ai_config
from interview_forge.core.paths import PROJECT_ROOT
from interview_forge.core.runtime import server_runtime
from interview_forge.observability.costs import estimate_cost, load_pricing
from interview_forge.observability.logging import _safe_value, log_paths
from interview_forge.observability.metrics import started_at, uptime_seconds
from interview_forge.services import auth
from interview_forge.runtime.task_manager import task_manager
from interview_forge.services.leetcode import admin_list_sync_tasks


WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}


def bounded_window(value: str | None) -> str:
    return value if value in WINDOWS else "24h"


def bounded_limit(value: int | None, default: int = 100, maximum: int = 500) -> int:
    try:
        number = int(value if value is not None else default)
    except (TypeError, ValueError):
        number = default
    return max(1, min(number, maximum))


def iter_user_databases(username: str | None = None) -> Iterable[tuple[dict[str, Any], Path]]:
    for user in auth.list_users():
        name = str(user.get("username", ""))
        if username and name != username:
            continue
        try:
            path = auth.user_db_path(name)
        except (TypeError, ValueError):
            continue
        yield user, path


def _cutoff(window: str) -> str:
    return (datetime.now(timezone.utc) - WINDOWS[bounded_window(window)]).isoformat(timespec="seconds")


def _percentile(values: list[float], percentile: float = 0.95) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return round(ordered[index], 2)


def _iter_log_records(
    *, level: str = "", module: str = "", event: str = "", request_id: str = "",
) -> Iterator[dict[str, Any]]:
    for path in log_paths():
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if len(line) > 16_384:
                continue
            try:
                row = json.loads(line)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(row, dict):
                continue
            if level and str(row.get("level", "")).upper() != level.upper():
                continue
            if module and str(row.get("module", "")) != module:
                continue
            if event and str(row.get("event", "")) != event:
                continue
            if request_id and str(row.get("request_id", "")) != request_id:
                continue
            yield {str(key): _safe_value(str(key), value) for key, value in row.items()}


def _read_log_records(
    *, level: str = "", module: str = "", event: str = "", request_id: str = "", limit: int = 100,
) -> dict[str, Any]:
    normalized_limit = bounded_limit(limit)
    records: list[dict[str, Any]] = []
    for row in _iter_log_records(level=level, module=module, event=event, request_id=request_id):
        records.append(row)
        if len(records) >= normalized_limit:
            return {"items": records, "has_more": True}
    return {"items": records, "has_more": False}


def list_logs(*, level: str = "", module: str = "", event: str = "", request_id: str = "", limit: int = 100) -> dict[str, Any]:
    return _read_log_records(
        level=str(level or "")[:32], module=str(module or "")[:96],
        event=str(event or "")[:128], request_id=str(request_id or "")[:128],
        limit=limit,
    )


def _trace_rows(
    path: Path, *, cutoff: str | None = None, model: str = "", trace_id: str = "",
    limit: int | None = 2000,
) -> list[sqlite3.Row]:
    if not path.is_file():
        return []
    try:
        with closing(server_runtime.connect(path)) as connection:
            clauses = ["event_type IN ('chat', 'llm')"]
            params: list[Any] = []
            if cutoff:
                clauses.append("(finished_at IS NULL OR finished_at >= ?)")
                params.append(cutoff)
            if model:
                clauses.append("model = ?")
                params.append(model[:128])
            if trace_id:
                clauses.append("trace_id = ?")
                params.append(trace_id[:128])
            query = (
                "SELECT id, trace_id, session_id, request_id, event_type, name, status, provider, model, "
                "round_index, started_at, finished_at, duration_ms, input_tokens, output_tokens, "
                "reasoning_tokens, error_code, metadata_json FROM ai_trace_events WHERE "
                + " AND ".join(clauses) + " ORDER BY id DESC"
            )
            if limit is not None:
                query += " LIMIT ?"
                params.append(max(1, int(limit)))
            return connection.execute(query, params).fetchall()
    except sqlite3.Error:
        return []


def _row_int(row: Any, key: str) -> int:
    value = row[key]
    return int(value) if isinstance(value, (int, float)) else 0


def _request_stats() -> tuple[int, int, float | None]:
    recent: list[dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc) - WINDOWS["24h"]
    for row in _iter_log_records():
        try:
            timestamp = datetime.fromisoformat(str(row.get("time", "")).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if timestamp >= cutoff and row.get("event") == "api_request":
            recent.append(row)
    durations = [float(row["elapsed_ms"]) for row in recent if isinstance(row.get("elapsed_ms"), (int, float))]
    errors = sum(1 for row in recent if int(row.get("status", 0) or 0) >= 500)
    return len(recent), errors, _percentile(durations)


def overview() -> dict[str, Any]:
    total_requests, request_errors, request_p95 = _request_stats()
    turns = 0
    successes = 0
    durations: list[float] = []
    input_tokens = output_tokens = tool_calls = tool_errors = 0
    failed_tasks = running_tasks = 0
    db_bytes = 0
    users = list(auth.list_users())
    cutoff = _cutoff("24h")
    for user, path in iter_user_databases():
        try:
            db_bytes += path.stat().st_size if path.is_file() else 0
        except OSError:
            pass
        rows = _trace_rows(path, cutoff=cutoff, limit=None)
        for row in rows:
            if str(row["event_type"]) == "chat":
                turns += 1
                successes += str(row["status"]) == "success"
                if isinstance(row["duration_ms"], (int, float)):
                    durations.append(float(row["duration_ms"]))
                input_tokens += _row_int(row, "input_tokens")
                output_tokens += _row_int(row, "output_tokens")
        try:
            with closing(server_runtime.connect(path)) as connection:
                tool_calls += int(connection.execute("SELECT COUNT(*) FROM chat_tool_runs WHERE created_at >= ?", (cutoff,)).fetchone()[0])
                tool_errors += int(connection.execute("SELECT COUNT(*) FROM chat_tool_runs WHERE created_at >= ? AND status NOT IN ('ok','cache_hit','confirmation_required')", (cutoff,)).fetchone()[0])
                running_tasks += int(connection.execute("SELECT COUNT(*) FROM ai_tasks WHERE status IN ('queued','running')").fetchone()[0])
                failed_tasks += int(connection.execute("SELECT COUNT(*) FROM ai_tasks WHERE status = 'failed' AND finished_at >= ?", (cutoff,)).fetchone()[0])
        except sqlite3.Error:
            continue
    leetcode_tasks = admin_list_sync_tasks()
    running_tasks += sum(1 for item in leetcode_tasks if item.get("running"))
    failed_tasks += sum(1 for item in leetcode_tasks if item.get("error_category"))
    disk = shutil.disk_usage(PROJECT_ROOT)
    return {
        "system": {"status": "ok", "uptime": uptime_seconds(), "version": version_sha()},
        "users": {
            "total": len(users),
            "active_24h": _active_count(users, timedelta(hours=24)),
            "active_7d": _active_count(users, timedelta(days=7)),
        },
        "requests": {
            "total_24h": total_requests, "error_5xx_24h": request_errors,
            "error_rate": round(request_errors / total_requests, 4) if total_requests else 0,
            "p95_ms": request_p95,
        },
        "ai": {
            "turns_24h": turns, "success_rate": round(successes / turns, 4) if turns else 0,
            "p95_ms": _percentile(durations), "input_tokens": input_tokens,
            "output_tokens": output_tokens, "tool_calls": tool_calls, "tool_errors": tool_errors,
        },
        "tasks": {"running": running_tasks, "failed": failed_tasks},
        "storage": {"user_db_bytes": db_bytes, "disk_total": disk.total, "disk_used": disk.used, "disk_free": disk.free},
    }


def _active_count(users: list[dict[str, Any]], age: timedelta) -> int:
    cutoff = datetime.now(timezone.utc) - age
    count = 0
    for user in users:
        value = user.get("last_active") or user.get("last_login")
        try:
            parsed = datetime.fromisoformat(str(value)).astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        count += parsed >= cutoff
    return count


def ai_usage(*, window: str = "24h", username: str = "", model: str = "") -> dict[str, Any]:
    selected = bounded_window(window)
    rows: list[tuple[str, sqlite3.Row]] = []
    cutoff = _cutoff(selected)
    for user, path in iter_user_databases(username or None):
        rows.extend((str(user["username"]), row) for row in _trace_rows(path, cutoff=cutoff, model=model, limit=None))
    chats = [row for _, row in rows if str(row["event_type"]) == "chat"]
    turns = len(chats)
    success = sum(str(row["status"]) == "success" for row in chats)
    durations = [float(row["duration_ms"]) for row in chats if isinstance(row["duration_ms"], (int, float))]
    input_tokens = sum(_row_int(row, "input_tokens") for _, row in rows if str(row["event_type"]) == "chat")
    output_tokens = sum(_row_int(row, "output_tokens") for _, row in rows if str(row["event_type"]) == "chat")
    reasoning_tokens = sum(_row_int(row, "reasoning_tokens") for _, row in rows if str(row["event_type"]) == "chat")
    tool_calls = tool_errors = memory_writes = 0
    for user, path in iter_user_databases(username or None):
        try:
            with closing(server_runtime.connect(path)) as connection:
                tool_calls += int(connection.execute("SELECT COUNT(*) FROM chat_tool_runs WHERE created_at >= ?", (cutoff,)).fetchone()[0])
                tool_errors += int(connection.execute("SELECT COUNT(*) FROM chat_tool_runs WHERE created_at >= ? AND status NOT IN ('ok','cache_hit','confirmation_required')", (cutoff,)).fetchone()[0])
                memory_writes += int(connection.execute("SELECT COUNT(*) FROM user_memories WHERE created_at >= ?", (cutoff,)).fetchone()[0])
        except sqlite3.Error:
            continue
    models: dict[str, dict[str, Any]] = {}
    priced = 0
    total_chat = 0
    estimated_cost = 0.0
    for _, row in rows:
        if str(row["event_type"]) != "chat":
            continue
        key = str(row["model"] or "unknown")
        item = models.setdefault(key, {"model": key, "turns": 0, "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": None})
        item["turns"] += 1
        item["input_tokens"] += _row_int(row, "input_tokens")
        item["output_tokens"] += _row_int(row, "output_tokens")
        cost = estimate_cost(key, _row_int(row, "input_tokens"), _row_int(row, "output_tokens"))
        if cost is not None:
            item["estimated_cost_usd"] = round(float(item["estimated_cost_usd"] or 0) + cost, 8)
            estimated_cost += cost
            priced += 1
        total_chat += 1
    return {
        "window": selected, "turns": turns, "success": success, "failed": turns - success,
        "success_rate": round(success / turns, 4) if turns else 0,
        "input_tokens": input_tokens, "output_tokens": output_tokens, "reasoning_tokens": reasoning_tokens,
        "avg_latency_ms": round(sum(durations) / len(durations), 2) if durations else None,
        "p95_latency_ms": _percentile(durations), "tool_calls": tool_calls,
        "tool_errors": tool_errors, "memory_writes": memory_writes, "models": list(models.values()),
        "estimated_cost_usd": round(estimated_cost, 8) if priced else None,
        "cost_coverage_percent": round(priced / total_chat * 100, 2) if total_chat else 0,
        "pricing_configured": bool(load_pricing()),
    }


def list_traces(*, username: str = "", status: str = "", model: str = "", window: str = "24h", limit: int = 100) -> dict[str, Any]:
    selected = bounded_window(window)
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for user, path in iter_user_databases(username or None):
        user_name = str(user["username"])
        for row in _trace_rows(path, cutoff=_cutoff(selected), model=model):
            if str(row["event_type"]) != "chat" or (status and str(row["status"]) != status):
                continue
            key = (user_name, str(row["trace_id"]))
            if key in grouped:
                continue
            grouped[key] = {
                "username": user_name, "trace_id": str(row["trace_id"]), "session_id": row["session_id"],
                "request_id": row["request_id"], "status": row["status"], "model": row["model"],
                "provider": row["provider"], "started_at": row["started_at"], "finished_at": row["finished_at"],
                "duration_ms": row["duration_ms"], "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"], "reasoning_tokens": row["reasoning_tokens"],
                "error_code": row["error_code"],
            }
    items = sorted(grouped.values(), key=lambda item: str(item.get("finished_at") or ""), reverse=True)
    bounded = items[:bounded_limit(limit)]
    return {"items": bounded, "has_more": len(items) > len(bounded)}


def trace_detail(trace_id: str, *, username: str = "") -> dict[str, Any] | None:
    trace_id = str(trace_id).strip()[:128]
    for user, path in iter_user_databases(username or None):
        user_name = str(user["username"])
        # A detail view must not depend on the newest-traces page window.  A
        # trace may be older than the latest 2,000 events while still being a
        # valid direct lookup.
        selected = _trace_rows(path, trace_id=trace_id, limit=None)
        if not selected:
            continue
        timeline = [
            {"type": str(row["event_type"]), "name": str(row["name"]), "status": str(row["status"]),
             "round": row["round_index"], "provider": row["provider"], "model": row["model"],
             "duration_ms": row["duration_ms"], "input_tokens": row["input_tokens"],
             "output_tokens": row["output_tokens"], "reasoning_tokens": row["reasoning_tokens"],
             "error_code": row["error_code"], "started_at": row["started_at"], "finished_at": row["finished_at"]}
            for row in selected
        ]
        try:
            with closing(server_runtime.connect(path)) as connection:
                tools = [dict(row) for row in connection.execute(
                    "SELECT tool_name, tool_kind, status, duration_ms, error_code, created_at, completed_at "
                    "FROM chat_tool_runs WHERE turn_id = ? ORDER BY created_at ASC", (trace_id,)
                ).fetchall()]
                actions = [dict(row) for row in connection.execute(
                    "SELECT tool_name, status, confirmation_text, created_at, decided_at, completed_at, error_code "
                    "FROM chat_action_requests WHERE turn_id = ? ORDER BY created_at ASC", (trace_id,)
                ).fetchall()]
        except sqlite3.Error:
            tools, actions = [], []
        return {"username": user_name, "trace_id": trace_id, "request_id": selected[0]["request_id"], "timeline": timeline, "tools": tools, "actions": actions}
    return None


def version_sha() -> str:
    configured = os.environ.get("INTERVIEW_FORGE_VERSION", "").strip()
    if configured:
        return configured[:128]
    head = PROJECT_ROOT / ".git" / "HEAD"
    try:
        value = head.read_text(encoding="utf-8").strip()
        if value.startswith("ref: "):
            ref = PROJECT_ROOT / ".git" / value[5:]
            return ref.read_text(encoding="utf-8").strip()[:128]
        return value[:128]
    except OSError:
        return "unknown"


__all__ = [
    "ai_usage", "bounded_limit", "bounded_window", "iter_user_databases", "list_logs",
    "list_traces", "overview", "trace_detail", "version_sha",
]
