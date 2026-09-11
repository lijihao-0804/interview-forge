"""Contract checks for the production FastAPI route assembly.

These tests intentionally use synthetic users and patched service boundaries;
the legacy StudyHandler is not involved.
"""
from __future__ import annotations

import threading
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from interview_forge.api.app import app


USER = {"id": 7, "username": "alice", "nickname": "Alice", "lang": "java", "role": "user"}
ADMIN = {**USER, "role": "admin"}


class FastApiRouteContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)
        self.db_path = Path("data") / "__fastapi_contract_test__.db"

    def tearDown(self):
        self.client.close()

    def test_domain_paths_are_explicit_and_not_legacy_catch_all(self):
        paths = app.openapi()["paths"]
        required = {
            "/api/health", "/api/me", "/api/login", "/api/register", "/api/profile",
            "/api/bootstrap", "/api/dashboard", "/api/complete", "/api/library",
            "/api/leetcode/status", "/api/leetcode/sync", "/api/coach/analytics",
            "/api/coach/analyze", "/api/weather", "/api/weather/preferences",
            "/api/chat/messages", "/api/chat/send", "/api/admin/users",
        }
        self.assertTrue(required.issubset(paths))
        self.assertFalse(any("legacy" in getattr(route.endpoint, "__module__", "") for route in app.routes))

    def test_unauthenticated_contracts_and_public_static(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/me").status_code, 401)
        for path in ("/api/dashboard", "/api/library", "/api/weather", "/api/chat/messages",
                     "/api/leetcode/status", "/api/coach/analytics", "/api/admin/users"):
            self.assertEqual(self.client.get(path).status_code, 401, path)
        self.assertEqual(self.client.get("/pages/login.html").status_code, 200)
        self.assertEqual(self.client.get("/cockpit.html", follow_redirects=False).status_code, 307)
        self.assertEqual(self.client.post("/api/login", content=b"{}", headers={"content-type": "application/json"}).status_code, 400)

    def test_authenticated_domain_success_and_validation_errors(self):
        with patch("interview_forge.api.support.current_user", return_value=USER), \
             patch("interview_forge.api.routers.study.user_db", return_value=self.db_path), \
             patch("interview_forge.api.routers.study.dashboard_cached", return_value={"ok": True}), \
             patch("interview_forge.api.routers.weather.weather_for_user", return_value={"location": {"name": "南京"}}), \
             patch("interview_forge.api.routers.community.search_index_server", return_value=[]):
            self.assertEqual(self.client.get("/api/dashboard").json(), {"ok": True})
            self.assertEqual(self.client.get("/api/weather").status_code, 200)
            self.assertEqual(self.client.get("/api/search?q=x").status_code, 200)
            self.assertEqual(self.client.get("/api/chat/messages?after=1&before=2").status_code, 400)
            self.assertEqual(self.client.get("/api/weather/locations?q=x").status_code, 400)

    def test_admin_boundary_and_admin_service_success(self):
        with patch("interview_forge.api.support.current_user", return_value=USER):
            self.assertEqual(self.client.get("/api/admin/users").status_code, 403)
        with patch("interview_forge.api.support.current_user", return_value=ADMIN), \
             patch("interview_forge.api.routers.admin.list_users", return_value=[]):
            response = self.client.get("/api/admin/users")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"items": []})

    def test_leetcode_clear_service_error_keeps_http_contract(self):
        with patch("interview_forge.api.support.current_user", return_value=USER), \
             patch("interview_forge.api.routers.leetcode.user_db", return_value=self.db_path), \
             patch("interview_forge.api.routers.leetcode.clear_credentials", side_effect=RuntimeError("boom")):
            response = self.client.post("/api/leetcode/clear")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "服务暂时不可用"})

    def test_leetcode_sync_awaits_existing_async_adapter(self):
        credentials = {"leetcode_session": "saved"}
        adapter = AsyncMock(return_value={"solved_added": 1, "sync_errors": []})
        with patch("interview_forge.api.support.current_user", return_value=USER), \
             patch("interview_forge.api.routers.leetcode.user_db", return_value=self.db_path), \
             patch("interview_forge.api.routers.leetcode.get_credentials", return_value=credentials), \
             patch("interview_forge.api.routers.leetcode.leetcode_sync_async", adapter), \
             patch("interview_forge.services.leetcode.leetcode_sync", side_effect=AssertionError("sync implementation must not be called by this route")), \
             patch("interview_forge.api.routers.leetcode.invalidate_learning"):
            response = self.client.post("/api/leetcode/sync", json={"full": False})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"ok": True, "solved_added": 1, "sync_errors": []})
        adapter.assert_awaited_once_with(credentials, db_path=self.db_path, full=False)

    def test_leetcode_status_and_background_sync_contracts(self):
        credentials = {"leetcode_session": "saved"}
        with patch("interview_forge.api.support.current_user", return_value=USER), \
             patch("interview_forge.api.routers.leetcode.user_db", return_value=self.db_path), \
             patch("interview_forge.api.routers.leetcode.get_credentials", return_value=credentials), \
             patch("interview_forge.api.routers.leetcode.lc_status_cached", return_value={"connected": True}):
            status = self.client.get("/api/leetcode/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json(), {"credentials_saved": True, "connected": True})

        with patch("interview_forge.api.support.current_user", return_value=USER), \
             patch("interview_forge.api.routers.leetcode.user_db", return_value=self.db_path), \
             patch("interview_forge.api.routers.leetcode.get_credentials", return_value=credentials), \
             patch("interview_forge.api.routers.leetcode.task_manager.submit", return_value="task-1") as submit:
            queued = self.client.post("/api/leetcode/sync", json={"async": True})
        self.assertEqual(queued.status_code, 201)
        self.assertEqual(queued.json(), {"ok": True, "task_id": "task-1"})
        submit.assert_called_once()

    def test_study_write_routes_use_service_contracts(self):
        cases = (
            ("/api/complete", {"problem_id": 1}, "complete_round", {"ok": True}),
            ("/api/mark", {"target_type": "problem", "target_id": "1", "mark": "weak"}, "set_mark", {"ok": True}),
            ("/api/settings", {"key": "daily_goal_rounds", "value": "3"}, "set_setting", {"ok": True}),
            ("/api/submit", {"problem_id": 1, "status": "ac", "lang": "python"}, "record_submission", {"ok": True}),
            ("/api/plan/pin", {"problem_id": 1}, "pin_problem_for_tomorrow", {"pinned": True, "problem_id": 1}),
        )
        for path, payload, service_name, result in cases:
            with self.subTest(path=path), \
                 patch("interview_forge.api.support.current_user", return_value=USER), \
                 patch("interview_forge.api.routers.study.user_db", return_value=self.db_path), \
                 patch(f"interview_forge.api.routers.study.{service_name}", return_value=result), \
                 patch("interview_forge.api.routers.study.invalidate_learning"):
                response = self.client.post(path, json=payload)
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json(), result)

    def test_bootstrap_settings_and_analytics_contracts(self):
        with patch("interview_forge.api.support.current_user", return_value=USER), \
             patch("interview_forge.api.routers.study.user_db", return_value=self.db_path), \
             patch("interview_forge.api.routers.study.dashboard_cached", return_value={"dashboard": True}), \
             patch("interview_forge.api.routers.study.daily_data", return_value={"daily": True}), \
             patch("interview_forge.api.routers.study.get_settings", return_value={"theme": "light"}), \
             patch("interview_forge.api.routers.study.ai_capability", return_value={"allowed": True}), \
             patch("interview_forge.api.routers.study.get_ai_quota", return_value={"remaining": 3}), \
             patch("interview_forge.api.routers.analytics.user_db", return_value=self.db_path), \
             patch("interview_forge.api.routers.analytics.analytics_cached", return_value={"summary": {"completed": 1}}):
            bootstrap = self.client.get("/api/bootstrap")
            settings = self.client.get("/api/settings")
            analytics = self.client.get("/api/coach/analytics")
        self.assertEqual(bootstrap.status_code, 200)
        self.assertEqual(bootstrap.json()["dashboard"], {"dashboard": True})
        self.assertEqual(settings.json(), {"theme": "light"})
        self.assertEqual(analytics.json(), {"summary": {"completed": 1}})

    def test_export_database_snapshot_preserves_source(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as source:
            source_path = Path(source.name)
        backup_path = None
        try:
            connection = sqlite3.connect(source_path)
            try:
                connection.execute("CREATE TABLE marker (value TEXT)")
                connection.execute("INSERT INTO marker VALUES ('ok')")
                connection.commit()
            finally:
                connection.close()
            original = source_path.read_bytes()
            with patch("interview_forge.api.support.current_user", return_value=USER), \
                 patch("interview_forge.api.routers.study.user_db", return_value=source_path):
                response = self.client.get("/api/export?kind=db")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "application/octet-stream")
            self.assertIn("hot100-study.db", response.headers["content-disposition"])
            self.assertGreater(len(response.content), 0)
            self.assertEqual(source_path.read_bytes(), original)
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as backup:
                backup_path = Path(backup.name)
            backup_path.write_bytes(response.content)
            connection = sqlite3.connect(backup_path)
            try:
                self.assertEqual(connection.execute("SELECT value FROM marker").fetchone()[0], "ok")
            finally:
                connection.close()
        finally:
            source_path.unlink(missing_ok=True)
            if backup_path is not None:
                backup_path.unlink(missing_ok=True)

    def test_leetcode_connect_runs_status_check_off_event_loop(self):
        thread_names = []

        def status_check(_credentials, _timeout=20):
            thread_names.append(threading.current_thread().name)
            return {"connected": True, "user_name": "alice", "num_solved": 1}

        with patch("interview_forge.api.support.current_user", return_value=USER), \
             patch("interview_forge.api.routers.leetcode.user_db", return_value=self.db_path), \
             patch("interview_forge.api.routers.leetcode.set_credentials"), \
             patch("interview_forge.api.routers.leetcode.get_credentials", return_value={"leetcode_session": "saved"}), \
             patch("interview_forge.services.leetcode.leetcode_status", side_effect=status_check), \
             patch("interview_forge.api.routers.leetcode.lc_status_invalidate"), \
             patch("interview_forge.api.routers.leetcode.invalidate_dashboard"):
            response = self.client.post("/api/leetcode/connect", json={"leetcode_session": "saved"})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(thread_names)
        self.assertNotEqual(thread_names[0], threading.current_thread().name)

    def test_study_export_and_plan_pin_delegate_to_service(self):
        with patch("interview_forge.api.support.current_user", return_value=USER), \
             patch("interview_forge.api.routers.study.user_db", return_value=self.db_path), \
             patch("interview_forge.api.routers.study.export_database_snapshot", return_value=b"sqlite-snapshot"):
            exported = self.client.get("/api/export?kind=db")
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.content, b"sqlite-snapshot")
        self.assertIn("hot100-study.db", exported.headers["content-disposition"])

        with patch("interview_forge.api.support.current_user", return_value=USER), \
             patch("interview_forge.api.routers.study.user_db", return_value=self.db_path), \
             patch("interview_forge.api.routers.study.pin_problem_for_tomorrow", return_value={"pinned": True, "problem_id": 1, "for_date": "2099-01-02"}) as pin, \
             patch("interview_forge.api.routers.study.invalidate_learning"):
            pinned = self.client.post("/api/plan/pin", json={"problem_id": 1})
        self.assertEqual(pinned.status_code, 201)
        self.assertTrue(pinned.json()["pinned"])
        pin.assert_called_once_with(1, self.db_path)

    def test_fastapi_error_paths_remain_explicit(self):
        self.assertEqual(self.client.get("/api/not-a-route").status_code, 404)
        self.assertEqual(self.client.post("/api/logout").status_code, 401)
        self.assertEqual(self.client.get("/api/leetcode/sync/status").status_code, 401)
