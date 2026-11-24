"""限时模拟进行中会话：按账号保存、跨设备恢复的服务层测试。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from interview_forge.core.runtime import server_runtime
from interview_forge.services import study


class MockSessionStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Path(tempfile.mkdtemp()) / "user.db"
        with server_runtime.connect(self.db) as connection:
            connection.commit()
        self.ids = list(study.PROBLEM_BY_ID)[:2]

    def payload(self, **overrides):
        base = {
            "version": 1,
            "problem_ids": self.ids,
            "index": 1,
            "done": [self.ids[0]],
            "skip": [],
            "minutes": 60,
            "duration_ms": 3_600_000,
            "remaining_ms": 1_800_000,
        }
        base.update(overrides)
        return base

    def test_save_then_get_returns_remaining_from_server_clock(self):
        saved = study.save_mock_session(self.payload(), self.db)
        self.assertTrue(saved["saved"])
        got = study.get_mock_session(self.db)
        session = got["session"]
        self.assertEqual(session["problem_ids"], self.ids)
        self.assertEqual(session["index"], 1)
        self.assertEqual(session["done"], [self.ids[0]])
        self.assertLessEqual(got["remaining_ms"], 1_800_000)
        self.assertGreater(got["remaining_ms"], 1_700_000)

    def test_clear_removes_session(self):
        study.save_mock_session(self.payload(), self.db)
        self.assertTrue(study.clear_mock_session(self.db)["cleared"])
        self.assertIsNone(study.get_mock_session(self.db)["session"])

    def test_invalid_payloads_rejected(self):
        for bad in (
            self.payload(problem_ids=[999_999]),
            self.payload(index=9),
            self.payload(remaining_ms=9_999_999_999),
            self.payload(done=[999_999]),
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    study.save_mock_session(bad, self.db)

    def test_settings_api_hides_internal_mock_state(self):
        study.save_mock_session(self.payload(), self.db)
        settings = study.get_settings(self.db)
        self.assertNotIn("mock_active_session", settings)
        self.assertNotIn("mock_recent_rounds", settings)


if __name__ == "__main__":
    unittest.main()
