import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from interview_forge.ai.config_store import AIConfigError, AIConfigStore, AISecretUnavailable
from interview_forge.ai.errors import AIServiceError
from interview_forge.ai.quota import consume_chat_quota
from interview_forge.core.runtime import server_runtime
from interview_forge.services.leetcode import get_credentials, set_credentials
from interview_forge.services.study import export_database_snapshot
from interview_forge.db.schema import SCHEMA


class AuditHardeningTests(unittest.TestCase):
    def _learning_db(self, root: Path) -> Path:
        db = root / "user.db"
        with closing(server_runtime.connect(db)) as connection:
            connection.executescript(SCHEMA)
            connection.commit()
        return db

    def test_leetcode_credentials_are_encrypted_and_wrong_key_is_safe(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"INTERVIEW_FORGE_AI_CONFIG_KEY": "audit-master-key"}, clear=False
        ):
            db = self._learning_db(Path(directory))
            secret = "session-secret-that-must-not-be-plain"
            set_credentials({"leetcode_session": secret}, db)
            connection = sqlite3.connect(db)
            try:
                raw = connection.execute(
                    "SELECT value FROM credentials WHERE key = 'leetcode_session'"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertNotIn(secret, raw)
            self.assertTrue(raw.startswith("gAAAA"))
            self.assertEqual(get_credentials(db)["leetcode_session"], secret)
            with patch.dict(os.environ, {"INTERVIEW_FORGE_AI_CONFIG_KEY": "wrong-key"}, clear=False):
                with self.assertRaises(AISecretUnavailable):
                    get_credentials(db)

    def test_database_export_excludes_credentials_without_mutating_source(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"INTERVIEW_FORGE_AI_CONFIG_KEY": "audit-master-key"}, clear=False
        ):
            db = self._learning_db(Path(directory))
            set_credentials({"leetcode_session": "export-secret"}, db)
            snapshot = export_database_snapshot(db)
            backup = Path(directory) / "backup.db"
            backup.write_bytes(snapshot)
            connection = sqlite3.connect(backup)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM credentials").fetchone()[0], 0)
            finally:
                connection.close()
            self.assertEqual(get_credentials(db)["leetcode_session"], "export-secret")

    def test_chat_quota_is_atomic_and_separate_from_analysis_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            db = self._learning_db(Path(directory))
            self.assertEqual(consume_chat_quota(db, daily_limit=2)["used"], 1)
            self.assertEqual(consume_chat_quota(db, daily_limit=2)["used"], 2)
            with self.assertRaises(AIServiceError) as raised:
                consume_chat_quota(db, daily_limit=2)
            self.assertEqual(raised.exception.category, "chat_quota")
            with closing(server_runtime.connect(db)) as connection:
                self.assertEqual(connection.execute("SELECT used FROM ai_daily_quota").fetchone(), None)

    def test_provider_save_wires_network_target_validation(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"INTERVIEW_FORGE_AI_CONFIG_KEY": "audit-master-key"}, clear=False
        ), patch(
            "interview_forge.ai.config_store.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("169.254.10.10", 443))],
        ):
            store = AIConfigStore(Path(directory) / "ai.db")
            with self.assertRaises(AIConfigError):
                store.create_provider(
                    name="unsafe", vendor="custom", protocol="openai_chat",
                    base_url="https://provider.example", api_key="k",
                )


if __name__ == "__main__":
    unittest.main()
