"""年度报告后端：学习时长 / 搜索埋点 / 每日汇总 / 模拟考试记录。"""
import sqlite3
import tempfile
from pathlib import Path
from unittest import TestCase

from interview_forge.db.schema import SCHEMA
from interview_forge.services import study


def _make_db(tmp: Path, name: str = "hot100-study.db") -> Path:
    db = tmp / name
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    return db


class StudyDurationTests(TestCase):
    def test_accumulates_same_target_same_day(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = _make_db(Path(raw))
            study.record_study_duration("content", "java-core:01", 30, "java-core", db)
            study.record_study_duration("content", "java-core:01", 45, "java-core", db)
            conn = sqlite3.connect(db)
            rows = conn.execute("SELECT * FROM study_duration").fetchall()
            self.assertEqual(len(rows), 1, "同一天同一目标只保留一行")
            self.assertEqual(rows[0][5], 75, "秒数应累加")
            conn.close()

    def test_rejects_non_positive_and_bad_type(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = _make_db(Path(raw))
            self.assertFalse(study.record_study_duration("content", "x", 0, None, db)["recorded"])
            self.assertFalse(study.record_study_duration("content", "x", -5, None, db)["recorded"])
            with self.assertRaises(ValueError):
                study.record_study_duration("video", "x", 10, None, db)

    def test_caps_single_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = _make_db(Path(raw))
            out = study.record_study_duration("problem", "1", 99999, None, db)
            self.assertTrue(out["recorded"])
            conn = sqlite3.connect(db)
            self.assertEqual(conn.execute("SELECT seconds FROM study_duration").fetchone()[0], 3600)
            conn.close()


class SearchEventTests(TestCase):
    def test_records_keyword(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = _make_db(Path(raw))
            out = study.record_search("分布式锁", result_count=12, source="library", db_path=db)
            self.assertTrue(out["recorded"])
            conn = sqlite3.connect(db)
            row = conn.execute("SELECT keyword, result_count, source FROM search_events").fetchone()
            self.assertEqual(row, ("分布式锁", 12, "library"))
            conn.close()

    def test_ignores_empty_keyword(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = _make_db(Path(raw))
            self.assertFalse(study.record_search("   ", db_path=db)["recorded"])


class DailySummaryTests(TestCase):
    def test_aggregates_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = _make_db(Path(raw))
            study.record_view(1, db)
            study.record_study_duration("problem", "1", 120, None, db)

            first = study.refresh_daily_summary(db_path=db)
            second = study.refresh_daily_summary(db_path=db)
            self.assertEqual(first["view_count"], second["view_count"], "重复刷新应幂等")
            self.assertEqual(first["study_seconds"], 120)

            conn = sqlite3.connect(db)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM daily_summary").fetchone()[0], 1)
            conn.close()


class MockExamRecordTests(TestCase):
    def test_mock_exam_writes_record(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = _make_db(Path(raw))
            out = study.mock_exam(count=3, db_path=db)
            self.assertEqual(out["count"], 3)
            conn = sqlite3.connect(db)
            rows = conn.execute(
                "SELECT problem_count, scope, problem_ids FROM mock_exam_records").fetchall()
            self.assertEqual(len(rows), 1, "每次出题应记录一条")
            self.assertEqual(rows[0][0], 3)
            self.assertEqual(rows[0][1], "all")
            self.assertEqual(len(__import__("json").loads(rows[0][2])), 3)
            conn.close()


class ReportSummaryTests(TestCase):
    def test_aggregates_across_users(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            dbs = []
            for user in ("alice", "bob"):
                db = _make_db(root, f"{user}.db")
                study.record_view(1, db)
                study.record_search("滑动窗口", db_path=db)
                study.refresh_daily_summary(db_path=db)
                dbs.append(db)

            summary = study.report_summary(db_paths=dbs)
            self.assertEqual(summary["active_days"], 1, "同一天两人只算一天")
            self.assertGreaterEqual(summary["total_problems"], 1)
            self.assertTrue(summary["top_keywords"])
            self.assertEqual(summary["top_keywords"][0]["keyword"], "滑动窗口")
