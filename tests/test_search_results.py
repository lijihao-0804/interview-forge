from pathlib import Path
import unittest
from unittest.mock import patch

from interview_forge.services import community


ROOT = Path(__file__).resolve().parents[1]


class SearchResultsTests(unittest.TestCase):
    def test_server_search_returns_bounded_items_and_total_match_count(self):
        entries = [
            {
                "id": f"module:{index:03d}",
                "title": f"needle chapter {index}",
                "url": f"module/{index}.html",
                "module_title": "测试模块",
                "text": "needle appears in this chapter",
            }
            for index in range(65)
        ]
        with patch.object(community, "_load_search_index", return_value=entries):
            items, total = community.search_index_server_with_count("needle")

        self.assertEqual(len(items), 60)
        self.assertEqual(total, 65)

    def test_search_page_reports_counts_and_explicit_empty_state(self):
        source = (ROOT / "scripts" / "build" / "build_library.py").read_text(encoding="utf-8")
        self.assertIn('id="searchSummary"', source)
        self.assertIn("renderSearchSummary(count,truncated)", source)
        self.assertIn("Boolean(d.has_more)", source)
        self.assertIn("没有找到匹配章节", source)


if __name__ == "__main__":
    unittest.main()
