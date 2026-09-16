from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime
from interview_forge.observability.ai_trace import TraceRecorder
from interview_forge.observability.logging import close_log_handlers
from interview_forge.observability.logging import log_event
from interview_forge.services.auth import create_session, create_user, user_db_path
from interview_forge.services import admin_observability
from interview_forge.services import admin_operations
from interview_forge.ai.config_store import AIConfigError


class AdminV2BackendTests(unittest.TestCase):
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
        self.admin = create_user("AdminV2", "password-1", role="admin")
        self.user = create_user("UserV2", "password-2")
        self.admin_token = create_session(int(self.admin["id"]))
        self.user_token = create_session(int(self.user["id"]))
        self.log_path = root / "logs" / "app.jsonl"
        self.env = patch.dict(os.environ, {"INTERVIEW_FORGE_LOG_PATH": str(self.log_path)}, clear=False)
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

    def _admin(self):
        client = self.client
        client.cookies.set("forge_session", self.admin_token)
        return client

    def test_admin_guard_and_request_id_log(self):
        self.assertEqual(self.client.get("/api/admin/overview").status_code, 401)
        self.client.cookies.set("forge_session", self.user_token)
        self.assertEqual(self.client.get("/api/admin/overview").status_code, 403)
        response = self._admin().get("/api/health", headers={"X-Request-ID": "admin-v2-test"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Request-ID"), "admin-v2-test")
        logs = self._admin().get("/api/admin/logs", params={"request_id": "admin-v2-test"})
        self.assertEqual(logs.status_code, 200)
        self.assertTrue(any(item.get("event") == "api_request" for item in logs.json()["items"]))

    def test_log_redaction_is_applied_on_write_and_admin_read(self):
        log_event("redaction_test", module="test", password="secret-password", token="secret-token", safe_value="visible")
        payload = self._admin().get("/api/admin/logs", params={"event": "redaction_test"})
        self.assertEqual(payload.status_code, 200)
        rendered = json.dumps(payload.json(), ensure_ascii=False)
        self.assertNotIn("secret-password", rendered)
        self.assertNotIn("secret-token", rendered)
        self.assertIn("[redacted]", rendered)

    def test_trace_aggregation_and_detail_never_returns_bodies(self):
        db = user_db_path("UserV2")
        recorder = TraceRecorder(
            user_db=db, trace_id="trace-admin-v2", session_id="session-1",
            request_id="request-1", provider="openai-compatible", model="test-model",
        )
        recorder.record_chat(status="success", duration_ms=12, usage={"input_tokens": 10, "output_tokens": 4, "content": "secret"})
        recorder.record_llm_round(round_index=1, status="success", duration_ms=8, usage={"input_tokens": 10, "output_tokens": 4})
        from interview_forge.core.runtime import server_runtime as runtime
        with closing(runtime.connect(db)) as connection:
            connection.execute(
                "INSERT INTO chat_tool_runs(id, session_id, turn_id, tool_name, tool_kind, arguments_json, status, result_meta_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("run-1", "session-1", "trace-admin-v2", "get_problem", "read", '{"password":"secret"}', "ok", '{"result":"secret"}', "2026-09-14T01:00:00+00:00"),
            )
            connection.execute(
                "INSERT INTO chat_action_requests(id, session_id, turn_id, tool_name, arguments_json, status, confirmation_text, created_at, expires_at, result_meta_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("action-1", "session-1", "trace-admin-v2", "mark_problem", '{"token":"secret"}', "pending", "confirm", "2026-09-14T01:00:00+00:00", "2026-09-15T01:00:00+00:00", '{"body":"secret"}'),
            )
            connection.commit()
        client = self._admin()
        traces = client.get("/api/admin/ai/traces", params={"username": "UserV2"})
        self.assertEqual(traces.status_code, 200)
        payload = json.dumps(traces.json(), ensure_ascii=False)
        self.assertNotIn("secret", payload)
        detail = client.get("/api/admin/ai/traces/trace-admin-v2", params={"username": "UserV2"})
        self.assertEqual(detail.status_code, 200)
        detail_payload = json.dumps(detail.json(), ensure_ascii=False)
        self.assertNotIn("arguments_json", detail_payload)
        self.assertNotIn("result_meta_json", detail_payload)
        self.assertNotIn("secret", detail_payload)
        usage = client.get("/api/admin/ai/usage", params={"username": "UserV2"})
        self.assertEqual(usage.status_code, 200)
        self.assertEqual(usage.json()["turns"], 1)

    def test_observability_ui_uses_separate_assets_and_safe_text_rendering(self):
        root = Path(__file__).resolve().parents[1]
        page = (root / "pages" / "admin.html").read_text(encoding="utf-8")
        script = (root / "assets" / "admin-observability.js").read_text(encoding="utf-8")
        self.assertIn("../assets/admin-observability.css?v=1", page)
        self.assertIn("../assets/admin-observability.js?v=2", page)
        self.assertIn("data-admin-v2", page)
        self.assertIn("textContent", script)
        self.assertNotIn("innerHTML", script)

    def test_operations_ui_is_separate_and_does_not_use_html_injection(self):
        root = Path(__file__).resolve().parents[1]
        page = (root / "pages" / "admin.html").read_text(encoding="utf-8")
        script = (root / "assets" / "admin-operations.js").read_text(encoding="utf-8")
        self.assertIn("../assets/admin-operations.css?v=2", page)
        self.assertIn("../assets/admin-operations.js?v=2", page)
        self.assertIn("data-admin-operations", page)
        self.assertNotIn("innerHTML", script)

    def test_operations_projections_and_diagnostics_are_metadata_only(self):
        db = user_db_path("UserV2")
        with closing(server_runtime.connect(db)) as connection:
            connection.execute(
                "INSERT INTO ai_tasks(task_id, task, status, snapshot_hash, prompt_version, model_key, created_at, context_preview, fallback_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("task-1", "analysis", "failed", "hash", "v1", "model", "2026-09-14T01:00:00+00:00", "private context", "{}"),
            )
            connection.commit()
        client = self._admin()
        tasks = client.get("/api/admin/tasks", params={"kind": "ai", "username": "UserV2"})
        self.assertEqual(tasks.status_code, 200)
        self.assertIn("task-1", json.dumps(tasks.json()))
        self.assertNotIn("private context", json.dumps(tasks.json()))
        detail = client.get("/api/admin/users/UserV2/detail")
        self.assertEqual(detail.status_code, 200)
        detail_text = json.dumps(detail.json(), ensure_ascii=False)
        self.assertNotIn("content", detail_text)
        self.assertNotIn("display_text", detail_text)
        memory = client.get("/api/admin/memory/summary")
        self.assertEqual(memory.status_code, 200)
        system = client.get("/api/admin/system/info")
        self.assertEqual(system.status_code, 200)
        self.assertNotIn("API_KEY", json.dumps(system.json()))
        diagnostics = client.post("/api/admin/system/diagnostics")
        self.assertEqual(diagnostics.status_code, 200)
        self.assertIn(diagnostics.json()["status"], {"ok", "warning", "failed"})

    @staticmethod
    def _fake_runtime(*, source="db", model="deepseek-v4-flash", provider_id="provider-1", provider_name="DeepSeek", vendor="deepseek", enabled=True, configured=True):
        return SimpleNamespace(
            config=SimpleNamespace(enabled=enabled, configured=configured, provider="openai-compatible"),
            provider_id=provider_id if source == "db" else None,
            provider_name=provider_name,
            vendor=vendor,
            protocol="openai_chat",
            model=model,
            reasoning_policy=SimpleNamespace(mode="auto", effort=None, budget_tokens=None),
            config_source=source,
        )

    def test_system_info_uses_effective_managed_route_and_separates_legacy_env(self):
        env_runtime = self._fake_runtime(source="env", model="gpt-5.6-luna", provider_name="openai", vendor="openai", provider_id=None)

        def resolve(business_key):
            return self._fake_runtime() if business_key == "chat" else env_runtime

        legacy = SimpleNamespace(enabled=True, configured=True, provider="openai", model="gpt-5.6-luna")
        with patch.object(admin_operations, "resolve_ai_runtime", side_effect=resolve), patch.object(admin_operations, "load_ai_config", return_value=legacy):
            payload = self._admin().get("/api/admin/system/info")
        self.assertEqual(payload.status_code, 200)
        ai = payload.json()["ai"]
        self.assertEqual(ai["routes"]["chat"]["model"], "deepseek-v4-flash")
        self.assertEqual(ai["routes"]["chat"]["source"], "db")
        self.assertEqual(ai["legacy_fallback"]["model"], "gpt-5.6-luna")
        self.assertEqual(ai["legacy_fallback"]["source"], "legacy_env")

    def test_system_info_shows_env_fallback_when_managed_route_is_missing(self):
        env_runtime = self._fake_runtime(source="env", model="gpt-5.6-luna", provider_name="openai", vendor="openai", provider_id=None)
        legacy = SimpleNamespace(enabled=True, configured=True, provider="openai", model="gpt-5.6-luna")
        with patch.object(admin_operations, "resolve_ai_runtime", return_value=env_runtime), patch.object(admin_operations, "load_ai_config", return_value=legacy):
            payload = self._admin().get("/api/admin/system/info")
        self.assertEqual(payload.status_code, 200)
        self.assertEqual(payload.json()["ai"]["routes"]["chat"]["source"], "env")
        self.assertEqual(payload.json()["ai"]["routes"]["chat"]["model"], "gpt-5.6-luna")

    def test_system_info_contains_safe_error_when_one_managed_route_is_broken(self):
        env_runtime = self._fake_runtime(source="env", model="gpt-5.6-luna", provider_name="openai", vendor="openai", provider_id=None)

        def resolve(business_key):
            if business_key == "chat":
                raise AIConfigError("AI 模型已停用")
            return env_runtime

        with patch.object(admin_operations, "resolve_ai_runtime", side_effect=resolve):
            payload = self._admin().get("/api/admin/system/info")
        self.assertEqual(payload.status_code, 200)
        self.assertEqual(payload.json()["ai"]["routes"]["chat"]["status"], "error")
        self.assertEqual(payload.json()["ai"]["routes"]["chat"]["error_category"], "model_disabled")

    def test_diagnostics_does_not_fail_whole_ai_when_managed_routes_work_without_env(self):
        managed = self._fake_runtime()
        missing_env = SimpleNamespace(enabled=False, configured=False, provider="", model="")
        with patch.object(admin_operations, "resolve_ai_runtime", return_value=managed), patch.object(admin_operations, "load_ai_config", return_value=missing_env):
            payload = self._admin().post("/api/admin/system/diagnostics")
        self.assertEqual(payload.status_code, 200)
        data = payload.json()
        self.assertNotEqual(data["status"], "failed")
        checks = {item["name"]: item for item in data["checks"]}
        self.assertEqual(checks["ai_route_chat"]["status"], "ok")
        self.assertEqual(checks["ai_legacy_fallback"]["status"], "warning")

    def test_request_stats_reads_all_recent_request_events_not_the_log_page_limit(self):
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).isoformat()
        rows = iter(
            {"time": timestamp, "event": "api_request", "status": 200, "elapsed_ms": 3}
            for _ in range(501)
        )
        with patch.object(admin_observability, "_iter_log_records", return_value=rows):
            total, errors, p95 = admin_observability._request_stats()
        self.assertEqual(total, 501)
        self.assertEqual(errors, 0)
        self.assertEqual(p95, 3.0)

    def test_trace_detail_queries_trace_id_directly_beyond_recent_page_window(self):
        db = user_db_path("UserV2")
        rows = []
        for index in range(2001):
            rows.append((
                "trace-old" if index == 0 else f"trace-{index}",
                "session-1", "request-1", "chat", "chat_turn", "success",
                "openai-compatible", "test-model", None,
                "2026-09-14T01:00:00+00:00", "2026-09-14T01:00:00+00:00",
                10, 1, 1, 0, None, "{}",
            ))
        with closing(server_runtime.connect(db)) as connection:
            connection.executemany(
                """INSERT INTO ai_trace_events(
                    trace_id, session_id, request_id, event_type, name, status,
                    provider, model, round_index, started_at, finished_at,
                    duration_ms, input_tokens, output_tokens, reasoning_tokens,
                    error_code, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            connection.commit()
        detail = admin_observability.trace_detail("trace-old", username="UserV2")
        self.assertIsNotNone(detail)
        self.assertEqual(detail["trace_id"], "trace-old")
        self.assertEqual(len(detail["timeline"]), 1)


if __name__ == "__main__":
    unittest.main()
