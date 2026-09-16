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

try:
    from zoneinfo import ZoneInfo
    _DISPLAY_TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # pragma: no cover - minimal Python installations
    _DISPLAY_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")

from interview_forge.ai.config import load_ai_config
from interview_forge.core.paths import PROJECT_ROOT
from interview_forge.core.runtime import server_runtime
from interview_forge.observability.costs import estimate_cost, load_pricing
from interview_forge.observability.logging import _safe_value, log_paths
from interview_forge.observability.metrics import started_at, uptime_seconds
from interview_forge.observability.store import request_metrics as stored_request_metrics
from interview_forge.observability.store import storage_size as observability_storage_size
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


def _business_cutoff(window: str) -> str:
    """Return a Beijing cutoff for timestamps in per-user business tables.

    Trace/log/observability records are UTC and continue to use ``_cutoff``.
    User DB business records are written through ``server_runtime.now_iso`` in
    Asia/Shanghai; SQLite's datetime() comparison below also handles older
    rows that were written with an explicit UTC offset.
    """
    return (server_runtime.business_now() - WINDOWS[bounded_window(window)]).isoformat(timespec="seconds")


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


def _trace_dimensions(row: Any) -> dict[str, Any]:
    """Read only the non-sensitive dimensions written by TraceRecorder."""
    try:
        value = json.loads(str(row["metadata_json"] or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    return {
        "provider_id": str(value.get("provider_id") or ""),
        "provider_name": str(value.get("provider_name") or row["provider"] or ""),
        "business_key": str(value.get("business_key") or ""),
        "reasoning_mode": str(value.get("reasoning_mode") or ""),
        "reasoning_effort": str(value.get("reasoning_effort") or ""),
        "config_source": str(value.get("config_source") or "env"),
    }


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


def _request_snapshot_stats() -> tuple[int, int, float | None]:
    """Read the bounded aggregate store; never scans JSONL for Overview."""
    payload = stored_request_metrics("24h")
    totals = payload.get("totals", {})
    return int(totals.get("request_count", 0)), int(totals.get("5xx", 0)), totals.get("p95_ms")


def overview() -> dict[str, Any]:
    total_requests, request_errors, request_p95 = _request_snapshot_stats()
    turns = 0
    successes = 0
    durations: list[float] = []
    input_tokens = output_tokens = tool_calls = tool_errors = 0
    ttft_values: list[float] = []
    task_counts = {key: 0 for key in ("queued", "running", "succeeded", "degraded", "failed", "cancelled")}
    db_bytes = 0
    users = list(auth.list_users())
    cutoff = _cutoff("24h")
    business_cutoff = _business_cutoff("24h")
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
                    value = json.loads(str(row["metadata_json"] or "{}")).get("ttft_ms")
                    if isinstance(value, (int, float)) and value >= 0:
                        ttft_values.append(float(value))
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
        try:
            with closing(server_runtime.connect(path)) as connection:
                tool_calls += int(connection.execute("SELECT COUNT(*) FROM chat_tool_runs WHERE datetime(created_at) >= datetime(?)", (business_cutoff,)).fetchone()[0])
                tool_errors += int(connection.execute("SELECT COUNT(*) FROM chat_tool_runs WHERE datetime(created_at) >= datetime(?) AND status NOT IN ('ok','cache_hit','confirmation_required')", (business_cutoff,)).fetchone()[0])
                for task_row in connection.execute("SELECT status, COUNT(*) AS count FROM ai_tasks GROUP BY status"):
                    if str(task_row["status"]) in task_counts:
                        task_counts[str(task_row["status"])] += int(task_row["count"])
        except sqlite3.Error:
            continue
    leetcode_tasks = admin_list_sync_tasks()
    task_counts["running"] += sum(1 for item in leetcode_tasks if item.get("running"))
    task_counts["degraded"] += sum(1 for item in leetcode_tasks if not item.get("running") and item.get("partial"))
    task_counts["failed"] += sum(1 for item in leetcode_tasks if not item.get("running") and item.get("error_category") and not item.get("partial"))
    task_counts["succeeded"] += sum(1 for item in leetcode_tasks if not item.get("running") and not item.get("error_category"))
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
            "p50_ms": _percentile(durations, .50), "p95_ms": _percentile(durations), "ttft_p95_ms": _percentile(ttft_values), "input_tokens": input_tokens,
            "output_tokens": output_tokens, "tool_calls": tool_calls, "tool_errors": tool_errors,
        },
        "tasks": {**task_counts, "running": task_counts["running"], "failed": task_counts["failed"]},
        "recent_exceptions": {
            "request_5xx_24h": request_errors,
            "ai_failed_24h": turns - successes,
            "tool_errors_24h": tool_errors,
            "task_failed": task_counts["failed"],
            "task_degraded": task_counts["degraded"],
        },
        "storage": {"user_db_bytes": db_bytes, "observability_db_bytes": observability_storage_size(), "disk_total": disk.total, "disk_used": disk.used, "disk_free": disk.free},
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
    business_cutoff = _business_cutoff(selected)
    for user, path in iter_user_databases(username or None):
        rows.extend((str(user["username"]), row) for row in _trace_rows(path, cutoff=cutoff, model=model, limit=None))
    chats = [row for _, row in rows if str(row["event_type"]) == "chat"]
    turns = len(chats)
    success = sum(str(row["status"]) == "success" for row in chats)
    durations = [float(row["duration_ms"]) for row in chats if isinstance(row["duration_ms"], (int, float))]
    ttft_values: list[float] = []
    for row in chats:
        try:
            metadata = json.loads(str(row["metadata_json"] or "{}"))
            value = metadata.get("ttft_ms")
            if isinstance(value, (int, float)) and value >= 0:
                ttft_values.append(float(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    input_tokens = sum(_row_int(row, "input_tokens") for _, row in rows if str(row["event_type"]) == "chat")
    output_tokens = sum(_row_int(row, "output_tokens") for _, row in rows if str(row["event_type"]) == "chat")
    reasoning_tokens = sum(_row_int(row, "reasoning_tokens") for _, row in rows if str(row["event_type"]) == "chat")
    tool_calls = tool_errors = memory_writes = 0
    for user, path in iter_user_databases(username or None):
        try:
            with closing(server_runtime.connect(path)) as connection:
                tool_calls += int(connection.execute("SELECT COUNT(*) FROM chat_tool_runs WHERE datetime(created_at) >= datetime(?)", (business_cutoff,)).fetchone()[0])
                tool_errors += int(connection.execute("SELECT COUNT(*) FROM chat_tool_runs WHERE datetime(created_at) >= datetime(?) AND status NOT IN ('ok','cache_hit','confirmation_required')", (business_cutoff,)).fetchone()[0])
                memory_writes += int(connection.execute("SELECT COUNT(*) FROM user_memories WHERE datetime(created_at) >= datetime(?)", (business_cutoff,)).fetchone()[0])
        except sqlite3.Error:
            continue
    models: dict[tuple[str, str, str], dict[str, Any]] = {}
    priced = 0
    total_chat = 0
    estimated_cost = 0.0
    for _, row in rows:
        if str(row["event_type"]) != "chat":
            continue
        dimensions = _trace_dimensions(row)
        key = (dimensions["provider_name"], str(row["model"] or "unknown"), dimensions["business_key"])
        item = models.setdefault(key, {"model": key[1], **dimensions, "turns": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "estimated_cost_usd": None})
        item["turns"] += 1
        item["input_tokens"] += _row_int(row, "input_tokens")
        item["output_tokens"] += _row_int(row, "output_tokens")
        item["reasoning_tokens"] += _row_int(row, "reasoning_tokens")
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
        "p50_latency_ms": _percentile(durations, .50),
        "p95_latency_ms": _percentile(durations), "ttft_p50_ms": _percentile(ttft_values, .50),
        "ttft_p95_ms": _percentile(ttft_values), "ttft_count": len(ttft_values), "tool_calls": tool_calls,
        "tool_errors": tool_errors, "memory_writes": memory_writes, "models": list(models.values()),
        "estimated_cost_usd": round(estimated_cost, 8) if priced else None,
        "cost_coverage_percent": round(priced / total_chat * 100, 2) if total_chat else 0,
        "pricing_configured": bool(load_pricing()),
    }


def _metric_bucket_key(value: Any, window: str) -> str:
    parsed = _parse_time(value)
    if parsed is not None:
        if window == "24h":
            return parsed.replace(minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
        return parsed.astimezone(_DISPLAY_TZ).date().isoformat()
    text = str(value or "")
    return text[:13] if window == "24h" else text[:10]


def ai_metrics(*, window: str = "24h", username: str = "", model: str = "") -> dict[str, Any]:
    selected = bounded_window(window)
    # AI traces are observability records and are persisted in UTC.
    cutoff = _cutoff(selected)
    buckets: dict[str, dict[str, Any]] = {}
    for user, path in iter_user_databases(username or None):
        for row in _trace_rows(path, cutoff=cutoff, model=model, limit=None):
            if str(row["event_type"]) != "chat":
                continue
            key = _metric_bucket_key(row["finished_at"] or row["started_at"], selected)
            item = buckets.setdefault(key, {"bucket_start": key, "turns": 0, "success": 0, "failed": 0, "latencies": [], "ttft": [], "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0})
            item["turns"] += 1
            if str(row["status"]) == "success":
                item["success"] += 1
            else:
                item["failed"] += 1
            if isinstance(row["duration_ms"], (int, float)):
                item["latencies"].append(float(row["duration_ms"]))
            item["input_tokens"] += _row_int(row, "input_tokens")
            item["output_tokens"] += _row_int(row, "output_tokens")
            item["reasoning_tokens"] += _row_int(row, "reasoning_tokens")
            try:
                value = json.loads(str(row["metadata_json"] or "{}")).get("ttft_ms")
                if isinstance(value, (int, float)) and value >= 0:
                    item["ttft"].append(float(value))
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
    series = []
    for key in sorted(buckets):
        item = buckets[key]
        series.append({
            "bucket_start": key, "turns": item["turns"], "success": item["success"], "failed": item["failed"],
            "success_rate": round(item["success"] / item["turns"], 4) if item["turns"] else 0,
            "p50_latency_ms": _percentile(item["latencies"], .50), "p95_latency_ms": _percentile(item["latencies"]),
            "ttft_p50_ms": _percentile(item["ttft"], .50), "ttft_p95_ms": _percentile(item["ttft"]),
            "input_tokens": item["input_tokens"], "output_tokens": item["output_tokens"], "reasoning_tokens": item["reasoning_tokens"],
        })
    summary = ai_usage(window=selected, username=username, model=model)
    return {"window": selected, "granularity": "hour" if selected == "24h" else "day", "summary": summary, "series": series}


def user_metrics(*, window: str = "24h") -> dict[str, Any]:
    selected = bounded_window(window)
    now = datetime.now(timezone.utc)
    cutoff = now - WINDOWS[selected]
    users = list(auth.list_users())
    registered = active = 0
    registration_buckets: dict[str, int] = {}
    activity_buckets: dict[str, int] = {}
    for user in users:
        created = _parse_time(user.get("created_at"))
        last_active = _parse_time(user.get("last_active") or user.get("last_login"))
        if created and created >= cutoff:
            registered += 1
            key = _metric_bucket_key(created, selected)
            registration_buckets[key] = registration_buckets.get(key, 0) + 1
        if last_active and last_active >= cutoff:
            active += 1
            key = _metric_bucket_key(last_active, selected)
            activity_buckets[key] = activity_buckets.get(key, 0) + 1
    return {
        "window": selected, "granularity": "hour" if selected == "24h" else "day",
        "total": len(users), "active": active, "registered": registered,
        "dau": _active_count(users, timedelta(days=1)), "wau": _active_count(users, timedelta(days=7)),
        "mau": _active_count(users, timedelta(days=30)),
        "series": [{"bucket_start": key, "registered": registration_buckets.get(key, 0), "active": activity_buckets.get(key, 0)} for key in sorted(set(registration_buckets) | set(activity_buckets))],
    }


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def tool_metrics(*, window: str = "24h", username: str = "") -> dict[str, Any]:
    selected = bounded_window(window)
    cutoff = _business_cutoff(selected)
    grouped: dict[str, dict[str, Any]] = {}
    series: dict[str, dict[str, Any]] = {}
    for _, path in iter_user_databases(username or None):
        try:
            with closing(server_runtime.connect(path)) as connection:
                rows = connection.execute(
                    "SELECT tool_name, status, duration_ms, created_at FROM chat_tool_runs WHERE datetime(created_at) >= datetime(?)",
                    (cutoff,),
                ).fetchall()
        except sqlite3.Error:
            continue
        for row in rows:
            name = str(row["tool_name"])
            item = grouped.setdefault(name, {"tool": name, "calls": 0, "success": 0, "failed": 0, "latencies": []})
            item["calls"] += 1
            if str(row["status"]) in {"ok", "cache_hit"}:
                item["success"] += 1
            elif str(row["status"]) != "confirmation_required":
                item["failed"] += 1
            if isinstance(row["duration_ms"], (int, float)):
                item["latencies"].append(float(row["duration_ms"]))
            key = _metric_bucket_key(row["created_at"], selected)
            point = series.setdefault(key, {"bucket_start": key, "calls": 0, "success": 0, "failed": 0})
            point["calls"] += 1
            point["success"] += int(str(row["status"]) in {"ok", "cache_hit"})
            point["failed"] += int(str(row["status"]) not in {"ok", "cache_hit", "confirmation_required"})
    items = []
    for item in grouped.values():
        item["p95_ms"] = _percentile(item.pop("latencies"))
        item["error_rate"] = round(item["failed"] / item["calls"], 4) if item["calls"] else 0
        items.append(item)
    items.sort(key=lambda item: (-item["calls"], item["tool"]))
    return {"window": selected, "granularity": "hour" if selected == "24h" else "day", "items": items, "series": [series[key] for key in sorted(series)]}


def list_traces(*, username: str = "", request_id: str = "", status: str = "", model: str = "", window: str = "24h", limit: int = 100) -> dict[str, Any]:
    selected = bounded_window(window)
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for user, path in iter_user_databases(username or None):
        user_name = str(user["username"])
        for row in _trace_rows(path, cutoff=_cutoff(selected), model=model):
            if str(row["event_type"]) != "chat" or (request_id and str(row["request_id"] or "") != request_id) or (status and str(row["status"]) != status):
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
            grouped[key].update(_trace_dimensions(row))
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
        for item, row in zip(timeline, selected):
            item.update(_trace_dimensions(row))
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
    "ai_metrics", "ai_usage", "bounded_limit", "bounded_window", "iter_user_databases", "list_logs",
    "list_traces", "overview", "request_metrics", "tool_metrics", "trace_detail", "user_metrics", "version_sha",
]


def request_metrics(*, window: str = "24h") -> dict[str, Any]:
    return stored_request_metrics(bounded_window(window))
