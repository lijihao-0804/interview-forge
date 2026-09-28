import sqlite3
import tempfile
import unittest
from datetime import timedelta, timezone
from pathlib import Path

from interview_forge.db.connection import _migrate_legacy_review_cards, connect


class FSRSStateMigrationTests(unittest.TestCase):
    def test_connect_seeds_fsrs_cards_from_an_existing_legacy_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "legacy.db"
            connection = sqlite3.connect(path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE study_events (
                        id INTEGER PRIMARY KEY, problem_id INTEGER NOT NULL,
                        action TEXT NOT NULL, studied_at TEXT NOT NULL,
                        study_date TEXT NOT NULL, round_no INTEGER,
                        source TEXT NOT NULL DEFAULT 'learning-site'
                    );
                    CREATE TABLE submissions (
                        id INTEGER PRIMARY KEY, problem_id INTEGER NOT NULL,
                        status TEXT NOT NULL, lang TEXT NOT NULL DEFAULT '',
                        runtime_ms INTEGER, memory_kb INTEGER,
                        submitted_at TEXT NOT NULL,
                        source TEXT NOT NULL DEFAULT 'manual'
                    );
                    CREATE TABLE content_events (
                        id INTEGER PRIMARY KEY, module_id TEXT NOT NULL,
                        content_id TEXT NOT NULL, action TEXT NOT NULL,
                        studied_at TEXT NOT NULL, study_date TEXT NOT NULL,
                        round_no INTEGER
                    );
                    INSERT INTO submissions(problem_id, status, submitted_at)
                    VALUES
                        (1, 'ac', '2026-09-01T16:30:00+00:00'),
                        (1, 'ac', '2026-09-04T12:00:00+08:00');
                    INSERT INTO content_events(
                        module_id, content_id, action, studied_at, study_date, round_no
                    ) VALUES
                        ('module', 'module:01', 'complete', '2026-09-01T12:00:00+08:00', '2026-09-01', 1),
                        ('module', 'module:01', 'complete', '2026-09-05T12:00:00+08:00', '2026-09-05', 2);
                    """
                )
                connection.commit()
            finally:
                connection.close()

            initialized = connect(path)
            try:
                problem = initialized.execute(
                    "SELECT due_date, stability, reps FROM review_cards "
                    "WHERE target_type = 'problem' AND target_id = '1'"
                ).fetchone()
                content = initialized.execute(
                    "SELECT due_date, stability, reps FROM review_cards "
                    "WHERE target_type = 'content' AND target_id = 'module:01'"
                ).fetchone()
                self.assertEqual(tuple(problem), ("2026-09-07", 3.0, 2))
                self.assertEqual(tuple(content), ("2026-09-12", 7.0, 2))
                self.assertEqual(
                    initialized.execute("SELECT COUNT(*) FROM review_logs").fetchone()[0],
                    0,
                )
            finally:
                initialized.close()

    def test_legacy_due_dates_are_preserved_without_synthetic_ratings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "user.db"
            connection = connect(path)
            try:
                connection.executemany(
                    """INSERT INTO submissions(
                           problem_id, status, submitted_at, source
                       ) VALUES (1, 'ac', ?, 'manual')""",
                    (
                        ("2026-09-01T12:00:00+08:00",),
                        ("2026-09-04T12:00:00+08:00",),
                    ),
                )
                connection.executemany(
                    """INSERT INTO content_events(
                           module_id, content_id, action, studied_at, study_date, round_no
                       ) VALUES ('module', 'module:01', 'complete', ?, ?, ?)""",
                    (
                        ("2026-09-01T12:00:00+08:00", "2026-09-01", 1),
                        ("2026-09-05T12:00:00+08:00", "2026-09-05", 2),
                    ),
                )
                connection.commit()

                shanghai = timezone(timedelta(hours=8), "Asia/Shanghai")
                _migrate_legacy_review_cards(connection, shanghai)
                problem = connection.execute(
                    "SELECT * FROM review_cards WHERE target_type = 'problem' AND target_id = '1'"
                ).fetchone()
                content = connection.execute(
                    "SELECT * FROM review_cards WHERE target_type = 'content' AND target_id = 'module:01'"
                ).fetchone()
                self.assertEqual((problem["reps"], problem["stability"], problem["due_date"]), (2, 3.0, "2026-09-07"))
                self.assertEqual((content["reps"], content["stability"], content["due_date"]), (2, 7.0, "2026-09-12"))
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM review_logs").fetchone()[0], 0)

                connection.execute(
                    "UPDATE review_cards SET stability = 12 WHERE target_type = 'problem' AND target_id = '1'"
                )
                _migrate_legacy_review_cards(connection, shanghai)
                preserved = connection.execute(
                    "SELECT stability FROM review_cards WHERE target_type = 'problem' AND target_id = '1'"
                ).fetchone()[0]
                self.assertEqual(preserved, 12.0)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
