from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime
from interview_forge.observability.ai_trace import TraceRecorder
from interview_forge.observability.logging import close_log_handlers
from interview_forge.services.auth import create_session, create_user, user_db_path


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
        self.assertIn("/assets/admin-observability.css?v=1", page)
        self.assertIn("/assets/admin-observability.js?v=1", page)
        self.assertIn("data-admin-v2", page)
        self.assertIn("textContent", script)
        self.assertNotIn("innerHTML", script)


if __name__ == "__main__":
    unittest.main()
