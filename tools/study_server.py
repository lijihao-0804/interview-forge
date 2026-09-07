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
import json
import random
import re
import secrets
import sqlite3
import tempfile
import threading
import time
import unicodedata
import uuid
import webbrowser
from contextlib import closing, suppress
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

try:
    from build_hot100 import LEETCODE_SLUGS, PROBLEM_BY_ID, problem_filename
except ModuleNotFoundError:  # package import (for example, ``tools.study_server``)
    import sys
    _TOOLS_IMPORT_DIR = str(Path(__file__).resolve().parent)
    if _TOOLS_IMPORT_DIR not in sys.path:
        sys.path.insert(0, _TOOLS_IMPORT_DIR)
    from build_hot100 import LEETCODE_SLUGS, PROBLEM_BY_ID, problem_filename

try:
    from .learning_analytics import (
        AnalyticsUnavailableError,
        RULE_VERSION as ANALYTICS_RULE_VERSION,
        SCHEMA_VERSION as ANALYTICS_SCHEMA_VERSION,
        build_learning_analytics,
    )
except (ImportError, ModuleNotFoundError):  # direct script execution
    from learning_analytics import (
        AnalyticsUnavailableError,
        RULE_VERSION as ANALYTICS_RULE_VERSION,
        SCHEMA_VERSION as ANALYTICS_SCHEMA_VERSION,
        build_learning_analytics,
    )

try:
    from .context_compiler import compile_learning_context
except (ImportError, ModuleNotFoundError):  # direct script execution
    from context_compiler import compile_learning_context

try:
    from .ai_coach import (
        AI_DB_SCHEMA,
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
except (ImportError, ModuleNotFoundError):  # direct script execution
    from ai_coach import (
        AI_DB_SCHEMA,
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


# ---- 路径常量：锁定"项目根 / 数据目录 / 数据库文件"三个位置 ----
# ROOT    取本文件所在目录的上一级（tools/ 的 parents[1] 即学习站根目录），静态文件与题库都以此为准；
# DATA_DIR  数据目录（data/），放置 SQLite 文件；
# DB_PATH   全部学习记录的唯一落盘位置（data/hot100-study.db）。
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "hot100-study.db"
# ---- 认证与多用户路径常量 ----
# AUTH_DB_PATH   账户库（users/sessions/invite_codes），与学习记录库分离；
# USERS_DIR      每用户独立学习库的根目录 data/users/<用户名>/hot100-study.db。
AUTH_DB_PATH = DATA_DIR / "auth.db"
USERS_DIR = DATA_DIR / "users"
SESSION_COOKIE = "forge_session"
SESSION_TTL = timedelta(days=30)
# 用户名同时用作 data/users/ 下的目录名：只允许字母数字下划线连字符（2~32 位），
# 从源头排除路径穿越与特殊字符。
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")
# 注册码字符表：去掉易混淆的 0/O/1/I，便于口头转述与抄写。
_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

# 力扣同步后台任务：task_id -> 日志/状态/结果，供前端轮询打印进度。
SYNC_TASKS: dict[str, dict[str, object]] = {}
SYNC_TASKS_LOCK = threading.Lock()


# 间隔重复（简化 FSRS 风格）：完成第 n 轮后的下次复习间隔（天）。
# 第 1 轮 +1d、第 2 轮 +3d、第 3 轮 +7d、第 4 轮 +15d、第 5 轮 +30d，之后稳定在 +60d。
REVIEW_INTERVALS = (1, 3, 7, 15, 30, 60)
# 书架章节（阅读+理解型记忆）专用间隔：首轮 +3d，之后 +7/+15/+30/+60/+90d。
REVIEW_INTERVALS_CONTENT = (3, 7, 15, 30, 60, 90)


# ---- 间隔重复调度核心：轮次 → 间隔天数 → 到期日 ----
# review_interval(round_no)：第 n 次完成后的下次复习间隔（天），查表 + 夹逼：
#   round_no 落在 [1..6] 时取对应档位；小于 1 按第 1 档、大于 6 按最后一档（60 天封顶）。
# due_after(completed_at, round_no)：完成时间（ISO 带时区）→ 下一次到期日（YYYY-MM-DD 纯日期）。
#   "到期日 <= 今天" 即视为待复习（daily_data 的判断依据）。
def review_interval(round_no: int) -> int:
    """完成第 round_no 轮后的复习间隔（天）。"""
    # 索引公式：round_no-1 是 0 基下标；min/max 双夹逼保证任何输入都不越界。
    return REVIEW_INTERVALS[min(max(round_no - 1, 0), len(REVIEW_INTERVALS) - 1)]


def due_after(completed_at: str, round_no: int) -> str:
    """由完成时间与轮次推导下次复习到期日（YYYY-MM-DD）。"""
    # 时间解析链路：ISO 字符串 → 带时区 datetime → 纯日期（astimezone 保证与当前时区一致）。
    completed = datetime.fromisoformat(completed_at).astimezone().date()
    return (completed + timedelta(days=review_interval(round_no))).isoformat()


def review_interval_content(round_no: int) -> int:
    """完成第 round_no 轮书架章节后的复习间隔（天）。"""
    # 书架章节走独立间隔序列（首轮 +3d，节奏比题目略缓，适应"阅读+理解"型记忆）。
    return REVIEW_INTERVALS_CONTENT[min(max(round_no - 1, 0), len(REVIEW_INTERVALS_CONTENT) - 1)]


def due_after_content(completed_at: str, round_no: int) -> str:
    """由完成时间与轮次推导书架章节下次复习到期日（YYYY-MM-DD）。"""
    # 与 due_after 同构：唯一差别是把题目间隔表换成章节专用间隔表。
    completed = datetime.fromisoformat(completed_at).astimezone().date()
    return (completed + timedelta(days=review_interval_content(round_no))).isoformat()


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
SCHEMA = """
CREATE TABLE IF NOT EXISTS study_events (
    id INTEGER PRIMARY KEY,
    problem_id INTEGER NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('view', 'complete')),
    studied_at TEXT NOT NULL,
    study_date TEXT NOT NULL,
    round_no INTEGER,
    source TEXT NOT NULL DEFAULT 'learning-site',
    CHECK ((action = 'complete' AND round_no IS NOT NULL) OR
           (action = 'view' AND round_no IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_problem_round
    ON study_events(problem_id, round_no) WHERE action = 'complete';
CREATE INDEX IF NOT EXISTS ix_study_date ON study_events(study_date DESC);
CREATE INDEX IF NOT EXISTS ix_problem_activity ON study_events(problem_id, studied_at DESC);
CREATE TABLE IF NOT EXISTS content_events (
    id INTEGER PRIMARY KEY,
    module_id TEXT NOT NULL,
    content_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('view', 'complete')),
    studied_at TEXT NOT NULL,
    study_date TEXT NOT NULL,
    round_no INTEGER,
    CHECK ((action = 'complete' AND round_no IS NOT NULL) OR
           (action = 'view' AND round_no IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_content_round
    ON content_events(content_id, round_no) WHERE action = 'complete';
CREATE INDEX IF NOT EXISTS ix_content_date ON content_events(study_date DESC);
CREATE INDEX IF NOT EXISTS ix_content_activity ON content_events(content_id, studied_at DESC);
CREATE TABLE IF NOT EXISTS marks (
    target_type TEXT NOT NULL CHECK (target_type IN ('problem', 'content')),
    target_id TEXT NOT NULL,
    mark TEXT NOT NULL CHECK (mark IN ('mastered', 'reviewing', 'weak')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (target_type, target_id)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY,
    problem_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ac', 'wa')),
    lang TEXT NOT NULL DEFAULT '',
    runtime_ms INTEGER,
    memory_kb INTEGER,
    submitted_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'bookmarklet', 'extension', 'sync')),
    lc_id INTEGER
);
CREATE INDEX IF NOT EXISTS ix_submissions_problem ON submissions(problem_id, submitted_at DESC);
CREATE TABLE IF NOT EXISTS plan_pins (
    problem_id INTEGER PRIMARY KEY,
    for_date TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS credentials (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
""" + AI_DB_SCHEMA


# ---- 模块级进程内状态 ----
# _SCHEMA_DONE     已建表数据库路径集合：多用户下每个用户的库文件首次连接都要各自建表，
#                  因此按"绝对路径"记录，取代旧的全局布尔标记；
# QUIET            请求日志开关（--quiet 或脚本内置 True 后不再打印每条请求）；
# _SCHEMA_LOCK     建表互斥锁：多线程并发首次连接时，保证只有一个线程执行建表；
# _MANIFEST_CACHE  书架 manifest.json 的内存缓存 (mtime, 内容)：文件没改动就直接复用。
_SCHEMA_DONE: set[str] = set()
QUIET = False
_SCHEMA_LOCK = threading.Lock()
_MANIFEST_CACHE: tuple[float, dict[str, object]] | None = None

# /api/coach/analytics 的进程内只读快照缓存：缓存键不保存原始路径，而是使用
# resolved 用户库路径的 SHA-256 作用域，并带 schema/rule/generation 版本。
# 分析本身永远在锁外执行，避免慢读阻塞其它请求。
_ANALYTICS_CACHE: dict[str, tuple[float, dict[str, object]]] = {}
_ANALYTICS_CACHE_LOCK = threading.Lock()
_ANALYTICS_CACHE_GENERATIONS: dict[str, int] = {}
_ANALYTICS_GENERATION_TOUCHED: dict[str, float] = {}
# Number of lock-free analytics builds currently in flight for each resolved
# user database.  This must be a reference count rather than a set: two
# concurrent builds for one user can finish at different times, and the
# generation bookkeeping must stay pinned until the last one finishes.
_ANALYTICS_CACHE_ACTIVE: dict[str, int] = {}
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


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """打开数据库连接：确保目录存在、设置行工厂、开启外键；该库文件首次连接时加锁执行建库 DDL。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    # Row 工厂：查询结果支持按列名取值（row["problem_id"]），后面代码大量依赖它。
    connection.row_factory = sqlite3.Row
    # 开启外键约束（当前表结构暂无级联，保持规范）；timeout=10 秒缓解多线程并发写锁等待。
    connection.execute("PRAGMA foreign_keys = ON")
    # WAL 日志模式：多用户并发下读不阻塞写（持久属性，写一次即可）。
    connection.execute("PRAGMA journal_mode = WAL")
    # 按库文件路径记录建表状态：新用户库首次连接执行幂等 DDL，之后同一库直接跳过。
    schema_key = str(db_path)
    if schema_key not in _SCHEMA_DONE:
        with _SCHEMA_LOCK:
            if schema_key not in _SCHEMA_DONE:
                connection.executescript(SCHEMA)
                ensure_ai_schema(connection)
                # 老库迁移：为 submissions 补充力扣提交 ID 列（幂等）。
                try:
                    connection.execute("ALTER TABLE submissions ADD COLUMN lc_id INTEGER")
                except sqlite3.OperationalError:
                    pass  # 已存在
                # 部分唯一索引：仅 lc_id 非空的行参与唯一 —— 同步记录按力扣提交 ID 去重，
                # 而手动/扩展提交（lc_id 为空）不受影响。
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_submissions_lc ON submissions(lc_id) WHERE lc_id IS NOT NULL"
                )
                _SCHEMA_DONE.add(schema_key)
    return connection


def _analytics_resolved_path(db_path: Path) -> str:
    """Return the only path identity used by analytics cache/generation state."""
    return str(Path(db_path).resolve())


def _analytics_cache_prefix(resolved_path: str) -> str:
    """Build a non-reversible, versioned cache-key prefix for one user DB."""
    return (
        f"analytics:{ANALYTICS_SCHEMA_VERSION}:{ANALYTICS_RULE_VERSION}:"
        f"{_analytics_cache_scope(resolved_path)}"
    )


def _analytics_cache_scope(resolved_path: str) -> str:
    return hashlib.sha256(resolved_path.encode("utf-8")).hexdigest()


def _analytics_cache_key(db_path: Path, generation: int | None = None) -> str:
    """Return a versioned cache key with a hashed resolved-user scope."""
    if generation is None:
        resolved_path = _analytics_resolved_path(db_path)
        with _ANALYTICS_CACHE_LOCK:
            generation = _ANALYTICS_CACHE_GENERATIONS.get(resolved_path, 0)
    else:
        resolved_path = _analytics_resolved_path(db_path)
    return f"{_analytics_cache_prefix(resolved_path)}:g{int(generation)}"


def _analytics_cache_has_path_locked(resolved_path: str) -> bool:
    marker = f":{_analytics_cache_scope(resolved_path)}:g"
    return any(key.startswith("analytics:") and marker in key for key in _ANALYTICS_CACHE)


def _prune_analytics_cache_locked(now: float) -> None:
    """Remove expired snapshots and enforce the bounded snapshot capacity.

    The caller must hold ``_ANALYTICS_CACHE_LOCK``.  Eviction is deliberately
    generation-agnostic: a future read will rebuild under the current key, and
    an in-flight old build can still not reinsert after its generation changed.
    """
    expired = [
        key for key, (created_at, _result) in _ANALYTICS_CACHE.items()
        if now - float(created_at) >= _ANALYTICS_TTL
    ]
    for key in expired:
        _ANALYTICS_CACHE.pop(key, None)

    max_entries = max(0, int(_ANALYTICS_CACHE_MAX_ENTRIES))
    while len(_ANALYTICS_CACHE) > max_entries:
        oldest_key = min(
            _ANALYTICS_CACHE,
            key=lambda item: (float(_ANALYTICS_CACHE[item][0]), item),
        )
        _ANALYTICS_CACHE.pop(oldest_key, None)


def _prune_analytics_generations_locked() -> None:
    """Bound generation bookkeeping without dropping active read generations."""
    max_entries = max(0, int(_ANALYTICS_GENERATION_MAX_ENTRIES))
    if len(_ANALYTICS_CACHE_GENERATIONS) <= max_entries:
        return
    candidates = sorted(
        (
            _ANALYTICS_GENERATION_TOUCHED.get(path, 0.0),
            path,
        )
        for path in _ANALYTICS_CACHE_GENERATIONS
        if _ANALYTICS_CACHE_ACTIVE.get(path, 0) == 0
    )
    for _touched, path in candidates:
        if len(_ANALYTICS_CACHE_GENERATIONS) <= max_entries:
            break
        _ANALYTICS_CACHE_GENERATIONS.pop(path, None)
        _ANALYTICS_GENERATION_TOUCHED.pop(path, None)


def _invalidate_analytics_cache(db_path: Path) -> None:
    """Invalidate exactly one resolved user's analytics snapshots."""
    resolved_path = _analytics_resolved_path(db_path)
    with _ANALYTICS_CACHE_LOCK:
        now = time.time()
        _prune_analytics_cache_locked(now)
        # Invalidation is path-exact even if an old schema/rule-version entry
        # is still resident after a hot reload.
        marker = f":{_analytics_cache_scope(resolved_path)}:g"
        for key in list(_ANALYTICS_CACHE):
            if key.startswith("analytics:") and marker in key:
                _ANALYTICS_CACHE.pop(key, None)
        _ANALYTICS_CACHE_GENERATIONS[resolved_path] = (
            _ANALYTICS_CACHE_GENERATIONS.get(resolved_path, 0) + 1
        )
        _ANALYTICS_GENERATION_TOUCHED[resolved_path] = now
        _prune_analytics_generations_locked()


def _analytics_build_started_locked(resolved_path: str) -> None:
    """Pin a user's generation while one lock-free analytics build runs."""
    _ANALYTICS_CACHE_ACTIVE[resolved_path] = (
        _ANALYTICS_CACHE_ACTIVE.get(resolved_path, 0) + 1
    )


def _analytics_build_finished_locked(resolved_path: str) -> None:
    """Release one analytics build reference without underflowing the count."""
    active = _ANALYTICS_CACHE_ACTIVE.get(resolved_path, 0)
    if active <= 1:
        _ANALYTICS_CACHE_ACTIVE.pop(resolved_path, None)
    else:
        _ANALYTICS_CACHE_ACTIVE[resolved_path] = active - 1


def _invalidate_learning_caches(db_path: Path) -> None:
    """Invalidate all read models affected by a learning-db write."""
    _invalidate_analytics_cache(db_path)
    _invalidate_dashboard_cache(db_path)


def analytics_cached(db_path: Path) -> dict[str, object]:
    """Return a cached analytics snapshot, analyzing outside the cache lock."""
    resolved_path = _analytics_resolved_path(db_path)
    with _ANALYTICS_CACHE_LOCK:
        now = time.time()
        _prune_analytics_cache_locked(now)
        generation = _ANALYTICS_CACHE_GENERATIONS.get(resolved_path, 0)
        _ANALYTICS_GENERATION_TOUCHED[resolved_path] = now
        key = _analytics_cache_key(db_path, generation)
        hit = _ANALYTICS_CACHE.get(key)
        if hit and now - hit[0] < _ANALYTICS_TTL:
            return hit[1]
        if hit:
            # The general prune above normally removes this; keep the local
            # removal explicit for a patched/zero TTL and exactness.
            _ANALYTICS_CACHE.pop(key, None)
        _analytics_build_started_locked(resolved_path)

    # The core deliberately requires an existing root for its path guard.  A
    # fresh installation may have no user database yet; create only the empty
    # root directory so that the current user's missing DB still yields the
    # core's normal data_insufficient result, never the legacy DB_PATH.
    try:
        if not USERS_DIR.is_dir():
            USERS_DIR.mkdir(parents=True, exist_ok=True)

        # Do not hold _ANALYTICS_CACHE_LOCK while reading/analyzing SQLite.
        result = build_learning_analytics(
            db_path,
            PROBLEM_BY_ID,
            load_library_manifest(),
            allowed_db_root=USERS_DIR,
        )
    except BaseException:
        with _ANALYTICS_CACHE_LOCK:
            _analytics_build_finished_locked(resolved_path)
            _prune_analytics_generations_locked()
        raise

    with _ANALYTICS_CACHE_LOCK:
        _analytics_build_finished_locked(resolved_path)
        # A write may have invalidated the key while the lock-free analysis ran.
        # In that case return this snapshot to the in-flight caller but do not
        # reinsert a stale result for the next request.
        if _ANALYTICS_CACHE_GENERATIONS.get(resolved_path, 0) == generation:
            created_at = time.time()
            _prune_analytics_cache_locked(created_at)
            _ANALYTICS_CACHE[key] = (created_at, result)
            _prune_analytics_cache_locked(created_at)
        _prune_analytics_generations_locked()
    return result


# =============================================================================
# 认证与多用户（auth.db + 每用户独立学习库）
# -----------------------------------------------------------------------------
# 设计要点（纯标准库实现，参考 sub2api 的邀请码注册模式）：
#   * 账户数据放 data/auth.db 三张表，与各用户的学习库物理分离；
#   * 密码用 hashlib.scrypt（n=2^14, r=8, p=1）+ 16 字节随机盐，格式
#     "scrypt$n$r$p$盐hex$摘要hex"，校验用恒定时间比较；
#   * 会话令牌服务端存储（sessions 表，可吊销），Cookie 带 HttpOnly + SameSite=Lax
#     （Lax 本身就阻断跨站 POST 带 Cookie，天然防 CSRF）；
#   * 注册必须持有管理员签发的一次性注册码；"占用注册码 + 创建用户"在同一
#     BEGIN IMMEDIATE 事务中完成（仿 sub2api 的 createUserAndClaimInvitation），
#     并发抢同一个码时 UPDATE 的 status 条件只可能让一个请求成功；
#   * 每个注册用户在 data/users/<用户名>/hot100-study.db 拥有独立学习库，
#     数据函数全部接受 db_path 参数，由路由层传入当前用户路径即完成隔离。
# =============================================================================
_NICKNAME_MAX = 16

# 昵称审核分四层：
# 1) 统一归一化（全半角、大小写、常见繁体、零宽字符、标点/空格、数字变体）；
# 2) 项目自己的恶意昵称词库 + Trie，匹配文本任意位置而不是只看尾部；
# 3) 关系型侮辱表达与词库里的拼音/谐音变体；
# 4) 高置信度直接拒绝，历史数据启动时按同一规则恢复为用户名。
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

# 词库读取失败时仍保留这组内置兜底词；正式词条放在 data/nickname_banned_words.txt，便于维护。
_NICKNAME_FALLBACK_WORDS = (
    "傻逼", "傻比", "傻币", "煞笔", "沙比", "脑残", "弱智", "智障", "垃圾", "废物",
    "狗东西", "狗日", "畜生", "杂种", "贱人", "婊子", "臭婊", "妈的", "他妈", "他妈的",
    "操你妈", "草泥马", "日你妈", "去你妈", "干你娘",
    "shabi", "sabi", "shaibi", "naocan", "ruozhi", "zhizhang", "feiwu", "laji", "goutongxi",
    "zazhong", "jianren", "biaozi", "nima", "nmsl", "cnm", "caonima", "qunima", "ganniang",
    "fuck", "shit", "bitch",
    # 常见的亲属化侮辱/谐音写法，专门覆盖“爹地”及其拼音变体。
    "爹地", "爸比", "die", "diedi", "diedie", "baba", "babi", "mami", "yeye", "erzi", "sunzi", "zuzong", "laozi",
)


def _nickname_key(value: str) -> str:
    """压平全角、大小写、常见繁体、空格/标点和数字变体。"""
    value = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", value)).casefold()
    value = value.translate(_NICKNAME_TRADITIONAL_MAP).translate(_NICKNAME_LEET_MAP)
    return "".join(
        ch for ch in value
        if unicodedata.category(ch) != "Mn" and (ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    )


def _nickname_compact_key(value: str) -> str:
    """额外压缩连续重复字符，用于识别“傻——逼”“爹爹爹地”等规避写法。"""
    return _NICKNAME_REPEAT_RE.sub(r"\1", _nickname_key(value))


class _NicknameTrie:
    """昵称词库的轻量 Trie；昵称很短，逐起点扫描即可覆盖任意位置命中。"""

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
    """校验昵称并返回清理后的文本；规则在服务端统一执行，不能靠前端绕过。"""
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
    """启动迁移：把历史违规昵称恢复为对应用户名，避免旧数据继续外显。"""
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
    last_login TEXT
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
"""

_AUTH_READY = False
_AUTH_LOCK = threading.Lock()


def connect_auth() -> sqlite3.Connection:
    """打开账户库连接（首次连接建表并清理过期会话；事务改为手动模式支持原子注册）。"""
    global _AUTH_READY
    connection = sqlite3.connect(AUTH_DB_PATH, timeout=10, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    if not _AUTH_READY:
        with _AUTH_LOCK:
            if not _AUTH_READY:
                connection.executescript(AUTH_SCHEMA)
                # 老库迁移：users 补充聊天昵称列（幂等）。
                try:
                    connection.execute("ALTER TABLE users ADD COLUMN nickname TEXT NOT NULL DEFAULT ''")
                except sqlite3.OperationalError:
                    pass  # 已存在
                try:
                    connection.execute("ALTER TABLE users ADD COLUMN lang TEXT NOT NULL DEFAULT 'java'")
                except sqlite3.OperationalError:
                    pass  # 已存在
                try:
                    connection.execute("ALTER TABLE users ADD COLUMN last_seen TEXT")
                except sqlite3.OperationalError:
                    pass  # 已存在
                try:
                    connection.execute("ALTER TABLE feedback ADD COLUMN username TEXT NOT NULL DEFAULT ''")
                except sqlite3.OperationalError:
                    pass  # 已存在
                reset_invalid_nicknames(connection)
                # 启动期顺手清掉过期会话（幂等，不影响运行中新会话）。
                connection.execute("DELETE FROM sessions WHERE expires_at < ?", (now_iso(),))
                _AUTH_READY = True
    return connection


def now_iso() -> str:
    """当前时间 ISO 字符串（会话过期判断与审计字段统一入口）。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def hash_password(password: str) -> str:
    """scrypt 加盐哈希：随机 16 字节盐，参数固定 n=2^14/r=8/p=1，输出可自校验的存储串。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=1 << 14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """按存储串的参数重算 scrypt 并恒定时间比较；格式不合法一律返回 False。"""
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=32,
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def user_db_path(username: str) -> Path:
    """用户独立学习库路径；用户名必须通过白名单正则（防目录穿越），否则拒绝。"""
    if not USERNAME_RE.match(username):
        raise ValueError("非法用户名")
    return USERS_DIR / username / "hot100-study.db"


def _username_case_collision(
    connection: sqlite3.Connection,
    username: str,
    *,
    exclude_user_id: int | None = None,
) -> bool:
    """Return whether another account occupies the same Windows name.

    The auth schema intentionally remains backward-compatible and therefore
    keeps its historical case-sensitive UNIQUE constraint.  This explicit
    NOCASE lookup is the application-level invariant that also protects the
    case-insensitive ``data/users`` directory on Windows.
    """
    if exclude_user_id is None:
        row = connection.execute(
            "SELECT id FROM users WHERE username = ? COLLATE NOCASE LIMIT 1",
            (username,),
        ).fetchone()
    else:
        row = connection.execute(
            """SELECT id FROM users
               WHERE username = ? COLLATE NOCASE AND id <> ?
               LIMIT 1""",
            (username, exclude_user_id),
        ).fetchone()
    return row is not None


def create_user(username: str, password: str, role: str = "user",
                conn: sqlite3.Connection | None = None) -> dict[str, object]:
    """创建用户并在同一写事务内执行 NOCASE 冲突检查与插入。"""
    if not USERNAME_RE.match(username):
        raise ValueError("用户名限 2~32 位字母数字下划线连字符")
    if len(password) < 8:
        raise ValueError("密码至少 8 位")
    if role not in ("admin", "user"):
        raise ValueError("非法角色")
    own_connection = conn is None
    connection = conn or connect_auth()
    started_transaction = False
    try:
        # ``connect_auth`` is autocommit.  Standalone creation therefore needs
        # the same BEGIN IMMEDIATE boundary as registration; a caller that has
        # already started the registration transaction owns that boundary.
        if not connection.in_transaction:
            connection.execute("BEGIN IMMEDIATE")
            started_transaction = True
        if _username_case_collision(connection, username):
            raise ValueError("用户名已被占用")
        connection.execute(
            "INSERT INTO users(username, password_hash, role, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
            (username, hash_password(password), role, now_iso()),
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
    """幂等创建管理员：不存在则创建，已存在则原样返回（不重置密码、不改角色）。"""
    if not USERNAME_RE.match(username):
        raise ValueError("用户名限 2~32 位字母数字下划线连字符")
    with closing(connect_auth()) as connection:
        row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is not None:
        return dict(row)
    return create_user(username, password, role="admin")


def auth_login(username: str, password: str) -> sqlite3.Row:
    """登录校验：用户存在、已启用、密码正确三者缺一不可；成功则刷新 last_login。
    查无此用户时对假哈希跑一次等价校验，保证与"密码错误"耗时一致（防用户名枚举）。"""
    with closing(connect_auth()) as connection:
        row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            verify_password(password, _DUMMY_HASH)
            raise ValueError("用户名或密码错误")
        # A legacy auth.db may already contain Alice and alice because the old
        # UNIQUE constraint was case-sensitive.  Refuse both accounts rather
        # than guessing which physical Windows user directory is intended.
        if _username_case_collision(
            connection,
            str(row["username"]),
            exclude_user_id=int(row["id"]),
        ):
            verify_password(password, _DUMMY_HASH)
            raise ValueError("用户名或密码错误")
        if int(row["is_active"]) != 1 or not verify_password(password, str(row["password_hash"])):
            raise ValueError("用户名或密码错误")
        connection.execute("UPDATE users SET last_login = ? WHERE id = ?", (now_iso(), row["id"]))
        connection.execute("UPDATE users SET last_seen = ? WHERE id = ?", (now_iso(), row["id"]))
        return row


def create_session(user_id: int) -> str:
    """签发会话：32 字节随机令牌入库，30 天有效；令牌只存一份、删除即吊销。"""
    token = secrets.token_urlsafe(32)
    expires = (datetime.now().astimezone() + SESSION_TTL).isoformat(timespec="seconds")
    with closing(connect_auth()) as connection:
        connection.execute(
            "INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now_iso(), expires),
        )
    return token


def destroy_session(token: str) -> None:
    """登出：删除会话行（Cookie 由处理器置空）。"""
    with closing(connect_auth()) as connection:
        connection.execute("DELETE FROM sessions WHERE token = ?", (token,))


def session_user(token: str) -> sqlite3.Row | None:
    """由会话令牌解析当前用户：过期或被停用一律视为未登录；顺带触发每日过期清理。
    命中会话时以节流方式刷新 users.last_seen（管理后台"最近活跃"的数据来源）。"""
    if not token:
        return None
    _maybe_purge_sessions()
    row: sqlite3.Row | None = None
    with closing(connect_auth()) as connection:
        row = connection.execute(
            """SELECT u.id, u.username, u.role, u.is_active, COALESCE(NULLIF(u.nickname, ''), u.username) AS nickname, COALESCE(u.lang, 'java') AS lang
               FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token = ? AND s.expires_at > ? AND u.is_active = 1
                 AND NOT EXISTS (
                     SELECT 1 FROM users collision
                     WHERE collision.username COLLATE NOCASE = u.username COLLATE NOCASE
                       AND collision.id <> u.id
                 )""",
            (token, now_iso()),
        ).fetchone()
        if row is not None:
            seen_now = time.time()
            with _LAST_SEEN_LOCK:
                if seen_now - _LAST_SEEN_TS.get(row["id"], 0) >= _LAST_SEEN_INTERVAL:
                    _LAST_SEEN_TS[row["id"]] = seen_now
                    try:
                        connection.execute("UPDATE users SET last_seen = ? WHERE id = ?",
                                           (now_iso(), row["id"]))
                    except sqlite3.Error:
                        pass
    return row


def generate_invite_codes(count: int, days: int, note: str, created_by: int) -> list[str]:
    """批量签发一次性注册码：days>0 时从当天起算过期日，note 记录用途便于审计。"""
    count = max(1, min(count, 50))
    days = max(0, min(days, 365))
    expires = (datetime.now().astimezone().date() + timedelta(days=days)).isoformat() if days else None
    codes: list[str] = []
    with closing(connect_auth()) as connection:
        while len(codes) < count:
            body = "-".join(
                "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4)) for _ in range(2)
            )
            code = f"FORGE-{body}"
            try:
                connection.execute(
                    "INSERT INTO invite_codes(code, status, note, created_at, expires_at) VALUES (?, 'unused', ?, ?, ?)",
                    (code, note[:64], now_iso(), expires),
                )
                codes.append(code)
            except sqlite3.IntegrityError:
                continue  # 随机码撞车（概率极低），重抽即可
    return codes


def list_invite_codes() -> list[dict[str, object]]:
    """注册码清单（新签发在前），供管理页展示与审计。"""
    with closing(connect_auth()) as connection:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM invite_codes ORDER BY created_at DESC, code LIMIT 500"
        )]


def revoke_invite_code(code: str) -> dict[str, object]:
    """吊销未使用注册码（已用/已吊销的码不可再操作，保留审计记录）。"""
    with closing(connect_auth()) as connection:
        cursor = connection.execute(
            "UPDATE invite_codes SET status = 'revoked' WHERE code = ? AND status = 'unused'",
            (code,),
        )
        if cursor.rowcount != 1:
            raise ValueError("注册码不存在或不可吊销")
    return {"code": code, "status": "revoked"}


def register_with_code(username: str, password: str, code: str) -> dict[str, object]:
    """注册码兑换注册（原子）：占用码 + 建用户在同一事务，任一步失败整体回滚。"""
    username = username.strip()
    today = datetime.now().astimezone().date().isoformat()
    connection = connect_auth()
    try:
        connection.execute("BEGIN IMMEDIATE")  # 写锁从校验那一刻就持有，杜绝并发抢码窗口
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
        # 条件更新抢占注册码：并发场景只有一个请求能把 status 从 unused 改掉。
        cursor = connection.execute(
            "UPDATE invite_codes SET status = 'used', used_at = ? WHERE code = ? AND status = 'unused'",
            (now_iso(), code.strip().upper()),
        )
        if cursor.rowcount != 1:
            raise ValueError("注册码已被使用")
        user = create_user(username, password, conn=connection)
        connection.execute("COMMIT")
    except (ValueError, sqlite3.Error):
        with suppress(sqlite3.Error):
            connection.execute("ROLLBACK")  # 空事务回滚报错无害，吞掉即可
        raise
    finally:
        connection.close()
    # 建立该用户的独立学习库（幂等 DDL），注册后首次登录即可写记录。
    with closing(connect(user_db_path(user["username"]))):
        pass
    return user


def list_users() -> list[dict[str, object]]:
    """用户清单：附学习库体积，供管理页展示。"""
    items: list[dict[str, object]] = []
    with closing(connect_auth()) as connection:
        for row in connection.execute(
            "SELECT id, username, COALESCE(nickname, '') AS nickname, role, is_active, created_at, last_login, COALESCE(last_seen, last_login) AS last_active FROM users ORDER BY id"
        ):
            item = dict(row)
            db_file = user_db_path(str(item["username"]))
            item["db_bytes"] = db_file.stat().st_size if db_file.is_file() else 0
            item["ai_quota"] = get_ai_quota(db_file, str(item["role"]))
            items.append(item)
    return items


def admin_reset_user_ai_quota(
    username: str, actor_user_id: int
) -> dict[str, object]:
    """Reset a normal user's Shanghai-day quota and write the required audit row."""
    username = username.strip()
    if not username:
        raise ValueError("用户名不能为空")
    with closing(connect_auth()) as connection:
        actor = connection.execute(
            "SELECT id, role FROM users WHERE id = ?", (actor_user_id,)
        ).fetchone()
        target = connection.execute(
            "SELECT id, username, role FROM users WHERE username = ?", (username,)
        ).fetchone()
        if actor is None or str(actor["role"]) != "admin":
            raise PermissionError("需要管理员权限")
        if target is None:
            raise ValueError("用户不存在")
        if str(target["role"]) == "admin":
            raise ValueError("不能重置管理员的分析次数")
        reset = reset_ai_quota(user_db_path(str(target["username"])))
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """INSERT INTO ai_quota_reset_audit(
               actor_admin_id, target_user_id, reset_at, before_used
            ) VALUES (?, ?, ?, ?)""",
            (int(actor["id"]), int(target["id"]), now_iso(), int(reset["before_used"])),
        )
        connection.execute("COMMIT")
    return {"username": username, "reset": True, "quota": reset["quota"]}


def set_user_active(username: str, active: bool) -> dict[str, object]:
    """停用/启用用户：停用时同步清除其全部会话（立即踢下线）。"""
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
    """管理员调整用户角色；避免自降权或误删最后一个管理员。"""
    username = username.strip()
    role = role.strip().lower()
    if role not in ("admin", "user"):
        raise ValueError("角色只能是 admin 或 user")
    if not username:
        raise ValueError("用户名不能为空")
    with closing(connect_auth()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, username, role FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None:
            raise ValueError("用户不存在")
        current_role = str(row["role"])
        if current_role == role:
            connection.execute("COMMIT")
            return {"username": username, "role": role}
        if username == actor_username and role != "admin":
            raise ValueError("不能把当前管理员降为普通用户")
        if current_role == "admin" and role == "user":
            admin_count = connection.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin'"
            ).fetchone()[0]
            if int(admin_count) <= 1:
                raise ValueError("不能降级最后一个管理员")
        connection.execute("UPDATE users SET role = ? WHERE id = ?", (role, row["id"]))
        connection.execute("COMMIT")
    return {"username": username, "role": role}


def reset_user_nickname(username: str, actor_username: str = "") -> dict[str, object]:
    """管理员修复昵称；不能修改其他管理员，恢复值为该用户自己的用户名。"""
    username = username.strip()
    if not username:
        raise ValueError("用户名不能为空")
    with closing(connect_auth()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, username, role FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None:
            raise ValueError("用户不存在")
        if str(row["role"]) == "admin" and username != actor_username:
            raise ValueError("不能修改其他管理员的昵称")
        connection.execute("UPDATE users SET nickname = ? WHERE id = ?", (username, row["id"]))
        connection.execute("COMMIT")
    return {"username": username, "nickname": username}


def reset_user_password(username: str, new_password: str) -> dict[str, object]:
    """管理员重置用户密码：更新哈希并清除该用户全部会话（强制重新登录）。"""
    if len(new_password) < 8:
        raise ValueError("密码至少 8 位")
    with closing(connect_auth()) as connection:
        row = connection.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            raise ValueError("用户不存在")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                           (hash_password(new_password), row["id"]))
        connection.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
        connection.execute("COMMIT")
    return {"username": username, "reset": True}


def change_own_password(user_id: int, old_password: str, new_password: str,
                        keep_token: str = "") -> dict[str, object]:
    """登录用户修改自己的密码：需验证原密码；成功后吊销本人其余会话（当前会话保留）。"""
    if len(new_password) < 8:
        raise ValueError("密码至少 8 位")
    with closing(connect_auth()) as connection:
        row = connection.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or not verify_password(old_password, str(row["password_hash"])):
            raise ValueError("原密码错误")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                           (hash_password(new_password), user_id))
        connection.execute("DELETE FROM sessions WHERE user_id = ? AND token != ?",
                           (user_id, keep_token))
        connection.execute("COMMIT")
    return {"changed": True}


# ---- 登录防爆破：进程内滑动窗口（IP → [失败次数, 解禁时间戳]），重启即清零 ----
_LOGIN_FAILS: dict[str, list[float]] = {}
_LOGIN_LOCK = threading.Lock()
_LOGIN_MAX_FAILS = 5
_LOGIN_LOCKOUT_SECONDS = 600.0

# ---- 注册频控：每 IP 每小时 10 次 + 全局每小时 100 次（防高速穷举注册码）----
_REGISTER_ATTEMPTS: dict[str, list[float]] = {}
_REGISTER_GLOBAL: list[float] = []
_REGISTER_LOCK = threading.Lock()
_REGISTER_WINDOW = 3600.0
_REGISTER_MAX_PER_IP = 10
_REGISTER_MAX_GLOBAL = 100


def login_rate_limit_ok(ip: str) -> bool:
    """该 IP 当前是否允许尝试登录（失败 5 次锁 10 分钟）。"""
    with _LOGIN_LOCK:
        entry = _LOGIN_FAILS.get(ip)
        if not entry:
            return True
        fails, unlock_at = entry
        if fails < _LOGIN_MAX_FAILS or time.time() >= unlock_at:
            return True
        return False


def login_rate_limit_fail(ip: str) -> None:
    """记录一次登录失败，达到阈值时启动锁定期。"""
    with _LOGIN_LOCK:
        entry = _LOGIN_FAILS.setdefault(ip, [0, 0.0])
        entry[0] += 1
        if entry[0] >= _LOGIN_MAX_FAILS:
            entry[1] = time.time() + _LOGIN_LOCKOUT_SECONDS


def login_rate_limit_clear(ip: str) -> None:
    """登录成功后清零该 IP 的失败计数。"""
    with _LOGIN_LOCK:
        _LOGIN_FAILS.pop(ip, None)


def register_rate_limit_ok(ip: str) -> bool:
    """注册接口频控：滑动 1 小时窗口内该 IP ≤10 次、全站 ≤100 次。"""
    now = time.time()
    with _REGISTER_LOCK:
        stamps = [t for t in _REGISTER_ATTEMPTS.get(ip, []) if now - t < _REGISTER_WINDOW]
        global_stamps = [t for t in _REGISTER_GLOBAL if now - t < _REGISTER_WINDOW]
        _REGISTER_ATTEMPTS[ip] = stamps
        _REGISTER_GLOBAL[:] = global_stamps
        return len(stamps) < _REGISTER_MAX_PER_IP and len(global_stamps) < _REGISTER_MAX_GLOBAL


def register_rate_limit_record(ip: str) -> None:
    """记录一次注册尝试（无论成败都计数）。"""
    now = time.time()
    with _REGISTER_LOCK:
        _REGISTER_ATTEMPTS.setdefault(ip, []).append(now)
        _REGISTER_GLOBAL.append(now)


# ---- 反馈提交频控：每 IP 每小时 5 次（反馈接口公开，防垃圾灌水）----
_FEEDBACK_ATTEMPTS: dict[str, list[float]] = {}
_FEEDBACK_LOCK = threading.Lock()
_FEEDBACK_WINDOW = 3600.0
_FEEDBACK_MAX_PER_IP = 5


def feedback_rate_limit_ok(ip: str) -> bool:
    """该 IP 当前是否允许提交反馈（滑动 1 小时窗口 ≤5 次）。"""
    now = time.time()
    with _FEEDBACK_LOCK:
        stamps = [t for t in _FEEDBACK_ATTEMPTS.get(ip, []) if now - t < _FEEDBACK_WINDOW]
        _FEEDBACK_ATTEMPTS[ip] = stamps
        return len(stamps) < _FEEDBACK_MAX_PER_IP


def feedback_rate_limit_record(ip: str) -> None:
    """记录一次反馈提交。"""
    with _FEEDBACK_LOCK:
        _FEEDBACK_ATTEMPTS.setdefault(ip, []).append(time.time())


def submit_feedback(content: str, contact: str, page: str, user_agent: str,
                    username: str = "") -> dict[str, object]:
    """保存一条 Bug/问题反馈（公开接口，频控由调用方执行）。"""
    content = content.strip()
    if not (1 <= len(content) <= 2000):
        raise ValueError("反馈内容需为 1~2000 字")
    if len(contact) > 120 or len(page) > 500:
        raise ValueError("联系方式或页面地址过长")
    with closing(connect_auth()) as connection:
        cursor = connection.execute(
            "INSERT INTO feedback(content, username, contact, page, user_agent, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'open', ?)",
            (content, username[:64], contact[:120], page[:500], user_agent[:300], now_iso()),
        )
    return {"id": cursor.lastrowid, "submitted": True}


def list_feedback(status: str = "") -> list[dict[str, object]]:
    """反馈清单（新提交在前）；status=open/resolved 过滤，空为全部。"""
    sql = "SELECT * FROM feedback"
    params: list[object] = []
    if status in ("open", "resolved"):
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY id DESC LIMIT 500"
    with closing(connect_auth()) as connection:
        return [dict(row) for row in connection.execute(sql, params)]


def resolve_feedback(feedback_id: int, resolved: bool, note: str = "") -> dict[str, object]:
    """管理员处理反馈：标记已解决（可附处理说明）或重新打开。"""
    if resolved and not note.strip():
        note = ""
    with closing(connect_auth()) as connection:
        cursor = connection.execute(
            "UPDATE feedback SET status = ?, resolved_at = ?, resolved_note = ? WHERE id = ?",
            ("resolved" if resolved else "open",
             now_iso() if resolved else None,
             note[:300], feedback_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("反馈不存在")
    return {"id": feedback_id, "status": "resolved" if resolved else "open"}


# =============================================================================
# 聊天室（公屏）：自研轻量实现 —— 登录用户可发、所有人可见、轮询拉增量。
# 消息保留最近 CHAT_KEEP 条（超出自动清理）；昵称/头像在 users/avatars 表。
# =============================================================================
CHAT_KEEP = 2000
CHAT_MAX_LEN = 500
_CHAT_SEND_LOG: dict[int, list[float]] = {}   # user_id → 发送时间戳（10 条/分钟）
_CHAT_SEND_LOCK = threading.Lock()
# 题解语言偏好（用户资料项；题解页据此切换代码实现显示）
SOLUTION_LANGS = ("java", "cpp", "python", "go", "c")
# 单轮完成标准：累计 AC 过 ≥90 道题（Hot 100 的 90%）才算完整一轮
ROUND_COMPLETE_THRESHOLD = 90
_AVATAR_MAX_BYTES = 150 * 1024


def chat_rate_limit_ok(user_id: int) -> bool:
    """单用户发送频控：滑动 1 分钟窗口 ≤10 条。"""
    now = time.time()
    with _CHAT_SEND_LOCK:
        stamps = [t for t in _CHAT_SEND_LOG.get(user_id, []) if now - t < 60.0]
        _CHAT_SEND_LOG[user_id] = stamps
        return len(stamps) < 10


def chat_rate_limit_record(user_id: int) -> None:
    with _CHAT_SEND_LOCK:
        _CHAT_SEND_LOG.setdefault(user_id, []).append(time.time())


def chat_send(user_id: int, username: str, content: str) -> dict[str, object]:
    """发送一条公屏消息；超出保留量的最旧消息自动清理。"""
    content = content.strip()
    if not (1 <= len(content) <= CHAT_MAX_LEN):
        raise ValueError(f"消息需为 1~{CHAT_MAX_LEN} 字")
    with closing(connect_auth()) as connection:
        cursor = connection.execute(
            "INSERT INTO chat_messages(user_id, content, created_at) VALUES (?, ?, ?)",
            (user_id, content, now_iso()),
        )
        connection.execute(
            "DELETE FROM chat_messages WHERE id <= (SELECT MAX(id) FROM chat_messages) - ?",
            (CHAT_KEEP,),
        )
    return {"id": cursor.lastrowid, "created_at": now_iso(), "username": username}


def chat_messages_after(after_id: int, limit: int = 50) -> list[dict[str, object]]:
    """拉取 id > after_id 的增量消息（昵称实时取自 users 表）；after_id=-1 时取最近 limit 条。"""
    limit = max(1, min(limit, 100))
    with closing(connect_auth()) as connection:
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


def chat_delete(feedback_id_alias: int) -> dict[str, object]:
    """管理员删除一条消息（公屏治理）。"""
    with closing(connect_auth()) as connection:
        cursor = connection.execute("DELETE FROM chat_messages WHERE id = ?", (feedback_id_alias,))
        if cursor.rowcount != 1:
            raise ValueError("消息不存在")
    return {"id": feedback_id_alias, "deleted": True}


# ---- 全文搜索（服务端执行）：索引常驻内存，公网搜索只传关键词与结果，
#      免去浏览器拉取 1.5MB 的 search-index.json ----
_SEARCH_INDEX: list[dict] | None = None
_SEARCH_LOCK = threading.Lock()


def _load_search_index() -> list[dict]:
    """首次请求时加载 library/search-index.json 到内存（此后常驻）。"""
    global _SEARCH_INDEX
    if _SEARCH_INDEX is None:
        with _SEARCH_LOCK:
            if _SEARCH_INDEX is None:
                path = ROOT / "library" / "search-index.json"
                _SEARCH_INDEX = json.loads(path.read_text(encoding="utf-8"))
    return _SEARCH_INDEX


def search_index_server(query: str) -> list[dict[str, object]]:
    """服务端评分搜索：标题命中 3 分、模块名 2 分、正文 1 分，降序取前 60。"""
    q = query.strip().lower()
    if not q:
        return []
    hits = []
    for entry in _load_search_index():
        title = str(entry.get("title", "")).lower()
        mod = str(entry.get("module_title", "")).lower()
        text = str(entry.get("text", "")).lower()
        s = 3 if q in title else 2 if q in mod else 1 if q in text else 0
        if s:
            hits.append({"id": entry.get("id"), "title": entry.get("title"),
                         "url": entry.get("url"), "module_title": entry.get("module_title"), "s": s})
    hits.sort(key=lambda x: -x["s"])
    return hits[:60]


def get_profile(username: str) -> dict[str, object]:
    """读取自己的昵称与头像状态。"""
    with closing(connect_auth()) as connection:
        row = connection.execute(
            "SELECT username, COALESCE(nickname, '') AS nickname, COALESCE(lang, 'java') AS lang FROM users WHERE username = ?", (username,)).fetchone()
        av = connection.execute("SELECT mime FROM avatars WHERE user_id = (SELECT id FROM users WHERE username = ?)",
                                (username,)).fetchone()
    if row is None:
        raise ValueError("用户不存在")
    return {"username": row["username"], "nickname": row["nickname"], "lang": row["lang"], "has_avatar": av is not None}


def set_profile(username: str, nickname: str = None, avatar_data_url: str = None,
                lang: str = None) -> dict[str, object]:
    """更新昵称/头像/题解语言。头像为 data URL（客户端已压至 64×64），传空串清除。"""
    with closing(connect_auth()) as connection:
        row = connection.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            raise ValueError("用户不存在")
        if nickname is not None:
            nickname = nickname.strip()
            if nickname:
                nickname = validate_nickname(nickname)
            connection.execute("UPDATE users SET nickname = ? WHERE id = ?", (nickname, row["id"]))
        if lang is not None:
            if lang not in SOLUTION_LANGS:
                raise ValueError("不支持的语言")
            connection.execute("UPDATE users SET lang = ? WHERE id = ?", (lang, row["id"]))
        if avatar_data_url is not None:
            if avatar_data_url == "":
                connection.execute("DELETE FROM avatars WHERE user_id = ?", (row["id"],))
            else:
                import base64, re as _re
                m = _re.match(r"^data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$", avatar_data_url)
                if not m:
                    raise ValueError("头像格式不支持（仅 png/jpeg/webp）")
                blob = base64.b64decode(m.group(2))
                if len(blob) > _AVATAR_MAX_BYTES:
                    raise ValueError("头像过大（压缩后需小于 150KB）")
                connection.execute(
                    "INSERT INTO avatars(user_id, mime, data, updated_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(user_id) DO UPDATE SET mime = excluded.mime, data = excluded.data, updated_at = excluded.updated_at",
                    (row["id"], "image/" + m.group(1), blob, now_iso()))
    return get_profile(username)


def get_avatar(username: str):
    """读取用户头像，返回 (mime, bytes)；未设置返回 None。"""
    with closing(connect_auth()) as connection:
        row = connection.execute(
            "SELECT a.mime, a.data FROM avatars a JOIN users u ON u.id = a.user_id WHERE u.username = ?",
            (username,)).fetchone()
    if row is None:
        return None
    return str(row["mime"]), bytes(row["data"])


# 时序侧信道防御：用户名不存在时也跑一次等价 scrypt 校验，抹平"查无此用户"与
# "密码错误"的响应时间差（假哈希与真实校验计算量完全一致）。
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))

# 过期会话每日清理：session_user 每个请求都会调用 _maybe_purge_sessions，
# 但只有距上次清理超过 24 小时才真正执行 DELETE。
_LAST_SESSION_PURGE = 0.0

# 最近活跃（last_seen）写库节流：每个用户最多 60 秒落盘一次，避免每请求写库
_LAST_SEEN_TS: dict[int, float] = {}
_LAST_SEEN_LOCK = threading.Lock()
_LAST_SEEN_INTERVAL = 60.0


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
    now = datetime.now().astimezone()
    return now.isoformat(timespec="seconds"), now.date().isoformat()


def record_view(problem_id: int, db_path: Path = DB_PATH) -> bool:
    """记录一次题目浏览（view 事件）：60 秒内对同一题去重，防止翻页/刷接口产生垃圾记录。"""
    if problem_id not in PROBLEM_BY_ID:
        # 未知题号直接忽略 —— 浏览埋点属"尽力而为"，不因脏请求而报错。
        return False
    studied_at, study_date = now_parts()
    with closing(connect(db_path)) as connection:
        # 取该题最近一条 view 的时间戳，用于 60 秒窗口的去重判断。
        recent = connection.execute(
            """SELECT studied_at FROM study_events
               WHERE problem_id = ? AND action = 'view'
               ORDER BY id DESC LIMIT 1""",
            (problem_id,),
        ).fetchone()
        if recent:
            last = datetime.fromisoformat(recent["studied_at"])
            if (datetime.fromisoformat(studied_at) - last).total_seconds() < 60:
                return False
        # 通过 60 秒窗口：落一条 view 记录（studied_at / study_date 由 now_parts 统一生成）。
        connection.execute(
            "INSERT INTO study_events(problem_id, action, studied_at, study_date) VALUES (?, 'view', ?, ?)",
            (problem_id, studied_at, study_date),
        )
        connection.commit()
    _invalidate_learning_caches(db_path)
    return True


def complete_round(problem_id: int, db_path: Path = DB_PATH) -> dict[str, object]:
    """兼容旧面板的手动完成接口：Hot100 轮次已改由 AC 记录自动推导，页面不再调用。"""
    if problem_id not in PROBLEM_BY_ID:
        raise ValueError("未知题号")
    studied_at, study_date = now_parts()
    with closing(connect(db_path)) as connection:
        # BEGIN IMMEDIATE：立刻拿写锁，"取下一轮次 + 插入"在同一事务内原子完成，
        # 并发双击也不会开出重复轮次（配合唯一索引 uq_problem_round 双保险）。
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT COALESCE(MAX(round_no), 0) + 1 AS next_round FROM study_events WHERE problem_id = ? AND action = 'complete'",
            (problem_id,),
        ).fetchone()
        round_no = int(row["next_round"])
        connection.execute(
            """INSERT INTO study_events(problem_id, action, studied_at, study_date, round_no)
               VALUES (?, 'complete', ?, ?, ?)""",
            (problem_id, studied_at, study_date, round_no),
        )
        connection.commit()
    # Invalidate immediately after the first committed write.  If the legacy
    # mirrored content write below fails, the study event cannot leave an old
    # analytics/dashboard snapshot visible.
    _invalidate_learning_caches(db_path)
    # 同步到书架：Hot 100 题目的完成轮次同时写入 content_events，
    # 让书架“算法刷题”模块的进度与题解面板保持一致。
    try:
        complete_content("hot100", f"hot100:{problem_id:04d}", db_path)
    except ValueError:
        pass
    # next_due：前端用它展示"下次复习时间"（= 完成时间 + 轮次对应间隔）。
    return {
        "problem_id": problem_id,
        "round_no": round_no,
        "studied_at": studied_at,
        "next_due": due_after(studied_at, round_no),
    }


# 面板聚合缓存：/api/dashboard 每次全量计算较重（100 题状态 + 365 天活动 + 提交统计），
# 按"数据库路径"缓存 60 秒；任何写操作（完成/标记/提交）后立即失效。
_DASH_CACHE: dict[str, tuple[float, dict[str, object]]] = {}
_DASH_CACHE_LOCK = threading.Lock()
_DASH_CACHE_GENERATIONS: dict[str, int] = {}
_DASH_TTL = 60.0


def dashboard_cached(db_path: Path) -> dict[str, object]:
    """带 60 秒缓存的仪表盘聚合；写操作后由调用方清缓存。"""
    key = str(Path(db_path).resolve())
    now = time.time()
    with _DASH_CACHE_LOCK:
        generation = _DASH_CACHE_GENERATIONS.get(key, 0)
        hit = _DASH_CACHE.get(key)
        if hit and now - hit[0] < _DASH_TTL:
            return hit[1]
        if hit:
            _DASH_CACHE.pop(key, None)
    data = dashboard_data(db_path)
    with _DASH_CACHE_LOCK:
        # A write/invalidation may have happened while the dashboard was
        # calculated outside the lock.  Returning this caller's result remains
        # valid, but an old snapshot must never repopulate the shared cache.
        if _DASH_CACHE_GENERATIONS.get(key, 0) == generation:
            _DASH_CACHE[key] = (time.time(), data)
    return data


def _invalidate_dashboard_cache(db_path: Path) -> None:
    """Invalidate the existing dashboard snapshot for one database path."""
    key = str(Path(db_path).resolve())
    with _DASH_CACHE_LOCK:
        # Remove both the canonical key and the historical/raw spelling so a
        # cache entry created by an older process cannot survive a write.
        _DASH_CACHE.pop(key, None)
        _DASH_CACHE.pop(str(db_path), None)
        _DASH_CACHE_GENERATIONS[key] = _DASH_CACHE_GENERATIONS.get(key, 0) + 1


def dashboard_data(db_path: Path = DB_PATH) -> dict[str, object]:
    """聚合仪表盘全部数据：题目轮次按 AC 自然日推导，同日多次 AC 只计一轮。"""
    today = datetime.now().astimezone().date().isoformat()
    with closing(connect(db_path)) as connection:
        view_rows = connection.execute(
            """SELECT problem_id, MAX(studied_at) AS last_viewed_at
               FROM study_events WHERE action = 'view' GROUP BY problem_id"""
        ).fetchall()
        # 题目完成轮次 = 出现过 AC 的自然日数量；同日多提交只计一轮。
        ac_rows = connection.execute(
            """SELECT problem_id,
                      COUNT(DISTINCT substr(submitted_at, 1, 10)) AS rounds,
                      MAX(submitted_at) AS last_completed_at,
                      MAX(substr(submitted_at, 1, 10)) AS last_ac_date
               FROM submissions WHERE status = 'ac' GROUP BY problem_id"""
        ).fetchall()
        study_summary = connection.execute(
            """SELECT
                 COUNT(DISTINCT CASE WHEN study_date = ? AND action = 'view' THEN problem_id END) AS today_viewed
               FROM study_events WHERE action = 'view'""",
            (today,),
        ).fetchone()
        ac_summary = connection.execute(
            """SELECT
                 COUNT(DISTINCT CASE WHEN substr(submitted_at, 1, 10) = ? THEN problem_id END) AS today_rounds,
                 COUNT(DISTINCT problem_id) AS completed_problems
               FROM submissions WHERE status = 'ac'""",
            (today,),
        ).fetchone()
        # 累计轮次 = 完整刷题遍数：每题按"AC 过的不同天数"计轮，
        # 轮次 k 达成 = 有 ≥ ROUND_COMPLETE_THRESHOLD 道题的轮数 ≥ k
        per_problem_rounds = [int(r["rd"]) for r in connection.execute(
            """SELECT problem_id, COUNT(DISTINCT substr(submitted_at, 1, 10)) AS rd
               FROM submissions WHERE status = 'ac' GROUP BY problem_id"""
        ).fetchall()]
        total_rounds = 0
        completed = len(per_problem_rounds)
        k = 1
        while True:
            reached = sum(1 for rd in per_problem_rounds if rd >= k)
            if k == 1:
                ok = reached >= ROUND_COMPLETE_THRESHOLD          # 首轮：完成 90 题以上
            else:
                ok = completed > 0 and reached * 2 > completed    # 之后：大部分题完成即达成
            if not ok:
                break
            total_rounds = k
            k += 1
        view_events = connection.execute(
            """SELECT problem_id, studied_at FROM study_events
               WHERE action = 'view' ORDER BY studied_at DESC, id DESC LIMIT 200"""
        ).fetchall()
        ac_date_rows = connection.execute(
            """SELECT problem_id,
                      substr(submitted_at, 1, 10) AS study_date,
                      MAX(submitted_at) AS studied_at
               FROM submissions WHERE status = 'ac'
               GROUP BY problem_id, study_date"""
        ).fetchall()
        # 每日每题只产生一条 complete 事件，round_no 按该题的 AC 日期自然顺序编号。
        ac_by_problem: dict[int, list[dict[str, object]]] = {}
        for row in ac_date_rows:
            ac_by_problem.setdefault(int(row["problem_id"]), []).append(dict(row))
        complete_events: list[dict[str, object]] = []
        for pid, rows in ac_by_problem.items():
            rows.sort(key=lambda item: str(item["study_date"]))
            for index, row in enumerate(rows, start=1):
                complete_events.append({
                    "problem_id": pid,
                    "action": "complete",
                    "studied_at": row["studied_at"],
                    "round_no": index,
                })
        view_days = connection.execute(
            """SELECT study_date,
                      COUNT(DISTINCT problem_id) AS viewed
               FROM study_events WHERE action = 'view' GROUP BY study_date"""
        ).fetchall()
        ac_days = connection.execute(
            """SELECT substr(submitted_at, 1, 10) AS study_date,
                      COUNT(DISTINCT problem_id) AS rounds
               FROM submissions WHERE status = 'ac' GROUP BY study_date"""
        ).fetchall()
        content_days = connection.execute(
            """SELECT study_date,
                      COUNT(DISTINCT CASE WHEN action = 'view' THEN content_id END) AS viewed,
                      SUM(CASE WHEN action = 'complete' THEN 1 ELSE 0 END) AS rounds
               FROM content_events WHERE module_id <> 'hot100' GROUP BY study_date"""
        ).fetchall()
        submission_days = connection.execute(
            """SELECT substr(submitted_at, 1, 10) AS study_date, COUNT(1) AS submits
               FROM submissions GROUP BY study_date"""
        ).fetchall()
        active_dates = {
            str(row["study_date"]) for row in view_days
        } | {
            str(row["study_date"]) for row in ac_days
        } | {
            str(row["study_date"]) for row in content_days
        } | {
            str(row["study_date"]) for row in submission_days
        }
    # 把三类按日计数合并进 day_stats：一个日期 → {viewed, rounds, submits} 三元组。
    day_stats: dict[str, dict[str, int]] = {}
    for row in view_days:
        day_stats.setdefault(str(row["study_date"]), {"viewed": 0, "rounds": 0, "submits": 0})
        day_stats[str(row["study_date"])]["viewed"] += int(row["viewed"] or 0)
    for row in ac_days:
        day_stats.setdefault(str(row["study_date"]), {"viewed": 0, "rounds": 0, "submits": 0})
        day_stats[str(row["study_date"])]["rounds"] += int(row["rounds"] or 0)
    for row in content_days:
        day_stats.setdefault(str(row["study_date"]), {"viewed": 0, "rounds": 0, "submits": 0})
        day_stats[str(row["study_date"])]["viewed"] += int(row["viewed"] or 0)
        day_stats[str(row["study_date"])]["rounds"] += int(row["rounds"] or 0)
    for row in submission_days:
        day_stats.setdefault(str(row["study_date"]), {"viewed": 0, "rounds": 0, "submits": 0})
        day_stats[str(row["study_date"])]["submits"] += int(row["submits"] or 0)
    # 热力图数据：生成过去 365 天逐日计数（缺数据的补 0），前端按格子渲染 GitHub 风格日历。
    base = datetime.now().astimezone().date() - timedelta(days=364)
    activity = [
        {
            "date": (base + timedelta(days=offset)).isoformat(),
            "viewed": day_stats.get((base + timedelta(days=offset)).isoformat(), {}).get("viewed", 0),
            "rounds": day_stats.get((base + timedelta(days=offset)).isoformat(), {}).get("rounds", 0),
            "submits": day_stats.get((base + timedelta(days=offset)).isoformat(), {}).get("submits", 0),
        }
        for offset in range(365)
    ]
    # 连续学习天数：从今天（今天无记录则从昨天）往回数连续有活动的天数。
    streak = 0
    cursor = datetime.now().astimezone().date()
    if cursor.isoformat() not in active_dates:
        cursor -= timedelta(days=1)
    while cursor.isoformat() in active_dates:
        streak += 1
        cursor -= timedelta(days=1)
    try:
        daily_goal = max(1, min(50, int(get_settings(db_path).get("daily_goal_rounds", "3") or "3")))
    except (TypeError, ValueError):
        daily_goal = 3
    summary = {
        "today_viewed": int(study_summary["today_viewed"] or 0),
        "today_rounds": int(ac_summary["today_rounds"] or 0),
        "completed_problems": int(ac_summary["completed_problems"] or 0),
        "total_rounds": total_rounds,
        "active_days": len(active_dates),
    }
    summary["streak"] = streak
    summary["daily_goal"] = daily_goal
    problems_payload: dict[str, dict[str, object]] = {}
    view_map = {int(row["problem_id"]): dict(row) for row in view_rows}
    ac_map = {int(row["problem_id"]): dict(row) for row in ac_rows}
    for pid in sorted(set(view_map) | set(ac_map)):
        viewed = view_map.get(pid, {})
        ac = ac_map.get(pid, {})
        rounds = int(ac.get("rounds") or 0)
        last_viewed = str(viewed.get("last_viewed_at") or "") if viewed else ""
        last_completed = str(ac.get("last_completed_at") or "") if ac else ""
        item: dict[str, object] = {
            "rounds": rounds,
            "last_viewed_at": last_viewed or None,
            "last_completed_at": last_completed or None,
            "last_activity_at": max(
                value for value in (last_viewed, last_completed) if value
            ) or None,
        }
        if rounds > 0 and last_completed:
            item["next_due"] = due_after(last_completed, rounds)
        problems_payload[str(pid)] = item
    submissions_payload = submission_summary(db_path)
    with closing(connect(db_path)) as connection:
        recent_submissions = [
            dict(row)
            for row in connection.execute(
                """SELECT problem_id, status, lang, submitted_at, source
                   FROM submissions ORDER BY submitted_at DESC, id DESC LIMIT 10000"""
            ).fetchall()
        ]
    for pid_str, item in problems_payload.items():
        stat = submissions_payload["problems"].get(int(pid_str))
        if stat:
            item.update(stat)
            last_submit = str(stat.get("last_submitted_at") or "")
            last_activity = str(item.get("last_activity_at") or "")
            if last_submit and (not last_activity or last_submit > last_activity):
                item["last_activity_at"] = last_submit
    for pid, stat in submissions_payload["problems"].items():
        if str(pid) not in problems_payload:
            problems_payload[str(pid)] = {
                "rounds": 0,
                "last_viewed_at": None,
                "last_completed_at": None,
                "last_activity_at": None,
                **stat,
            }
            problems_payload[str(pid)]["last_activity_at"] = stat.get("last_submitted_at") or ""
    recent_items = [dict(row) for row in view_events] + complete_events
    recent_items.sort(key=lambda item: str(item["studied_at"]), reverse=True)
    recent = recent_items[:20]
    recent_days = sorted(day_stats, reverse=True)[:14]
    return {
        "today": today,
        "summary": summary,
        "problems": problems_payload,
        "days": [
            {
                "study_date": date,
                "viewed": day_stats[date]["viewed"],
                "rounds": day_stats[date]["rounds"],
                "submits": day_stats[date]["submits"],
            }
            for date in recent_days
        ],
        "recent": recent,
        "recent_submissions": recent_submissions,
        "activity": activity,
        "marks": problem_marks(db_path),
        "submissions": submissions_payload,
    }


def load_library_manifest() -> dict[str, object]:
    """加载书架目录 manifest.json（构建工具生成的模块/章节/路由元数据），带 mtime 内存缓存。"""
    global _MANIFEST_CACHE
    path = ROOT / "library" / "manifest.json"
    if not path.exists():
        return {"modules": [], "routes": {}}
    mtime = path.stat().st_mtime
    # 缓存命中条件：文件修改时间未变 → 直接复用内存里的 manifest，避免每次请求都读盘。
    if _MANIFEST_CACHE is not None and _MANIFEST_CACHE[0] == mtime:
        return _MANIFEST_CACHE[1]
    manifest = json.loads(path.read_text(encoding="utf-8"))
    _MANIFEST_CACHE = (mtime, manifest)
    return manifest


def valid_content(module_id: str, content_id: str) -> bool:
    """校验 (module_id, content_id) 是否真实存在于书架 manifest —— 防止不存在的内容写进学习记录。"""
    manifest = load_library_manifest()
    # 双层命中检测：外层先找 module_id 匹配的模块，内层在该模块 chapters 里找 content_id，
    # 两者都命中才返回 True（防止跨模块引用或不存在的章节混入学习记录）。
    return any(
        module.get("id") == module_id and any(chapter.get("id") == content_id for chapter in module.get("chapters", []))
        for module in manifest.get("modules", [])
    )


def record_content_view(module_id: str, content_id: str, db_path: Path = DB_PATH) -> bool:
    """书架章节浏览事件：与题目 record_view 完全同构（含 60 秒去重），写进 content_events。"""
    if not valid_content(module_id, content_id):
        return False
    studied_at, study_date = now_parts()
    with closing(connect(db_path)) as connection:
        # 同样的 60 秒去重窗口（这里按 content_id 查最近一条 view）。
        recent = connection.execute(
            """SELECT studied_at FROM content_events
               WHERE content_id = ? AND action = 'view' ORDER BY id DESC LIMIT 1""",
            (content_id,),
        ).fetchone()
        if recent:
            last = datetime.fromisoformat(recent["studied_at"])
            if (datetime.fromisoformat(studied_at) - last).total_seconds() < 60:
                return False
        connection.execute(
            """INSERT INTO content_events(module_id, content_id, action, studied_at, study_date)
               VALUES (?, ?, 'view', ?, ?)""",
            (module_id, content_id, studied_at, study_date),
        )
        connection.commit()
    _invalidate_learning_caches(db_path)
    return True


def complete_content(module_id: str, content_id: str, db_path: Path = DB_PATH) -> dict[str, object]:
    """书架章节"完成一轮"：轮次自增 + 写库（事务内原子完成），返回下次到期日。"""
    if not valid_content(module_id, content_id):
        raise ValueError("未知课程章节")
    studied_at, study_date = now_parts()
    with closing(connect(db_path)) as connection:
        # BEGIN IMMEDIATE 立刻拿写锁："取下一轮次 + 插入"同一事务内原子完成，
        # 并发点击也不会开出重复轮次（配合部分唯一索引 uq_content_round 双保险）。
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """SELECT COALESCE(MAX(round_no), 0) + 1 AS next_round
               FROM content_events WHERE content_id = ? AND action = 'complete'""",
            (content_id,),
        ).fetchone()
        round_no = int(row["next_round"])
        connection.execute(
            """INSERT INTO content_events(module_id, content_id, action, studied_at, study_date, round_no)
               VALUES (?, ?, 'complete', ?, ?, ?)""",
            (module_id, content_id, studied_at, study_date, round_no),
        )
        connection.commit()
    _invalidate_learning_caches(db_path)
    # next_due：按章节专用间隔表（REVIEW_INTERVALS_CONTENT）推算的到期日，前端展示"下次复习"。
    return {
        "module_id": module_id,
        "content_id": content_id,
        "round_no": round_no,
        "studied_at": studied_at,
        "next_due": due_after(studied_at, round_no),
    }


def ac_problem_progress(db_path: Path = DB_PATH) -> dict[int, dict[str, object]]:
    """按 AC 日期统计 Hot100 题目轮次：同一天多次 AC 只算一轮。"""
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            """SELECT problem_id,
                      COUNT(DISTINCT substr(submitted_at, 1, 10)) AS rounds,
                      MAX(submitted_at) AS last_completed_at
               FROM submissions WHERE status = 'ac' GROUP BY problem_id"""
        ).fetchall()
    return {
        int(row["problem_id"]): {
            "rounds": int(row["rounds"] or 0),
            "last_completed_at": str(row["last_completed_at"]),
        }
        for row in rows
    }


def problem_review_state(db_path: Path = DB_PATH) -> dict[int, dict[str, object]]:
    """每题推荐/计划用状态：AC 决定是否完成，浏览和 AC 共同决定最近活动。"""
    ac = ac_problem_progress(db_path)
    with closing(connect(db_path)) as connection:
        view_rows = connection.execute(
            """SELECT problem_id, MAX(studied_at) AS last_viewed_at
               FROM study_events WHERE action = 'view' GROUP BY problem_id"""
        ).fetchall()
    info: dict[int, dict[str, object]] = {}
    for row in view_rows:
        pid = int(row["problem_id"])
        info[pid] = {
            "rounds": 0,
            "last_completed_at": "",
            "last_activity_at": str(row["last_viewed_at"] or ""),
        }
    for pid, progress in ac.items():
        entry = info.setdefault(pid, {
            "rounds": 0,
            "last_completed_at": "",
            "last_activity_at": "",
        })
        entry["rounds"] = int(progress["rounds"])
        entry["last_completed_at"] = str(progress["last_completed_at"] or "")
        last = str(entry["last_activity_at"] or "")
        ac_at = str(progress["last_completed_at"] or "")
        if ac_at and (not last or ac_at > last):
            entry["last_activity_at"] = ac_at
    return info


def library_data(db_path: Path = DB_PATH) -> dict[str, object]:
    """书架数据：每个模块的章节总数/已完成数（rounds>0 即算开始学习）+ 每章节的轮次与最近活动。"""
    manifest = load_library_manifest()
    with closing(connect(db_path)) as connection:
        # 非 Hot100 章节仍按手动“完成一轮”；Hot100 题目由 AC 日期自动推进。
        rows = connection.execute(
            """SELECT content_id,
                      SUM(CASE WHEN action = 'complete' THEN 1 ELSE 0 END) AS rounds,
                      MAX(studied_at) AS last_activity_at
               FROM content_events WHERE module_id <> 'hot100' GROUP BY content_id"""
        ).fetchall()
    contents = {str(row["content_id"]): dict(row) for row in rows}
    for pid, progress in ac_problem_progress(db_path).items():
        contents[f"hot100:{pid:04d}"] = {
            "rounds": int(progress["rounds"]),
            "last_activity_at": progress["last_completed_at"],
        }
    # 逐模块统计 total / completed：completed 按"该模块里 rounds>0 的章节数"计算 → 进度条。
    modules: dict[str, dict[str, int]] = {}
    for module in manifest.get("modules", []):
        chapter_ids = [chapter["id"] for chapter in module.get("chapters", [])]
        modules[module["id"]] = {
            "total": len(chapter_ids),
            "completed": sum(1 for content_id in chapter_ids if int(contents.get(content_id, {}).get("rounds") or 0) > 0),
        }
    return {"modules": modules, "contents": contents}


def daily_data(db_path: Path = DB_PATH, module_id: str = "") -> dict[str, object]:
    """间隔重复的“今日待复习”：到期日 <= 今天 的 Hot100 题目与书架章节。

    传 module_id 时只返回该模块的 contents（problems 置空），供书架模块页使用。
    """
    today = datetime.now().astimezone().date().isoformat()
    ac_progress = ac_problem_progress(db_path)
    with closing(connect(db_path)) as connection:
        # 章节侧：传 module_id 时只统计该模块；hot100 模块由 AC 推导，不走手动按钮。
        if module_id == "hot100":
            content_rows = [
                {
                    "content_id": f"hot100:{pid:04d}",
                    "module_id": "hot100",
                    "rounds": int(progress["rounds"]),
                    "last_completed_at": progress["last_completed_at"],
                }
                for pid, progress in ac_progress.items()
                if int(progress["rounds"]) > 0
            ]
        elif module_id:
            content_rows = connection.execute(
                """SELECT content_id, COUNT(*) AS rounds, MAX(studied_at) AS last_completed_at
                   FROM content_events WHERE action = 'complete' AND module_id = ?
                   GROUP BY content_id HAVING COUNT(*) > 0""",
                (module_id,),
            ).fetchall()
        else:
            content_rows = connection.execute(
                """SELECT content_id, COUNT(*) AS rounds, MAX(studied_at) AS last_completed_at
                   FROM content_events
                   WHERE action = 'complete' AND module_id <> 'hot100'
                   GROUP BY content_id HAVING COUNT(*) > 0"""
            ).fetchall()
            content_rows += [
                {
                    "content_id": f"hot100:{pid:04d}",
                    "module_id": "hot100",
                    "rounds": int(progress["rounds"]),
                    "last_completed_at": progress["last_completed_at"],
                }
                for pid, progress in ac_progress.items()
                if int(progress["rounds"]) > 0
            ]

    # 组装题目待复习列表：到期日还没到（> 今天）的跳过，其余带上题名/分类/难度/题解链接。
    problems: list[dict[str, object]] = []
    relearn: list[dict[str, object]] = []   # 逾期 >60 天，需重新学习的题
    if not module_id:
        for pid, progress in ac_progress.items():
            problem = PROBLEM_BY_ID.get(int(pid))
            rounds = int(progress["rounds"])
            if rounds <= 0:
                continue
            due = due_after(str(progress["last_completed_at"]), rounds)
            if due > today:
                continue
            overdue_days = (datetime.fromisoformat(today).date()
                            - datetime.fromisoformat(due).date()).days
            if overdue_days > 60:
                # 逾期超过 60 天：记忆已衰退，复习转为"重新学习"，进今日计划池
                relearn.append({
                    "id": int(pid),
                    "title": problem["title"] if problem else f"题号 {pid}",
                    "category": problem["category"] if problem else "",
                    "difficulty": problem["difficulty"] if problem else "",
                    "rounds": rounds,
                    "due_date": due,
                    "note": (
                        f"books/hot100/03-题解/{problem['folder']}/"
                        f"{Path(problem_filename(problem)).with_suffix('.html').name}"
                        if problem else ""
                    ),
                })
                continue
            problems.append({
                "id": int(pid),
                "title": problem["title"] if problem else f"题号 {pid}",
                "category": problem["category"] if problem else "",
                "difficulty": problem["difficulty"] if problem else "",
                "rounds": rounds,
                "last_completed_at": progress["last_completed_at"],
                "due_date": due,
                "note": (
                    f"books/hot100/03-题解/{problem['folder']}/"
                    f"{Path(problem_filename(problem)).with_suffix('.html').name}"
                    if problem else ""
                ),
            })

    manifest = load_library_manifest()
    # 建立 content_id → (模块/标题/URL) 的查表，给章节补全展示元数据。
    content_index: dict[str, dict[str, str]] = {}
    for module in manifest.get("modules", []):
        for chapter in module.get("chapters", []):
            content_index[str(chapter["id"])] = {
                "module_id": str(module["id"]),
                "module_title": str(module["title"]),
                "title": str(chapter["title"]),
                "url": f"library/{chapter['url']}",
            }
    # 组装章节待复习列表：manifest 查不到的 content_id 直接跳过（防脏数据）。
    contents: list[dict[str, object]] = []
    for row in content_rows:
        meta = content_index.get(str(row["content_id"]))
        if meta is None:
            continue
        rounds = int(row["rounds"])
        due = due_after_content(row["last_completed_at"], rounds)
        if due > today:
            continue
        contents.append({
            "content_id": str(row["content_id"]),
            "title": meta["title"],
            "module_id": meta["module_id"],
            "module_title": meta["module_title"],
            "url": meta["url"],
            "rounds": rounds,
            "last_completed_at": row["last_completed_at"],
            "due_date": due,
        })

    # 汇总口径：due = 到期或过期（<= 今天）；overdue = 严格早于今天；
    # 同时按模块统计 due/overdue 分布，供书架模块页显示到期角标。
    problem_overdue = sum(1 for item in problems if str(item["due_date"]) < today)
    content_overdue = sum(1 for item in contents if str(item["due_date"]) < today)
    modules: dict[str, dict[str, int]] = {}
    for item in contents:
        mid = str(item["module_id"])
        entry = modules.setdefault(mid, {"due": 0, "overdue": 0})
        entry["due"] += 1
        if str(item["due_date"]) < today:
            entry["overdue"] += 1
    summary = {
        "due": len(problems) + len(contents),
        "overdue": problem_overdue + content_overdue,
        "problems": len(problems),
        "overdue_problems": problem_overdue,
        "relearn": len(relearn),
        "contents": len(contents),
        "overdue_contents": content_overdue,
        "modules": modules,
    }
    return {"today": today, "summary": summary, "problems": problems, "relearn": relearn, "contents": contents}


def problem_marks(db_path: Path = DB_PATH) -> dict[str, str]:
    """读全部题目标记 → {题号: mastered|reviewing|weak}，仪表盘/今日计划用它筛薄弱题。"""
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT target_id, mark FROM marks WHERE target_type = 'problem'"
        ).fetchall()
    return {str(row["target_id"]): str(row["mark"]) for row in rows}


def get_settings(db_path: Path = DB_PATH) -> dict[str, str]:
    """读取 settings 表全部 KV → {key: value} 字典。"""
    with closing(connect(db_path)) as connection:
        rows = connection.execute("SELECT key, value FROM settings").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def set_setting(key: str, value: str, db_path: Path = DB_PATH) -> dict[str, str]:
    """写一个设置项：key 白名单 + 长度/格式校验，Upsert 语义（存在即更新）。"""
    if not key or len(key) > 64 or len(value) > 256:
        raise ValueError("设置项不合法")
    # 白名单机制：只有登记过的 key 可写，防止前端/注入写入任意键。
    allowed = {"daily_goal_rounds"}
    if key not in allowed:
        raise ValueError("未知设置项")
    if key == "daily_goal_rounds" and not re.fullmatch(r"\d{1,3}", value):
        raise ValueError("每日目标轮次需为数字")
    with closing(connect(db_path)) as connection:
        connection.execute(
            """INSERT INTO settings(key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )
        connection.commit()
    _invalidate_learning_caches(db_path)
    return {"key": key, "value": value}


def valid_content_id(content_id: str) -> bool:
    """仅校验 content_id 是否存在于书架（不区分模块），set_mark 打章节标记时用。"""
    manifest = load_library_manifest()
    return any(
        str(chapter.get("id")) == content_id
        for module in manifest.get("modules", [])
        for chapter in module.get("chapters", [])
    )


def set_mark(target_type: str, target_id: str, mark: str, db_path: Path = DB_PATH) -> dict[str, str]:
    """设置/清除标记：mark 为 '' 表示删除标记，否则校验枚举值并 Upsert 到 marks 表。"""
    # 入参三道校验：① 目标类型枚举 ② 标记枚举（'' 表示删除）③ 目标必须真实存在
    # （题号须在题库、章节须在 manifest），防止未知 ID 写进 marks 表。
    if target_type not in ("problem", "content"):
        raise ValueError("未知标记类型")
    if mark != "" and mark not in ("mastered", "reviewing", "weak"):
        raise ValueError("未知标记状态")
    if target_type == "problem":
        try:
            if int(target_id) not in PROBLEM_BY_ID:
                raise ValueError("未知题号")
        except (TypeError, ValueError) as exc:
            raise ValueError("未知题号") from exc
    elif not valid_content_id(target_id):
        raise ValueError("未知章节")
    studied_at, _ = now_parts()
    with closing(connect(db_path)) as connection:
        # mark 为空 → 删除该目标的标记；否则插入或更新（ON CONFLICT 主键 (target_type, target_id)）。
        if mark == "":
            connection.execute(
                "DELETE FROM marks WHERE target_type = ? AND target_id = ?",
                (target_type, target_id),
            )
        else:
            connection.execute(
                """INSERT INTO marks(target_type, target_id, mark, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(target_type, target_id)
                   DO UPDATE SET mark = excluded.mark, updated_at = excluded.updated_at""",
                (target_type, target_id, mark, studied_at),
            )
        connection.commit()
    _invalidate_learning_caches(db_path)
    return {"target_type": target_type, "target_id": target_id, "mark": mark}


def problem_note(problem: dict[str, object]) -> str:
    """生成题解页相对路径（03-题解/<folder>/<文件名>.html），供前端跳转与导出链接使用。"""
    return f"books/hot100/03-题解/{problem['folder']}/{Path(problem_filename(problem)).with_suffix('.html').name}"


def problem_card(problem: dict[str, object]) -> tuple[str, str, str]:
    """从题目页提取 Anki 卡字段：记忆锚点、复杂度、力扣链接。"""
    # 先读题解 Markdown（utf-8-sig 兼容 BOM）；提取不到时兜底用 method 字段当记忆锚点。
    md_path = ROOT / "books" / "hot100" / "03-题解" / problem["folder"] / Path(problem_filename(problem)).with_suffix(".md")
    anchor = str(problem["method"])
    complexity = ""
    if md_path.exists():
        text = md_path.read_text(encoding="utf-8-sig")
        # “## 核心不变量”标题下的引用行就是记忆锚点（题目页约定的写作格式）。
        anchor_match = re.search(r"## 核心不变量\s*\n> ?([^\n]+)", text)
        if anchor_match:
            anchor = anchor_match.group(1).strip()
        # 复杂度表行 → "时间 / 空间"；缺一项用 '-' 占位。
        time_match = re.search(r"^\| 时间复杂度 \| ([^|]+) \|", text, re.M)
        space_match = re.search(r"^\| 空间复杂度 \| ([^|]+) \|", text, re.M)
        if time_match or space_match:
            complexity = f"{time_match.group(1).strip() if time_match else '-'} / {space_match.group(1).strip() if space_match else '-'}"
    # 力扣链接：本地题库登记了 slug 才拼链接，没登记返回空串（前端自行隐藏）。
    slug = LEETCODE_SLUGS.get(int(problem["id"]))
    leetcode_url = f"https://leetcode.cn/problems/{slug}/" if slug else ""
    return anchor, complexity, leetcode_url


def pick_problem(
    db_path: Path = DB_PATH,
    randomize: bool = False,
    category: str = "",
    difficulty: str = "",
) -> dict[str, object]:
    """今日推荐：未完成优先、按最近活动最久排序；randomize 时随机抽一题。"""
    info = problem_review_state(db_path)
    # 候选集：按专题/难度过滤题目清单；条件为空表示不限制（pick_problem 与 mock_exam 共用过滤逻辑）。
    candidates = [
        p for p in PROBLEM_BY_ID.values()
        if (not category or str(p["category"]) == category)
        and (not difficulty or str(p["difficulty"]) == difficulty)
    ]
    if not candidates:
        raise ValueError("没有匹配的题目")
    if randomize:
        chosen = random.choice(candidates)
    else:
        # 排序键 (完成否, 最近活动时间)：未完成优先、再按"最久没碰"排序；min 取键最小者。
        def key(p: dict[str, object]) -> tuple[int, str]:
            row = info.get(int(p["id"]))
            rounds = int(row["rounds"]) if row else 0
            last = str(row["last_activity_at"] or "") if row else ""
            return (1 if rounds else 0, last)
        chosen = min(candidates, key=key)
    return {
        "id": int(chosen["id"]),
        "title": chosen["title"],
        "category": chosen["category"],
        "difficulty": chosen["difficulty"],
        "method": chosen["method"],
        "rounds": int(info.get(int(chosen["id"]), {}).get("rounds") or 0),
        "note": problem_note(chosen),
    }


def mock_exam(
    count: int = 10,
    category: str = "",
    difficulty: str = "",
) -> dict[str, object]:
    """限时模拟组卷：按条件随机抽 count 道不重复题目。"""
    # 候选集：按专题/难度过滤题目清单；条件为空表示不限制（pick_problem 与 mock_exam 共用过滤逻辑）。
    candidates = [
        p for p in PROBLEM_BY_ID.values()
        if (not category or str(p["category"]) == category)
        and (not difficulty or str(p["difficulty"]) == difficulty)
    ]
    if not candidates:
        raise ValueError("没有匹配的题目")
    # 抽题量夹逼到 1~候选数；random.sample 无放回，保证组卷不重复。
    count = max(1, min(count, len(candidates)))
    chosen = random.sample(candidates, count)
    return {
        "count": len(chosen),
        "problems": [
            {
                "id": int(p["id"]),
                "title": p["title"],
                "category": p["category"],
                "difficulty": p["difficulty"],
                "method": p["method"],
                "note": problem_note(p),
            }
            for p in chosen
        ],
    }


def today_plan(db_path: Path = DB_PATH, count: int = 3, randomize: bool = False) -> dict[str, object]:
    """今日计划（与今日待复习互补）：已排期 → 未学习 → 需重学（逾期 >60 天）
    → 轮数较少；每类内部按学习路径顺序；排除今日待复习中的题。"""
    today = datetime.now().astimezone().date().isoformat()
    daily = daily_data(db_path)
    due_ids = {int(item["id"]) for item in daily["problems"]}
    relearn_ids = {int(item["id"]) for item in daily.get("relearn", [])}
    info = problem_review_state(db_path)
    count = max(1, min(count, 100))

    def entry(pid: int, reason: str) -> dict[str, object]:
        p2 = PROBLEM_BY_ID[pid]
        return {
            "id": pid,
            "title": p2["title"],
            "category": p2["category"],
            "difficulty": p2["difficulty"],
            "method": p2["method"],
            "note": problem_note(p2),
            "reason": reason,
        }

    # 已排期（用户显式"纳入明天计划"，到期自动进入）。
    # 只清理"已过期"（for_date < today）的 pin；当天的 pin 保留可重复读取，
    # 避免中控台/面板多次拉取互相吞掉排期（GET 无副作用原则）。
    pinned: list[int] = []
    with closing(connect(db_path)) as connection:
        connection.execute("DELETE FROM plan_pins WHERE for_date < ?", (today,))
        for row in connection.execute(
            "SELECT problem_id FROM plan_pins WHERE for_date <= ? ORDER BY for_date", (today,)
        ):
            pid = int(row["problem_id"])
            if pid in PROBLEM_BY_ID:
                pinned.append(pid)

    # 候选池：学习路径顺序，排除待复习（≤60 天逾期）与已排期
    pool = []
    for pid in PROBLEM_BY_ID:
        if pid in due_ids or pid in pinned:
            continue
        rounds = int(info.get(pid, {}).get("rounds") or 0)
        reason = ("未学习" if rounds == 0
                  else "需重学" if pid in relearn_ids
                  else "轮数较少")
        prio = 1 if rounds == 0 else (2 if pid in relearn_ids else 3)
        pool.append((prio, pid, rounds, reason))
    pool.sort(key=lambda t2: (t2[0], t2[1]))

    if randomize:
        picked = random.sample(pool, min(count, len(pool)))
        picked.sort(key=lambda t2: (t2[0], t2[1]))
        items = [entry(pid, reason) for _, pid, _, reason in picked]
    else:
        items = [entry(pid, reason) for _, pid, _, reason in pool[:count]]
    items = [entry(pid, "已排期") for pid in pinned] + items
    return {"today": today, "count": len(items), "items": items}


def weaklist(db_path: Path = DB_PATH) -> dict[str, object]:
    """薄弱题清单：含专题、轮次、最近复习、标记时间，按标记时间排序。"""
    with closing(connect(db_path)) as connection:
        # 手动薄弱标记（按标记时间排序）。
        manual_marks = [dict(row) for row in connection.execute(
            "SELECT target_id, updated_at FROM marks WHERE target_type='problem' AND mark='weak' ORDER BY updated_at"
        )]
        # 每题首次浏览时间（展示"什么时候开始学这道题"）。
        view_rows = connection.execute(
            "SELECT problem_id, MIN(studied_at) AS first_view FROM study_events WHERE action='view' GROUP BY problem_id"
        ).fetchall()
    info = {
        pid: {"rounds": int(progress["rounds"]), "last_completed_at": progress["last_completed_at"]}
        for pid, progress in ac_problem_progress(db_path).items()
    }
    first_view = {int(row["problem_id"]): str(row["first_view"]) for row in view_rows}
    submissions = submission_summary(db_path)
    all_marks = problem_marks(db_path)
    manual_by_id = {int(row["target_id"]): row for row in manual_marks}
    auto_by_id: dict[int, dict[str, object]] = {}
    for pid_text in submissions["auto_weak"]:
        pid = int(pid_text)
        if pid not in PROBLEM_BY_ID:
            continue
        if all_marks.get(pid_text) in ("mastered", "reviewing"):
            continue
        auto_by_id[pid] = submissions["problems"][pid]

    combined: list[tuple[int, str, str, dict[str, object]]] = []
    for pid, row in manual_by_id.items():
        if pid in PROBLEM_BY_ID:
            combined.append((pid, str(row["updated_at"]), "手动标记", row))
    for pid, stat in auto_by_id.items():
        if pid in manual_by_id:
            continue
        rate = stat.get("pass_rate")
        reason = f"AC 通过率 {rate * 100:.0f}%" if rate is not None else "AC 通过率低于 50%"
        combined.append((pid, str(stat.get("last_submitted_at") or ""), reason, stat))
    combined.sort(key=lambda item: item[1])

    items: list[dict[str, object]] = []
    for pid, _marked_at, reason, source in combined:
        p = PROBLEM_BY_ID.get(pid)
        if not p:
            continue
        row = info.get(pid)
        marked_at = str(source.get("updated_at") or source.get("last_submitted_at") or "")
        items.append({
            "id": pid,
            "title": p["title"],
            "category": p["category"],
            "difficulty": p["difficulty"],
            "method": p["method"],
            "note": problem_note(p),
            "rounds": int(row["rounds"]) if row else 0,
            "last_completed_at": str(row["last_completed_at"]) if row else "",
            "first_view": first_view.get(pid, ""),
            "marked_at": marked_at,
            "reason": reason,
        })
    return {"count": len(items), "items": items}


def export_data(kind: str, db_path: Path = DB_PATH) -> tuple[str, str, str]:
    """返回 (content_type, filename, data)。kind: anki / weak / records。"""
    # anki：CSV 全量导出，供 Anki 批量导入；字段=题号/题名/记忆锚点/方法/复杂度/题解链接/力扣链接。
    #   \ufeff 是 UTF-8 BOM，避免 Excel 打开中文乱码；引号转义成 "" 满足 CSV 转义规则。
    if kind == "anki":
        rows: list[str] = ["题号,题名,记忆锚点,核心方法,时间/空间复杂度,题解链接,力扣链接"]
        for p in PROBLEM_BY_ID.values():
            title = str(p["title"]).replace('"', '""')
            method = str(p["method"]).replace('"', '""')
            anchor, complexity, leetcode_url = problem_card(p)
            anchor = anchor.replace('"', '""')
            complexity = complexity.replace('"', '""')
            rows.append(
                f'"{p["id"]}","{title}","{anchor}","{method}","{complexity}","{problem_note(p)}","{leetcode_url}"'
            )
        return "text/csv; charset=utf-8", "hot100-anki.csv", "\ufeff" + "\n".join(rows)
    # weak：Markdown 表格清单，只列标记为 weak 的题（按题号升序，可贴进笔记/日报）。
    if kind == "weak":
        marks = problem_marks(db_path)
        lines = ["# Hot 100 薄弱题清单", "", "| 题号 | 题目 | 难度 | 最近学习 |", "|---|---|---|---|"]
        for pid_str, _mark in sorted(marks.items(), key=lambda item: int(item[0])):
            if _mark != "weak":
                continue
            p = PROBLEM_BY_ID.get(int(pid_str))
            if not p:
                continue
            lines.append(f"| {p['id']} | [{p['title']}]({problem_note(p)}) | {p['difficulty']} | 见学习站 |")
        return "text/markdown; charset=utf-8", "hot100-薄弱清单.md", "\n".join(lines)
    # records：四张业务表全量导出为 JSON（题目/章节/标记/设置），可作备份或数据迁移。
    if kind == "records":
        with closing(connect(db_path)) as connection:
            problems = [dict(row) for row in connection.execute(
                "SELECT problem_id, action, studied_at, study_date, round_no FROM study_events ORDER BY id")]
            contents = [dict(row) for row in connection.execute(
                "SELECT module_id, content_id, action, studied_at, study_date, round_no FROM content_events ORDER BY id")]
            marks = [dict(row) for row in connection.execute(
                "SELECT target_type, target_id, mark, updated_at FROM marks ORDER BY updated_at")]
            settings = [dict(row) for row in connection.execute("SELECT key, value FROM settings ORDER BY key")]
            submissions = [dict(row) for row in connection.execute(
                "SELECT id, problem_id, status, lang, runtime_ms, memory_kb, submitted_at, source, lc_id FROM submissions ORDER BY id"
            )]
        payload = {
            "problems": problems,
            "contents": contents,
            "submissions": submissions,
            "marks": marks,
            "settings": settings,
        }
        return "application/json; charset=utf-8", "hot100-records.json", json.dumps(payload, ensure_ascii=False, indent=2)
    # weekly：本周（本周一 00:00 起）统计生成 Markdown 周报：轮次/活跃天数/连击/薄弱清单。
    if kind == "weekly":
        now = datetime.now().astimezone()
        monday = (now - timedelta(days=now.weekday())).date()
        monday_iso = monday.isoformat()
        today_iso = now.date().isoformat()
        with closing(connect(db_path)) as connection:
            problem_rounds = int(connection.execute(
                """SELECT COUNT(*) AS n FROM (
                    SELECT problem_id, substr(submitted_at, 1, 10) AS d
                    FROM submissions WHERE status = 'ac' AND substr(submitted_at, 1, 10) >= ?
                    GROUP BY problem_id, d
                )""",
                (monday_iso,),
            ).fetchone()["n"] or 0)
            content_rounds = int(connection.execute(
                "SELECT COUNT(*) AS n FROM content_events WHERE action='complete' AND module_id <> 'hot100' AND study_date >= ?",
                (monday_iso,),
            ).fetchone()["n"] or 0)
            active_days = int(connection.execute(
                """SELECT COUNT(DISTINCT study_date) AS n FROM (
                    SELECT study_date FROM study_events WHERE action = 'view' AND study_date >= ?
                    UNION
                    SELECT substr(submitted_at, 1, 10) FROM submissions WHERE substr(submitted_at, 1, 10) >= ?
                    UNION
                    SELECT study_date FROM content_events
                    WHERE module_id <> 'hot100' AND study_date >= ?
                )""",
                (monday_iso, monday_iso, monday_iso),
            ).fetchone()["n"] or 0)
            active_dates_all = {str(r["study_date"]) for r in connection.execute(
                """SELECT study_date FROM study_events WHERE action = 'view'
                   UNION SELECT substr(submitted_at, 1, 10) AS study_date FROM submissions
                   UNION SELECT study_date FROM content_events WHERE module_id <> 'hot100'"""
            )}
        streak = 0
        cursor = now.date()
        if cursor.isoformat() not in active_dates_all:
            cursor -= timedelta(days=1)
        while cursor.isoformat() in active_dates_all:
            streak += 1
            cursor -= timedelta(days=1)
        marks = problem_marks(db_path)
        weak_titles = [
            f"{PROBLEM_BY_ID[int(k)]['id']}. {PROBLEM_BY_ID[int(k)]['title']}"
            for k, v in marks.items() if v == "weak" and int(k) in PROBLEM_BY_ID
        ]
        lines = [
            "# 学习周报",
            "",
            f"统计周期：{monday_iso} ~ {today_iso}",
            "",
            f"- 本周完成轮次：题目 {problem_rounds} 轮 + 章节 {content_rounds} 轮",
            f"- 本周活跃天数：{active_days} 天",
            f"- 当前连续学习：{streak} 天",
            f"- 薄弱题：{len(weak_titles)} 道",
            "",
            "## 薄弱清单",
            "",
        ]
        lines += [f"- {title}" for title in weak_titles] or ["（本周无薄弱标记）"]
        lines += [
            "",
            "## 下周建议",
            "",
            "- 优先复习到期题目（见面板“今日待复习”）；",
            "- 每天先做薄弱题，再开新题；",
            "- 保持连击：每次 AC 都会自动推进一轮，隔日复习节奏更稳。",
            "",
        ]
        return "text/markdown; charset=utf-8", "hot100-周报.md", "\n".join(lines)
    # 未支持的 kind 抛 ValueError → do_GET 捕获后返回 400（db 备份在 do_GET 内特判，不走这里）。
    raise ValueError("未知导出类型")


# —— 力扣刷题记录（NEW-REQ-005：submissions + 力扣连接）——

# 提交记录合法来源：手动录入 / 浏览器书签脚本 / 浏览器扩展 / 力扣同步；
# 非白名单来源在 record_submission 里会被宽容地降级成 manual（而不是报错）。
VALID_SUBMIT_SOURCES = ("manual", "bookmarklet", "extension", "sync")


def record_submission(
    problem_id: int,
    status: str,
    lang: str = "",
    runtime_ms: int | None = None,
    memory_kb: int | None = None,
    source: str = "manual",
    db_path: Path = DB_PATH,
) -> dict[str, object]:
    """记录一次力扣提交结果（ac/wa）。problem_id/status/source 白名单校验；
    runtime_ms/memory_kb 严格转整数（脏类型报 400 而非落库时 500）。"""
    if problem_id not in PROBLEM_BY_ID:
        raise ValueError("未知题号")
    if status not in ("ac", "wa"):
        raise ValueError("未知提交状态")
    if source not in VALID_SUBMIT_SOURCES:
        source = "manual"

    def optional_int(value: object, name: str) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)  # type: ignore[arg-type] - 脏类型（字符串数字/bool）在此收敛
        except (TypeError, ValueError):
            raise ValueError(f"{name} 必须是整数")

    runtime_ms = optional_int(runtime_ms, "runtime_ms")
    memory_kb = optional_int(memory_kb, "memory_kb")
    studied_at, study_date = now_parts()
    with closing(connect(db_path)) as connection:
        # 直接 INSERT 不查重：同题多次 ac/wa 都是合法历史记录流；
        # lang[:40] 截断语言名，防御超长脏数据撑大数据库。
        connection.execute(
            """INSERT INTO submissions(problem_id, status, lang, runtime_ms, memory_kb, submitted_at, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (problem_id, status, lang[:40], runtime_ms, memory_kb, studied_at, source),
        )
        connection.commit()
    _invalidate_learning_caches(db_path)
    return {"problem_id": problem_id, "status": status, "submitted_at": studied_at}


def submissions_for_problem(problem_id: int, limit: int = 50, db_path: Path = DB_PATH) -> list[dict[str, object]]:
    """返回单题提交记录（按 id 倒序取最近 limit 条，limit 夹逼到 1~200 防极端值）。"""
    rows = []
    with closing(connect(db_path)) as connection:
        for row in connection.execute(
            """SELECT id, problem_id, status, lang, runtime_ms, memory_kb, submitted_at, source
               FROM submissions WHERE problem_id = ? ORDER BY id DESC LIMIT ?""",
            (problem_id, min(max(limit, 1), 200)),
        ):
            rows.append(dict(row))
    return rows


def submission_summary(db_path: Path = DB_PATH) -> dict[str, object]:
    """全站提交统计：今日 AC/提交、累计 AC 次数、已解决题数、通过率、每题是否 AC 过。"""
    today = datetime.now().astimezone().date().isoformat()
    with closing(connect(db_path)) as connection:
        # 累计 AC 次数按每次 AC 提交累计；已解决题数按题目去重。
        row = connection.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN status = 'ac' AND substr(submitted_at, 1, 10) = ? THEN 1 ELSE 0 END), 0) AS today_ac,
                 COALESCE(SUM(CASE WHEN substr(submitted_at, 1, 10) = ? THEN 1 ELSE 0 END), 0) AS today_submits,
                 COALESCE(SUM(CASE WHEN status = 'ac' THEN 1 ELSE 0 END), 0) AS total_ac,
                 COALESCE(COUNT(DISTINCT CASE WHEN status = 'ac' THEN problem_id END), 0) AS solved_ac,
                 COALESCE(SUM(1), 0) AS total_submits
               FROM submissions""",
            (today, today),
        ).fetchone()
        problem_rows = connection.execute(
            """SELECT problem_id,
                      MAX(CASE WHEN status = 'ac' THEN 1 ELSE 0 END) AS ever_ac,
                      COUNT(*) AS submits,
                      SUM(CASE WHEN status = 'ac' THEN 1 ELSE 0 END) AS ac_submits,
                      MAX(submitted_at) AS last_submitted_at
               FROM submissions GROUP BY problem_id"""
        ).fetchall()
        last_rows = connection.execute(
            """SELECT s.problem_id, s.status, s.submitted_at
               FROM submissions s
               WHERE s.id IN (SELECT MAX(id) FROM submissions GROUP BY problem_id)"""
        ).fetchall()
    summary = {key: int(row[key] or 0) for key in row.keys()}
    # 通过率 = AC 提交次数 / 总提交次数；一条提交都没有 → None（前端显示"暂无数据"而非除零）。
    summary["pass_rate"] = round(summary["total_ac"] / summary["total_submits"], 3) if summary["total_submits"] else None
    last_map = {int(r["problem_id"]): dict(r) for r in last_rows}
    problems: dict[int, dict[str, object]] = {}
    auto_weak: dict[str, bool] = {}
    for row in problem_rows:
        pid = int(row["problem_id"])
        submits = int(row["submits"] or 0)
        ac_submits = int(row["ac_submits"] or 0)
        pass_rate = round(ac_submits / submits, 3) if submits else None
        last = last_map.get(pid, {})
        problems[pid] = {
            "submits": submits,
            "ac_submits": ac_submits,
            "pass_rate": pass_rate,
            "last_submitted_at": str(row["last_submitted_at"]) if row["last_submitted_at"] else "",
            "last_status": str(last.get("status") or ""),
        }
        if submits and pass_rate is not None and pass_rate < 0.5:
            auto_weak[str(pid)] = True
    return {
        "summary": summary,
        "ever_ac": {int(r["problem_id"]): bool(r["ever_ac"]) for r in problem_rows},
        "problems": problems,
        "auto_weak": auto_weak,
    }


def get_credentials(db_path: Path = DB_PATH) -> dict[str, str]:
    """读取全部力扣凭证（session/csrf）→ {key: value}，供连接页/同步逻辑使用。"""
    with closing(connect(db_path)) as connection:
        rows = connection.execute("SELECT key, value FROM credentials").fetchall()
    return {str(r["key"]): str(r["value"]) for r in rows}


def set_credentials(pairs: dict[str, str], db_path: Path = DB_PATH) -> None:
    """保存力扣凭证（仅本机 SQLite；可一键清除）。"""
    studied_at, _ = now_parts()
    with closing(connect(db_path)) as connection:
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
    """一键清空全部力扣凭证（等价"退出力扣连接"）；已同步的提交记录不受影响。"""
    with closing(connect(db_path)) as connection:
        connection.execute("DELETE FROM credentials")
        connection.commit()


def _leetcode_headers(credentials: dict[str, str]) -> dict[str, str]:
    # 组装力扣 API 请求头：伪装浏览器 UA/Referer；有会话则拼 Cookie（session[+csrf]），
    # 并单独带 X-CSRFToken 头；无凭证时只发基础头（供匿名探测用）。
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
    """力扣 GET：优先 curl_cffi（模拟 Chrome TLS 指纹）。海外机房 IP 用标准库
    urllib 访问 leetcode.cn 会被 Cloudflare"Just a moment"挑战页 403 拦截
    （与会话是否有效无关），curl_cffi 的浏览器指纹可正常通过；未安装时回退
    标准库 urllib。非 2xx 一律合成 urllib.error.HTTPError 抛出，调用方逻辑不变。"""
    import io
    import urllib.error
    try:
        from curl_cffi import requests as _curl_requests
    except ImportError:
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError:
            raise
    resp = _curl_requests.get(url, headers=headers, timeout=timeout, impersonate="chrome")
    if resp.status_code >= 400:
        # 合成 HTTPError 让调用方沿用同一套状态码分支；响应体挂到 fp 供 exc.read() 识别挑战页。
        raise urllib.error.HTTPError(
            url, resp.status_code, "HTTP Error", resp.headers, io.BytesIO(resp.content)
        )
    return resp.content


def _fetch_json_with_retry(
    url: str,
    headers: dict[str, str],
    timeout: int = 25,
    retries: int = 3,
    backoff: float = 2.0,
) -> dict:
    """带退避重试的力扣 JSON 请求，缓解翻页过快触发的 403/429/5xx 风控。"""
    import urllib.error

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return json.loads(_lc_http_get(url, headers, timeout).decode("utf-8"))
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


# ---- 力扣状态缓存：/api/leetcode/status 的服务端校验需要实时访问
# leetcode.cn（海外服务器延迟波动大），结果按 会话串 缓存 10 分钟；
# connect/clear 等改变凭证的操作主动失效。----
LC_STATUS_TTL = 600.0
_LC_STATUS_CACHE: dict[tuple, tuple[float, dict]] = {}
_LC_STATUS_LOCK = threading.Lock()


def lc_status_cached(db_path: Path, credentials: dict[str, str], force: bool = False) -> dict:
    """带 TTL 缓存的力扣连接状态查询；force=True 跳过缓存（连接测试用）。"""
    key = (str(db_path), credentials.get("leetcode_session", ""))
    now = time.time()
    if not force:
        with _LC_STATUS_LOCK:
            hit = _LC_STATUS_CACHE.get(key)
            if hit and now - hit[0] < LC_STATUS_TTL:
                return hit[1]
    result = leetcode_status(credentials)
    with _LC_STATUS_LOCK:
        _LC_STATUS_CACHE[key] = (now, result)
    return result


def lc_status_invalidate(db_path: Path) -> None:
    """凭证变化后清空该库的力扣状态缓存。"""
    with _LC_STATUS_LOCK:
        for key in [k for k in _LC_STATUS_CACHE if k[0] == str(db_path)]:
            _LC_STATUS_CACHE.pop(key, None)


def leetcode_status(credentials: dict[str, str], timeout: int = 20) -> dict[str, object]:
    """测试力扣连接：调公开题目列表接口，校验登录态字段。"""
    import urllib.error

    if not credentials.get("leetcode_session"):
        return {"connected": False, "reason": "no-session", "message": "尚未保存 LEETCODE_SESSION"}
    # 探测原理：公开题目列表接口在登录态下会带 user_name —— 用户名非空即视为会话生效
    # （num_solved 仅作附加展示）；401/403 → 会话过期或 IP 被风控，其余 HTTP/网络错误分别归类。
    try:
        data = json.loads(_lc_http_get(
            "https://leetcode.cn/api/problems/all/", _leetcode_headers(credentials), timeout
        ).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_head = b""
        try:
            body_head = exc.read(500)
        except Exception:  # noqa: BLE001 - 读不到响应体不影响分类
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
    if user_name and num_solved > 0:
        return {"connected": True, "user_name": user_name, "num_solved": num_solved}
    if user_name:
        return {"connected": True, "user_name": user_name, "num_solved": num_solved}
    return {"connected": False, "reason": "anonymous", "message": "返回匿名数据，会话未生效"}


def leetcode_sync(
    credentials: dict[str, str],
    db_path: Path = DB_PATH,
    limit: int = 100,
    full: bool = False,
    progress=None,
) -> dict[str, object]:
    """同步力扣提交记录。

    full=True：分页翻到底，同步全部历史提交（首次建议）；full=False：只同步最近 limit 条（增量日常用）。
    所有记录用提交接口的真实 timestamp（日期不为“同步当天”），并以力扣提交 ID（lc_id）唯一去重。
    ① problems/all 的已解答仅作兜底：该题没有任何 AC 提交记录时才从中补一条（用其最早提交时间，拿不到则跳过，不伪造日期）。
    """
    import urllib.request
    import urllib.error

    if not credentials.get("leetcode_session"):
        raise ValueError("未保存力扣会话，请先在“力扣连接”页保存")
    headers = _leetcode_headers(credentials)
    results: dict[str, object] = {
        "solved_added": 0, "solved_existing": 0,
        "submissions_added": 0, "submissions_seen": 0, "sync_errors": [],
        "full": bool(full),
    }

    try:
        data = _fetch_json_with_retry("https://leetcode.cn/api/problems/all/", headers)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"同步失败：力扣返回 HTTP {exc.code}（会话可能过期或被风控）")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"同步失败：{type(exc).__name__}: {exc}")

    if progress is not None:
        progress("已读取力扣题目列表")

    slug_to_id = {slug: pid for pid, slug in LEETCODE_SLUGS.items()}
    # 题名→题号：本地中文题名为主，英文题名（经 slug）兜底。
    title_to_id: dict[str, int] = {}
    for pid, problem in PROBLEM_BY_ID.items():
        title_to_id.setdefault(str(problem["title"]).strip(), int(pid))
    for pair in data.get("stat_status_pairs", []):
        stat = pair.get("stat", {})
        title = str(stat.get("question__title") or "").strip()
        pid = slug_to_id.get(str(stat.get("question__title_slug") or ""))
        if title and pid is not None:
            title_to_id.setdefault(title, int(pid))

    # —— 全量/增量拉取提交记录 ——
    collected: list[dict[str, object]] = []  # 每条: pid,status,lang,runtime_ms,memory_kb,submitted_at,lc_id
    fetch_errors: list[str] = []
    offset = 0
    page = 0
    max_pages = 50 if full else 1  # full 封顶 5000 条，防止异常无限翻页
    if progress is not None:
        progress("开始拉取提交记录")
    while True:
        page += 1
        if page > max_pages:
            fetch_errors.append(f"已达分页上限（{max_pages} 页），如有更多历史请再次全量同步")
            break
        try:
            payload = _fetch_json_with_retry(
                f"https://leetcode.cn/api/submissions/?offset={offset}&limit={min(int(limit), 100)}",
                headers,
            )
        except Exception as exc:  # noqa: BLE001
            fetch_errors.append(
                f"第 {page} 页拉取失败：{type(exc).__name__}: {exc}"
                "（已自动重试，仍失败可能是力扣风控，请稍后重试或重新复制 LEETCODE_SESSION）"
            )
            if progress is not None:
                progress(f"第 {page} 页拉取失败，已停止拉取")
            break
        dump = payload.get("submissions_dump") or []
        if not dump:
            break
        for item in dump:
            if str(item.get("is_pending")) not in ("", "Not Pending"):
                continue  # 判题中/失败样本跳过
            title = str(item.get("title") or "").strip()
            pid = title_to_id.get(title)
            if pid is None:
                continue
            lc_id = item.get("id")
            status = "ac" if str(item.get("status_display")) == "Accepted" else "wa"
            ts = str(item.get("timestamp") or "")
            submitted_at = (
                datetime.fromtimestamp(int(ts)).astimezone().isoformat(timespec="seconds")
                if ts.isdigit()
                else now_parts()[0]
            )
            collected.append({
                "pid": pid,
                "status": status,
                "lang": str(item.get("lang") or "")[:40],
                "runtime_ms": _parse_ms(str(item.get("runtime") or "")),
                "memory_kb": _parse_kb(str(item.get("memory") or "")),
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

    # —— 写库（lc_id 唯一去重，批量插入）——
    with closing(connect(db_path)) as connection:
        existing_lc = {
            int(r["lc_id"])
            for r in connection.execute(
                "SELECT lc_id FROM submissions WHERE lc_id IS NOT NULL"
            ).fetchall()
        }
        rows: list[tuple[object, ...]] = []
        for item in collected:
            if item["lc_id"] is not None and item["lc_id"] in existing_lc:
                continue
            if item["lc_id"] is not None:
                existing_lc.add(item["lc_id"])
            rows.append((
                item["pid"], item["status"], item["lang"],
                item["runtime_ms"], item["memory_kb"], item["submitted_at"],
                "sync", item["lc_id"],
            ))
        if rows:
            connection.executemany(
                """INSERT INTO submissions(problem_id, status, lang, runtime_ms, memory_kb, submitted_at, source, lc_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
        results["submissions_added"] = len(rows)
        connection.commit()
        if progress is not None:
            progress("提交记录已写入本地数据库")

        # —— 已解答兜底：某题在 problems/all 为 ac 但库中无任何 AC 提交记录时，
        #     用该题最早一次提交的时间补一条；拿不到真实时间则跳过（不伪造“今天”）。 ——
        earliest_ac: dict[int, str] = {}
        for pid in slug_to_id.values():
            found = connection.execute(
                "SELECT 1 FROM submissions WHERE problem_id = ? AND status = 'ac' LIMIT 1", (pid,)
            ).fetchone()
            if found:
                results["solved_existing"] = int(results["solved_existing"]) + 1
                continue
            times = [
                i["submitted_at"] for i in collected if i["pid"] == pid and i["status"] == "ac"
            ]
            if times:
                earliest_ac[pid] = min(times)
        for pair in data.get("stat_status_pairs", []):
            if pair.get("status") != "ac":
                continue
            pid = slug_to_id.get(str(pair.get("stat", {}).get("question__title_slug") or ""))
            if pid is None:
                continue
            if pid in earliest_ac:
                connection.execute(
                    """INSERT INTO submissions(problem_id, status, lang, submitted_at, source, lc_id)
                       VALUES (?, 'ac', '', ?, 'sync', NULL)""",
                    (pid, earliest_ac[pid]),
                )
                results["solved_added"] = int(results["solved_added"]) + 1
        connection.commit()
    results["sync_errors"] = fetch_errors
    _invalidate_learning_caches(db_path)
    return results


def start_leetcode_sync_task(
    credentials: dict[str, str],
    full: bool,
    owner: str = "",
    db_path: Path = DB_PATH,
) -> str:
    """后台执行力扣同步，返回 task_id；前端轮询状态接口打印进度日志。
    owner 记录发起用户名：状态轮询接口校验归属，防止跨用户窥探进度。"""
    task_id = uuid.uuid4().hex[:12]
    task: dict[str, object] = {
        "logs": [],
        "running": True,
        "result": None,
        "error": None,
        "owner": owner,
    }

    def progress(text: str) -> None:
        with SYNC_TASKS_LOCK:
            logs = task["logs"]
            if isinstance(logs, list):
                logs.append({"text": text, "at": now_parts()[0]})

    def worker() -> None:
        try:
            task["result"] = leetcode_sync(
                credentials,
                db_path=db_path,
                full=full,
                progress=progress,
            )
        except Exception as exc:  # noqa: BLE001 - 错误交给前端展示
            task["error"] = str(exc)
        finally:
            # The worker may have committed rows before a later network or
            # parsing error.  Invalidate on both success and failure, and do it
            # before publishing running=False so the completed task never
            # races a GET that can still observe the old snapshot.
            try:
                _invalidate_learning_caches(db_path)
            finally:
                with SYNC_TASKS_LOCK:
                    task["running"] = False

    with SYNC_TASKS_LOCK:
        SYNC_TASKS[task_id] = task
    threading.Thread(target=worker, daemon=True).start()

    # 只保留最近 10 个已完成任务，防止长期运行后内存累积。
    with SYNC_TASKS_LOCK:
        completed = [tid for tid, item in SYNC_TASKS.items() if not item["running"]]
        for tid in completed[:-10]:
            SYNC_TASKS.pop(tid, None)
    return task_id


def sync_task_status(task_id: str, owner: str = "") -> dict[str, object] | None:
    """查询同步任务进度；owner 非空时校验任务归属，非本人任务视为不存在。"""
    with SYNC_TASKS_LOCK:
        task = SYNC_TASKS.get(task_id)
        if task is None:
            return None
        if str(task.get("owner", "")) != owner:
            return None
        return {
            "task_id": task_id,
            "running": bool(task["running"]),
            "logs": list(task["logs"]),
            "result": task["result"],
            "error": task["error"],
        }


def _parse_ms(text: str) -> int | None:
    # 解析力扣耗时文本（"120 ms" / "45"）→ 毫秒整数；格式不匹配返回 None（入库 NULL）。
    match = re.search(r"(\d+(?:\.\d+)?)\s*(ms)?", text, re.I)
    return int(float(match.group(1))) if match else None


def _parse_kb(text: str) -> int | None:
    # 解析力扣内存文本（"125.6 MB" / "38.4 KB" / "1.2 GB"）→ 统一换算成 KB 整数；匹配失败返回 None。
    match = re.search(r"([\d.]+)\s*(KB|MB|GB)?", text, re.I)
    if not match:
        return None
    value = float(match.group(1))
    unit = (match.group(2) or "").upper()
    # 单位换算：没写单位按 KB 计；MB → ×1024，GB → ×1024²，保证入库单位一致。
    if unit == "MB":
        value *= 1024
    elif unit == "GB":
        value *= 1024 * 1024
    return int(value)


class StudyHandler(SimpleHTTPRequestHandler):
    server_version = "Hot100Study/1.0"
    # HTTP/1.1：启用 keep-alive，公网访问省去每请求的 TCP/TLS 握手。
    # 前提：所有响应必须带准确 Content-Length（send_json/静态/头像/导出均已带；
    # 手动 307 跳转补 Content-Length: 0，见 do_GET）。
    protocol_version = "HTTP/1.1"
    # 不注入认证胶囊的页面：登录/注册/管理页自带登录与退出界面。
    AUTH_WIDGET_SKIP_PATHS = {"/pages/login.html", "/pages/register.html", "/pages/admin.html"}
    # 悬浮组件注入的脚本清单（v 参数用于更新缓存）：认证胶囊/反馈/主题切换。
    WIDGET_SCRIPTS = ["/assets/auth-widget.js?v=2", "/assets/feedback-widget.js?v=1", "/assets/theme-toggle.js?v=1"]

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
        normalized = posixpath.normpath(decoded_path)
        if ".." in normalized.split("/"):
            return True
        return normalized.startswith(("/data", "/tools", "/.git", "/.", "/docs", "/MAINTENANCE",
                                      "/QA-REPORT", "/README"))                 or normalized in ("/maintenance.html", "/guide.html.md")                 or normalized.lower().endswith(".md")

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
        parsed = urlparse(self.path)
        decoded_path = unquote(parsed.path)
        if not self._access_gate(decoded_path):
            return
        super().do_HEAD()

    def do_GET(self) -> None:
        # GET 路由总览：安全过滤 → 认证门禁 → 根路径/API 特判 → 浏览埋点 → 兜底静态文件服务。
        parsed = urlparse(self.path)
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
        # /api/chat/messages：公屏聊天增量拉取（?after=<id>，-1 取最近 50 条）。
        if parsed.path == "/api/chat/messages":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            try:
                after = int(params.get("after", "-1"))
            except ValueError:
                after = -1
            try:
                limit = max(1, min(int(params.get("limit", "50")), 100))
            except ValueError:
                limit = 50
            self.send_json({"items": chat_messages_after(after, limit)})
            return
        # /api/profile：自己的昵称与头像状态。
        if parsed.path == "/api/profile":
            self.send_json(get_profile(str(user["username"])))
            return
        # /api/bootstrap：面板打开的一次性拉取（dashboard + daily + settings 合并，
        # 省两个 RTT；dashboard 自带 60 秒缓存）。
        if parsed.path == "/api/bootstrap":
            ai_state = ai_capability(str(user["username"]), str(user["role"]))
            ai_state["quota"] = get_ai_quota(db, str(user["role"]))
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
            capability = ai_capability(str(user["username"]), str(user["role"]))
            capability["quota"] = get_ai_quota(db, str(user["role"]))
            self.send_json({"ai_coach": capability})
            return
        # /api/coach/insights/recent：页面刷新时恢复最近任务，不触发模型调用。
        if parsed.path == "/api/coach/insights/recent":
            try:
                self.send_json(get_recent_ai_tasks(db, str(user["username"]), str(user["role"])))
            except sqlite3.Error:
                self.send_json({"error": "分析记录暂时不可用"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        # /api/coach/tasks/<id>：查询当前用户自己的任务状态和脱敏上下文预览。
        task_match = re.fullmatch(r"/api/coach/tasks/([0-9a-f]{32})", parsed.path)
        if task_match:
            task = get_ai_task(db, task_match.group(1), str(user["role"]))
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
            status = sync_task_status(task_id, owner=str(user["username"]) if user is not None else "")
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
                    tmp_path.unlink(missing_ok=True)
                except Exception as exc:
                    self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                    return
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
        # ---- 前端小部件注入：阅读页/面板 HTML 在发送前插入认证胶囊与反馈按钮 ----
        # 05-可视化 页面会被 iframe 内嵌，均跳过；注入发生在服务层，不改任何生成产物。
        if decoded_path.lower().endswith(".html") and not decoded_path.startswith("/books/hot100/05-可视化/"):
            if self.serve_html_with_widget(decoded_path):
                return
        super().do_GET()

    def serve_html_with_widget(self, decoded_path: str) -> bool:
        """读取 HTML 文件、在 </body> 前注入小部件脚本后发送；文件不存在返回 False 交给默认 404。
        认证胶囊在登录/注册/管理页跳过（它们自带登录界面），反馈按钮全站可见。"""
        try:
            target = (ROOT / decoded_path.lstrip("/")).resolve()
            if not (target.is_file() and str(target).startswith(str(ROOT.resolve()))):
                return False
            body = target.read_bytes()
        except OSError:
            return False
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
                      "/api/admin/users/ai-quota/reset",
                      "/api/admin/users/reset-password",
                      "/api/admin/feedback/resolve", "/api/admin/chat/delete"}
        known_post = public_post | admin_post | {
            "/api/logout", "/api/password", "/api/profile", "/api/chat/send", "/api/complete",
            "/api/content/complete", "/api/mark", "/api/settings", "/api/submit",
            "/api/plan/pin",
            "/api/coach/context",
            "/api/coach/analyze",
            "/api/leetcode/connect", "/api/leetcode/sync", "/api/leetcode/clear",
        }
        cancel_match = re.fullmatch(r"/api/coach/tasks/([0-9a-f]{32})/cancel", path)
        feedback_match = re.fullmatch(r"/api/coach/insights/([0-9a-f]{32})/feedback", path)
        if path not in known_post and cancel_match is None and feedback_match is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        # ---- 认证门禁：公开端点放行；其余需登录；admin_post 需管理员 ----
        user = self.current_user()
        if path not in public_post:
            if user is None:
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
                self.send_json({"error": "需要管理员权限"}, HTTPStatus.FORBIDDEN)
                return
        db = user_db_path(str(user["username"])) if user is not None else DB_PATH
        learning_write_path = path in _ANALYTICS_WRITE_PATHS
        cookie_headers: list[tuple[str, str]] = []
        try:
            # 请求体约束：必须是 JSON 且 1~4096 字节（/api/profile 例外：头像 base64
            # 膨胀 1.33 倍后仍需容纳 150KB 图片，上限放宽到 220KB），空体/超大直接拒绝。
            length = int(self.headers.get("Content-Length", "0"))
            max_len = 262144 if path == "/api/profile" else 4096
            if length < 1 or length > max_len:
                raise ValueError("请求大小不正确")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
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
                result = create_ai_task(db, context, str(user["username"]), str(user["role"]))
                debug_ai_event(
                    "request_prepared",
                    task_id=str(result.get("task_id", "")),
                    analytics_ms=analytics_ms,
                    context_compile_ms=compile_ms,
                    task_create_ms=round((time.perf_counter() - create_started) * 1000, 2),
                    context=context,
                )
            # /api/coach/tasks/<id>/cancel：只允许取消仍在队列中的任务。
            elif cancel_match is not None:
                if not isinstance(payload, dict) or payload:
                    raise ValueError("请求参数不正确")
                result = cancel_ai_task(db, cancel_match.group(1))
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
                for_date = (datetime.now().astimezone().date() + timedelta(days=1)).isoformat()
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
                result = set_user_active(str(payload.get("username", "")), bool(payload.get("active")))
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
            # /api/admin/users/reset-password：管理员重置用户密码（重置后该用户全部会话失效）。
            elif path == "/api/admin/users/reset-password":
                result = reset_user_password(str(payload.get("username", "")), str(payload.get("new_password", "")))
            # /api/admin/chat/delete：管理员删除公屏消息（公屏治理）。
            elif path == "/api/admin/chat/delete":
                result = chat_delete(int(payload.get("id", 0)))
            # /api/admin/feedback/resolve：标记反馈已解决（可附说明）或重新打开。
            elif path == "/api/admin/feedback/resolve":
                result = resolve_feedback(
                    int(payload.get("id", 0)),
                    bool(payload.get("resolved")),
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
                if payload.get("async") in (1, True, "1", "true", "True"):
                    result = {
                        "ok": True,
                        "task_id": start_leetcode_sync_task(
                            get_credentials(db),
                            full,
                            owner=str(user["username"]),
                            db_path=db,
                        ),
                    }
                else:
                    result = {"ok": True, **leetcode_sync(get_credentials(db), db_path=db, full=full)}
            # /api/leetcode/clear：一键清空凭证（等价"退出力扣连接"，不影响已同步记录）。
            else:
                clear_credentials(db)
                lc_status_invalidate(db)
                result = {"cleared": True}
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
        恒为 127.0.0.1，此时改取 CF-Connecting-IP（Cloudflare 边缘强制写入、不可伪造）；
        其余情况用 socket 对端地址，防止伪造请求头绕过限流。"""
        peer = self.client_address[0] if self.client_address else ""
        if peer in ("127.0.0.1", "::1"):
            cf_ip = (self.headers.get("CF-Connecting-IP") or "").strip()
            if cf_ip:
                return cf_ip
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
    # ThreadingHTTPServer 每请求一线程；daemon_threads 保证 Ctrl+C 后线程随主进程一起退出。
    server = ThreadingHTTPServer((args.host, args.port), StudyHandler)
    server.daemon_threads = True
    if args.open:
        # 延迟 0.5 秒再开浏览器：等服务就绪，避免浏览器首请求落空。
        threading.Timer(0.5, lambda: webbrowser.open(address)).start()
    print(f"Interview Forge：{address}")
    print("账户数据库：" + str(AUTH_DB_PATH))
    print("按 Ctrl+C 停止服务。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
