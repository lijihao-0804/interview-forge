"""Independent acceptance counterexamples for guest and email registration."""
from __future__ import annotations

import os
import re
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import interview_forge.api.routers.static as static_router
from interview_forge.api.app import app
from interview_forge.core.runtime import server_runtime
from interview_forge.core.web_access import canonical_url_path, is_sensitive_path
from interview_forge.services.auth import (
    auth_login,
    connect_auth,
    create_user,
    ensure_admin,
)
from interview_forge.services.registration import (
    RegistrationError,
    register_with_email_code,
    send_registration_code,
)

_REGISTRATION_ENV = {
    "IF_REGISTER_EMAIL_COOLDOWN_SECONDS": "1",
    "IF_REGISTER_IP_HOURLY_LIMIT": "100",
    "IF_REGISTER_IP_DAILY_LIMIT": "100",
    "IF_REGISTER_EMAIL_HOURLY_LIMIT": "100",
    "IF_REGISTER_EMAIL_DAILY_LIMIT": "100",
    "IF_REGISTER_GLOBAL_HOURLY_LIMIT": "100",
    "IF_REGISTER_GLOBAL_DAILY_LIMIT": "100",
    "IF_REGISTER_VERIFY_IP_HOURLY_LIMIT": "100",
    "IF_REGISTER_VERIFY_IP_DAILY_LIMIT": "100",
    "IF_REGISTER_VERIFY_GLOBAL_HOURLY_LIMIT": "100",
    "IF_REGISTER_VERIFY_GLOBAL_DAILY_LIMIT": "100",
}


class RegistrationAcceptanceReviewTests(unittest.TestCase):
    def test_duplicate_email_response_carries_frontend_error_category(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sent: list[tuple[str, str, str]] = []
            runtime = {
                "AUTH_DB_PATH": root / "auth.db",
                "USERS_DIR": root / "users",
                "_AUTH_READY": False,
            }
            with patch.dict(server_runtime._values, runtime, clear=False), \
                 patch.dict(os.environ, _REGISTRATION_ENV, clear=False), \
                 patch("interview_forge.services.gym.send_email",
                       side_effect=lambda *args: sent.append(args)):
                create_user("ExistingUser", "password-1", email="alice@example.com")
                client = TestClient(app, raise_server_exceptions=False)
                try:
                    send_response = client.post(
                        "/api/register/send-code", json={"email": "alice@example.com"}
                    )
                    self.assertEqual(send_response.status_code, 200, send_response.text)
                    match = re.search(r"验证码：(\d{6})", sent[-1][2])
                    self.assertIsNotNone(match)
                    response = client.post("/api/register", json={
                        "email": "alice@example.com",
                        "username": "NewUser",
                        "password": "password-2",
                        "code": match.group(1),
                    })
                    with closing(connect_auth()) as connection:
                        code_status = connection.execute(
                            "SELECT status FROM registration_email_codes WHERE email = ?",
                            ("alice@example.com",),
                        ).fetchone()[0]
                finally:
                    client.close()

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json().get("error_category"), "already_registered", response.text)
        self.assertEqual(code_status, "active")

    def test_duplicate_username_response_carries_frontend_error_category(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sent: list[tuple[str, str, str]] = []
            runtime = {
                "AUTH_DB_PATH": root / "auth.db",
                "USERS_DIR": root / "users",
                "_AUTH_READY": False,
            }
            with patch.dict(server_runtime._values, runtime, clear=False), \
                 patch.dict(os.environ, _REGISTRATION_ENV, clear=False), \
                 patch("interview_forge.services.gym.send_email",
                       side_effect=lambda *args: sent.append(args)):
                create_user("ExistingUser", "password-1")
                client = TestClient(app, raise_server_exceptions=False)
                try:
                    send_response = client.post(
                        "/api/register/send-code", json={"email": "new@example.com"}
                    )
                    self.assertEqual(send_response.status_code, 200, send_response.text)
                    match = re.search(r"验证码：(\d{6})", sent[-1][2])
                    self.assertIsNotNone(match)
                    response = client.post("/api/register", json={
                        "email": "new@example.com",
                        "username": "ExistingUser",
                        "password": "password-2",
                        "code": match.group(1),
                    })
                    with closing(connect_auth()) as connection:
                        failed_status = connection.execute(
                            "SELECT status FROM registration_email_codes WHERE email = ?",
                            ("new@example.com",),
                        ).fetchone()[0]
                        failed_user_count = connection.execute(
                            "SELECT COUNT(*) FROM users WHERE email = ?", ("new@example.com",)
                        ).fetchone()[0]
                    retry = client.post("/api/register", json={
                        "email": "new@example.com",
                        "username": "NewUser",
                        "password": "password-2",
                        "code": match.group(1),
                    })
                    with closing(connect_auth()) as connection:
                        retry_status = connection.execute(
                            "SELECT status FROM registration_email_codes WHERE email = ?",
                            ("new@example.com",),
                        ).fetchone()[0]
                finally:
                    client.close()

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json().get("error_category"), "already_registered", response.text)
        self.assertEqual(failed_status, "active")
        self.assertEqual(failed_user_count, 0)
        self.assertEqual(retry.status_code, 201, retry.text)
        self.assertEqual(retry_status, "consumed")

    def test_public_email_registration_cannot_claim_permanent_admin_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sent: list[tuple[str, str, str]] = []
            runtime = {
                "AUTH_DB_PATH": root / "auth.db",
                "USERS_DIR": root / "users",
                "PERMANENT_ADMIN_USERNAME": "reserved_founder",
                "_AUTH_READY": False,
            }
            with patch.dict(server_runtime._values, runtime, clear=False), \
                 patch.dict(os.environ, _REGISTRATION_ENV, clear=False), \
                 patch("interview_forge.services.gym.send_email",
                       side_effect=lambda *args: sent.append(args)):
                send_registration_code("candidate@example.com", "198.51.100.44")
                match = re.search(r"验证码：(\d{6})", sent[-1][2])
                self.assertIsNotNone(match)

                for reserved_name in ("reserved_founder", "Reserved_Founder"):
                    with self.subTest(reserved_name=reserved_name):
                        with self.assertRaises(RegistrationError) as rejected:
                            register_with_email_code(
                                "candidate@example.com",
                                reserved_name,
                                "password-2",
                                match.group(1),
                                "198.51.100.44",
                            )
                        self.assertEqual(rejected.exception.status, 409)
                        self.assertEqual(rejected.exception.category, "already_registered")

                with closing(connect_auth()) as connection:
                    self.assertEqual(
                        connection.execute(
                            "SELECT COUNT(*) FROM users WHERE username = ? COLLATE NOCASE",
                            ("reserved_founder",),
                        ).fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        connection.execute(
                            "SELECT status FROM registration_email_codes WHERE email = ?",
                            ("candidate@example.com",),
                        ).fetchone()[0],
                        "active",
                    )

                registered = register_with_email_code(
                    "candidate@example.com",
                    "OrdinaryUser",
                    "password-2",
                    match.group(1),
                    "198.51.100.44",
                )
                self.assertEqual(registered["role"], "user")

                # Simulate a second worker starting with stale in-process schema state.
                server_runtime._values["_AUTH_READY"] = False
                with closing(connect_auth()) as connection:
                    self.assertEqual(
                        connection.execute(
                            "SELECT role FROM users WHERE username = 'OrdinaryUser'"
                        ).fetchone()[0],
                        "user",
                    )
                self.assertEqual(auth_login("OrdinaryUser", "password-2")["role"], "user")

                admin = ensure_admin("reserved_founder", "admin-password-1")
                self.assertEqual(admin["role"], "admin")
                self.assertEqual(auth_login("reserved_founder", "admin-password-1")["role"], "admin")
                explicit_admin = create_user(
                    "ExplicitOperator", "admin-password-2", role="admin"
                )
                self.assertEqual(explicit_admin["role"], "admin")

    def test_expired_code_is_rejected_and_invalidated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sent: list[tuple[str, str, str]] = []
            runtime = {
                "AUTH_DB_PATH": root / "auth.db",
                "USERS_DIR": root / "users",
                "_AUTH_READY": False,
            }
            with patch.dict(server_runtime._values, runtime, clear=False), \
                 patch.dict(os.environ, _REGISTRATION_ENV, clear=False), \
                 patch("interview_forge.services.gym.send_email",
                       side_effect=lambda *args: sent.append(args)):
                client = TestClient(app, raise_server_exceptions=False)
                try:
                    send_response = client.post(
                        "/api/register/send-code", json={"email": "expired@example.com"}
                    )
                    self.assertEqual(send_response.status_code, 200, send_response.text)
                    match = re.search(r"验证码：(\d{6})", sent[-1][2])
                    self.assertIsNotNone(match)
                    with closing(connect_auth()) as connection:
                        connection.execute(
                            "UPDATE registration_email_codes SET expires_at = ? WHERE email = ?",
                            (int(time.time()) - 1, "expired@example.com"),
                        )
                    response = client.post("/api/register", json={
                        "email": "expired@example.com",
                        "username": "ExpiredUser",
                        "password": "password-2",
                        "code": match.group(1),
                    })
                    with closing(connect_auth()) as connection:
                        status = connection.execute(
                            "SELECT status FROM registration_email_codes WHERE email = ?",
                            ("expired@example.com",),
                        ).fetchone()[0]
                finally:
                    client.close()

        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json().get("error_category"), "registration")
        self.assertIn("已过期", response.json().get("error", ""))
        self.assertEqual(status, "invalidated")

    def test_anonymous_openapi_schema_is_not_part_of_the_public_surface(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        try:
            response = client.get("/openapi.json", follow_redirects=False)
        finally:
            client.close()
        self.assertEqual(response.status_code, 404, response.text[:200])
        schema = app.openapi()
        self.assertTrue(schema["openapi"].startswith("3."))
        self.assertIn("/api/catalog", schema["paths"])

    def test_sqlite_rollback_journal_cannot_be_served_from_a_public_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "assets" / "state.db"
            target.parent.mkdir(parents=True)
            connection = sqlite3.connect(target)
            try:
                connection.execute("PRAGMA journal_mode = DELETE")
                connection.execute("CREATE TABLE secrets(value TEXT)")
                connection.execute("INSERT INTO secrets VALUES ('SYNTHETIC_ROLLBACK_JOURNAL_SECRET')")
                connection.commit()
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("UPDATE secrets SET value = 'updated'")
                client = TestClient(app, raise_server_exceptions=False)
                try:
                    with patch.object(static_router, "ROOT", root):
                        response = client.get("/assets/state.db-journal", follow_redirects=False)
                finally:
                    client.close()
            finally:
                connection.rollback()
                connection.close()

        self.assertEqual(response.status_code, 404, "SQLite rollback journal was served")
        self.assertNotIn(b"SYNTHETIC_ROLLBACK_JOURNAL_SECRET", response.content)

    def test_nginx_asset_alias_blocks_every_sqlite_sidecar(self) -> None:
        config = (Path(__file__).resolve().parents[1] / "deploy" / "hot100-nginx.conf").read_text(
            encoding="utf-8"
        )
        deny_line = next(
            line for line in config.splitlines()
            if "location ~* \\." in line and "sqlite3" in line and "journal" in line
        )
        pattern = deny_line.split("location ~* ", 1)[1].rsplit(" {", 1)[0]
        deny = re.compile(pattern, re.IGNORECASE)
        for stem in ("db", "sqlite", "sqlite3"):
            for suffix in ("", "-journal", "-wal", "-shm"):
                path = f"/assets/state.{stem}{suffix}"
                with self.subTest(path=path):
                    self.assertIsNotNone(deny.search(path), deny_line)
        self.assertIsNone(deny.search("/assets/state.dbx"))

    def test_sqlite_family_sidecars_are_sensitive_on_every_platform(self) -> None:
        for stem in ("db", "sqlite", "sqlite3"):
            for suffix in ("", "-journal", "-wal", "-shm"):
                path = f"/assets/state.{stem}{suffix}"
                with self.subTest(path=path):
                    self.assertTrue(is_sensitive_path(path))

    def test_decoded_colons_are_rejected_on_every_platform(self) -> None:
        for path in (
            "/assets/state.db:reviewsecret",
            "/assets/state.db%3Areviewsecret",
            "/assets/state.db%253Areviewsecret",
            "/assets/state.db%25253Areviewsecret",
            "/assets/state.db::$DATA",
        ):
            with self.subTest(path=path):
                self.assertIsNone(canonical_url_path(path))
                self.assertTrue(is_sensitive_path(path))

    @unittest.skipUnless(os.name == "nt", "NTFS alternate streams are Windows-specific")
    def test_windows_default_stream_and_semicolon_do_not_bypass_suffix_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "assets" / "state.db"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"SYNTHETIC_DB_SECRET")
            client = TestClient(app, raise_server_exceptions=False)
            try:
                with patch.object(static_router, "ROOT", root):
                    for path in (
                        "/assets/state.db::$DATA",
                        "/assets/state.db%3A%3A%24DATA",
                        "/assets/state.db%253A%253A%2524DATA",
                        "/assets/state.db%25253A%25253A%252524DATA",
                        "/assets/state.db;",
                        "/assets/state.db%3B",
                        "/assets/state.db%253B",
                        "/assets/state.db%25253B",
                    ):
                        with self.subTest(path=path):
                            response = client.get(path, follow_redirects=False)
                            self.assertEqual(response.status_code, 404, path)
                            self.assertNotIn(b"SYNTHETIC_DB_SECRET", response.content, path)
            finally:
                client.close()

    @unittest.skipUnless(os.name == "nt", "NTFS alternate streams are Windows-specific")
    def test_windows_named_alternate_stream_cannot_be_served(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "assets" / "state.db"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"SYNTHETIC_DB_DEFAULT_STREAM")
            with open(str(target) + ":reviewsecret", "wb") as stream:
                stream.write(b"SYNTHETIC_DB_NAMED_STREAM_SECRET")
            client = TestClient(app, raise_server_exceptions=False)
            try:
                with patch.object(static_router, "ROOT", root):
                    for path in (
                        "/assets/state.db:reviewsecret",
                        "/assets/state.db%3Areviewsecret",
                        "/assets/state.db%253Areviewsecret",
                        "/assets/state.db%25253Areviewsecret",
                    ):
                        with self.subTest(path=path):
                            response = client.get(path, follow_redirects=False)
                            self.assertEqual(response.status_code, 404, path)
                            self.assertNotIn(b"SYNTHETIC_DB_NAMED_STREAM_SECRET", response.content, path)
            finally:
                client.close()


if __name__ == "__main__":
    unittest.main()
