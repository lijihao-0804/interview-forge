import json
import unittest
from pathlib import Path

from interview_forge.ai.chat.learning_context import select_learning_task
from interview_forge.ai.tools.registry import build_default_tool_registry


class AIToolDeterministicEvaluationTests(unittest.TestCase):
    def test_selection_fixture_is_bounded_and_registered(self):
        fixture_path = Path(__file__).parent / "fixtures" / "ai_tool_selection_cases.json"
        cases = json.loads(fixture_path.read_text(encoding="utf-8"))
        registered = {spec.name for spec in build_default_tool_registry().list_specs()}
        self.assertEqual(len(cases), 7)
        for case in cases:
            self.assertLessEqual(len(case["query"]), 120)
            self.assertTrue(set(case["expected_tools"]).issubset(registered))
            if not case.get("preloaded_learning_context"):
                if case["expected_tools"] == []:
                    self.assertIsNone(select_learning_task(case["query"]))

    def test_problem_tool_only_returns_links_and_never_opens_browser(self):
        source = (
            Path(__file__).parents[1] / "interview_forge" / "ai" / "tools" / "builtins" / "problem.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("webbrowser.open", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("题解正文", source)


if __name__ == "__main__":
    unittest.main()
