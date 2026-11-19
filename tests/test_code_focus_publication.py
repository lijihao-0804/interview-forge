from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.api.routers import code_focus as routes
from interview_forge.core.runtime import server_runtime
from interview_forge.services.auth import create_session, create_user
from interview_forge.services.code_focus import PublicationConflict, publish, read_publication


PUBLIC = "/api/code-focus/publication"
ADMIN = "/api/admin/code-focus/publication"
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
