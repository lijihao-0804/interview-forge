from __future__ import annotations

import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime
from interview_forge.observability.ai_trace import TraceRecorder
from interview_forge.observability import store as observability_store
from interview_forge.observability.store import _bucket_start, normalize_route, record_request, request_metrics
from interview_forge.observability.logging import close_log_handlers
from interview_forge.services import admin_observability
from interview_forge.services.auth import create_session, create_user, user_db_path


class AdminObservabilityMetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.old_provider = server_runtime._provider
        self.old_values = dict(server_runtime._values)
        self.old_ready = default_runtime._AUTH_READY
        default_runtime._AUTH_READY = False
        default_runtime.AUTH_DB_PATH = root / "auth.db"
        default_runtime.USERS_DIR = root / "users"
        default_runtime.USERS_DIR.mkdir()
        server_runtime.bind_provider(lambda: default_runtime)
        self.admin = create_user("MetricAdmin", "password-1", role="admin")
        self.user = create_user("MetricUser", "password-2")
        self.admin_token = create_session(int(self.admin["id"]))
        self.user_token = create_session(int(self.user["id"]))
        self.env = patch.dict(os.environ, {
            "INTERVIEW_FORGE_OBSERVABILITY_DB": str(root / "observability.db"),
            "INTERVIEW_FORGE_LOG_PATH": str(root / "logs" / "app.jsonl"),
        }, clear=False)
        self.env.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        close_log_handlers()
        self.env.stop()
        default_runtime._AUTH_READY = self.old_ready
        server_runtime._provider = self.old_provider
        server_runtime._values = self.old_values
        self.temp.cleanup()

    def admin_client(self):
        self.client.cookies.set("forge_session", self.admin_token)
        return self.client

    def test_request_aggregate_normalizes_dynamic_routes_and_percentiles(self):
        self.assertEqual(normalize_route("/api/chat/sessions/{session_id}/stream", "/api/chat/sessions/secret/stream"), "/api/chat/sessions/{session_id}/stream")
        for status, elapsed in ((200, 20), (201, 90), (404, 400), (500, 8000)):
            record_request(route="/api/items/{item_id}", path="/api/items/1234567890abcdef", method="GET", status=status, elapsed_ms=elapsed)
        payload = request_metrics("24h")
        self.assertEqual(payload["totals"]["request_count"], 4)
        self.assertEqual(payload["totals"]["2xx"], 2)
        self.assertEqual(payload["totals"]["4xx"], 1)
        self.assertEqual(payload["totals"]["5xx"], 1)
        self.assertEqual(payload["totals"]["5xx_rate"], 0.25)
        self.assertEqual(len(payload["endpoints"]), 1)
        self.assertEqual(payload["endpoints"][0]["route"], "/api/items/{item_id}")
        self.assertIsNotNone(payload["totals"]["p95_ms"])

    def test_observability_buckets_are_complete_iso_and_beijing_day_keys(self):
        sample = datetime.fromisoformat("2026-09-16T14:37:12+00:00")
        self.assertEqual(_bucket_start(sample), "2026-09-16T14:00:00+00:00")
        self.assertEqual(
            admin_observability._metric_bucket_key("2026-09-16T14:37:12+00:00", "24h"),
            "2026-09-16T14:00:00+00:00",
        )
        self.assertEqual(
            admin_observability._metric_bucket_key("2026-09-16T16:30:00+00:00", "7d"),
            "2026-09-17",
        )
        self.assertEqual(
            admin_observability._metric_bucket_key("2026-09-16T16:30:00+00:00", "30d"),
            "2026-09-17",
        )

        record_request(route="/api/health", path="/api/health", method="GET", status=200, elapsed_ms=10)
        series = request_metrics("24h")["series"]
        self.assertTrue(series)
        self.assertTrue(all(len(item["bucket_start"]) == 25 for item in series))
        self.assertTrue(all(item["bucket_start"].endswith("+00:00") for item in series))

    def test_request_metrics_reads_legacy_hour_shape_without_returning_it(self):
        legacy = "2026-09-16T14+00:00"
        with patch.object(observability_store, "_cutoff", return_value=datetime.fromisoformat("2026-09-16T14:00:00+00:00")):
            with closing(observability_store._connect()) as connection:
                connection.execute(
                    "INSERT INTO request_metric_buckets(bucket_start, route, method, request_count, status_2xx, status_3xx, status_4xx, status_5xx, latency_count, latency_sum_ms, latency_histogram_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (legacy, "/api/legacy", "GET", 1, 1, 0, 0, 0, 1, 12, '{"50":1}'),
                )
                connection.commit()
            payload = observability_store.request_metrics("24h")
        self.assertEqual(payload["series"][0]["bucket_start"], "2026-09-16T14:00:00+00:00")

    def test_request_metrics_uses_beijing_dates_for_day_series(self):
        rows = [
            ("2026-09-16T15:00:00+00:00", "/api/late", 1),
            ("2026-09-16T15:30:00+00:00", "/api/late", 2),
            ("2026-09-16T16:30:00+00:00", "/api/next", 1),
        ]
        with patch.object(observability_store, "_cutoff", return_value=datetime.fromisoformat("2026-09-15T00:00:00+00:00")):
            with closing(observability_store._connect()) as connection:
                for bucket, route, count in rows:
                    connection.execute(
                        "INSERT INTO request_metric_buckets(bucket_start, route, method, request_count, status_2xx, status_3xx, status_4xx, status_5xx, latency_count, latency_sum_ms, latency_histogram_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (bucket, route, "GET", count, count, 0, 0, 0, count, 10 * count, '{"50":%d}' % count),
                    )
                connection.commit()
            payload = observability_store.request_metrics("7d")
        self.assertEqual([item["bucket_start"] for item in payload["series"]], ["2026-09-16", "2026-09-17"])
        self.assertEqual([item["request_count"] for item in payload["series"]], [3, 1])

    def test_request_aggregate_concurrent_writes_keep_counts(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: record_request(route="/api/health", path="/api/health", method="GET", status=200, elapsed_ms=12), range(32)))
        self.assertEqual(request_metrics("24h")["totals"]["request_count"], 32)

    def test_metrics_contracts_permissions_and_empty_windows(self):
        self.assertEqual(self.client.get("/api/admin/metrics/requests").status_code, 401)
        self.client.cookies.set("forge_session", self.user_token)
        self.assertEqual(self.client.get("/api/admin/metrics/requests").status_code, 403)
        client = self.admin_client()
        for endpoint in ("/api/admin/metrics/requests", "/api/admin/metrics/ai", "/api/admin/metrics/users", "/api/admin/metrics/tools"):
            response = client.get(endpoint, params={"window": "30d"})
            self.assertEqual(response.status_code, 200, endpoint)
            self.assertEqual(response.json()["window"], "30d")
        self.assertEqual(client.get("/api/admin/metrics/requests", params={"window": "bad"}).json()["window"], "24h")

    def test_ai_ttft_is_persisted_as_safe_trace_metadata_and_aggregated(self):
        recorder = TraceRecorder(
            user_db=user_db_path("MetricUser"), trace_id="trace-ttft", request_id="req-ttft",
            provider="test", model="test-model",
        )
        recorder.record_chat(status="success", duration_ms=500, ttft_ms=123.4, usage={"input_tokens": 10, "output_tokens": 4})
        payload = self.admin_client().get("/api/admin/metrics/ai", params={"username": "MetricUser"}).json()
        self.assertEqual(payload["summary"]["ttft_count"], 1)
        self.assertEqual(payload["summary"]["ttft_p95_ms"], 123.4)
        with closing(server_runtime.connect(user_db_path("MetricUser"))) as connection:
            row = connection.execute("SELECT started_at, finished_at, metadata_json FROM ai_trace_events WHERE trace_id = 'trace-ttft'").fetchone()
        self.assertTrue(str(row["started_at"]).endswith("+00:00"))
        self.assertTrue(str(row["finished_at"]).endswith("+00:00"))
        self.assertEqual(json.loads(row["metadata_json"])["ttft_ms"], 123.4)

    def test_tool_and_user_metrics_are_metadata_only(self):
        with closing(server_runtime.connect(user_db_path("MetricUser"))) as connection:
            connection.execute(
                "INSERT INTO chat_tool_runs(id, session_id, turn_id, tool_name, tool_kind, arguments_json, status, duration_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("run-metric", "s", "t", "get_weather", "read", '{"secret":"hidden"}', "ok", 120, default_runtime.now_iso()),
            )
            connection.commit()
        client = self.admin_client()
        tools = client.get("/api/admin/metrics/tools", params={"username": "MetricUser"}).json()
        self.assertEqual(tools["items"][0]["tool"], "get_weather")
        self.assertEqual(tools["items"][0]["calls"], 1)
        users = client.get("/api/admin/metrics/users", params={"window": "30d"}).json()
        self.assertGreaterEqual(users["total"], 2)
        self.assertIn("dau", users)
        self.assertNotIn("hidden", json.dumps(tools, ensure_ascii=False))

    def test_overview_uses_aggregate_store_not_jsonl_scan(self):
        with patch.object(admin_observability, "_iter_log_records", side_effect=AssertionError("overview must not scan JSONL")):
            payload = admin_observability.overview()
        self.assertIn("requests", payload)
        self.assertIn("observability_db_bytes", payload["storage"])

    def test_business_cutoff_handles_beijing_midnight_and_mixed_offsets(self):
        with closing(server_runtime.connect(user_db_path("MetricUser"))) as connection:
            connection.executemany(
                "INSERT INTO chat_tool_runs(id, session_id, turn_id, tool_name, tool_kind, arguments_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("before-midnight", "s", "t", "get_weather", "read", "{}", "ok", "2026-09-15T16:29:59+00:00"),
                    ("at-midnight", "s", "t", "get_weather", "read", "{}", "ok", "2026-09-15T16:30:00+00:00"),
                ],
            )
            connection.commit()
        fixed_now = datetime.fromisoformat("2026-09-17T00:30:00+08:00")
        with patch.object(default_runtime, "business_now", return_value=fixed_now):
            cutoff = admin_observability._business_cutoff("24h")
            payload = admin_observability.tool_metrics(window="24h", username="MetricUser")
        self.assertEqual(cutoff, "2026-09-16T00:30:00+08:00")
        self.assertEqual(payload["items"][0]["calls"], 1)

        with closing(server_runtime.connect(user_db_path("MetricUser"))) as connection:
            connection.executemany(
                "INSERT INTO chat_tool_runs(id, session_id, turn_id, tool_name, tool_kind, arguments_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("before-evening", "s", "t", "get_problem", "read", "{}", "ok", "2026-09-16T15:29:59+00:00"),
                    ("at-evening", "s", "t", "get_problem", "read", "{}", "ok", "2026-09-16T15:30:00+00:00"),
                ],
            )
            connection.commit()
        fixed_evening = datetime.fromisoformat("2026-09-17T23:30:00+08:00")
        with patch.object(default_runtime, "business_now", return_value=fixed_evening):
            cutoff = admin_observability._business_cutoff("24h")
            payload = admin_observability.tool_metrics(window="24h", username="MetricUser")
        self.assertEqual(cutoff, "2026-09-16T23:30:00+08:00")
        self.assertEqual(payload["items"][0]["tool"], "get_problem")
        self.assertEqual(payload["items"][0]["calls"], 1)


if __name__ == "__main__":
    unittest.main()
