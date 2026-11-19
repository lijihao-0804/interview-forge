import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import aclosing, closing
from importlib.util import find_spec
import multiprocessing
import socket
import sqlite3
import sys
import time
from threading import Barrier
from unittest.mock import patch

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.api.routers import code_focus as routes
from interview_forge.core.runtime import server_runtime
from interview_forge.services.auth import create_session, create_user
from interview_forge.services import code_focus, code_focus_events
from interview_forge.services.code_focus import PublicationConflict, publish, read_publication


PUBLIC = "/api/code-focus/publication"
ADMIN = "/api/admin/code-focus/publish"
OLD_ADMIN = "/api/admin/code-focus/publication"
EVENTS = PUBLIC + "/events"
EMPTY = {"version": 0, "code": "", "language": "auto", "answers": ""}
EDIT = {"version": 0, "code": "  print('你好')\n", "language": "python", "answers": "a，Ｂ\nc"}


@pytest.fixture
def client(tmp_path):
    with patch.object(server_runtime, "_provider", None), patch.dict(server_runtime._values, {
        "AUTH_DB_PATH": tmp_path / "auth.db", "USERS_DIR": tmp_path / "users", "_AUTH_READY": False,
    }):
        instance = TestClient(app)
        yield instance
        instance.close()


def sign_in(client, role):
    account = create_user("editor_" + role, "test-password", role=role)
    client.cookies.set("forge_session", create_session(account["id"]))


def test_guest_reads_admin_publishes_and_stale_write_fails(client):
    start = client.get(PUBLIC)
    assert start.status_code == 200 and start.json() == EMPTY
    assert client.put(ADMIN, json=EDIT).status_code == 401
    sign_in(client, "user")
    assert client.get(PUBLIC).json() == EMPTY
    assert client.put(ADMIN, json=EDIT).status_code == 403
    sign_in(client, "admin")
    assert client.put(OLD_ADMIN, json=EDIT).status_code in (404, 405)
    assert client.put(ADMIN, json=EDIT, headers={"Origin": "https://cross-site.example"}).status_code == 403
    saved = client.put(ADMIN, json=EDIT)
    assert saved.status_code == 200 and saved.json() == {**EDIT, "version": 1}
    assert client.put(ADMIN, json=EMPTY).status_code == 409

    client.cookies.clear()
    latest = client.get(PUBLIC, headers={"If-None-Match": start.headers["etag"]})
    assert latest.status_code == 200 and latest.json() == saved.json()
    assert latest.headers["etag"] != start.headers["etag"]
    assert latest.headers["etag"] == saved.headers["etag"]
    with patch.object(routes, "read_publication", side_effect=AssertionError("loaded full body")):
        for condition in (latest.headers["etag"], '"old", W/' + latest.headers["etag"], "*"):
            unchanged = client.get(PUBLIC, headers={"If-None-Match": condition})
            assert unchanged.status_code == 304 and unchanged.content == b""
            assert unchanged.headers["etag"] == latest.headers["etag"]
            assert unchanged.headers["cache-control"] == "no-cache"


def test_body_bound_and_field_validation_preserve_the_last_publication(client):
    sign_in(client, "admin")
    long_doc = {**EDIT, "code": "print(123)\n" * 20000}
    assert client.put(ADMIN, json=long_doc).status_code == 200
    oversize = client.put(ADMIN, json={**EMPTY, "code": "x" * routes.MAX_PUBLICATION_BYTES})
    assert oversize.status_code == 413 and "1 MiB" in oversize.json()["error"]
    for changes in ({"version": True}, {"version": -1}, {"language": "unknown"},
                    {"code": None}, {"answers": []}, {"username": "attacker"}):
        assert client.put(ADMIN, json={**EMPTY, "version": 1, **changes}).status_code == 400
    assert client.put(ADMIN, json={"version": 1}).status_code == 400
    assert client.get(PUBLIC).json() == {**long_doc, "version": 1}
    assert client.put(ADMIN, json={**EMPTY, "version": 1}).json() == {**EMPTY, "version": 2}


def test_simultaneous_editors_cannot_publish_against_the_same_version(client):
    assert client.get(PUBLIC).json() == EMPTY
    barrier = Barrier(2)

    def write(code):
        barrier.wait(timeout=10)
        try:
            return publish({**EDIT, "code": code})
        except PublicationConflict:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(write, ("first", "second")))
    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    # A restarted worker initializes its own connection to the same persisted row.
    server_runtime._AUTH_READY = False
    assert read_publication() == winners[0]


def test_notifications_follow_successful_changed_commits_only(client):
    sign_in(client, "admin")
    observed = []
    with patch.object(code_focus, "_signal_publication",
                      side_effect=lambda: observed.append(read_publication())) as notify:
        assert client.put(ADMIN, json=EMPTY).json() == EMPTY
        notify.assert_not_called()
        saved = client.put(ADMIN, json=EDIT).json()
        assert saved == {**EDIT, "version": 1}
        assert observed == [saved]
        notify.assert_called_once_with()
        assert client.put(ADMIN, json=saved).json() == saved
        assert client.put(ADMIN, json=EDIT).status_code == 409
        assert client.put(ADMIN, json={**saved, "language": "invalid"}).status_code == 400
        with closing(code_focus.connect_auth()) as db:
            db.execute("""CREATE TRIGGER fail_publish BEFORE UPDATE ON code_focus_publication
                          BEGIN SELECT RAISE(ABORT, 'failed publication'); END""")
        with pytest.raises(sqlite3.IntegrityError):
            publish({**saved, "answers": "b"})
        assert read_publication() == saved
        notify.assert_called_once_with()


def test_same_worker_wakes_readers_and_releases_the_shared_watcher(client):
    sign_in(client, "admin")

    async def check():
        feed = code_focus_events.PublicationFeed()
        started, stopped = asyncio.Event(), asyncio.Event()

        async def idle_watcher(stop):
            started.set()
            try:
                await asyncio.Future()
            finally:
                assert stop.is_set()
                stopped.set()

        with patch.object(feed, "_watch", side_effect=idle_watcher) as watch, \
             patch.object(app.state, "code_focus_feed", feed, create=True), \
             patch.object(code_focus_events, "publication_version", wraps=code_focus.publication_version) as read:
            async with aclosing(feed.frames()) as a, aclosing(feed.frames()) as b:
                assert b"data: 0\n" in await anext(a)
                assert b"data: 0\n" in await anext(b)
                assert started.is_set() and watch.call_count == 1
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                             base_url="http://localhost", cookies=client.cookies) as admin:
                    saved = await admin.put(ADMIN, json=EDIT)
                    assert saved.status_code == 200
                assert b"data: 1\n" in await asyncio.wait_for(anext(a), 1)
                assert b"data: 1\n" in await asyncio.wait_for(anext(b), 1)
                assert read.call_count == 2
                await a.aclose()
                assert feed.readers == 1 and not stopped.is_set()
            await asyncio.wait_for(stopped.wait(), 1)
            assert feed.readers == 0 and feed.watcher is None

    asyncio.run(check())


def _serve_reader(db_path, port_pipe, native_watch):
    server_runtime.bind(AUTH_DB_PATH=db_path, _AUTH_READY=False)
    code_focus_events.HEARTBEAT_INTERVAL_SECONDS = 0.1
    if not native_watch:
        sys.modules["watchfiles"] = None
        code_focus_events.RECONCILE_SECONDS = 0.25
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port_pipe.send(listener.getsockname()[1])
        port_pipe.close()
        config = uvicorn.Config(app, lifespan="off", log_level="error")
        uvicorn.Server(config).run(sockets=[listener])


def _next_event(lines, expected):
    deadline = time.monotonic() + 5
    fields = []
    for line in lines:
        assert time.monotonic() < deadline, "timed out waiting for publication"
        if line.startswith(":"):
            assert not fields
        elif line:
            fields.append(line)
        elif fields:
            assert fields == [f"id: {expected}", "event: publication", f"data: {expected}"]
            return
    pytest.fail("stream ended before publication")


@pytest.mark.parametrize("native_watch", [
    pytest.param(True, marks=pytest.mark.skipif(find_spec("watchfiles") is None,
                                               reason="requires uvicorn[standard]")),
    False,
], ids=["filesystem-notification", "database-reconciliation"])
def test_other_worker_streams_to_guests_and_reconnects_at_latest(client, monkeypatch, tmp_path, native_watch):
    monkeypatch.setenv("IF_RUNTIME_DIR", str(tmp_path / "runtime"))
    sign_in(client, "admin")
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    worker = context.Process(target=_serve_reader, args=(tmp_path / "auth.db", sender, native_watch))
    worker.start()
    sender.close()
    try:
        assert receiver.poll(20), "reader worker did not start"
        base = f"http://127.0.0.1:{receiver.recv()}"
        with httpx.Client(base_url=base, timeout=8, trust_env=False) as guest:
            with guest.stream("GET", EVENTS) as first, guest.stream("GET", EVENTS) as second:
                for response in (first, second):
                    assert response.status_code == 200
                    assert response.headers["content-type"].startswith("text/event-stream")
                    assert response.headers["x-accel-buffering"] == "no"
                a, b = first.iter_lines(), second.iter_lines()
                _next_event(a, 0)
                _next_event(b, 0)
                assert next(a) == ": ping" and next(a) == ""
                assert client.put(ADMIN, json=EDIT).json()["version"] == 1
                _next_event(a, 1)
                _next_event(b, 1)
                assert client.put(ADMIN, json={**EMPTY, "version": 1}).json()["version"] == 2
                _next_event(a, 2)
                _next_event(b, 2)
                if not native_watch:
                    with patch.object(code_focus, "_signal_publication", side_effect=OSError):
                        assert client.put(ADMIN, json={**EDIT, "version": 2}).json()["version"] == 3
                    _next_event(a, 3)
                    _next_event(b, 3)
            # A reader disconnected while a publish was committed and its IPC failed.
            last_seen = 2 if native_watch else 3
            missed = {**EDIT, "code": "after disconnect", "version": last_seen}
            with patch.object(code_focus, "_signal_publication", side_effect=OSError):
                assert client.put(ADMIN, json=missed).json()["version"] == last_seen + 1
            with guest.stream("GET", EVENTS, headers={"Last-Event-ID": "1"}) as reconnected:
                _next_event(reconnected.iter_lines(), last_seen + 1)
            assert guest.get(PUBLIC).json() == {**missed, "version": last_seen + 1}
    finally:
        receiver.close()
        worker.terminate()
        worker.join(10)
