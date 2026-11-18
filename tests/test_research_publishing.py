"""Public research navigation, downloads and cache boundaries."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.api.routers.static import _inject_html


@pytest.fixture
def client():
    with patch("interview_forge.api.routers.static.current_user", return_value=None):
        instance = TestClient(app, raise_server_exceptions=False)
        yield instance
        instance.close()


def test_market_directory_and_cache_revalidation(client):
    response = client.get("/research/market?city=北京", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].endswith("/?city=%E5%8C%97%E4%BA%AC")
    page = client.get("/research/market/")
    assert page.status_code == 200
    assert "AI 应用与电子信息就业研究" in page.text
    assert "no-cache" in page.headers["cache-control"]
    assert client.get("/research/market/", headers={"If-None-Match": page.headers["etag"]}).status_code == 304
    assert client.get("/research/market/", headers={"If-None-Match": '"old-release"'}).status_code == 200


@pytest.mark.parametrize(("alias", "destination"), [
    ("jobs", "ai-employment-research"), ("communications", "communications-research"),
])
def test_historical_aliases_keep_filters(client, alias, destination):
    response = client.get(f"/research/{alias}/?city=test", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == f"/library/{destination}/index.html?city=test"
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert "/research/market/report.html" in page.text
    assert "data-research-upgrade" in page.text


@pytest.mark.parametrize(("path", "mime"), [
    ("app.mjs", "text/javascript"), ("data/catalog.json", "application/json"),
    ("data/corpus.ndjson.gz", "application/gzip"), ("data/jobs.sqlite.zip", "application/zip"),
])
def test_public_dataset_media_and_no_stale_cache(client, path, mime):
    response = client.head("/research/market/" + path)
    assert response.status_code == 200
    assert mime in response.headers["content-type"]
    assert response.headers["cache-control"] == "no-store"
    assert "content-encoding" not in response.headers


@pytest.mark.parametrize("path", [
    "/research/market/data/jobs.sqlite", "/research/market/.env",
    "/research/market/collector.py", "/research/private/index.html",
    "/research/market/%2e%2e/%2e%2e/data/auth.db",
])
def test_public_research_does_not_open_other_workspace_files(client, path):
    assert client.get(path).status_code == 404


def test_sqlite_link_is_updated_without_rewriting_the_frozen_page():
    original = b'<body><a href="data/jobs.sqlite">SQLite</a></body>'
    delivered = _inject_html("/research/market/maintenance.html", original)
    assert b'data/jobs.sqlite.zip' in delivered
    assert b'/research/jobs/' in delivered and b'/research/communications/' in delivered
    assert b'data/jobs.sqlite.zip' not in original
