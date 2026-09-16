"""Durable, low-cardinality observability storage.

Only aggregate request data is written here.  Raw JSONL remains the detailed
diagnostic source, while this store is the bounded source for dashboards and
historical request metrics.
"""
from __future__ import annotations

import json
import os
import queue
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from zoneinfo import ZoneInfo
    _DISPLAY_TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # pragma: no cover - minimal Python installations
    _DISPLAY_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")

from interview_forge.core.paths import DATA_DIR
from interview_forge.db.observability_schema import ensure_observability_schema

# Fixed histogram upper bounds make percentile estimates explicit and
# scientifically distinguishable from an average.  The final ``inf`` bucket
# captures slow/error requests beyond the last bound.
HISTOGRAM_BOUNDS_MS = (50, 100, 250, 500, 1000, 2000, 5000, 10000, 30000, 60000)
_HISTOGRAM_KEYS = tuple(str(value) for value in HISTOGRAM_BOUNDS_MS) + ("inf",)
_METRICS_QUEUE: queue.Queue[tuple[tuple[Any, ...], dict[str, Any]] | None] = queue.Queue(maxsize=1024)
_METRICS_WORKER: threading.Thread | None = None
_METRICS_LOCK = threading.Lock()
_METRICS_STOP = threading.Event()
_METRICS_WRITE_LOCK = threading.Lock()


def observability_db_path() -> Path:
    configured = os.environ.get("INTERVIEW_FORGE_OBSERVABILITY_DB", "").strip()
    return Path(configured) if configured else DATA_DIR / "observability.db"


def normalize_route(route: str, path: str = "") -> str:
    """Return a FastAPI route template with a conservative fallback."""
    value = str(route or "").strip()
    if value and value.startswith("/") and "{" in value:
        return value[:256]
    value = str(path or value or "/")
    parts = []
    for part in value.split("/"):
        if not part:
            continue
        if len(part) > 64 or part.isdigit() or _looks_like_identifier(part):
            part = "{id}"
        parts.append(part)
    return "/" + "/".join(parts) if parts else "/"


def _looks_like_identifier(value: str) -> bool:
    if len(value) < 12:
        return False
    hex_chars = set("0123456789abcdefABCDEF-")
    return all(char in hex_chars for char in value) and any(char.isdigit() for char in value)


def _bucket_start(value: datetime | None = None) -> str:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    # Keep the persisted UTC bucket sortable and parseable by browser Date.
    # ``timespec="hours"`` produces ``T14+00:00``, which is not a portable
    # ISO datetime for JavaScript consumers.
    return current.isoformat(timespec="seconds")


def _histogram(value: Any = None) -> dict[str, int]:
    try:
        parsed = json.loads(str(value or "{}")) if not isinstance(value, dict) else value
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = {}
    return {key: max(0, int(parsed.get(key, 0) or 0)) for key in _HISTOGRAM_KEYS}


def _histogram_for(value_ms: float) -> dict[str, int]:
    result = {key: 0 for key in _HISTOGRAM_KEYS}
    for upper in HISTOGRAM_BOUNDS_MS:
        if value_ms <= upper:
            result[str(upper)] += 1
            return result
    result["inf"] += 1
    return result


def _merge_histograms(target: dict[str, int], source: Any) -> None:
    other = _histogram(source)
    for key in _HISTOGRAM_KEYS:
        target[key] = target.get(key, 0) + other[key]


def _connect() -> sqlite3.Connection:
    path = observability_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=2.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 2000")
    connection.execute("PRAGMA journal_mode = WAL")
    ensure_observability_schema(connection)
    return connection


def _record_request_sync_unlocked(*, route: str, path: str, method: str, status: int, elapsed_ms: float) -> None:
    """Best-effort aggregate write; observability can never fail a request."""
    try:
        status_code = int(status)
        histogram = _histogram_for(max(0.0, float(elapsed_ms)))
        with closing(_connect()) as connection:
            # Serialize the read/merge/write sequence so concurrent requests
            # do not both observe an absent bucket and lose one INSERT.
            connection.execute("BEGIN IMMEDIATE")
            bucket = _bucket_start()
            normalized_route = normalize_route(route, path)
            normalized_method = str(method or "GET")[:16].upper()
            row = connection.execute(
                "SELECT * FROM request_metric_buckets WHERE bucket_start = ? AND route = ? AND method = ?",
                (bucket, normalized_route, normalized_method),
            ).fetchone()
            merged = _histogram(row["latency_histogram_json"] if row else "{}")
            _merge_histograms(merged, histogram)
            counts = (
                int(200 <= status_code < 300), int(300 <= status_code < 400),
                int(400 <= status_code < 500), int(status_code >= 500),
            )
            if row is None:
                connection.execute(
                    """INSERT INTO request_metric_buckets(
                        bucket_start, route, method, request_count,
                        status_2xx, status_3xx, status_4xx, status_5xx,
                        latency_count, latency_sum_ms, latency_histogram_json
                    ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, 1, ?, ?)""",
                    (bucket, normalized_route, normalized_method, *counts,
                     max(0.0, float(elapsed_ms)), json.dumps(merged, separators=(",", ":"))),
                )
            else:
                connection.execute(
                    """UPDATE request_metric_buckets SET
                        request_count = request_count + 1,
                        status_2xx = status_2xx + ?, status_3xx = status_3xx + ?,
                        status_4xx = status_4xx + ?, status_5xx = status_5xx + ?,
                        latency_count = latency_count + 1,
                        latency_sum_ms = latency_sum_ms + ?, latency_histogram_json = ?
                       WHERE bucket_start = ? AND route = ? AND method = ?""",
                    (*counts, max(0.0, float(elapsed_ms)), json.dumps(merged, separators=(",", ":")),
                     bucket, normalized_route, normalized_method),
                )
            connection.commit()
    except Exception:
        return


def _record_request_sync(*, route: str, path: str, method: str, status: int, elapsed_ms: float) -> None:
    with _METRICS_WRITE_LOCK:
        _record_request_sync_unlocked(
            route=route, path=path, method=method, status=status, elapsed_ms=elapsed_ms
        )


def record_request(*, route: str, path: str, method: str, status: int, elapsed_ms: float) -> None:
    """Synchronous compatibility API for scripts/tests and explicit callers."""
    _record_request_sync(route=route, path=path, method=method, status=status, elapsed_ms=elapsed_ms)


def _metrics_worker_loop() -> None:
    while True:
        item = _METRICS_QUEUE.get()
        try:
            if item is None:
                return
            args, kwargs = item
            _record_request_sync(*args, **kwargs)
        finally:
            _METRICS_QUEUE.task_done()


def start_metrics_writer() -> None:
    global _METRICS_WORKER
    with _METRICS_LOCK:
        if _METRICS_WORKER is not None and _METRICS_WORKER.is_alive():
            return
        _METRICS_STOP.clear()
        _METRICS_WORKER = threading.Thread(
            target=_metrics_worker_loop, name="interviewforge-metrics", daemon=True
        )
        _METRICS_WORKER.start()


def stop_metrics_writer(timeout: float = 2.0) -> None:
    global _METRICS_WORKER
    worker = _METRICS_WORKER
    if worker is None:
        return
    # Give queued writes a bounded opportunity to flush before stopping.
    deadline = time.monotonic() + max(0.0, timeout)
    while _METRICS_QUEUE.unfinished_tasks and time.monotonic() < deadline:
        time.sleep(0.02)
    # If a slow database write exceeded the bound, drop queued (not currently
    # executing) work so the sentinel can always reach the worker.
    while _METRICS_QUEUE.unfinished_tasks and time.monotonic() >= deadline:
        try:
            pending = _METRICS_QUEUE.get_nowait()
        except queue.Empty:
            break
        if pending is not None:
            _METRICS_QUEUE.task_done()
    _METRICS_STOP.set()
    _METRICS_QUEUE.put(None)
    worker.join(max(0.1, max(0.0, deadline - time.monotonic())))
    with _METRICS_LOCK:
        if not worker.is_alive():
            _METRICS_WORKER = None


def enqueue_request(*, route: str, path: str, method: str, status: int, elapsed_ms: float) -> bool:
    """Enqueue best-effort metrics without waiting for SQLite."""
    # The FastAPI lifespan owns the worker lifecycle.  Do not implicitly spawn
    # a process-lifetime thread when a test/client calls middleware without
    # entering lifespan.
    if _METRICS_WORKER is None or not _METRICS_WORKER.is_alive():
        return False
    try:
        _METRICS_QUEUE.put_nowait(((), {
            "route": route, "path": path, "method": method,
            "status": status, "elapsed_ms": elapsed_ms,
        }))
        return True
    except queue.Full:
        return False


def _cutoff(window: str) -> datetime:
    durations = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
    return datetime.now(timezone.utc) - durations.get(window, durations["24h"])


def _parse_bucket_start(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _display_bucket_start(value: Any, *, day: bool) -> str | None:
    parsed = _parse_bucket_start(value)
    if parsed is None:
        return None
    if day:
        return parsed.astimezone(_DISPLAY_TZ).date().isoformat()
    return parsed.replace(minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def _percentile(histogram: dict[str, int], percentile: float) -> float | None:
    total = sum(histogram.values())
    if not total:
        return None
    rank = max(1, int((total * percentile) + 0.999999))
    cumulative = 0
    for key in _HISTOGRAM_KEYS:
        cumulative += histogram.get(key, 0)
        if cumulative >= rank:
            return None if key == "inf" else float(key)
    return None


def _aggregate(rows: Iterable[sqlite3.Row]) -> dict[str, Any]:
    total = {"request_count": 0, "2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0, "latency_count": 0, "latency_sum_ms": 0.0}
    histogram = {key: 0 for key in _HISTOGRAM_KEYS}
    for row in rows:
        total["request_count"] += int(row["request_count"] or 0)
        for key, column in (("2xx", "status_2xx"), ("3xx", "status_3xx"), ("4xx", "status_4xx"), ("5xx", "status_5xx")):
            total[key] += int(row[column] or 0)
        total["latency_count"] += int(row["latency_count"] or 0)
        total["latency_sum_ms"] += float(row["latency_sum_ms"] or 0)
        _merge_histograms(histogram, row["latency_histogram_json"])
    total.update({"p50_ms": _percentile(histogram, .50), "p95_ms": _percentile(histogram, .95), "p99_ms": _percentile(histogram, .99)})
    total["avg_ms"] = round(total["latency_sum_ms"] / total["latency_count"], 2) if total["latency_count"] else None
    total["5xx_rate"] = round(total["5xx"] / total["request_count"], 4) if total["request_count"] else 0
    total.pop("latency_sum_ms")
    total.pop("latency_count")
    return total


def request_metrics(window: str = "24h") -> dict[str, Any]:
    selected = window if window in {"24h", "7d", "30d"} else "24h"
    cutoff_dt = _cutoff(selected).replace(minute=0, second=0, microsecond=0)
    granularity = "hour" if selected == "24h" else "day"
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM request_metric_buckets WHERE bucket_start >= ? ORDER BY bucket_start ASC",
            # Include the preceding hour so legacy ``T14+00:00`` rows at the
            # boundary are still readable; the precise filter below removes
            # anything older than the requested bucket.
            ((cutoff_dt - timedelta(hours=1)).isoformat(timespec="seconds"),),
        ).fetchall()
    filtered_rows: list[sqlite3.Row] = []
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        parsed = _parse_bucket_start(row["bucket_start"])
        if parsed is None or parsed < cutoff_dt:
            continue
        key = _display_bucket_start(row["bucket_start"], day=granularity == "day")
        if key is None:
            continue
        filtered_rows.append(row)
        grouped.setdefault(key, []).append(row)
    series = [{"bucket_start": key, **_aggregate(grouped[key])} for key in sorted(grouped)]
    endpoints: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in filtered_rows:
        endpoints.setdefault((str(row["method"]), str(row["route"])), []).append(row)
    endpoint_items = []
    for (method, route), endpoint_rows in endpoints.items():
        values = _aggregate(endpoint_rows)
        endpoint_items.append({"method": method, "route": route, **values, "error_count": values["4xx"] + values["5xx"]})
    endpoint_items.sort(key=lambda item: (-item["request_count"], item["route"]))
    slowest = sorted(endpoint_items, key=lambda item: (-(item["p95_ms"] or -1), item["route"]))
    return {
        "window": selected, "granularity": granularity, "series": series,
        "totals": _aggregate(filtered_rows), "endpoints": endpoint_items[:50], "slowest_endpoints": slowest[:10],
        "histogram_bounds_ms": list(HISTOGRAM_BOUNDS_MS),
    }


def storage_size() -> int:
    try:
        return observability_db_path().stat().st_size
    except OSError:
        return 0


__all__ = [
    "HISTOGRAM_BOUNDS_MS", "normalize_route", "observability_db_path", "record_request",
    "request_metrics", "storage_size", "enqueue_request", "start_metrics_writer", "stop_metrics_writer",
]
