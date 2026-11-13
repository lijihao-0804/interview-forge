from contextlib import closing
import sqlite3
import threading

from interview_forge.ai.chat import recovery


def test_orphan_is_refunded_on_its_original_day_without_a_request_or_status_read(tmp_path, monkeypatch):
    from interview_forge.ai.chat.request_ledger import RequestAttempt
    from interview_forge.core.runtime import server_runtime

    monkeypatch.setenv("IF_RUNTIME_DIR", str(tmp_path / "locks"))
    path = tmp_path / "learner" / "hot100-study.db"
    path.parent.mkdir()
    with closing(server_runtime.connect(path)) as conn:
        conn.execute("INSERT INTO chat_sessions VALUES ('s1','聊天','2026-01-01','2026-01-01')")
        conn.commit()
    attempt = RequestAttempt.new("s1", "client-key")
    attempt.reserve(path, "test-fingerprint", "user")
    with closing(sqlite3.connect(path)) as conn:
        # The failed worker charged yesterday, while another request charged today.
        conn.execute("UPDATE ai_chat_daily_quota SET day_key='1999-01-01'")
        conn.execute("INSERT INTO ai_chat_daily_quota VALUES ('1999-01-02',1,'1999-01-02')")
        conn.execute("UPDATE chat_request_ledger SET quota_day='1999-01-01'")
        conn.commit()

    def state():
        with closing(sqlite3.connect(path)) as conn:
            return (conn.execute("SELECT status, quota_state FROM chat_request_ledger").fetchone(),
                    conn.execute("SELECT used FROM ai_chat_daily_quota ORDER BY day_key").fetchall())

    assert recovery.reconcile_accounts(tmp_path)["refunded"] == 1
    assert state() == (("reserved", "charged"), [(1,), (1,)])
    assert recovery.reconcile_accounts(tmp_path, dry_run=False)["refunded"] == 1
    assert state() == (("retryable", "refunded"), [(0,), (1,)])
    assert recovery.reconcile_accounts(tmp_path, dry_run=False)["sessions"] == 0


def test_sweep_discovers_only_open_requests_without_migrating_legacy_accounts(tmp_path, monkeypatch):
    def account(name):
        path = tmp_path / name / "hot100-study.db"
        path.parent.mkdir()
        return path

    old = account("legacy")
    with closing(sqlite3.connect(old)) as conn:
        conn.execute("CREATE TABLE existing (id INTEGER PRIMARY KEY)")
    current = account("learner")
    with closing(sqlite3.connect(current)) as conn:
        conn.execute("CREATE TABLE chat_request_ledger (session_id TEXT, status TEXT)")
        conn.executemany("INSERT INTO chat_request_ledger VALUES (?, ?)", [
            ("s1", "reserved"), ("s1", "started"), ("s2", "completed"), ("s3", "started"),
        ])
        conn.commit()
    account("damaged").write_bytes(b"not a SQLite database")
    observed = []

    def reconcile(db, session_id, *, dry_run):
        observed.append((db, session_id, dry_run))
        return {"busy": int(session_id == "s1")}

    monkeypatch.setattr(recovery, "reconcile_session", reconcile)
    result = recovery.reconcile_accounts(tmp_path)
    assert set(observed) == {(current, "s1", True), (current, "s3", True)}
    assert result == {"accounts": 3, "sessions": 2, "failures": 1, "busy": 1}
    with closing(sqlite3.connect(old)) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("existing",)]


def test_shutdown_wakes_elected_worker_and_releases_scan_lock(tmp_path, monkeypatch):
    scanned = threading.Event()
    stop = threading.Event()
    monkeypatch.setenv("IF_RUNTIME_DIR", str(tmp_path / "locks"))

    def scan(users_dir, *, dry_run, stop):
        assert users_dir == tmp_path and not dry_run
        scanned.set()
        return {"sessions": 0, "failures": 0}

    monkeypatch.setattr(recovery, "reconcile_accounts", scan)
    worker = threading.Thread(target=recovery._recovery_worker, args=(tmp_path, stop))
    worker.start()
    try:
        assert scanned.wait(5)
        probe = recovery.FileLock("chat-recovery", str(tmp_path.resolve()))
        assert not probe.acquire()
    finally:
        stop.set()
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert probe.acquire()
    probe.release()
