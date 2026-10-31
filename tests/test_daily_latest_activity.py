"""「每天最晚一次打开」记录与全站统计的回归测试。"""
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


class DailyLatestActivityTests(TestCase):
    def test_keeps_only_the_latest_entry_per_day(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = _make_db(Path(raw))
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row

            self.assertTrue(study._touch_daily_latest(
                conn, latest_at="2026-10-31T08:00:00+08:00", study_date="2026-10-31",
                target_type="problem", target_id="1", target_title="两数之和"))
            # 更早的不应覆盖
            self.assertFalse(study._touch_daily_latest(
                conn, latest_at="2026-10-31T07:00:00+08:00", study_date="2026-10-31",
                target_type="problem", target_id="2", target_title="更早的题"))
            # 更晚的应覆盖
            self.assertTrue(study._touch_daily_latest(
                conn, latest_at="2026-10-31T23:40:00+08:00", study_date="2026-10-31",
                target_type="content", target_id="java-core:01", target_title="怎么用这份笔记"))
            conn.commit()

            rows = conn.execute("SELECT * FROM daily_latest_activity").fetchall()
            self.assertEqual(len(rows), 1, "一天只保留一条")
            self.assertEqual(rows[0]["target_id"], "java-core:01")
            self.assertEqual(rows[0]["latest_at"], "2026-10-31T23:40:00+08:00")
            conn.close()

    def test_different_days_are_kept_separately(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = _make_db(Path(raw))
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            for day in ("2026-10-30", "2026-10-31"):
                study._touch_daily_latest(
                    conn, latest_at=f"{day}T22:00:00+08:00", study_date=day,
                    target_type="problem", target_id="1", target_title="两数之和")
            conn.commit()
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM daily_latest_activity").fetchone()[0], 2)
            conn.close()


class LatestActivitySummaryTests(TestCase):
    def test_aggregates_across_user_databases(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            dbs = []
            for user, at, target in (
                ("alice", "2026-10-30T23:50:00+08:00", "1"),
                ("bob", "2026-10-31T07:10:00+08:00", "2"),
            ):
                db = _make_db(root, f"{user}.db")
                conn = sqlite3.connect(db)
                conn.row_factory = sqlite3.Row
                study._touch_daily_latest(
                    conn, latest_at=at, study_date=at[:10],
                    target_type="problem", target_id=target, target_title=f"题{target}")
                conn.commit()
                conn.close()
                dbs.append(db)

            summary = study.latest_activity_summary(year="2026", db_paths=dbs)
            self.assertEqual(summary["days"], 2)
            self.assertEqual(summary["total_records"], 2)
            self.assertEqual(summary["latest_clock"], "23:50", "全年最晚时刻取最大值")
            self.assertEqual(summary["hour_histogram"], {23: 1, 7: 1})
            self.assertEqual(len(summary["top_targets"]), 2)
