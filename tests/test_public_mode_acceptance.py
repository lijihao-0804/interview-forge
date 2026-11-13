"""Cross-domain acceptance gates for anonymous browsing and private APIs."""
from __future__ import annotations

import re
from unittest.mock import patch

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.core.paths import ROOT

# Every newly introduced API is private unless deliberately reviewed here.
PUBLIC_OPERATIONS = {
    ("GET", "/api/health"),
    ("GET", "/api/catalog"),
    ("GET", "/api/search"),
    ("POST", "/api/login"),
    ("POST", "/api/register"),
    ("POST", "/api/register/send-code"),
}

PRIVATE_OPERATIONS = sorted({
    (method, route.path)
    for route in app.routes
    if isinstance(route, APIRoute) and route.path.startswith("/api/")
    for method in route.methods
    if (method, route.path) not in PUBLIC_OPERATIONS
})


@pytest.fixture
def client():
    with patch("interview_forge.api.support.current_user", return_value=None), \
         patch("interview_forge.api.routers.auth.current_user", return_value=None), \
         patch("interview_forge.api.routers.static.current_user", return_value=None):
        instance = TestClient(app, raise_server_exceptions=False)
        yield instance
        instance.close()


@pytest.mark.parametrize(("method", "route"), PRIVATE_OPERATIONS)
def test_each_private_api_rejects_a_direct_anonymous_request(client, method, route):
    path = re.sub(r"\{[^}]+\}", "1", route)
    kwargs = {} if method in {"GET", "HEAD"} else {"json": {}}
    response = client.request(method, path, follow_redirects=False, **kwargs)
    assert response.status_code == 401, (method, route, response.status_code, response.text[:160])
    assert "location" not in response.headers


@pytest.mark.parametrize("path", [
    "/cockpit.html", "/index.html", "/library/index.html",
    "/library/search.html", "/pages/login.html", "/pages/register.html",
])
def test_guest_entry_pages_are_readable_without_redirect(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_hot100_pages_are_readable_without_recording_progress(client):
    pages = sorted((ROOT / "books/hot100/03-题解").rglob("*.html"))
    assert len(pages) == 100
    with patch("interview_forge.api.routers.static._record_view") as record:
        for path in (pages[0], pages[49], pages[-1]):
            response = client.get("/" + path.relative_to(ROOT).as_posix())
            assert response.status_code == 200
        record.assert_not_called()


@pytest.mark.parametrize("path", [
    "/data/auth.db", "/data/users/alice/hot100-study.db", "/.env",
    "/interview_forge/services/auth.py", "/deploy/hot100-nginx.conf",
    "/tools/lang_solutions.json", "/logs/access.jsonl",
])
def test_guest_cannot_download_private_workspace_files(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 404


@pytest.mark.parametrize("role", [None, "user"])
@pytest.mark.parametrize("path", [
    "/pages/admin.html", "/PAGES/ADMIN.HTML", "/pages/%61dmin.html",
    "/pages/%2e/admin.html", "/pages//admin.html", "/pages/tools.html",
    "/PAGES/TOOLS.HTML", "/pages/%74ools.html",
])
def test_guest_cannot_bypass_admin_page_policy_with_path_variations(client, path, role):
    user = None if role is None else {"role": role, "username": "reader"}
    with patch("interview_forge.api.routers.static.current_user", return_value=user):
        response = client.get(path, follow_redirects=False)
    assert response.status_code in {401, 403, 404}
    assert "location" not in response.headers


def test_catalog_contains_problem_metadata_and_no_personal_state(client):
    response = client.get("/api/catalog")
    assert response.status_code == 200
    payload = response.json()
    def all_keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from all_keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from all_keys(item)

    private_keys = {"password_hash", "leetcode_session", "csrftoken", "email", "last_login",
                    "user_id", "username", "rounds", "last_activity_at", "due_date"}
    assert not private_keys.intersection(all_keys(payload))
    assert payload.get("problems") and len(payload["problems"]) == 100


@pytest.mark.parametrize("path", ["books/.env", "assets/state.db", "books/nested/key.pem"])
def test_existing_secrets_in_public_trees_remain_unreachable(client, tmp_path, path):
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("synthetic-secret-do-not-serve", encoding="utf-8")
    with patch("interview_forge.api.routers.static.ROOT", tmp_path):
        response = client.get("/" + path)
    assert response.status_code == 404
    assert "synthetic-secret" not in response.text

