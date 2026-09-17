import json
import re
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

from interview_forge.core.problem_catalog import PROBLEMS, problem_filename


ROOT = Path(__file__).resolve().parents[1]


class Hot100ProblemOrderTests(unittest.TestCase):
    def test_canonical_order_matches_requested_hot100_sequence(self):
        expected = [
            1, 49, 128, 283, 11, 15, 42, 3, 438, 560, 239, 76,
            53, 56, 189, 238, 41, 73, 54, 48, 240, 160, 206, 234,
            141, 142, 21, 2, 19, 24, 25, 138, 148, 23, 146, 94, 104,
            226, 101, 543, 102, 108, 98, 230, 199, 114, 105, 437, 236,
            124, 200, 994, 207, 208, 46, 78, 17, 39, 22, 79, 131, 51,
            35, 74, 34, 33, 153, 4, 20, 155, 394, 739, 84, 215, 347,
            295, 121, 55, 45, 763, 70, 118, 198, 279, 322, 139, 300,
            152, 416, 32, 62, 64, 5, 1143, 72, 136, 169, 75, 31, 287,
        ]
        self.assertEqual([int(problem["id"]) for problem in PROBLEMS], expected)
        self.assertEqual(len(expected), 100)

    def test_dashboard_and_solution_sidebars_use_the_same_order(self):
        dashboard = (ROOT / "index.html").read_text(encoding="utf-8")
        match = re.search(r"const problems=(.*?);", dashboard)
        self.assertIsNotNone(match)
        dashboard_ids = [item["id"] for item in json.loads(match.group(1))]
        catalog_ids = [int(problem["id"]) for problem in PROBLEMS]
        self.assertEqual(dashboard_ids, catalog_ids)

        by_folder = {}
        for problem in PROBLEMS:
            by_folder.setdefault(str(problem["folder"]), []).append(problem)

        pages_root = ROOT / "books" / "hot100" / "03-题解"
        for page in pages_root.rglob("*.html"):
            expected = by_folder.get(page.parent.name)
            if not expected:
                continue
            soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
            actual_ids = [
                int(re.match(r"(\d{4})-", Path(link["href"]).name).group(1))
                for link in soup.select(".sol-rail-left .sol-nav-item")
            ]
            self.assertEqual(actual_ids, [int(item["id"]) for item in expected], page.name)

        # Every canonical entry must have a generated page, including the
        # replacement binary-search problem 34.
        for problem in PROBLEMS:
            page = pages_root / str(problem["folder"]) / problem_filename(problem).replace(".md", ".html")
            self.assertTrue(page.exists(), page)


if __name__ == "__main__":
    unittest.main()
