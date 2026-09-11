"""Dependency defaults for the FastAPI composition root.

The legacy command binds ``server_runtime`` to its compatibility facade.  A
direct ASGI import must not need that module, so these small defaults provide
paths, clock and service callbacks without importing an HTTP handler.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from interview_forge.core.paths import AUTH_DB_PATH, DATA_DIR, DB_PATH, ROOT, USERS_DIR
from interview_forge.db.connection import connect as _db_connect
from interview_forge.services.catalog import load_library_manifest
from interview_forge.services.review import due_after as _due_after, due_after_content as _due_after_content
from scripts.build.build_hot100 import LEETCODE_SLUGS, PROBLEM_BY_ID, problem_filename
from interview_forge.services.submissions import VALID_SUBMIT_SOURCES

try:
    from zoneinfo import ZoneInfo
    BUSINESS_TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # pragma: no cover - minimal Python installations
    BUSINESS_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")

SESSION_TTL = timedelta(days=30)
PERMANENT_ADMIN_USERNAME = "2030309470"
AI_DAILY_LIMIT_DEFAULT = 3
AI_DAILY_LIMIT_MAX = 100
ROUND_COMPLETE_THRESHOLD = 90
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")
_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_AUTH_READY = False
_AUTH_LOCK = threading.Lock()
_LAST_SESSION_PURGE = 0.0


def business_now() -> datetime:
    return datetime.now(BUSINESS_TZ)


def now_iso() -> str:
    return business_now().isoformat(timespec="seconds")


def now_parts() -> tuple[str, str]:
    value = business_now()
    return value.isoformat(timespec="seconds"), value.date().isoformat()


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    return _db_connect(db_path, business_tz=BUSINESS_TZ)


def due_after(completed_at: str, round_no: int) -> str:
    return _due_after(completed_at, round_no, BUSINESS_TZ)


def due_after_content(completed_at: str, round_no: int) -> str:
    return _due_after_content(completed_at, round_no, BUSINESS_TZ)


def valid_content(module_id: str, content_id: str) -> bool:
    manifest = load_library_manifest()
    return any(module.get("id") == module_id and any(ch.get("id") == content_id for ch in module.get("chapters", [])) for module in manifest.get("modules", []))


def valid_content_id(content_id: str) -> bool:
    return any(chapter.get("id") == content_id for module in load_library_manifest().get("modules", []) for chapter in module.get("chapters", []))


def _maybe_purge_sessions() -> None:
    global _LAST_SESSION_PURGE
    current = time.time()
    if current - _LAST_SESSION_PURGE < 86400:
        return
    try:
        from interview_forge.services.auth import connect_auth
        with closing(connect_auth()) as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at < ?", (now_iso(),))
        _LAST_SESSION_PURGE = current
    except sqlite3.Error:
        pass


def _invalidate_dashboard_cache(db_path: Path) -> None:
    from interview_forge.services.study import _invalidate_dashboard_cache as invalidate
    invalidate(db_path)


def _invalidate_learning_caches(db_path: Path) -> None:
    from interview_forge.analytics.cache import invalidate_learning_caches
    invalidate_learning_caches(db_path)


def _load_service_function(module: str, name: str):
    def callback(*args, **kwargs):
        imported = __import__(module, fromlist=[name])
        return getattr(imported, name)(*args, **kwargs)
    return callback


# Runtime callbacks used by domain modules that retain their established
# monkey-patch-compatible seams.  They resolve lazily to avoid import cycles.
dashboard_data = _load_service_function("interview_forge.services.study", "dashboard_data")
daily_data = _load_service_function("interview_forge.services.study", "daily_data")
get_settings = _load_service_function("interview_forge.services.study", "get_settings")
problem_marks = _load_service_function("interview_forge.services.study", "problem_marks")
problem_review_state = _load_service_function("interview_forge.services.study", "problem_review_state")
ac_problem_progress = _load_service_function("interview_forge.services.study", "ac_problem_progress")
submission_summary = _load_service_function("interview_forge.services.submissions", "submission_summary")


def _ai_task_callback(name: str):
    return _load_service_function("interview_forge.ai.tasks", name)


create_ai_task = _ai_task_callback("create_ai_task")
get_ai_task = _ai_task_callback("get_ai_task")
cancel_ai_task = _ai_task_callback("cancel_ai_task")
start_leetcode_sync_task = _load_service_function("interview_forge.services.leetcode", "start_leetcode_sync_task")
sync_task_status = _load_service_function("interview_forge.services.leetcode", "sync_task_status")
_lc_http_get = _load_service_function("interview_forge.services.leetcode", "_lc_http_get")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=1 << 14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))

# Compatibility seams used by the service modules when the ASGI app is
# imported directly.  Each callback is lazy so importing the app does not
# initialize optional providers or a user's SQLite file.
connect_auth = _load_service_function("interview_forge.services.auth", "connect_auth")
validate_nickname = _load_service_function("interview_forge.services.auth", "validate_nickname")
get_ai_quota = _load_service_function("interview_forge.ai.quota", "get_ai_quota")
reset_ai_quota = _load_service_function("interview_forge.ai.quota", "reset_ai_quota")
get_weather_preference = _load_service_function("interview_forge.services.weather", "get_weather_preference")
_fetch_weather = _load_service_function("interview_forge.services.weather", "_fetch_weather")
_rank_weather_location = _load_service_function("interview_forge.services.weather", "_rank_weather_location")
_weather_http_json = _load_service_function("interview_forge.services.weather", "_weather_http_json")
_weather_key_lock = _load_service_function("interview_forge.services.weather", "_weather_key_lock")
_fetch_json_with_retry = _load_service_function("interview_forge.services.leetcode", "_fetch_json_with_retry")
_parse_kb = _load_service_function("interview_forge.services.leetcode", "_parse_kb")
_parse_ms = _load_service_function("interview_forge.services.leetcode", "_parse_ms")
leetcode_status = _load_service_function("interview_forge.services.leetcode", "leetcode_status")
leetcode_sync = _load_service_function("interview_forge.services.leetcode", "leetcode_sync")
_ANALYTICS_TTL = 60.0
_DASH_TTL = 60.0
_ANALYTICS_CACHE_MAX_ENTRIES = 256
_ANALYTICS_GENERATION_MAX_ENTRIES = 256
ANALYTICS_RULE_VERSION = "rules-v1"
ANALYTICS_SCHEMA_VERSION = "analytics-v1"
build_learning_analytics = _load_service_function("interview_forge.analytics.learning_analytics", "build_learning_analytics")

from interview_forge.runtime.task_manager import task_manager
