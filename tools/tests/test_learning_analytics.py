import copy
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from tools.learning_analytics import AnalyticsUnavailableError, build_learning_analytics


AS_OF = "2026-09-07T12:00:00+08:00"


SCHEMA = """
CREATE TABLE study_events (
    id INTEGER PRIMARY KEY,
    problem_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    studied_at TEXT NOT NULL,
    study_date TEXT NOT NULL,
    round_no INTEGER,
    source TEXT NOT NULL DEFAULT 'learning-site'
);
CREATE TABLE content_events (
    id INTEGER PRIMARY KEY,
    module_id TEXT NOT NULL,
    content_id TEXT NOT NULL,
    action TEXT NOT NULL,
    studied_at TEXT NOT NULL,
    study_date TEXT NOT NULL,
    round_no INTEGER
);
CREATE TABLE marks (
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    mark TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (target_type, target_id)
);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE submissions (
    id INTEGER PRIMARY KEY,
    problem_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    lang TEXT NOT NULL DEFAULT '',
    runtime_ms INTEGER,
    memory_kb INTEGER,
    submitted_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    lc_id INTEGER
);
CREATE TABLE plan_pins (
    problem_id INTEGER PRIMARY KEY,
    for_date TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _study_schema_db() -> tuple[tempfile.TemporaryDirectory, Path]:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "learning.db"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA)
    finally:
        connection.close()
    return temp_dir, path


def _catalog(count: int = 14) -> dict[int, dict[str, str]]:
    categories = ["哈希表", "双指针", "滑动窗口", "普通数组"]
    return {
        pid: {
            "id": pid,
            "title": f"题目 {pid}",
            "category": categories[(pid - 1) % len(categories)],
            "difficulty": "中等",
        }
        for pid in range(1, count + 1)
    }


def _manifest(problem_count: int = 14) -> dict[str, object]:
    hot100 = {
        "id": "hot100",
        "title": "算法刷题",
        "chapters": [
            {
                "id": f"hot100:{pid:04d}",
                "title": f"题目 {pid}",
                "url": f"hot100/{pid}.html",
            }
            for pid in range(1, problem_count + 1)
        ],
    }
    course = {
        "id": "module-a",
        "title": "合成课程",
        "chapters": [
            {"id": "module-a:01", "title": "章节一", "url": "a/01.html"},
            {"id": "module-a:02", "title": "章节二", "url": "a/02.html"},
        ],
    }
    return {"modules": [hot100, course], "routes": {}}


def _study(path: Path, event_id: int, problem_id: int, action: str, timestamp: str) -> None:
    study_date = timestamp[:10]
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO study_events(id, problem_id, action, studied_at, study_date, round_no) VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, problem_id, action, timestamp, study_date, None if action == "view" else 1),
        )
        connection.commit()
    finally:
        connection.close()


def _content(
    path: Path,
    event_id: int,
    module_id: str,
    content_id: str,
    action: str,
    timestamp: str,
    round_no: int | None = None,
) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO content_events(id, module_id, content_id, action, studied_at, study_date, round_no) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                module_id,
                content_id,
                action,
                timestamp,
                timestamp[:10],
                round_no if action == "complete" else None,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _submit(
    path: Path,
    event_id: int,
    problem_id: int,
    status: str,
    timestamp: str,
    source: str = "manual",
    lc_id: int | None = None,
) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO submissions(id, problem_id, status, submitted_at, source, lc_id) VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, problem_id, status, timestamp, source, lc_id),
        )
        connection.commit()
    finally:
        connection.close()


def _mark(path: Path, target_type: str, target_id: str, mark: str) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO marks(target_type, target_id, mark, updated_at) VALUES (?, ?, ?, ?)",
            (target_type, target_id, mark, AS_OF),
        )
        connection.commit()
    finally:
        connection.close()


def _output_metric_ids(result: dict[str, object]) -> set[str]:
    ids = set(result["summary"]["metric_ids"].values())
    for item in result["problem_metrics"]:
        ids.update(item["metric_ids"].values())
    for module in result["module_metrics"]:
        ids.update(module["metric_ids"].values())
        for content in module["content_metrics"]:
            ids.update(content["metric_ids"].values())
    return ids


class LearningAnalyticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir, self.db_path = _study_schema_db()
        self.catalog = _catalog()
        self.manifest = _manifest()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def build(self, **kwargs):
        return build_learning_analytics(
            self.db_path,
            self.catalog,
            self.manifest,
            as_of=AS_OF,
            **kwargs,
        )

    @staticmethod
    def problem(result, pid: int):
        return next(item for item in result["problem_metrics"] if item["problem_id"] == pid)

    @staticmethod
    def signals(result, signal_type: str, entity_id: str | None = None):
        found = [item for item in result["signals"] if item["signal_type"] == signal_type]
        if entity_id is not None:
            found = [item for item in found if item["entity_id"] == entity_id]
        return found

    def test_01_empty_database_is_data_insufficient(self):
        result = self.build()
        self.assertEqual(result["schema_version"], "analytics-v1")
        self.assertEqual(result["summary"]["completed_problem_count"], 0)
        self.assertEqual(result["summary"]["active_days"], {"7d": 0, "14d": 0, "30d": 0})
        self.assertIsNone(result["summary"]["problem_completion_ratio"])
        self.assertIn("no_learning_data", result["data_quality"]["reason_codes"])
        self.assertIn("no_submission_data", result["data_quality"]["reason_codes"])
        self.assertTrue(self.signals(result, "data_insufficient"))

    def test_02_views_without_submissions_trigger_only_view_signal(self):
        _study(self.db_path, 1, 1, "view", "2026-09-01T10:00:00+08:00")
        _study(self.db_path, 2, 1, "view", "2026-09-03T10:00:00+08:00")
        _study(self.db_path, 3, 1, "view", "2026-09-07T10:00:00+08:00")
        result = self.build()
        problem = self.problem(result, 1)
        self.assertEqual(problem["view_count"]["all"], 3)
        self.assertEqual(problem["view_days"]["all"], 3)
        self.assertFalse(problem["ever_ac"])
        self.assertIsNone(problem["pass_rate"])
        self.assertTrue(self.signals(result, "view_without_ac", "1"))
        self.assertFalse(self.signals(result, "repeat_wa", "1"))

    def test_03_three_recent_wa_without_ac_is_high_repeat_wa(self):
        for event_id, day in enumerate((1, 3, 7), 1):
            _submit(self.db_path, event_id, 2, "wa", f"2026-09-{day:02d}T10:00:00+08:00")
        result = self.build()
        problem = self.problem(result, 2)
        self.assertEqual(problem["wa_count"]["30d"], 3)
        self.assertEqual(problem["ac_day_count"], 0)
        signal = self.signals(result, "repeat_wa", "2")
        self.assertEqual(len(signal), 1)
        self.assertEqual(signal[0]["severity"], "high")

    def test_04_wa_before_ac_does_not_trigger_repeat_or_wa_after_ac(self):
        _submit(self.db_path, 1, 3, "wa", "2026-09-01T10:00:00+08:00")
        _submit(self.db_path, 2, 3, "wa", "2026-09-02T10:00:00+08:00")
        _submit(self.db_path, 3, 3, "ac", "2026-09-03T10:00:00+08:00")
        result = self.build()
        problem = self.problem(result, 3)
        self.assertTrue(problem["ever_ac"])
        self.assertEqual(problem["ac_day_count"], 1)
        self.assertEqual(problem["last_submission_status"], "ac")
        self.assertFalse(self.signals(result, "repeat_wa", "3"))
        self.assertFalse(self.signals(result, "wa_after_ac", "3"))

    def test_05_wa_after_ac_is_medium(self):
        _submit(self.db_path, 1, 4, "ac", "2026-09-01T10:00:00+08:00")
        _submit(self.db_path, 2, 4, "wa", "2026-09-03T10:00:00+08:00")
        result = self.build()
        problem = self.problem(result, 4)
        self.assertEqual(problem["wa_after_latest_ac_count"], 1)
        signal = self.signals(result, "wa_after_ac", "4")
        self.assertEqual(signal[0]["severity"], "medium")

    def test_06_same_day_ac_is_one_round_but_three_submissions(self):
        for event_id, hour in enumerate((8, 9, 10), 1):
            _submit(self.db_path, event_id, 5, "ac", f"2026-09-07T{hour:02d}:00:00+08:00")
        result = self.build()
        problem = self.problem(result, 5)
        self.assertEqual(problem["ac_count"]["all"], 3)
        self.assertEqual(problem["ac_day_count"], 1)
        self.assertEqual(result["summary"]["today_problem_round_actions"], 1)

    def test_07_cross_day_ac_uses_problem_interval_for_due_date(self):
        for event_id, day in enumerate((5, 6, 7), 1):
            _submit(self.db_path, event_id, 6, "ac", f"2026-09-{day:02d}T10:00:00+08:00")
        result = self.build()
        problem = self.problem(result, 6)
        self.assertEqual(problem["ac_day_count"], 3)
        self.assertEqual(problem["next_due_date"], "2026-09-14")

    def test_08_mark_is_preserved_and_conflict_is_explicit(self):
        _submit(self.db_path, 1, 7, "ac", "2026-09-01T10:00:00+08:00")
        _submit(self.db_path, 2, 7, "wa", "2026-09-03T10:00:00+08:00")
        _submit(self.db_path, 3, 7, "wa", "2026-09-04T10:00:00+08:00")
        _mark(self.db_path, "problem", "7", "mastered")
        result = self.build()
        problem = self.problem(result, 7)
        self.assertEqual(problem["mark"], "mastered")
        self.assertTrue(problem["mark_conflict"])
        self.assertEqual(self.signals(result, "wa_after_ac", "7")[0]["severity"], "high")

    def test_09_content_due_uses_three_day_first_interval(self):
        _content(
            self.db_path,
            1,
            "module-a",
            "module-a:01",
            "complete",
            "2026-09-04T10:00:00+08:00",
            round_no=1,
        )
        result = self.build()
        module = next(item for item in result["module_metrics"] if item["module_id"] == "module-a")
        content = next(item for item in module["content_metrics"] if item["content_id"] == "module-a:01")
        self.assertEqual(content["next_due_date"], "2026-09-07")
        self.assertTrue(content["due"])
        self.assertTrue(self.signals(result, "due_overdue", "module-a:01"))

    def test_10_old_history_has_no_recent_active_days_and_stalled_module(self):
        connection = sqlite3.connect(self.db_path)
        try:
            connection.executemany(
                "INSERT INTO submissions(id, problem_id, status, submitted_at, source) VALUES (?, ?, ?, ?, ?)",
                ((event_id, 2, "wa", "2026-01-01T10:00:00+08:00", "manual") for event_id in range(1, 10001)),
            )
            connection.commit()
        finally:
            connection.close()
        _content(
            self.db_path,
            20001,
            "module-a",
            "module-a:01",
            "complete",
            "2026-01-01T10:00:00+08:00",
            round_no=1,
        )
        result = self.build()
        problem = self.problem(result, 2)
        self.assertEqual(problem["submit_count"]["all"], 10000)
        self.assertEqual(problem["submit_count"]["30d"], 0)
        self.assertEqual(result["summary"]["active_days"], {"7d": 0, "14d": 0, "30d": 0})
        stalled = self.signals(result, "stalled_module", "module-a")
        self.assertEqual(len(stalled), 1)
        self.assertEqual(stalled[0]["severity"], "high")
        self.assertLessEqual(len(result["evidence"]), 500)

    def test_11_mixed_manual_and_sync_is_quality_flagged_without_merging(self):
        timestamp = "2026-09-07T09:00:00+08:00"
        _submit(self.db_path, 1, 8, "ac", timestamp, source="manual", lc_id=None)
        _submit(self.db_path, 2, 8, "ac", timestamp, source="sync", lc_id=8001)
        result = self.build()
        problem = self.problem(result, 8)
        self.assertEqual(problem["ac_count"]["all"], 2)
        self.assertEqual(problem["source_distribution"], {"manual": 1, "sync": 1})
        self.assertEqual(result["data_quality"]["mixed_source_possible_duplicate_count"], 1)
        self.assertIn("mixed_source_possible_duplicate", result["data_quality"]["reason_codes"])

    def test_12_utc_timestamp_crosses_into_same_shanghai_day(self):
        _submit(self.db_path, 1, 12, "ac", "2026-09-06T16:30:00+00:00")
        _submit(self.db_path, 2, 12, "ac", "2026-09-07T00:40:00+08:00")
        result = self.build()
        problem = self.problem(result, 12)
        self.assertEqual(problem["ac_count"]["all"], 2)
        self.assertEqual(problem["ac_day_count"], 1)
        self.assertEqual(result["summary"]["today_problem_round_actions"], 1)

    def test_13_duplicate_manifest_content_id_is_rejected(self):
        duplicate = copy.deepcopy(self.manifest)
        duplicate["modules"][1]["chapters"].append(
            {"id": "hot100:0001", "title": "冲突", "url": "conflict.html"}
        )
        with self.assertRaises(ValueError):
            self.build_manifest(duplicate)

    def build_manifest(self, manifest):
        return build_learning_analytics(
            self.db_path,
            self.catalog,
            manifest,
            as_of=AS_OF,
        )

    def test_14_submission_time_beats_local_id_for_last_status_and_wa_after_ac(self):
        _submit(self.db_path, 20, 14, "wa", "2026-09-06T10:00:00+08:00")
        _submit(self.db_path, 10, 14, "ac", "2026-09-06T11:00:00+08:00")
        result = self.build()
        problem = self.problem(result, 14)
        self.assertEqual(problem["last_submission_status"], "ac")
        self.assertEqual(problem["wa_after_latest_ac_count"], 0)
        self.assertFalse(self.signals(result, "wa_after_ac", "14"))

    def test_15_stable_ids_json_serialization_and_invalid_time_quality(self):
        _submit(self.db_path, 1, 1, "wa", "not-a-timestamp")
        _submit(self.db_path, 2, 1, "wa", "2026-09-01T10:00:00+08:00")
        first = self.build()
        second = self.build()
        self.assertEqual(first, second)
        json.dumps(first, ensure_ascii=False, sort_keys=True)
        self.assertEqual(first["data_quality"]["invalid_timestamp_count"], 1)
        serialized_ids = json.dumps(first, ensure_ascii=False)
        self.assertNotIn(str(self.db_path), serialized_ids)
        self.assertNotIn("20303", serialized_ids)
        for signal in first["signals"]:
            for metric_id in signal["metric_ids"]:
                self.assertIn(metric_id, serialized_ids)
            for evidence_id in signal["evidence_ids"]:
                self.assertIn(evidence_id, serialized_ids)

    def test_16_output_limits_bound_evidence_and_event_ids(self):
        for event_id in range(1, 101):
            _submit(self.db_path, event_id, 2, "wa", f"2026-09-07T00:{event_id % 60:02d}:00+08:00")
        result = self.build(
            limits={"max_signals": 1, "max_evidence": 1, "max_evidence_event_ids": 3}
        )
        self.assertLessEqual(len(result["signals"]), 1)
        self.assertLessEqual(len(result["evidence"]), 1)
        if result["evidence"]:
            facts = result["evidence"][0]["facts"]
            self.assertLessEqual(len(facts["event_ids"]), 3)
            self.assertGreaterEqual(facts["omitted_event_ids"], 97)
        self.assertEqual(result["data_quality"]["limits"]["max_signals"], 1)

    def test_17_legacy_study_complete_never_adds_a_hot100_round(self):
        _study(self.db_path, 1, 13, "complete", "2026-09-01T10:00:00+08:00")
        result = self.build()
        problem = self.problem(result, 13)
        self.assertEqual(problem["ac_day_count"], 0)
        self.assertEqual(problem["problem_round_count"], 0)
        self.assertEqual(result["summary"]["completed_problem_count"], 0)
        self.assertEqual(result["data_quality"]["legacy_complete_ignored_count"], 1)

    def test_18_legacy_submissions_without_optional_columns_are_read_only_compatible(self):
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        legacy_schema = (
            SCHEMA.replace("    lang TEXT NOT NULL DEFAULT '',\n", "")
            .replace("    runtime_ms INTEGER,\n", "")
            .replace("    memory_kb INTEGER,\n", "")
            .replace("    source TEXT NOT NULL DEFAULT 'manual',\n", "")
            .replace("    lc_id INTEGER\n", "")
            .replace("    submitted_at TEXT NOT NULL,\n);", "    submitted_at TEXT NOT NULL\n);")
        )
        connection = sqlite3.connect(legacy_path)
        try:
            connection.executescript(legacy_schema)
            connection.execute(
                "INSERT INTO submissions(id, problem_id, status, submitted_at) VALUES (?, ?, ?, ?)",
                (1, 1, "ac", "2026-09-07T10:00:00+08:00"),
            )
            connection.commit()
        finally:
            connection.close()

        result = build_learning_analytics(
            legacy_path,
            self.catalog,
            self.manifest,
            as_of=AS_OF,
        )
        problem = self.problem(result, 1)
        self.assertEqual(problem["ac_count"]["all"], 1)
        self.assertEqual(problem["source_distribution"], {"manual": 1})
        self.assertFalse(result["data_quality"]["schema_incompatible"])
        connection = sqlite3.connect(legacy_path)
        try:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(submissions)")}
        finally:
            connection.close()
        self.assertNotIn("lc_id", columns)

    def test_19_missing_core_column_returns_explicit_schema_incompatible(self):
        incompatible_path = Path(self.temp_dir.name) / "incompatible.db"
        incompatible_schema = SCHEMA.replace("    status TEXT NOT NULL,\n", "")
        connection = sqlite3.connect(incompatible_path)
        try:
            connection.executescript(incompatible_schema)
            connection.commit()
        finally:
            connection.close()

        result = build_learning_analytics(
            incompatible_path,
            self.catalog,
            self.manifest,
            as_of=AS_OF,
        )
        quality = result["data_quality"]
        self.assertTrue(quality["schema_incompatible"])
        self.assertIn("schema_incompatible", quality["reason_codes"])
        self.assertEqual(
            quality["schema_incompatible_details"]["submissions"]["missing_core_columns"],
            ["status"],
        )
        self.assertEqual(result["signals"], [])

    def test_20_exclusive_lock_fails_fast_as_retryable_error(self):
        connection = sqlite3.connect(self.db_path, timeout=0.1)
        try:
            connection.execute("BEGIN EXCLUSIVE")
            started = time.monotonic()
            with self.assertRaises(AnalyticsUnavailableError) as raised:
                self.build()
            elapsed = time.monotonic() - started
        finally:
            connection.rollback()
            connection.close()
        self.assertTrue(raised.exception.retryable)
        self.assertLess(elapsed, 1.5)

    def test_21_future_rows_are_excluded_but_exact_as_of_is_included(self):
        _submit(self.db_path, 1, 1, "ac", AS_OF)
        _submit(self.db_path, 2, 1, "ac", "2026-09-07T12:00:00.000001+08:00")
        _submit(self.db_path, 3, 2, "ac", "2026-09-07T12:01:00+08:00")
        result = self.build()
        self.assertEqual(self.problem(result, 1)["ac_count"]["all"], 1)
        self.assertFalse(self.problem(result, 2)["ever_ac"])
        self.assertEqual(result["data_quality"]["future_event_count"], 2)
        self.assertEqual(self.problem(result, 1)["last_submitted_at"], AS_OF)

    def test_22_duplicate_lc_id_is_reported_without_migration_or_deduplication(self):
        _submit(
            self.db_path,
            1,
            1,
            "wa",
            "2026-09-07T09:00:00+08:00",
            source="sync",
            lc_id=9001,
        )
        _submit(
            self.db_path,
            2,
            1,
            "wa",
            "2026-09-07T09:01:00+08:00",
            source="sync",
            lc_id=9001,
        )
        result = self.build()
        self.assertEqual(self.problem(result, 1)["wa_count"]["all"], 2)
        self.assertEqual(result["data_quality"]["duplicate_lc_id_count"], 1)
        self.assertEqual(result["data_quality"]["duplicate_sync_lc_id_count"], 1)
        self.assertIn("duplicate_lc_id", result["data_quality"]["warning_codes"])

    def test_23_later_wa_wins_even_when_its_local_id_is_smaller(self):
        _submit(self.db_path, 20, 3, "ac", "2026-09-07T10:00:00+08:00")
        _submit(self.db_path, 10, 3, "wa", "2026-09-07T11:00:00+08:00")
        result = self.build()
        problem = self.problem(result, 3)
        self.assertEqual(problem["last_submission_status"], "wa")
        self.assertEqual(problem["wa_after_latest_ac_count"], 1)
        self.assertTrue(self.signals(result, "wa_after_ac", "3"))

    def test_24_all_output_caps_preserve_reference_closure(self):
        for event_id, day in enumerate((1, 2, 3), 1):
            _submit(
                self.db_path,
                event_id,
                1,
                "wa",
                f"2026-09-{day:02d}T09:00:00+08:00",
            )
        _content(
            self.db_path,
            100,
            "module-a",
            "module-a:01",
            "complete",
            "2026-01-01T09:00:00+08:00",
            round_no=1,
        )
        cap_cases = [
            {"max_problem_metrics": 0},
            {"max_module_metrics": 0},
            {"max_content_metrics": 0},
            {"max_signals": 0},
            {"max_evidence": 0},
            {
                "max_problem_metrics": 0,
                "max_module_metrics": 0,
                "max_content_metrics": 0,
                "max_signals": 0,
                "max_evidence": 0,
                "max_evidence_event_ids": 0,
            },
        ]
        for limits in cap_cases:
            with self.subTest(limits=limits):
                result = self.build(limits=limits)
                metric_ids = _output_metric_ids(result)
                evidence_ids = {item["evidence_id"] for item in result["evidence"]}
                for signal in result["signals"]:
                    self.assertTrue(set(signal["metric_ids"]).issubset(metric_ids))
                    self.assertTrue(set(signal["evidence_ids"]).issubset(evidence_ids))
                if "max_problem_metrics" in limits:
                    self.assertLessEqual(len(result["problem_metrics"]), limits["max_problem_metrics"])
                if "max_module_metrics" in limits:
                    self.assertLessEqual(len(result["module_metrics"]), limits["max_module_metrics"])
                if "max_signals" in limits:
                    self.assertLessEqual(len(result["signals"]), limits["max_signals"])
                if "max_evidence" in limits:
                    self.assertLessEqual(len(result["evidence"]), limits["max_evidence"])
        zero_event_limit = self.build(limits={"max_evidence_event_ids": 0})
        for item in zero_event_limit["evidence"]:
            self.assertEqual(item["facts"]["event_ids"], [])

    def test_25_allowed_db_root_rejects_traversal_and_symlink_escape(self):
        allowed_root = Path(self.temp_dir.name) / "allowed"
        allowed_root.mkdir()
        inside_path = allowed_root / "inside.db"
        connection = sqlite3.connect(inside_path)
        try:
            connection.executescript(SCHEMA)
            connection.commit()
        finally:
            connection.close()
        build_learning_analytics(
            inside_path,
            self.catalog,
            self.manifest,
            as_of=AS_OF,
            allowed_db_root=allowed_root,
        )
        with self.assertRaises(ValueError):
            build_learning_analytics(
                self.db_path,
                self.catalog,
                self.manifest,
                as_of=AS_OF,
                allowed_db_root=allowed_root,
            )
        with self.assertRaises(ValueError):
            build_learning_analytics(
                allowed_root / ".." / self.db_path.name,
                self.catalog,
                self.manifest,
                as_of=AS_OF,
                allowed_db_root=allowed_root,
            )
        symlink_path = allowed_root / "outside-link.db"
        try:
            symlink_path.symlink_to(self.db_path)
        except (OSError, NotImplementedError):
            symlink_path = None
        if symlink_path is not None:
            with self.assertRaises(ValueError):
                build_learning_analytics(
                    symlink_path,
                    self.catalog,
                    self.manifest,
                    as_of=AS_OF,
                    allowed_db_root=allowed_root,
                )

    def test_26_hot100_recent_problem_view_prevents_stalled_signal(self):
        _submit(self.db_path, 1, 1, "ac", "2026-08-01T09:00:00+08:00")
        _study(self.db_path, 2, 1, "view", AS_OF)
        result = self.build()
        hot100 = next(item for item in result["module_metrics"] if item["module_id"] == "hot100")
        hot_content = next(
            item for item in hot100["content_metrics"] if item["content_id"] == "hot100:0001"
        )
        self.assertEqual(hot_content["content_round_count"], 1)
        self.assertEqual(hot_content["last_activity_at"], AS_OF)
        self.assertEqual(hot100["module_last_activity_at"], AS_OF)
        self.assertFalse(self.signals(result, "stalled_module", "hot100"))

    def test_27_quality_warnings_do_not_become_global_data_insufficient(self):
        catalog = copy.deepcopy(self.catalog)
        catalog[2]["category"] = "algo.unverified"
        for event_id, day in enumerate((1, 3, 7), 1):
            _submit(
                self.db_path,
                event_id,
                2,
                "wa",
                f"2026-09-{day:02d}T09:00:00+08:00",
            )
        _submit(self.db_path, 4, 2, "wa", "bad-time")
        _submit(
            self.db_path,
            5,
            3,
            "wa",
            "2026-09-07T10:00:00+08:00",
            source="manual",
        )
        _submit(
            self.db_path,
            6,
            3,
            "wa",
            "2026-09-07T10:01:00+08:00",
            source="sync",
            lc_id=3001,
        )
        result = build_learning_analytics(
            self.db_path,
            catalog,
            self.manifest,
            as_of=AS_OF,
        )
        self.assertFalse(self.signals(result, "data_insufficient"))
        self.assertTrue(self.signals(result, "repeat_wa", "2"))
        self.assertEqual(self.problem(result, 2)["skill_ids"], [])
        self.assertIn("invalid_timestamps", result["data_quality"]["warning_codes"])
        self.assertIn("mixed_source_possible_duplicate", result["data_quality"]["warning_codes"])
        self.assertIn("skill_unmapped", result["data_quality"]["warning_codes"])

    def test_28_threshold_override_has_stable_hashed_rule_version_and_signal_id(self):
        for event_id in range(1, 5):
            _submit(
                self.db_path,
                event_id,
                4,
                "wa",
                f"2026-09-{event_id:02d}T09:00:00+08:00",
            )
        default_result = self.build()
        custom_result = self.build(rule_config={"repeat_wa_min": 4})
        custom_again = self.build(rule_config={"repeat_wa_min": 4})
        self.assertNotEqual(default_result["rule_version"], custom_result["rule_version"])
        self.assertEqual(custom_result["rule_version"], custom_again["rule_version"])
        default_signal = self.signals(default_result, "repeat_wa", "4")[0]
        custom_signal = self.signals(custom_result, "repeat_wa", "4")[0]
        self.assertNotEqual(default_signal["signal_id"], custom_signal["signal_id"])
        self.assertEqual(custom_signal["signal_id"], self.signals(custom_again, "repeat_wa", "4")[0]["signal_id"])

    def test_29_source_distribution_merges_untrusted_sources_into_bounded_other(self):
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                "INSERT INTO submissions(id, problem_id, status, submitted_at, source, lc_id) "
                "VALUES (1, 1, 'ac', ?, ?, NULL)",
                (AS_OF, "untrusted-source-0000-" + "x" * 2000),
            )
            connection.commit()
        finally:
            connection.close()
        one_result = self.build()

        connection = sqlite3.connect(self.db_path)
        try:
            connection.executemany(
                "INSERT INTO submissions(id, problem_id, status, submitted_at, source, lc_id) "
                "VALUES (?, 1, 'ac', ?, ?, NULL)",
                [
                    (event_id, AS_OF, f"untrusted-source-{event_id:04d}-" + "y" * 2000)
                    for event_id in range(2, 1001)
                ],
            )
            connection.commit()
        finally:
            connection.close()

        result = self.build()
        problem = self.problem(result, 1)
        self.assertEqual(problem["source_distribution"], {"other": 1000})
        self.assertEqual(result["summary"]["submission_source_distribution"], {"other": 1000})
        self.assertEqual(result["data_quality"]["invalid_source_count"], 1000)
        self.assertEqual(result["data_quality"]["other_source_count"], 1000)
        self.assertLessEqual(len(problem["source_distribution"]), 5)
        self.assertLess(len(json.dumps(result, ensure_ascii=False)), len(json.dumps(one_result, ensure_ascii=False)) + 5000)
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("untrusted-source-", encoded)


if __name__ == "__main__":
    unittest.main()
