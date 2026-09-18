"""LeetCode credentials, status checks and incremental sync business logic.

The HTTP assembly remains the compatibility surface.  Runtime dependencies
are resolved lazily so existing tests and callers can replace the server's
database path, catalog, cache invalidation and provider retry hooks exactly as
before.  No credential is logged or included in errors.
"""
from __future__ import annotations

import io
import asyncio
import json
import re
import threading
import time
import urllib.error
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from pathlib import Path

from interview_forge.core.paths import DB_PATH
from interview_forge.core.runtime import server_runtime
from interview_forge.observability.logging import log_event
from interview_forge.ai.config_store import decrypt_secret, encrypt_secret


LC_STATUS_TTL = 60.0
_LC_STATUS_CACHE: dict[tuple[str, str], tuple[float, dict[str, object]]] = {}
_LC_STATUS_LOCK = threading.Lock()
SYNC_TASKS: dict[str, dict[str, object]] = {}
SYNC_TASKS_LOCK = threading.Lock()
_SYNC_OWNER_LOCKS: dict[str, threading.Lock] = {}
_SYNC_OWNER_LOCKS_GUARD = threading.Lock()


def _sync_owner_lock(owner: str) -> threading.Lock | None:
    owner = str(owner or "")
    if not owner:
        return None
    with _SYNC_OWNER_LOCKS_GUARD:
        return _SYNC_OWNER_LOCKS.setdefault(owner, threading.Lock())


def try_acquire_sync_owner(owner: str) -> bool:
    """Reserve one user's sync slot for direct or background execution."""
    lock = _sync_owner_lock(owner)
    return lock is None or lock.acquire(blocking=False)


def release_sync_owner(owner: str) -> None:
    lock = _sync_owner_lock(owner)
    if lock is not None and lock.locked():
        lock.release()


def _normalize_sync_offset(value: object) -> int:
    try:
        return max(0, min(int(value or 0), 1_000_000))
    except (TypeError, ValueError):
        return 0


def _safe_log_event(event: str, **fields: object) -> None:
    """Observability must never change sync success/failure semantics."""
    try:
        log_event(event, **fields)
    except Exception:  # noqa: BLE001 - logging is deliberately best effort
        return


def _record_sync_action_background_result(
    *,
    db_path: Path,
    action_id: str,
    task_id: str,
    status: str,
    error_category: str | None,
    partial: bool,
    result: dict[str, object] | None,
    finished_at: str,
) -> None:
    """Attach a safe final worker result to the originating chat action."""
    if not action_id:
        return
    try:
        from interview_forge.ai.actions.store import ActionRequestStore

        background: dict[str, object] = {
            "task_id": task_id,
            "status": status,
            "partial": bool(partial),
            "finished_at": finished_at,
        }
        if error_category:
            background["error_category"] = str(error_category)
        if isinstance(result, dict):
            background["submissions_seen"] = int(result.get("submissions_seen") or 0)
            background["submissions_added"] = int(result.get("submissions_added") or 0)
            background["solved_added"] = int(result.get("solved_added") or 0)
        ActionRequestStore().update_background_result(
            user_db=db_path,
            action_id=action_id,
            background=background,
        )
    except Exception:  # noqa: BLE001 - audit enrichment must never affect sync
        _safe_log_event(
            "leetcode_sync_action_result_persist_failed",
            module="leetcode",
            task_id=task_id,
        )



def get_credentials(db_path: Path = DB_PATH):
    runtime = server_runtime
    with closing(runtime.connect(db_path)) as connection:
        rows = connection.execute("SELECT key, value FROM credentials").fetchall()
        result: dict[str, str] = {}
        legacy: list[tuple[str, str]] = []
        for row in rows:
            key = str(row["key"])
            raw = str(row["value"] or "")
            if raw.startswith("gAAAA"):
                value = decrypt_secret(raw)
            else:
                value = raw
                if value:
                    legacy.append((key, value))
            result[key] = value
        if legacy:
            for key, value in legacy:
                connection.execute(
                    "UPDATE credentials SET value = ? WHERE key = ?",
                    (encrypt_secret(value), key),
                )
            connection.commit()
    return result


def set_credentials(pairs: dict[str, str], db_path: Path = DB_PATH) -> None:
    runtime = server_runtime
    studied_at, _ = runtime.now_parts()
    with closing(runtime.connect(db_path)) as connection:
        for key, value in pairs.items():
            if key not in ("leetcode_session", "leetcode_csrf"):
                continue
            if not isinstance(value, str):
                continue
            encrypted = encrypt_secret(value.strip()) if value.strip() else ""
            connection.execute(
                """INSERT INTO credentials(key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                (key, encrypted, studied_at),
            )
            connection.commit()


def clear_credentials(db_path: Path = DB_PATH) -> None:
    runtime = server_runtime
    with closing(runtime.connect(db_path)) as connection:
        connection.execute("DELETE FROM credentials")
        connection.commit()


def _leetcode_headers(credentials: dict[str, str]) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://leetcode.cn/problemset/",
        "Origin": "https://leetcode.cn",
        "X-Requested-With": "XMLHttpRequest",
    }
    session = credentials.get("leetcode_session", "")
    if session:
        csrf = credentials.get("leetcode_csrf", "")
        cookies = f"LEETCODE_SESSION={session}"
        if csrf:
            cookies += f"; csrftoken={csrf}"
        headers["Cookie"] = cookies
    if credentials.get("leetcode_csrf", ""):
        headers["X-CSRFToken"] = credentials["leetcode_csrf"]
    return headers


def _lc_http_get(url: str, headers: dict[str, str], timeout: int = 25) -> bytes:
    import urllib.request

    try:
        from curl_cffi import requests as _curl_requests
    except ImportError:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError:
            raise
    response = _curl_requests.get(url, headers=headers, timeout=timeout, impersonate="chrome")
    if response.status_code >= 400:
        raise urllib.error.HTTPError(
            url, response.status_code, "HTTP Error", response.headers, io.BytesIO(response.content)
        )
    return response.content


@dataclass(frozen=True)
class _LeetCodeHTTPClassification:
    category: str
    message: str
    status: HTTPStatus
    retryable: bool


def _http_error_body_head(exc: urllib.error.HTTPError, limit: int = 512) -> bytes:
    """Read only a finite body prefix, caching it for later classification."""
    cached = getattr(exc, "_interview_forge_body_head", None)
    if isinstance(cached, bytes):
        return cached
    try:
        body = exc.read(limit)
    except Exception:  # noqa: BLE001 - classification must never mask the error
        body = b""
    if not isinstance(body, bytes):
        body = str(body).encode("utf-8", errors="ignore")[:limit]
    try:
        setattr(exc, "_interview_forge_body_head", body[:limit])
    except Exception:  # noqa: BLE001 - some HTTPError-like objects may be immutable
        pass
    return body[:limit]


def _header_value(headers, name: str) -> str:
    try:
        value = headers.get(name, "") if headers is not None else ""
    except Exception:  # noqa: BLE001 - a provider header object is untrusted
        value = ""
    return str(value or "").strip().lower()


def _classify_leetcode_http_error(exc: urllib.error.HTTPError) -> _LeetCodeHTTPClassification:
    """Classify an upstream response without exposing its body or headers."""
    headers = getattr(exc, "headers", None)
    body_head = _http_error_body_head(exc)
    cloudflare_challenge = (
        _header_value(headers, "cf-mitigated") == "challenge"
        or b"just a moment" in body_head.lower()
    )
    code = int(getattr(exc, "code", 0) or 0)
    if cloudflare_challenge:
        return _LeetCodeHTTPClassification(
            "provider_blocked",
            "检测到力扣 Cloudflare challenge，服务器请求被上游拦截。请同时更新 LEETCODE_SESSION 与 csrftoken 后重试；若仍失败，再检查服务器出口网络。",
            HTTPStatus.BAD_GATEWAY,
            False,
        )
    if code in (401, 403):
        return _LeetCodeHTTPClassification(
            "session_invalid",
            "LEETCODE_SESSION 或 csrftoken 已过期/无效，请同时更新两者后重试",
            HTTPStatus.UNAUTHORIZED,
            False,
        )
    if code == 429:
        return _LeetCodeHTTPClassification(
            "provider_rate_limited",
            "力扣请求较频繁，请稍后重试",
            HTTPStatus.SERVICE_UNAVAILABLE,
            True,
        )
    if 500 <= code <= 599:
        return _LeetCodeHTTPClassification(
            "provider_unavailable",
            "力扣服务暂时不可用，请稍后重试",
            HTTPStatus.BAD_GATEWAY,
            True,
        )
    return _LeetCodeHTTPClassification(
        "provider_unavailable",
        "力扣服务暂时不可用，请稍后重试",
        HTTPStatus.BAD_GATEWAY,
        False,
    )


def _exception_category(exc: Exception) -> str:
    if isinstance(exc, LeetCodeSyncError):
        return exc.category
    if isinstance(exc, urllib.error.HTTPError):
        return _classify_leetcode_http_error(exc).category
    if isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower():
        return "network_error"
    if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError)):
        return "provider_unavailable"
    return "network_error"


def _fetch_json_with_retry(
    url: str,
    headers: dict[str, str],
    timeout: int = 25,
    retries: int = 3,
    backoff: float = 2.0,
) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return json.loads(server_runtime._lc_http_get(url, headers, timeout).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            classification = _classify_leetcode_http_error(exc)
            if not classification.retryable:
                raise
        except Exception as exc:  # noqa: BLE001 - 网络抖动统一走退避重试
            last_error = exc
        if attempt + 1 < retries:
            time.sleep(backoff * (2**attempt))
    if isinstance(last_error, urllib.error.HTTPError):
        raise last_error
    raise last_error


def lc_status_cached(db_path: Path, credentials: dict[str, str], force: bool = False) -> dict:
    runtime = server_runtime
    key = (str(db_path), credentials.get("leetcode_session", ""))
    now = time.time()
    if not force:
        with _LC_STATUS_LOCK:
            hit = _LC_STATUS_CACHE.get(key)
            if hit and now - hit[0] < LC_STATUS_TTL:
                return hit[1]
    result = runtime.leetcode_status(credentials)
    with _LC_STATUS_LOCK:
        _LC_STATUS_CACHE[key] = (now, result)
    return result


def lc_status_invalidate(db_path: Path) -> None:
    runtime = server_runtime
    with _LC_STATUS_LOCK:
        for key in [key for key in _LC_STATUS_CACHE if key[0] == str(db_path)]:
            _LC_STATUS_CACHE.pop(key, None)


def leetcode_status(credentials: dict[str, str], timeout: int = 20) -> dict[str, object]:
    if not credentials.get("leetcode_session"):
        return {"connected": False, "reason": "no-session", "message": "尚未保存 LEETCODE_SESSION"}
    try:
        data = json.loads(server_runtime._lc_http_get(
            "https://leetcode.cn/api/problems/all/", _leetcode_headers(credentials), timeout
        ).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        classification = _classify_leetcode_http_error(exc)
        if classification.category == "provider_blocked":
            return {
                "connected": False,
                "reason": "cloudflare",
                "message": classification.message,
            }
        if classification.category == "session_invalid":
            return {"connected": False, "reason": "expired", "message": classification.message}
        if classification.category == "provider_rate_limited":
            return {"connected": False, "reason": "rate-limited", "message": classification.message}
        return {"connected": False, "reason": "http", "message": classification.message}
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "reason": "network", "message": f"网络错误：{type(exc).__name__}"}
    user_name = str(data.get("user_name") or "")
    num_solved = int(data.get("num_solved") or 0)
    if user_name:
        return {"connected": True, "user_name": user_name, "num_solved": num_solved}
    return {"connected": False, "reason": "anonymous", "message": "返回匿名数据，会话未生效"}


async def leetcode_status_async(credentials: dict[str, str], timeout: int = 20) -> dict[str, object]:
    """Run the existing status probe without blocking an async HTTP route."""
    return await asyncio.to_thread(leetcode_status, credentials, timeout)


class LeetCodeSyncError(RuntimeError):
    """可安全返回前端的力扣同步错误；不携带凭证、响应头或内部路径。"""

    def __init__(
        self,
        category: str,
        user_message: str,
        status: HTTPStatus = HTTPStatus.BAD_GATEWAY,
    ) -> None:
        super().__init__(user_message)
        self.category = category
        self.user_message = user_message
        self.status = status


def _safe_sync_error(category: str) -> LeetCodeSyncError:
    messages = {
        "provider_blocked": "检测到力扣 Cloudflare challenge，服务器请求被上游拦截。请同时更新 LEETCODE_SESSION 与 csrftoken 后重试；若仍失败，再检查服务器出口网络。",
        "session_invalid": "LEETCODE_SESSION 或 csrftoken 已过期/无效，请同时更新两者后重试",
        "provider_rate_limited": "力扣请求较频繁，请稍后重试",
        "provider_unavailable": "力扣服务暂时不可用，请稍后重试",
        "network_error": "连接力扣失败，请检查网络后重试",
        "sync_in_progress": "已有力扣同步任务运行中，请稍后重试",
    }
    statuses = {
        "session_invalid": HTTPStatus.UNAUTHORIZED,
        "provider_rate_limited": HTTPStatus.SERVICE_UNAVAILABLE,
        "sync_in_progress": HTTPStatus.CONFLICT,
    }
    return LeetCodeSyncError(
        category, messages.get(category, "连接力扣失败，请稍后重试"),
        statuses.get(category, HTTPStatus.BAD_GATEWAY),
    )


def _leetcode_sync_http_error(exc) -> LeetCodeSyncError:
    classification = _classify_leetcode_http_error(exc)
    return LeetCodeSyncError(classification.category, classification.message, classification.status)


def leetcode_sync(
    credentials: dict[str, str],
    db_path: Path = DB_PATH,
    limit: int = 100,
    full: bool = False,
    progress=None,
    offset: int = 0,
) -> dict[str, object]:
    runtime = server_runtime
    if not credentials.get("leetcode_session"):
        raise LeetCodeSyncError("not_configured", "请先前往力扣连接页面填写 LEETCODE_SESSION", HTTPStatus.CONFLICT)
    headers = _leetcode_headers(credentials)
    # Incremental sync always means "the newest page".  Continuation offsets
    # are only meaningful for an explicit full/backfill sync.
    start_offset = _normalize_sync_offset(offset) if full else 0
    results: dict[str, object] = {
        "solved_added": 0, "solved_existing": 0,
        "submissions_added": 0, "submissions_seen": 0, "sync_errors": [],
        "full": bool(full), "offset": start_offset, "next_offset": None,
        "has_more": False, "partial": False, "degraded": False,
    }
    try:
        data = runtime._fetch_json_with_retry("https://leetcode.cn/api/problems/all/", headers)
    except urllib.error.HTTPError as exc:
        raise _leetcode_sync_http_error(exc) from None
    except Exception:  # noqa: BLE001
        raise LeetCodeSyncError("network_error", "连接力扣失败，请检查网络后重试", HTTPStatus.BAD_GATEWAY) from None
    if not str(data.get("user_name") or ""):
        raise LeetCodeSyncError(
            "session_invalid",
            "LEETCODE_SESSION 或 csrftoken 已过期/无效，请同时更新两者后重试",
            HTTPStatus.UNAUTHORIZED,
        )
    if progress is not None:
        progress("已读取力扣题目列表")

    slug_to_id = {slug: pid for pid, slug in runtime.LEETCODE_SLUGS.items()}
    title_to_id: dict[str, int] = {}
    for pid, problem in runtime.PROBLEM_BY_ID.items():
        title_to_id.setdefault(str(problem["title"]).strip(), int(pid))
    for pair in data.get("stat_status_pairs", []):
        stat = pair.get("stat", {})
        title = str(stat.get("question__title") or "").strip()
        pid = slug_to_id.get(str(stat.get("question__title_slug") or ""))
        if title and pid is not None:
            title_to_id.setdefault(title, int(pid))

    collected: list[dict[str, object]] = []
    fetch_errors: list[str] = []
    partial_error_category: str | None = None
    offset = start_offset
    page = 0
    max_pages = 50 if full else 1
    if progress is not None:
        progress("开始拉取提交记录")
    while True:
        page += 1
        try:
            payload = runtime._fetch_json_with_retry(
                f"https://leetcode.cn/api/submissions/?offset={offset}&limit={min(int(limit), 100)}",
                headers,
            )
        except Exception as exc:  # noqa: BLE001 - later pages degrade safely
            if page == 1:
                if isinstance(exc, LeetCodeSyncError):
                    raise exc
                if isinstance(exc, urllib.error.HTTPError):
                    raise _leetcode_sync_http_error(exc) from None
                raise _safe_sync_error(_exception_category(exc)) from None
            partial_error_category = _exception_category(exc)
            results["next_offset"] = offset
            results["has_more"] = True
            fetch_errors.append(f"第 {page} 页拉取失败（错误类别：{partial_error_category}，已停止后续拉取）")
            if progress is not None:
                progress(f"第 {page} 页拉取失败，已停止拉取")
            break
        dump = payload.get("submissions_dump") or []
        if not dump:
            break
        for item in dump:
            if str(item.get("is_pending")) not in ("", "Not Pending"):
                continue
            title = str(item.get("title") or "").strip()
            pid = title_to_id.get(title)
            if pid is None:
                continue
            lc_id = item.get("id")
            status = "ac" if str(item.get("status_display")) == "Accepted" else "wa"
            timestamp = str(item.get("timestamp") or "")
            submitted_at = (
                datetime.fromtimestamp(int(timestamp), tz=runtime.BUSINESS_TZ).isoformat(timespec="seconds")
                if timestamp.isdigit() else runtime.now_parts()[0]
            )
            collected.append({
                "pid": pid, "status": status, "lang": str(item.get("lang") or "")[:40],
                "runtime_ms": runtime._parse_ms(str(item.get("runtime") or "")),
                "memory_kb": runtime._parse_kb(str(item.get("memory") or "")),
                "submitted_at": submitted_at,
                "lc_id": int(lc_id) if str(lc_id).isdigit() else None,
            })
        results["submissions_seen"] = int(results["submissions_seen"]) + len(dump)
        if progress is not None:
            progress(f"第 {page} 页完成，已读取 {results['submissions_seen']} 条")
        # Incremental mode intentionally reads one newest page.  A provider
        # reporting older pages does not make this run partial and must not
        # turn the daily sync into a historical cursor walk.
        if not payload.get("has_next") or not full:
            break
        next_offset = offset + len(dump)
        if page >= max_pages:
            results["next_offset"] = next_offset
            results["has_more"] = True
            fetch_errors.append(f"已达分页上限（{max_pages} 页），可继续同步剩余历史记录")
            partial_error_category = "page_limit"
            break
        time.sleep(0.8)
        offset = next_offset

    with closing(runtime.connect(db_path)) as connection:
        # Serialize the read/merge/write sequence with the background sync
        # writer.  This also lets us repair an older synthetic AC row in the
        # same transaction when a real submission is found later.
        connection.execute("BEGIN IMMEDIATE")
        existing_lc = {
            int(row["lc_id"])
            for row in connection.execute("SELECT lc_id FROM submissions WHERE lc_id IS NOT NULL").fetchall()
        }
        synthetic_rows = {
            int(row["problem_id"]): row
            for row in connection.execute(
                "SELECT id, problem_id, submitted_at FROM submissions "
                "WHERE status = 'ac' AND source = 'sync' AND lc_id IS NULL"
            ).fetchall()
        }
        rows: list[tuple[object, ...]] = []
        for item in collected:
            synthetic = synthetic_rows.get(int(item["pid"])) if item["status"] == "ac" else None
            if synthetic is not None:
                # A previous stat_status_pairs fallback had no real timestamp.
                # Replace it once a real submission arrives; otherwise retain
                # the earlier factual row and avoid creating a duplicate AC.
                if str(item["submitted_at"]) < str(synthetic["submitted_at"]):
                    candidate_lc = item["lc_id"]
                    if candidate_lc is None or candidate_lc not in existing_lc:
                        connection.execute(
                            """UPDATE submissions SET lang = ?, runtime_ms = ?, memory_kb = ?,
                                      submitted_at = ?, source = 'sync', lc_id = ? WHERE id = ?""",
                            (item["lang"], item["runtime_ms"], item["memory_kb"],
                             item["submitted_at"], candidate_lc, synthetic["id"]),
                        )
                        if candidate_lc is not None:
                            existing_lc.add(int(candidate_lc))
                synthetic_rows.pop(int(item["pid"]), None)
                continue
            if item["lc_id"] is not None and item["lc_id"] in existing_lc:
                continue
            if item["lc_id"] is not None:
                existing_lc.add(item["lc_id"])
            rows.append((item["pid"], item["status"], item["lang"], item["runtime_ms"], item["memory_kb"],
                         item["submitted_at"], "sync", item["lc_id"]))
        if rows:
            connection.executemany(
                """INSERT INTO submissions(problem_id, status, lang, runtime_ms, memory_kb, submitted_at, source, lc_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", rows,
            )
        results["submissions_added"] = len(rows)
        for pair in data.get("stat_status_pairs", []):
            if pair.get("status") != "ac":
                continue
            pid = slug_to_id.get(str(pair.get("stat", {}).get("question__title_slug") or ""))
            if pid is None:
                continue
            found = connection.execute(
                "SELECT 1 FROM submissions WHERE problem_id = ? AND status = 'ac' LIMIT 1", (pid,)
            ).fetchone()
            if found:
                results["solved_existing"] = int(results["solved_existing"]) + 1
                continue
            connection.execute(
                """INSERT INTO submissions(problem_id, status, lang, submitted_at, source, lc_id)
                   VALUES (?, 'ac', '', ?, 'sync', NULL)""", (pid, runtime.now_parts()[0]),
            )
            results["solved_added"] = int(results["solved_added"]) + 1
        connection.commit()
        if progress is not None:
            progress("提交记录已写入本地数据库")
    results["sync_errors"] = fetch_errors
    if partial_error_category is not None:
        results["partial"] = True
        results["degraded"] = True
        results["partial_error_category"] = partial_error_category
    runtime._invalidate_learning_caches(db_path)
    return results


async def leetcode_sync_async(
    credentials: dict[str, str],
    db_path: Path = DB_PATH,
    limit: int = 100,
    full: bool = False,
    progress=None,
    offset: int = 0,
) -> dict[str, object]:
    """Run the existing sync/SQLite workflow without blocking an async caller."""
    return await asyncio.to_thread(
        leetcode_sync, credentials, db_path, limit, full, progress, offset
    )


def start_leetcode_sync_task(
    credentials: dict[str, str],
    full: bool,
    owner: str = "",
    db_path: Path = DB_PATH,
    offset: int = 0,
    action_id: str = "",
) -> str:
    runtime = server_runtime
    reused_task_id: str | None = None
    task_id: str | None = None
    task: dict[str, object] | None = None

    # Check and insert are one atomic operation.  The task manager remains the
    # source of truth; this only prevents duplicate work for one owner.
    with SYNC_TASKS_LOCK:
        for existing_id, existing in SYNC_TASKS.items():
            if str(existing.get("owner", "")) == owner and bool(existing.get("running")):
                if bool(existing.get("full")) == bool(full):
                    reused_task_id = str(existing_id)
                else:
                    raise LeetCodeSyncError(
                        "sync_in_progress",
                        f"已有{'全量' if bool(existing.get('full')) else '增量'}同步任务运行中，请稍后重试",
                        HTTPStatus.CONFLICT,
                    )
                break
        if reused_task_id is None:
            if not try_acquire_sync_owner(owner):
                raise LeetCodeSyncError(
                    "sync_in_progress", "已有力扣同步任务运行中，请稍后重试", HTTPStatus.CONFLICT
                )
            task_id = uuid.uuid4().hex[:12]
            task = {
                "logs": [], "running": True, "result": None, "error": None,
                "error_category": None, "partial": False, "degraded_category": None,
                "owner": owner, "full": bool(full),
                "offset": _normalize_sync_offset(offset) if full else 0,
                "action_id": str(action_id or ""),
                "created_at": runtime.now_iso(),
                "started_at": None, "finished_at": None,
            }
            SYNC_TASKS[task_id] = task

    if reused_task_id is not None:
        _safe_log_event(
            "leetcode_sync_reused", module="leetcode", task_id=reused_task_id,
            owner=owner, full=bool(full),
        )
        return reused_task_id

    assert task is not None
    assert task_id is not None
    started_monotonic: float | None = None

    def progress(text: str) -> None:
        with SYNC_TASKS_LOCK:
            logs = task["logs"]
            if isinstance(logs, list):
                logs.append({"text": text, "at": runtime.now_parts()[0]})

    def worker() -> None:
        nonlocal started_monotonic
        started_monotonic = time.monotonic()
        task["started_at"] = runtime.now_iso()
        _safe_log_event(
            "leetcode_sync_started", module="leetcode", task_id=task_id,
            owner=owner, full=bool(full), duration_ms=0,
        )
        try:
            if task["offset"]:
                result = runtime.leetcode_sync(
                    credentials, db_path=db_path, full=full, offset=task["offset"], progress=progress
                )
            else:
                # Keep the legacy composition-root seam callable by existing workers/tests.
                result = runtime.leetcode_sync(credentials, db_path=db_path, full=full, progress=progress)
            task["result"] = result
            if isinstance(result, dict) and bool(result.get("partial")):
                task["partial"] = True
                task["degraded_category"] = result.get("partial_error_category")
                task["error"] = "同步部分完成，请稍后重试"
                task["error_category"] = "partial"
        except LeetCodeSyncError as exc:
            task["error"] = exc.user_message
            task["error_category"] = exc.category
        except Exception:  # noqa: BLE001
            task["error"] = "同步服务暂时不可用，请稍后重试"
            task["error_category"] = "server_error"
        finally:
            try:
                runtime._invalidate_learning_caches(db_path)
            finally:
                with SYNC_TASKS_LOCK:
                    task["running"] = False
                    task["finished_at"] = runtime.now_iso()
                    result = task.get("result")
                    if isinstance(result, dict):
                        seen = int(result.get("submissions_seen") or 0)
                        added = int(result.get("submissions_added") or 0)
                    else:
                        seen = added = 0
                    error_category = task.get("error_category")
                    partial = bool(task.get("partial"))
                    degraded_category = task.get("degraded_category")
                    finished_at = str(task.get("finished_at") or runtime.now_iso())
                    duration_ms = int((time.monotonic() - started_monotonic) * 1000) if started_monotonic is not None else None
                    release_sync_owner(owner)
                    action_id_value = str(task.get("action_id") or "")
                if partial:
                    event = "leetcode_sync_partial"
                    event_category = str(degraded_category or "partial")
                elif error_category:
                    event = "leetcode_sync_failed"
                    event_category = str(error_category)
                else:
                    event = "leetcode_sync_succeeded"
                    event_category = None
                fields = {
                    "module": "leetcode", "task_id": task_id, "owner": owner,
                    "full": bool(full), "duration_ms": duration_ms,
                    "submissions_seen": seen, "submissions_added": added,
                }
                if event_category is not None:
                    fields["error_category"] = event_category
                _safe_log_event(event, **fields)
                _record_sync_action_background_result(
                    db_path=db_path,
                    action_id=action_id_value,
                    task_id=task_id,
                    status="partial" if partial else ("failed" if error_category else "succeeded"),
                    error_category=str(degraded_category or error_category or "") or None,
                    partial=partial,
                    result=result if isinstance(result, dict) else None,
                    finished_at=finished_at,
                )

    threading.Thread(target=worker, daemon=True).start()
    with SYNC_TASKS_LOCK:
        completed = [tid for tid, item in SYNC_TASKS.items() if not item["running"]]
        for tid in completed[:-10]:
            SYNC_TASKS.pop(tid, None)
    return task_id


def sync_task_status(task_id: str, owner: str = "") -> dict[str, object] | None:
    runtime = server_runtime
    with SYNC_TASKS_LOCK:
        task = SYNC_TASKS.get(task_id)
        if task is None or str(task.get("owner", "")) != owner:
            return None
        return {
            "task_id": task_id, "running": bool(task["running"]),
            "logs": list(task["logs"]), "result": task["result"],
            "error": task["error"], "error_category": task.get("error_category"),
            "partial": bool(task.get("partial")),
            "degraded_category": task.get("degraded_category"),
        }


def admin_list_sync_tasks() -> list[dict[str, object]]:
    """Return a credential-free projection of process-local sync tasks."""
    with SYNC_TASKS_LOCK:
        items: list[dict[str, object]] = []
        for task_id, task in SYNC_TASKS.items():
            logs = task.get("logs")
            items.append({
                "task_id": str(task_id),
                "owner": str(task.get("owner", "")),
                "running": bool(task.get("running")),
                "error_category": task.get("error_category"),
                "partial": bool(task.get("partial")),
                "degraded_category": task.get("degraded_category"),
                "created_at": task.get("created_at"),
                "started_at": task.get("started_at"),
                "finished_at": task.get("finished_at"),
                "log_count": len(logs) if isinstance(logs, list) else 0,
            })
        return items


from interview_forge.runtime.task_manager import TaskBackend, task_manager


def _registered_submit(*args, **kwargs):
    return server_runtime.start_leetcode_sync_task(*args, **kwargs)


def _registered_query(*args, **kwargs):
    return server_runtime.sync_task_status(*args, **kwargs)


task_manager.register(
    "leetcode",
    TaskBackend(
        submit=_registered_submit,
        query=_registered_query,
    ),
)


def _parse_ms(text: str) -> int | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(ms)?", text, re.I)
    return int(float(match.group(1))) if match else None


def _parse_kb(text: str) -> int | None:
    match = re.search(r"([\d.]+)\s*(KB|MB|GB)?", text, re.I)
    if not match:
        return None
    value = float(match.group(1))
    unit = (match.group(2) or "").upper()
    if unit == "MB":
        value *= 1024
    elif unit == "GB":
        value *= 1024 * 1024
    return int(value)
