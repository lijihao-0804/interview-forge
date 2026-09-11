import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from tools import ai_coach
from tools import study_server as server


AS_OF = "2026-09-07T12:00:00+08:00"


CATALOG = {
    1: {
        "id": 1,
        "title": "题目一",
        "category": "数组",
        "difficulty": "简单",
        "method": "双指针",
        "folder": "数组",
    },
    2: {
        "id": 2,
        "title": "题目二",
        "category": "哈希表",
        "difficulty": "中等",
        "method": "哈希",
        "folder": "哈希表",
    },
}


MANIFEST = {
    "modules": [
        {
            "id": "hot100",
            "title": "算法刷题",
            "chapters": [
                {"id": "hot100:0001", "title": "题目一", "url": "hot100/0001.html"},
                {"id": "hot100:0002", "title": "题目二", "url": "hot100/0002.html"},
            ],
        },
        {
            "id": "module-a",
            "title": "测试课程",
            "chapters": [
                {"id": "module-a:01", "title": "章节一", "url": "module-a/01.html"},
            ],
        },
    ],
    "routes": {
        "/library/module-a-01.html": {
            "module_id": "module-a",
            "content_id": "module-a:01",
        },
    },
}


SCHEMA = server.SCHEMA


def create_learning_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()


def insert_submission(path: Path, problem_id: int, event_id: int = 1) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """INSERT INTO submissions(
                   id, problem_id, status, lang, submitted_at, source, lc_id
               ) VALUES (?, ?, 'ac', 'java', ?, 'manual', NULL)""",
            (event_id, problem_id, AS_OF),
        )
        connection.commit()
    finally:
        connection.close()


class LearningAnalyticsAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "site"
        self.users_dir = self.root / "data" / "users"
        self.default_db = self.root / "data" / "default.db"
        self.users = {
            "token-a": {"id": 1, "username": "alice", "role": "user", "nickname": "alice", "lang": "java"},
            "token-b": {"id": 2, "username": "bob", "role": "user", "nickname": "bob", "lang": "java"},
            "token-c": {"id": 3, "username": "charlie", "role": "user", "nickname": "charlie", "lang": "java"},
        }
        self.patches = [
            patch.object(server, "ROOT", self.root),
            patch.object(server, "USERS_DIR", self.users_dir),
            patch.object(server, "DB_PATH", self.default_db),
            patch.object(server, "PROBLEM_BY_ID", CATALOG),
            patch.object(server, "load_library_manifest", return_value=MANIFEST),
            patch.object(server, "session_user", side_effect=lambda token: self.users.get(token)),
            patch.object(server, "QUIET", True),
        ]
        for item in self.patches:
            item.start()
        with server._ANALYTICS_CACHE_LOCK:
            server._ANALYTICS_CACHE.clear()
            server._ANALYTICS_CACHE_GENERATIONS.clear()
            server._ANALYTICS_GENERATION_TOUCHED.clear()
            server._ANALYTICS_CACHE_ACTIVE.clear()
        with server._DASH_CACHE_LOCK:
            server._DASH_CACHE.clear()
            server._DASH_CACHE_GENERATIONS.clear()

        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.StudyHandler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        with server._ANALYTICS_CACHE_LOCK:
            server._ANALYTICS_CACHE.clear()
            server._ANALYTICS_CACHE_GENERATIONS.clear()
            server._ANALYTICS_GENERATION_TOUCHED.clear()
            server._ANALYTICS_CACHE_ACTIVE.clear()
        with server._DASH_CACHE_LOCK:
            server._DASH_CACHE.clear()
            server._DASH_CACHE_GENERATIONS.clear()
        with server.SYNC_TASKS_LOCK:
            server.SYNC_TASKS.clear()
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def user_db(self, username: str) -> Path:
        return self.users_dir / username / "hot100-study.db"

    def request(self, path: str, token: str | None = "token-a", payload: dict | None = None):
        body = None
        headers = {}
        if token:
            headers["Cookie"] = f"{server.SESSION_COOKIE}={token}"
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            f"http://127.0.0.1:{self.httpd.server_address[1]}{path}",
            data=body,
            headers=headers,
            method="POST" if payload is not None else "GET",
        )
        try:
            with urlopen(request, timeout=5) as response:
                raw = response.read()
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    parsed = raw
                return response.status, parsed, response.headers
        except HTTPError as exc:
            raw = exc.read()
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed = raw
            return exc.code, parsed, exc.headers

    def static_request(self, path: str, token: str = "token-a") -> int:
        status, body, _headers = self.request(quote(path, safe="/"), token=token)
        self.assertIsInstance(body, bytes)
        return status

    def test_unauthenticated_request_is_401(self):
        status, body, _headers = self.request("/api/coach/analytics", token=None)
        self.assertEqual(status, 401)
        self.assertEqual(body, {"error": "未登录"})

    def test_context_post_is_authenticated_isolated_and_read_only(self):
        alice_db = self.user_db("alice")
        bob_db = self.user_db("bob")
        create_learning_db(alice_db)
        create_learning_db(bob_db)
        insert_submission(alice_db, 1)
        insert_submission(bob_db, 2)
        insert_submission(bob_db, 2, event_id=2)

        with patch.object(server, "_invalidate_analytics_cache") as invalidate_analytics, patch.object(
            server, "_invalidate_dashboard_cache"
        ) as invalidate_dashboard:
            status_a, body_a, _ = self.request(
                "/api/coach/context?username=bob&db_path=%2Ftmp%2Fother.db",
                token="token-a",
                payload={
                    "task": "learning_diagnosis",
                    "user_request": "请根据我的学习事实给出诊断",
                    "profile": {"available_minutes": 20},
                },
            )
        status_b, body_b, _ = self.request(
            "/api/coach/context",
            token="token-b",
            payload={"task": "learning_diagnosis"},
        )

        self.assertEqual(status_a, 201)
        self.assertEqual(status_b, 201)
        self.assertEqual(body_a["summary"]["total_submissions"], 1)
        self.assertEqual(body_b["summary"]["total_submissions"], 2)
        self.assertEqual(body_a["profile"], {"available_minutes": 20})
        self.assertEqual(invalidate_analytics.call_count, 0)
        self.assertEqual(invalidate_dashboard.call_count, 0)
        serialized = json.dumps(body_a, ensure_ascii=False)
        self.assertNotIn("alice", serialized)
        self.assertNotIn("bob", serialized)
        self.assertNotIn(str(bob_db), serialized)

    def test_context_post_validation_and_problem_target_scope(self):
        db_path = self.user_db("alice")
        create_learning_db(db_path)
        insert_submission(db_path, 1)
        insert_submission(db_path, 2, event_id=2)

        status, body, _ = self.request(
            "/api/coach/context",
            payload={"task": "problem_review"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "target_problem_id is invalid"})

        status, body, _ = self.request(
            "/api/coach/context",
            payload={"task": "learning_diagnosis", "credentials": "secret-sentinel"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "请求参数不正确"})
        self.assertNotIn("secret-sentinel", json.dumps(body, ensure_ascii=False))

        status, body, _ = self.request(
            "/api/coach/context",
            payload={
                "task": "problem_review",
                "target_problem_id": 1,
                "profile": {
                    "nickname": "nickname-sentinel",
                    "password": "password-sentinel",
                    "learning_goal": "复盘错误",
                },
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual({item["problem_id"] for item in body["facts"]}, {1})
        # The fixture is intentionally dated; once the clock passes its first
        # review interval a valid due signal may appear.  The invariant here
        # is target isolation, not the absence of a date-dependent signal.
        self.assertTrue({item["entity_id"] for item in body["signals"]}.issubset({"1"}))
        self.assertEqual(body["profile"], {"learning_goal": "复盘错误"})
        serialized = json.dumps(body, ensure_ascii=False)
        self.assertNotIn("nickname-sentinel", serialized)
        self.assertNotIn("password-sentinel", serialized)

    def test_context_post_route_reservation_and_unauthenticated_rejection(self):
        status, body, _ = self.request(
            "/api/coach/context",
            token=None,
            payload={"task": "learning_route", "user_request": "推荐课程"},
        )
        self.assertEqual(status, 401)
        self.assertEqual(body, {"error": "未登录"})

        db_path = self.user_db("alice")
        create_learning_db(db_path)
        status, body, _ = self.request(
            "/api/coach/context",
            payload={"task": "learning_route", "user_request": "推荐课程"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["summary"]["course_retrieval"], "unavailable")
        self.assertEqual(body["summary"]["reason_code"], "no_course_retrieval")
        self.assertEqual(body["facts"], [])
        self.assertEqual(body["evidence"], [])

    def test_accounts_are_isolated_and_query_database_overrides_are_ignored(self):
        alice_db = self.user_db("alice")
        bob_db = self.user_db("bob")
        create_learning_db(alice_db)
        create_learning_db(bob_db)
        insert_submission(alice_db, 1)
        insert_submission(bob_db, 2)
        insert_submission(bob_db, 2, event_id=2)

        status_a, body_a, _ = self.request(
            "/api/coach/analytics?username=bob&user_id=2&db_path=%2Ftmp%2Fother.db",
            token="token-a",
        )
        status_b, body_b, _ = self.request("/api/coach/analytics", token="token-b")

        self.assertEqual(status_a, 200)
        self.assertEqual(status_b, 200)
        self.assertEqual(body_a["schema_version"], "analytics-v1")
        self.assertEqual(body_a["summary"]["total_submissions"], 1)
        self.assertEqual(body_b["summary"]["total_submissions"], 2)
        self.assertNotIn("token-a", json.dumps(body_a, ensure_ascii=False))
        self.assertNotIn(str(bob_db), json.dumps(body_a, ensure_ascii=False))

    def test_missing_current_user_db_does_not_fall_back_to_default_db(self):
        create_learning_db(self.default_db)
        insert_submission(self.default_db, 1)

        status, body, _ = self.request("/api/coach/analytics", token="token-c")

        self.assertEqual(status, 200)
        self.assertEqual(body["summary"]["total_submissions"], 0)
        self.assertIn("no_learning_data", body["data_quality"]["reason_codes"])

    def test_cache_hit_ttl_expiry_and_explicit_invalidation(self):
        db_path = self.user_db("alice")
        create_learning_db(db_path)
        real_builder = server.build_learning_analytics
        with patch.object(server, "build_learning_analytics", wraps=real_builder) as builder:
            with patch.object(server.time, "time", return_value=100.0):
                first = server.analytics_cached(db_path)
            with patch.object(server.time, "time", return_value=100.0):
                second = server.analytics_cached(db_path)
            self.assertIs(first, second)
            self.assertEqual(builder.call_count, 1)

            with patch.object(server.time, "time", return_value=161.0):
                third = server.analytics_cached(db_path)
            self.assertIsNot(first, third)
            self.assertEqual(builder.call_count, 2)

            server._invalidate_analytics_cache(db_path)
            with patch.object(server.time, "time", return_value=161.0):
                server.analytics_cached(db_path)
            self.assertEqual(builder.call_count, 3)

    def test_cache_key_is_versioned_hashed_and_a_b_isolation_is_exact(self):
        alice_db = self.user_db("alice")
        bob_db = self.user_db("bob")
        create_learning_db(alice_db)
        create_learning_db(bob_db)
        real_builder = server.build_learning_analytics
        with patch.object(server, "build_learning_analytics", wraps=real_builder) as builder:
            alice_first = server.analytics_cached(alice_db)
            bob_first = server.analytics_cached(bob_db)
            self.assertIsNot(alice_first, bob_first)
            self.assertIs(server.analytics_cached(bob_db), bob_first)

            alice_key = server._analytics_cache_key(alice_db)
            self.assertNotIn(str(alice_db.resolve()), alice_key)
            self.assertIn(server.ANALYTICS_SCHEMA_VERSION, alice_key)
            self.assertIn(server.ANALYTICS_RULE_VERSION, alice_key)
            self.assertIn(":g", alice_key)

            server._invalidate_analytics_cache(alice_db)
            self.assertIs(server.analytics_cached(bob_db), bob_first)
            alice_second = server.analytics_cached(alice_db)
            self.assertIsNot(alice_second, alice_first)
            self.assertEqual(builder.call_count, 3)

            old_rule_version = server.ANALYTICS_RULE_VERSION
            with patch.object(server, "ANALYTICS_RULE_VERSION", old_rule_version + "-ab"):
                rule_isolated = server.analytics_cached(alice_db)
            self.assertIsNot(rule_isolated, alice_second)
            self.assertEqual(builder.call_count, 4)

    def test_cache_expiry_capacity_and_generation_state_are_bounded(self):
        real_result = {"schema_version": "analytics-v1", "summary": {}}
        paths = [self.user_db(f"u{i:03d}") for i in range(300)]
        with patch.object(server, "build_learning_analytics", return_value=real_result) as builder:
            with patch.object(server.time, "time", return_value=100.0):
                for path in paths:
                    server.analytics_cached(path)
            with server._ANALYTICS_CACHE_LOCK:
                self.assertLessEqual(len(server._ANALYTICS_CACHE), 256)
                self.assertLessEqual(len(server._ANALYTICS_CACHE_GENERATIONS), 256)

            with patch.object(server.time, "time", return_value=200.0):
                server.analytics_cached(paths[-1])
            with server._ANALYTICS_CACHE_LOCK:
                self.assertLessEqual(len(server._ANALYTICS_CACHE), 1)
        self.assertEqual(builder.call_count, 301)

    def test_analytics_concurrent_builds_pin_generation_through_invalidation_and_capacity_prune(self):
        db_path = self.user_db("alice")
        create_learning_db(db_path)
        ready = threading.Barrier(2)
        first_ready = threading.Event()
        second_ready = threading.Event()
        release_first = threading.Event()
        release_second = threading.Event()
        call_lock = threading.Lock()
        call_count = 0
        results = []
        errors = []

        def blocked_builder(*_args, **_kwargs):
            nonlocal call_count
            with call_lock:
                call_count += 1
                call_no = call_count
            if call_no >= 3:
                return {"snapshot": "new"}
            try:
                ready.wait(timeout=5)
            except threading.BrokenBarrierError as exc:
                errors.append(exc)
                raise
            (first_ready if call_no == 1 else second_ready).set()
            release = release_first if call_no == 1 else release_second
            if not release.wait(timeout=5):
                error = TimeoutError(f"analytics build {call_no} was not released")
                errors.append(error)
                raise error
            return {"snapshot": f"old-{call_no}"}

        def run_build():
            try:
                results.append(server.analytics_cached(db_path))
            except BaseException as exc:
                errors.append(exc)

        with patch.object(server, "build_learning_analytics", side_effect=blocked_builder):
            first = threading.Thread(target=run_build)
            second = threading.Thread(target=run_build)
            first.start()
            second.start()
            self.assertTrue(first_ready.wait(timeout=5))
            self.assertTrue(second_ready.wait(timeout=5))

            server._invalidate_analytics_cache(db_path)
            release_first.set()
            first.join(timeout=5)
            self.assertFalse(first.is_alive())

            # Force the generation-pruning path while the second build is
            # still in flight.  Its reference must keep the invalidated
            # generation alive even though the first build already finished.
            with patch.object(server, "_ANALYTICS_GENERATION_MAX_ENTRIES", 0):
                with server._ANALYTICS_CACHE_LOCK:
                    server._prune_analytics_generations_locked()
                    resolved = str(db_path.resolve())
                    self.assertEqual(server._ANALYTICS_CACHE_ACTIVE.get(resolved), 1)
                    self.assertIn(resolved, server._ANALYTICS_CACHE_GENERATIONS)

            release_second.set()
            second.join(timeout=5)
            self.assertFalse(second.is_alive())

            self.assertEqual(errors, [])
            self.assertEqual({item["snapshot"] for item in results}, {"old-1", "old-2"})
            with server._ANALYTICS_CACHE_LOCK:
                resolved = str(db_path.resolve())
                self.assertEqual(server._ANALYTICS_CACHE_ACTIVE.get(resolved, 0), 0)
                self.assertFalse(server._analytics_cache_has_path_locked(resolved))

            fresh = server.analytics_cached(db_path)
            self.assertEqual(fresh, {"snapshot": "new"})
            self.assertEqual(call_count, 3)

    def test_analytics_build_exception_releases_each_inflight_reference(self):
        db_path = self.user_db("alice")
        create_learning_db(db_path)
        ready = threading.Barrier(2)
        failed = threading.Event()
        success_started = threading.Event()
        release_success = threading.Event()
        outcomes = []
        errors = []
        call_lock = threading.Lock()
        call_count = 0

        def builder(*_args, **_kwargs):
            nonlocal call_count
            with call_lock:
                call_count += 1
                call_no = call_count
            ready.wait(timeout=5)
            if call_no == 1:
                failed.set()
                raise RuntimeError("expected analytics build failure")
            success_started.set()
            if not release_success.wait(timeout=5):
                raise TimeoutError("successful analytics build was not released")
            return {"snapshot": "success"}

        def run_build():
            try:
                outcomes.append(server.analytics_cached(db_path))
            except BaseException as exc:
                errors.append(exc)

        with patch.object(server, "build_learning_analytics", side_effect=builder):
            first = threading.Thread(target=run_build)
            second = threading.Thread(target=run_build)
            first.start()
            second.start()
            # The first build raises, while the second remains in flight.
            self.assertTrue(failed.wait(timeout=5))
            self.assertTrue(success_started.wait(timeout=5))
            with server._ANALYTICS_CACHE_LOCK:
                self.assertEqual(
                    server._ANALYTICS_CACHE_ACTIVE.get(str(db_path.resolve())),
                    1,
                )
            release_success.set()
            first.join(timeout=5)
            second.join(timeout=5)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RuntimeError)
        with server._ANALYTICS_CACHE_LOCK:
            self.assertEqual(server._ANALYTICS_CACHE_ACTIVE, {})

    def test_dashboard_invalidation_blocks_old_inflight_snapshot_from_cache(self):
        db_path = self.user_db("alice")
        create_learning_db(db_path)
        started = threading.Event()
        release = threading.Event()
        result_holder = []
        errors = []

        def old_dashboard(*_args, **_kwargs):
            started.set()
            if not release.wait(timeout=5):
                raise TimeoutError("dashboard build was not released")
            return {"snapshot": "old"}

        def run_dashboard():
            try:
                result_holder.append(server.dashboard_cached(db_path))
            except BaseException as exc:
                errors.append(exc)

        with patch.object(server, "dashboard_data", side_effect=old_dashboard):
            worker = threading.Thread(target=run_dashboard)
            worker.start()
            self.assertTrue(started.wait(timeout=5))
            server._invalidate_dashboard_cache(db_path)
            release.set()
            worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(result_holder, [{"snapshot": "old"}])
        cache_key = str(db_path.resolve())
        with server._DASH_CACHE_LOCK:
            self.assertNotIn(cache_key, server._DASH_CACHE)

        with patch.object(server, "dashboard_data", return_value={"snapshot": "fresh"}) as builder:
            fresh = server.dashboard_cached(db_path)
        self.assertEqual(fresh, {"snapshot": "fresh"})
        self.assertEqual(builder.call_count, 1)
        with server._DASH_CACHE_LOCK:
            self.assertEqual(server._DASH_CACHE[cache_key][1], {"snapshot": "fresh"})

    def test_dashboard_cache_hit_resolves_legacy_dash_ttl_without_recursion(self):
        db_path = self.user_db("alice")
        create_learning_db(db_path)
        cache_key = str(db_path.resolve())
        cached = {"snapshot": "cached"}
        with server._DASH_CACHE_LOCK:
            server._DASH_CACHE[cache_key] = (time.time(), cached)

        self.assertEqual(float(server._DASH_TTL), 60.0)
        with patch.object(server, "dashboard_data", side_effect=AssertionError("cache hit should not rebuild dashboard")):
            self.assertIs(server.dashboard_cached(db_path), cached)

    def test_complete_does_not_depend_on_redundant_content_mirror(self):
        db_path = self.user_db("alice")
        create_learning_db(db_path)
        server.analytics_cached(db_path)
        server.dashboard_cached(db_path)

        def failing_content(module_id, content_id, failing_db_path):
            connection = sqlite3.connect(failing_db_path)
            try:
                connection.execute(
                    "INSERT INTO content_events(module_id, content_id, action, studied_at, study_date, round_no) "
                    "VALUES (?, ?, 'complete', ?, ?, 1)",
                    (module_id, content_id, AS_OF, AS_OF[:10]),
                )
                connection.commit()
            finally:
                connection.close()
            raise RuntimeError("content write failed after commit")

        with patch.object(server, "complete_content", side_effect=failing_content) as mirror:
            status, body, _headers = self.request("/api/complete", payload={"problem_id": 1})
        self.assertEqual(status, 201)
        self.assertEqual(body["problem_id"], 1)
        self.assertEqual(body["round_no"], 1)
        mirror.assert_not_called()

        status, analytics, _headers = self.request("/api/coach/analytics")
        self.assertEqual(status, 200)
        self.assertEqual(analytics["data_quality"]["table_row_counts"]["study_events"], 1)
        self.assertEqual(analytics["data_quality"]["table_row_counts"]["submissions"], 1)
        self.assertEqual(analytics["data_quality"]["table_row_counts"]["content_events"], 0)
        with server._DASH_CACHE_LOCK:
            self.assertNotIn(str(db_path.resolve()), server._DASH_CACHE)
        status, dashboard, _headers = self.request("/api/dashboard")
        self.assertEqual(status, 200)
        self.assertEqual(dashboard["summary"]["today_rounds"], 1)
        self.assertEqual(dashboard["problems"]["1"]["rounds"], 1)
        self.assertFalse(self.default_db.exists())

    def test_async_sync_http_route_waits_for_worker_and_invalidates_after_success(self):
        db_path = self.user_db("alice")
        create_learning_db(db_path)
        server.set_credentials({"leetcode_session": "test-session"}, db_path)
        finished = threading.Event()

        def fake_fetch(url, headers, *args, **kwargs):
            self.assertEqual(headers.get("Cookie"), "LEETCODE_SESSION=test-session")
            if "problems/all" in url:
                return {"user_name": "alice", "stat_status_pairs": []}
            if "submissions" in url:
                self.assertIn("offset=0&limit=100", url)
                finished.set()
                return {
                    "submissions_dump": [{
                        "id": 9001,
                        "title": "题目一",
                        "status_display": "Accepted",
                        "is_pending": "Not Pending",
                        "timestamp": "1780000000",
                        "lang": "python3",
                    }],
                    "has_next": False,
                }
            raise AssertionError(url)

        real_builder = server.build_learning_analytics
        with patch.object(server, "build_learning_analytics", wraps=real_builder) as builder:
            server.analytics_cached(db_path)
            with patch.object(server, "_fetch_json_with_retry", side_effect=fake_fetch):
                status, started, _headers = self.request(
                    "/api/leetcode/sync",
                    payload={"full": False, "async": True},
                )
                self.assertEqual(status, 201)
                task_id = started["task_id"]
                self.assertTrue(finished.wait(timeout=5))

                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    status, task, _headers = self.request(
                        f"/api/leetcode/sync/status?task_id={quote(task_id)}"
                    )
                    self.assertEqual(status, 200)
                    if not task["running"]:
                        break
                    time.sleep(0.01)
                else:
                    self.fail("异步同步任务未完成")

            status, analytics, _headers = self.request("/api/coach/analytics")
            self.assertEqual(status, 200)
            self.assertEqual(analytics["summary"]["total_submissions"], 1)
            self.assertEqual(builder.call_count, 2)
        self.assertFalse(self.default_db.exists())

    def test_async_sync_rejects_missing_session_with_structured_safe_error(self):
        db_path = self.user_db("alice")
        create_learning_db(db_path)

        status, body, _headers = self.request(
            "/api/leetcode/sync",
            payload={"full": False, "async": True},
        )

        self.assertEqual(status, 409)
        self.assertEqual(body["error_category"], "not_configured")
        self.assertIn("LEETCODE_SESSION", body["error"])
        self.assertNotIn("Cookie", json.dumps(body, ensure_ascii=False))
        with server.SYNC_TASKS_LOCK:
            self.assertFalse(server.SYNC_TASKS)

    def test_async_sync_reports_invalid_session_without_exposing_credential(self):
        db_path = self.user_db("alice")
        create_learning_db(db_path)
        secret = "private-leetcode-session"
        server.set_credentials({"leetcode_session": secret}, db_path)

        with patch.object(
            server,
            "_fetch_json_with_retry",
            return_value={"user_name": "", "stat_status_pairs": []},
        ):
            status, started, _headers = self.request(
                "/api/leetcode/sync",
                payload={"full": False, "async": True},
            )
            self.assertEqual(status, 201)
            task_id = started["task_id"]
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                status, task, _headers = self.request(
                    f"/api/leetcode/sync/status?task_id={quote(task_id)}"
                )
                self.assertEqual(status, 200)
                if not task["running"]:
                    break
                time.sleep(0.01)
            else:
                self.fail("失效会话同步任务未结束")

        self.assertEqual(task["error_category"], "session_invalid")
        serialized = json.dumps(task, ensure_ascii=False)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("Cookie", serialized)

    def test_async_sync_failure_after_write_invalidates_and_wrong_owner_is_denied(self):
        db_path = self.user_db("alice")
        create_learning_db(db_path)
        server.set_credentials({"leetcode_session": "test-session"}, db_path)
        server.analytics_cached(db_path)
        server.dashboard_cached(db_path)
        entered = threading.Event()
        release = threading.Event()

        def failing_sync(credentials, db_path, full=False, progress=None):
            insert_submission(db_path, 2, event_id=1)
            entered.set()
            self.assertTrue(release.wait(timeout=5))
            raise RuntimeError("sync failed after local write")

        with patch.object(server, "leetcode_sync", side_effect=failing_sync):
            status, started, _headers = self.request(
                "/api/leetcode/sync",
                payload={"async": True},
            )
            self.assertEqual(status, 201)
            task_id = started["task_id"]
            self.assertTrue(entered.wait(timeout=5))

            # Rebuild a snapshot while the worker is still blocked; only the
            # worker's finally invalidation can remove this newly-created one.
            status, before_failure, _headers = self.request("/api/coach/analytics")
            self.assertEqual(status, 200)
            self.assertEqual(before_failure["summary"]["total_submissions"], 1)
            status, _body, _headers = self.request(
                f"/api/leetcode/sync/status?task_id={quote(task_id)}",
                token="token-b",
            )
            self.assertEqual(status, 404)

            release.set()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                status, task, _headers = self.request(
                    f"/api/leetcode/sync/status?task_id={quote(task_id)}"
                )
                self.assertEqual(status, 200)
                if not task["running"]:
                    self.assertEqual(task["error"], "同步服务暂时不可用，请稍后重试")
                    self.assertEqual(task["error_category"], "server_error")
                    break
                time.sleep(0.01)
            else:
                self.fail("失败的异步同步任务未完成")

            status, after_failure, _headers = self.request("/api/coach/analytics")
            self.assertEqual(status, 200)
            self.assertEqual(after_failure["summary"]["total_submissions"], 1)
        with server._DASH_CACHE_LOCK:
            self.assertNotIn(str(db_path.resolve()), server._DASH_CACHE)
        self.assertFalse(self.default_db.exists())

    def test_unavailable_and_internal_errors_are_controlled(self):
        db_path = self.user_db("alice")
        create_learning_db(db_path)
        with patch.object(
            server,
            "build_learning_analytics",
            side_effect=server.AnalyticsUnavailableError("secret /private/locked.db"),
        ):
            status, body, headers = self.request("/api/coach/analytics")
        self.assertEqual(status, 503)
        self.assertEqual(body, {"error": "学习分析暂时不可用，请稍后重试", "retryable": True})
        self.assertEqual(headers.get("Retry-After"), "1")
        self.assertNotIn("secret", json.dumps(body, ensure_ascii=False))
        self.assertNotIn("locked.db", json.dumps(body, ensure_ascii=False))

        with patch.object(server, "build_learning_analytics", side_effect=ValueError("secret config path")):
            status, body, _headers = self.request("/api/coach/analytics")
        self.assertEqual(status, 500)
        self.assertEqual(body, {"error": "学习分析服务暂时不可用"})
        self.assertNotIn("secret", json.dumps(body, ensure_ascii=False))

    def test_successful_learning_writes_and_get_views_invalidate_analytics_cache(self):
        db_path = self.user_db("alice")
        create_learning_db(db_path)
        problem_page = self.root / "books" / "hot100" / "03-题解" / "数组" / "0001-test.html"
        problem_page.parent.mkdir(parents=True, exist_ok=True)
        problem_page.write_text("<html><body>problem</body></html>", encoding="utf-8")
        content_page = self.root / "library" / "module-a-01.html"
        content_page.parent.mkdir(parents=True, exist_ok=True)
        content_page.write_text("<html><body>content</body></html>", encoding="utf-8")

        real_builder = server.build_learning_analytics
        with patch.object(server, "build_learning_analytics", wraps=real_builder) as builder:
            self.request("/api/coach/analytics")
            write_requests = [
                ("/api/complete", {"problem_id": 1}),
                ("/api/content/complete", {"module_id": "module-a", "content_id": "module-a:01"}),
                ("/api/mark", {"target_type": "problem", "target_id": "1", "mark": "weak"}),
                ("/api/settings", {"key": "daily_goal_rounds", "value": "5"}),
                ("/api/plan/pin", {"problem_id": 1}),
                ("/api/submit", {"problem_id": 1, "status": "ac"}),
            ]
            for path, payload in write_requests:
                status, _body, _headers = self.request(path, payload=payload)
                self.assertEqual(status, 201, path)
                self.request("/api/coach/analytics")
            self.assertEqual(builder.call_count, 1 + len(write_requests))

            self.assertEqual(self.static_request("/books/hot100/03-题解/数组/0001-test.html"), 200)
            self.request("/api/coach/analytics")
            self.assertEqual(builder.call_count, 2 + len(write_requests))

            self.assertEqual(self.static_request("/library/module-a-01.html"), 200)
            self.request("/api/coach/analytics")
            self.assertEqual(builder.call_count, 3 + len(write_requests))

    def test_async_sync_invalidates_after_real_write_and_dashboard_cache(self):
        db_path = self.user_db("alice")
        create_learning_db(db_path)
        finished = threading.Event()

        def fake_sync(credentials, db_path, full=False, progress=None):
            self.assertEqual(credentials["leetcode_session"], "test-session")
            insert_submission(db_path, 1)
            finished.set()
            return {"submissions_added": 1, "full": bool(full)}

        real_builder = server.build_learning_analytics
        with patch.object(server, "build_learning_analytics", wraps=real_builder) as builder:
            server.analytics_cached(db_path)
            cache_key = str(db_path)
            with server._DASH_CACHE_LOCK:
                server._DASH_CACHE[cache_key] = (time.time(), {"stale": True})
            with patch.object(server, "leetcode_sync", side_effect=fake_sync):
                task_id = server.start_leetcode_sync_task(
                    {"leetcode_session": "test-session"},
                    full=False,
                    owner="alice",
                    db_path=db_path,
                )
                self.assertTrue(finished.wait(timeout=5))
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    status = server.sync_task_status(task_id, owner="alice")
                    if status is not None and not status["running"]:
                        break
                    time.sleep(0.01)
                else:
                    self.fail("异步同步任务未完成")

            server.analytics_cached(db_path)
            self.assertEqual(builder.call_count, 2)
            with server._DASH_CACHE_LOCK:
                self.assertNotIn(cache_key, server._DASH_CACHE)

    def test_dashboard_daily_and_plan_regression_shapes_remain_unchanged(self):
        db_path = self.user_db("alice")
        create_learning_db(db_path)

        dashboard_status, dashboard, _ = self.request("/api/dashboard")
        daily_status, daily, _ = self.request("/api/daily")
        plan_status, plan, _ = self.request("/api/plan")

        self.assertEqual(dashboard_status, 200)
        self.assertIn("summary", dashboard)
        self.assertIn("activity", dashboard)
        self.assertEqual(daily_status, 200)
        self.assertIn("summary", daily)
        self.assertIn("problems", daily)
        self.assertEqual(plan_status, 200)
        self.assertIn("count", plan)
        self.assertIn("items", plan)


class RealAuthenticationIsolationTests(unittest.TestCase):
    """Exercise the real auth.db/session/Cookie path without touching data/."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "site"
        self.data_dir = self.root / "data"
        self.data_dir.mkdir(parents=True)
        self.auth_db = self.data_dir / "auth.db"
        self.users_dir = self.data_dir / "users"
        self.default_db = self.data_dir / "default.db"
        self._auth_ready_before = server._AUTH_READY
        self._schema_done_before = set(server._SCHEMA_DONE)
        self._last_purge_before = server._LAST_SESSION_PURGE
        self._last_seen_before = dict(server._LAST_SEEN_TS)
        self.patches = [
            patch.object(server, "ROOT", self.root),
            patch.object(server, "DATA_DIR", self.data_dir),
            patch.object(server, "AUTH_DB_PATH", self.auth_db),
            patch.object(server, "USERS_DIR", self.users_dir),
            patch.object(server, "DB_PATH", self.default_db),
            patch.object(server, "PROBLEM_BY_ID", CATALOG),
            patch.object(server, "load_library_manifest", return_value=MANIFEST),
            patch.object(server, "QUIET", True),
            patch.object(server, "_AUTH_READY", False),
            patch.object(server, "_LAST_SESSION_PURGE", 0.0),
        ]
        for item in self.patches:
            item.start()
        with server._ANALYTICS_CACHE_LOCK:
            server._ANALYTICS_CACHE.clear()
            server._ANALYTICS_CACHE_GENERATIONS.clear()
            server._ANALYTICS_GENERATION_TOUCHED.clear()
            server._ANALYTICS_CACHE_ACTIVE.clear()
        with server._DASH_CACHE_LOCK:
            server._DASH_CACHE.clear()
            server._DASH_CACHE_GENERATIONS.clear()
        with server.SYNC_TASKS_LOCK:
            server.SYNC_TASKS.clear()

        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.StudyHandler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        with server._ANALYTICS_CACHE_LOCK:
            server._ANALYTICS_CACHE.clear()
            server._ANALYTICS_CACHE_GENERATIONS.clear()
            server._ANALYTICS_GENERATION_TOUCHED.clear()
            server._ANALYTICS_CACHE_ACTIVE.clear()
        with server._DASH_CACHE_LOCK:
            server._DASH_CACHE.clear()
            server._DASH_CACHE_GENERATIONS.clear()
        with server.SYNC_TASKS_LOCK:
            server.SYNC_TASKS.clear()
        for item in reversed(self.patches):
            item.stop()
        server._SCHEMA_DONE.intersection_update(self._schema_done_before)
        server._LAST_SEEN_TS.clear()
        server._LAST_SEEN_TS.update(self._last_seen_before)
        server._LAST_SESSION_PURGE = self._last_purge_before
        self.assertEqual(server._AUTH_READY, self._auth_ready_before)
        self.temp_dir.cleanup()

    def add_invite(self, code: str) -> None:
        with server.closing(server.connect_auth()) as connection:
            connection.execute(
                "INSERT INTO invite_codes(code, status, note, created_at, expires_at) "
                "VALUES (?, 'unused', '', ?, NULL)",
                (code, server.now_iso()),
            )

    def request(self, path: str, token: str | None = None, payload: dict | None = None):
        body = None
        headers = {}
        if token:
            headers["Cookie"] = f"{server.SESSION_COOKIE}={token}"
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            f"http://127.0.0.1:{self.httpd.server_address[1]}{path}",
            data=body,
            headers=headers,
            method="POST" if payload is not None else "GET",
        )
        try:
            with urlopen(request, timeout=5) as response:
                raw = response.read()
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    parsed = raw
                return response.status, parsed, response.headers
        except HTTPError as exc:
            raw = exc.read()
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed = raw
            return exc.code, parsed, exc.headers

    @staticmethod
    def cookie_token(headers) -> str:
        cookie = headers.get("Set-Cookie", "")
        return cookie.split(";", 1)[0].split("=", 1)[1]

    def test_register_rejects_case_collision_atomically_and_keeps_normal_users_working(self):
        self.add_invite("CODE-ALICE")
        status, body, headers = self.request(
            "/api/register",
            payload={"username": "Alice", "password": "alice-pass-1", "code": "CODE-ALICE"},
        )
        self.assertEqual(status, 201)
        alice_token = self.cookie_token(headers)
        self.assertEqual(body["username"], "Alice")

        self.add_invite("CODE-ALICE-2")
        status, body, _headers = self.request(
            "/api/register",
            payload={"username": "alice", "password": "alice-pass-2", "code": "CODE-ALICE-2"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "用户名已被占用"})
        self.assertNotIn("Alice", json.dumps(body, ensure_ascii=False))

        with server.closing(server.connect_auth()) as connection:
            users = connection.execute("SELECT username FROM users ORDER BY id").fetchall()
            invite = connection.execute(
                "SELECT status FROM invite_codes WHERE code = 'CODE-ALICE-2'"
            ).fetchone()
        self.assertEqual([row["username"] for row in users], ["Alice"])
        self.assertEqual(invite["status"], "unused")
        self.assertTrue(server.user_db_path("Alice").exists())

        self.add_invite("CODE-BOB")
        status, bob_body, bob_headers = self.request(
            "/api/register",
            payload={"username": "Bob", "password": "bob-pass-1", "code": "CODE-BOB"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(bob_body["username"], "Bob")
        bob_token = self.cookie_token(bob_headers)
        status, me, _headers = self.request("/api/me", token=bob_token)
        self.assertEqual(status, 200)
        self.assertEqual(me["username"], "Bob")
        self.assertNotEqual(alice_token, bob_token)
        self.assertFalse(self.default_db.exists())

    def test_legacy_case_conflict_fails_closed_for_login_and_session_but_not_bob(self):
        alice = server.create_user("Alice", "alice-pass-1")
        alice_token = server.create_session(int(alice["id"]))
        with server.closing(server.connect_auth()) as connection:
            # Deliberately reproduce the historical case-sensitive UNIQUE
            # behavior; current create_user/register must never create this.
            connection.execute(
                "INSERT INTO users(username, password_hash, role, is_active, created_at) "
                "VALUES (?, ?, 'user', 1, ?)",
                ("alice", server.hash_password("alice-pass-2"), server.now_iso()),
            )

        with self.assertRaisesRegex(ValueError, "用户名或密码错误"):
            server.auth_login("Alice", "alice-pass-1")
        with self.assertRaisesRegex(ValueError, "用户名或密码错误"):
            server.auth_login("alice", "alice-pass-2")
        self.assertIsNone(server.session_user(alice_token))

        status, body, _headers = self.request("/api/login", payload={
            "username": "Alice",
            "password": "alice-pass-1",
        })
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "用户名或密码错误"})
        self.assertNotIn("alice", json.dumps(body, ensure_ascii=False).lower())

        status, body, _headers = self.request("/api/coach/analytics", token=alice_token)
        self.assertEqual(status, 401)
        self.assertEqual(body, {"error": "未登录"})

        bob = server.create_user("Bob", "bob-pass-1")
        bob_token = server.create_session(int(bob["id"]))
        status, body, _headers = self.request("/api/coach/analytics", token=bob_token)
        self.assertEqual(status, 200)
        self.assertEqual(body["summary"]["total_submissions"], 0)
        status, body, _headers = self.request("/api/me", token=bob_token)
        self.assertEqual(status, 200)
        self.assertEqual(body["username"], "Bob")
        self.assertFalse(self.default_db.exists())

    def test_admin_can_reset_normal_user_quota_with_audit_but_nobody_can_reset_admin(self):
        admin = server.create_user("RootAdmin", "admin-pass-1", role="admin")
        alice = server.create_user("Alice", "alice-pass-1")
        admin_token = server.create_session(int(admin["id"]))
        alice_token = server.create_session(int(alice["id"]))
        alice_db = server.user_db_path("Alice")
        with server.closing(server.connect(alice_db)):
            pass
        with server.closing(ai_coach._open_ai_db(alice_db)) as connection:
            day_key, _ = ai_coach._quota_window()
            connection.execute(
                "INSERT OR REPLACE INTO ai_daily_quota(day_key, used, reserved, updated_at) VALUES (?, 2, 0, ?)",
                (day_key, server.now_iso()),
            )
            connection.commit()

        status, body, _ = self.request(
            "/api/admin/users/ai-quota/reset", token=alice_token, payload={"username": "Alice"}
        )
        self.assertEqual(status, 403)

        status, body, _ = self.request(
            "/api/admin/users/ai-quota/reset", token=admin_token, payload={"username": "Alice"}
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["quota"]["used"], 2)
        self.assertEqual(body["quota"]["remaining"], 3)
        with server.closing(server.connect_auth()) as connection:
            audit = connection.execute(
                "SELECT actor_admin_id, target_user_id, before_used FROM ai_quota_reset_audit"
            ).fetchone()
        self.assertEqual((audit["actor_admin_id"], audit["target_user_id"], audit["before_used"]),
                         (admin["id"], alice["id"], 2))

        status, body, _ = self.request(
            "/api/admin/users/ai-quota/reset", token=admin_token, payload={"username": "RootAdmin"}
        )
        self.assertEqual(status, 400)
        self.assertIn("不能重置管理员", body["error"])

    def test_admin_ai_limit_api_updates_effective_quota_without_resetting_usage(self):
        admin = server.create_user("QuotaAdmin", "admin-pass-1", role="admin")
        alice = server.create_user("QuotaAlice", "alice-pass-1")
        admin_token = server.create_session(int(admin["id"]))
        alice_token = server.create_session(int(alice["id"]))
        alice_db = server.user_db_path("QuotaAlice")
        with server.closing(ai_coach._open_ai_db(alice_db)) as connection:
            day_key, _ = ai_coach._quota_window()
            connection.execute(
                "INSERT OR REPLACE INTO ai_daily_quota(day_key, used, reserved, updated_at) VALUES (?, 2, 0, ?)",
                (day_key, server.now_iso()),
            )
            connection.commit()

        status, _body, _ = self.request(
            "/api/admin/users/ai-quota/limit", token=alice_token,
            payload={"username": "QuotaAlice", "limit": 5},
        )
        self.assertEqual(status, 403)
        status, body, _ = self.request(
            "/api/admin/users/ai-quota/limit", token=admin_token,
            payload={"username": "QuotaAlice", "limit": 1},
        )
        self.assertEqual(status, 201)
        self.assertEqual((body["quota"]["used"], body["quota"]["remaining"]), (2, 0))
        status, body, _ = self.request(
            "/api/admin/users/ai-quota/limit", token=admin_token,
            payload={"username": "QuotaAlice", "limit": 5},
        )
        self.assertEqual((body["quota"]["limit"], body["quota"]["remaining"]), (5, 3))
        status, users_body, _ = self.request("/api/admin/users", token=admin_token)
        listed = next(item for item in users_body["items"] if item["username"] == "QuotaAlice")
        self.assertEqual(listed["ai_daily_limit_effective"], 5)
        self.assertTrue(listed["ai_daily_limit_custom"])
        status, reset_body, _ = self.request(
            "/api/admin/users/ai-quota/reset", token=admin_token,
            payload={"username": "QuotaAlice"},
        )
        self.assertEqual((reset_body["quota"]["limit"], reset_body["quota"]["used"]), (5, 2))
        status, body, _ = self.request(
            "/api/admin/users/ai-quota/limit", token=admin_token,
            payload={"username": "QuotaAlice", "limit": None},
        )
        self.assertFalse(body["ai_daily_limit_custom"])
        self.assertEqual((body["quota"]["limit"], body["quota"]["used"]), (3, 2))
        for invalid in (-1, 101, True, "5"):
            status, _body, _ = self.request(
                "/api/admin/users/ai-quota/limit", token=admin_token,
                payload={"username": "QuotaAlice", "limit": invalid},
            )
            self.assertEqual(status, 400)
        status, body, _ = self.request(
            "/api/admin/users/ai-quota/limit", token=admin_token,
            payload={"username": "QuotaAdmin", "limit": 5},
        )
        self.assertEqual(status, 400)
        self.assertIn("管理员账号", body["error"])

    def test_permanent_admin_is_repaired_marked_and_cannot_be_demoted(self):
        server._AUTH_READY = False
        with server.closing(server.connect_auth()) as connection:
            self.assertIsNone(connection.execute(
                "SELECT id FROM users WHERE username = ?", (server.PERMANENT_ADMIN_USERNAME,)
            ).fetchone())
        permanent = server.create_user(server.PERMANENT_ADMIN_USERNAME, "permanent-pass-1", role="user")
        with server.closing(server.connect_auth()) as connection:
            connection.execute("UPDATE users SET role = 'user' WHERE id = ?", (permanent["id"],))
        server._AUTH_READY = False
        with server.closing(server.connect_auth()) as connection:
            role = connection.execute(
                "SELECT role FROM users WHERE id = ?", (permanent["id"],)
            ).fetchone()["role"]
        self.assertEqual(role, "admin")
        items = {item["username"]: item for item in server.list_users()}
        self.assertTrue(items[server.PERMANENT_ADMIN_USERNAME]["permanent_admin"])
        with self.assertRaisesRegex(ValueError, "永久管理员"):
            server.set_user_role(server.PERMANENT_ADMIN_USERNAME, "user", "AnotherAdmin")

        other = server.create_user("OtherRoleUser", "other-pass-1")
        self.assertEqual(server.set_user_role("OtherRoleUser", "admin", server.PERMANENT_ADMIN_USERNAME)["role"], "admin")
        self.assertEqual(server.set_user_role("OtherRoleUser", "user", server.PERMANENT_ADMIN_USERNAME)["role"], "user")

    def test_admin_page_quota_and_permanent_admin_contract(self):
        page = (Path(__file__).parents[1] / "pages" / "admin.html").read_text(encoding="utf-8")
        for marker in (
            "ai_daily_limit_effective", "ai_daily_limit_custom", "每日 AI 分析上限",
            "/api/admin/users/ai-quota/limit", "保存上限", "恢复默认(3次)",
            "永久管理员", "user.permanent_admin", 'roleSelect.disabled = true',
            "/api/admin/users/ai-quota/reset", "重置今日分析次数",
        ):
            self.assertIn(marker, page)


if __name__ == "__main__":
    unittest.main()
