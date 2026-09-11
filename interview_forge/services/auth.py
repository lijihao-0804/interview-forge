"""Authentication, sessions, registration and account administration.

This module owns the account rules while resolving deployment/test state from
the server assembly lazily.  In particular, auth initialization remains a
single process-wide state machine and all existing server symbols are
re-exported by the assembly module.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import unicodedata
from contextlib import closing, suppress
from datetime import datetime, timedelta
from pathlib import Path
from typing import Mapping

from interview_forge.core.paths import DATA_DIR, DB_PATH, USERS_DIR
from interview_forge.core.runtime import server_runtime

_LAST_SEEN_TS: dict[int, float] = {}
_LAST_SEEN_LOCK = threading.Lock()
_LAST_SEEN_INTERVAL = 60.0

_NICKNAME_MAX = 16
_NICKNAME_WORDLIST_PATH = DATA_DIR / "nickname_banned_words.txt"
_NICKNAME_LEET_MAP = str.maketrans({
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "6": "g", "7": "t", "8": "b", "9": "g",
    "@": "a", "$": "s",
})
_NICKNAME_TRADITIONAL_MAP = str.maketrans({
    "爺": "爷", "媽": "妈", "妳": "你", "兒": "儿", "孫": "孙", "腦": "脑", "殘": "残",
    "廢": "废", "東": "东", "畜": "畜",
})
_NICKNAME_REPEAT_RE = re.compile(r"(.)\1+")
_NICKNAME_TARGETED_RE = re.compile(
    r"(?:[\u4e00-\u9fffA-Za-z0-9]{1,12}(?:的|是|叫|当|做|为)|"
    r"(?:我|你|他|她)(?:是|叫|当|做|为)?(?:你|我|他|她)?)"
    r"(?:爹地|爸比|爸爸|爹爹|爹|妈咪|妈妈|妈|爷爷|爷|儿子|孙子|祖宗)"
)
_NICKNAME_FALLBACK_WORDS = (
    "傻逼", "傻比", "傻币", "煞笔", "沙比", "脑残", "弱智", "智障", "垃圾", "废物",
    "狗东西", "狗日", "畜生", "杂种", "贱人", "婊子", "臭婊", "妈的", "他妈", "他妈的",
    "操你妈", "草泥马", "日你妈", "去你妈", "干你娘",
    "shabi", "sabi", "shaibi", "naocan", "ruozhi", "zhizhang", "feiwu", "laji", "goutongxi",
    "zazhong", "jianren", "biaozi", "nima", "nmsl", "cnm", "caonima", "qunima", "ganniang",
    "fuck", "shit", "bitch", "爹地", "爸比", "die", "diedi", "diedie", "baba", "babi", "mami", "yeye", "erzi", "sunzi", "zuzong", "laozi",
)


def _nickname_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", value)).casefold()
    value = value.translate(_NICKNAME_TRADITIONAL_MAP).translate(_NICKNAME_LEET_MAP)
    return "".join(
        ch for ch in value
        if unicodedata.category(ch) != "Mn" and (ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    )


def _nickname_compact_key(value: str) -> str:
    return _NICKNAME_REPEAT_RE.sub(r"\1", _nickname_key(value))


class _NicknameTrie:
    _END = "\0"

    def __init__(self, words: tuple[str, ...]):
        self.root: dict[str, object] = {}
        for word in words:
            node = self.root
            for char in word:
                node = node.setdefault(char, {})  # type: ignore[assignment]
            node[self._END] = word

    def find(self, value: str) -> str:
        for start in range(len(value)):
            node: dict[str, object] = self.root
            for char in value[start:]:
                child = node.get(char)
                if not isinstance(child, dict):
                    break
                node = child
                matched = node.get(self._END)
                if isinstance(matched, str):
                    return matched
        return ""


def _load_nickname_words() -> tuple[str, ...]:
    words = list(_NICKNAME_FALLBACK_WORDS)
    try:
        lines = _NICKNAME_WORDLIST_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        word = line.split("#", 1)[0].strip()
        if word:
            words.append(word)
    normalized = {_nickname_compact_key(word) for word in words}
    normalized.discard("")
    return tuple(sorted(normalized, key=lambda word: (-len(word), word)))


_NICKNAME_BANNED_KEYS = _load_nickname_words()
_NICKNAME_MATCHER = _NicknameTrie(_NICKNAME_BANNED_KEYS)
_NICKNAME_COMPACT_MATCHER = _NicknameTrie(_NICKNAME_BANNED_KEYS)


def validate_nickname(nickname: str) -> str:
    nickname = nickname.strip()
    if not (1 <= len(nickname) <= _NICKNAME_MAX):
        raise ValueError(f"昵称需为 1~{_NICKNAME_MAX} 个字符")
    key = _nickname_key(nickname)
    compact_key = _nickname_compact_key(nickname)
    if _NICKNAME_MATCHER.find(key) or _NICKNAME_COMPACT_MATCHER.find(compact_key):
        raise ValueError("昵称包含不当或攻击性内容，请换一个昵称")
    if _NICKNAME_TARGETED_RE.search(key):
        raise ValueError("昵称包含针对他人的侮辱或疑似谐音变体，请换一个昵称")
    return nickname


def reset_invalid_nicknames(connection: sqlite3.Connection) -> int:
    changed = 0
    rows = connection.execute(
        "SELECT id, username, nickname FROM users WHERE COALESCE(nickname, '') <> ''"
    ).fetchall()
    for row in rows:
        try:
            validate_nickname(str(row["nickname"]))
        except ValueError:
            connection.execute("UPDATE users SET nickname = ? WHERE id = ?", (row["username"], row["id"]))
            changed += 1
    return changed


AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login TEXT,
    ai_daily_limit INTEGER CHECK (ai_daily_limit IS NULL OR (ai_daily_limit >= 0 AND ai_daily_limit <= 100))
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sessions_expiry ON sessions(expires_at);
CREATE TABLE IF NOT EXISTS invite_codes (
    code TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'unused' CHECK (status IN ('unused', 'used', 'revoked')),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    expires_at TEXT,
    used_by INTEGER,
    used_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_invite_status ON invite_codes(status);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,
    username TEXT NOT NULL DEFAULT '',
    contact TEXT NOT NULL DEFAULT '',
    page TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_feedback_status ON feedback(status, id DESC);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS avatars (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    mime TEXT NOT NULL,
    data BLOB NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_quota_reset_audit (
    id INTEGER PRIMARY KEY,
    actor_admin_id INTEGER NOT NULL REFERENCES users(id),
    target_user_id INTEGER NOT NULL REFERENCES users(id),
    reset_at TEXT NOT NULL,
    before_used INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS weather_preferences (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    mode TEXT NOT NULL CHECK (mode IN ('city', 'geolocation')),
    display_name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    timezone TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
"""


def connect_auth() -> sqlite3.Connection:
    runtime = server_runtime
    connection = sqlite3.connect(runtime.AUTH_DB_PATH, timeout=10, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if not runtime._AUTH_READY:
        with runtime._AUTH_LOCK:
            if not runtime._AUTH_READY:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(AUTH_SCHEMA)
                for statement in (
                    "ALTER TABLE users ADD COLUMN nickname TEXT NOT NULL DEFAULT ''",
                    "ALTER TABLE users ADD COLUMN lang TEXT NOT NULL DEFAULT 'java'",
                    "ALTER TABLE users ADD COLUMN last_seen TEXT",
                    "ALTER TABLE users ADD COLUMN ai_daily_limit INTEGER CHECK (ai_daily_limit IS NULL OR (ai_daily_limit >= 0 AND ai_daily_limit <= 100))",
                    "ALTER TABLE feedback ADD COLUMN username TEXT NOT NULL DEFAULT ''",
                ):
                    try:
                        connection.execute(statement)
                    except sqlite3.OperationalError:
                        pass
                reset_invalid_nicknames(connection)
                connection.execute(
                    "UPDATE users SET role = 'admin' WHERE username = ? AND role <> 'admin'",
                    (runtime.PERMANENT_ADMIN_USERNAME,),
                )
                connection.execute("DELETE FROM sessions WHERE expires_at < ?", (runtime.now_iso(),))
                runtime._AUTH_READY = True
    return connection


def business_now() -> datetime:
    return datetime.now(server_runtime.BUSINESS_TZ)


def now_iso() -> str:
    return business_now().isoformat(timespec="seconds")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=1 << 14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                                n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def user_db_path(username: str) -> Path:
    runtime = server_runtime
    if not runtime.USERNAME_RE.match(username):
        raise ValueError("非法用户名")
    return runtime.USERS_DIR / username / "hot100-study.db"


def _username_case_collision(connection: sqlite3.Connection, username: str, *, exclude_user_id: int | None = None) -> bool:
    if exclude_user_id is None:
        row = connection.execute("SELECT id FROM users WHERE username = ? COLLATE NOCASE LIMIT 1", (username,)).fetchone()
    else:
        row = connection.execute(
            "SELECT id FROM users WHERE username = ? COLLATE NOCASE AND id <> ? LIMIT 1",
            (username, exclude_user_id),
        ).fetchone()
    return row is not None


def create_user(username: str, password: str, role: str = "user", conn: sqlite3.Connection | None = None) -> dict[str, object]:
    runtime = server_runtime
    if not runtime.USERNAME_RE.match(username):
        raise ValueError("用户名限 2~32 位字母数字下划线连字符")
    if len(password) < 8:
        raise ValueError("密码至少 8 位")
    if role not in ("admin", "user"):
        raise ValueError("非法角色")
    own_connection = conn is None
    connection = conn or connect_auth()
    started_transaction = False
    try:
        if not connection.in_transaction:
            connection.execute("BEGIN IMMEDIATE")
            started_transaction = True
        if _username_case_collision(connection, username):
            raise ValueError("用户名已被占用")
        connection.execute(
            "INSERT INTO users(username, password_hash, role, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
            (username, hash_password(password), role, runtime.now_iso()),
        )
        row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if started_transaction:
            connection.execute("COMMIT")
        return dict(row)
    except ValueError:
        if started_transaction:
            with suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
        raise
    except sqlite3.IntegrityError as exc:
        if started_transaction:
            with suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
        raise ValueError("用户名已被占用") from exc
    except BaseException:
        if started_transaction:
            with suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
        raise
    finally:
        if own_connection:
            connection.close()


def ensure_admin(username: str, password: str) -> dict[str, object]:
    runtime = server_runtime
    if not runtime.USERNAME_RE.match(username):
        raise ValueError("用户名限 2~32 位字母数字下划线连字符")
    with closing(connect_auth()) as connection:
        row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is not None:
        return dict(row)
    return create_user(username, password, role="admin")


def auth_login(username: str, password: str) -> sqlite3.Row:
    runtime = server_runtime
    with closing(connect_auth()) as connection:
        row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            verify_password(password, runtime._DUMMY_HASH)
            raise ValueError("用户名或密码错误")
        if _username_case_collision(connection, str(row["username"]), exclude_user_id=int(row["id"])):
            verify_password(password, runtime._DUMMY_HASH)
            raise ValueError("用户名或密码错误")
        if int(row["is_active"]) != 1 or not verify_password(password, str(row["password_hash"])):
            raise ValueError("用户名或密码错误")
        connection.execute("UPDATE users SET last_login = ? WHERE id = ?", (runtime.now_iso(), row["id"]))
        connection.execute("UPDATE users SET last_seen = ? WHERE id = ?", (runtime.now_iso(), row["id"]))
        return row


def create_session(user_id: int) -> str:
    runtime = server_runtime
    token = secrets.token_urlsafe(32)
    expires = (business_now() + runtime.SESSION_TTL).isoformat(timespec="seconds")
    with closing(connect_auth()) as connection:
        connection.execute(
            "INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, runtime.now_iso(), expires),
        )
    return token


def destroy_session(token: str) -> None:
    with closing(connect_auth()) as connection:
        connection.execute("DELETE FROM sessions WHERE token = ?", (token,))


def session_user(token: str) -> sqlite3.Row | None:
    runtime = server_runtime
    if not token:
        return None
    runtime._maybe_purge_sessions()
    with closing(connect_auth()) as connection:
        row = connection.execute(
            """SELECT u.id, u.username, u.role, u.is_active, u.ai_daily_limit,
                      COALESCE(NULLIF(u.nickname, ''), u.username) AS nickname, COALESCE(u.lang, 'java') AS lang
               FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token = ? AND s.expires_at > ? AND u.is_active = 1
                 AND NOT EXISTS (
                     SELECT 1 FROM users collision
                     WHERE collision.username COLLATE NOCASE = u.username COLLATE NOCASE
                       AND collision.id <> u.id
                 )""",
            (token, runtime.now_iso()),
        ).fetchone()
        if row is not None:
            seen_now = runtime.time.time()
            with _LAST_SEEN_LOCK:
                if seen_now - _LAST_SEEN_TS.get(row["id"], 0) >= _LAST_SEEN_INTERVAL:
                    _LAST_SEEN_TS[row["id"]] = seen_now
                    try:
                        connection.execute("UPDATE users SET last_seen = ? WHERE id = ?", (runtime.now_iso(), row["id"]))
                    except sqlite3.Error:
                        pass
    return row


def generate_invite_codes(count: int, days: int, note: str, created_by: int) -> list[str]:
    runtime = server_runtime
    count = max(1, min(count, 50))
    days = max(0, min(days, 365))
    expires = (business_now().date() + timedelta(days=days)).isoformat() if days else None
    codes: list[str] = []
    with closing(connect_auth()) as connection:
        while len(codes) < count:
            body = "-".join("".join(secrets.choice(runtime._CODE_ALPHABET) for _ in range(4)) for _ in range(2))
            code = f"FORGE-{body}"
            try:
                connection.execute(
                    "INSERT INTO invite_codes(code, status, note, created_at, expires_at) VALUES (?, 'unused', ?, ?, ?)",
                    (code, note[:64], runtime.now_iso(), expires),
                )
                codes.append(code)
            except sqlite3.IntegrityError:
                continue
    return codes


def list_invite_codes() -> list[dict[str, object]]:
    with closing(connect_auth()) as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM invite_codes ORDER BY created_at DESC, code LIMIT 500")]


def revoke_invite_code(code: str) -> dict[str, object]:
    with closing(connect_auth()) as connection:
        cursor = connection.execute("UPDATE invite_codes SET status = 'revoked' WHERE code = ? AND status = 'unused'", (code,))
        if cursor.rowcount != 1:
            raise ValueError("注册码不存在或不可吊销")
    return {"code": code, "status": "revoked"}


def register_with_code(username: str, password: str, code: str) -> dict[str, object]:
    runtime = server_runtime
    username = username.strip()
    today = business_now().date().isoformat()
    connection = connect_auth()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM invite_codes WHERE code = ?", (code.strip().upper(),)).fetchone()
        if row is None:
            raise ValueError("注册码无效")
        if row["status"] == "used":
            raise ValueError("注册码已被使用")
        if row["status"] == "revoked":
            raise ValueError("注册码已被吊销")
        if row["expires_at"] and str(row["expires_at"]) < today:
            raise ValueError("注册码已过期")
        if _username_case_collision(connection, username):
            raise ValueError("用户名已被占用")
        cursor = connection.execute(
            "UPDATE invite_codes SET status = 'used', used_at = ? WHERE code = ? AND status = 'unused'",
            (runtime.now_iso(), code.strip().upper()),
        )
        if cursor.rowcount != 1:
            raise ValueError("注册码已被使用")
        user = create_user(username, password, conn=connection)
        connection.execute("COMMIT")
    except (ValueError, sqlite3.Error):
        with suppress(sqlite3.Error):
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    with closing(runtime.connect(user_db_path(str(user["username"])))):
        pass
    return user


def list_users() -> list[dict[str, object]]:
    runtime = server_runtime
    items: list[dict[str, object]] = []
    with closing(connect_auth()) as connection:
        for row in connection.execute(
            "SELECT id, username, COALESCE(nickname, '') AS nickname, role, is_active, created_at, last_login, "
            "COALESCE(last_seen, last_login) AS last_active, ai_daily_limit FROM users ORDER BY id"
        ):
            item = dict(row)
            item["permanent_admin"] = str(item["username"]) == runtime.PERMANENT_ADMIN_USERNAME
            custom_limit = item.get("ai_daily_limit")
            effective_limit = runtime.AI_DAILY_LIMIT_DEFAULT if custom_limit is None else int(custom_limit)
            item["ai_daily_limit_custom"] = custom_limit is not None
            item["ai_daily_limit_effective"] = None if item["role"] == "admin" else effective_limit
            db_file = user_db_path(str(item["username"]))
            item["db_bytes"] = db_file.stat().st_size if db_file.is_file() else 0
            item["ai_quota"] = runtime.get_ai_quota(db_file, str(item["role"]), daily_limit=effective_limit)
            items.append(item)
    return items


def effective_ai_daily_limit(user: Mapping[str, object] | sqlite3.Row) -> int:
    runtime = server_runtime
    value = user["ai_daily_limit"] if "ai_daily_limit" in user.keys() else None
    return runtime.AI_DAILY_LIMIT_DEFAULT if value is None else int(value)


def admin_set_user_ai_daily_limit(username: str, daily_limit: int | None, actor_user_id: int) -> dict[str, object]:
    runtime = server_runtime
    username = username.strip()
    if not username:
        raise ValueError("用户名不能为空")
    if daily_limit is not None and (isinstance(daily_limit, bool) or not isinstance(daily_limit, int) or not 0 <= daily_limit <= runtime.AI_DAILY_LIMIT_MAX):
        raise ValueError(f"每日 AI 分析上限必须是 0~{runtime.AI_DAILY_LIMIT_MAX} 的整数或 null")
    with closing(connect_auth()) as connection:
        actor = connection.execute("SELECT id, role FROM users WHERE id = ?", (actor_user_id,)).fetchone()
        target = connection.execute("SELECT id, username, role, ai_daily_limit FROM users WHERE username = ?", (username,)).fetchone()
        if actor is None or str(actor["role"]) != "admin":
            raise PermissionError("需要管理员权限")
        if target is None:
            raise ValueError("用户不存在")
        if str(target["role"]) == "admin":
            raise ValueError("管理员账号不设有限 AI 分析额度")
        connection.execute("UPDATE users SET ai_daily_limit = ? WHERE id = ?", (daily_limit, int(target["id"])))
    effective = runtime.AI_DAILY_LIMIT_DEFAULT if daily_limit is None else daily_limit
    quota = runtime.get_ai_quota(user_db_path(str(target["username"])), "user", daily_limit=effective)
    return {"username": str(target["username"]), "ai_daily_limit": daily_limit,
            "ai_daily_limit_custom": daily_limit is not None, "ai_daily_limit_effective": effective, "quota": quota}


def admin_reset_user_ai_quota(username: str, actor_user_id: int) -> dict[str, object]:
    runtime = server_runtime
    username = username.strip()
    if not username:
        raise ValueError("用户名不能为空")
    with closing(connect_auth()) as connection:
        actor = connection.execute("SELECT id, role FROM users WHERE id = ?", (actor_user_id,)).fetchone()
        target = connection.execute("SELECT id, username, role, ai_daily_limit FROM users WHERE username = ?", (username,)).fetchone()
        if actor is None or str(actor["role"]) != "admin":
            raise PermissionError("需要管理员权限")
        if target is None:
            raise ValueError("用户不存在")
        if str(target["role"]) == "admin":
            raise ValueError("不能重置管理员的分析次数")
        reset = runtime.reset_ai_quota(user_db_path(str(target["username"])), daily_limit=effective_ai_daily_limit(target))
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """INSERT INTO ai_quota_reset_audit(actor_admin_id, target_user_id, reset_at, before_used)
               VALUES (?, ?, ?, ?)""",
            (int(actor["id"]), int(target["id"]), runtime.now_iso(), int(reset["before_used"])),
        )
        connection.execute("COMMIT")
    return {"username": username, "reset": True, "quota": reset["quota"]}


def set_user_active(username: str, active: bool) -> dict[str, object]:
    username = username.strip()
    with closing(connect_auth()) as connection:
        row = connection.execute("SELECT id, role FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            raise ValueError("用户不存在")
        if str(row["role"]) == "admin":
            raise ValueError("不能停用管理员账号")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if active else 0, row["id"]))
        if not active:
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
        connection.execute("COMMIT")
    return {"username": username, "is_active": 1 if active else 0}


def set_user_role(username: str, role: str, actor_username: str = "") -> dict[str, object]:
    runtime = server_runtime
    username = username.strip()
    role = role.strip().lower()
    if role not in ("admin", "user"):
        raise ValueError("角色只能是 admin 或 user")
    if not username:
        raise ValueError("用户名不能为空")
    with closing(connect_auth()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT id, username, role FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            raise ValueError("用户不存在")
        current_role = str(row["role"])
        if username == runtime.PERMANENT_ADMIN_USERNAME and role != "admin":
            raise ValueError("永久管理员账号不能降级为普通用户")
        if current_role == role:
            connection.execute("COMMIT")
            return {"username": username, "role": role}
        if username == actor_username and role != "admin":
            raise ValueError("不能把当前管理员降为普通用户")
        if current_role == "admin" and role == "user":
            admin_count = connection.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
            if int(admin_count) <= 1:
                raise ValueError("不能降级最后一个管理员")
        connection.execute("UPDATE users SET role = ? WHERE id = ?", (role, row["id"]))
        connection.execute("COMMIT")
    return {"username": username, "role": role}


def reset_user_nickname(username: str, actor_username: str = "") -> dict[str, object]:
    username = username.strip()
    if not username:
        raise ValueError("用户名不能为空")
    with closing(connect_auth()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT id, username, role FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            raise ValueError("用户不存在")
        if str(row["role"]) == "admin" and username != actor_username:
            raise ValueError("不能修改其他管理员的昵称")
        connection.execute("UPDATE users SET nickname = ? WHERE id = ?", (username, row["id"]))
        connection.execute("COMMIT")
    return {"username": username, "nickname": username}


def reset_user_password(username: str, new_password: str) -> dict[str, object]:
    if len(new_password) < 8:
        raise ValueError("密码至少 8 位")
    with closing(connect_auth()) as connection:
        row = connection.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            raise ValueError("用户不存在")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_password), row["id"]))
        connection.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
        connection.execute("COMMIT")
    return {"username": username, "reset": True}


def change_own_password(user_id: int, old_password: str, new_password: str, keep_token: str = "") -> dict[str, object]:
    if len(new_password) < 8:
        raise ValueError("密码至少 8 位")
    with closing(connect_auth()) as connection:
        row = connection.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or not verify_password(old_password, str(row["password_hash"])):
            raise ValueError("原密码错误")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_password), user_id))
        connection.execute("DELETE FROM sessions WHERE user_id = ? AND token != ?", (user_id, keep_token))
        connection.execute("COMMIT")
    return {"changed": True}
