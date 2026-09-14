"""Schema for process-wide, low-cardinality observability aggregates.

This database is intentionally separate from every user's learning database.
The schema is idempotent so a deployment can create it on first request and
upgrade it without touching learning data.
"""
from __future__ import annotations

OBSERVABILITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS request_metric_buckets (
    bucket_start TEXT NOT NULL,
    route TEXT NOT NULL,
    method TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    status_2xx INTEGER NOT NULL DEFAULT 0,
    status_3xx INTEGER NOT NULL DEFAULT 0,
    status_4xx INTEGER NOT NULL DEFAULT 0,
    status_5xx INTEGER NOT NULL DEFAULT 0,
    latency_count INTEGER NOT NULL DEFAULT 0,
    latency_sum_ms REAL NOT NULL DEFAULT 0,
    latency_histogram_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (bucket_start, route, method)
);
CREATE INDEX IF NOT EXISTS ix_request_metric_bucket
    ON request_metric_buckets(bucket_start);
CREATE INDEX IF NOT EXISTS ix_request_metric_route
    ON request_metric_buckets(route, bucket_start);
"""


def ensure_observability_schema(connection) -> None:
    connection.executescript(OBSERVABILITY_SCHEMA)
    connection.commit()


__all__ = ["OBSERVABILITY_SCHEMA", "ensure_observability_schema"]
