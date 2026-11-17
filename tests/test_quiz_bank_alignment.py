import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class QuizBankAlignmentTests(unittest.TestCase):
    def test_published_keys_and_answer_indices(self):
        keys = set()
        for filename in ("quiz.json", "ai-exam-quiz.json"):
            bank = json.loads((ROOT / "assets" / filename).read_text(encoding="utf-8"))
            self.assertEqual(bank["total"], len(bank["questions"]))
            for question in bank["questions"]:
                with self.subTest(key=question["key"]):
                    self.assertNotIn(question["key"], keys)
                    keys.add(question["key"])
                    options = question["options"]
                    answer = question["answer"]
                    self.assertIsInstance(answer, list)
                    self.assertTrue(answer)
                    self.assertTrue(all(type(i) is int and 0 <= i < len(options) for i in answer))
                    if not question.get("multi"):
                        self.assertEqual(len(answer), 1)
                        matches = [i for i, text in enumerate(options) if text == options[answer[0]]]
                        self.assertEqual(question.get("equivalent_answers", answer), matches)

    def test_multiline_heading_and_options_keep_their_own_answers(self):
        from tools.parse_ai_quiz import parse_by_headings

        snapshot = json.loads((ROOT / "data/ai_exam/zero2leetcode_ai_pages.json").read_text(encoding="utf-8"))
        page = next(p for p in snapshot if p["company"] == "alibaba" and p["slug"] == "agent-20260815")
        questions = parse_by_headings(page)
        bagging, bounds = questions[6:8]
        self.assertEqual(len(bagging["options"]), 4)
        self.assertNotIn("lower_bound", bagging["explain"])
        self.assertTrue(bounds["stem"].startswith("lower_bound"))
        self.assertIn("lower(6)-lower(2)", bounds["options"][1])
        self.assertEqual(bounds["answer"], [0, 1])
