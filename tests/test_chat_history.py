import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from tools import study_server as server


class ChatHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.auth_path = Path(self.temp.name) / "auth.db"
        self.old_ready = server._AUTH_READY
        server._AUTH_READY = False
        self.auth_patch = patch.object(server, "AUTH_DB_PATH", self.auth_path)
        self.auth_patch.start()
        self.user = server.create_user("chat_user", "password1")
        with server.closing(server.connect_auth()) as connection:
            connection.executemany(
                "INSERT INTO chat_messages(user_id, content, created_at) VALUES (?, ?, ?)",
                [(self.user["id"], f"message-{index}", f"2026-09-08T10:{index % 60:02d}:00+08:00")
                 for index in range(1, 121)],
            )

    def tearDown(self):
        self.auth_patch.stop()
        server._AUTH_READY = self.old_ready
        self.temp.cleanup()

    def test_before_pages_are_ascending_non_overlapping_and_report_end(self):
        recent = server.chat_messages_after(-1, 50)
        self.assertEqual([item["id"] for item in recent], list(range(71, 121)))

        middle, has_older = server.chat_messages_before(71, 50)
        self.assertTrue(has_older)
        self.assertEqual([item["id"] for item in middle], list(range(21, 71)))

        oldest, has_older = server.chat_messages_before(21, 50)
        self.assertFalse(has_older)
        self.assertEqual([item["id"] for item in oldest], list(range(1, 21)))
        self.assertFalse(set(item["id"] for item in recent) & set(item["id"] for item in middle))
        self.assertFalse(set(item["id"] for item in middle) & set(item["id"] for item in oldest))

    def test_after_incremental_behavior_and_limit_bounds_remain(self):
        self.assertEqual([item["id"] for item in server.chat_messages_after(115, 50)], list(range(116, 121)))
        self.assertEqual(len(server.chat_messages_after(-1, 999)), 100)
        one, _ = server.chat_messages_before(121, 0)
        self.assertEqual([item["id"] for item in one], [120])

    def test_http_rejects_mixed_cursors_and_returns_before_metadata(self):
        token = server.create_session(int(self.user["id"]))
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.StudyHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        headers = {"Cookie": f"{server.SESSION_COOKIE}={token}"}
        try:
            with urlopen(Request(base + "/api/chat/messages?after=-1&limit=50", headers=headers)) as response:
                initial = json.loads(response.read())
            self.assertTrue(initial["has_older"])
            self.assertEqual([item["id"] for item in initial["items"]], list(range(71, 121)))
            with urlopen(Request(base + "/api/chat/messages?before=71&limit=50", headers=headers)) as response:
                payload = json.loads(response.read())
            self.assertTrue(payload["has_older"])
            self.assertEqual([item["id"] for item in payload["items"]], list(range(21, 71)))
            with self.assertRaises(HTTPError) as raised:
                urlopen(Request(base + "/api/chat/messages?after=1&before=50", headers=headers))
            self.assertEqual(raised.exception.code, 400)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_frontend_history_contract(self):
        source = (Path(__file__).parents[1] / "assets" / "auth-widget.js").read_text(encoding="utf-8")
        for marker in (
            "oldestId", "latestId", "hasOlder", "olderLoading",
            'before=" + chatState.oldestId + "&limit=50',
            "加载更早消息", "没有更早消息了", "加载失败，请重试", "重新加载",
            "msgs.scrollHeight - oldHeight + oldTop",
            'msgs.addEventListener("scroll"', "msgs.scrollTop < 64",
            "chatState.messages.sort", "chatState.messages.length > 2000",
            'scrollMode === "preserve"', "previousTime",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("while (msgs.children.length > 300)", source)
        self.assertNotIn("renderedOrder.length > 1000", source)


if __name__ == "__main__":
    unittest.main()
