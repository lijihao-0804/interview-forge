"""Account-security acceptance tests for email login, reset, and email change."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.core.runtime import server_runtime
from interview_forge.core.web_access import PUBLIC_FILES
from interview_forge.services import registration
from interview_forge.services.auth import (
    auth_login,
    connect_auth,
    create_session,
    create_user,
    session_user,
)
from interview_forge.services.registration import (
    PublicRateLimitError,
    normalize_email,
)

_ENV = {
    "IF_REGISTER_EMAIL_COOLDOWN_SECONDS": "1",
    "IF_REGISTER_IP_HOURLY_LIMIT": "100",
    "IF_REGISTER_IP_DAILY_LIMIT": "100",
    "IF_REGISTER_EMAIL_HOURLY_LIMIT": "100",
    "IF_REGISTER_EMAIL_DAILY_LIMIT": "100",
    "IF_REGISTER_DOMAIN_HOURLY_LIMIT": "100",
    "IF_REGISTER_DOMAIN_DAILY_LIMIT": "100",
    "IF_REGISTER_GLOBAL_HOURLY_LIMIT": "100",
    "IF_REGISTER_GLOBAL_DAILY_LIMIT": "100",
    "IF_REGISTER_VERIFY_IP_HOURLY_LIMIT": "100",
    "IF_REGISTER_VERIFY_IP_DAILY_LIMIT": "100",
    "IF_REGISTER_VERIFY_GLOBAL_HOURLY_LIMIT": "100",
    "IF_REGISTER_VERIFY_GLOBAL_DAILY_LIMIT": "100",
}


class _FakeUrlopen:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __call__(self, *_args, **_kwargs):
        payload = self.payload

        class Response:
            def read(self, _size: int = -1) -> bytes:
                return json.dumps(payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *_exc) -> bool:
                return False

        return Response()


class AccountSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.sent: list[tuple[str, str, str]] = []
        self.patches = [
            patch.dict(server_runtime._values, {
                "AUTH_DB_PATH": root / "auth.db",
                "USERS_DIR": root / "users",
                "_AUTH_READY": False,
            }, clear=False),
            patch.dict(os.environ, _ENV, clear=False),
            patch("interview_forge.services.gym.send_email",
                  side_effect=lambda *args: self.sent.append(args)),
        ]
        for item in self.patches:
            item.start()
        registration._SEARCH_EVENTS.clear()
        registration._SEARCH_GLOBAL.clear()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        registration._SEARCH_EVENTS.clear()
        registration._SEARCH_GLOBAL.clear()
        self.temp.cleanup()

    def _client(self) -> TestClient:
        return TestClient(app, raise_server_exceptions=False)

    def _code_from_last_mail(self) -> str:
        match = re.search(r"验证码：(\d{6})", self.sent[-1][2])
        self.assertIsNotNone(match)
        return match.group(1)

    def test_login_accepts_username_or_verified_email(self) -> None:
        user = create_user("AliceUser", "password-1", email="Alice@Example.com")
        self.assertEqual(
            auth_login("AliceUser", "password-1")["id"], user["id"]
        )
        self.assertEqual(
            auth_login("alice@example.com", "password-1")["id"], user["id"]
        )
        self.assertEqual(
            auth_login("ALICE@EXAMPLE.COM", "password-1")["id"], user["id"]
        )
        # A single unambiguous case variant is accepted; ambiguous legacy
        # duplicates are covered by test_learning_analytics_api.
        self.assertEqual(auth_login("aliceuser", "password-1")["id"], user["id"])
        self.assertEqual(auth_login("ALICEUSER", "password-1")["id"], user["id"])
        self.assertEqual(str(auth_login("alice@example.com", "password-1")["email"]), "alice@example.com")
        with self.assertRaisesRegex(ValueError, "用户名或密码错误"):
            auth_login("alice@example.com", "wrong-password")
        with self.assertRaisesRegex(ValueError, "用户名或密码错误"):
            auth_login("nobody@example.com", "password-1")

    def test_login_endpoint_and_me_expose_email_without_hash(self) -> None:
        create_user("BobUser", "password-1", email="bob@example.com")
        client = self._client()
        try:
            login = client.post("/api/login", json={"username": "bob@example.com", "password": "password-1"})
            self.assertEqual(login.status_code, 201, login.text)
            self.assertEqual(login.json()["username"], "BobUser")
            self.assertEqual(login.json()["email"], "bob@example.com")
            identifier_login = client.post(
                "/api/login", json={"identifier": "BobUser", "password": "password-1"}
            )
            self.assertEqual(identifier_login.status_code, 201, identifier_login.text)
            email_field_login = client.post(
                "/api/login", json={"email": "BOB@example.com", "password": "password-1"}
            )
            self.assertEqual(email_field_login.status_code, 201, email_field_login.text)
            me = client.get("/api/me")
        finally:
            client.close()
        self.assertEqual(me.status_code, 200, me.text)
        payload = me.json()
        self.assertEqual(payload["email"], "bob@example.com")
        self.assertNotIn("password_hash", json.dumps(payload))
        self.assertNotIn("password-1", json.dumps(payload))

    def test_password_reset_rotates_password_and_revokes_sessions(self) -> None:
        user = create_user("Carol", "old-password-1", email="carol@example.com")
        session = create_session(int(user["id"]))
        self.assertIsNotNone(session_user(session))

        client = self._client()
        try:
            sent = client.post("/api/password/forgot/send-code", json={"email": "carol@example.com"})
            self.assertEqual(sent.status_code, 200, sent.text)
            code = self._code_from_last_mail()
            reset = client.post("/api/password/forgot/reset", json={
                "email": "carol@example.com", "code": code, "password": "new-password-2",
            })
            reused = client.post("/api/password/forgot/reset", json={
                "email": "carol@example.com", "code": code, "password": "another-password-3",
            })
        finally:
            client.close()

        self.assertEqual(reset.status_code, 201, reset.text)
        self.assertEqual(reused.status_code, 400, reused.text)
        self.assertIsNone(session_user(session))
        with self.assertRaisesRegex(ValueError, "用户名或密码错误"):
            auth_login("carol@example.com", "old-password-1")
        self.assertEqual(auth_login("carol@example.com", "new-password-2")["id"], user["id"])

    def test_forgot_password_does_not_reveal_unknown_addresses(self) -> None:
        client = self._client()
        try:
            unknown = client.post(
                "/api/password/forgot/send-code", json={"email": "ghost@example.com"}
            )
        finally:
            client.close()
        self.assertEqual(unknown.status_code, 200, unknown.text)
        self.assertEqual(unknown.json()["ok"], True)
        self.assertIn("resend_after", unknown.json())
        self.assertEqual(self.sent, [])
        with closing(connect_auth()) as connection:
            codes = connection.execute(
                "SELECT COUNT(*) FROM registration_email_codes WHERE purpose = 'reset'"
            ).fetchone()[0]
        self.assertEqual(codes, 0)

    def test_code_purpose_cannot_cross_between_flows(self) -> None:
        create_user("Dana", "password-1", email="dana@example.com")
        client = self._client()
        try:
            sent = client.post("/api/register/send-code", json={"email": "dana@example.com"})
            self.assertEqual(sent.status_code, 200, sent.text)
            registration_code = self._code_from_last_mail()
            rejected = client.post("/api/password/forgot/reset", json={
                "email": "dana@example.com", "code": registration_code,
                "password": "new-password-2",
            })
        finally:
            client.close()
        self.assertEqual(rejected.status_code, 400, rejected.text)
        with self.assertRaisesRegex(ValueError, "用户名或密码错误"):
            auth_login("dana@example.com", "new-password-2")

    def test_email_change_requires_password_and_verified_code(self) -> None:
        user = create_user("Eve", "password-1", email="eve@example.com")
        token = create_session(int(user["id"]))
        client = self._client()
        try:
            sent = client.post(
                "/api/account/email/send-code", json={"email": "eve.new@example.com"},
                cookies={"forge_session": token},
            )
            self.assertEqual(sent.status_code, 200, sent.text)
            code = self._code_from_last_mail()
            wrong_password = client.post("/api/account/email", json={
                "email": "eve.new@example.com", "code": code, "password": "not-the-password",
            }, cookies={"forge_session": token})
            changed = client.post("/api/account/email", json={
                "email": "eve.new@example.com", "code": code, "password": "password-1",
            }, cookies={"forge_session": token})
        finally:
            client.close()

        self.assertEqual(wrong_password.status_code, 400, wrong_password.text)
        self.assertEqual(wrong_password.json()["error_category"], "password_mismatch")
        self.assertEqual(changed.status_code, 201, changed.text)
        self.assertEqual(changed.json()["email"], "eve.new@example.com")
        self.assertEqual(auth_login("eve.new@example.com", "password-1")["id"], user["id"])
        with self.assertRaisesRegex(ValueError, "用户名或密码错误"):
            auth_login("eve@example.com", "password-1")
        self.assertEqual(auth_login("Eve", "password-1")["id"], user["id"])

    def test_email_change_rejects_address_owned_by_another_account(self) -> None:
        create_user("Frank", "password-1", email="frank@example.com")
        create_user("Grace", "password-1", email="grace@example.com")
        client = self._client()
        try:
            login = client.post("/api/login", json={"username": "Frank", "password": "password-1"})
            self.assertEqual(login.status_code, 201, login.text)
            taken = client.post(
                "/api/account/email/send-code", json={"email": "grace@example.com"}
            )
        finally:
            client.close()
        self.assertEqual(taken.status_code, 409, taken.text)
        self.assertEqual(taken.json()["error_category"], "email_taken")

    def test_two_users_requesting_the_same_new_address_keep_their_own_codes(self) -> None:
        first = create_user("Henry", "password-1", email="henry@example.com")
        second = create_user("Ivy", "password-1", email="ivy@example.com")
        target = "shared-target@example.com"

        class Clock:
            now = 1_800_000_000

        clock = Clock()
        with patch("interview_forge.services.registration.time.time",
                   side_effect=lambda: clock.now):
            registration.send_email_change_code(int(first["id"]), target, "203.0.113.20")
            first_code = self._code_from_last_mail()
            clock.now += 61
            registration.send_email_change_code(int(second["id"]), target, "203.0.113.21")
            second_code = self._code_from_last_mail()
            clock.now += 1
            changed = registration.confirm_email_change(
                int(first["id"]), target, first_code, "password-1", "203.0.113.20"
            )
            with self.assertRaises(registration.RegistrationError) as conflict:
                registration.confirm_email_change(
                    int(second["id"]), target, second_code, "password-1", "203.0.113.21"
                )
        self.assertEqual(changed["email"], target)
        self.assertEqual(conflict.exception.status, 409)
        self.assertEqual(conflict.exception.category, "email_taken")
        self.assertEqual(auth_login(target, "password-1")["id"], first["id"])

    def test_search_rate_limit_never_opens_the_auth_database(self) -> None:
        with patch.dict(os.environ, {
            "IF_SEARCH_RATE_PER_MINUTE": "2",
            "IF_SEARCH_RATE_PER_DAY": "100",
            "IF_SEARCH_GLOBAL_PER_MINUTE": "1000",
        }, clear=False), patch(
            "interview_forge.services.registration.connect_auth",
            side_effect=AssertionError("search must not touch auth.db"),
        ):
            registration.public_search_rate_limit("203.0.113.5")
            registration.public_search_rate_limit("203.0.113.5")
            with self.assertRaises(PublicRateLimitError) as limited:
                registration.public_search_rate_limit("203.0.113.5")
        self.assertEqual(limited.exception.status, 429)
        self.assertGreaterEqual(limited.exception.retry_after, 1)

    def test_registration_send_is_bucketed_by_recipient_domain(self) -> None:
        with patch.dict(os.environ, {
            "IF_REGISTER_DOMAIN_HOURLY_LIMIT": "2",
            "IF_REGISTER_DOMAIN_DAILY_LIMIT": "100",
        }, clear=False):
            registration.send_registration_code("one@shared.example", "203.0.113.9")
            registration.send_registration_code("two@shared.example", "203.0.113.10")
            with self.assertRaises(PublicRateLimitError) as limited:
                registration.send_registration_code("three@shared.example", "203.0.113.11")
        self.assertEqual(limited.exception.status, 429)
        # A different recipient domain still has its own budget.
        registration.send_registration_code("four@other.example", "203.0.113.12")
        self.assertEqual(len(self.sent), 3)

    def test_turnstile_is_enforced_only_when_configured(self) -> None:
        with patch.dict(os.environ, {
            "IF_TURNSTILE_SITE_KEY": "site-key",
            "IF_TURNSTILE_SECRET": "secret-key",
        }, clear=False):
            client = self._client()
            try:
                missing = client.post(
                    "/api/register/send-code", json={"email": "captcha@example.com"}
                )
                with patch(
                    "interview_forge.services.registration.urllib.request.urlopen",
                    _FakeUrlopen({"success": True}),
                ):
                    accepted = client.post("/api/register/send-code", json={
                        "email": "captcha@example.com", "captcha": "solved-token",
                    })
                with patch(
                    "interview_forge.services.registration.urllib.request.urlopen",
                    _FakeUrlopen({"success": False}),
                ):
                    rejected = client.post("/api/register/send-code", json={
                        "email": "captcha2@example.com", "captcha": "bad-token",
                    })
                config = client.get("/api/register/config")
            finally:
                client.close()
        self.assertEqual(missing.status_code, 400, missing.text)
        self.assertEqual(missing.json()["error_category"], "captcha_required")
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertEqual(rejected.json()["error_category"], "captcha_failed")
        self.assertEqual(config.json()["captcha"]["site_key"], "site-key")

    def test_wrong_method_is_reported_as_405_not_401(self) -> None:
        client = self._client()
        try:
            wrong_method = client.get("/api/register")
            public_wrong_method = client.post("/api/catalog", json={})
            private = client.get("/api/me")
        finally:
            client.close()
        self.assertEqual(wrong_method.status_code, 405, wrong_method.text)
        self.assertIn("POST", wrong_method.headers.get("allow", ""))
        self.assertEqual(public_wrong_method.status_code, 405, public_wrong_method.text)
        self.assertEqual(private.status_code, 401)

    def test_public_surface_single_source_matches_routes_and_allowlist(self) -> None:
        from interview_forge.core.public_api import PUBLIC_API_OPERATIONS

        routes = {
            (method, route.path)
            for route in app.routes
            if isinstance(route, APIRoute) and route.path.startswith("/api/")
            for method in route.methods
        }
        for operation in PUBLIC_API_OPERATIONS:
            with self.subTest(operation=operation):
                self.assertIn(operation, routes)
                self.assertIn(operation[1], PUBLIC_FILES)
        for page in ("/pages/login.html", "/pages/register.html",
                     "/pages/forgot-password.html", "/pages/account.html"):
            self.assertIn(page, PUBLIC_FILES)

    def test_idn_domains_are_normalized_and_non_ascii_local_parts_rejected(self) -> None:
        self.assertEqual(normalize_email("User@例子.中国"), "user@xn--fsqu00a.xn--fiqs8s")
        with self.assertRaises(registration.RegistrationError):
            normalize_email("用户@example.com")
        with self.assertRaises(registration.RegistrationError):
            normalize_email("user@例子.中国".replace("例子.中国", "ex..com"))

    def test_integrity_error_is_attributed_to_the_violated_column(self) -> None:
        from interview_forge.services.auth import _unique_violation_message

        self.assertEqual(
            _unique_violation_message(
                sqlite3.IntegrityError("UNIQUE constraint failed: users.email"), "a@b.c"
            ),
            "该邮箱已注册",
        )
        self.assertEqual(
            _unique_violation_message(
                sqlite3.IntegrityError("UNIQUE constraint failed: users.username"), "a@b.c"
            ),
            "用户名已被占用",
        )

    def test_pages_wire_code_length_aria_and_shared_asset_versions(self) -> None:
        from scripts.build import build_html_site

        root = Path(__file__).resolve().parents[1]
        register_page = (root / "pages" / "register.html").read_text(encoding="utf-8")
        self.assertIn('maxlength="6"', register_page)
        self.assertIn('pattern="[0-9]{6}"', register_page)
        self.assertIn('aria-describedby="emailHint"', register_page)
        self.assertNotIn("registered=1", (root / "pages" / "login.html").read_text(encoding="utf-8"))
        self.assertIn("用户名或邮箱", (root / "pages" / "login.html").read_text(encoding="utf-8"))
        for page in ("register.html", "forgot-password.html", "account.html"):
            markup = (root / "pages" / page).read_text(encoding="utf-8")
            match = re.search(r"register-flow\.js\?v=([0-9]+)", markup)
            self.assertIsNotNone(match, page)
            self.assertEqual(match.group(1), build_html_site.SHARED_ASSET_VERSIONS["register-flow.js"])


if __name__ == "__main__":
    unittest.main()