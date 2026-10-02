import unittest
from urllib.parse import unquote

from scripts.benchmarks.http_load import ROOT, SOLUTION_PATH


class BenchmarkPathTests(unittest.TestCase):
    def test_solution_probe_matches_a_real_tracked_page(self):
        decoded = unquote(SOLUTION_PATH)
        self.assertEqual(decoded, "/books/hot100/03-题解/01-哈希表/0001-两数之和.html")
        self.assertTrue((ROOT / decoded.lstrip("/")).is_file())


if __name__ == "__main__":
    unittest.main()
