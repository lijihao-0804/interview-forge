import json
import sqlite3
import socket
import tempfile
import threading
import unittest
from datetime import datetime
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer
from http.client import HTTPConnection

from tools import study_server as server


class StudyServerHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "study.db"
        self.catalog = {
            1: {
                "id": 1,
                "title": "题目一",
                "category": "数组",
                "difficulty": "简单",
                "method": "双指针",
                "folder": "数组",
            }
        }
        self.patches = [
            patch.object(server, "PROBLEM_BY_ID", self.catalog),
            patch.object(server, "now_parts", return_value=("2026-09-07T12:00:00+08:00", "2026-09-07")),
            patch.object(server, "_invalidate_learning_caches"),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def test_content_completion_uses_content_review_interval(self) -> None:
        with patch.object(server, "valid_content", return_value=True):
            result = server.complete_content("module", "module:01", self.db_path)
        self.assertEqual(result["round_no"], 1)
        self.assertEqual(result["next_due"], "2026-09-10")

    def test_legacy_complete_populates_ac_model_and_deduplicates_same_day_round(self) -> None:
        with patch.object(server, "complete_content", return_value={}):
            first = server.complete_round(1, self.db_path)
            second = server.complete_round(1, self.db_path)
        self.assertEqual(first["round_no"], 1)
        self.assertEqual(second["round_no"], 1)
        self.assertEqual(server.ac_problem_progress(self.db_path)[1]["rounds"], 1)
        connection = sqlite3.connect(self.db_path)
        try:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM study_events WHERE problem_id = 1 AND action = 'complete'"
            ).fetchone()[0], 1)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM submissions WHERE problem_id = 1 AND status = 'ac'"
            ).fetchone()[0], 2)
        finally:
            connection.close()

    def test_legacy_event_type_completes_are_backfilled_once_by_shanghai_day(self) -> None:
        # Build the pre-AC schema directly, including duplicate events that
        # fall on one Shanghai business day despite different source offsets.
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                "CREATE TABLE study_events (id INTEGER PRIMARY KEY, problem_id INTEGER NOT NULL, "
                "event_type TEXT NOT NULL, studied_at TEXT NOT NULL, study_date TEXT, round_no INTEGER)"
            )
            connection.executemany(
                "INSERT INTO study_events(problem_id, event_type, studied_at, study_date, round_no) VALUES (?, 'complete', ?, ?, ?)",
                [
                    (1, "2026-09-07T16:30:00+00:00", "2026-09-07", 1),
                    (1, "2026-09-08T01:00:00+08:00", "2026-09-08", 2),
                ],
            )
            connection.commit()
        finally:
            connection.close()

        connection = server.connect(self.db_path)
        try:
            rows = connection.execute(
                "SELECT problem_id, status, submitted_at, source FROM submissions"
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0:2], (1, "ac"))
            self.assertEqual(rows[0][2][:10], "2026-09-08")
            self.assertEqual(rows[0][3], "manual")
        finally:
            connection.close()

        # Simulate a process restart by allowing schema initialization to run
        # again; business-day deduplication must keep one migrated row.
        server._SCHEMA_DONE.discard(str(self.db_path))
        connection = server.connect(self.db_path)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM submissions").fetchone()[0], 1)
        finally:
            connection.close()

    def test_due_dates_use_shanghai_business_date_at_utc_midnight_boundary(self) -> None:
        # 16:30 UTC is already the next calendar day in Shanghai.
        completed_at = "2026-09-07T16:30:00+00:00"
        self.assertEqual(server.due_after(completed_at, 1), "2026-09-09")
        self.assertEqual(server.due_after_content(completed_at, 1), "2026-09-11")

    def test_submission_aggregates_use_shanghai_business_day(self) -> None:
        connection = server.connect(self.db_path)
        try:
            connection.executemany(
                "INSERT INTO submissions(problem_id, status, lang, submitted_at, source) VALUES (1, 'ac', '', ?, 'manual')",
                [
                    ("2026-09-07T16:30:00+00:00",),  # Shanghai 2026-09-08
                    ("2026-09-07T15:59:59+00:00",),  # Shanghai 2026-09-07
                ],
            )
            connection.commit()
        finally:
            connection.close()
        with patch.object(server, "business_now", return_value=datetime.fromisoformat("2026-09-08T12:00:00+08:00")):
            self.assertEqual(server.ac_problem_progress(self.db_path)[1]["rounds"], 2)
            summary = server.submission_summary(self.db_path)["summary"]
            self.assertEqual(summary["today_ac"], 1)
            self.assertEqual(summary["today_submits"], 1)
            dashboard = server.dashboard_data(self.db_path)
            self.assertEqual(dashboard["summary"]["today_rounds"], 1)
            active = {item["date"]: item for item in dashboard["activity"] if item["rounds"]}
            self.assertEqual(active["2026-09-07"]["rounds"], 1)
            self.assertEqual(active["2026-09-08"]["rounds"], 1)
            _content_type, _filename, weekly = server.export_data("weekly", self.db_path)
            self.assertIn("题目 2 轮", weekly)

    def test_event_date_aggregates_use_studied_at_shanghai_day(self) -> None:
        # The persisted study_date in old VPS databases may have been written
        # in UTC.  Aggregates must derive the business day from studied_at.
        connection = server.connect(self.db_path)
        try:
            connection.execute(
                "INSERT INTO study_events(problem_id, action, studied_at, study_date) "
                "VALUES (1, 'view', ?, '2026-09-07')",
                ("2026-09-07T16:30:00+00:00",),  # Shanghai 2026-09-08
            )
            connection.execute(
                "INSERT INTO content_events(module_id, content_id, action, studied_at, study_date) "
                "VALUES ('module', 'module:01', 'view', ?, '2026-09-07')",
                ("2026-09-07T16:30:00+00:00",),
            )
            connection.execute(
                "INSERT INTO content_events(module_id, content_id, action, studied_at, study_date, round_no) "
                "VALUES ('module', 'module:01', 'complete', ?, '2026-09-07', 1)",
                ("2026-09-07T16:30:00+00:00",),
            )
            connection.commit()
        finally:
            connection.close()

        with patch.object(server, "business_now", return_value=datetime.fromisoformat("2026-09-08T12:00:00+08:00")):
            dashboard = server.dashboard_data(self.db_path)
            self.assertEqual(dashboard["summary"]["today_viewed"], 1)
            active = {item["date"]: item for item in dashboard["activity"] if item["viewed"] or item["rounds"]}
            self.assertEqual(active["2026-09-08"]["viewed"], 2)
            self.assertEqual(active["2026-09-08"]["rounds"], 1)
            _content_type, _filename, weekly = server.export_data("weekly", self.db_path)
            self.assertIn("题目 0 轮 + 章节 1 轮", weekly)
            self.assertIn("本周活跃天数：1 天", weekly)

    def test_view_deduplication_is_atomic_under_concurrency(self) -> None:
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _: server.record_view(1, self.db_path), range(40)))
        self.assertEqual(sum(results), 1)
        connection = sqlite3.connect(self.db_path)
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM study_events WHERE problem_id = 1 AND action = 'view'"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 1)

    def test_content_view_deduplication_is_atomic_under_concurrency(self) -> None:
        with patch.object(server, "valid_content", return_value=True):
            with ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(
                    lambda _: server.record_content_view("module", "module:01", self.db_path),
                    range(40),
                ))
        self.assertEqual(sum(results), 1)
        connection = sqlite3.connect(self.db_path)
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM content_events WHERE content_id = 'module:01' AND action = 'view'"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 1)

    def test_today_plan_commits_expired_pin_cleanup(self) -> None:
        connection = server.connect(self.db_path)
        try:
            connection.execute(
                "INSERT INTO plan_pins(problem_id, for_date, created_at) VALUES (1, '2020-01-01', '2020-01-01T00:00:00+08:00')"
            )
            connection.commit()
        finally:
            connection.close()
        with patch.object(server, "daily_data", return_value={"problems": [], "relearn": []}), \
             patch.object(server, "problem_review_state", return_value={}):
            server.today_plan(self.db_path)
        connection = sqlite3.connect(self.db_path)
        try:
            remaining = connection.execute("SELECT COUNT(*) FROM plan_pins").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(remaining, 0)

    def test_sensitive_path_rejects_case_and_double_encoded_variants(self) -> None:
        handler = object.__new__(server.StudyHandler)
        for path in (
            "/DATA/auth.db",
            "/%2564ata/auth.db",
            "//data/auth.db",
            "/%2Fdata/auth.db",
            "/ToOlS/study_server.py",
            "//tools/study_server.py",
            "/x/%252e%252e/data/auth.db",
        ):
            self.assertTrue(handler._sensitive_path(path), path)
        for path in (
            "/docs/QA-REPORT.html",
            "//docs/QA-REPORT.html",
            "/%2Fdocs/%51A-REPORT.html",
            "/docs/深度审查与修复报告-2026-09-08.html",
            "/docs/学情分析AI专项审查报告.html",
        ):
            self.assertFalse(handler._sensitive_path(path), path)
        for path in ("/docs/QA-REPORT.md", "/docs/other.html", "//docs/other.html"):
            self.assertTrue(handler._sensitive_path(path), path)
        self.assertFalse(handler._sensitive_path("/pages/login.html"))

    def test_http_path_parser_canonicalizes_double_slash_before_gate(self) -> None:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.StudyHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection("127.0.0.1", httpd.server_port, timeout=3)
        try:
            for target in ("//data/auth.db", "//tools/study_server.py", "/%2Fdata/auth.db"):
                connection.request("GET", target, headers={"Host": "127.0.0.1"})
                response = connection.getresponse()
                self.assertEqual(response.status, 404, target)
                response.read()
        finally:
            connection.close()
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)

    def test_public_audit_reports_are_served_but_other_docs_are_blocked(self) -> None:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.StudyHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection("127.0.0.1", httpd.server_port, timeout=3)
        admin = {"id": 1, "username": "admin", "role": "admin"}
        try:
            with patch.object(server.StudyHandler, "current_user", return_value=admin):
                for target in ("/docs/QA-REPORT.html", "//docs/QA-REPORT.html", "/%2Fdocs/QA-REPORT.html"):
                    connection.request("GET", target, headers={"Host": "127.0.0.1"})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200, target)
                    response.read()
                for target in ("/docs/QA-REPORT.md", "//docs/other.html"):
                    connection.request("GET", target, headers={"Host": "127.0.0.1"})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 404, target)
                    response.read()
        finally:
            connection.close()
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)

    def test_client_ip_uses_first_valid_forwarded_address_from_loopback_proxy(self) -> None:
        handler = object.__new__(server.StudyHandler)
        handler.client_address = ("127.0.0.1", 8765)
        handler.headers = Message()
        handler.headers["X-Forwarded-For"] = "not-an-ip, 203.0.113.8, 198.51.100.4"
        # nginx $proxy_add_x_forwarded_for appends its peer on the right;
        # client-supplied values on the left must not control the bucket.
        self.assertEqual(handler.client_ip(), "198.51.100.4")

        handler.headers = Message()
        handler.headers["X-Real-IP"] = "203.0.113.8"
        handler.headers["X-Forwarded-For"] = "198.51.100.4, 192.0.2.10"
        self.assertEqual(handler.client_ip(), "203.0.113.8")

        handler.headers = Message()
        handler.headers["X-Forwarded-For"] = "invalid"
        handler.headers["CF-Connecting-IP"] = "2001:db8::8"
        self.assertEqual(handler.client_ip(), "2001:db8::8")

    def test_client_ip_does_not_trust_forwarding_headers_from_remote_peer(self) -> None:
        handler = object.__new__(server.StudyHandler)
        handler.client_address = ("198.51.100.7", 8765)
        handler.headers = Message()
        handler.headers["X-Forwarded-For"] = "203.0.113.8"
        handler.headers["CF-Connecting-IP"] = "203.0.113.9"
        self.assertEqual(handler.client_ip(), "198.51.100.7")

    def _post_status(self, path: str, payload: object, user: object = None) -> int:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.StudyHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{httpd.server_port}{path}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with patch.object(server.StudyHandler, "current_user", return_value=user):
                try:
                    with urlopen(request, timeout=3) as response:
                        return response.status
                except HTTPError as exc:
                    return exc.code
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)

    def test_post_rejects_non_object_json_payload(self) -> None:
        self.assertEqual(self._post_status("/api/login", []), 400)

    def test_post_early_rejections_close_keep_alive_connection(self) -> None:
        cases = [
            ("/api/not-a-route", None),
            ("/api/submit", None),
            ("/api/admin/users/toggle", {"id": 1, "username": "admin", "role": "user"}),
        ]
        for path, user in cases:
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.StudyHandler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            sock = socket.create_connection(("127.0.0.1", httpd.server_port), timeout=3)
            try:
                request = (
                    f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                    "Connection: keep-alive\r\nContent-Length: 4\r\n"
                    "Content-Type: application/json\r\n\r\nxxxx"
                ).encode("ascii")
                with patch.object(server.StudyHandler, "current_user", return_value=user):
                    sock.sendall(request)
                    chunks = []
                    while True:
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    response = b"".join(chunks)
                self.assertIn(b"HTTP/1.1", response)
            finally:
                sock.close()
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=3)

    def test_admin_boolean_fields_require_json_boolean(self) -> None:
        admin = {"id": 1, "username": "admin", "role": "admin"}
        self.assertEqual(self._post_status("/api/admin/users/toggle", {"username": "alice", "active": "false"}, admin), 400)
        self.assertEqual(self._post_status("/api/admin/feedback/resolve", {"id": 1, "resolved": "false"}, admin), 400)

    def test_profile_rejects_malformed_base64_without_avatar_write(self) -> None:
        auth_path = Path(self.temp_dir.name) / "auth.db"
        with patch.object(server, "AUTH_DB_PATH", auth_path), patch.object(server, "_AUTH_READY", False):
            connection = server.connect_auth()
            try:
                connection.execute(
                    "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, 'user', ?)",
                    ("alice", "not-used", "2026-09-07T12:00:00+08:00"),
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaises(ValueError):
                server.set_profile("alice", avatar_data_url="data:image/png;base64,abc===")
            connection = sqlite3.connect(auth_path)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM avatars").fetchone()[0], 0)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
