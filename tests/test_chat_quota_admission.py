import asyncio
import json
import threading
from builtins import ExceptionGroup
from contextlib import closing
from datetime import datetime
from types import SimpleNamespace

import pytest

from interview_forge.ai.chat.service import claim_chat_session, release_chat_session
from interview_forge.ai.chat import request_ledger
from interview_forge.ai.quota import AI_QUOTA_TIMEZONE, charge_chat_quota, consume_chat_quota
from interview_forge.api.routers import chat
from interview_forge.core.runtime import server_runtime


@pytest.fixture
def route(tmp_path, monkeypatch):
    db = tmp_path / "owner.db"
    with closing(server_runtime.connect(db)) as conn:
        conn.execute("INSERT INTO chat_sessions VALUES('session','test','2026-01-01','2026-01-01')")
        conn.commit()

    async def user(_request):
        return {"username": "owner", "role": "user"}, None

    async def payload(_request, **_limits):
        return {"message": "这轮继续"}

    async def connected():
        return False

    monkeypatch.setattr(chat, "async_require_user", user)
    monkeypatch.setattr(chat, "read_json", payload)
    monkeypatch.setattr(chat, "user_db", lambda _user: db)
    monkeypatch.setattr(chat.chat_service, "preflight", lambda: None)
    request = SimpleNamespace(state=SimpleNamespace(request_id="test"), is_disconnected=connected)
    return db, request


def counters(db):
    with closing(server_runtime.connect(db)) as conn:
        return dict(conn.execute("SELECT day_key, used FROM ai_chat_daily_quota"))


async def drive_response(response, *, fail_headers=False, fail_first_frame=False):
    async def receive():
        await asyncio.Future()

    async def send(event):
        if fail_headers and event["type"] == "http.response.start":
            raise OSError("client disconnected before the first frame")
        if fail_first_frame and event["type"] == "http.response.body":
            assert event["body"].startswith(b"event: message.start")
            raise OSError("client disconnected on the first frame")

    await response({"type": "http", "method": "POST", "asgi": {"spec_version": "2.3"}}, receive, send)


def test_cancelled_charge_keeps_lease_until_worker_refunds_original_day(route, monkeypatch):
    db, request = route
    before_midnight = datetime(2026, 1, 1, 23, 59, tzinfo=AI_QUOTA_TIMEZONE)
    after_midnight = datetime(2026, 1, 2, 0, 1, tzinfo=AI_QUOTA_TIMEZONE)
    for instant in (before_midnight, after_midnight):
        consume_chat_quota(db, now=instant)
    arrived, resume = threading.Event(), threading.Event()

    def paused_charge(connection, role):
        arrived.set()
        assert resume.wait(3)
        return charge_chat_quota(connection, role, now=before_midnight)

    monkeypatch.setattr(request_ledger, "charge_chat_quota", paused_charge)

    async def exercise():
        task = asyncio.create_task(chat.stream_session(request, "session"))
        assert await asyncio.to_thread(arrived.wait, 3)
        try:
            task.cancel()
            await asyncio.sleep(0)
            assert (await chat.stream_session(request, "session")).status_code == 409
            task.cancel()
            await asyncio.sleep(0)
            assert not claim_chat_session(db, "session")
        finally:
            resume.set()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(exercise())
    assert counters(db) == {"2026-01-01": 1, "2026-01-02": 1}
    assert claim_chat_session(db, "session")
    release_chat_session(db, "session")


def test_disconnect_before_source_starts_refunds_and_allows_retry(route, monkeypatch):
    db, request = route

    async def unstarted(**_args):
        pytest.fail("the source must not run before response headers")
        yield  # pragma: no cover

    monkeypatch.setattr(chat.chat_service, "stream_reply", unstarted)

    async def exercise():
        response = await chat.stream_session(request, "session")
        assert sum(counters(db).values()) == 1
        with pytest.raises((OSError, ExceptionGroup)) as failure:
            await drive_response(response, fail_headers=True)
        assert "client disconnected before the first frame" in repr(failure.value)
        assert sum(counters(db).values()) == 0
        assert claim_chat_session(db, "session")
        release_chat_session(db, "session")

    asyncio.run(exercise())


def test_keyed_active_status_never_settles_live_turn_and_refunds_after_stop(route, monkeypatch):
    db, request = route
    body = {"message": "这轮继续", "client_request_id": "one"}

    async def payload(_request, **_limits):
        return dict(body)

    monkeypatch.setattr(chat, "read_json", payload)
    monkeypatch.setattr(chat, "require_user", lambda _req: ({"username": "owner", "role": "user"}, None))

    async def exercise():
        response = await chat.stream_session(request, "session")
        assert response.status_code == 200
        state = chat.request_status(request, "session", "one")
        assert json.loads(state.body) == {"status": "in_progress", "message_id": None}
        assert json.loads((await chat.stream_session(request, "session")).body)["error_category"] == "chat_in_progress"
        body["message"] = "不相同"
        assert json.loads((await chat.stream_session(request, "session")).body)["error_category"] == "idempotency_conflict"
        assert sum(counters(db).values()) == 1
        with pytest.raises((OSError, ExceptionGroup)):
            await drive_response(response, fail_first_frame=True)
        assert json.loads(chat.request_status(request, "session", "one").body)["status"] == "retryable"
        assert sum(counters(db).values()) == 0
        assert chat.chat_service.list_messages(user_db=db, session_id="session") == []

    asyncio.run(exercise())


def test_prestart_service_error_refunds_but_persisted_turn_counts(route, monkeypatch):
    db, request = route

    async def missing(**_args):
        yield {"event": "error", "data": {"code": "session_not_found"}}

    async def persisted(**args):
        attempt = args["attempt"]
        chat.chat_service._save_user_message(user_db=db, session_id="session", content="这轮继续", attempt=attempt)
        yield {"event": "message.start", "data": {"message_id": attempt.turn_id}}
        done = chat.chat_service._save_assistant_message(user_db=db, session_id="session", content="好",
                                                         stream_message_id=attempt.turn_id, usage={}, attempt=attempt)
        yield {"event": "message.done", "data": done}

    async def exercise():
        monkeypatch.setattr(chat.chat_service, "stream_reply", missing)
        await drive_response(await chat.stream_session(request, "session"))
        assert sum(counters(db).values()) == 0
        monkeypatch.setattr(chat.chat_service, "stream_reply", persisted)
        await drive_response(await chat.stream_session(request, "session"))
        assert sum(counters(db).values()) == 1

    asyncio.run(exercise())


def test_disconnect_on_first_frame_closes_real_service_once(route):
    db, request = route

    async def exercise():
        response = await chat.stream_session(request, "session")
        with pytest.raises((OSError, ExceptionGroup)) as failure:
            await drive_response(response, fail_first_frame=True)
        assert "client disconnected on the first frame" in repr(failure.value)
        assert sum(counters(db).values()) == 1
        # ChatService rolls the interrupted conversation back before releasing the
        # lease. Its already-started request still counts towards the daily limit.
        with closing(server_runtime.connect(db)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 0
        assert claim_chat_session(db, "session")
        release_chat_session(db, "session")

    asyncio.run(exercise())
