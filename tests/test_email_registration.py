"""Email verification and public registration regression tests."""
from __future__ import annotations

import os
import re
import smtplib
import tempfile
import threading
import unittest
import multiprocessing
import json
import time
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.core.runtime import server_runtime
from interview_forge.services import gym, registration
from interview_forge.services.auth import auth_login, create_user


def _reserve_in_process(auth_path: str, users_path: str, email: str,
                        start_path: str, result_path: str) -> None:
    """Child-process worker used to prove SQLite quota serialization."""
    from interview_forge.core.runtime import server_runtime as child_runtime
    from interview_forge.services.registration import PublicRateLimitError, _reserve_registration_send

    child_runtime._values.update({
        "AUTH_DB_PATH": Path(auth_path),
        "USERS_DIR": Path(users_path),
        "_AUTH_READY": True,
    })
    deadline = time.monotonic() + 10
    while not Path(start_path).exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    try:
        attempt_id, _policy = _reserve_registration_send(email, "203.0.113.77", 1_800_000_000)
        result = ("ok", attempt_id)
    except PublicRateLimitError as exc:
        result = ("limited", exc.retry_after)
    except BaseException as exc:  # noqa: BLE001 - parent assertion reports the failure
        result = ("error", type(exc).__name__, str(exc))
    Path(result_path).write_text(json.dumps(result), encoding="utf-8")


def _register_in_process(auth_path: str, users_path: str, email: str, username: str,
                         code: str, ip: str, start_path: str, result_path: str) -> None:
    """Child-process worker proving verification quotas share SQLite state."""
    from interview_forge.core.runtime import server_runtime as child_runtime
    from interview_forge.services.registration import PublicRateLimitError, register_with_email_code

    child_runtime._values.update({
        "AUTH_DB_PATH": Path(auth_path),
        "USERS_DIR": Path(users_path),
        "_AUTH_READY": True,
    })
    deadline = time.monotonic() + 10
    while not Path(start_path).exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    try:
        user = register_with_email_code(email, username, "password-1", code, ip)
        result = ("ok", user["username"])
    except PublicRateLimitError as exc:
        result = ("limited", exc.retry_after)
    except BaseException as exc:  # noqa: BLE001 - parent assertion reports the failure
        result = ("error", type(exc).__name__, str(exc))
    Path(result_path).write_text(json.dumps(result), encoding="utf-8")


class EmailRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.clock = 1_800_000_000
        self.patches = [
            patch.dict(server_runtime._values, {
                "AUTH_DB_PATH": root / "auth.db",
                "USERS_DIR": root / "users",
                "_AUTH_READY": False,
            }, clear=False),
            patch.dict(os.environ, {
                "IF_REGISTER_EMAIL_COOLDOWN_SECONDS": "60",
                "IF_REGISTER_IP_HOURLY_LIMIT": "20",
                "IF_REGISTER_IP_DAILY_LIMIT": "50",
                "IF_REGISTER_EMAIL_HOURLY_LIMIT": "10",
                "IF_REGISTER_EMAIL_DAILY_LIMIT": "20",
                "IF_REGISTER_GLOBAL_HOURLY_LIMIT": "100",
                "IF_REGISTER_GLOBAL_DAILY_LIMIT": "200",
                "IF_REGISTER_VERIFY_IP_HOURLY_LIMIT": "20",
                "IF_REGISTER_VERIFY_IP_DAILY_LIMIT": "60",
                "IF_REGISTER_VERIFY_GLOBAL_HOURLY_LIMIT": "500",
                "IF_REGISTER_VERIFY_GLOBAL_DAILY_LIMIT": "5000",
                "IF_REGISTER_CODE_TTL_SECONDS": "600",
                "IF_REGISTER_CODE_MAX_ATTEMPTS": "3",
            }, clear=False),
            patch.object(registration.time, "time", side_effect=lambda: self.clock),
        ]
        for item in self.patches:
            item.start()
        self.sent: list[tuple[str, str, str]] = []

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def _send(self, email: str = "Alice@Example.com") -> tuple[dict, str]:
        with patch("interview_forge.services.gym.send_email", side_effect=lambda *args: self.sent.append(args)):
            result = registration.send_registration_code(email, "203.0.113.8")
        body = self.sent[-1][2]
        code = re.search(r"验证码：(\d{6})", body)
        self.assertIsNotNone(code)
        return result, code.group(1)

    def test_code_is_hashed_then_consumed_atomically_with_normalized_email(self) -> None:
        result, code = self._send()
        self.assertTrue(result["ok"])
        self.assertEqual(result["resend_after"], 60)
        self.assertEqual(result["expires_in"], 600)

        with closing(server_runtime.connect_auth()) as connection:
            row = connection.execute(
                "SELECT email, code_hash, status FROM registration_email_codes"
            ).fetchone()
            self.assertEqual(row["email"], "alice@example.com")
            self.assertEqual(row["status"], "active")
            self.assertNotIn(code, row["code_hash"])

        user = registration.register_with_email_code(
            "ALICE@example.com", "AliceUser", "password-1", code
        )
        self.assertEqual(user["username"], "AliceUser")
        with closing(server_runtime.connect_auth()) as connection:
            stored = connection.execute(
                "SELECT email FROM users WHERE username = 'AliceUser'"
            ).fetchone()
            self.assertEqual(stored["email"], "alice@example.com")
            self.assertEqual(connection.execute(
                "SELECT status FROM registration_email_codes WHERE id = 1"
            ).fetchone()["status"], "consumed")
        self.assertTrue((Path(self.temp.name) / "users" / "AliceUser" / "hot100-study.db").is_file())

        with self.assertRaises(registration.RegistrationError):
            registration.register_with_email_code(
                "alice@example.com", "SecondUser", "password-2", code
            )

    def test_wrong_code_attempts_stay_bounded_and_do_not_consume_code(self) -> None:
        _result, code = self._send()
        wrong = "000000" if code != "000000" else "999999"
        for left in (2, 1):
            with self.assertRaisesRegex(registration.RegistrationError, f"还可尝试 {left} 次"):
                registration.register_with_email_code(
                    "alice@example.com", "AliceUser", "password-1", wrong
                )
        with closing(server_runtime.connect_auth()) as connection:
            self.assertEqual(connection.execute(
                "SELECT attempts FROM registration_email_codes WHERE id = 1"
            ).fetchone()[0], 2)
        user = registration.register_with_email_code(
            "alice@example.com", "AliceUser", "password-1", code
        )
        self.assertEqual(user["username"], "AliceUser")

    def test_non_ascii_digits_fail_before_rate_ledger_or_scrypt(self) -> None:
        with patch.object(registration, "_code_digest") as code_digest:
            with self.assertRaisesRegex(registration.RegistrationError, "6 位数字"):
                registration.register_with_email_code(
                    "alice@example.com", "AliceUser", "password-1", "１２３４５６",
                    "203.0.113.8",
                )
        code_digest.assert_not_called()
        with closing(server_runtime.connect_auth()) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM public_rate_events WHERE namespace LIKE 'register_verify_%'"
            ).fetchone()[0], 0)

    def test_failed_smtp_send_is_recorded_and_obeys_cooldown(self) -> None:
        with patch(
            "interview_forge.services.gym.send_email",
            side_effect=gym.SMTPNotConfiguredError("not configured"),
        ):
            with self.assertRaises(registration.RegistrationError) as raised:
                registration.send_registration_code("alice@example.com", "203.0.113.8")
        self.assertEqual(raised.exception.status, 503)
        self.assertEqual(raised.exception.category, "email_not_configured")

        with closing(server_runtime.connect_auth()) as connection:
            attempt = connection.execute(
                "SELECT status, failure_category FROM registration_send_attempts"
            ).fetchone()
            code_status = connection.execute(
                "SELECT status FROM registration_email_codes"
            ).fetchone()
        self.assertEqual(attempt["status"], "failed")
        self.assertEqual(attempt["failure_category"], "email_not_configured")
        self.assertEqual(code_status["status"], "invalidated")

        with patch("interview_forge.services.gym.send_email") as sender:
            with self.assertRaises(registration.PublicRateLimitError) as limited:
                registration.send_registration_code("alice@example.com", "203.0.113.8")
        self.assertEqual(limited.exception.status, 429)
        self.assertGreaterEqual(limited.exception.retry_after, 1)
        sender.assert_not_called()

    def test_hash_storage_failure_is_explained_without_unbound_smtp_error(self) -> None:
        with patch.object(registration, "_code_digest", side_effect=RuntimeError("hash failed")):
            with self.assertRaises(registration.RegistrationError) as raised:
                registration.send_registration_code("alice@example.com", "203.0.113.8")
        self.assertEqual(raised.exception.status, 503)
        self.assertEqual(raised.exception.category, "registration_storage_failed")
        with closing(server_runtime.connect_auth()) as connection:
            attempt = connection.execute(
                "SELECT status, failure_category FROM registration_send_attempts"
            ).fetchone()
        self.assertEqual((attempt["status"], attempt["failure_category"]),
                         ("failed", "code_storage_failed"))

    def test_old_attempt_cleanup_removes_dependent_codes_first(self) -> None:
        self._send("old@example.com")
        self.clock += 8 * 86400
        self._send("new@example.com")
        with closing(server_runtime.connect_auth()) as connection:
            codes = connection.execute(
                "SELECT email FROM registration_email_codes ORDER BY id"
            ).fetchall()
            attempts = connection.execute(
                "SELECT COUNT(*) FROM registration_send_attempts"
            ).fetchone()[0]
        self.assertEqual([row["email"] for row in codes], ["new@example.com"])
        self.assertEqual(attempts, 1)

    def test_concurrent_redemption_creates_only_one_user(self) -> None:
        _result, code = self._send()
        barrier = threading.Barrier(2)
        outcomes: list[object] = []

        def redeem(username: str) -> None:
            barrier.wait()
            try:
                outcomes.append(registration.register_with_email_code(
                    "alice@example.com", username, "password-1", code
                ))
            except Exception as exc:  # noqa: BLE001 - assertions inspect the type below
                outcomes.append(exc)

        threads = [threading.Thread(target=redeem, args=(name,)) for name in ("AliceOne", "AliceTwo")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(sum(isinstance(item, dict) for item in outcomes), 1)
        self.assertEqual(sum(isinstance(item, registration.RegistrationError) for item in outcomes), 1)
        with closing(server_runtime.connect_auth()) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM users WHERE email = 'alice@example.com'"
            ).fetchone()[0], 1)

    def test_concurrent_unique_email_and_legacy_null_email_users(self) -> None:
        legacy_a = create_user("LegacyA", "password-1")
        legacy_b = create_user("LegacyB", "password-2")
        self.assertEqual(auth_login("LegacyA", "password-1")["id"], legacy_a["id"])
        self.assertEqual(auth_login("LegacyB", "password-2")["id"], legacy_b["id"])

        barrier = threading.Barrier(2)
        outcomes: list[object] = []

        def make_user(username: str) -> None:
            barrier.wait()
            try:
                outcomes.append(create_user(
                    username, "password-1", email="shared@example.com"
                ))
            except Exception as exc:  # noqa: BLE001 - assertion inspects the type below
                outcomes.append(exc)

        threads = [
            threading.Thread(target=make_user, args=("EmailRaceA",)),
            threading.Thread(target=make_user, args=("EmailRaceB",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertEqual(sum(isinstance(item, dict) for item in outcomes), 1)
        self.assertEqual(sum(isinstance(item, ValueError) for item in outcomes), 1)

    def test_sqlite_quota_is_atomic_across_processes(self) -> None:
        with closing(server_runtime.connect_auth()):
            pass
        with patch.dict(os.environ, {
            "IF_REGISTER_IP_HOURLY_LIMIT": "1",
            "IF_REGISTER_IP_DAILY_LIMIT": "1",
        }, clear=False):
            context = multiprocessing.get_context("spawn")
            start_path = Path(self.temp.name) / "start.limit"
            result_paths = [Path(self.temp.name) / f"result-{index}.json" for index in range(2)]
            processes = [
                context.Process(
                    target=_reserve_in_process,
                    args=(str(Path(self.temp.name) / "auth.db"),
                          str(Path(self.temp.name) / "users"), email,
                          str(start_path), str(result_paths[index])),
                )
                for index, email in enumerate(("one@example.com", "two@example.com"))
            ]
            for process in processes:
                process.start()
            start_path.write_text("1", encoding="ascii")
            deadline = time.monotonic() + 15
            while any(not path.exists() for path in result_paths) and time.monotonic() < deadline:
                time.sleep(0.02)
            for process in processes:
                process.join(timeout=15)
                if process.is_alive():
                    process.terminate()
                    self.fail("cross-process limiter worker did not finish")
            self.assertTrue(all(path.is_file() for path in result_paths))
            outcomes = [json.loads(path.read_text(encoding="utf-8")) for path in result_paths]
        self.assertEqual(sorted(item[0] for item in outcomes), ["limited", "ok"])

    def test_verification_quota_is_atomic_across_processes(self) -> None:
        _result, code = self._send()
        with patch.dict(os.environ, {
            "IF_REGISTER_VERIFY_IP_HOURLY_LIMIT": "20",
            "IF_REGISTER_VERIFY_IP_DAILY_LIMIT": "60",
            "IF_REGISTER_VERIFY_GLOBAL_HOURLY_LIMIT": "1",
            "IF_REGISTER_VERIFY_GLOBAL_DAILY_LIMIT": "1",
        }, clear=False):
            context = multiprocessing.get_context("spawn")
            start_path = Path(self.temp.name) / "start-register.limit"
            result_paths = [Path(self.temp.name) / f"register-result-{index}.json" for index in range(2)]
            processes = [
                context.Process(
                    target=_register_in_process,
                    args=(
                        str(Path(self.temp.name) / "auth.db"),
                        str(Path(self.temp.name) / "users"),
                        "alice@example.com",
                        username,
                        code,
                        f"203.0.113.{index + 10}",
                        str(start_path),
                        str(result_paths[index]),
                    ),
                )
                for index, username in enumerate(("RaceAlpha", "RaceBeta"))
            ]
            for process in processes:
                process.start()
            start_path.write_text("1", encoding="ascii")
            deadline = time.monotonic() + 15
            while any(not path.exists() for path in result_paths) and time.monotonic() < deadline:
                time.sleep(0.02)
            for process in processes:
                process.join(timeout=15)
                if process.is_alive():
                    process.terminate()
                    self.fail("cross-process verification worker did not finish")
            self.assertTrue(all(path.is_file() for path in result_paths))
            outcomes = [json.loads(path.read_text(encoding="utf-8")) for path in result_paths]
        self.assertEqual(sorted(item[0] for item in outcomes), ["limited", "ok"])
        with closing(server_runtime.connect_auth()) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM users WHERE email = 'alice@example.com'"
            ).fetchone()[0], 1)
            events = {
                row["namespace"]: row["count"]
                for row in connection.execute(
                    "SELECT namespace, COUNT(*) AS count FROM public_rate_events "
                    "WHERE namespace IN ('register_verify_ip', 'register_verify_global') "
                    "GROUP BY namespace"
                )
            }
        self.assertEqual(events, {"register_verify_ip": 1, "register_verify_global": 1})

    def test_newer_delivery_is_not_overwritten_by_slower_old_delivery(self) -> None:
        old_delivery_started = threading.Event()
        release_old_delivery = threading.Event()
        call_lock = threading.Lock()
        call_count = [0]

        def deliver(*_args) -> None:
            with call_lock:
                call_count[0] += 1
                number = call_count[0]
            if number == 1:
                old_delivery_started.set()
                release_old_delivery.wait(10)

        first_result: list[object] = []

        def first_send() -> None:
            try:
                first_result.append(registration.send_registration_code(
                    "alice@example.com", "203.0.113.8"
                ))
            except BaseException as exc:  # noqa: BLE001 - assertion inspects outcome
                first_result.append(exc)

        with patch("interview_forge.services.gym.send_email", side_effect=deliver):
            first = threading.Thread(target=first_send)
            first.start()
            self.assertTrue(old_delivery_started.wait(5))
            self.clock += 61
            second = registration.send_registration_code("alice@example.com", "203.0.113.8")
            self.assertTrue(second["ok"])
            release_old_delivery.set()
            first.join(timeout=10)

        self.assertFalse(first.is_alive())
        self.assertEqual(len(first_result), 1)
        self.assertIsInstance(first_result[0], registration.RegistrationError)
        self.assertEqual(first_result[0].category, "email_delivery_failed")
        with closing(server_runtime.connect_auth()) as connection:
            rows = connection.execute(
                "SELECT send_attempt_id, status FROM registration_email_codes ORDER BY id"
            ).fetchall()
            newest_attempt = connection.execute(
                "SELECT MAX(id) FROM registration_send_attempts"
            ).fetchone()[0]
            attempts = connection.execute(
                "SELECT status, failure_category FROM registration_send_attempts ORDER BY id"
            ).fetchall()
        self.assertEqual([row["status"] for row in rows], ["invalidated", "active"])
        self.assertEqual(rows[-1]["send_attempt_id"], newest_attempt)
        self.assertEqual(
            [(row["status"], row["failure_category"]) for row in attempts],
            [("failed", "email_delivery_failed"), ("sent", "")],
        )

    def test_fastapi_returns_retry_after_and_old_invite_cannot_register(self) -> None:
        with closing(server_runtime.connect_auth()) as connection:
            connection.execute(
                "INSERT INTO invite_codes(code, status, note, created_at) VALUES ('FORGE-OLD-CODE', 'unused', '', ?)",
                ("2026-11-12T10:00:00+08:00",),
            )
        client = TestClient(app, raise_server_exceptions=False)
        try:
            response = client.post("/api/register", json={
                "email": "alice@example.com",
                "username": "AliceUser",
                "password": "password-1",
                "code": "FORGE-OLD-CODE",
            })
            self.assertEqual(response.status_code, 400)
            self.assertNotIn("AliceUser", response.text)

            with patch(
                "interview_forge.api.routers.auth.send_registration_code",
                side_effect=registration.PublicRateLimitError("请求过于频繁", 17),
            ):
                limited = client.post("/api/register/send-code", json={"email": "alice@example.com"})
            self.assertEqual(limited.status_code, 429)
            self.assertEqual(limited.headers["Retry-After"], "17")
            self.assertEqual(limited.json()["retry_after"], 17)
        finally:
            client.close()

    def test_fastapi_registration_verification_limit_uses_client_ip(self) -> None:
        _result, code = self._send()
        wrong = "000000" if code != "000000" else "999999"
        payload = {
            "email": "alice@example.com",
            "username": "AliceUser",
            "password": "password-1",
            "code": wrong,
        }
        with patch.dict(os.environ, {
            "IF_REGISTER_VERIFY_IP_HOURLY_LIMIT": "1",
            "IF_REGISTER_VERIFY_IP_DAILY_LIMIT": "10",
            "IF_REGISTER_VERIFY_GLOBAL_HOURLY_LIMIT": "100",
            "IF_REGISTER_VERIFY_GLOBAL_DAILY_LIMIT": "1000",
        }, clear=False):
            client = TestClient(app, raise_server_exceptions=False)
            try:
                first = client.post("/api/register", json=payload)
                second = client.post("/api/register", json=payload)
            finally:
                client.close()
        self.assertEqual(first.status_code, 400)
        self.assertEqual(second.status_code, 429)
        self.assertIn("Retry-After", second.headers)
        self.assertGreaterEqual(int(second.headers["Retry-After"]), 1)
        self.assertEqual(second.json()["retry_after"], int(second.headers["Retry-After"]))
        self.assertEqual(second.json()["error_category"], "rate_limited")

    def test_smtp_starttls_failure_never_falls_back_to_plaintext_login(self) -> None:
        cipher = MagicMock()
        cipher.decrypt.return_value = b"smtp-auth-code"
        fake_connection = MagicMock()
        fake_connection.execute.return_value.fetchone.return_value = {
            "auth_code_encrypted": "encrypted"
        }
        fake_server = MagicMock()
        fake_server.starttls.side_effect = smtplib.SMTPException("tls required")

        with patch.object(gym, "smtp_config_status", return_value={
            "configured": True,
            "smtp_host": "smtp.example.test",
            "smtp_port": 587,
            "smtp_user": "sender@example.com",
        }), patch.object(gym, "connect", return_value=fake_connection), \
             patch.object(gym, "_fernet", return_value=cipher), \
             patch("smtplib.SMTP", return_value=fake_server):
            with self.assertRaises(smtplib.SMTPException):
                gym.send_email("recipient@example.com", "subject", "body")

        fake_server.starttls.assert_called_once()
        fake_server.login.assert_not_called()
        fake_server.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
