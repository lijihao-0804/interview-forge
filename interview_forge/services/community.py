"""Feedback, chat, search and account-profile application services."""
from __future__ import annotations
from interview_forge.core.runtime import server_runtime

import base64
import binascii
import html
import json
import re
import threading
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import parse_qs

from interview_forge.core.paths import ROOT
from interview_forge.core.roles import effective_role
from interview_forge.core.web_access import canonical_url_path, is_sensitive_path, target_relative_path


_FEEDBACK_ATTEMPTS: dict[str, list[float]] = {}
_FEEDBACK_LOCK = threading.Lock()
_FEEDBACK_WINDOW = 3600.0
_FEEDBACK_MAX_PER_IP = 5
CHAT_KEEP = 2000
CHAT_MAX_LEN = 500
_CHAT_SEND_LOG: dict[int, list[float]] = {}
_CHAT_SEND_LOCK = threading.Lock()
SOLUTION_LANGS = ("java", "cpp", "python", "go", "c")
_AVATAR_MAX_BYTES = 150 * 1024
_SEARCH_INDEX: list[dict] | None = None
_SEARCH_LOCK = threading.Lock()



def feedback_rate_limit_ok(ip: str) -> bool:
    now = time.time()
    with _FEEDBACK_LOCK:
        stamps = [t for t in _FEEDBACK_ATTEMPTS.get(ip, []) if now - t < _FEEDBACK_WINDOW]
        _FEEDBACK_ATTEMPTS[ip] = stamps
        return len(stamps) < _FEEDBACK_MAX_PER_IP


def feedback_rate_limit_record(ip: str) -> None:
    with _FEEDBACK_LOCK:
        _FEEDBACK_ATTEMPTS.setdefault(ip, []).append(time.time())


def submit_feedback(content: str, contact: str, page: str, user_agent: str, username: str = "") -> dict[str, object]:
    runtime = server_runtime
    content = content.strip()
    if not (1 <= len(content) <= 2000):
        raise ValueError("反馈内容需为 1~2000 字")
    if len(contact) > 120 or len(page) > 500:
        raise ValueError("联系方式或页面地址过长")
    with closing(runtime.connect_auth()) as connection:
        cursor = connection.execute(
            "INSERT INTO feedback(content, username, contact, page, user_agent, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?)",
            (content, username[:64], contact[:120], page[:500], user_agent[:300], runtime.now_iso()),
        )
    return {"id": cursor.lastrowid, "submitted": True}


def _feedback_page_title(path: str, *, private_reader: bool) -> str:
    if private_reader and path == "/api/private-archive/index.html":
        return "AgentHub 教学档案"
    if not path.endswith(".html") or path.startswith("/api/"):
        return ""
    project_book = private_reader and re.fullmatch(
        r"/library/(?:development-history/(?:index|chapters/[a-z0-9-]+)|"
        r"voltedu-study/(?:index|(?:story|claims|interview|notes)/[a-z0-9-]+)|"
        r"agenthub-study/(?:index|chapter-\d{2}))\.html", path
    )
    if is_sensitive_path(path) and not project_book:
        return ""
    if target_relative_path(ROOT, path) != path:
        return ""
    try:
        with (ROOT / path.lstrip("/")).open("rb") as stream:
            head = stream.read(16384).decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return ""
    title = re.search(r"<title\b[^>]*>(.*?)</title>", head, re.I | re.S)
    if not title:
        return ""
    label = html.unescape(title[1]).split(" · Interview", 1)[0].strip()
    chapter = re.fullmatch(r"/library/[^/]+/chapter-(\d+)\.html", path)
    return f"第 {int(chapter[1])} 章 · {label}" if chapter else label


def list_feedback(status: str = "", *, viewer=None) -> list[dict[str, object]]:
    runtime = server_runtime
    sql = "SELECT * FROM feedback"
    params: list[object] = []
    if status in ("open", "resolved"):
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY id DESC LIMIT 500"
    with closing(runtime.connect_auth()) as connection:
        items = [dict(row) for row in connection.execute(sql, params)]
    titles = {}
    agenthub_chapters = None
    private_reader = effective_role(viewer) == "super_admin"
    for item in items:
        page = item["page"]
        path = None
        if page.startswith("/") and not page.startswith("//") and "\\" not in page:
            path = canonical_url_path(page.partition("#")[0].partition("?")[0])
            if path == "/":
                path = "/cockpit.html"
        if path and path not in titles:
            titles[path] = _feedback_page_title(path, private_reader=private_reader)
        item["page_title"] = titles.get(path, "")
        if private_reader and path == "/api/private-archive/index.html":
            chapter = parse_qs(page.partition("#")[2]).get("chapter", [""])[0]
            if chapter:
                if agenthub_chapters is None:
                    try:
                        manifest = json.loads((ROOT / "library/agenthub/data/manifest.json").read_text(encoding="utf-8"))
                        agenthub_chapters = {entry["id"]: entry["title"] for key in ("chapters", "originals")
                                             for entry in manifest.get(key, [])}
                    except (OSError, ValueError, KeyError, TypeError):
                        agenthub_chapters = {}
                if chapter in agenthub_chapters:
                    item["page_title"] += " · " + agenthub_chapters[chapter]
    return items


def feedback_replies(user_id: int) -> list[dict[str, object]]:
    with closing(server_runtime.connect_auth()) as connection:
        return [dict(row) for row in connection.execute(
            "SELECT id, content, resolved_note, resolved_at FROM feedback "
            "WHERE reply_user_id = ? AND status = 'resolved' AND resolved_note <> '' "
            "ORDER BY resolved_at DESC, id DESC LIMIT 50", (user_id,)
        )]


def resolve_feedback(feedback_id: int, resolved: bool, note: str = "") -> dict[str, object]:
    runtime = server_runtime
    reply = note.strip()[:300] if resolved else ""
    with closing(runtime.connect_auth()) as connection:
        cursor = connection.execute(
            "UPDATE feedback SET status = ?, resolved_at = ?, resolved_note = ?, "
            "reply_user_id = CASE WHEN ? <> '' THEN (SELECT u.id FROM users AS u "
            "WHERE u.username = feedback.username AND julianday(u.created_at) <= julianday(feedback.created_at)) END "
            "WHERE id = ?",
            ("resolved" if resolved else "open", runtime.now_iso() if resolved else None, reply, reply, feedback_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("反馈不存在")
    return {"id": feedback_id, "status": "resolved" if resolved else "open"}


def chat_rate_limit_ok(user_id: int) -> bool:
    now = time.time()
    with _CHAT_SEND_LOCK:
        stamps = [t for t in _CHAT_SEND_LOG.get(user_id, []) if now - t < 60.0]
        _CHAT_SEND_LOG[user_id] = stamps
        return len(stamps) < 10


def chat_rate_limit_record(user_id: int) -> None:
    with _CHAT_SEND_LOCK:
        _CHAT_SEND_LOG.setdefault(user_id, []).append(time.time())


def chat_send(user_id: int, username: str, content: str) -> dict[str, object]:
    runtime = server_runtime
    content = content.strip()
    if not (1 <= len(content) <= CHAT_MAX_LEN):
        raise ValueError(f"消息需为 1~{CHAT_MAX_LEN} 字")
    with closing(runtime.connect_auth()) as connection:
        cursor = connection.execute(
            "INSERT INTO chat_messages(user_id, content, created_at) VALUES (?, ?, ?)",
            (user_id, content, runtime.now_iso()),
        )
        connection.execute(
            "DELETE FROM chat_messages WHERE id <= (SELECT MAX(id) FROM chat_messages) - ?",
            (CHAT_KEEP,),
        )
    return {"id": cursor.lastrowid, "created_at": runtime.now_iso(), "username": username}


def chat_messages_after(after_id: int, limit: int = 50) -> list[dict[str, object]]:
    runtime = server_runtime
    limit = max(1, min(limit, 100))
    with closing(runtime.connect_auth()) as connection:
        if after_id < 0:
            rows = connection.execute(
                "SELECT m.id, m.user_id, u.username AS username, COALESCE(NULLIF(u.nickname, ''), u.username) AS nickname, "
                "m.content, m.created_at, u.role FROM chat_messages m JOIN users u ON u.id = m.user_id "
                "ORDER BY m.id DESC LIMIT ?", (limit,))
            items = [dict(r) for r in rows]
            items.reverse()
            return items
        rows = connection.execute(
            "SELECT m.id, m.user_id, u.username AS username, COALESCE(NULLIF(u.nickname, ''), u.username) AS nickname, "
            "m.content, m.created_at, u.role FROM chat_messages m JOIN users u ON u.id = m.user_id "
            "WHERE m.id > ? ORDER BY m.id ASC LIMIT ?", (after_id, limit))
        return [dict(r) for r in rows]


def chat_messages_before(before_id: int, limit: int = 50) -> tuple[list[dict[str, object]], bool]:
    runtime = server_runtime
    limit = max(1, min(limit, 100))
    with closing(runtime.connect_auth()) as connection:
        rows = connection.execute(
            "SELECT m.id, m.user_id, u.username AS username, COALESCE(NULLIF(u.nickname, ''), u.username) AS nickname, "
            "m.content, m.created_at, u.role FROM chat_messages m JOIN users u ON u.id = m.user_id "
            "WHERE m.id < ? ORDER BY m.id DESC LIMIT ?", (before_id, limit + 1))
        items = [dict(r) for r in rows]
    has_older = len(items) > limit
    items = items[:limit]
    items.reverse()
    return items, has_older


def chat_has_older(oldest_id: int | None) -> bool:
    runtime = server_runtime
    if oldest_id is None:
        return False
    with closing(runtime.connect_auth()) as connection:
        return connection.execute("SELECT 1 FROM chat_messages WHERE id < ? LIMIT 1", (oldest_id,)).fetchone() is not None


def chat_delete(feedback_id_alias: int) -> dict[str, object]:
    runtime = server_runtime
    with closing(runtime.connect_auth()) as connection:
        cursor = connection.execute("DELETE FROM chat_messages WHERE id = ?", (feedback_id_alias,))
        if cursor.rowcount != 1:
            raise ValueError("消息不存在")
    return {"id": feedback_id_alias, "deleted": True}


def _load_search_index() -> list[dict]:
    runtime = server_runtime
    global _SEARCH_INDEX
    if _SEARCH_INDEX is None:
        with _SEARCH_LOCK:
            if _SEARCH_INDEX is None:
                path = runtime.ROOT / "library" / "search-index.json"
                _SEARCH_INDEX = json.loads(path.read_text(encoding="utf-8"))
    return _SEARCH_INDEX


def search_index_server(query: str, *, all_terms: bool = False) -> list[dict[str, object]]:
    items, _total = search_index_server_with_count(query, all_terms=all_terms)
    return items


def indexed_chapter(index_url: str) -> dict | None:
    return next((entry for entry in _load_search_index() if entry.get("url") == index_url), None)


def search_index_server_with_count(query: str, *, all_terms: bool = False) -> tuple[list[dict[str, object]], int]:
    """Return the bounded search page plus the complete match count."""
    q = query.strip().lower()
    if not q:
        return [], 0
    terms = list(dict.fromkeys(q.split())) if all_terms else []
    hits = []
    for entry in _load_search_index():
        title = str(entry.get("title", "")).lower()
        mod = str(entry.get("module_title", "")).lower()
        body = str(entry.get("text", ""))
        text = body.lower()
        score = 3 if q in title else 2 if q in mod else 1 if q in text else 0
        body_match = q if q in text else ""
        if not score and 2 <= len(terms) <= 6 and all(
            term in title or term in mod or term in text for term in terms
        ):
            score = (1 + sum(term in title for term in terms) / len(terms)) / 3
            body_match = max((term for term in terms if term in text), key=len, default="")
        if score:
            snippet = ""
            if body_match:
                index = text.find(body_match)
                start = max(0, index - 64)
                end = min(len(body), index + len(body_match) + 80)
                snippet = ("…" if start else "") + body[start:end].strip() + ("…" if end < len(body) else "")
            hits.append({"id": entry.get("id"), "title": entry.get("title"), "url": entry.get("url"), "module_title": entry.get("module_title"), "snippet": snippet, "s": score})
            if all_terms:
                hits[-1]["body_match"] = body_match
    hits.sort(key=lambda x: -x["s"])
    return hits[:60], len(hits)


def get_profile(username: str) -> dict[str, object]:
    runtime = server_runtime
    with closing(runtime.connect_auth()) as connection:
        row = connection.execute(
            "SELECT username, COALESCE(nickname, '') AS nickname, COALESCE(lang, 'java') AS lang FROM users WHERE username = ?", (username,)
        ).fetchone()
        avatar = connection.execute(
            "SELECT mime FROM avatars WHERE user_id = (SELECT id FROM users WHERE username = ?)", (username,)
        ).fetchone()
    if row is None:
        raise ValueError("用户不存在")
    return {"username": row["username"], "nickname": row["nickname"], "lang": row["lang"], "has_avatar": avatar is not None}


def set_profile(username: str, nickname: str = None, avatar_data_url: str = None, lang: str = None) -> dict[str, object]:
    runtime = server_runtime
    with closing(runtime.connect_auth()) as connection:
        row = connection.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            raise ValueError("用户不存在")
        if nickname is not None:
            nickname = nickname.strip()
            if nickname:
                nickname = runtime.validate_nickname(nickname)
            connection.execute("UPDATE users SET nickname = ? WHERE id = ?", (nickname, row["id"]))
        if lang is not None:
            if lang not in SOLUTION_LANGS:
                raise ValueError("不支持的语言")
            connection.execute("UPDATE users SET lang = ? WHERE id = ?", (lang, row["id"]))
        if avatar_data_url is not None:
            if avatar_data_url == "":
                connection.execute("DELETE FROM avatars WHERE user_id = ?", (row["id"],))
            else:
                import re
                match = re.match(r"^data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$", avatar_data_url)
                if not match:
                    raise ValueError("头像格式不支持（仅 png/jpeg/webp）")
                try:
                    blob = base64.b64decode(match.group(2), validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise ValueError("头像数据不是合法的 Base64") from exc
                if len(blob) > _AVATAR_MAX_BYTES:
                    raise ValueError("头像过大（压缩后需小于 150KB）")
                connection.execute(
                    "INSERT INTO avatars(user_id, mime, data, updated_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(user_id) DO UPDATE SET mime = excluded.mime, data = excluded.data, updated_at = excluded.updated_at",
                    (row["id"], "image/" + match.group(1), blob, runtime.now_iso()),
                )
    return get_profile(username)


def get_avatar(username: str):
    runtime = server_runtime
    with closing(runtime.connect_auth()) as connection:
        row = connection.execute(
            "SELECT a.mime, a.data FROM avatars a JOIN users u ON u.id = a.user_id WHERE u.username = ?", (username,)
        ).fetchone()
    if row is None:
        return None
    return str(row["mime"]), bytes(row["data"])
