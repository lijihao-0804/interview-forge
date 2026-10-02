import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from interview_forge.db.connection import connect
from interview_forge.db.tuning import configure_connection


class SQLiteTuningTests(unittest.TestCase):
    def test_settings_apply_after_schema_is_already_initialized(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / "study.db"
            for _ in range(2):
                with closing(connect(path)) as connection:
                    self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                    self.assertEqual(connection.execute("PRAGMA busy_timeout").fetchone()[0], 10000)
                    self.assertEqual(connection.execute("PRAGMA cache_size").fetchone()[0], -32000)
                    self.assertEqual(connection.execute("PRAGMA synchronous").fetchone()[0], 2)

    def test_normal_is_opt_in_and_auth_keeps_full(self):
        with patch.dict(os.environ, {"IF_SQLITE_SYNCHRONOUS": "NORMAL"}), closing(sqlite3.connect(":memory:")) as connection:
            configure_connection(connection)
            self.assertEqual(connection.execute("PRAGMA synchronous").fetchone()[0], 1)
            configure_connection(connection, auth=True)
            self.assertEqual(connection.execute("PRAGMA synchronous").fetchone()[0], 2)

    def test_invalid_configuration_falls_back_safely(self):
        values = {"IF_SQLITE_BUSY_TIMEOUT_MS": "bad", "IF_SQLITE_CACHE_KIB": "-1",
                  "IF_SQLITE_MMAP_BYTES": "999999999999", "IF_SQLITE_SYNCHRONOUS": "OFF"}
        with patch.dict(os.environ, values), closing(sqlite3.connect(":memory:")) as connection:
            configure_connection(connection)
            self.assertEqual(connection.execute("PRAGMA busy_timeout").fetchone()[0], 10000)
            self.assertEqual(connection.execute("PRAGMA cache_size").fetchone()[0], -32000)
            self.assertEqual(connection.execute("PRAGMA synchronous").fetchone()[0], 2)

    def test_reader_does_not_request_writer_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "study.db"
            with closing(connect(path)) as writer, closing(connect(path)) as reader:
                writer.execute("BEGIN IMMEDIATE")
                try:
                    reader.execute("SELECT COUNT(*) FROM review_cards").fetchone()
                    self.assertFalse(reader.in_transaction)
                finally:
                    writer.rollback()


if __name__ == "__main__":
    unittest.main()
