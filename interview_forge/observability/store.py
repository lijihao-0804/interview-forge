"""Durable, low-cardinality observability storage.

Only aggregate request data is written here.  Raw JSONL remains the detailed
diagnostic source, while this store is the bounded source for dashboards and
historical request metrics.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from interview_forge.core.paths import DATA_DIR
from interview_forge.db.observability_schema import ensure_observability_schema

# Fixed histogram upper bounds make percentile estimates explicit and
# scientifically distinguishable from an average.  The final ``inf`` bucket
# captures slow/error requests beyond the last bound.
HISTOGRAM_BOUNDS_MS = (50, 100, 250, 500, 1000, 2000, 5000, 10000, 30000, 60000)
_HISTOGRAM_KEYS = tuple(str(value) for value in HISTOGRAM_BOUNDS_MS) + ("inf",)


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
    return current.isoformat(timespec="hours")


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


def record_request(*, route: str, path: str, method: str, status: int, elapsed_ms: float) -> None:
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


def _cutoff(window: str) -> datetime:
    durations = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
    return datetime.now(timezone.utc) - durations.get(window, durations["24h"])


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
    cutoff = _cutoff(selected).isoformat(timespec="hours")
    granularity = "hour" if selected == "24h" else "day"
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM request_metric_buckets WHERE bucket_start >= ? ORDER BY bucket_start ASC",
            (cutoff,),
        ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        key = str(row["bucket_start"])
        if granularity == "day":
            key = key[:10]
        grouped.setdefault(key, []).append(row)
    series = [{"bucket_start": key, **_aggregate(bucket_rows)} for key, bucket_rows in grouped.items()]
    endpoints: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in rows:
        endpoints.setdefault((str(row["method"]), str(row["route"])), []).append(row)
    endpoint_items = []
    for (method, route), endpoint_rows in endpoints.items():
        values = _aggregate(endpoint_rows)
        endpoint_items.append({"method": method, "route": route, **values, "error_count": values["4xx"] + values["5xx"]})
    endpoint_items.sort(key=lambda item: (-item["request_count"], item["route"]))
    slowest = sorted(endpoint_items, key=lambda item: (-(item["p95_ms"] or -1), item["route"]))
    return {
        "window": selected, "granularity": granularity, "series": series,
        "totals": _aggregate(rows), "endpoints": endpoint_items[:50], "slowest_endpoints": slowest[:10],
        "histogram_bounds_ms": list(HISTOGRAM_BOUNDS_MS),
    }


def storage_size() -> int:
    try:
        return observability_db_path().stat().st_size
    except OSError:
        return 0


__all__ = [
    "HISTOGRAM_BOUNDS_MS", "normalize_route", "observability_db_path", "record_request",
    "request_metrics", "storage_size",
]
