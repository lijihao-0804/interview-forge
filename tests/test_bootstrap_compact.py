"""Regression tests for the cockpit's compact bootstrap payload."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from interview_forge.api.app import app

USER = {"id": 7, "username": "alice", "nickname": "Alice", "lang": "java", "role": "user"}

BIG_DASHBOARD = {
    "summary": {"today_viewed": 2, "completed_problems": 42, "total_rounds": 50},
    "language_summary": {"java": 3},
    "problems": {str(i): {"rounds": i % 3} for i in range(100)},
    "activity": [{"date": f"2026-10-{d:02d}", "solved": d} for d in range(1, 29)],
    "recent_submissions": [{"problem_id": i, "status": "ac"} for i in range(500)],
}

BIG_DAILY = {
    "today": "2026-11-21",
    "summary": {"due": 12, "overdue": 3, "problems": 12},
    "problems": [{"id": i, "title": f"题 {i}", "due_date": "2026-11-21"} for i in range(12)],
    "relearn": [{"id": i} for i in range(12)],
    "contents": [{"content_id": str(i)} for i in range(12)],
}


class BootstrapCompactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, raise_server_exceptions=False)
        self.patches = [
            patch("interview_forge.api.support.current_user", return_value=USER),
            patch("interview_forge.api.routers.study.user_db", return_value=Path("synthetic.db")),
            patch("interview_forge.api.routers.study.dashboard_cached", return_value=BIG_DASHBOARD),
            patch("interview_forge.api.routers.study.daily_data", return_value=BIG_DAILY),
            patch("interview_forge.api.routers.study.get_settings", return_value={"theme": "light"}),
            patch("interview_forge.api.routers.study.ai_capability", return_value={"visible": True, "can_analyze": False}),
            patch("interview_forge.api.routers.study.get_ai_quota", return_value={"limit": 3, "used": 0, "remaining": 3, "reset_at": "x"}),
            patch("interview_forge.api.routers.study.effective_ai_daily_limit", return_value=3),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.client.close()

    def test_full_bootstrap_keeps_every_field(self) -> None:
        body = self.client.get("/api/bootstrap").json()
        self.assertEqual(set(body["dashboard"]), set(BIG_DASHBOARD))
        self.assertEqual(set(body["daily"]), set(BIG_DAILY))

    def test_compact_bootstrap_returns_only_what_the_cockpit_renders(self) -> None:
        body = self.client.get("/api/bootstrap?compact=1").json()
        self.assertEqual(set(body["dashboard"]), {"summary", "language_summary"})
        self.assertEqual(body["daily"]["today"], "2026-11-21")
        self.assertEqual(len(body["daily"]["problems"]), 3)
        self.assertNotIn("contents", body["daily"])
        self.assertNotIn("relearn", body["daily"])
        self.assertEqual(body["settings"], {"theme": "light"})
        self.assertIn("capabilities", body)


if __name__ == "__main__":
    unittest.main()