"""Contract checks for the production FastAPI route assembly.

These tests intentionally use synthetic users and patched service boundaries;
the legacy StudyHandler is not involved.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

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
