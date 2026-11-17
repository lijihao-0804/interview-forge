import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from interview_forge.core.runtime import server_runtime
from interview_forge.services.study import library_data, record_content_view, record_view


class LibraryResumeTests(unittest.TestCase):
    def test_existing_account_uses_a_view_even_when_completion_is_newer(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "legacy.db"
            with closing(server_runtime.connect(db)) as connection:
                connection.executemany(
                    """INSERT INTO content_events(module_id, content_id, action, studied_at, study_date, round_no)
                       VALUES ('java-core', ?, ?, ?, '2026-01-01', ?)""",
                    [("java-core:01", "view", "2026-01-01T10:00:00", None),
                     ("java-core:02", "complete", "2026-01-01T10:01:00", 1)],
                )
                connection.commit()
            self.assertEqual(library_data(db)["resume"]["chapter_url"], "java-core/chapter-01.html")

    def test_views_are_account_scoped_and_include_rapid_revisits(self):
        with tempfile.TemporaryDirectory() as directory:
            alice = Path(directory) / "alice.db"
            bob = Path(directory) / "bob.db"
            self.assertIsNone(library_data(alice)["resume"])
            self.assertTrue(record_content_view("java-core", "java-core:01", alice))
            self.assertTrue(record_content_view("java-core", "java-core:02", alice))
            self.assertFalse(record_content_view("java-core", "java-core:01", alice))
            resume = library_data(alice)["resume"]
            self.assertEqual(resume["book_url"], "java-core/index.html")
            self.assertEqual(resume["chapter_url"], "java-core/chapter-01.html")
            self.assertTrue(resume["book_title"] and resume["chapter_title"])
            self.assertIsNone(library_data(bob)["resume"])
            self.assertTrue(record_view(1, bob))
            self.assertIn("0001-", library_data(bob)["resume"]["chapter_url"])
            self.assertEqual(library_data(alice)["resume"], resume)
