"""年度报告数据组装：字段完整性、统计正确性、人格标签规则。"""
import sqlite3
import tempfile
from pathlib import Path
from unittest import TestCase

from interview_forge.db.schema import SCHEMA
from interview_forge.services import study
from interview_forge.services.annual_report import build_annual_report


def _make_db(tmp: Path, name: str = "hot100-study.db") -> Path:
    db = tmp / name
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    return db


class AnnualReportTests(TestCase):
    def test_empty_database_returns_zeroed_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = _make_db(Path(raw))
            report = build_annual_report("2026", db_paths=[db])
            self.assertEqual(report["year"], "2026")
            self.assertEqual(report["active_days"], 0)
            self.assertEqual(report["total_problems"], 0)
            self.assertEqual(report["persona"], [])
            self.assertEqual(report["daily_calendar"], {})
            # 结构字段必须存在，前端不必兜底
            for key in ("firsts", "latest_activity", "gym", "module_distribution",
                        "hour_histogram", "top_keywords", "longest_streak",
                        "submission_stats", "memory_stats"):
                self.assertIn(key, report)

    def test_counts_and_persona_from_real_events(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = _make_db(Path(raw))
            # 造一条深夜浏览 + 一次提交 + 一次收藏
            study.record_view(1, db)
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            conn.execute(
                "INSERT INTO submissions(problem_id, status, lang, submitted_at, source) "
                "VALUES (1, 'ac', 'Java', '2026-05-01T10:00:00+08:00', 'manual')")
            conn.execute(
                "INSERT INTO favorites(target_type, target_id, module_id, title, url, created_at) "
                "VALUES ('content', 'java-core:01', 'java-core', '标题', '/x', '2026-05-02T09:00:00+08:00')")
            conn.commit()
            conn.close()

            report = build_annual_report("2026", db_paths=[db])
            self.assertEqual(report["active_days"], 1)
            self.assertEqual(report["total_submissions"], 1)
            self.assertEqual(report["favorites"], 1)
            self.assertEqual(report["longest_streak"], 1)
            self.assertTrue(report["firsts"]["first_ac"])
            self.assertTrue(report["firsts"]["first_favorite"])

    def test_longest_streak_across_consecutive_days(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = _make_db(Path(raw))
            conn = sqlite3.connect(db)
            for day in ("2026-03-01", "2026-03-02", "2026-03-03", "2026-03-06"):
                conn.execute(
                    "INSERT INTO study_events(problem_id, action, studied_at, study_date) "
                    "VALUES (1, 'view', ?, ?)", (f"{day}T10:00:00+08:00", day))
            conn.commit()
            conn.close()

            report = build_annual_report("2026", db_paths=[db])
            self.assertEqual(report["active_days"], 4)
            self.assertEqual(report["longest_streak"], 3, "3 月 1~3 日连续三天")

    def test_night_owl_persona(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = _make_db(Path(raw))
            conn = sqlite3.connect(db)
            for hour in (23, 23, 0, 1, 23):
                conn.execute(
                    "INSERT INTO study_events(problem_id, action, studied_at, study_date) "
                    "VALUES (1, 'view', ?, '2026-04-01')",
                    (f"2026-04-01T{hour:02d}:00:00+08:00",))
            conn.commit()
            conn.close()

            report = build_annual_report("2026", db_paths=[db])
            labels = [t["label"] for t in report["persona"]]
            self.assertIn("夜猫子", labels)


    def test_language_names_are_case_merged(self) -> None:
        """Java 与 java 应合并成同一个语言。"""
        with tempfile.TemporaryDirectory() as raw:
            db = _make_db(Path(raw))
            conn = sqlite3.connect(db)
            for lang in ("Java", "java", "Java"):
                conn.execute(
                    "INSERT INTO submissions(problem_id, status, lang, submitted_at, source) "
                    "VALUES (1, 'ac', ?, '2026-06-01T10:00:00+08:00', 'manual')", (lang,))
            conn.commit()
            conn.close()

            report = build_annual_report("2026", db_paths=[db])
            langs = report["submission_stats"]["languages"]
            self.assertEqual(len(langs), 1)
            self.assertEqual(langs[0]["name"], "Java")
            self.assertEqual(langs[0]["count"], 3)
