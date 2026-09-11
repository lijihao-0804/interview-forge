"""LeetCode credentials, status checks and incremental sync business logic.

The HTTP assembly remains the compatibility surface.  Runtime dependencies
are resolved lazily so existing tests and callers can replace the server's
database path, catalog, cache invalidation and provider retry hooks exactly as
before.  No credential is logged or included in errors.
"""
from __future__ import annotations

import io
import json
import re
import threading
import time
import urllib.error
import uuid
from contextlib import closing
from datetime import datetime
from http import HTTPStatus
from pathlib import Path

from interview_forge.core.paths import DB_PATH


def _runtime():
    from interview_forge.server import study_server

    return study_server


def get_credentials(db_path: Path = DB_PATH):
    runtime = _runtime()
    with closing(runtime.connect(db_path)) as connection:
        rows = connection.execute("SELECT key, value FROM credentials").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def set_credentials(pairs: dict[str, str], db_path: Path = DB_PATH) -> None:
    runtime = _runtime()
    studied_at, _ = runtime.now_parts()
    with closing(runtime.connect(db_path)) as connection:
        for key, value in pairs.items():
            if key not in ("leetcode_session", "leetcode_csrf"):
                continue
            if not isinstance(value, str):
                continue
            connection.execute(
                """INSERT INTO credentials(key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                (key, value.strip(), studied_at),
            )
            connection.commit()


def clear_credentials(db_path: Path = DB_PATH) -> None:
    runtime = _runtime()
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
            return json.loads(_runtime()._lc_http_get(url, headers, timeout).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in (403, 429, 500, 502, 503, 504):
                raise
        except Exception as exc:  # noqa: BLE001 - 网络抖动统一走退避重试
            last_error = exc
        if attempt + 1 < retries:
            time.sleep(backoff * (2**attempt))
    if isinstance(last_error, urllib.error.HTTPError):
        raise last_error
    raise last_error


def lc_status_cached(db_path: Path, credentials: dict[str, str], force: bool = False) -> dict:
    runtime = _runtime()
    key = (str(db_path), credentials.get("leetcode_session", ""))
    now = time.time()
    if not force:
        with runtime._LC_STATUS_LOCK:
            hit = runtime._LC_STATUS_CACHE.get(key)
            if hit and now - hit[0] < runtime.LC_STATUS_TTL:
                return hit[1]
    result = runtime.leetcode_status(credentials)
    with runtime._LC_STATUS_LOCK:
        runtime._LC_STATUS_CACHE[key] = (now, result)
    return result


def lc_status_invalidate(db_path: Path) -> None:
    runtime = _runtime()
    with runtime._LC_STATUS_LOCK:
        for key in [key for key in runtime._LC_STATUS_CACHE if key[0] == str(db_path)]:
            runtime._LC_STATUS_CACHE.pop(key, None)


def leetcode_status(credentials: dict[str, str], timeout: int = 20) -> dict[str, object]:
    if not credentials.get("leetcode_session"):
        return {"connected": False, "reason": "no-session", "message": "尚未保存 LEETCODE_SESSION"}
    try:
        data = json.loads(_runtime()._lc_http_get(
            "https://leetcode.cn/api/problems/all/", _leetcode_headers(credentials), timeout
        ).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_head = b""
        try:
            body_head = exc.read(500)
        except Exception:  # noqa: BLE001
            pass
        if b"Just a moment" in body_head:
            return {
                "connected": False,
                "reason": "cloudflare",
                "message": "出口 IP 被力扣 Cloudflare 拦截（非会话问题）；在服务器执行 pip3 install curl_cffi 后重启服务即可",
            }
        if exc.code in (401, 403):
            return {"connected": False, "reason": "expired", "message": "会话无效或已过期（HTTP %s）" % exc.code}
        return {"connected": False, "reason": "http", "message": "力扣返回 HTTP %s" % exc.code}
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "reason": "network", "message": f"网络错误：{type(exc).__name__}"}
    user_name = str(data.get("user_name") or "")
    num_solved = int(data.get("num_solved") or 0)
    if user_name:
        return {"connected": True, "user_name": user_name, "num_solved": num_solved}
    return {"connected": False, "reason": "anonymous", "message": "返回匿名数据，会话未生效"}


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


def _leetcode_sync_http_error(exc) -> LeetCodeSyncError:
    body_head = b""
    try:
        body_head = exc.read(500)
    except Exception:  # noqa: BLE001
        pass
    if b"Just a moment" in body_head:
        return LeetCodeSyncError("provider_blocked", "力扣暂时拒绝了服务器连接，请稍后重试", HTTPStatus.BAD_GATEWAY)
    if exc.code in (401, 403):
        return LeetCodeSyncError("session_invalid", "LEETCODE_SESSION 已过期或无效，请前往力扣连接页面更新", HTTPStatus.UNAUTHORIZED)
    if exc.code == 429:
        return LeetCodeSyncError("provider_rate_limited", "力扣请求较频繁，请稍后重试", HTTPStatus.SERVICE_UNAVAILABLE)
    return LeetCodeSyncError("provider_unavailable", "力扣服务暂时不可用，请稍后重试", HTTPStatus.BAD_GATEWAY)


def leetcode_sync(
    credentials: dict[str, str],
    db_path: Path = DB_PATH,
    limit: int = 100,
    full: bool = False,
    progress=None,
) -> dict[str, object]:
    runtime = _runtime()
    if not credentials.get("leetcode_session"):
        raise LeetCodeSyncError("not_configured", "请先前往力扣连接页面填写 LEETCODE_SESSION", HTTPStatus.CONFLICT)
    headers = _leetcode_headers(credentials)
    results: dict[str, object] = {
        "solved_added": 0, "solved_existing": 0,
        "submissions_added": 0, "submissions_seen": 0, "sync_errors": [],
        "full": bool(full),
    }
    try:
        data = runtime._fetch_json_with_retry("https://leetcode.cn/api/problems/all/", headers)
    except urllib.error.HTTPError as exc:
        raise _leetcode_sync_http_error(exc) from None
    except Exception:  # noqa: BLE001
        raise LeetCodeSyncError("network_error", "连接力扣失败，请检查网络后重试", HTTPStatus.BAD_GATEWAY) from None
    if not str(data.get("user_name") or ""):
        raise LeetCodeSyncError("session_invalid", "LEETCODE_SESSION 已过期或无效，请前往力扣连接页面更新", HTTPStatus.UNAUTHORIZED)
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
    offset = 0
    page = 0
    max_pages = 50 if full else 1
    if progress is not None:
        progress("开始拉取提交记录")
    while True:
        page += 1
        if page > max_pages:
            fetch_errors.append(f"已达分页上限（{max_pages} 页），如有更多历史请再次全量同步")
            break
        try:
            payload = runtime._fetch_json_with_retry(
                f"https://leetcode.cn/api/submissions/?offset={offset}&limit={min(int(limit), 100)}",
                headers,
            )
        except Exception as exc:  # noqa: BLE001
            fetch_errors.append(
                f"第 {page} 页拉取失败：{type(exc).__name__}: {exc}（已自动重试，仍失败可能是力扣风控，请稍后重试或重新复制 LEETCODE_SESSION）"
            )
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
        if not payload.get("has_next"):
            break
        time.sleep(0.8)
        offset += len(dump)

    with closing(runtime.connect(db_path)) as connection:
        existing_lc = {
            int(row["lc_id"])
            for row in connection.execute("SELECT lc_id FROM submissions WHERE lc_id IS NOT NULL").fetchall()
        }
        rows: list[tuple[object, ...]] = []
        for item in collected:
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
        connection.commit()
        if progress is not None:
            progress("提交记录已写入本地数据库")
        earliest_ac: dict[int, str] = {}
        for pid in slug_to_id.values():
            found = connection.execute(
                "SELECT 1 FROM submissions WHERE problem_id = ? AND status = 'ac' LIMIT 1", (pid,)
            ).fetchone()
            if found:
                results["solved_existing"] = int(results["solved_existing"]) + 1
                continue
            times = [item["submitted_at"] for item in collected if item["pid"] == pid and item["status"] == "ac"]
            if times:
                earliest_ac[pid] = min(times)
        for pair in data.get("stat_status_pairs", []):
            if pair.get("status") != "ac":
                continue
            pid = slug_to_id.get(str(pair.get("stat", {}).get("question__title_slug") or ""))
            if pid is None or pid not in earliest_ac:
                continue
            connection.execute(
                """INSERT INTO submissions(problem_id, status, lang, submitted_at, source, lc_id)
                   VALUES (?, 'ac', '', ?, 'sync', NULL)""", (pid, earliest_ac[pid]),
            )
            results["solved_added"] = int(results["solved_added"]) + 1
        connection.commit()
    results["sync_errors"] = fetch_errors
    runtime._invalidate_learning_caches(db_path)
    return results


def start_leetcode_sync_task(credentials: dict[str, str], full: bool, owner: str = "", db_path: Path = DB_PATH) -> str:
    runtime = _runtime()
    task_id = uuid.uuid4().hex[:12]
    task: dict[str, object] = {
        "logs": [], "running": True, "result": None, "error": None,
        "error_category": None, "owner": owner,
    }

    def progress(text: str) -> None:
        with runtime.SYNC_TASKS_LOCK:
            logs = task["logs"]
            if isinstance(logs, list):
                logs.append({"text": text, "at": runtime.now_parts()[0]})

    def worker() -> None:
        try:
            task["result"] = runtime.leetcode_sync(credentials, db_path=db_path, full=full, progress=progress)
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
                with runtime.SYNC_TASKS_LOCK:
                    task["running"] = False

    with runtime.SYNC_TASKS_LOCK:
        runtime.SYNC_TASKS[task_id] = task
    threading.Thread(target=worker, daemon=True).start()
    with runtime.SYNC_TASKS_LOCK:
        completed = [tid for tid, item in runtime.SYNC_TASKS.items() if not item["running"]]
        for tid in completed[:-10]:
            runtime.SYNC_TASKS.pop(tid, None)
    return task_id


def sync_task_status(task_id: str, owner: str = "") -> dict[str, object] | None:
    runtime = _runtime()
    with runtime.SYNC_TASKS_LOCK:
        task = runtime.SYNC_TASKS.get(task_id)
        if task is None or str(task.get("owner", "")) != owner:
            return None
        return {
            "task_id": task_id, "running": bool(task["running"]),
            "logs": list(task["logs"]), "result": task["result"],
            "error": task["error"], "error_category": task.get("error_category"),
        }


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
