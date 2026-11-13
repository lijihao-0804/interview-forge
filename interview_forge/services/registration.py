"""Public registration, email verification, and guest API rate limiting.

Quota reservations are committed with ``BEGIN IMMEDIATE`` before SMTP work so
concurrent workers serialize without holding a database transaction during a
network call.  Failed deliveries remain in the attempt ledger and therefore
consume the same limits as successful sends.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import os
import re
import secrets
import sqlite3
import time
from collections.abc import Iterable
from contextlib import closing, suppress
from dataclasses import dataclass

from interview_forge.core.runtime import server_runtime
from interview_forge.services.auth import connect_auth, create_user, user_db_path

_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
_CODE_RE = re.compile(r"^[0-9]{6}$")


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
    email = str(value or "").strip().lower()
    if len(email) > 254 or not _EMAIL_RE.fullmatch(email):
        raise RegistrationError("邮箱格式不正确")
    local, domain = email.rsplit("@", 1)
    if ".." in local or local.startswith(".") or local.endswith(".") or ".." in domain:
        raise RegistrationError("邮箱格式不正确")
    return email


def _digest(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}:{value}".encode()).hexdigest()


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


def _reserve_registration_send(email: str, ip: str, now: int | None = None) -> tuple[int, RegistrationPolicy]:
    policy = RegistrationPolicy.from_environment()
    now = int(time.time()) if now is None else int(now)
    hour_cutoff = now - 3600
    day_cutoff = now - 86400
    email_hash = _digest("email", email)
    ip_hash = _digest("ip", ip or "unknown")

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
                "WHERE email_hash = ? ORDER BY requested_at DESC LIMIT 1",
                (email_hash,),
            ).fetchone()
            if latest is not None:
                retry_after = policy.email_cooldown - (now - int(latest[0]))
                if retry_after > 0:
                    raise PublicRateLimitError("验证码发送过于频繁，请稍后再试", retry_after)

            checks = (
                ("IP 小时发送次数过多，请稍后再试",
                 "SELECT COUNT(*) FROM registration_send_attempts WHERE ip_hash = ? AND requested_at >= ?",
                 (ip_hash, hour_cutoff), policy.ip_hourly, 3600,
                 "SELECT MIN(requested_at) FROM registration_send_attempts WHERE ip_hash = ? AND requested_at >= ?"),
                ("IP 当日发送次数过多，请明天再试",
                 "SELECT COUNT(*) FROM registration_send_attempts WHERE ip_hash = ? AND requested_at >= ?",
                 (ip_hash, day_cutoff), policy.ip_daily, 86400,
                 "SELECT MIN(requested_at) FROM registration_send_attempts WHERE ip_hash = ? AND requested_at >= ?"),
                ("该邮箱发送次数过多，请稍后再试",
                 "SELECT COUNT(*) FROM registration_send_attempts WHERE email_hash = ? AND requested_at >= ?",
                 (email_hash, hour_cutoff), policy.email_hourly, 3600,
                 "SELECT MIN(requested_at) FROM registration_send_attempts WHERE email_hash = ? AND requested_at >= ?"),
                ("该邮箱当日发送次数过多，请明天再试",
                 "SELECT COUNT(*) FROM registration_send_attempts WHERE email_hash = ? AND requested_at >= ?",
                 (email_hash, day_cutoff), policy.email_daily, 86400,
                 "SELECT MIN(requested_at) FROM registration_send_attempts WHERE email_hash = ? AND requested_at >= ?"),
                ("注册邮件服务繁忙，请稍后再试",
                 "SELECT COUNT(*) FROM registration_send_attempts WHERE requested_at >= ?",
                 (hour_cutoff,), policy.global_hourly, 3600,
                 "SELECT MIN(requested_at) FROM registration_send_attempts WHERE requested_at >= ?"),
                ("注册邮件服务当日额度已用完，请明天再试",
                 "SELECT COUNT(*) FROM registration_send_attempts WHERE requested_at >= ?",
                 (day_cutoff,), policy.global_daily, 86400,
                 "SELECT MIN(requested_at) FROM registration_send_attempts WHERE requested_at >= ?"),
            )
            for message, count_sql, params, limit, window, oldest_sql in checks:
                count = int(connection.execute(count_sql, params).fetchone()[0])
                if count >= limit:
                    retry_after = _retry_from_oldest(connection, oldest_sql, params, window, now)
                    raise PublicRateLimitError(message, retry_after)

            cursor = connection.execute(
                "INSERT INTO registration_send_attempts"
                "(ip_hash, email_hash, requested_at, status) VALUES (?, ?, ?, 'reserved')",
                (ip_hash, email_hash, now),
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


def send_registration_code(email_value: object, ip: str) -> dict[str, int | bool]:
    """Reserve limits, persist only a salted hash, then deliver the code."""
    email = normalize_email(email_value)
    now = int(time.time())
    attempt_id, policy = _reserve_registration_send(email, str(ip or "unknown"), now)
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
                    "WHERE email = ? COLLATE NOCASE AND status IN ('pending', 'active')",
                    (now, email),
                )
                connection.execute(
                    "INSERT INTO registration_email_codes"
                    "(email, code_hash, code_salt, status, created_at, expires_at, send_attempt_id) "
                    "VALUES (?, ?, ?, 'pending', ?, ?, ?)",
                    (email, _code_digest(code, salt), salt.hex(), now, expires_at, attempt_id),
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
        body = (
            "你正在注册 InterviewForge。\n\n"
            f"验证码：{code}\n"
            f"有效期：{policy.code_ttl // 60} 分钟。\n"
            f"同一验证码最多尝试 {policy.code_attempts} 次，使用一次后立即失效。\n\n"
            "如果这不是你本人操作，请忽略这封邮件。"
        )
        gym.send_email(
            email,
            "【InterviewForge】注册邮箱验证码",
            body,
        )
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
            row = connection.execute(
                "SELECT id, code_hash, code_salt, attempts, expires_at FROM registration_email_codes "
                "WHERE email = ? COLLATE NOCASE AND status = 'active' ORDER BY id DESC LIMIT 1",
                (email,),
            ).fetchone()
            if row is None:
                raise RegistrationError("验证码无效或已过期")
            if int(row["expires_at"]) <= now:
                connection.execute(
                    "UPDATE registration_email_codes SET status = 'invalidated', invalidated_at = ? "
                    "WHERE id = ?", (now, int(row["id"]))
                )
                connection.execute("COMMIT")
                raise RegistrationError("验证码已过期，请重新获取")
            if int(row["attempts"]) >= policy.code_attempts:
                connection.execute(
                    "UPDATE registration_email_codes SET status = 'invalidated', invalidated_at = ? "
                    "WHERE id = ?", (now, int(row["id"]))
                )
                connection.execute("COMMIT")
                raise RegistrationError("验证码尝试次数过多，请重新获取")

            expected = str(row["code_hash"])
            actual = _code_digest(code, bytes.fromhex(str(row["code_salt"])))
            if not hmac.compare_digest(actual, expected):
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
                connection.execute("COMMIT")
                if exhausted:
                    raise RegistrationError("验证码尝试次数过多，请重新获取")
                raise RegistrationError(f"验证码错误，还可尝试 {policy.code_attempts - attempts} 次")

            user = create_user(username, password, conn=connection, email=email)
            consumed = connection.execute(
                "UPDATE registration_email_codes SET status = 'consumed', consumed_at = ? "
                "WHERE id = ? AND status = 'active'",
                (now, int(row["id"])),
            )
            if consumed.rowcount != 1:
                raise RegistrationError("验证码已被使用，请重新获取")
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


def public_search_rate_limit(ip: str) -> None:
    def integer(name: str, default: int) -> int:
        try:
            return max(1, int(os.environ.get(name, str(default))))
        except ValueError:
            return default

    consume_public_rate_limit(
        "search",
        str(ip or "unknown"),
        ((integer("IF_SEARCH_RATE_PER_MINUTE", 30), 60),
         (integer("IF_SEARCH_RATE_PER_DAY", 500), 86400)),
    )
