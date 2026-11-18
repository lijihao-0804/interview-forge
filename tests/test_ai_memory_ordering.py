from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from threading import Barrier

import pytest

from interview_forge.ai.chat.request_ledger import RequestAttempt, payload_hash, read_request
from interview_forge.ai.chat.service import ChatService
from interview_forge.ai.memory.extractor import _deterministic_candidate
from interview_forge.ai.memory.store import MemorySourceSuperseded, MemoryStore
from interview_forge.core.runtime import server_runtime


def test_reordered_memory_and_forget(tmp_path):
    db = tmp_path / "user.db"
    store = MemoryStore()
    original = _deterministic_candidate("记住我喜欢 Python")
    inferred = replace(original, explicit=False)
    forget = replace(original, operation="forget")

    def save(candidate, message_id):
        return store.save_candidate(user_db=db, candidate=candidate,
                                    source_session_id="s", source_message_id=message_id)

    newest = save(original, 20)
    assert save(inferred, 10) is None
    with pytest.raises(MemorySourceSuperseded):
        save(forget, 12)
    assert [item.id for item in store.list_active(user_db=db)] == [newest.id]
    save(forget, 21)
    assert save(inferred, 20) is None
    assert store.list_active(user_db=db) == []
    with closing(server_runtime.connect(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM user_memories").fetchone()[0] == 0
        digest, sequence = conn.execute("SELECT * FROM memory_forget_watermarks").fetchone()
        assert len(digest) == 32 and sequence == 21
    assert save(original, 22).source_message_id == 22


def test_ui_delete_blocks_dispatched_extraction_after_session_deletion(tmp_path):
    db = tmp_path / "user.db"
    store = MemoryStore()
    candidate = _deterministic_candidate("记住我喜欢 Python")
    with closing(server_runtime.connect(db)) as conn:
        conn.execute("INSERT INTO chat_sessions VALUES ('s','s','now','now')")
        conn.executemany("INSERT INTO chat_messages(session_id,role,content,created_at) VALUES ('s','user',?,'now')",
                         [("first",), ("later",)])
        conn.execute("DELETE FROM chat_sessions WHERE id='s'")
        conn.commit()

    def save(message_id):
        return store.save_candidate(user_db=db, candidate=replace(candidate, explicit=False),
                                    source_session_id="s", source_message_id=message_id)

    first = save(1)
    assert store.delete(user_db=db, memory_id=first.id)
    assert not store.delete(user_db=db, memory_id=first.id)
    assert save(2) is None
    assert save(3).source_message_id == 3


def test_forget_precedes_first_extraction_and_preexisting_unsequenced_row(tmp_path):
    db = tmp_path / "user.db"
    store = MemoryStore()
    original = _deterministic_candidate("记住我喜欢 Python")

    def save(candidate, sequence):
        return store.save_candidate(user_db=db, candidate=candidate, source_session_id="s",
                                    source_message_id=sequence)

    save(replace(original, operation="forget"), 5)
    assert save(replace(original, explicit=False), 2) is None
    assert store.list_active(user_db=db) == []
    legacy = save(original, 6)
    with closing(server_runtime.connect(db)) as conn:
        conn.execute("DELETE FROM memory_forget_watermarks")
        conn.execute("UPDATE user_memories SET source_message_id=NULL WHERE id=?", (legacy.id,))
        conn.commit()
    assert save(original, 8).source_message_id == 8
    assert len(store.list_active(user_db=db)) == 1


def test_concurrent_extractors_keep_latest_message(tmp_path):
    db = tmp_path / "user.db"
    store = MemoryStore()
    candidate = replace(_deterministic_candidate("记住我喜欢 Python"), explicit=False)
    store.list_active(user_db=db)
    barrier = Barrier(4)

    def save(message_id):
        barrier.wait(timeout=10)
        store.save_candidate(user_db=db, candidate=candidate, source_session_id=str(message_id),
                             source_message_id=message_id)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(save, [1, 4, 2, 3]))
    assert [item.source_message_id for item in store.list_active(user_db=db)] == [4]


@pytest.mark.parametrize("newer_second_key", [False, True])
def test_explicit_multifact_receipt_matches_atomic_memory_and_ledger(tmp_path, monkeypatch, newer_second_key):
    db = tmp_path / "user.db"
    store = MemoryStore()
    service = ChatService()
    session = service.create_session(user_db=db)["id"]
    message = "记住我喜欢 Python，也喜欢先讲思路"
    attempt = RequestAttempt.new(session, "two-facts")
    attempt.reserve(db, payload_hash(message, None), "user")
    first_source = service._save_user_message(user_db=db, session_id=session, content=message, attempt=attempt)["id"]
    language = _deterministic_candidate("记住我喜欢 Python")
    style = _deterministic_candidate("记住我喜欢先讲思路")
    if newer_second_key:
        newer_source = service._save_user_message(user_db=db, session_id=session, content="记住我喜欢先讲直觉")["id"]
        newest = store.save_candidate(user_db=db, candidate=replace(style, display_text="我喜欢先讲直觉"),
                                      source_session_id=session, source_message_id=newer_source)
    monkeypatch.setattr(service, "_extract_memory", lambda *_args, **_kwargs: [language, style])

    receipt = service._persist_explicit_memory(
        user_db=db, session_id=session, message_id=first_source, message=message, attempt=attempt,
    )
    active = store.list_active(user_db=db)
    effect = read_request(db, session, "two-facts")["has_memory_effect"]
    if newer_second_key:
        assert not receipt.success and receipt.error_code == "source_superseded"
        assert "已有更新" in service._explicit_failure_message(receipt)
        assert [item.id for item in active] == [newest.id]
        assert effect == 0
    else:
        assert receipt.success and receipt.count == 2 and receipt.operation == "upsert"
        assert {(item.canonical_key, item.display_text) for item in active} == {
            (language.canonical_key, language.display_text), (style.canonical_key, style.display_text),
        }
        assert all(item.source_message_id == first_source and item.source_session_id == session
                   and item.source_type == "explicit" for item in active)
        assert effect == 1
