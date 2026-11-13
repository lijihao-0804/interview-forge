"""Guest browsing and private-boundary regression tests."""
from __future__ import annotations

import os
import re
import threading
import unittest
from email.message import Message
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.core.client_ip import client_ip
from interview_forge.core.web_access import is_sensitive_path, target_relative_path
from interview_forge.server import study_server


class GuestAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self) -> None:
        self.client.close()

    def test_guest_can_browse_learning_content_but_me_never_redirects(self) -> None:
        for path in ("/cockpit.html", "/index.html", "/library/index.html"):
            with self.subTest(path=path):
                response = self.client.get(path, follow_redirects=False)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.headers["content-type"])
        me = self.client.get("/api/me", follow_redirects=False)
        self.assertEqual(me.status_code, 401)
        self.assertNotIn("location", me.headers)

    def test_public_search_is_read_only_and_chat_remains_private(self) -> None:
        with patch("interview_forge.api.routers.community.current_user", return_value=None), \
             patch("interview_forge.api.routers.community.public_search_rate_limit") as limited, \
             patch(
                 "interview_forge.api.routers.community.search_index_server_with_count",
                 return_value=([{"id": "1", "title": "公开命中"}], 1),
             ):
            search = self.client.get("/api/search?q=公开")
            chat = self.client.get("/api/chat/messages", follow_redirects=False)
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()["count"], 1)
        limited.assert_called_once()
        self.assertEqual(chat.status_code, 401)
        self.assertNotIn("location", chat.headers)

    def test_catalog_has_all_problem_metadata_and_no_account_fields(self) -> None:
        response = self.client.get("/api/catalog")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["problems"]), 100)
        self.assertTrue(all({"id", "title", "category", "difficulty", "url"} <= item.keys()
                            for item in payload["problems"]))
        serialized = str(payload).lower()
        for forbidden in ("password_hash", "leetcode_session", "csrftoken", "email", "last_login"):
            self.assertNotIn(forbidden, serialized)

    def test_admin_aliases_never_redirect_to_login_or_render(self) -> None:
        paths = (
            "/pages/admin.html", "/PAGES/ADMIN.HTML", "/pages/%61dmin.html",
            "/pages/%2e/admin.html", "/pages//admin.html", "/pages/%252e/admin.html",
            "/pages/tools.html", "/PAGES/TOOLS.HTML",
        )
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path, follow_redirects=False)
                self.assertIn(response.status_code, {403, 404})
                self.assertNotIn("location", response.headers)

    def test_forwarded_headers_are_ignored_unless_proxy_is_configured(self) -> None:
        headers = Message()
        headers["X-Forwarded-For"] = "198.51.100.9, 203.0.113.9"
        headers["X-Real-IP"] = "192.0.2.9"
        with patch.dict(os.environ, {"INTERVIEW_FORGE_TRUSTED_PROXIES": ""}, clear=False):
            self.assertEqual(client_ip("198.51.100.7", headers), "198.51.100.7")
        with patch.dict(os.environ, {"INTERVIEW_FORGE_TRUSTED_PROXIES": "127.0.0.1"}, clear=False):
            self.assertEqual(client_ip("127.0.0.1", headers), "192.0.2.9")

    def test_public_trees_still_reject_dotfiles_and_sensitive_extensions(self) -> None:
        for path in (
            "/books/demo.db", "/books/records.SQLITE", "/assets/site.key",
            "/assets/cert.pem", "/books/.env", "/assets/.private/token.js",
            "/library/backup.bak", "/books/generated.py",
        ):
            with self.subTest(path=path):
                self.assertTrue(is_sensitive_path(path))
        self.assertFalse(is_sensitive_path("/books/hot100/03-题解/0001-两数之和.html"))

    def test_nginx_asset_alias_has_the_same_sensitive_extension_boundary(self) -> None:
        config = (Path(__file__).resolve().parents[1] / "deploy" / "hot100-nginx.conf").read_text(
            encoding="utf-8"
        )
        self.assertIn("location /assets/ {", config)
        self.assertNotIn("location ^~ /assets/", config)
        deny_line = next(
            line for line in config.splitlines() if "location ~* \\." in line and "db-wal" in line
        )
        for extension in (
            "db", "db-wal", "db-shm", "sqlite", "sqlite3", "key", "pem", "p12",
            "pfx", "bak", "backup", "dump", "sql", "py", "pyc", "log", "env",
        ):
            with self.subTest(extension=extension):
                self.assertIn(extension, deny_line)
        self.assertIn("(?:/|$)", deny_line)
        pattern = deny_line.split("location ~* ", 1)[1].rsplit(" {", 1)[0]
        deny = re.compile(pattern, re.IGNORECASE)
        for path in ("/assets/site.DB", "/assets/record.db-wal", "/assets/private.env/app.js"):
            with self.subTest(path=path):
                self.assertIsNotNone(deny.search(path))
        self.assertIsNone(deny.search("/assets/site.js?v=20261112"))

    def test_target_containment_rejects_same_prefix_sibling(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "site"
            sibling = Path(directory) / "site-evil"
            root.mkdir()
            sibling.mkdir()
            self.assertIsNone(target_relative_path(root, "/../site-evil/secret.html"))

    def test_legacy_handler_public_pages_and_anonymous_me_contract(self) -> None:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), study_server.StudyHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
        try:
            with patch.object(study_server.StudyHandler, "current_user", return_value=None):
                connection.request("GET", "/cockpit.html", headers={"Host": "127.0.0.1"})
                page = connection.getresponse()
                self.assertEqual(page.status, 200)
                page.read()

                connection.request("GET", "/api/me", headers={"Host": "127.0.0.1"})
                me = connection.getresponse()
                self.assertEqual(me.status, 401)
                self.assertIsNone(me.getheader("Location"))
                me.read()

                connection.request("GET", "/PAGES/%61DMIN.HTML", headers={"Host": "127.0.0.1"})
                admin = connection.getresponse()
                self.assertIn(admin.status, (403, 404))
                self.assertIsNone(admin.getheader("Location"))
                admin.read()
        finally:
            connection.close()
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
