import io
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from interview_forge.services import admin_operations
from interview_forge.services import leetcode


def http_error(code=403, *, headers=None, body=b""):
    return urllib.error.HTTPError(
        "https://leetcode.cn/api/test", code, "upstream error", headers or {}, io.BytesIO(body)
    )


class _UrlopenResponse:
    def __init__(self, payload=b"{}"):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class LeetCodeHTTPReliabilityTests(unittest.TestCase):
    def test_curl_cffi_missing_uses_stdlib_fallback(self):
        with patch.dict(sys.modules, {"curl_cffi": None}), patch(
            "urllib.request.urlopen", return_value=_UrlopenResponse(b'{"ok":true}')
        ) as urlopen:
            payload = leetcode._lc_http_get("https://leetcode.cn/api/test", {}, timeout=1)
        self.assertEqual(payload, b'{"ok":true}')
        urlopen.assert_called_once()

    def test_cloudflare_header_and_body_are_challenge_but_server_header_alone_is_not(self):
        by_header = leetcode._classify_leetcode_http_error(
            http_error(403, headers={"cf-mitigated": "challenge"})
        )
        by_body = leetcode._classify_leetcode_http_error(
            http_error(403, headers={"server": "cloudflare"}, body=b"<title>Just a moment...</title>")
        )
        ordinary = leetcode._classify_leetcode_http_error(
            http_error(403, headers={"server": "cloudflare"}, body=b"forbidden")
        )
        self.assertEqual(by_header.category, "provider_blocked")
        self.assertEqual(by_body.category, "provider_blocked")
        self.assertEqual(ordinary.category, "session_invalid")
        self.assertIn("LEETCODE_SESSION", by_header.message)
        self.assertIn("csrftoken", by_header.message)
        self.assertIn("LEETCODE_SESSION", ordinary.message)
        self.assertIn("csrftoken", ordinary.message)

        with patch.dict(leetcode.server_runtime._values, {
            "_lc_http_get": Mock(side_effect=http_error(403, headers={"cf-mitigated": "challenge"}))
        }):
            status = leetcode.leetcode_status({"leetcode_session": "session-secret"})
        self.assertEqual(status["reason"], "cloudflare")
        self.assertIn("Cloudflare challenge", status["message"])

    def test_challenge_and_invalid_session_fail_fast_without_retry(self):
        challenge = http_error(403, headers={"cf-mitigated": "challenge"}, body=b"Just a moment")
        getter = Mock(side_effect=challenge)
        with patch.dict(leetcode.server_runtime._values, {"_lc_http_get": getter}), patch(
            "interview_forge.services.leetcode.time.sleep"
        ) as sleeper:
            with self.assertRaises(urllib.error.HTTPError):
                leetcode._fetch_json_with_retry("https://leetcode.cn/api/test", {}, retries=3, backoff=0)
        self.assertEqual(getter.call_count, 1)
        sleeper.assert_not_called()

        invalid = http_error(403, headers={"server": "cloudflare"})
        getter = Mock(side_effect=invalid)
        with patch.dict(leetcode.server_runtime._values, {"_lc_http_get": getter}):
            with self.assertRaises(urllib.error.HTTPError):
                leetcode._fetch_json_with_retry("https://leetcode.cn/api/test", {}, retries=3, backoff=0)
        self.assertEqual(getter.call_count, 1)

    def test_rate_limit_retries_with_bounded_backoff(self):
        first = http_error(429)
        second = http_error(429)
        getter = Mock(side_effect=[first, second, b'{"ok":true}'])
        with patch.dict(leetcode.server_runtime._values, {"_lc_http_get": getter}), patch(
            "interview_forge.services.leetcode.time.sleep"
        ) as sleeper:
            payload = leetcode._fetch_json_with_retry("https://leetcode.cn/api/test", {}, retries=3, backoff=0.25)
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(getter.call_count, 3)
        self.assertEqual([call.args[0] for call in sleeper.call_args_list], [0.25, 0.5])

    def test_first_submissions_page_failure_fails_task_with_safe_category(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "learning.db"

            def fake_fetch(url, headers, *args, **kwargs):
                if "problems/all" in url:
                    return {"user_name": "alice", "stat_status_pairs": []}
                raise http_error(403, headers={"cf-mitigated": "challenge"}, body=b"Just a moment")

            with patch.dict(leetcode.server_runtime._values, {"_fetch_json_with_retry": fake_fetch}):
                with self.assertRaises(leetcode.LeetCodeSyncError) as raised:
                    leetcode.leetcode_sync({"leetcode_session": "session-secret"}, db_path=db_path)
        self.assertEqual(raised.exception.category, "provider_blocked")
        self.assertNotIn("HTTPError", str(raised.exception))
        self.assertNotIn("leetcode.cn", str(raised.exception))

    def test_later_submissions_page_failure_returns_partial_and_safe_error(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "learning.db"

            def fake_fetch(url, headers, *args, **kwargs):
                if "problems/all" in url:
                    return {"user_name": "alice", "stat_status_pairs": []}
                if "offset=0" in url:
                    return {
                        "submissions_dump": [{
                            "id": 7, "title": "Two Sum", "status_display": "Accepted",
                            "is_pending": "Not Pending", "timestamp": "1780000000", "lang": "python3",
                        }],
                        "has_next": True,
                    }
                raise http_error(403, headers={"cf-mitigated": "challenge"}, body=b"Just a moment")

            with patch.dict(leetcode.server_runtime._values, {"_fetch_json_with_retry": fake_fetch}), patch(
                "interview_forge.services.leetcode.time.sleep"
            ):
                result = leetcode.leetcode_sync(
                    {"leetcode_session": "session-secret"}, db_path=db_path, full=True
                )
        self.assertTrue(result["partial"])
        self.assertTrue(result["degraded"])
        self.assertEqual(result["partial_error_category"], "provider_blocked")
        self.assertEqual(result["sync_errors"], ["第 2 页拉取失败（错误类别：provider_blocked，已停止后续拉取）"])
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("HTTPError", serialized)
        self.assertNotIn("leetcode.cn", serialized)
        self.assertNotIn("session-secret", serialized)

    def test_incremental_sync_always_starts_at_newest_page(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "learning.db"
            requested_urls = []

            def fake_fetch(url, headers, *args, **kwargs):
                requested_urls.append(url)
                if "problems/all" in url:
                    return {"user_name": "alice", "stat_status_pairs": []}
                if "offset=0" in url:
                    return {"submissions_dump": [{"id": 7, "title": "Two Sum", "status_display": "Accepted",
                                                   "is_pending": "Not Pending", "timestamp": "1780000000", "lang": "python3"}],
                            "has_next": True}
                raise AssertionError(f"incremental sync walked to an old page: {url}")

            with patch.dict(leetcode.server_runtime._values, {"_fetch_json_with_retry": fake_fetch}):
                first = leetcode.leetcode_sync({"leetcode_session": "session-secret"}, db_path=db_path, full=False)
                second = leetcode.leetcode_sync(
                    {"leetcode_session": "session-secret"}, db_path=db_path, full=False,
                    offset=5000,
                )

        self.assertFalse(first["partial"])
        self.assertFalse(first["degraded"])
        self.assertIsNone(first["next_offset"])
        self.assertFalse(first["has_more"])
        self.assertFalse(second["partial"])
        self.assertIsNone(second["next_offset"])
        submission_urls = [url for url in requested_urls if "submissions" in url]
        self.assertEqual(len(submission_urls), 2)
        self.assertTrue(all("offset=0" in url for url in submission_urls))

    def test_full_sync_keeps_continuation_offset_after_page_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "learning.db"
            submission_calls = 0
            requested_urls = []

            def fake_fetch(url, headers, *args, **kwargs):
                nonlocal submission_calls
                if "problems/all" in url:
                    return {"user_name": "alice", "stat_status_pairs": []}
                requested_urls.append(url)
                submission_calls += 1
                if submission_calls <= 50:
                    return {"submissions_dump": [{"id": submission_calls, "title": "Two Sum",
                                                    "status_display": "Accepted", "is_pending": "Not Pending",
                                                    "timestamp": "1780000000", "lang": "python3"}], "has_next": True}
                return {"submissions_dump": [], "has_next": False}

            with patch.dict(leetcode.server_runtime._values, {"_fetch_json_with_retry": fake_fetch}), patch(
                "interview_forge.services.leetcode.time.sleep"
            ):
                first = leetcode.leetcode_sync({"leetcode_session": "session-secret"}, db_path=db_path, full=True)
                second = leetcode.leetcode_sync(
                    {"leetcode_session": "session-secret"}, db_path=db_path, full=True,
                    offset=first["next_offset"],
                )

        self.assertTrue(first["partial"])
        self.assertEqual(first["partial_error_category"], "page_limit")
        self.assertEqual(first["next_offset"], 50)
        self.assertTrue(first["has_more"])
        self.assertFalse(second["partial"])
        self.assertEqual(requested_urls[0].split("offset=", 1)[1].split("&", 1)[0], "0")
        self.assertEqual(requested_urls[-1].split("offset=", 1)[1].split("&", 1)[0], "50")

    def test_real_submission_replaces_older_synthetic_solved_row(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "learning.db"
            calls = {"submissions": 0}

            def fake_fetch(url, headers, *args, **kwargs):
                if "problems/all" in url:
                    return {
                        "user_name": "alice",
                        "stat_status_pairs": [{
                            "status": "ac",
                            "stat": {"question__title_slug": "two-sum"},
                        }],
                    }
                calls["submissions"] += 1
                if calls["submissions"] == 1:
                    return {"submissions_dump": [], "has_next": False}
                return {
                    "submissions_dump": [{
                        "id": 9001,
                        "title": "两数之和",
                        "status_display": "Accepted",
                        "is_pending": "Not Pending",
                        "timestamp": "1780000000",
                        "lang": "python3",
                    }],
                    "has_next": False,
                }

            with patch.dict(leetcode.server_runtime._values, {"_fetch_json_with_retry": fake_fetch}):
                first = leetcode.leetcode_sync(
                    {"leetcode_session": "session-secret"}, db_path=db_path, full=False
                )
                with closing(leetcode.server_runtime.connect(db_path)) as connection:
                    synthetic = connection.execute(
                        "SELECT source, lc_id, submitted_at FROM submissions WHERE problem_id = 1"
                    ).fetchone()
                second = leetcode.leetcode_sync(
                    {"leetcode_session": "session-secret"}, db_path=db_path, full=False
                )
                with closing(leetcode.server_runtime.connect(db_path)) as connection:
                    rows = connection.execute(
                        "SELECT source, lc_id, submitted_at FROM submissions WHERE problem_id = 1"
                    ).fetchall()

        self.assertEqual(first["solved_added"], 1)
        self.assertEqual(synthetic["source"], "sync")
        self.assertIsNone(synthetic["lc_id"])
        self.assertLess("2026-05-29T04:26:40+08:00", synthetic["submitted_at"])
        self.assertEqual(second["submissions_added"], 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "sync")
        self.assertEqual(rows[0]["lc_id"], 9001)
        self.assertNotEqual(rows[0]["submitted_at"], "")


class LeetCodeTaskReliabilityTests(unittest.TestCase):
    def setUp(self):
        with leetcode.SYNC_TASKS_LOCK:
            leetcode.SYNC_TASKS.clear()

    def tearDown(self):
        with leetcode.SYNC_TASKS_LOCK:
            leetcode.SYNC_TASKS.clear()

    def _wait_for_done(self, task_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = leetcode.sync_task_status(task_id, owner="alice")
            if status is not None and not status["running"]:
                return status
            time.sleep(0.01)
        self.fail("LeetCode sync task did not finish")

    def test_same_owner_has_one_running_worker_and_same_task_id(self):
        started = threading.Event()
        release = threading.Event()
        calls = []

        def fake_sync(*args, **kwargs):
            calls.append(True)
            started.set()
            self.assertTrue(release.wait(timeout=5))
            return {"submissions_seen": 1, "submissions_added": 1, "partial": False}

        with patch.dict(leetcode.server_runtime._values, {"leetcode_sync": fake_sync}), patch(
            "interview_forge.services.leetcode.log_event"
        ) as events:
            task_ids = [
                leetcode.start_leetcode_sync_task(
                    {"leetcode_session": "session-secret"}, False, owner="alice", db_path=Path("test.db")
                )
                for _ in range(5)
            ]
            self.assertTrue(started.wait(timeout=5))
            self.assertEqual(len(set(task_ids)), 1)
            self.assertEqual(len(calls), 1)
            reused = [call for call in events.call_args_list if call.args and call.args[0] == "leetcode_sync_reused"]
            self.assertEqual(len(reused), 4)
            release.set()
            result = self._wait_for_done(task_ids[0])
        self.assertEqual(result["result"]["submissions_added"], 1)

    def test_same_owner_different_sync_modes_are_not_silently_reused(self):
        started = threading.Event()
        release = threading.Event()

        def fake_sync(*args, **kwargs):
            started.set()
            self.assertTrue(release.wait(timeout=5))
            return {"submissions_seen": 0, "submissions_added": 0, "partial": False}

        with patch.dict(leetcode.server_runtime._values, {"leetcode_sync": fake_sync}):
            incremental = leetcode.start_leetcode_sync_task({}, False, owner="alice", db_path=Path("alice.db"))
            self.assertTrue(started.wait(timeout=5))
            with self.assertRaises(leetcode.LeetCodeSyncError) as raised:
                leetcode.start_leetcode_sync_task({}, True, owner="alice", db_path=Path("alice.db"))
            release.set()
            self._wait_for_done(incremental)

        self.assertEqual(raised.exception.category, "sync_in_progress")
        self.assertEqual(raised.exception.status, 409)

    def test_different_owners_can_run_concurrently(self):
        started = {"alice": threading.Event(), "bob": threading.Event()}
        release = threading.Event()
        calls = []

        def fake_sync(*args, **kwargs):
            owner = "alice" if len(calls) == 0 else "bob"
            calls.append(owner)
            started[owner].set()
            self.assertTrue(release.wait(timeout=5))
            return {"submissions_seen": 0, "submissions_added": 0, "partial": False}

        with patch.dict(leetcode.server_runtime._values, {"leetcode_sync": fake_sync}), patch(
            "interview_forge.services.leetcode.log_event"
        ):
            alice = leetcode.start_leetcode_sync_task({}, False, owner="alice", db_path=Path("alice.db"))
            bob = leetcode.start_leetcode_sync_task({}, False, owner="bob", db_path=Path("bob.db"))
            self.assertNotEqual(alice, bob)
            self.assertTrue(started["alice"].wait(timeout=5))
            self.assertTrue(started["bob"].wait(timeout=5))
            self.assertEqual(len(calls), 2)
            release.set()
            self._wait_for_done(alice)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = leetcode.sync_task_status(bob, owner="bob")
            if status is not None and not status["running"]:
                break
            time.sleep(0.01)
        else:
            self.fail("Bob's task did not finish")

    def test_partial_task_is_projected_as_degraded_in_admin_view(self):
        def fake_sync(*args, **kwargs):
            return {
                "submissions_seen": 1, "submissions_added": 0, "partial": True,
                "degraded": True, "partial_error_category": "provider_blocked",
            }

        with patch.dict(leetcode.server_runtime._values, {"leetcode_sync": fake_sync}), patch(
            "interview_forge.services.leetcode.log_event"
        ):
            task_id = leetcode.start_leetcode_sync_task({}, False, owner="alice", db_path=Path("alice.db"))
            status = self._wait_for_done(task_id)
        self.assertTrue(status["partial"])
        self.assertEqual(status["error_category"], "partial")
        self.assertEqual(status["degraded_category"], "provider_blocked")
        admin = leetcode.admin_list_sync_tasks()
        self.assertEqual(admin[0]["partial"], True)
        self.assertEqual(admin[0]["degraded_category"], "provider_blocked")

    def test_admin_operations_does_not_report_partial_as_succeeded(self):
        with patch.object(admin_operations, "admin_list_sync_tasks", return_value=[{
            "task_id": "task-1", "owner": "alice", "running": False,
            "error_category": "partial", "partial": True,
            "degraded_category": "provider_blocked", "created_at": "2026-09-16T10:00:00+08:00",
            "started_at": "2026-09-16T10:00:00+08:00", "finished_at": "2026-09-16T10:00:01+08:00",
        }]):
            result = admin_operations.list_tasks(kind="leetcode")
        self.assertEqual(result["items"][0]["status"], "degraded")
        self.assertEqual(result["items"][0]["error_code"], "partial:provider_blocked")
        self.assertEqual(result["counts"]["degraded"], 1)
        self.assertEqual(result["counts"]["succeeded"], 0)

    def test_task_events_do_not_contain_credentials_or_raw_exception(self):
        secret = "session-secret-value"

        def failing_sync(*args, **kwargs):
            raise leetcode.LeetCodeSyncError("provider_blocked", "安全错误")

        with patch.dict(leetcode.server_runtime._values, {"leetcode_sync": failing_sync}), patch(
            "interview_forge.services.leetcode.log_event"
        ) as events:
            task_id = leetcode.start_leetcode_sync_task(
                {"leetcode_session": secret, "leetcode_csrf": "csrf-secret"},
                False, owner="alice", db_path=Path("alice.db"),
            )
            self._wait_for_done(task_id)
        serialized = json.dumps(events.call_args_list, default=str, ensure_ascii=False)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("csrf-secret", serialized)
        self.assertNotIn("安全错误", serialized)
        self.assertIn("leetcode_sync_failed", serialized)


class LeetCodeConnectPageTests(unittest.TestCase):
    def test_connection_page_blocks_duplicate_sync_and_releases_both_buttons(self):
        source = (Path(__file__).resolve().parents[1] / "pages" / "leetcode-connect.html").read_text(encoding="utf-8")
        self.assertIn("let syncInFlight=false", source)
        self.assertIn("if(syncInFlight)return;", source)
        self.assertIn("syncBtn.disabled=busy", source)
        self.assertIn("syncFullBtn.disabled=busy", source)
        self.assertIn("finally{setSyncBusy(false);}", source)
        self.assertIn("sessionStorage", source)

    def test_connection_page_invalidates_full_cursor_when_account_changes(self):
        source = (Path(__file__).resolve().parents[1] / "pages" / "leetcode-connect.html").read_text(encoding="utf-8")
        self.assertIn("function clearLeetcodeFullSyncCursor()", source)
        self.assertIn("forge_leetcode_sync_user", source)
        self.assertIn("if(previous&&previous!==current)clearLeetcodeFullSyncCursor();", source)
        self.assertIn("clearLeetcodeFullSyncCursor();\n    if(data.connected)rememberLeetcodeSyncUser(data.user_name);", source)
        self.assertIn("clearLeetcodeFullSyncCursor();clearLeetcodeSyncUser();", source)

    def test_homepage_preserves_and_continues_partial_sync(self):
        source = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")
        self.assertIn("sessionStorage", source)
        self.assertLess(source.index("if(task.partial||result.partial)"), source.index("if(task.error)"))
        self.assertIn("await refresh();", source[source.index("if(task.partial||result.partial)"):])


if __name__ == "__main__":
    unittest.main()
