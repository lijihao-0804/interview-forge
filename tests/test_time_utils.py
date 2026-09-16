from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


class FrontendTimeUtilsTests(unittest.TestCase):
    def test_formatter_is_browser_timezone_independent(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [node, str(root / "tests" / "test_time_utils.js")],
            cwd=root, capture_output=True, text=True, check=True,
        )
        self.assertIn("regression PASS", result.stdout)

    def test_user_facing_time_consumers_load_shared_formatter(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for relative in ("index.html", "cockpit.html", "pages/history.html", "pages/admin.html", "pages/ai-assistant.html"):
            source = (root / relative).read_text(encoding="utf-8")
            self.assertIn("time-utils.js?v=1", source, relative)
        self.assertIn('"/assets/time-utils.js?v=1"', (root / "interview_forge" / "api" / "routers" / "static.py").read_text(encoding="utf-8"))
        self.assertIn('time-utils.js?v=1', (root / "scripts" / "build" / "build_library.py").read_text(encoding="utf-8"))

    def test_business_date_heatmap_does_not_parse_date_only_in_browser_timezone(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "index.html").read_text(encoding="utf-8")
        self.assertIn("InterviewForgeTime.weekdayForDate(days[0].date)", source)
        self.assertNotIn("new Date(`${days[0].date}T00:00:00`)", source)


if __name__ == "__main__":
    unittest.main()
