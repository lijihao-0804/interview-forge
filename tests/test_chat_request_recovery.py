"""Crash boundaries of the session lease, SQLite receipts and late worker writes."""
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from interview_forge.ai.actions.store import ActionRequestStore
from interview_forge.ai.chat.request_ledger import (
    RequestAttempt, claim_chat_session, payload_hash, public_status, read_request, reconcile_session,
    release_chat_session, replay,
)
from interview_forge.ai.chat.service import ChatService
from interview_forge.ai.memory import MemoryStore
from interview_forge.ai.memory.extractor import _deterministic_candidate
from interview_forge.core.runtime import server_runtime


def _abrupt_worker(db, phase):
    # A process exit releases the kernel lease but executes no Python cleanup.
    assert claim_chat_session(db, "s")
    attempt = RequestAttempt.new("s", "same-key")
    attempt.reserve(db, payload_hash("q", None), "user")
    if phase != "reserved":
        user = ChatService._save_user_message(user_db=db, session_id="s", content="q", attempt=attempt)
        if phase == "completed":
            ChatService._save_assistant_message(user_db=db, session_id="s", content="answer", usage={},
                                                stream_message_id=attempt.turn_id, attempt=attempt)
        if phase == "memory":
            candidate = _deterministic_candidate("记住我以后解释算法先讲思路")
            MemoryStore().save_candidate(user_db=db, source_session_id="s", source_message_id=user["id"],
                                         candidate=candidate, attempt=attempt)
    os._exit(73)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("IF_RUNTIME_DIR", str(tmp_path / "leases"))
    monkeypatch.setenv("IF_SHARED_RUNTIME", "0")
    path = tmp_path / "owner.db"
    with closing(server_runtime.connect(path)) as conn:
        conn.execute("INSERT INTO chat_sessions VALUES('s','新会话','now','now')")
        conn.commit()
    return path


@pytest.mark.parametrize("phase", ["reserved", "started", "completed", "memory"])
def test_real_worker_death_at_committed_boundaries(db, phase):
    worker = subprocess.run([sys.executable, "-c",
        "import sys; from pathlib import Path; from runpy import run_path; "
        "run_path(sys.argv[1])['_abrupt_worker'](Path(sys.argv[2]), sys.argv[3])",
        str(Path(__file__).resolve()), str(db), phase], capture_output=True, text=True, timeout=45)
    assert worker.returncode == 73, worker.stderr
    original = read_request(db, "s", "same-key")
    preview = reconcile_session(db, "s", dry_run=True)
    assert read_request(db, "s", "same-key")["status"] == original["status"]
    assert preview == reconcile_session(db, "s")
    assert not any(reconcile_session(db, "s").values())
    row = read_request(db, "s", "same-key")
    counts = lambda conn: conn.execute("SELECT SUM(used) FROM ai_chat_daily_quota").fetchone()[0]
    with closing(server_runtime.connect(db)) as conn:
        if phase == "completed":
            assert public_status(row) == {"status": "completed", "message_id": original["turn_id"]}
            assert replay(db, row)[1] == {"event": "message.delta", "data": {"delta": "answer"}}
            assert counts(conn) == 1
        elif phase == "memory":
            assert row["status"] == "interrupted" and row["has_memory_effect"] == 1
            assert conn.execute("SELECT source_message_id FROM user_memories").fetchone()[0] == row["user_message_id"]
            assert counts(conn) == 1
        else:
            assert row["status"] == "retryable" and row["quota_state"] == "refunded"
            assert conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == counts(conn) == 0
            assert conn.execute("SELECT title, updated_at FROM chat_sessions").fetchone()[:] == ("新会话", "now")
            assert claim_chat_session(db, "s")
            try:
                new = RequestAttempt.new("s", "same-key")
                new.reserve(db, payload_hash("q", None), "user")
                ChatService._save_user_message(user_db=db, session_id="s", content="q", attempt=new)
                ChatService._save_assistant_message(user_db=db, session_id="s", content="ok", usage={},
                                                    stream_message_id=new.turn_id, attempt=new)
                assert counts(conn) == 1
                assert read_request(db, "s", "same-key")["attempt_count"] == 2
                assert conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 2
            finally:
                release_chat_session(db, "s")


def test_late_old_worker_cannot_commit_memory_action_user_or_assistant_under_new_attempt(db):
    first = RequestAttempt.new("s", "k")
    first.reserve(db, payload_hash("q", None), "user")
    user = ChatService._save_user_message(user_db=db, session_id="s", content="q", attempt=first)
    assert reconcile_session(db, "s")["refunded"] == 1
    second = RequestAttempt.new("s", "k")
    second.reserve(db, payload_hash("q", None), "user")
    candidate = _deterministic_candidate("记住我以后解释算法先讲思路")
    for late in (
        lambda: MemoryStore().save_candidate(user_db=db, source_session_id="s", source_message_id=user["id"],
                                             candidate=candidate, attempt=first),
        lambda: ActionRequestStore().create(user_db=db, session_id="s", turn_id=first.turn_id,
            user_message_id=user["id"], tool_name="sync_leetcode", arguments={}, confirmation_text="确认", attempt=first),
        lambda: ChatService._save_user_message(user_db=db, session_id="s", content="late", attempt=first),
        lambda: ChatService._save_assistant_message(user_db=db, session_id="s", content="late",
                                                    stream_message_id=first.turn_id, usage={}, attempt=first),
    ):
        with pytest.raises(RuntimeError, match="stale"):
            late()
    with closing(server_runtime.connect(db)) as conn:
        for table in ("chat_messages", "user_memories", "chat_action_requests"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert conn.execute("SELECT SUM(used) FROM ai_chat_daily_quota").fetchone()[0] == 1
    assert read_request(db, "s", "k")["turn_id"] == second.turn_id


def test_same_transaction_rolls_back_quota_and_reply_on_receipt_failure(db):
    attempt = RequestAttempt.new("s", "key")
    with closing(server_runtime.connect(db)) as conn:
        conn.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON chat_request_ledger "
                     "BEGIN SELECT RAISE(ABORT, 'test reservation'); END")
        with pytest.raises(sqlite3.IntegrityError, match="test reservation"):
            attempt.reserve(db, payload_hash("q", None), "user")
        assert conn.execute("SELECT COUNT(*) FROM ai_chat_daily_quota").fetchone()[0] == 0
        conn.execute("DROP TRIGGER fail_insert")
        attempt.reserve(db, payload_hash("q", None), "user")
        ChatService._save_user_message(user_db=db, session_id="s", content="q", attempt=attempt)
        conn.execute("CREATE TRIGGER fail_completion BEFORE UPDATE ON chat_request_ledger WHEN NEW.status='completed' "
                     "BEGIN SELECT RAISE(ABORT, 'test completion'); END")
        with pytest.raises(sqlite3.IntegrityError, match="test completion"):
            ChatService._save_assistant_message(user_db=db, session_id="s", content="answer",
                                                stream_message_id=attempt.turn_id, usage={}, attempt=attempt)
        assert conn.execute("SELECT role FROM chat_messages").fetchall()[0][0] == "user"
        assert conn.execute("SELECT COUNT(*) FROM chat_messages WHERE role='assistant'").fetchone()[0] == 0
        assert read_request(db, "s", "key")["status"] == "started"


@pytest.mark.parametrize("existing", [True, False])
def test_forget_only_records_an_effect_when_it_deletes_a_memory(db, existing):
    store = MemoryStore()
    if existing:
        store.save_candidate(user_db=db, source_session_id="s", source_message_id=6,
                             candidate=_deterministic_candidate("记住我喜欢 Python"))
    turn = RequestAttempt.new("s", "forget")
    turn.reserve(db, payload_hash("forget", None), "user")
    source = ChatService._save_user_message(user_db=db, session_id="s", content="forget", attempt=turn)
    store.save_candidate(user_db=db, source_session_id="s", source_message_id=source["id"],
                         candidate=_deterministic_candidate("不要再记住我喜欢 Python"), attempt=turn)
    reconcile_session(db, "s")
    result = read_request(db, "s", "forget")
    assert result["status"] == ("interrupted" if existing else "retryable")
    assert result["quota_state"] == ("charged" if existing else "refunded")
    assert not store.list_active(user_db=db)
