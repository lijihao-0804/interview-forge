"""Contract checks for the production FastAPI route assembly.

These tests intentionally use synthetic users and patched service boundaries;
the legacy StudyHandler is not involved.
"""
from __future__ import annotations

import threading
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
             patch("interview_forge.api.routers.leetcode.invalidate_learning"):
            response = self.client.post("/api/leetcode/sync", json={"full": False})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"ok": True, "solved_added": 1, "sync_errors": []})
        adapter.assert_awaited_once_with(credentials, db_path=self.db_path, full=False)

    def test_leetcode_connect_runs_status_check_off_event_loop(self):
        thread_names = []

        def status_check(_credentials):
            thread_names.append(threading.current_thread().name)
            return {"connected": True, "user_name": "alice", "num_solved": 1}

        with patch("interview_forge.api.support.current_user", return_value=USER), \
             patch("interview_forge.api.routers.leetcode.user_db", return_value=self.db_path), \
             patch("interview_forge.api.routers.leetcode.set_credentials"), \
             patch("interview_forge.api.routers.leetcode.get_credentials", return_value={"leetcode_session": "saved"}), \
             patch("interview_forge.api.routers.leetcode.leetcode_status", side_effect=status_check), \
             patch("interview_forge.api.routers.leetcode.lc_status_invalidate"), \
             patch("interview_forge.api.routers.leetcode.invalidate_dashboard"):
            response = self.client.post("/api/leetcode/connect", json={"leetcode_session": "saved"})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(thread_names)
        self.assertNotEqual(thread_names[0], threading.current_thread().name)

    def test_study_export_and_plan_pin_delegate_to_service(self):
        with patch("interview_forge.api.support.current_user", return_value=USER), \
             patch("interview_forge.api.routers.study.user_db", return_value=self.db_path), \
             patch("interview_forge.api.routers.study.export_database", return_value=b"sqlite-snapshot"):
            exported = self.client.get("/api/export?kind=db")
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.content, b"sqlite-snapshot")
        self.assertIn("hot100-study.db", exported.headers["content-disposition"])

        with patch("interview_forge.api.support.current_user", return_value=USER), \
             patch("interview_forge.api.routers.study.user_db", return_value=self.db_path), \
             patch("interview_forge.api.routers.study.pin_plan", return_value={"pinned": True, "problem_id": 1, "for_date": "2099-01-02"}) as pin, \
             patch("interview_forge.api.routers.study.invalidate_learning"):
            pinned = self.client.post("/api/plan/pin", json={"problem_id": 1})
        self.assertEqual(pinned.status_code, 201)
        self.assertTrue(pinned.json()["pinned"])
        pin.assert_called_once_with(1, self.db_path)

    def test_fastapi_error_paths_remain_explicit(self):
        self.assertEqual(self.client.get("/api/not-a-route").status_code, 404)
        self.assertEqual(self.client.post("/api/logout").status_code, 401)
        self.assertEqual(self.client.get("/api/leetcode/sync/status").status_code, 401)
