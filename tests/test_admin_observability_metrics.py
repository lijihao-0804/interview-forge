from __future__ import annotations

import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime
from interview_forge.observability.ai_trace import TraceRecorder
from interview_forge.observability.store import normalize_route, record_request, request_metrics
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
            row = connection.execute("SELECT metadata_json FROM ai_trace_events WHERE trace_id = 'trace-ttft'").fetchone()
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


if __name__ == "__main__":
    unittest.main()
