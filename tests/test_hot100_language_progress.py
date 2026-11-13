"""Language attribution across Hot 100 submissions, manual review, and LeetCode sync."""
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from interview_forge.core.runtime import server_runtime
from interview_forge.services import leetcode, study
from interview_forge.services.submissions import (
    record_submission,
    submission_language_key,
)


class Hot100LanguageProgressTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db = Path(temporary.name) / "learner.db"

    def test_business_days_per_language_and_unattributed_history(self):
        submissions = [
            ("ac", "Java", "2026-09-01T15:59:00Z"),
            ("ac", "java", "2026-09-01T16:00:00Z"),
            ("ac", " JAVA ", "2026-09-02T22:30:00+08:00"),
            ("ac", "Java", "2026-09-02T15:59:00Z"),
            ("ac", "Python3", "2026-09-02T08:00:00+08:00"),
            ("ac", "python", "2026-09-02T09:00:00+08:00"),
            ("wa", "C++", "2026-09-02T10:00:00+08:00"),
            ("ac", "", "2026-09-03T09:00:00+08:00"),
        ]
        with closing(server_runtime.connect(self.db)) as connection:
            connection.executemany(
                "INSERT INTO submissions(problem_id, status, lang, submitted_at) VALUES (1, ?, ?, ?)",
                submissions,
            )
            connection.commit()
        detail = study.problem_progress(1, self.db)
        dashboard = study.dashboard_data(self.db)
        item = dashboard["problems"]["1"]
        self.assertEqual(detail["by_language"], item["by_language"])
        self.assertEqual((detail["rounds"], item["rounds"]), (3, 3))
        languages = detail["by_language"]
        self.assertEqual({key: data["rounds"] for key, data in languages.items()},
                         {"java": 2, "python": 1, "cpp": 0, "unknown": 1})
        self.assertEqual((languages["java"]["submits"], languages["python"]["ac_submits"]), (4, 2))
        self.assertEqual(languages["cpp"]["submits"], 1)
        self.assertEqual(languages["java"]["last_submitted_at"], "2026-09-02T15:59:00.000Z")
        self.assertNotIn("go", languages)
        self.assertEqual(dashboard["language_summary"]["cpp"]["completed_problems"], 0)

    def test_review_in_two_languages_shares_one_daily_review_and_overall_round(self):
        with patch.dict(server_runtime._values, {"now_parts": lambda: ("2026-09-08T12:00:00+08:00", "2026-09-08")}):
            record_submission(1, "ac", "Java", db_path=self.db)
            first = study.complete_round(1, self.db, 3, 0.9, lang="python")
            second = study.complete_round(1, self.db, 1, 0.9, lang="java")
            study.complete_round(1, self.db, 4, 0.9)  # An older client sends no language.
        self.assertEqual((first["round_no"], second["round_no"]), (1, 1))
        self.assertTrue(second["already_reviewed_today"])
        self.assertEqual(first["next_due"], second["next_due"])
        detail = study.problem_progress(1, self.db)
        self.assertEqual(detail["rounds"], 1)
        self.assertEqual({key: stats["rounds"] for key, stats in detail["by_language"].items()},
                         {"java": 1, "python": 1, "unknown": 1})
        self.assertEqual(study.dashboard_cached(self.db)["problems"]["1"]["by_language"], detail["by_language"])

    def test_curriculum_passes_use_the_selected_language(self):
        ids = list(server_runtime.PROBLEM_BY_ID)[:90]
        with closing(server_runtime.connect(self.db)) as connection:
            statement = "INSERT INTO submissions(problem_id, status, lang, submitted_at) VALUES (?, 'ac', ?, ?)"
            for lang, pids, day in [("Java", ids, 1), ("java", ids[:46], 2), ("Java", ids[:45], 3),
                                    ("Python3", ids[:89], 1)]:
                connection.executemany(statement, [(pid, lang, f"2026-09-0{day}T12:00:00+08:00") for pid in pids])
            connection.commit()
        summary = study.dashboard_data(self.db)
        self.assertEqual(summary["summary"]["total_rounds"], 2)
        self.assertEqual(summary["language_summary"], {
            "java": {"completed_problems": 90, "total_rounds": 2},
            "python": {"completed_problems": 89, "total_rounds": 0},
        })

    def test_sync_repairs_known_id_and_replaces_unknown_solved_placeholder_once(self):
        with closing(server_runtime.connect(self.db)) as connection:
            connection.executemany(
                "INSERT INTO submissions(problem_id, status, lang, submitted_at, source, lc_id) "
                "VALUES (1, 'ac', '', '2026-09-01T12:00:00+08:00', 'sync', ?)",
                [(None,), (10,)],
            )
            connection.execute(
                "INSERT INTO submissions(problem_id, status, lang, submitted_at, source) "
                "VALUES (1, 'ac', 'Rust', '2026-08-20T12:00:00+08:00', 'sync')"
            )
            connection.commit()

        def fetch(url, _headers):
            if "problems/all" in url:
                return {"user_name": "learner", "stat_status_pairs": []}
            return {"has_next": False, "submissions_dump": [
                {"id": sid, "title": "两数之和", "is_pending": "Not Pending", "status_display": "Accepted",
                 "timestamp": "1788220800", "lang": lang}
                for sid, lang in [(10, "Java"), (11, ""), (11, "Python3")]
            ]}
        with patch.dict(server_runtime._values, {"_fetch_json_with_retry": fetch, "get_fsrs_desired_retention": lambda: 0.9}):
            for _ in range(2):
                leetcode.leetcode_sync({"leetcode_session": "test"}, db_path=self.db)
        detail = study.problem_progress(1, self.db)
        self.assertEqual(detail["submits"], 3)
        self.assertEqual(set(detail["by_language"]), {"java", "python", "rust"})
        self.assertEqual(detail["by_language"]["python"]["rounds"], 1)

    def test_language_aliases_do_not_fold_distinct_languages(self):
        for lang, key in [(" c++ ", "cpp"), ("C", "c"), ("C#", "c#"), ("GoLang", "go"),
                          ("PyPy3", "python"), ("Java 17", "java"), ("JavaScript", "javascript"),
                          ("Rust", "rust"), ("   ", "unknown")]:
            with self.subTest(lang=lang):
                self.assertEqual(submission_language_key(lang), key)
