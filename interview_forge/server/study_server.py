# ============================================================================
# study_server.py —— Interview Forge后端（纯 Python 标准库 + SQLite 的本地 HTTP 服务）
#
# 职责总述（这个文件做了什么）：
#   1) 静态文件服务：以项目根目录 ROOT 为文档根目录，直接服务网页/题解/题库等静态资源；
#   2) REST API：提供 /api/* JSON 接口（仪表盘、每日计划、书架、导出、力扣同步等）；
#   3) 学习记录：所有学习行为（浏览/完成轮次/提交/标记/设置）持久化到 SQLite 单文件数据库；
#   4) 力扣同步：读取本机保存的 LEETCODE_SESSION，拉取力扣提交历史写回本地库（只读力扣、写本地）；
#   5) 认证与多用户：账号存 data/auth.db（scrypt 哈希 + 服务端会话），全站登录后才能访问；
#      每个用户在 data/users/<用户名>/ 拥有独立学习库，注册需管理员签发的一次性注册码。
#
# 启动方式（在学习站根目录下）：
#   python tools/study_server.py [--host 127.0.0.1] [--port 8765]
#       --open       启动后自动打开浏览器
#       --init-only  只初始化数据库后退出（建表用途）
#       --quiet      不打印每一条请求日志
#   （配套校验脚本 tools/check_hot100.py：检查题库/文档完整性，与此服务相互独立）
#
# 数据表一览（SCHEMA 里的六张表，均为 IF NOT EXISTS 幂等创建）：
#   study_events   题目学习事件流：view（浏览，round_no 为空）/ complete（完成，必须带轮次）
#   content_events 书架章节事件流：与 study_events 结构对称，服务"阅读+理解"型内容的间隔复习
#   marks          标记表：(problem|content, target_id) → mastered / reviewing / weak，主键即二元组
#   settings       键值配置表：key 为 PRIMARY KEY，value 为字符串（目前仅 daily_goal_rounds）
#   submissions    力扣提交记录表：ac/wa、语言、耗时/内存、提交时间、来源、力扣提交 ID（lc_id）
#   credentials    力扣登录凭证表：LEETCODE_SESSION / leetcode_csrf，明文保存在本机
#
# 间隔重复模型（简化 FSRS）：
#   完成第 n 轮后按查表拿到"下次复习间隔天数"，到期日 = 完成时间 + 间隔；
#   "到期日 <= 今天" 的条目就是"今日待复习"（见 daily_data / today_plan）。
# ============================================================================
from __future__ import annotations

# ---- 标准库导入分组说明 ----
# argparse      命令行参数（--host/--port/--open/--init-only/--quiet/--create-admin）
# json / sqlite3 HTTP 请求体解析、数据库读写（本库核心存储）
# hashlib/hmac/secrets  scrypt 密码哈希与校验、随机会话令牌与注册码
# random / re    随机抽题（今日推荐/组卷）、文本匹配（题解锚点、力扣耗时解析）
# http.server    标准库 HTTP 服务器（ThreadingHTTPServer 每请求一线程）
# urllib.parse   URL 解析/中文路径解码/查询参数解析
# build_hot100   同目录下的题库构建模块：题目清单（PROBLEM_BY_ID）、力扣 slug 映射、文件名规则
import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import random
import re
import secrets
import sqlite3
import sys
import tempfile
import threading
import time
import unicodedata
import uuid
import webbrowser
from contextlib import closing, suppress
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python versions without zoneinfo
    ZoneInfo = None  # type: ignore[assignment,misc]
    ZoneInfoNotFoundError = LookupError  # type: ignore[assignment,misc]

if ZoneInfo is not None:
    try:
        BUSINESS_TZ = ZoneInfo("Asia/Shanghai")
    except ZoneInfoNotFoundError:  # minimal Windows/Python installs without tzdata
        BUSINESS_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")
else:  # pragma: no cover - retained for Python < 3.9 compatibility
    BUSINESS_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")

from scripts.build.build_hot100 import LEETCODE_SLUGS, PROBLEM_BY_ID, problem_filename
from interview_forge.analytics.learning_analytics import (
    AnalyticsUnavailableError,
    RULE_VERSION as ANALYTICS_RULE_VERSION,
    SCHEMA_VERSION as ANALYTICS_SCHEMA_VERSION,
    build_learning_analytics,
)
from interview_forge.analytics.context_compiler import compile_learning_context
from interview_forge.analytics.cache import (
    _analytics_build_finished_locked,
    _analytics_build_started_locked,
    _analytics_cache_has_path_locked,
    _analytics_cache_key,
    _analytics_cache_prefix,
    _analytics_cache_scope,
    _analytics_resolved_path,
    _invalidate_analytics_cache,
    _prune_analytics_cache_locked,
    _prune_analytics_generations_locked,
    analytics_cached,
    invalidate_learning_caches as _invalidate_learning_caches,
    _ANALYTICS_CACHE,
    _ANALYTICS_CACHE_LOCK,
    _ANALYTICS_CACHE_GENERATIONS,
    _ANALYTICS_GENERATION_TOUCHED,
    _ANALYTICS_CACHE_ACTIVE,
)
from interview_forge.ai.ai_coach import (
    AI_DB_SCHEMA,
    AI_DAILY_LIMIT,
    AIServiceError,
    cancel_ai_task,
    create_ai_task,
    get_ai_task,
    get_recent_ai_tasks,
    get_ai_quota,
    reset_ai_quota,
    ai_capability,
    ensure_ai_schema,
    debug_ai_event,
    submit_ai_feedback,
)
from interview_forge.services.review import (
    REVIEW_INTERVALS,
    REVIEW_INTERVALS_CONTENT,
    due_after as _due_after,
    due_after_content as _due_after_content,
    review_interval as _review_interval,
    review_interval_content as _review_interval_content,
)
from interview_forge.server.rate_limit import (
    login_rate_limit_clear,
    login_rate_limit_fail,
    login_rate_limit_ok,
    register_rate_limit_ok,
    register_rate_limit_record,
)
from interview_forge.services.weather import (
    WeatherServiceError,
    _WEATHER_DEFAULT,
    _WEATHER_FRESH_DEFAULT,
    _WEATHER_FRESH_CUSTOM,
    _WEATHER_STALE_MAX,
    _WEATHER_SEARCH_TTL,
    _WEATHER_SEARCH_VERSION,
    _WEATHER_CACHE,
    _WEATHER_SEARCH_CACHE,
    _WEATHER_CACHE_LOCK,
    _WEATHER_KEY_LOCKS,
    _WEATHER_KEY_LOCKS_LOCK,
    _CN_MAJOR_CITIES,
    _PLACE_FEATURE_RANK,
    _administrative_name,
    _fetch_weather,
    _normalize_place,
    _rank_weather_location,
    _weather_code,
    _weather_http_json,
    _weather_key_lock,
    _weather_response,
    get_weather_preference,
    search_weather_locations,
    set_weather_preference,
    weather_for_user,
)
from interview_forge.services.leetcode import (
    LeetCodeSyncError,
    LC_STATUS_TTL,
    _LC_STATUS_CACHE,
    _LC_STATUS_LOCK,
    SYNC_TASKS,
    SYNC_TASKS_LOCK,
    _fetch_json_with_retry,
    _lc_http_get,
    _leetcode_headers,
    _leetcode_sync_http_error,
    _parse_kb,
    _parse_ms,
    clear_credentials,
    get_credentials,
    lc_status_cached,
    lc_status_invalidate,
    leetcode_status,
    leetcode_sync,
    set_credentials,
    start_leetcode_sync_task,
    sync_task_status,
)
from interview_forge.services.submissions import (
    VALID_SUBMIT_SOURCES,
    record_submission,
    submission_summary,
    submissions_for_problem,
)
from interview_forge.services.auth import (
    AUTH_SCHEMA,
    _NicknameTrie,
    _NICKNAME_BANNED_KEYS,
    _NICKNAME_COMPACT_MATCHER,
    _NICKNAME_FALLBACK_WORDS,
    _NICKNAME_LEET_MAP,
    _NICKNAME_MATCHER,
    _NICKNAME_MAX,
    _NICKNAME_REPEAT_RE,
    _NICKNAME_TARGETED_RE,
    _NICKNAME_TRADITIONAL_MAP,
    _NICKNAME_WORDLIST_PATH,
    _load_nickname_words,
    _LAST_SEEN_TS,
    _LAST_SEEN_LOCK,
    _LAST_SEEN_INTERVAL,
    admin_reset_user_ai_quota,
    admin_set_user_ai_daily_limit,
    auth_login,
    business_now,
    change_own_password,
    connect_auth,
    create_session,
    create_user,
    destroy_session,
    effective_ai_daily_limit,
    ensure_admin,
    generate_invite_codes,
    hash_password,
    list_invite_codes,
    list_users,
    now_iso,
    register_with_code,
    reset_invalid_nicknames,
    reset_user_nickname,
    reset_user_password,
    revoke_invite_code,
    session_user,
    set_user_active,
    set_user_role,
    user_db_path,
    validate_nickname,
    verify_password,
)
from interview_forge.services.community import (
    _FEEDBACK_ATTEMPTS,
    _FEEDBACK_LOCK,
    _FEEDBACK_WINDOW,
    _FEEDBACK_MAX_PER_IP,
    CHAT_KEEP,
    CHAT_MAX_LEN,
    _CHAT_SEND_LOG,
    _CHAT_SEND_LOCK,
    SOLUTION_LANGS,
    _AVATAR_MAX_BYTES,
    _SEARCH_INDEX,
    _SEARCH_LOCK,
    chat_delete,
    chat_has_older,
    chat_messages_after,
    chat_messages_before,
    chat_rate_limit_ok,
    chat_rate_limit_record,
    chat_send,
    feedback_rate_limit_ok,
    feedback_rate_limit_record,
    get_avatar,
    get_profile,
    list_feedback,
    resolve_feedback,
    search_index_server,
    set_profile,
    submit_feedback,
)


# ---- 路径常量：锁定"项目根 / 数据目录 / 数据库文件"三个位置 ----
# ROOT    由共享路径模块提供，避免源码移动后改变静态文件和数据库位置；
# DATA_DIR  数据目录（data/），放置 SQLite 文件；
# DB_PATH   全部学习记录的唯一落盘位置（data/hot100-study.db）。
from interview_forge.core.paths import AUTH_DB_PATH, DATA_DIR, DB_PATH, ROOT, USERS_DIR
from interview_forge.core.runtime import server_runtime
from interview_forge.runtime.task_manager import task_manager

# Composition root: domain services consume this registry instead of importing
# the HTTP assembly.  Capture the real module when imported normally.  The
# small globals proxy covers ``python tools/study_server.py`` where runpy
# executes this file as ``__main__`` without replacing sys.modules['__main__'].
class _ServerGlobals:
    def __getattr__(self, name: str):
        return globals()[name]

    def __setattr__(self, name: str, value: object) -> None:
        globals()[name] = value


_candidate_owner = sys.modules.get(__name__)
_RUNTIME_OWNER = (
    _candidate_owner
    if _candidate_owner is not None
    and "interview_forge" in str(getattr(_candidate_owner, "__file__", "")).replace("\\", "/")
    else _ServerGlobals()
)
server_runtime.bind_provider(lambda: _RUNTIME_OWNER)
SESSION_COOKIE = "forge_session"
SESSION_TTL = timedelta(days=30)
PERMANENT_ADMIN_USERNAME = "2030309470"
AI_DAILY_LIMIT_DEFAULT = AI_DAILY_LIMIT
AI_DAILY_LIMIT_MAX = 100
# 用户名同时用作 data/users/ 下的目录名：只允许字母数字下划线连字符（2~32 位），
# 从源头排除路径穿越与特殊字符。
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")
# 注册码字符表：去掉易混淆的 0/O/1/I，便于口头转述与抄写。
_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_AUTH_READY = False
_AUTH_LOCK = threading.Lock()

# ---- 间隔重复调度核心：轮次 → 间隔天数 → 到期日 ----
# review_interval(round_no)：第 n 次完成后的下次复习间隔（天），查表 + 夹逼：
#   round_no 落在 [1..6] 时取对应档位；小于 1 按第 1 档、大于 6 按最后一档（60 天封顶）。
# due_after(completed_at, round_no)：完成时间（ISO 带时区）→ 下一次到期日（YYYY-MM-DD 纯日期）。
#   "到期日 <= 今天" 即视为待复习（daily_data 的判断依据）。
def review_interval(round_no: int) -> int:
    """完成第 round_no 轮后的复习间隔（天）。"""
    # 索引公式：round_no-1 是 0 基下标；min/max 双夹逼保证任何输入都不越界。
    return _review_interval(round_no)


def due_after(completed_at: str, round_no: int) -> str:
    """由完成时间与轮次推导下次复习到期日（YYYY-MM-DD）。"""
    # 时间解析链路：ISO 字符串 → 带时区 datetime → 业务时区日期。
    return _due_after(completed_at, round_no, BUSINESS_TZ)


def review_interval_content(round_no: int) -> int:
    """完成第 round_no 轮书架章节后的复习间隔（天）。"""
    # 书架章节走独立间隔序列（首轮 +3d，节奏比题目略缓，适应"阅读+理解"型记忆）。
    return _review_interval_content(round_no)


def due_after_content(completed_at: str, round_no: int) -> str:
    """由完成时间与轮次推导书架章节下次复习到期日（YYYY-MM-DD）。"""
    # 与 due_after 同构：唯一差别是把题目间隔表换成章节专用间隔表。
    return _due_after_content(completed_at, round_no, BUSINESS_TZ)


# ---- SCHEMA：建库 DDL（connect 首次调用时 executescript 一次性执行，全部 IF NOT EXISTS 幂等）----
# 六张表各一句话：
#   study_events   题目事件流：每行一次 view/complete；view 不带轮次，complete 必带递增轮次 round_no；
#   content_events 书架章节事件流：与 study_events 结构对称，维度是 (module_id, content_id)；
#   marks          标记表：(target_type, target_id) 为主键，值为 mastered/reviewing/weak；
#   settings       KV 配置表：key 主键 + value 字符串（当前只有 daily_goal_rounds 每日目标）；
#   submissions    力扣提交记录：ac/wa、语言、耗时/内存、提交时间、来源、力扣提交 ID lc_id（可空）；
#   credentials    力扣登录凭证：LEETCODE_SESSION / leetcode_csrf 明文保存在本机。
# 关键索引/约束的意图：
#   uq_problem_round / uq_content_round 是"仅对 complete 生效"的部分唯一索引：
#       保证同一对象永远不会出现重复轮次 —— 防并发/防重复插写的最后一道保险；
#   ix_study_date / ix_content_date 按日期倒序，支撑"今日/近 14 天/365 天"统计查询；
#   CHECK 约束强制 complete 必须带 round_no、view 必须不带 —— 保证数据自洽。
from interview_forge.db.schema import SCHEMA
from interview_forge.db.connection import (
    _SCHEMA_DONE,
    _SCHEMA_LOCK,
    _backfill_legacy_completes as _db_backfill_legacy_completes,
    _legacy_business_date as _db_legacy_business_date,
    _legacy_submission_timestamp as _db_legacy_submission_timestamp,
    _prepare_legacy_study_events_schema as _db_prepare_legacy_study_events_schema,
    connect as _db_connect,
)


# ---- 模块级进程内状态 ----
# _SCHEMA_DONE     已建表数据库路径集合：多用户下每个用户的库文件首次连接都要各自建表，
#                  因此按"绝对路径"记录，取代旧的全局布尔标记；
# QUIET            请求日志开关（--quiet 或脚本内置 True 后不再打印每条请求）；
# _SCHEMA_LOCK     建表互斥锁：多线程并发首次连接时，保证只有一个线程执行建表；
# _MANIFEST_CACHE  书架 manifest.json 的内存缓存 (mtime, 内容)：文件没改动就直接复用。
QUIET = False
_MANIFEST_CACHE: tuple[float, dict[str, object]] | None = None

_ANALYTICS_TTL = 60.0
_ANALYTICS_CACHE_MAX_ENTRIES = 256
_ANALYTICS_GENERATION_MAX_ENTRIES = 256
_ANALYTICS_WRITE_PATHS = frozenset({
    "/api/complete",
    "/api/content/complete",
    "/api/mark",
    "/api/settings",
    "/api/submit",
    "/api/plan/pin",
    "/api/leetcode/sync",
})


def _prepare_legacy_study_events_schema(connection: sqlite3.Connection) -> None:
    return _db_prepare_legacy_study_events_schema(connection)


def _legacy_business_date(timestamp: object, fallback: object = "") -> str:
    return _db_legacy_business_date(timestamp, fallback, BUSINESS_TZ)


def _legacy_submission_timestamp(timestamp: object, study_date: str) -> str:
    return _db_legacy_submission_timestamp(timestamp, study_date, BUSINESS_TZ)


def _backfill_legacy_completes(connection: sqlite3.Connection) -> None:
    return _db_backfill_legacy_completes(connection, BUSINESS_TZ)


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    return _db_connect(db_path, business_tz=BUSINESS_TZ, ensure_ai_schema=ensure_ai_schema)



# =============================================================================
# 聊天室（公屏）兼容导出：实际状态与业务逻辑归属 community service。
# =============================================================================
# 单轮完成标准：累计 AC 过 ≥90 道题（Hot 100 的 90%）才算完整一轮
ROUND_COMPLETE_THRESHOLD = 90
# 时序侧信道防御：用户名不存在时也跑一次等价 scrypt 校验，抹平"查无此用户"与
# "密码错误"的响应时间差（假哈希与真实校验计算量完全一致）。
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))

# 过期会话每日清理：session_user 每个请求都会调用 _maybe_purge_sessions，
# 但只有距上次清理超过 24 小时才真正执行 DELETE。
_LAST_SESSION_PURGE = 0.0

def _maybe_purge_sessions() -> None:
    """每天清理一次过期会话行，避免 auth.db 无限增长。
    注意：这里不能持有 _AUTH_LOCK（connect_auth 初始化时要拿同一把锁，会自锁）；
    DELETE 幂等，并发重复清理无害，因此无需加锁。"""
    global _LAST_SESSION_PURGE
    now = time.time()
    if now - _LAST_SESSION_PURGE < 86400.0:
        return
    try:
        with closing(connect_auth()) as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at < ?", (now_iso(),))
        _LAST_SESSION_PURGE = now
    except sqlite3.Error:
        pass  # 清理失败不影响主流程，下个请求再试


def now_parts() -> tuple[str, str]:
    """返回 (当前时间 ISO 字符串, 今天日期 YYYY-MM-DD)，是所有写记录统一的时间入口。"""
    now = business_now()
    return now.isoformat(timespec="seconds"), now.date().isoformat()


from interview_forge.services.study import (
    _DASH_CACHE,
    _DASH_CACHE_LOCK,
    _DASH_CACHE_GENERATIONS,
    _DASH_TTL,
    record_view,
    complete_round,
    dashboard_cached,
    _invalidate_dashboard_cache,
    dashboard_data,
    record_content_view,
    complete_content,
    ac_problem_progress,
    problem_review_state,
    library_data,
    daily_data,
    problem_marks,
    get_settings,
    set_setting,
    valid_content_id,
    set_mark,
    problem_note,
    problem_card,
    pick_problem,
    mock_exam,
    today_plan,
    weaklist,
    export_data,
)
def load_library_manifest() -> dict[str, object]:
    """加载书架目录 manifest.json（兼容测试中的 ROOT/缓存 patch 点）。"""
    global _MANIFEST_CACHE
    path = ROOT / "library" / "manifest.json"
    if not path.exists():
        return {"modules": [], "routes": {}}
    mtime = path.stat().st_mtime
    if _MANIFEST_CACHE is not None and _MANIFEST_CACHE[0] == mtime:
        return _MANIFEST_CACHE[1]
    manifest = json.loads(path.read_text(encoding="utf-8"))
    _MANIFEST_CACHE = (mtime, manifest)
    return manifest


def valid_content(module_id: str, content_id: str) -> bool:
    """校验 (module_id, content_id) 是否真实存在于书架 manifest —— 防止不存在的内容写进学习记录。"""
    manifest = load_library_manifest()
    return any(
        module.get("id") == module_id and any(chapter.get("id") == content_id for chapter in module.get("chapters", []))
        for module in manifest.get("modules", [])
    )


class StudyHandler(SimpleHTTPRequestHandler):
    server_version = "Hot100Study/1.0"
    # HTTP/1.1：启用 keep-alive，公网访问省去每请求的 TCP/TLS 握手。
    # 前提：所有响应必须带准确 Content-Length（send_json/静态/头像/导出均已带；
    # 手动 307 跳转补 Content-Length: 0，见 do_GET）。
    protocol_version = "HTTP/1.1"
    # 不注入认证胶囊的页面：登录/注册/管理页自带登录与退出界面。
    AUTH_WIDGET_SKIP_PATHS = {"/pages/login.html", "/pages/register.html", "/pages/admin.html"}
    # 页面增强脚本清单（v 参数用于更新缓存）：导航策略/认证胶囊/反馈/主题切换。
    WIDGET_SCRIPTS = ["/assets/navigation-policy.js?v=1", "/assets/auth-widget.js?v=2", "/assets/feedback-widget.js?v=1", "/assets/theme-toggle.js?v=1"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        # 缓存策略分级（慢链路下回访体验的关键）：
        #   HTML/JSON/manifest → no-store：内容随部署与学习动作实时变化；
        #   CSS/JS → 5 分钟强缓存 + Last-Modified 协商（过期后 304，不重传）；
        #   图片/字体 → 7 天强缓存（静态资源基本不变）。
        # 部署更新 CSS/JS 的场景由 ASSET_VERSION 查询参数与 SW 缓存版本兜底。
        path = getattr(self, "path", "") or ""
        suffix = path.split("?", 1)[0].lower()
        if suffix.endswith((".html", ".json", ".webmanifest")):
            self.send_header("Cache-Control", "no-store")
        elif suffix.endswith((".css", ".js")):
            self.send_header("Cache-Control", "no-cache")   # 每次协商验证（304 秒回），保证部署后立刻新鲜
        elif suffix.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg",
                              ".ico", ".woff", ".woff2", ".ttf", ".mp4")):
            self.send_header("Cache-Control", "public, max-age=604800")
        else:
            self.send_header("Cache-Control", "no-store")
        # 通用安全响应头：禁止 MIME 嗅探；页面只允许同源 iframe（05-可视化 内嵌即为同源）。
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        super().end_headers()

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK,
                  extra_headers: list[tuple[str, str]] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # Cache-Control 由 end_headers 的分级策略统一添加（API 无扩展名 → no-store）。
        # 附加响应头（登录/登出时携带 Set-Cookie）。
        for name, value in (extra_headers or []):
            self.send_header(name, value)
        # CORS：仅放行本机（浏览器扩展/书签脚本跨源到 localhost 提交记录）。
        origin = self.headers.get("Origin", "")
        if origin in ("http://localhost", "http://127.0.0.1", "http://localhost:8765", "http://127.0.0.1:8765"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CSRFToken")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def current_user(self) -> sqlite3.Row | None:
        """解析请求 Cookie 中的会话令牌 → 当前登录用户行；未登录返回 None。"""
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == SESSION_COOKIE:
                try:
                    return session_user(value)
                except sqlite3.Error:
                    return None
        return None

    def do_OPTIONS(self) -> None:
        # CORS 预检：浏览器在跨源 POST（浏览器扩展/书签脚本）前先发 OPTIONS 探测；
        # 来源白名单内回 204 + 允许头（Max-Age 缓存 1 小时），白名单外回 405 拒绝。
        origin = self.headers.get("Origin", "")
        if origin in ("http://localhost", "http://127.0.0.1", "http://localhost:8765", "http://127.0.0.1:8765"):
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CSRFToken")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Max-Age", "3600")
            self.end_headers()
            return
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    def _sensitive_path(self, decoded_path: str) -> bool:
        """敏感/开发者内容判定：先规范化再匹配（防 /x/../data/auth.db 绕过），
        且拒绝任何含 `..` 段的路径 —— SimpleHTTPRequestHandler.translate_path
        会在落盘前再做一次 normpath，前缀黑名单必须以规范化后的路径为准。"""
        import posixpath
        # do_GET normally unquotes once before this check.  Unquote once more
        # here to cover double-encoded traversal/case variants before the
        # filesystem handler normalizes the path on Windows.
        normalized = decoded_path or "/"
        for _ in range(2):
            unquoted = unquote(normalized)
            if unquoted == normalized:
                break
            normalized = unquoted
        # ``posixpath.normpath`` deliberately preserves exactly two leading
        # slashes (POSIX implementation-defined network-path semantics).  The
        # Windows static handler does not preserve that distinction and would
        # still map ``//data/...`` to ROOT/data/..., so canonicalize the URL
        # root before applying the sensitive-path allow/deny rules.
        normalized = "/" + normalized.replace("\\", "/").lstrip("/")
        normalized = posixpath.normpath(normalized)
        lowered = normalized.lower()
        if ".." in lowered.split("/"):
            return True
        # These reports are intentionally public release artifacts referenced
        # by README/guide.  Markdown and every other docs file remain private.
        public_docs = {
            "/docs/qa-report.html",
            "/docs/深度审查与修复报告-2026-09-08.html",
            "/docs/学情分析ai专项审查报告.html",
        }
        if lowered in public_docs:
            return False
        sensitive_prefixes = ("/data/", "/tools/", "/.git/", "/docs/", "/qa-report/")
        return (
            lowered.startswith(sensitive_prefixes)
            or lowered in ("/data", "/tools", "/.git", "/docs", "/maintenance.html", "/guide.html.md")
            or lowered.startswith(("/.", "/maintenance", "/readme"))
            or lowered.endswith(".md")
        )

    def _access_gate(self, decoded_path: str) -> bool:
        """GET/HEAD 共用的安全门禁：敏感路径 404 + 登录门禁。
        返回 False 表示已直接发送错误/跳转响应，调用方应立即 return。"""
        # 敏感/开发者内容不对外：403 = 存在但禁止；404 = 不暴露存在性。
        # data/：数据库与凭证；tools/：服务端脚本；.git 与点文件：版本库与缓存；
        # .md 与 docs/：开发者文档（含部署信息）；maintenance/QA-REPORT：维护与校验报告。
        if self._sensitive_path(decoded_path):
            self.send_error(HTTPStatus.NOT_FOUND)
            return False
        # ---- 认证门禁：未登录页面跳登录页、API 回 401；管理页/管理 API 仅限管理员 ----
        # 公开白名单：登录页、注册页、图标与健康检查。
        user = self.current_user()
        self._gate_user = user  # 复用给 do_GET，避免同请求二次查会话库
        public_get = {"/pages/login.html", "/pages/register.html", "/favicon.ico", "/api/health"}
        # 字体非敏感且登录页也需要，放行（前缀判断）
        public_prefixes = ("/assets/fonts",)
        if user is None and decoded_path not in public_get                 and not decoded_path.startswith(public_prefixes):
            if decoded_path.startswith("/api/"):
                self.send_json({"error": "未登录"}, HTTPStatus.UNAUTHORIZED)
            else:
                self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
                self.send_header("Location", f"/pages/login.html?next={quote(decoded_path)}")
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            return False
        return True

    def do_HEAD(self) -> None:
        """HEAD 与 GET 同门禁：未认证/敏感路径一律拒绝，不允许借 HEAD 探测
        敏感文件的存在与大小；通过门禁后走基类静态头服务（无 body）。"""
        request_target = self.path
        if request_target.startswith("//"):
            request_target = "/" + request_target.lstrip("/")
        parsed = urlparse(request_target)
        decoded_path = unquote(parsed.path)
        if not self._access_gate(decoded_path):
            return
        super().do_HEAD()

    def do_GET(self) -> None:
        # GET 路由总览：安全过滤 → 认证门禁 → 根路径/API 特判 → 浏览埋点 → 兜底静态文件服务。
        request_target = self.path
        if request_target.startswith("//"):
            request_target = "/" + request_target.lstrip("/")
        parsed = urlparse(request_target)
        decoded_path = unquote(parsed.path)
        if not self._access_gate(decoded_path):
            return
        user = getattr(self, "_gate_user", None)
        if decoded_path == "/pages/admin.html" or decoded_path.startswith("/api/admin/"):
            if user is None or str(user["role"]) != "admin":
                if decoded_path.startswith("/api/"):
                    self.send_json({"error": "需要管理员权限"}, HTTPStatus.FORBIDDEN)
                else:
                    self.send_error(HTTPStatus.FORBIDDEN)
                return
        # 已登录用户的独立学习库：本请求内所有 /api/* 读写与浏览埋点都落到该库。
        db = user_db_path(str(user["username"])) if user is not None else DB_PATH
        # 根路径 302 重定向到书架首页 library/index.html："打开学习站"直达内容而非目录列表。
        if parsed.path == "/":
            self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
            self.send_header("Location", "/cockpit.html")
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        # /api/me：当前登录用户信息（登录页/管理页/页面右上角展示用）。
        if parsed.path == "/api/me":
            self.send_json({"username": str(user["username"]), "nickname": str(user["nickname"]),
                            "lang": str(user["lang"]), "role": str(user["role"])})
            return
        # /api/avatar/<用户名>：读取用户头像（登录可见）。
        if decoded_path.startswith("/api/avatar/"):
            target_name = decoded_path[len("/api/avatar/"):]
            avatar = None
            try:
                if USERNAME_RE.match(target_name):
                    avatar = get_avatar(target_name)
            except (ValueError, sqlite3.Error):
                avatar = None
            if avatar is None:
                self.send_json({"error": "未设置头像"}, HTTPStatus.NOT_FOUND)
                return
            mime, blob = avatar
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Cache-Control", "max-age=60")
            self.end_headers()
            self.wfile.write(blob)
            return
        # /api/search：服务端全文搜索（?q=关键词），公网免下载索引。
        if parsed.path == "/api/search":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            try:
                self.send_json({"items": search_index_server(params.get("q", ""))})
            except (OSError, ValueError, json.JSONDecodeError):
                self.send_json({"error": "搜索索引不可用"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        # /api/chat/messages：after 拉增量；before 向前分页；两种游标互斥。
        if parsed.path == "/api/chat/messages":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            if "after" in params and "before" in params:
                self.send_json({"error": "after 与 before 不能同时使用"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                limit = max(1, min(int(params.get("limit", "50")), 100))
            except ValueError:
                self.send_json({"error": "limit 必须是整数"}, HTTPStatus.BAD_REQUEST)
                return
            if "before" in params:
                try:
                    before = int(params["before"])
                except ValueError:
                    self.send_json({"error": "before 必须是整数"}, HTTPStatus.BAD_REQUEST)
                    return
                if before <= 0:
                    self.send_json({"error": "before 必须大于 0"}, HTTPStatus.BAD_REQUEST)
                    return
                items, has_older = chat_messages_before(before, limit)
                self.send_json({"items": items, "has_older": has_older})
                return
            try:
                after = int(params.get("after", "-1"))
            except ValueError:
                self.send_json({"error": "after 必须是整数"}, HTTPStatus.BAD_REQUEST)
                return
            items = chat_messages_after(after, limit)
            oldest_id = int(items[0]["id"]) if items else None
            self.send_json({"items": items, "has_older": chat_has_older(oldest_id) if after < 0 else None})
            return
        # /api/profile：自己的昵称与头像状态。
        if parsed.path == "/api/profile":
            self.send_json(get_profile(str(user["username"])))
            return
        if parsed.path == "/api/weather":
            try:
                self.send_json(weather_for_user(str(user["username"])))
            except WeatherServiceError:
                self.send_json({"error": "天气服务暂时不可用", "error_category": "weather_unavailable",
                                "retryable": True}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if parsed.path == "/api/weather/locations":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            try:
                self.send_json({"items": search_weather_locations(params.get("q", ""))})
            except ValueError as exc:
                self.send_json({"error": str(exc), "error_category": "invalid_query"}, HTTPStatus.BAD_REQUEST)
            except WeatherServiceError:
                self.send_json({"error": "城市搜索暂时不可用", "error_category": "weather_unavailable",
                                "retryable": True}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        # /api/bootstrap：面板打开的一次性拉取（dashboard + daily + settings 合并，
        # 省两个 RTT；dashboard 自带 60 秒缓存）。
        if parsed.path == "/api/bootstrap":
            user_limit = effective_ai_daily_limit(user)
            ai_state = ai_capability(str(user["username"]), str(user["role"]), user_limit)
            ai_state["quota"] = get_ai_quota(
                db, str(user["role"]), daily_limit=user_limit
            )
            self.send_json({
                "dashboard": dashboard_cached(db),
                "daily": daily_data(db),
                "settings": get_settings(db),
                "capabilities": {
                    "ai_coach": ai_state
                },
            })
            return
        # /api/dashboard：仪表盘聚合 —— 今日概览/每题进度/近 14 天/最近活动/365 天热力图/标记与提交统计。
        if parsed.path == "/api/dashboard":
            self.send_json(dashboard_cached(db))
            return
        # /api/coach/analytics：隐藏的只读教练分析快照；数据库路径只来自当前会话用户。
        if parsed.path == "/api/coach/analytics":
            try:
                self.send_json(analytics_cached(db))
            except AnalyticsUnavailableError:
                self.send_json(
                    {"error": "学习分析暂时不可用，请稍后重试", "retryable": True},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    extra_headers=[("Retry-After", "1")],
                )
            except Exception:
                # 包括 ValueError/配置错误：不把路径、SQLite 细节或其它内部信息回显给客户端。
                self.send_json({"error": "学习分析服务暂时不可用"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        # /api/coach/capability：只返回当前账号的服务端能力状态；不暴露密钥、端点或原始模型名。
        if parsed.path == "/api/coach/capability":
            user_limit = effective_ai_daily_limit(user)
            capability = ai_capability(str(user["username"]), str(user["role"]), user_limit)
            capability["quota"] = get_ai_quota(
                db, str(user["role"]), daily_limit=user_limit
            )
            self.send_json({"ai_coach": capability})
            return
        # /api/coach/insights/recent：页面刷新时恢复最近任务，不触发模型调用。
        if parsed.path == "/api/coach/insights/recent":
            try:
                self.send_json(get_recent_ai_tasks(
                    db, str(user["username"]), str(user["role"]),
                    effective_ai_daily_limit(user),
                ))
            except sqlite3.Error:
                self.send_json({"error": "分析记录暂时不可用"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        # /api/coach/tasks/<id>：查询当前用户自己的任务状态和脱敏上下文预览。
        task_match = re.fullmatch(r"/api/coach/tasks/([0-9a-f]{32})", parsed.path)
        if task_match:
            task = get_ai_task(
                db, task_match.group(1), str(user["role"]), effective_ai_daily_limit(user)
            )
            if task is None:
                self.send_json({"error": "任务不存在或已过期"}, HTTPStatus.NOT_FOUND)
            else:
                self.send_json(task)
            return
        # /api/health：健康检查 —— 只回存活状态，不暴露库文件名等内部信息。
        if parsed.path == "/api/health":
            self.send_json({"ok": True})
            return
        # /api/library：书架进度 —— 各模块 total/completed 进度条 + 每章节轮次与最近活动。
        if parsed.path == "/api/library":
            self.send_json(library_data(db))
            return
        # /api/admin/codes：注册码清单（管理员）。
        if parsed.path == "/api/admin/codes":
            self.send_json({"items": list_invite_codes()})
            return
        # /api/admin/users：用户清单（管理员）。
        if parsed.path == "/api/admin/users":
            self.send_json({"items": list_users()})
            return
        # /api/admin/feedback：Bug 反馈清单（管理员）；?status=open/resolved 过滤。
        if parsed.path == "/api/admin/feedback":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            self.send_json({"items": list_feedback(params.get("status", ""))})
            return
        # /api/daily：今日待复习 —— 到期日 <= 今天 的题目与章节；?module= 指定只筛某模块的章节。
        if parsed.path == "/api/daily":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            self.send_json(daily_data(db, module_id=params.get("module", "")))
            return
        # /api/settings：读全部设置 KV（前端初始化时填充每日目标等）。
        if parsed.path == "/api/settings":
            self.send_json(get_settings(db))
            return
        # /api/pick：今日推荐 —— 未完成优先、按最久未碰排序；?random=1 随机抽（"换一题"）。
        if parsed.path == "/api/pick":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            try:
                self.send_json(pick_problem(
                    db_path=db,
                    randomize=params.get("random", "") == "1",
                    category=params.get("category", ""),
                    difficulty=params.get("difficulty", ""),
                ))
            except ValueError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        # /api/mock：模拟组卷 —— 按 ?category/?difficulty 过滤后随机抽 count 道（上限 50，无放回）。
        if parsed.path == "/api/mock":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            try:
                count = max(1, min(int(params.get("count", "10") or "10"), 50))
            except ValueError:
                self.send_json({"error": "count 必须是整数"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                self.send_json(mock_exam(
                    count=count,
                    category=params.get("category", ""),
                    difficulty=params.get("difficulty", ""),
                ))
            except ValueError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        # /api/plan：今日计划 —— 待复习+薄弱题全部纳入，新题补足到 count 道；?random=1 新题随机（"换一组"）。
        if parsed.path == "/api/plan":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            try:
                count = max(1, min(int(params.get("count", "3") or "3"), 20))
            except ValueError:
                self.send_json({"error": "count 必须是整数"}, HTTPStatus.BAD_REQUEST)
                return
            self.send_json(today_plan(db, count=count, randomize=params.get("random", "") == "1"))
            return
        # /api/weaklist：薄弱题清单 —— 带轮次/首次浏览/标记时间，按标记时间排序。
        if parsed.path == "/api/weaklist":
            self.send_json(weaklist(db))
            return
        # /api/submissions：单题提交记录 —— 按 id 倒序最近 limit 条；problem_id 缺失/非法 → 400。
        if parsed.path == "/api/submissions":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            try:
                problem_id = int(params.get("problem_id", ""))
            except ValueError:
                self.send_json({"error": "缺少合法 problem_id"}, HTTPStatus.BAD_REQUEST)
                return
            self.send_json({"problem_id": problem_id, "items": submissions_for_problem(problem_id, db_path=db)})
            return
        # /api/leetcode/sync/status：后台同步任务进度（日志列表 + 完成状态）。
        if parsed.path == "/api/leetcode/sync/status":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            task_id = params.get("task_id", "")
            if not task_id:
                self.send_json({"error": "缺少 task_id"}, HTTPStatus.BAD_REQUEST)
                return
            status = task_manager.query(
                "leetcode", task_id, owner=str(user["username"]) if user is not None else ""
            )
            if status is None:
                self.send_json({"error": "任务不存在或已过期"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json(status)
            return
        # /api/leetcode/status：力扣连接状态 —— 凭证是否已保存 + 实测登录态是否生效，合并成一个响应。
        if parsed.path == "/api/leetcode/status":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            credentials = get_credentials(db)
            status = lc_status_cached(db, credentials, force=params.get("refresh") == "1")
            self.send_json({
                "credentials_saved": bool(credentials.get("leetcode_session")),
                # 安全：会话密钥/CSRF 不回显前端（避免被日志/代理/扩展捕获），
                # 连接页只需要"已保存"布尔与连接状态。
                **status,
            })
            return
        # /api/export：数据导出 —— kind=anki/weak/records/weekly 走 export_data；kind=db 走整库快照。
        if parsed.path == "/api/export":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            if params.get("kind") == "db":
                # db 备份：sqlite3 backup API 在线快照到 data/ 下临时文件（对正在写的库也安全），发送后即删。
                tmp_path: Path | None = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".db", delete=False, dir=str(DATA_DIR)) as tmp:
                        tmp_path = Path(tmp.name)
                    source = sqlite3.connect(db)
                    dest = sqlite3.connect(tmp_path)
                    try:
                        source.backup(dest)
                    finally:
                        dest.close()
                        source.close()
                    body = tmp_path.read_bytes()
                except Exception as exc:
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                    return
                finally:
                    if tmp_path is not None:
                        with suppress(OSError):
                            tmp_path.unlink(missing_ok=True)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", 'attachment; filename="hot100-study.db"')
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            try:
                content_type, filename, data = export_data(params.get("kind", ""), db)
            except ValueError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            body = data.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            # 下载文件名双保险：ascii_name 兼容旧浏览器，filename*=UTF-8'' 用 RFC 5987 携带中文原名。
            ascii_name = {
                "anki": "hot100-anki.csv",
                "weak": "hot100-weak.md",
                "records": "hot100-records.json",
            }.get(params.get("kind", ""), "export.txt")
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}',
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        # 题解页浏览埋点：打开 03-题解/<folder>/<name>.html 时按文件名前 4 位取题号记一次 view；
        #   resolve() + startswith(ROOT) 防路径穿越，埋点解析失败静默忽略（不阻断页面）。
        if decoded_path.startswith("/books/hot100/03-题解/") and decoded_path.lower().endswith(".html"):
            filename = Path(decoded_path).name
            try:
                target = (ROOT / decoded_path.lstrip("/")).resolve()
                if target.is_file() and str(target).startswith(str(ROOT.resolve())):
                    if record_view(int(filename[:4]), db):
                        _invalidate_learning_caches(db)
            except Exception:
                _invalidate_learning_caches(db)
                pass
        # 书架章节埋点：manifest routes 表映射 library/* 路径 → content_id 记章节浏览；
        # 其余路径落到 super().do_GET() 走静态文件服务。
        route = load_library_manifest().get("routes", {}).get(decoded_path)
        if route:
            try:
                if record_content_view(str(route["module_id"]), str(route["content_id"]), db):
                    _invalidate_learning_caches(db)
            except Exception:
                _invalidate_learning_caches(db)
                pass
        # ---- 前端小部件注入：阅读页/面板 HTML 在发送前插入统一导航策略与其他小部件 ----
        # 05-可视化 页面可能被 iframe 内嵌，保持认证/反馈/主题脚本不注入，但仍需要统一导航策略。
        if decoded_path.lower().endswith(".html"):
            if self.serve_html_with_widget(
                decoded_path,
                navigation_only=decoded_path.startswith("/books/hot100/05-可视化/"),
            ):
                return
        super().do_GET()

    def serve_html_with_widget(self, decoded_path: str, navigation_only: bool = False) -> bool:
        """读取 HTML 文件、在 </body> 前注入小部件脚本后发送；文件不存在返回 False 交给默认 404。
        可视化页只注入导航策略；认证胶囊在登录/注册/管理页跳过（它们自带登录界面），反馈按钮全站可见。"""
        try:
            target = (ROOT / decoded_path.lstrip("/")).resolve()
            if not (target.is_file() and str(target).startswith(str(ROOT.resolve()))):
                return False
            body = target.read_bytes()
        except OSError:
            return False
        if navigation_only:
            scripts = ["/assets/navigation-policy.js?v=1"]
        else:
            scripts = [
                s for s in self.WIDGET_SCRIPTS
                if not (s.startswith("/assets/auth-widget") and decoded_path in self.AUTH_WIDGET_SKIP_PATHS)
            ]
        widget = "".join(f'<script src="{s}" defer></script>' for s in scripts).encode()
        idx = body.lower().rfind(b"</body>")
        body = body[:idx] + widget + body[idx:] if idx != -1 else body + widget
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # end_headers 钩子会为 .html 自动附加 Cache-Control: no-store。
        self.end_headers()
        self.wfile.write(body)
        return True

    def do_POST(self) -> None:
        # POST 路由白名单：公开（登录/注册）、管理员、普通登录用户三类，未知路径直接 404
        # （不会误入静态文件服务）。
        parsed = urlparse(self.path)
        path = parsed.path
        public_post = {"/api/login", "/api/register", "/api/feedback"}
        admin_post = {"/api/admin/codes", "/api/admin/codes/revoke", "/api/admin/users/toggle",
                      "/api/admin/users/role", "/api/admin/users/nickname/reset",
                      "/api/admin/users/ai-quota/reset", "/api/admin/users/ai-quota/limit",
                      "/api/admin/users/reset-password",
                      "/api/admin/feedback/resolve", "/api/admin/chat/delete"}
        known_post = public_post | admin_post | {
            "/api/logout", "/api/password", "/api/profile", "/api/chat/send", "/api/complete",
            "/api/weather/preferences",
            "/api/content/complete", "/api/mark", "/api/settings", "/api/submit",
            "/api/plan/pin",
            "/api/coach/context",
            "/api/coach/analyze",
            "/api/leetcode/connect", "/api/leetcode/sync", "/api/leetcode/clear",
        }
        cancel_match = re.fullmatch(r"/api/coach/tasks/([0-9a-f]{32})/cancel", path)
        feedback_match = re.fullmatch(r"/api/coach/insights/([0-9a-f]{32})/feedback", path)
        if path not in known_post and cancel_match is None and feedback_match is None:
            # The request body is intentionally not parsed for unknown
            # routes; close keep-alive connections so any body cannot poison
            # the next HTTP request on the same socket.
            self.close_connection = True
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        # ---- 认证门禁：公开端点放行；其余需登录；admin_post 需管理员 ----
        user = self.current_user()
        if path not in public_post:
            if user is None:
                self.close_connection = True
                # A hidden POST endpoint can be probed with a body.  Consume
                # its small bounded body before returning 401 so an HTTP/1.1
                # client does not see a reset while the request is still in
                # flight; never read an unbounded unauthenticated body.
                if path == "/api/coach/context":
                    self.close_connection = True
                    try:
                        unauthenticated_length = int(self.headers.get("Content-Length", "0"))
                    except (TypeError, ValueError):
                        unauthenticated_length = 0
                    if 0 < unauthenticated_length <= 4096:
                        self.rfile.read(unauthenticated_length)
                self.send_json({"error": "未登录"}, HTTPStatus.UNAUTHORIZED)
                return
            if path in admin_post and str(user["role"]) != "admin":
                self.close_connection = True
                self.send_json({"error": "需要管理员权限"}, HTTPStatus.FORBIDDEN)
                return
        db = user_db_path(str(user["username"])) if user is not None else DB_PATH
        learning_write_path = path in _ANALYTICS_WRITE_PATHS
        cookie_headers: list[tuple[str, str]] = []
        try:
            # 请求体约束：必须是 JSON 且 1~4096 字节（/api/profile 例外：头像 base64
            # 膨胀 1.33 倍后仍需容纳 150KB 图片，上限放宽到 220KB），空体/超大直接拒绝。
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except (TypeError, ValueError) as exc:
                self.close_connection = True
                raise ValueError("请求大小不正确") from exc
            max_len = 262144 if path == "/api/profile" else 4096
            if length < 1 or length > max_len:
                # The request body has not been consumed.  Close the
                # persistent connection so leftover bytes cannot be parsed as
                # a subsequent HTTP request.
                self.close_connection = True
                raise ValueError("请求大小不正确")
            if self.headers.get("Transfer-Encoding"):
                # Chunked and other transfer codings are unsupported because
                # this handler only reads a bounded Content-Length body.
                self.close_connection = True
                raise ValueError("不支持的 Transfer-Encoding")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("请求参数不正确")
            # /api/coach/context：隐藏的只读上下文编译接口。输入字段是严格
            # 白名单，数据库仍只来自当前会话；context_compiler 本身不写库、不
            # 调模型，也不会把请求中的命令当作规则。
            if path == "/api/coach/context":
                if not isinstance(payload, dict):
                    raise ValueError("请求参数不正确")
                allowed_context_keys = {
                    "task",
                    "user_request",
                    "target_problem_id",
                    "profile",
                    "budget_tier",
                }
                if any(key not in allowed_context_keys for key in payload):
                    raise ValueError("请求参数不正确")
                result = compile_learning_context(
                    analytics_cached(db),
                    task=payload.get("task"),
                    user_request=payload.get("user_request", ""),
                    target_problem_id=payload.get("target_problem_id"),
                    profile=payload.get("profile"),
                    budget_tier=payload.get("budget_tier"),
                )
            # /api/coach/analyze：一键学习情况分析。上下文先由确定性编译器生成，
            # 创建任务后立即返回；客户端不能指定模型、用户、数据库或快照。
            elif path == "/api/coach/analyze":
                if not isinstance(payload, dict) or payload:
                    raise ValueError("请求参数不正确")
                analytics_started = time.perf_counter()
                analytics = analytics_cached(db)
                analytics_ms = round((time.perf_counter() - analytics_started) * 1000, 2)
                compile_started = time.perf_counter()
                context = compile_learning_context(
                    analytics,
                    task="learning_diagnosis",
                    budget_tier="small",
                )
                compile_ms = round((time.perf_counter() - compile_started) * 1000, 2)
                create_started = time.perf_counter()
                result = task_manager.submit(
                    "ai",
                    db, context, str(user["username"]), str(user["role"]),
                    effective_ai_daily_limit(user),
                )
                debug_context_metadata: dict[str, object] = {}
                if os.environ.get("AI_DEBUG_LOG_PATH", "").strip():
                    context_serialized = json.dumps(
                        context,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    debug_context_metadata = {
                        "context_sha256": hashlib.sha256(
                            context_serialized.encode("utf-8")
                        ).hexdigest(),
                        "context_chars": len(context_serialized),
                    }
                debug_ai_event(
                    "request_prepared",
                    task_id=str(result.get("task_id", "")),
                    analytics_ms=analytics_ms,
                    context_compile_ms=compile_ms,
                    task_create_ms=round((time.perf_counter() - create_started) * 1000, 2),
                    snapshot_hash=str(context.get("snapshot_hash", "")),
                    **debug_context_metadata,
                    fact_count=len(context.get("facts", [])) if isinstance(context.get("facts"), list) else 0,
                    signal_count=len(context.get("signals", [])) if isinstance(context.get("signals"), list) else 0,
                    evidence_count=len(context.get("evidence", [])) if isinstance(context.get("evidence"), list) else 0,
                )
            # /api/coach/tasks/<id>/cancel：只允许取消仍在队列中的任务。
            elif cancel_match is not None:
                if not isinstance(payload, dict) or payload:
                    raise ValueError("请求参数不正确")
                result = task_manager.cancel(
                    "ai", db, cancel_match.group(1), str(user["role"]), effective_ai_daily_limit(user)
                )
            # /api/coach/insights/<id>/feedback：反馈只写当前用户学习库中的 insight。
            elif feedback_match is not None:
                if not isinstance(payload, dict) or set(payload) != {"helpful"}:
                    raise ValueError("反馈参数不正确")
                if not isinstance(payload.get("helpful"), bool):
                    raise ValueError("反馈参数不正确")
                result = submit_ai_feedback(db, feedback_match.group(1), payload["helpful"])
            # /api/login：账号密码登录 —— 防爆破锁定期 → 校验 scrypt 哈希 → 签发会话 Cookie。
            elif path == "/api/login":
                ip = self.client_ip()
                if not login_rate_limit_ok(ip):
                    raise ValueError("尝试次数过多，请 10 分钟后再试")
                username = str(payload.get("username", "")).strip()
                try:
                    row_user = auth_login(username, str(payload.get("password", "")))
                except ValueError:
                    login_rate_limit_fail(ip)  # 失败计数：5 次锁 10 分钟
                    raise
                login_rate_limit_clear(ip)
                token = create_session(int(row_user["id"]))
                cookie_headers.append(("Set-Cookie", self.session_cookie(token)))
                result = {"ok": True, "username": str(row_user["username"]), "role": str(row_user["role"])}
            # /api/feedback：公开的 Bug/问题反馈（频控防灌水），由悬浮按钮提交。
            elif path == "/api/feedback":
                fb_ip = self.client_ip()
                if not feedback_rate_limit_ok(fb_ip):
                    raise ValueError("提交过于频繁，请稍后再试")
                feedback_rate_limit_record(fb_ip)
                result = submit_feedback(
                    str(payload.get("content", "")),
                    str(payload.get("contact", "")),
                    str(payload.get("page", "")),
                    self.headers.get("User-Agent", ""),
                    str(user["username"]) if user is not None else "",
                )
            # /api/register：注册码注册 —— 频控 → 原子兑换码 + 建用户 + 初始化独立学习库，成功即自动登录。
            elif path == "/api/register":
                reg_ip = self.client_ip()
                if not register_rate_limit_ok(reg_ip):
                    raise ValueError("注册尝试过于频繁，请稍后再试")
                register_rate_limit_record(reg_ip)
                row_user = register_with_code(
                    str(payload.get("username", "")),
                    str(payload.get("password", "")),
                    str(payload.get("code", "")),
                )
                token = create_session(int(row_user["id"]))
                cookie_headers.append(("Set-Cookie", self.session_cookie(token)))
                result = {"ok": True, "username": str(row_user["username"]), "role": str(row_user["role"])}
            # /api/plan/pin：把题目排入明天的今日计划（用户显式排期，展示后消费）。
            elif path == "/api/plan/pin":
                pid = int(payload.get("problem_id", 0))
                if pid not in PROBLEM_BY_ID:
                    raise ValueError("未知题号")
                for_date = (business_now().date() + timedelta(days=1)).isoformat()
                with closing(connect(db)) as connection:
                    connection.execute(
                        "INSERT INTO plan_pins(problem_id, for_date, created_at) VALUES (?, ?, ?) "
                        "ON CONFLICT(problem_id) DO UPDATE SET for_date = excluded.for_date",
                        (pid, for_date, now_iso()))
                    connection.commit()
                result = {"pinned": True, "problem_id": pid, "for_date": for_date}
            # /api/chat/send：公屏聊天发送（登录用户，10 条/分钟，500 字内）。
            elif path == "/api/chat/send":
                if not chat_rate_limit_ok(int(user["id"])):
                    raise ValueError("发言太快了，休息一下再发")
                chat_rate_limit_record(int(user["id"]))
                result = chat_send(int(user["id"]), str(user["username"]), str(payload.get("content", "")))
            # /api/profile：更新自己的昵称和/或头像（头像为 data URL，传空串清除）。
            elif path == "/api/profile":
                result = set_profile(
                    str(user["username"]),
                    payload.get("nickname") if "nickname" in payload else None,
                    payload.get("avatar") if "avatar" in payload else None,
                    payload.get("lang") if "lang" in payload else None,
                )
            elif path == "/api/weather/preferences":
                allowed = {"mode", "display_name", "latitude", "longitude", "timezone"}
                if any(key not in allowed for key in payload):
                    raise ValueError("请求参数不正确")
                preference = set_weather_preference(str(user["username"]), payload)
                result = {"preference": {key: preference[key] for key in ("mode", "display_name", "timezone")}}
            # /api/password：登录用户修改自己的密码（验证原密码；成功后其余会话失效）。
            elif path == "/api/password":
                result = change_own_password(
                    int(user["id"]),
                    str(payload.get("old_password", "")),
                    str(payload.get("new_password", "")),
                    keep_token=self.current_token(),
                )
            # /api/logout：删除服务端会话并清 Cookie。
            elif path == "/api/logout":
                token = self.current_token()
                if token:
                    destroy_session(token)
                cookie_headers.append(("Set-Cookie", self.session_cookie("", expire=True)))
                result = {"ok": True}
            # /api/admin/codes：批量签发一次性注册码（count 1~50，days 有效天数，0=永久）。
            elif path == "/api/admin/codes":
                codes = generate_invite_codes(
                    int(payload.get("count", 1)),
                    int(payload.get("days", 0) or 0),
                    str(payload.get("note", "")),
                    int(user["id"]),
                )
                result = {"codes": codes}
            # /api/admin/codes/revoke：吊销未使用注册码。
            elif path == "/api/admin/codes/revoke":
                result = revoke_invite_code(str(payload.get("code", "")))
            # /api/admin/users/toggle：停用/启用用户（停用即踢下线；管理员账号不可停用）。
            elif path == "/api/admin/users/toggle":
                if not isinstance(payload.get("active"), bool):
                    raise ValueError("active 必须是布尔值")
                result = set_user_active(str(payload.get("username", "")), payload["active"])
            # /api/admin/users/role：调整用户角色；不能自降权或清空最后一个管理员。
            elif path == "/api/admin/users/role":
                result = set_user_role(
                    str(payload.get("username", "")),
                    str(payload.get("role", "")),
                    str(user["username"]),
                )
            # /api/admin/users/nickname/reset：将用户昵称恢复为用户名；其他管理员不可修改。
            elif path == "/api/admin/users/nickname/reset":
                result = reset_user_nickname(
                    str(payload.get("username", "")),
                    str(user["username"]),
                )
            # 仅重置普通用户今日 AI 次数；操作者和重置前次数写入最小审计。
            elif path == "/api/admin/users/ai-quota/reset":
                if not isinstance(payload, dict) or set(payload) != {"username"}:
                    raise ValueError("请求参数不正确")
                result = admin_reset_user_ai_quota(
                    str(payload.get("username", "")), int(user["id"])
                )
            # 修改每日上限不重置已用次数；null 恢复系统默认值。
            elif path == "/api/admin/users/ai-quota/limit":
                if not isinstance(payload, dict) or set(payload) != {"username", "limit"}:
                    raise ValueError("请求参数不正确")
                result = admin_set_user_ai_daily_limit(
                    str(payload.get("username", "")), payload.get("limit"), int(user["id"])
                )
            # /api/admin/users/reset-password：管理员重置用户密码（重置后该用户全部会话失效）。
            elif path == "/api/admin/users/reset-password":
                result = reset_user_password(str(payload.get("username", "")), str(payload.get("new_password", "")))
            # /api/admin/chat/delete：管理员删除公屏消息（公屏治理）。
            elif path == "/api/admin/chat/delete":
                result = chat_delete(int(payload.get("id", 0)))
            # /api/admin/feedback/resolve：标记反馈已解决（可附说明）或重新打开。
            elif path == "/api/admin/feedback/resolve":
                if not isinstance(payload.get("resolved"), bool):
                    raise ValueError("resolved 必须是布尔值")
                result = resolve_feedback(
                    int(payload.get("id", 0)),
                    payload["resolved"],
                    str(payload.get("note", "")),
                )
            # /api/complete：兼容旧面板调用；Hot100 轮次现由 AC 记录自动推进。
            elif path == "/api/complete":
                result = complete_round(int(payload["problem_id"]), db)
            # /api/content/complete：书架章节完成一轮（独立的事件表与轮次序列）。
            elif path == "/api/content/complete":
                result = complete_content(str(payload["module_id"]), str(payload["content_id"]), db)
            # /api/mark：设置/清除标记 —— mastered/reviewing/weak，'' 表示删除标记。
            elif path == "/api/mark":
                result = set_mark(str(payload["target_type"]), str(payload["target_id"]), str(payload.get("mark", "")), db)
            # /api/settings：更新设置 KV（目前为每日目标轮次）。
            elif path == "/api/settings":
                result = set_setting(str(payload.get("key", "")), str(payload.get("value", "")), db)
            # /api/submit：记录一次力扣提交结果（ac/wa + 语言/耗时/内存，来自手动/书签/扩展）。
            elif path == "/api/submit":
                result = record_submission(
                    problem_id=int(payload["problem_id"]),
                    status=str(payload["status"]),
                    lang=str(payload.get("lang", "")),
                    runtime_ms=payload.get("runtime_ms"),
                    memory_kb=payload.get("memory_kb"),
                    source=str(payload.get("source", "manual")),
                    db_path=db,
                )
            # /api/leetcode/connect：保存力扣凭证（session/csrf）并立刻实测连接状态后返回。
            elif path == "/api/leetcode/connect":
                set_credentials({
                    "leetcode_session": str(payload.get("leetcode_session", "")),
                    "leetcode_csrf": str(payload.get("leetcode_csrf", "")),
                }, db)
                lc_status_invalidate(db)
                result = {"saved": True, **leetcode_status(get_credentials(db))}
            # /api/leetcode/sync：拉取力扣提交历史入库 —— full=1 全量翻页，否则增量最近 100 条。
            elif path == "/api/leetcode/sync":
                full = str(payload.get("full", "0")) in ("1", "true", "True")
                credentials = get_credentials(db)
                if not credentials.get("leetcode_session"):
                    raise LeetCodeSyncError(
                        "not_configured",
                        "请先前往力扣连接页面填写 LEETCODE_SESSION",
                        HTTPStatus.CONFLICT,
                    )
                if payload.get("async") in (1, True, "1", "true", "True"):
                    result = {
                        "ok": True,
                        "task_id": task_manager.submit(
                            "leetcode",
                            credentials,
                            full,
                            owner=str(user["username"]),
                            db_path=db,
                        ),
                    }
                else:
                    result = {"ok": True, **leetcode_sync(credentials, db_path=db, full=full)}
            # /api/leetcode/clear：一键清空凭证（等价"退出力扣连接"，不影响已同步记录）。
            else:
                clear_credentials(db)
                lc_status_invalidate(db)
                result = {"cleared": True}
        except LeetCodeSyncError as exc:
            self.send_json(
                {"error": exc.user_message, "error_category": exc.category},
                exc.status,
            )
            return
        except AnalyticsUnavailableError:
            self.send_json(
                {"error": "学习分析暂时不可用，请稍后重试", "retryable": True},
                HTTPStatus.SERVICE_UNAVAILABLE,
                extra_headers=[("Retry-After", "1")],
            )
            return
        except AIServiceError as exc:
            response: dict[str, object] = {
                "error": exc.user_message,
                "error_category": exc.category,
            }
            if exc.fallback is not None:
                response["fallback"] = exc.fallback
            if exc.details:
                response.update(exc.details)
            self.send_json(response, exc.status)
            return
        except PermissionError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            return
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            # 参数缺失/类型错/校验失败/JSON 非法 → 400（请求本身有问题，业务层抛 ValueError）。
            if learning_write_path:
                _invalidate_learning_caches(db)
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except sqlite3.Error:
            # 数据库层故障 → 500（请求没问题但写入失败）。
            if learning_write_path:
                _invalidate_learning_caches(db)
            self.send_json({"error": "数据库写入失败"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        except Exception:
            # A learning operation can commit one table and fail while writing
            # a mirrored/secondary table.  Always discard both read models
            # before returning the controlled error response.
            if learning_write_path:
                _invalidate_learning_caches(db)
            self.send_json({"error": "学习记录写入失败"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        # 写操作成功后使面板聚合缓存失效，保证下一次 /api/dashboard 拿到最新状态。
        if learning_write_path:
            _invalidate_learning_caches(db)
        elif path not in public_post and path != "/api/coach/context":
            _invalidate_dashboard_cache(db)
        # POST 创建/更新资源成功统一回 201 Created；send_json 内部附加 CORS 与 Set-Cookie 头。
        self.send_json(result, HTTPStatus.CREATED, extra_headers=cookie_headers)

    def session_cookie(self, token: str, expire: bool = False) -> str:
        """会话 Cookie：HttpOnly + SameSite=Lax（Lax 阻断跨站 POST 携带 Cookie，天然防 CSRF）。
        Secure 按访问源动态附加：公网域名（HTTPS）携带，局域网/本机 HTTP 访问不加，
        否则浏览器会拒存 Cookie 导致局域网入口无法登录。"""
        host = (self.headers.get("Host") or "").split(":")[0].strip("[]").lower()
        is_local = (
            "." not in host  # localhost / 主机名 / IPv6 字面量
            or host == "::1"
            or host.startswith(("127.", "10.", "192.168.", "172.16.", "172.17.", "172.18.",
                                "172.19.", "172.2", "172.30.", "172.31."))
            or host.endswith(".local")
        )
        secure = "" if is_local else "; Secure"
        max_age = 0 if expire else int(SESSION_TTL.total_seconds())
        return f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax{secure}; Max-Age={max_age}"

    def client_ip(self) -> str:
        """客户端真实 IP：经 Cloudflare Tunnel（cloudflared 走本机回环）时，socket 对端
        恒为 127.0.0.1，此时改取可信反代明确覆盖的 X-Real-IP，兼容 CF-Connecting-IP；
        若仅有 X-Forwarded-For 则取最右侧合法地址（nginx $proxy_add_x_forwarded_for
        会把客户端可伪造链放在左侧）；其余情况用 socket 对端地址。"""
        peer = self.client_address[0] if self.client_address else ""
        if peer in ("127.0.0.1", "::1"):
            # Only trust forwarding headers from the loopback proxy.  Prefer
            # headers explicitly overwritten by the proxy.  With nginx
            # $proxy_add_x_forwarded_for, the left side is client-controlled,
            # so use the rightmost valid address from the chain instead.
            for header_name in ("X-Real-IP", "CF-Connecting-IP"):
                candidate = (self.headers.get(header_name) or "").strip()
                try:
                    return str(ipaddress.ip_address(candidate))
                except ValueError:
                    continue
            forwarded = self.headers.get("X-Forwarded-For") or ""
            for candidate in reversed(forwarded.split(",")):
                try:
                    return str(ipaddress.ip_address(candidate.strip()))
                except ValueError:
                    continue
        return peer

    def current_token(self) -> str:
        """从 Cookie 头提取会话令牌（登出时用于删除服务端会话行）。"""
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == SESSION_COOKIE:
                return value
        return ""

    def log_message(self, format: str, *args: object) -> None:
        if not QUIET:
            print(f"[{self.log_date_time_string()}] {format % args}")


def main() -> None:
    global QUIET
    parser = argparse.ArgumentParser(description="Hot 100 本地学习站")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="启动后打开浏览器")
    parser.add_argument("--init-only", action="store_true", help="仅初始化数据库")
    parser.add_argument("--quiet", action="store_true", help="不打印请求日志")
    parser.add_argument("--create-admin", metavar="USERNAME",
                        help="幂等创建管理员账号（配合 --admin-password）；若旧单用户库存在且"
                             "该管理员尚无独立学习库，则自动把 data/hot100-study.db 迁移为其学习库")
    parser.add_argument("--admin-password", metavar="PASSWORD", help="与管理员用户名一起传入的初始密码")
    args = parser.parse_args()
    QUIET = args.quiet
    # ---- 管理员引导（幂等）：创建账号并按需收编旧单用户库 ----
    adopted = False
    if args.create_admin:
        if not args.admin_password:
            parser.error("--create-admin 需要同时提供 --admin-password")
        admin = ensure_admin(args.create_admin, args.admin_password)
        print(f"管理员账号就绪：{admin['username']}")
        legacy, target = DB_PATH, user_db_path(str(admin["username"]))
        if legacy.is_file() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            legacy.replace(target)
            adopted = True
            print(f"已将原学习库迁移为管理员学习库：{target}")
    # 初始化账户库（幂等建表 + 清过期会话）；学习库在管理员迁移或首个请求时按需建表。
    with closing(connect_auth()):
        pass
    # 未发生迁移时保持旧行为：确保默认库存在（兼容 --init-only 与扩展脚本）。
    if not adopted:
        with closing(connect()):
            pass
    if args.init_only:
        print(f"Database ready: {AUTH_DB_PATH}")
        return
    # 绑定 0.0.0.0 时浏览器仍应打开本机回环地址；0.0.0.0 不是浏览器可访问地址。
    browser_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    address = f"http://{browser_host}:{args.port}/"
    if args.open:
        # 延迟 0.5 秒再开浏览器：等服务就绪，避免浏览器首请求落空。
        threading.Timer(0.5, lambda: webbrowser.open(address)).start()
    print(f"Interview Forge：{address}")
    print("账户数据库：" + str(AUTH_DB_PATH))
    print("按 Ctrl+C 停止服务。")
    try:
        # FastAPI/Uvicorn is now the default runtime.  StudyHandler remains a
        # compatibility adapter for direct tests and the legacy router, so
        # public URLs and cookie/static semantics stay unchanged.
        import uvicorn
        from interview_forge.api.app import app
        uvicorn.run(app, host=args.host, port=args.port,
                    log_level="warning" if args.quiet else "info")
    except ImportError as exc:
        # A source checkout that has not installed requirements-server can
        # still use the historical command; packaged deployments use the
        # pinned FastAPI/Uvicorn dependency and take the branch above.
        if not QUIET:
            print(f"FastAPI/Uvicorn 不可用，回退兼容 HTTP 服务：{exc}")
        server = ThreadingHTTPServer((args.host, args.port), StudyHandler)
        server.daemon_threads = True
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
