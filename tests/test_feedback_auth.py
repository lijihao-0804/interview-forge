"""Feedback is a write operation and requires an authenticated session."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import quote

from fastapi.testclient import TestClient
from starlette.requests import Request

from interview_forge.api.app import app
from interview_forge.api.routers.auth import feedback as feedback_route
from interview_forge.server import study_server
from interview_forge.services import community


def test_feedback_list_resolves_saved_page_titles_and_keeps_original_urls():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE feedback(id INTEGER PRIMARY KEY, page TEXT, status TEXT)")
    problem = quote("/books/hot100/03-题解/13-堆/0215-数组中的第K个最大元素.html")
    pages = [problem + "?lang=python#python", "/library/acm-io/chapter-09.html#96",
             "/cockpit.html", "", "/library/development-history/chapters/origin.html"]
    connection.executemany("INSERT INTO feedback(page,status) VALUES (?, 'open')", [(p,) for p in pages])
    with patch.dict(community.server_runtime._values, {"connect_auth": lambda: connection}):
        rows = community.list_feedback("open")
    labels = {row["page"]: row["page_title"] for row in rows}
    assert labels == dict(zip(pages, ["215. 数组中的第K个最大元素", "第 9 章 · Python 输出与多组数据",
                                      "学习中控台", "", ""]))

USER = {"id": 7, "username": "alice", "nickname": "Alice", "lang": "python", "role": "user"}


class FeedbackAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self) -> None:
        self.client.close()

    def test_anonymous_feedback_is_private_and_uses_no_redirect(self) -> None:
        with patch("interview_forge.api.support.current_user", return_value=None), \
             patch("interview_forge.api.routers.auth.read_json") as read_json, \
             patch("interview_forge.api.routers.auth.feedback_rate_limit_ok") as rate_ok, \
             patch("interview_forge.api.routers.auth.feedback_rate_limit_record") as rate_record, \
             patch("interview_forge.api.routers.auth.submit_feedback") as submit:
            response = self.client.post("/api/feedback", json={"content": "guest"}, follow_redirects=False)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "未登录"})
        self.assertNotIn("location", response.headers)
        read_json.assert_not_called()
        rate_ok.assert_not_called()
        rate_record.assert_not_called()
        submit.assert_not_called()

    def test_route_also_guards_anonymous_requests_without_the_middleware(self) -> None:
        request = Request({
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/feedback",
            "raw_path": b"/api/feedback",
            "query_string": b"",
            "headers": [(b"content-length", b"2")],
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 18987),
            "root_path": "",
        })
        with patch("interview_forge.api.support.current_user", return_value=None), \
             patch("interview_forge.api.routers.auth.read_json") as read_json, \
             patch("interview_forge.api.routers.auth.feedback_rate_limit_ok") as rate_ok, \
             patch("interview_forge.api.routers.auth.feedback_rate_limit_record") as rate_record, \
             patch("interview_forge.api.routers.auth.submit_feedback") as submit:
            response = asyncio.run(feedback_route(request))
        self.assertEqual(response.status_code, 401)
        read_json.assert_not_called()
        rate_ok.assert_not_called()
        rate_record.assert_not_called()
        submit.assert_not_called()

    def test_authenticated_feedback_is_recorded_for_the_session_user(self) -> None:
        with patch("interview_forge.api.support.current_user", return_value=USER), \
             patch("interview_forge.api.routers.auth.feedback_rate_limit_ok", return_value=True) as rate_ok, \
             patch("interview_forge.api.routers.auth.feedback_rate_limit_record") as rate_record, \
             patch("interview_forge.api.routers.auth.submit_feedback", return_value={"id": 9, "submitted": True}) as submit:
            response = self.client.post(
                "/api/feedback",
                json={"content": "页面显示错误", "contact": "reader@example.test", "page": "/cockpit.html?tab=plan"},
                headers={"user-agent": "feedback-regression"},
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"id": 9, "submitted": True})
        rate_ok.assert_called_once()
        rate_record.assert_called_once()
        submit.assert_called_once_with(
            "页面显示错误",
            "reader@example.test",
            "/cockpit.html?tab=plan",
            "feedback-regression",
            "alice",
        )

    def test_legacy_feedback_is_known_but_anonymous_post_gets_401(self) -> None:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), study_server.StudyHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
        try:
            with patch.object(study_server.StudyHandler, "current_user", return_value=None), \
                 patch.object(study_server, "feedback_rate_limit_ok") as rate_ok, \
                 patch.object(study_server, "submit_feedback") as submit:
                body = json.dumps({"content": "guest"}).encode("utf-8")
                connection.request(
                    "POST",
                    "/api/feedback",
                    body=body,
                    headers={"Host": "127.0.0.1", "Content-Type": "application/json"},
                )
                response = connection.getresponse()
                payload = json.loads(response.read())
            self.assertEqual(response.status, 401)
            self.assertIsNone(response.getheader("Location"))
            self.assertEqual(payload, {"error": "未登录"})
            rate_ok.assert_not_called()
            submit.assert_not_called()
        finally:
            connection.close()
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

    def test_server_injects_the_new_feedback_script_version(self) -> None:
        self.assertIn("/assets/feedback-widget.js?v=4", study_server.StudyHandler.WIDGET_SCRIPTS)
        self.assertNotIn("/assets/feedback-widget.js?v=3", study_server.StudyHandler.WIDGET_SCRIPTS)


if __name__ == "__main__":
    unittest.main()
