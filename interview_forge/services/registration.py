"""Public registration, email verification, and guest API rate limiting.

Verification codes carry an explicit purpose (``register``, ``reset``,
``email_change``) so one flow's pending code can never be redeemed by another.
Quota reservations are committed with ``BEGIN IMMEDIATE`` before SMTP work so
concurrent workers serialize without holding a database transaction during a
network call.  Failed deliveries remain in the attempt ledger and therefore
consume the same limits as successful sends.

Anonymous search limits live in process memory: search must never queue behind
an authentication-database write lock, and losing those counters on restart is
harmless.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import math
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, suppress
from dataclasses import dataclass

from interview_forge.core.runtime import server_runtime
from interview_forge.services.auth import (
    connect_auth,
    create_user,
    hash_password,
    user_db_path,
    verify_password,
)

_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
_CODE_RE = re.compile(r"^[0-9]{6}$")
_CODE_PURPOSES = frozenset({"register", "reset", "email_change"})

# SMTP delivery is slow and can stall on TLS; never occupy the default
# asyncio executor (which also runs logging and database work) with it.
registration_email_executor = ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="registration-email"
)


class RegistrationError(Exception):
    def __init__(self, message: str, status: int = 400, *, category: str = "registration",
                 retry_after: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = int(status)
        self.category = category
        self.retry_after = retry_after


class PublicRateLimitError(RegistrationError):
    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message, 429, category="rate_limited", retry_after=max(1, int(retry_after)))


@dataclass(frozen=True)
class RegistrationPolicy:
    email_cooldown: int
    ip_hourly: int
    ip_daily: int
    email_hourly: int
    email_daily: int
    domain_hourly: int
    domain_daily: int
    global_hourly: int
    global_daily: int
    verify_ip_hourly: int
    verify_ip_daily: int
    verify_global_hourly: int
    verify_global_daily: int
    code_ttl: int
    code_attempts: int

    @classmethod
    def from_environment(cls) -> RegistrationPolicy:
        def integer(name: str, default: int, minimum: int, maximum: int) -> int:
            try:
                value = int(os.environ.get(name, str(default)))
            except ValueError:
                value = default
            return max(minimum, min(maximum, value))

        return cls(
            email_cooldown=integer("IF_REGISTER_EMAIL_COOLDOWN_SECONDS", 60, 1, 3600),
            ip_hourly=integer("IF_REGISTER_IP_HOURLY_LIMIT", 5, 1, 1000),
            ip_daily=integer("IF_REGISTER_IP_DAILY_LIMIT", 10, 1, 5000),
            email_hourly=integer("IF_REGISTER_EMAIL_HOURLY_LIMIT", 3, 1, 100),
            email_daily=integer("IF_REGISTER_EMAIL_DAILY_LIMIT", 5, 1, 500),
            domain_hourly=integer("IF_REGISTER_DOMAIN_HOURLY_LIMIT", 20, 1, 10000),
            domain_daily=integer("IF_REGISTER_DOMAIN_DAILY_LIMIT", 60, 1, 50000),
            global_hourly=integer("IF_REGISTER_GLOBAL_HOURLY_LIMIT", 100, 1, 10000),
            global_daily=integer("IF_REGISTER_GLOBAL_DAILY_LIMIT", 300, 1, 50000),
            verify_ip_hourly=integer("IF_REGISTER_VERIFY_IP_HOURLY_LIMIT", 20, 1, 10000),
            verify_ip_daily=integer("IF_REGISTER_VERIFY_IP_DAILY_LIMIT", 60, 1, 50000),
            verify_global_hourly=integer("IF_REGISTER_VERIFY_GLOBAL_HOURLY_LIMIT", 500, 1, 100000),
            verify_global_daily=integer("IF_REGISTER_VERIFY_GLOBAL_DAILY_LIMIT", 5000, 1, 500000),
            code_ttl=integer("IF_REGISTER_CODE_TTL_SECONDS", 600, 60, 1800),
            code_attempts=integer("IF_REGISTER_CODE_MAX_ATTEMPTS", 5, 1, 10),
        )


def normalize_email(value: object) -> str:
    """Normalize and validate an address, converting IDN domains to punycode."""
    email = str(value or "").strip().lower()
    if len(email) > 254 or not _EMAIL_RE.fullmatch(email):
        idn = _punycode_domain(email)
        if idn is None:
            raise RegistrationError("邮箱格式不正确")
        email = idn
        if len(email) > 254 or not _EMAIL_RE.fullmatch(email):
            raise RegistrationError("邮箱格式不正确")
    local, domain = email.rsplit("@", 1)
    if ".." in local or local.startswith(".") or local.endswith(".") or ".." in domain:
        raise RegistrationError("邮箱格式不正确")
    return email


def _punycode_domain(email: str) -> str | None:
    """Return the ASCII form of a non-ASCII domain, or ``None`` if unusable.

    Only the domain is converted; a non-ASCII local part is rejected because
    mail servers disagree about its wire encoding (SMTPUTF8 is not universal).
    """
    local, separator, domain = email.partition("@")
    if not separator or not local.isascii() or not domain:
        return None
    try:
        ascii_domain = domain.encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        return None
    return f"{local}@{ascii_domain}"


def _digest(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}:{value}".encode()).hexdigest()


def _captcha_settings() -> tuple[str, str]:
    """A partially configured anti-abuse check must never become optional."""
    site_key = os.environ.get("IF_TURNSTILE_SITE_KEY", "").strip()
    secret = os.environ.get("IF_TURNSTILE_SECRET", "").strip()
    if bool(site_key) != bool(secret):
        raise RegistrationError(
            "人机验证暂不可用，验证码发送已暂停，请稍后重试。",
            503, category="captcha_unavailable",
        )
    return site_key, secret


def captcha_config() -> dict[str, object] | None:
    """Describe the configured bot check, if any, for the public pages.

    Cloudflare Turnstile is optional so a self-hosted deployment keeps working
    without an external service; setting both the site key and secret enables
    an anonymous proof-of-human before any email is sent.
    """
    site_key, secret = _captcha_settings()
    if not secret:
        return None
    return {"provider": "turnstile", "site_key": site_key}


def verify_captcha(token: object, ip: str) -> None:
    """Validate an optional Turnstile token before spending SMTP quota."""
    _site_key, secret = _captcha_settings()
    if not secret:
        return
    token = str(token or "").strip()
    if not token:
        raise RegistrationError("请先完成人机验证", 400, category="captcha_required")
    if len(token) > 4096:
        raise RegistrationError("人机验证失败，请刷新页面后重试", 400, category="captcha_failed")
    fields = {"secret": secret, "response": token}
    try:
        fields["remoteip"] = str(ipaddress.ip_address(str(ip or "").strip()))
    except ValueError:
        pass
    payload = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read(16384)
        result = json.loads(body.decode("utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise RegistrationError(
            "人机验证暂时不可用，请稍后重试", 503, category="captcha_unavailable"
        ) from exc
    if not isinstance(result, dict) or result.get("success") is not True:
        raise RegistrationError("人机验证失败，请刷新页面后重试", 400, category="captcha_failed")


def _code_digest(code: str, salt: bytes) -> str:
    return hashlib.scrypt(
        code.encode("ascii"), salt=salt, n=1 << 14, r=8, p=1, dklen=32
    ).hex()


def _strict_username_password(username: object, password: object) -> tuple[str, str]:
    username = str(username or "").strip()
    password = str(password or "")
    if not server_runtime.USERNAME_RE.fullmatch(username):
        raise RegistrationError("用户名限 2~32 位字母数字下划线连字符")
    reserved_admin = str(server_runtime.PERMANENT_ADMIN_USERNAME or "").strip()
    if reserved_admin and username.casefold() == reserved_admin.casefold():
        raise RegistrationError(
            "该用户名不可用", 409, category="already_registered"
        )
    if len(password) < 8:
        raise RegistrationError("密码至少 8 位")
    if len(password) > 256:
        raise RegistrationError("密码不能超过 256 位")
    return username, password


def _retry_from_oldest(connection: sqlite3.Connection, sql: str, params: tuple[object, ...],
                       window: int, now: int) -> int:
    row = connection.execute(sql, params).fetchone()
    oldest = int(row[0]) if row and row[0] is not None else now
    return max(1, math.ceil(window - (now - oldest)))


def _reserve_registration_send(email: str, ip: str, now: int | None = None,
                               purpose: str = "register") -> tuple[int, RegistrationPolicy]:
    """Charge every send bucket and reserve a delivery attempt.

    Counters are scoped by purpose so a password-reset code request cannot
    consume registration quota (or vice versa), and by recipient domain so one
    domain's share of the global SMTP budget cannot be exhausted by a single
    attacker targeting that provider.
    """
    if purpose not in _CODE_PURPOSES:
        raise ValueError("unsupported verification purpose")
    policy = RegistrationPolicy.from_environment()
    now = int(time.time()) if now is None else int(now)
    hour_cutoff = now - 3600
    day_cutoff = now - 86400
    email_hash = _digest("email", email)
    ip_hash = _digest("ip", ip or "unknown")
    domain_hash = _digest("domain", email.rsplit("@", 1)[-1])

    with closing(connect_auth()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            cutoff = now - 7 * 86400
            connection.execute(
                "DELETE FROM registration_email_codes WHERE send_attempt_id IN "
                "(SELECT id FROM registration_send_attempts WHERE requested_at < ?)",
                (cutoff,),
            )
            connection.execute(
                "DELETE FROM registration_send_attempts WHERE requested_at < ?",
                (cutoff,),
            )
            latest = connection.execute(
                "SELECT COALESCE(completed_at, requested_at) FROM registration_send_attempts "
                "WHERE email_hash = ? AND purpose = ? ORDER BY requested_at DESC LIMIT 1",
                (email_hash, purpose),
            ).fetchone()
            if latest is not None:
                retry_after = policy.email_cooldown - (now - int(latest[0]))
                if retry_after > 0:
                    raise PublicRateLimitError("验证码发送过于频繁，请稍后再试", retry_after)

            def bucket(column: str, subject: str, window_sql: str):
                count_sql = (
                    "SELECT COUNT(*) FROM registration_send_attempts "
                    f"WHERE {column} = ? AND purpose = ? AND requested_at >= ?"
                )
                oldest_sql = (
                    "SELECT MIN(requested_at) FROM registration_send_attempts "
                    f"WHERE {column} = ? AND purpose = ? AND requested_at >= ?"
                )
                return count_sql, (subject, purpose, window_sql), oldest_sql

            ip_hour_count, ip_hour_params, ip_hour_oldest = bucket("ip_hash", ip_hash, hour_cutoff)
            ip_day_count, ip_day_params, ip_day_oldest = bucket("ip_hash", ip_hash, day_cutoff)
            email_hour_count, email_hour_params, email_hour_oldest = bucket("email_hash", email_hash, hour_cutoff)
            email_day_count, email_day_params, email_day_oldest = bucket("email_hash", email_hash, day_cutoff)
            domain_hour_count, domain_hour_params, domain_hour_oldest = bucket("domain_hash", domain_hash, hour_cutoff)
            domain_day_count, domain_day_params, domain_day_oldest = bucket("domain_hash", domain_hash, day_cutoff)
            global_hour_count = (
                "SELECT COUNT(*) FROM registration_send_attempts WHERE purpose = ? AND requested_at >= ?"
            )
            global_hour_params = (purpose, hour_cutoff)
            global_hour_oldest = (
                "SELECT MIN(requested_at) FROM registration_send_attempts WHERE purpose = ? AND requested_at >= ?"
            )
            global_day_count = (
                "SELECT COUNT(*) FROM registration_send_attempts WHERE purpose = ? AND requested_at >= ?"
            )
            global_day_params = (purpose, day_cutoff)
            global_day_oldest = (
                "SELECT MIN(requested_at) FROM registration_send_attempts WHERE purpose = ? AND requested_at >= ?"
            )

            checks = (
                ("IP 小时发送次数过多，请稍后再试",
                 ip_hour_count, ip_hour_params, policy.ip_hourly, 3600, ip_hour_oldest),
                ("IP 当日发送次数过多，请明天再试",
                 ip_day_count, ip_day_params, policy.ip_daily, 86400, ip_day_oldest),
                ("该邮箱发送次数过多，请稍后再试",
                 email_hour_count, email_hour_params, policy.email_hourly, 3600, email_hour_oldest),
                ("该邮箱当日发送次数过多，请明天再试",
                 email_day_count, email_day_params, policy.email_daily, 86400, email_day_oldest),
                ("该邮箱所属邮件服务收信压力过大，请稍后再试",
                 domain_hour_count, domain_hour_params, policy.domain_hourly, 3600, domain_hour_oldest),
                ("该邮箱所属邮件服务今日收信额度已满，请明天再试",
                 domain_day_count, domain_day_params, policy.domain_daily, 86400, domain_day_oldest),
                ("注册邮件服务繁忙，请稍后再试",
                 global_hour_count, global_hour_params, policy.global_hourly, 3600, global_hour_oldest),
                ("注册邮件服务当日额度已用完，请明天再试",
                 global_day_count, global_day_params, policy.global_daily, 86400, global_day_oldest),
            )
            for message, count_sql, params, limit, window, oldest_sql in checks:
                count = int(connection.execute(count_sql, params).fetchone()[0])
                if count >= limit:
                    retry_after = _retry_from_oldest(connection, oldest_sql, params, window, now)
                    raise PublicRateLimitError(message, retry_after)

            cursor = connection.execute(
                "INSERT INTO registration_send_attempts"
                "(ip_hash, email_hash, domain_hash, purpose, requested_at, status) "
                "VALUES (?, ?, ?, ?, ?, 'reserved')",
                (ip_hash, email_hash, domain_hash, purpose, now),
            )
            attempt_id = int(cursor.lastrowid)
            connection.execute("COMMIT")
            return attempt_id, policy
        except BaseException:
            if connection.in_transaction:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise


def _invalidate_attempt_code(attempt_id: int, category: str, now: int | None = None) -> None:
    completed = int(time.time()) if now is None else int(now)
    with closing(connect_auth()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                "UPDATE registration_email_codes SET status = 'invalidated', invalidated_at = ? "
                "WHERE send_attempt_id = ? AND status = 'pending'",
                (completed, attempt_id),
            )
            connection.execute(
                "UPDATE registration_send_attempts SET status = 'failed', completed_at = ?, "
                "failure_category = ? WHERE id = ?",
                (completed, category[:64], attempt_id),
            )
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise


def _activate_attempt_code(attempt_id: int, now: int | None = None) -> None:
    completed = int(time.time()) if now is None else int(now)
    with closing(connect_auth()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            cursor = connection.execute(
                "UPDATE registration_email_codes SET status = 'active' "
                "WHERE send_attempt_id = ? AND status = 'pending' AND expires_at > ?",
                (attempt_id, completed),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("verification code activation failed")
            connection.execute(
                "UPDATE registration_send_attempts SET status = 'sent', completed_at = ? WHERE id = ?",
                (completed, attempt_id),
            )
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise


_PURPOSE_MESSAGES = {
    "register": (
        "【InterviewForge】注册邮箱验证码",
        "你正在注册 InterviewForge。",
        "如果这不是你本人操作，请忽略这封邮件。",
    ),
    "reset": (
        "【InterviewForge】重置密码验证码",
        "你正在重置 InterviewForge 账号的登录密码。",
        "如果这不是你本人操作，请忽略这封邮件；若担心账号安全，请及时修改密码。",
    ),
    "email_change": (
        "【InterviewForge】绑定新邮箱验证码",
        "你正在为 InterviewForge 账号绑定这个邮箱。",
        "如果这不是你本人操作，请忽略这封邮件，你的账号不会有任何变化。",
    ),
}


def _send_verification_code(email_value: object, ip: str, *, purpose: str,
                            user_id: int | None = None) -> dict[str, int | bool]:
    """Reserve limits, persist only a salted hash, then deliver the code."""
    email = normalize_email(email_value)
    if purpose not in _CODE_PURPOSES:
        raise ValueError("unsupported verification purpose")
    now = int(time.time())
    attempt_id, policy = _reserve_registration_send(email, str(ip or "unknown"), now, purpose)
    code = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_bytes(16)
    expires_at = now + policy.code_ttl
    from interview_forge.services import gym

    try:
        with closing(connect_auth()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "UPDATE registration_email_codes SET status = 'invalidated', invalidated_at = ? "
                    "WHERE email = ? COLLATE NOCASE AND purpose = ? "
                    "AND IFNULL(user_id, 0) = ? AND status IN ('pending', 'active')",
                    (now, email, purpose, int(user_id or 0)),
                )
                connection.execute(
                    "INSERT INTO registration_email_codes"
                    "(email, code_hash, code_salt, status, created_at, expires_at, send_attempt_id, purpose, user_id) "
                    "VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?)",
                    (email, _code_digest(code, salt), salt.hex(), now, expires_at, attempt_id,
                     purpose, user_id),
                )
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    with suppress(sqlite3.Error):
                        connection.execute("ROLLBACK")
                raise
    except Exception as exc:
        with suppress(Exception):
            _invalidate_attempt_code(attempt_id, "code_storage_failed")
        raise RegistrationError(
            "验证码暂时无法生成，请稍后重试",
            503,
            category="registration_storage_failed",
        ) from exc

    try:
        subject, intro, footer = _PURPOSE_MESSAGES[purpose]
        body = (
            f"{intro}\n\n"
            f"验证码：{code}\n"
            f"有效期：{policy.code_ttl // 60} 分钟。\n"
            f"同一验证码最多尝试 {policy.code_attempts} 次，使用一次后立即失效。\n\n"
            f"{footer}"
        )
        gym.send_email(email, subject, body)
        _activate_attempt_code(attempt_id)
    except gym.SMTPNotConfiguredError as exc:
        _invalidate_attempt_code(attempt_id, "email_not_configured")
        raise RegistrationError(
            "注册邮件服务尚未配置，请联系站内管理员完成 SMTP 设置",
            503,
            category="email_not_configured",
        ) from exc
    except RegistrationError:
        raise
    except Exception as exc:
        with suppress(Exception):
            _invalidate_attempt_code(attempt_id, "email_delivery_failed")
        raise RegistrationError(
            "验证码邮件发送失败，请稍后重试",
            503,
            category="email_delivery_failed",
        ) from exc

    return {"ok": True, "resend_after": policy.email_cooldown, "expires_in": policy.code_ttl}


def send_registration_code(email_value: object, ip: str) -> dict[str, int | bool]:
    """Send a code that only the public registration endpoint may redeem."""
    return _send_verification_code(email_value, ip, purpose="register")


def _active_user_by_email(email: str) -> sqlite3.Row | None:
    with closing(connect_auth()) as connection:
        return connection.execute(
            "SELECT id, username FROM users WHERE email = ? COLLATE NOCASE AND is_active = 1 LIMIT 1",
            (email,),
        ).fetchone()


def send_password_reset_code(email_value: object, ip: str) -> dict[str, int | bool]:
    """Send a reset code without revealing whether the address is registered.

    Unknown addresses still consume their own send buckets (and never get a
    code row), so the response cannot be used to enumerate accounts and the
    endpoint cannot be driven as an unbounded probe.
    """
    email = normalize_email(email_value)
    policy = RegistrationPolicy.from_environment()
    user = _active_user_by_email(email)
    if user is None:
        _reserve_registration_send(email, str(ip or "unknown"), purpose="reset")
        return {"ok": True, "resend_after": policy.email_cooldown, "expires_in": policy.code_ttl}
    return _send_verification_code(email, ip, purpose="reset", user_id=int(user["id"]))


def send_email_change_code(user_id: int, email_value: object, ip: str) -> dict[str, int | bool]:
    """Send a code proving ownership of a new address for an authenticated user."""
    email = normalize_email(email_value)
    with closing(connect_auth()) as connection:
        user = connection.execute(
            "SELECT id, COALESCE(email, '') AS email FROM users WHERE id = ? AND is_active = 1",
            (int(user_id),),
        ).fetchone()
        if user is None:
            raise RegistrationError("登录状态已失效，请重新登录", 401, category="unauthorized")
        if email == str(user["email"] or "").lower():
            raise RegistrationError("新邮箱与当前绑定邮箱相同", 400, category="email_unchanged")
        taken = connection.execute(
            "SELECT 1 FROM users WHERE email = ? COLLATE NOCASE AND id <> ? LIMIT 1",
            (email, int(user_id)),
        ).fetchone()
        if taken is not None:
            raise RegistrationError("该邮箱已被其他账号使用", 409, category="email_taken")
    return _send_verification_code(email, ip, purpose="email_change", user_id=int(user_id))


@dataclass(frozen=True)
class _CodeCheck:
    row: sqlite3.Row | None = None
    error: RegistrationError | None = None
    persist: bool = False


def _check_active_code(connection: sqlite3.Connection, *, email: str, purpose: str, code: str,
                       policy: RegistrationPolicy, now: int, user_id: int | None = None) -> _CodeCheck:
    """Verify one purpose-scoped code inside the caller's transaction.

    A failed attempt never commits the caller's business writes; the caller
    decides whether the attempt-count/invalidation update must be persisted
    before raising (``persist``).
    """
    sql = (
        "SELECT id, code_hash, code_salt, attempts, expires_at, user_id "
        "FROM registration_email_codes "
        "WHERE email = ? COLLATE NOCASE AND purpose = ? AND status = 'active'"
    )
    params: list[object] = [email, purpose]
    if user_id is not None:
        sql += " AND user_id = ?"
        params.append(int(user_id))
    row = connection.execute(sql + " ORDER BY id DESC LIMIT 1", tuple(params)).fetchone()
    if row is None:
        return _CodeCheck(error=RegistrationError("验证码无效或已过期"))
    if user_id is not None and (row["user_id"] is None or int(row["user_id"]) != int(user_id)):
        return _CodeCheck(error=RegistrationError("验证码无效或已过期"))
    if int(row["expires_at"]) <= now:
        connection.execute(
            "UPDATE registration_email_codes SET status = 'invalidated', invalidated_at = ? WHERE id = ?",
            (now, int(row["id"])),
        )
        return _CodeCheck(error=RegistrationError("验证码已过期，请重新获取"), persist=True)
    if int(row["attempts"]) >= policy.code_attempts:
        connection.execute(
            "UPDATE registration_email_codes SET status = 'invalidated', invalidated_at = ? WHERE id = ?",
            (now, int(row["id"])),
        )
        return _CodeCheck(error=RegistrationError("验证码尝试次数过多，请重新获取"), persist=True)

    actual = _code_digest(code, bytes.fromhex(str(row["code_salt"])))
    if not hmac.compare_digest(actual, str(row["code_hash"])):
        attempts = int(row["attempts"]) + 1
        exhausted = attempts >= policy.code_attempts
        connection.execute(
            "UPDATE registration_email_codes SET attempts = ?, status = ? WHERE id = ?",
            (attempts, "invalidated" if exhausted else "active", int(row["id"])),
        )
        if exhausted:
            connection.execute(
                "UPDATE registration_email_codes SET invalidated_at = ? WHERE id = ?",
                (now, int(row["id"])),
            )
            return _CodeCheck(
                error=RegistrationError("验证码尝试次数过多，请重新获取"), persist=True
            )
        remaining = policy.code_attempts - attempts
        return _CodeCheck(
            error=RegistrationError(f"验证码错误，还可尝试 {remaining} 次"), persist=True
        )
    return _CodeCheck(row=row)


def _consume_code(connection: sqlite3.Connection, code_id: int, now: int) -> None:
    consumed = connection.execute(
        "UPDATE registration_email_codes SET status = 'consumed', consumed_at = ? "
        "WHERE id = ? AND status = 'active'",
        (now, code_id),
    )
    if consumed.rowcount != 1:
        raise RegistrationError("验证码已被使用，请重新获取")


def register_with_email_code(email_value: object, username_value: object, password_value: object,
                             code_value: object, ip: str = "unknown") -> dict[str, object]:
    email = normalize_email(email_value)
    username, password = _strict_username_password(username_value, password_value)
    code = str(code_value or "").strip()
    if not _CODE_RE.fullmatch(code):
        raise RegistrationError("验证码应为 6 位数字")
    policy = RegistrationPolicy.from_environment()
    now = int(time.time())
    registration_verify_rate_limit(ip, now=now)

    with closing(connect_auth()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            check = _check_active_code(
                connection, email=email, purpose="register", code=code, policy=policy, now=now,
            )
            if check.error is not None:
                if check.persist:
                    connection.execute("COMMIT")
                raise check.error
            row = check.row
            if row is None:  # defensive: a successful check always carries its row
                raise RegistrationError("验证码无效或已过期")
            user = create_user(username, password, conn=connection, email=email)
            _consume_code(connection, int(row["id"]), now)
            connection.execute("COMMIT")
        except RegistrationError:
            if connection.in_transaction:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise
        except ValueError as exc:
            if connection.in_transaction:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            if str(exc) in {"该邮箱已注册", "用户名已被占用"}:
                raise RegistrationError(
                    "该邮箱或用户名已被占用", 409, category="already_registered"
                ) from exc
            raise
        except sqlite3.IntegrityError as exc:
            if connection.in_transaction:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise RegistrationError("该邮箱或用户名已被占用", 409, category="already_registered") from exc
        except BaseException:
            if connection.in_transaction:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise

    with closing(server_runtime.connect(user_db_path(str(user["username"])))):
        pass
    return {
        "id": int(user["id"]),
        "username": str(user["username"]),
        "role": str(user["role"]),
    }


def _validate_password(password_value: object) -> str:
    password = str(password_value or "")
    if len(password) < 8:
        raise RegistrationError("密码至少 8 位")
    if len(password) > 256:
        raise RegistrationError("密码不能超过 256 位")
    return password


def _verified_code_row(code_value: object) -> str:
    code = str(code_value or "").strip()
    if not _CODE_RE.fullmatch(code):
        raise RegistrationError("验证码应为 6 位数字")
    return code


def reset_password_with_code(email_value: object, code_value: object, password_value: object,
                             ip: str = "unknown") -> dict[str, object]:
    """Redeem a reset code, rotate the password, and revoke every session."""
    email = normalize_email(email_value)
    password = _validate_password(password_value)
    code = _verified_code_row(code_value)
    policy = RegistrationPolicy.from_environment()
    now = int(time.time())
    registration_verify_rate_limit(ip, now=now)

    with closing(connect_auth()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            check = _check_active_code(
                connection, email=email, purpose="reset", code=code, policy=policy, now=now,
            )
            if check.error is not None:
                if check.persist:
                    connection.execute("COMMIT")
                raise check.error
            row = check.row
            if row is None:
                raise RegistrationError("验证码无效或已过期")
            user = connection.execute(
                "SELECT id FROM users WHERE email = ? COLLATE NOCASE AND is_active = 1 LIMIT 1",
                (email,),
            ).fetchone()
            if user is None:
                # The address was removed after the code was issued.  Do not
                # disclose that difference from an ordinary invalid code.
                connection.execute("COMMIT")
                raise RegistrationError("验证码无效或已过期")
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(password), int(user["id"])),
            )
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (int(user["id"]),))
            _consume_code(connection, int(row["id"]), now)
            connection.execute("COMMIT")
        except RegistrationError:
            if connection.in_transaction:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise
        except sqlite3.Error as exc:
            if connection.in_transaction:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise RegistrationError("密码重置暂时失败，请稍后重试", 503, category="reset_failed") from exc
        except BaseException:
            if connection.in_transaction:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise
    return {"ok": True}


def confirm_email_change(user_id: int, email_value: object, code_value: object, password_value: object,
                         ip: str = "unknown") -> dict[str, object]:
    """Bind a verified address to the signed-in account after a password check."""
    email = normalize_email(email_value)
    code = _verified_code_row(code_value)
    policy = RegistrationPolicy.from_environment()
    now = int(time.time())
    user_id = int(user_id)
    with closing(connect_auth()) as connection:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE id = ? AND is_active = 1", (user_id,)
        ).fetchone()
        if row is None or not verify_password(str(password_value or ""), str(row["password_hash"])):
            raise RegistrationError("密码错误，请重新输入", 400, category="password_mismatch")

    registration_verify_rate_limit(ip, now=now)
    with closing(connect_auth()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            check = _check_active_code(
                connection, email=email, purpose="email_change", code=code, policy=policy,
                now=now, user_id=user_id,
            )
            if check.error is not None:
                if check.persist:
                    connection.execute("COMMIT")
                raise check.error
            active = check.row
            if active is None:
                raise RegistrationError("验证码无效或已过期")
            taken = connection.execute(
                "SELECT 1 FROM users WHERE email = ? COLLATE NOCASE AND id <> ? LIMIT 1",
                (email, user_id),
            ).fetchone()
            if taken is not None:
                connection.execute("COMMIT")
                raise RegistrationError("该邮箱已被其他账号使用", 409, category="email_taken")
            connection.execute("UPDATE users SET email = ? WHERE id = ?", (email, user_id))
            _consume_code(connection, int(active["id"]), now)
            connection.execute("COMMIT")
        except RegistrationError:
            if connection.in_transaction:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise
        except sqlite3.IntegrityError as exc:
            if connection.in_transaction:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise RegistrationError("该邮箱已被其他账号使用", 409, category="email_taken") from exc
        except BaseException:
            if connection.in_transaction:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise
    return {"ok": True, "email": email}


def consume_public_rate_limits(
    buckets: Iterable[tuple[str, str, Iterable[tuple[int, int]]]],
    now: int | None = None,
) -> None:
    """Atomically consume several public rate buckets across processes.

    All checks and inserts share one ``BEGIN IMMEDIATE`` transaction.  That
    prevents a request from being charged to its IP bucket when the global
    bucket has already reached its limit, or vice versa.
    """
    normalized: list[tuple[str, str, tuple[tuple[int, int], ...]]] = []
    for namespace, subject, rules in buckets:
        clean_rules = tuple(sorted({
            (max(1, int(limit)), max(1, int(window)))
            for limit, window in rules
        }))
        if clean_rules:
            normalized.append((str(namespace), str(subject or "unknown"), clean_rules))
    if not normalized:
        return
    current = int(time.time()) if now is None else int(now)
    with closing(connect_auth()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for namespace, _subject, rules in normalized:
                max_window = max(window for _limit, window in rules)
                connection.execute(
                    "DELETE FROM public_rate_events WHERE namespace = ? AND occurred_at < ?",
                    (namespace, current - max_window),
                )
            retry_after = 0
            for namespace, subject, rules in normalized:
                subject_hash = _digest(namespace, subject)
                for limit, window in rules:
                    cutoff = current - window
                    row = connection.execute(
                        "SELECT COUNT(*), MIN(occurred_at) FROM public_rate_events "
                        "WHERE namespace = ? AND subject_hash = ? AND occurred_at >= ?",
                        (namespace, subject_hash, cutoff),
                    ).fetchone()
                    count = int(row[0])
                    if count >= limit:
                        oldest = int(row[1])
                        retry_after = max(
                            retry_after,
                            math.ceil(window - (current - oldest)),
                        )
            if retry_after:
                raise PublicRateLimitError("请求过于频繁，请稍后再试", retry_after)
            for namespace, subject, _rules in normalized:
                connection.execute(
                    "INSERT INTO public_rate_events(namespace, subject_hash, occurred_at) "
                    "VALUES (?, ?, ?)",
                    (namespace, _digest(namespace, subject), current),
                )
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            raise


def consume_public_rate_limit(namespace: str, subject: str,
                              rules: Iterable[tuple[int, int]], now: int | None = None) -> None:
    """Atomically consume one public API rate bucket across processes."""
    consume_public_rate_limits(((namespace, subject, rules),), now=now)


def registration_verify_rate_limit(ip: str, now: int | None = None) -> None:
    """Limit anonymous code checks before a database lookup or scrypt hash."""
    policy = RegistrationPolicy.from_environment()
    consume_public_rate_limits((
        ("register_verify_ip", str(ip or "unknown"), (
            (policy.verify_ip_hourly, 3600),
            (policy.verify_ip_daily, 86400),
        )),
        ("register_verify_global", "all", (
            (policy.verify_global_hourly, 3600),
            (policy.verify_global_daily, 86400),
        )),
    ), now=now)


_SEARCH_EVENTS: dict[str, list[float]] = {}
_SEARCH_GLOBAL: list[float] = []
_SEARCH_LOCK = threading.Lock()
_SEARCH_MAX_SUBJECTS = 4096


def _search_integer(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def public_search_rate_limit(ip: str) -> None:
    """Limit anonymous search in process memory, never in the auth database.

    Search is read-only and must stay available even while the authentication
    database is locked by a registration or session write.  Counters are
    per-process, so a multi-worker deployment allows a small multiple of the
    configured rate; that is an acceptable trade for removing the shared write
    lock, and the total is also capped globally in memory.
    """
    per_minute = _search_integer("IF_SEARCH_RATE_PER_MINUTE", 30)
    per_day = _search_integer("IF_SEARCH_RATE_PER_DAY", 500)
    global_per_minute = _search_integer("IF_SEARCH_GLOBAL_PER_MINUTE", 600)
    now = time.time()
    subject = str(ip or "unknown")
    with _SEARCH_LOCK:
        stamps = [stamp for stamp in _SEARCH_EVENTS.get(subject, ()) if now - stamp < 86400]
        if len(stamps) >= per_day:
            retry_after = math.ceil(86400 - (now - stamps[0]))
            _SEARCH_EVENTS[subject] = stamps
            raise PublicRateLimitError("搜索次数已达上限，请明天再试", retry_after)
        recent = [stamp for stamp in stamps if now - stamp < 60]
        if len(recent) >= per_minute:
            _SEARCH_EVENTS[subject] = stamps
            raise PublicRateLimitError("搜索过于频繁，请稍后再试", math.ceil(60 - (now - recent[0])))
        global_recent = [stamp for stamp in _SEARCH_GLOBAL if now - stamp < 60]
        if len(global_recent) >= global_per_minute:
            _SEARCH_GLOBAL[:] = global_recent
            _SEARCH_EVENTS[subject] = stamps
            raise PublicRateLimitError("搜索服务繁忙，请稍后再试", 60)
        if len(_SEARCH_EVENTS) > _SEARCH_MAX_SUBJECTS:
            for key in [key for key, value in _SEARCH_EVENTS.items() if not value or now - value[-1] >= 86400]:
                _SEARCH_EVENTS.pop(key, None)
        stamps.append(now)
        _SEARCH_EVENTS[subject] = stamps
        _SEARCH_GLOBAL[:] = global_recent + [now]
