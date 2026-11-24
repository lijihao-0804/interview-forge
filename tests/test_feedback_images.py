"""反馈图片附件：上传、关联、读取与权限边界。"""
from __future__ import annotations

import base64
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from interview_forge.services import community


def _connect_factory(path: Path):
    def connect():
        db = sqlite3.connect(path, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db
    return connect


class FeedbackImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.dir.name) / "auth.db"
        db = _connect_factory(self.db_path)()
        db.executescript(
            """
            CREATE TABLE feedback(
                id INTEGER PRIMARY KEY, content TEXT NOT NULL, username TEXT NOT NULL DEFAULT '',
                contact TEXT NOT NULL DEFAULT '', page TEXT NOT NULL DEFAULT '',
                user_agent TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL, resolved_at TEXT, resolved_note TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE feedback_attachments(
                id INTEGER PRIMARY KEY, feedback_id INTEGER, user_id INTEGER NOT NULL,
                mime TEXT NOT NULL, byte_size INTEGER NOT NULL, data BLOB NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        db.close()
        self.patch = patch.dict(
            community.server_runtime._values,
            {"connect_auth": _connect_factory(self.db_path)},
        )
        self.patch.start()
        self.data_url = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()

    def tearDown(self) -> None:
        self.patch.stop()
        self.dir.cleanup()

    def test_upload_then_attach_to_feedback(self):
        image = community.save_feedback_image(7, self.data_url)
        self.assertEqual(image["mime"], "image/png")
        result = community.submit_feedback(
            "页面有一张截图", "", "/cockpit.html", "ua", "alice",
            user_id=7, image_ids=[image["id"]],
        )
        self.assertEqual(result["images"], 1)
        mime, blob = community.get_feedback_image(image["id"])
        self.assertEqual(mime, "image/png")
        self.assertTrue(blob.startswith(b"\x89PNG"))
        items = community.list_feedback()
        self.assertEqual(items[0]["images"], [{"id": image["id"], "mime": "image/png", "size": len(blob)}])

    def test_cannot_attach_another_users_image(self):
        image = community.save_feedback_image(7, self.data_url)
        with self.assertRaises(ValueError):
            community.submit_feedback(
                "偷用附件", "", "/", "ua", "bob",
                user_id=8, image_ids=[image["id"]],
            )

    def test_rejects_bad_or_oversized_images(self):
        with self.assertRaises(ValueError):
            community.save_feedback_image(7, "data:text/plain;base64,abc")
        big = "data:image/png;base64," + base64.b64encode(b"x" * (community._FEEDBACK_IMAGE_MAX_BYTES + 1)).decode()
        with self.assertRaises(ValueError):
            community.save_feedback_image(7, big)

    def test_more_than_three_images_rejected(self):
        ids = [community.save_feedback_image(7, self.data_url)["id"] for _ in range(4)]
        with self.assertRaises(ValueError):
            community.submit_feedback("四张图", "", "/", "ua", "alice", user_id=7, image_ids=ids)


if __name__ == "__main__":
    unittest.main()
