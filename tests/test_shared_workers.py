"""Real independent-process regression checks for single-host multi-worker mode."""
import json
import multiprocessing
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from interview_forge.runtime import shared


def _hold_lock(directory, pipe):
    os.environ.update(IF_SHARED_RUNTIME="1", IF_RUNTIME_DIR=directory)
    lock = shared.FileLock("test", "owner")
    pipe.send(lock.acquire())
    pipe.recv()
    lock.release()


def _hold_process(directory, pipe):
    os.environ.update(IF_SHARED_RUNTIME="1", IF_RUNTIME_DIR=directory)
    shared.register_process("independent-worker")
    pipe.send(True)
    pipe.recv()


def _hold_model_slot(directory, pipe):
    os.environ.update(IF_SHARED_RUNTIME="1", IF_RUNTIME_DIR=directory)
    from interview_forge.ai.tasks import _release_model_slot, _try_claim_model_slot
    pipe.send(_try_claim_model_slot(1))
    pipe.recv()
    _release_model_slot()


def _sync_worker(directory, pipe):
    os.environ.update(IF_SHARED_RUNTIME="1", IF_RUNTIME_DIR=directory)
    from interview_forge.services import leetcode
    release = threading.Event()

    def fake_sync(*args, progress=None, **kwargs):
        if progress:
            progress("public progress")
        release.wait(10)
        return {"submissions_added": 1}

    with patch.dict(leetcode.server_runtime._values, {"leetcode_sync": fake_sync,
                                                   "_invalidate_learning_caches": lambda _: None}):
        task_id = leetcode.start_leetcode_sync_task({"leetcode_session": "never-persist-this"},
                                                   False, owner="alice", db_path=Path(directory) / "user.db")
        pipe.send(task_id)
        pipe.recv()
        release.set()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = leetcode.sync_task_status(task_id, "alice")
            if not status["running"]:
                pipe.send(status)
                return
            time.sleep(0.02)
        raise RuntimeError("test sync did not complete")


def _write_setting(path):
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("INSERT OR REPLACE INTO settings VALUES ('cross_worker', 'fresh')")
        connection.commit()


def _revoke_session(path):
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("DELETE FROM sessions")
        connection.commit()


def _write_worker_logs(directory, number):
    os.environ.update(IF_SHARED_RUNTIME="1", IF_RUNTIME_DIR=directory,
                      INTERVIEW_FORGE_LOG_PATH=str(Path(directory) / "workers.jsonl"))
    from interview_forge.observability.logging import close_log_handlers, log_event
    for sequence in range(10):
        log_event("worker_log_test", worker_number=number, sequence=sequence)
    close_log_handlers()


class SharedWorkerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"IF_SHARED_RUNTIME": "1", "IF_RUNTIME_DIR": self.directory.name})
        self.env.start()
        self.context = multiprocessing.get_context("spawn")
        self.children = []

    def tearDown(self):
        for process in self.children:
            if process.is_alive():
                process.terminate()
            process.join(5)
        # Test-created process leases intentionally last for a process lifetime.
        for key, lease in list(shared._PROCESS_LOCKS.items()):
            if key[0] == self.directory.name:
                lease.release()
                shared._PROCESS_LOCKS.pop(key)
        self.env.stop()
        self.directory.cleanup()

    def spawn(self, target):
        parent, child = self.context.Pipe()
        process = self.context.Process(target=target, args=(self.directory.name, child))
        process.start()
        self.children.append(process)
        child.close()
        self.assertTrue(parent.poll(15), "child failed to reach ready state")
        return process, parent

    def test_os_lock_excludes_other_process_and_releases_on_death(self):
        process, pipe = self.spawn(_hold_lock)
        self.assertTrue(pipe.recv())
        probe = shared.FileLock("test", "owner")
        self.assertFalse(probe.acquire())
        process.terminate()
        process.join(5)
        self.assertTrue(probe.acquire())
        probe.release()
        pipe.close()

    def test_short_mutex_contention_starts_with_millisecond_backoff(self):
        with patch.object(shared, "FileLock") as lock_class, patch.object(shared.time, "sleep") as sleep:
            lock_class.return_value.acquire.side_effect = [False, False, True]
            with shared.mutex("test", "short-write"):
                pass
            self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.001, 0.0015])
            lock_class.return_value.release.assert_called_once()

    def test_model_call_limit_is_global_across_processes(self):
        from interview_forge.ai.tasks import _release_model_slot, _try_claim_model_slot
        process, pipe = self.spawn(_hold_model_slot)
        self.assertTrue(pipe.recv())
        self.assertFalse(_try_claim_model_slot(1))
        pipe.send("release")
        process.join(5)
        self.assertEqual(process.exitcode, 0)
        self.assertTrue(_try_claim_model_slot(1))
        _release_model_slot()
        pipe.close()

    def test_sync_can_be_queried_and_reused_by_another_process(self):
        from interview_forge.services import leetcode
        process, pipe = self.spawn(_sync_worker)
        task_id = pipe.recv()
        self.assertEqual(leetcode.start_leetcode_sync_task({}, False, owner="alice"), task_id)
        with self.assertRaises(leetcode.LeetCodeSyncError):
            leetcode.start_leetcode_sync_task({}, True, owner="alice")
        self.assertIsNone(leetcode.sync_task_status(task_id, "bob"))
        self.assertTrue(leetcode.sync_task_status(task_id, "alice")["running"])
        self.assertNotIn("never-persist-this", repr(shared.sync_states()))
        pipe.send("finish")
        self.assertTrue(pipe.poll(15))
        self.assertFalse(pipe.recv()["running"])
        process.join(5)
        self.assertEqual(process.exitcode, 0)
        self.assertEqual(leetcode.sync_task_status(task_id, "alice")["result"]["submissions_added"], 1)
        pipe.close()

    def test_dead_sync_worker_is_not_reported_running_forever(self):
        from interview_forge.services import leetcode
        process, pipe = self.spawn(_sync_worker)
        task_id = pipe.recv()
        process.terminate()
        process.join(5)
        status = leetcode.sync_task_status(task_id, "alice")
        self.assertFalse(status["running"])
        self.assertEqual(status["error_category"], "cancelled")
        pipe.close()

    def test_ai_recovery_does_not_cancel_other_live_worker(self):
        from interview_forge.ai.quota import _open_ai_db
        from interview_forge.ai.tasks import recover_ai_tasks
        process, pipe = self.spawn(_hold_process)
        self.assertTrue(pipe.recv())
        db = Path(self.directory.name) / "ai.db"
        with closing(_open_ai_db(db)) as connection:
            connection.execute("INSERT INTO ai_tasks(task_id, task, status, snapshot_hash, prompt_version, "
                               "model_key, created_at, worker_id, context_preview, fallback_json) "
                               "VALUES (?, 'learning_diagnosis', 'queued', 'hash', 'version', 'model', "
                               "'2026-10-02T00:00:00+08:00', ?, '{}', '{}')",
                               ("a" * 32, "independent-worker"))
            connection.commit()
        self.assertEqual(recover_ai_tasks(db), 0)
        process.terminate()
        process.join(5)
        self.assertEqual(recover_ai_tasks(db), 1)
        pipe.close()

    def test_external_writer_invalidates_dashboard_snapshot(self):
        from interview_forge.core.runtime import server_runtime
        from interview_forge.db.connection import connect
        from interview_forge.services.study import (
            _invalidate_dashboard_cache,
            dashboard_cached,
        )
        db = Path(self.directory.name) / "study.db"
        with closing(connect(db)):
            pass
        _invalidate_dashboard_cache(db)
        builder = lambda _: {"signature": shared.db_signature(db)}
        with patch.dict(server_runtime._values, {"dashboard_data": builder}):
            before = dashboard_cached(db)
            process = self.context.Process(target=_write_setting, args=(str(db),))
            process.start()
            self.children.append(process)
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            after = dashboard_cached(db)
        self.assertNotEqual(before, after)

    def test_session_cache_hit_then_external_logout_is_immediately_visible(self):
        from interview_forge.services import auth
        db = Path(self.directory.name) / "auth.db"
        values = {"AUTH_DB_PATH": db, "_AUTH_READY": False, "_AUTH_LOCK": threading.Lock(),
                  "_maybe_purge_sessions": lambda: None}
        with patch.dict(auth.server_runtime._values, values):
            with closing(auth.connect_auth()) as connection:
                connection.execute("INSERT INTO users(id, username, password_hash, created_at) "
                                   "VALUES (1, 'cache-user', 'unused', '2026-10-02T00:00:00+08:00')")
            token = auth.create_session(1)
            self.assertIsNotNone(auth.session_user(token))
            self.assertIsNotNone(auth.session_user(token))
            with patch.object(auth, "connect_auth", wraps=auth.connect_auth) as connect_mock:
                self.assertIsNotNone(auth.session_user(token))
                self.assertEqual(connect_mock.call_count, 0)
            process = self.context.Process(target=_revoke_session, args=(str(db),))
            process.start()
            self.children.append(process)
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            self.assertIsNone(auth.session_user(token))

    def test_bootstrap_microcache_is_invalidated_by_learning_write(self):
        from starlette.requests import Request

        from interview_forge.api.routers import study
        from interview_forge.db.connection import connect
        db = Path(self.directory.name) / "bootstrap.db"
        with closing(connect(db)):
            pass
        request = Request({"type": "http", "method": "GET", "path": "/api/bootstrap", "headers": []})
        user = {"username": "microcache", "role": "admin", "id": 7}
        with patch.object(study, "_user", return_value=(user, None)), \
             patch.object(study, "user_db", return_value=db), \
             patch.object(study, "dashboard_cached", return_value={"count": 0}) as dashboard, \
             patch.object(study, "daily_data", return_value={}), \
             patch.object(study, "get_settings", return_value={}), \
             patch.object(study, "effective_ai_daily_limit", return_value=3), \
             patch.object(study, "ai_capability", return_value={"status": "available"}), \
             patch.object(study, "get_ai_quota", return_value={}):
            self.assertEqual(study.bootstrap(request).status_code, 200)
            self.assertEqual(study.bootstrap(request).status_code, 200)
            self.assertEqual(dashboard.call_count, 1)
            process = self.context.Process(target=_write_setting, args=(str(db),))
            process.start()
            self.children.append(process)
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            self.assertEqual(study.bootstrap(request).status_code, 200)
            self.assertEqual(dashboard.call_count, 2)

    def test_four_workers_share_structured_log_without_losing_records(self):
        for number in range(4):
            process = self.context.Process(target=_write_worker_logs, args=(self.directory.name, number))
            process.start()
            self.children.append(process)
        for process in self.children:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        rows = [json.loads(line) for line in (Path(self.directory.name) / "workers.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 40)
        self.assertEqual(len({(row["worker_number"], row["sequence"]) for row in rows}), 40)

    @unittest.skipUnless(os.name == "posix", "Linux production-runtime integration")
    def test_four_uvicorn_workers_serve_the_real_health_pipeline(self):
        import httpx
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        environment = dict(os.environ, INTERVIEW_FORGE_OBSERVABILITY_DB=str(Path(self.directory.name) / "metrics.db"),
                           INTERVIEW_FORGE_LOG_PATH=str(Path(self.directory.name) / "http.jsonl"),
                           INTERVIEW_FORGE_AI_CONFIG_DB=str(Path(self.directory.name) / "config.db"))
        with (Path(self.directory.name) / "uvicorn.log").open("wb") as output:
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.multiworker_app:app", "--host",
                                       "127.0.0.1", "--port", str(port), "--workers", "4", "--no-access-log"],
                                      cwd=Path(__file__).resolve().parents[1], env=environment,
                                      stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                workers = set()
                deadline = time.monotonic() + 30
                with httpx.Client(timeout=2, trust_env=False, headers={"Connection": "close"}) as client:
                    while time.monotonic() < deadline and len(workers) < 4:
                        self.assertIsNone(server.poll(), "uvicorn exited during startup")
                        try:
                            response = client.get(f"http://127.0.0.1:{port}/api/health")
                            self.assertEqual(response.status_code, 200)
                            workers.add(response.headers["X-Test-Worker"])
                        except httpx.TransportError:
                            time.sleep(0.05)
                self.assertEqual(len(workers), 4)
            finally:
                os.killpg(server.pid, signal.SIGTERM)
                try:
                    server.wait(10)
                except subprocess.TimeoutExpired:
                    os.killpg(server.pid, signal.SIGKILL)
                    server.wait(5)


if __name__ == "__main__":
    unittest.main()
