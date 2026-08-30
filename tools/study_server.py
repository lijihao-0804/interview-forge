# ============================================================================
# study_server.py —— Interview Forge后端（纯 Python 标准库 + SQLite 的本地 HTTP 服务）
#
# 职责总述（这个文件做了什么）：
#   1) 静态文件服务：以项目根目录 ROOT 为文档根目录，直接服务网页/题解/题库等静态资源；
#   2) REST API：提供 /api/* JSON 接口（仪表盘、每日计划、书架、导出、力扣同步等）；
#   3) 学习记录：所有学习行为（浏览/完成轮次/提交/标记/设置）持久化到 SQLite 单文件数据库；
#   4) 力扣同步：读取本机保存的 LEETCODE_SESSION，拉取力扣提交历史写回本地库（只读力扣、写本地）。
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
# argparse      命令行参数（--host/--port/--open/--init-only/--quiet）
# json / sqlite3 HTTP 请求体解析、数据库读写（本库核心存储）
# random / re    随机抽题（今日推荐/组卷）、文本匹配（题解锚点、力扣耗时解析）
# http.server    标准库 HTTP 服务器（ThreadingHTTPServer 每请求一线程）
# urllib.parse   URL 解析/中文路径解码/查询参数解析
# build_hot100   同目录下的题库构建模块：题目清单（PROBLEM_BY_ID）、力扣 slug 映射、文件名规则
import argparse
import json
import random
import re
import sqlite3
import tempfile
import threading
import webbrowser
from contextlib import closing
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from build_hot100 import LEETCODE_SLUGS, PROBLEM_BY_ID, problem_filename


# ---- 路径常量：锁定"项目根 / 数据目录 / 数据库文件"三个位置 ----
# ROOT    取本文件所在目录的上一级（tools/ 的 parents[1] 即学习站根目录），静态文件与题库都以此为准；
# DATA_DIR  数据目录（data/），放置 SQLite 文件；
# DB_PATH   全部学习记录的唯一落盘位置（data/hot100-study.db）。
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "hot100-study.db"


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
CREATE TABLE IF NOT EXISTS credentials (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


# ---- 模块级进程内状态 ----
# _SCHEMA_READY    建表完成标记：首次 connect 时执行一次 DDL，之后跳过（懒初始化）；
# QUIET            请求日志开关（--quiet 或脚本内置 True 后不再打印每条请求）；
# _SCHEMA_LOCK     建表互斥锁：多线程并发首次连接时，保证只有一个线程执行建表；
# _MANIFEST_CACHE  书架 manifest.json 的内存缓存 (mtime, 内容)：文件没改动就直接复用。
_SCHEMA_READY = False
QUIET = False
_SCHEMA_LOCK = threading.Lock()
_MANIFEST_CACHE: tuple[float, dict[str, object]] | None = None


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """打开数据库连接：确保目录存在、设置行工厂、开启外键；首次连接时加锁执行建库 DDL。"""
    global _SCHEMA_READY
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    # Row 工厂：查询结果支持按列名取值（row["problem_id"]），后面代码大量依赖它。
    connection.row_factory = sqlite3.Row
    # 开启外键约束（当前表结构暂无级联，保持规范）；timeout=10 秒缓解多线程并发写锁等待。
    connection.execute("PRAGMA foreign_keys = ON")
    # 双检锁（先查标记、锁内再查标记）：多线程并发首次连接也只会执行一次建表脚本。
    if not _SCHEMA_READY:
        with _SCHEMA_LOCK:
            if not _SCHEMA_READY:
                connection.executescript(SCHEMA)
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
                _SCHEMA_READY = True
    return connection


def now_parts() -> tuple[str, str]:
    """返回 (当前时间 ISO 字符串, 今天日期 YYYY-MM-DD)，是所有写记录统一的时间入口。"""
    now = datetime.now().astimezone()
    return now.isoformat(timespec="seconds"), now.date().isoformat()


def record_view(problem_id: int, db_path: Path = DB_PATH) -> None:
    """记录一次题目浏览（view 事件）：60 秒内对同一题去重，防止翻页/刷接口产生垃圾记录。"""
    if problem_id not in PROBLEM_BY_ID:
        # 未知题号直接忽略 —— 浏览埋点属"尽力而为"，不因脏请求而报错。
        return
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
                return
        # 通过 60 秒窗口：落一条 view 记录（studied_at / study_date 由 now_parts 统一生成）。
        connection.execute(
            "INSERT INTO study_events(problem_id, action, studied_at, study_date) VALUES (?, 'view', ?, ?)",
            (problem_id, studied_at, study_date),
        )
        connection.commit()


def complete_round(problem_id: int, db_path: Path = DB_PATH) -> dict[str, object]:
    """记录"完成一轮"：轮次自增写入 study_events，并联动写入书架 hot100 模块的进度。"""
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


def dashboard_data(db_path: Path = DB_PATH) -> dict[str, object]:
    """聚合仪表盘全部数据：今日概览、每题进度、近 14 天、最近 20 条事件、365 天热力图、标记与提交统计。

    6 个 SQL 分别回答：每题的累计进度 / 顶部汇总数字 / 近 14 天图表 / 最近活动列表 /
    三类事件（题目、章节、提交）的按日统计 —— 合并成活跃日历并推导连续学习天数。
    """
    today = datetime.now().astimezone().date().isoformat()
    with closing(connect(db_path)) as connection:
        # SQL① 每题进度：聚合轮次数、最近浏览/完成/活动时间（逐题进度卡的数据源）。
        problem_rows = connection.execute(
            """SELECT problem_id,
                      SUM(CASE WHEN action = 'complete' THEN 1 ELSE 0 END) AS rounds,
                      MAX(CASE WHEN action = 'view' THEN studied_at END) AS last_viewed_at,
                      MAX(CASE WHEN action = 'complete' THEN studied_at END) AS last_completed_at,
                      MAX(studied_at) AS last_activity_at
               FROM study_events GROUP BY problem_id"""
        ).fetchall()
        # SQL② 顶部汇总：今日浏览题数 / 今日完成轮次 / 累计完成题数 / 总轮次 / 活跃天数。
        summary = connection.execute(
            """SELECT
                 COUNT(DISTINCT CASE WHEN study_date = ? AND action = 'view' THEN problem_id END) AS today_viewed,
                 SUM(CASE WHEN study_date = ? AND action = 'complete' THEN 1 ELSE 0 END) AS today_rounds,
                 COUNT(DISTINCT CASE WHEN action = 'complete' THEN problem_id END) AS completed_problems,
                 SUM(CASE WHEN action = 'complete' THEN 1 ELSE 0 END) AS total_rounds,
                 COUNT(DISTINCT study_date) AS active_days
               FROM study_events""",
            (today, today),
        ).fetchone()
        # SQL③ 近 14 天每日（浏览题数、完成轮次），按日期倒序取最近 14 行。
        days = connection.execute(
            """SELECT study_date,
                      COUNT(DISTINCT CASE WHEN action = 'view' THEN problem_id END) AS viewed,
                      SUM(CASE WHEN action = 'complete' THEN 1 ELSE 0 END) AS rounds
               FROM study_events GROUP BY study_date ORDER BY study_date DESC LIMIT 14"""
        ).fetchall()
        # SQL④ 最近 20 条事件（题号/动作/时间/轮次），渲染"最近活动"列表。
        recent = connection.execute(
            """SELECT problem_id, action, studied_at, round_no
               FROM study_events ORDER BY id DESC LIMIT 20"""
        ).fetchall()
        # SQL⑤⑥⑦ 三类事件各自按天统计（题目/章节/提交），下面合并成一张活跃日历。
        problem_days = connection.execute(
            """SELECT study_date,
                      COUNT(DISTINCT CASE WHEN action = 'view' THEN problem_id END) AS viewed,
                      SUM(CASE WHEN action = 'complete' THEN 1 ELSE 0 END) AS rounds
               FROM study_events GROUP BY study_date"""
        ).fetchall()
        content_days = connection.execute(
            """SELECT study_date,
                      COUNT(DISTINCT CASE WHEN action = 'view' THEN content_id END) AS viewed,
                      SUM(CASE WHEN action = 'complete' THEN 1 ELSE 0 END) AS rounds
               FROM content_events GROUP BY study_date"""
        ).fetchall()
        submission_days = connection.execute(
            """SELECT substr(submitted_at, 1, 10) AS study_date, COUNT(1) AS submits
               FROM submissions GROUP BY study_date"""
        ).fetchall()
        # 并集：出现过任意一类活动的日期集合，用于下面计算连续学习天数。
        active_dates = (
            {str(row["study_date"]) for row in problem_days}
            | {str(row["study_date"]) for row in content_days}
            | {str(row["study_date"]) for row in submission_days}
        )
    # 把三类按日计数合并进 day_stats：一个日期 → {viewed, rounds, submits} 三元组。
    day_stats: dict[str, dict[str, int]] = {}
    for row in problem_days:
        day_stats.setdefault(str(row["study_date"]), {"viewed": 0, "rounds": 0, "submits": 0})
        day_stats[str(row["study_date"])]["viewed"] += int(row["viewed"] or 0)
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
        # 每日目标轮次：读 settings 里的 daily_goal_rounds，夹逼到 1~50，读不到/非法时兜底为 3。
        daily_goal = max(1, min(50, int(get_settings(db_path).get("daily_goal_rounds", "3") or "3")))
    except (TypeError, ValueError):
        daily_goal = 3
    summary = {key: int(summary[key] or 0) for key in summary.keys()}
    summary["streak"] = streak
    summary["daily_goal"] = daily_goal
    # 逐题附加 next_due（按最近完成时间 + 轮次推算），前端据此显示"下次复习"。
    problems_payload: dict[str, dict[str, object]] = {}
    for row in problem_rows:
        item = dict(row)
        rounds = int(row["rounds"] or 0)
        if rounds > 0 and row["last_completed_at"]:
            item["next_due"] = due_after(str(row["last_completed_at"]), rounds)
        problems_payload[str(row["problem_id"])] = item
    return {
        "today": today,
        "summary": summary,
        "problems": problems_payload,
        "days": [dict(row) for row in days],
        "recent": [dict(row) for row in recent],
        "activity": activity,
        "marks": problem_marks(db_path),
        "submissions": submission_summary(db_path),
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


def record_content_view(module_id: str, content_id: str, db_path: Path = DB_PATH) -> None:
    """书架章节浏览事件：与题目 record_view 完全同构（含 60 秒去重），写进 content_events。"""
    if not valid_content(module_id, content_id):
        return
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
                return
        connection.execute(
            """INSERT INTO content_events(module_id, content_id, action, studied_at, study_date)
               VALUES (?, ?, 'view', ?, ?)""",
            (module_id, content_id, studied_at, study_date),
        )
        connection.commit()


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
    # next_due：按章节专用间隔表（REVIEW_INTERVALS_CONTENT）推算的到期日，前端展示"下次复习"。
    return {
        "module_id": module_id,
        "content_id": content_id,
        "round_no": round_no,
        "studied_at": studied_at,
        "next_due": due_after(studied_at, round_no),
    }


def library_data(db_path: Path = DB_PATH) -> dict[str, object]:
    """书架数据：每个模块的章节总数/已完成数（rounds>0 即算开始学习）+ 每章节的轮次与最近活动。"""
    manifest = load_library_manifest()
    with closing(connect(db_path)) as connection:
        # 每章节聚合：完成轮次数 + 最近活动时间（内容维度的进度数据）。
        rows = connection.execute(
            """SELECT content_id,
                      SUM(CASE WHEN action = 'complete' THEN 1 ELSE 0 END) AS rounds,
                      MAX(studied_at) AS last_activity_at
               FROM content_events GROUP BY content_id"""
        ).fetchall()
    contents = {str(row["content_id"]): dict(row) for row in rows}
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
    with closing(connect(db_path)) as connection:
        # 题目侧：按题聚合完成轮次；到期日 = 最近完成时间 + 轮次对应间隔，<= 今天才算"待复习"。
        problem_rows = connection.execute(
            """SELECT problem_id, COUNT(*) AS rounds, MAX(studied_at) AS last_completed_at
               FROM study_events WHERE action = 'complete'
               GROUP BY problem_id HAVING COUNT(*) > 0"""
        ).fetchall()
        # 章节侧：传 module_id 时只统计该模块（书架模块页用），否则统计全部模块。
        if module_id:
            content_rows = connection.execute(
                """SELECT content_id, COUNT(*) AS rounds, MAX(studied_at) AS last_completed_at
                   FROM content_events WHERE action = 'complete' AND module_id = ?
                   GROUP BY content_id HAVING COUNT(*) > 0""",
                (module_id,),
            ).fetchall()
        else:
            content_rows = connection.execute(
                """SELECT content_id, COUNT(*) AS rounds, MAX(studied_at) AS last_completed_at
                   FROM content_events WHERE action = 'complete'
                   GROUP BY content_id HAVING COUNT(*) > 0"""
            ).fetchall()

    # 组装题目待复习列表：到期日还没到（> 今天）的跳过，其余带上题名/分类/难度/题解链接。
    problems: list[dict[str, object]] = []
    if not module_id:
        for row in problem_rows:
            problem = PROBLEM_BY_ID.get(int(row["problem_id"]))
            rounds = int(row["rounds"])
            due = due_after(row["last_completed_at"], rounds)
            if due > today:
                continue
            problems.append({
                "id": int(row["problem_id"]),
                "title": problem["title"] if problem else f"题号 {row['problem_id']}",
                "category": problem["category"] if problem else "",
                "difficulty": problem["difficulty"] if problem else "",
                "rounds": rounds,
                "last_completed_at": row["last_completed_at"],
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
        "contents": len(contents),
        "overdue_contents": content_overdue,
        "modules": modules,
    }
    return {"today": today, "summary": summary, "problems": problems, "contents": contents}


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
    with closing(connect(db_path)) as connection:
        # 每题聚合：完成轮次 + 最近活动时间，用于"最久未看"的推荐排序。
        rows = connection.execute(
            """SELECT problem_id,
                      SUM(CASE WHEN action = 'complete' THEN 1 ELSE 0 END) AS rounds,
                      MAX(studied_at) AS last_activity_at
               FROM study_events GROUP BY problem_id"""
        ).fetchall()
    info = {int(row["problem_id"]): dict(row) for row in rows}
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
    row = info.get(int(chosen["id"]))
    return {
        "id": int(chosen["id"]),
        "title": chosen["title"],
        "category": chosen["category"],
        "difficulty": chosen["difficulty"],
        "method": chosen["method"],
        "rounds": int(row["rounds"]) if row else 0,
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
    """今日计划：待复习 + 薄弱全部纳入，新题补足到 count 道。

    randomize=True 时新题部分随机抽取（“换一组”用）；默认按“最久未看”排序。
    """
    today = datetime.now().astimezone().date().isoformat()
    # 数据源一：今日待复习（到期日 <= 今天）的题目，无条件全部纳入计划。
    due_by_id = {int(item["id"]): item for item in daily_data(db_path)["problems"]}
    marks = problem_marks(db_path)
    # 数据源二：被标记为 weak 的题，即使还没到期也强制放进今日计划（查漏补缺）。
    weak_ids = {int(k) for k, value in marks.items() if value == "weak" and int(k) in PROBLEM_BY_ID}
    with closing(connect(db_path)) as connection:
        # 每题聚合：用于判断"未完成过"（rounds==0 => 新题）与"最久未学"排序。
        rows = connection.execute(
            """SELECT problem_id,
                      SUM(CASE WHEN action='complete' THEN 1 ELSE 0 END) AS rounds,
                      MAX(studied_at) AS last_activity_at
               FROM study_events GROUP BY problem_id"""
        ).fetchall()
    info = {int(row["problem_id"]): dict(row) for row in rows}

    def entry(pid: int, reason: str) -> dict[str, object]:
        p = PROBLEM_BY_ID[pid]
        return {
            "id": pid,
            "title": p["title"],
            "category": p["category"],
            "difficulty": p["difficulty"],
            "method": p["method"],
            "note": problem_note(p),
            "reason": reason,
        }

    # 组装优先级：待复习 → 薄弱 → 新题；seen 集合保证同一题不会重复出现。
    items: list[dict[str, object]] = []
    seen: set[int] = set()
    for pid in due_by_id:
        items.append(entry(pid, "待复习"))
        seen.add(pid)
    for pid in sorted(weak_ids - seen):
        items.append(entry(pid, "薄弱"))
        seen.add(pid)
    count = max(1, min(count, 100))
    # 新题候选：从未完成过（rounds==0）且不在上面集合里的题。
    new_candidates = [
        pid for pid in PROBLEM_BY_ID
        if pid not in seen and int(info.get(pid, {}).get("rounds") or 0) == 0
    ]
    # randomize：洗牌（"换一组"）；默认按最近活动时间升序，最久未学的优先补齐。
    if randomize:
        random.shuffle(new_candidates)
    else:
        new_candidates.sort(key=lambda pid: str(info.get(pid, {}).get("last_activity_at") or ""))
    for pid in new_candidates[: max(0, count - len(items))]:
        items.append(entry(pid, "新题"))
        seen.add(pid)
    return {"today": today, "count": len(items), "items": items}


def weaklist(db_path: Path = DB_PATH) -> dict[str, object]:
    """薄弱题清单：含专题、轮次、最近复习、标记时间，按标记时间排序。"""
    with closing(connect(db_path)) as connection:
        # 薄弱标记列表按标记时间排序（最早标记的最先展示）。
        marks = [dict(row) for row in connection.execute(
            "SELECT target_id, updated_at FROM marks WHERE target_type='problem' AND mark='weak' ORDER BY updated_at"
        )]
        # 每题完成轮次（列表里显示"已经复习了几轮"）。
        complete_rows = connection.execute(
            """SELECT problem_id, COUNT(*) AS rounds, MAX(studied_at) AS last_completed_at
               FROM study_events WHERE action='complete' GROUP BY problem_id"""
        ).fetchall()
        # 每题首次浏览时间（展示"什么时候开始学这道题"）。
        view_rows = connection.execute(
            "SELECT problem_id, MIN(studied_at) AS first_view FROM study_events WHERE action='view' GROUP BY problem_id"
        ).fetchall()
    info = {int(row["problem_id"]): row for row in complete_rows}
    first_view = {int(row["problem_id"]): str(row["first_view"]) for row in view_rows}
    items: list[dict[str, object]] = []
    for mark in marks:
        pid = int(mark["target_id"])
        p = PROBLEM_BY_ID.get(pid)
        if not p:
            continue
        row = info.get(pid)
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
            "marked_at": mark["updated_at"],
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
        payload = {"problems": problems, "contents": contents, "marks": marks, "settings": settings}
        return "application/json; charset=utf-8", "hot100-records.json", json.dumps(payload, ensure_ascii=False, indent=2)
    # weekly：本周（本周一 00:00 起）统计生成 Markdown 周报：轮次/活跃天数/连击/薄弱清单。
    if kind == "weekly":
        now = datetime.now().astimezone()
        monday = (now - timedelta(days=now.weekday())).date()
        monday_iso = monday.isoformat()
        today_iso = now.date().isoformat()
        with closing(connect(db_path)) as connection:
            problem_rounds = int(connection.execute(
                "SELECT COUNT(*) AS n FROM study_events WHERE action='complete' AND study_date >= ?",
                (monday_iso,),
            ).fetchone()["n"] or 0)
            content_rounds = int(connection.execute(
                "SELECT COUNT(*) AS n FROM content_events WHERE action='complete' AND study_date >= ?",
                (monday_iso,),
            ).fetchone()["n"] or 0)
            active_days = int(connection.execute(
                "SELECT COUNT(DISTINCT study_date) AS n FROM study_events WHERE study_date >= ?",
                (monday_iso,),
            ).fetchone()["n"] or 0)
            active_dates_all = {str(r["study_date"]) for r in connection.execute(
                "SELECT DISTINCT study_date FROM study_events UNION SELECT DISTINCT study_date FROM content_events"
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
            "- 保持连击：每天至少完成一轮。",
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
    """记录一次力扣提交结果（ac/wa）。problem_id/status/source 白名单校验。"""
    if problem_id not in PROBLEM_BY_ID:
        raise ValueError("未知题号")
    if status not in ("ac", "wa"):
        raise ValueError("未知提交状态")
    if source not in VALID_SUBMIT_SOURCES:
        source = "manual"
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
    """全站提交统计：今日/累计 AC 与提交数、通过率、每题是否 AC 过。"""
    today = datetime.now().astimezone().date().isoformat()
    with closing(connect(db_path)) as connection:
        # 单条 SQL 聚合四项：今日 AC / 今日提交 / 累计 AC 题数 / 累计提交数（substr 切日期前缀与今天比对）。
        row = connection.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN status = 'ac' AND substr(submitted_at, 1, 10) = ? THEN 1 ELSE 0 END), 0) AS today_ac,
                 COALESCE(SUM(CASE WHEN substr(submitted_at, 1, 10) = ? THEN 1 ELSE 0 END), 0) AS today_submits,
                 COALESCE(COUNT(DISTINCT CASE WHEN status = 'ac' THEN problem_id END), 0) AS total_ac,
                 COALESCE(SUM(1), 0) AS total_submits
               FROM submissions""",
            (today, today),
        ).fetchone()
        problem_rows = connection.execute(
            "SELECT problem_id, MAX(CASE WHEN status = 'ac' THEN 1 ELSE 0 END) AS ever_ac FROM submissions GROUP BY problem_id"
        ).fetchall()
    summary = {key: int(row[key] or 0) for key in row.keys()}
    # 通过率 = 累计 AC 题数 / 累计提交数；一条提交都没有 → None（前端显示"暂无数据"而非除零）。
    summary["pass_rate"] = round(summary["total_ac"] / summary["total_submits"], 3) if summary["total_submits"] else None
    return {"summary": summary, "ever_ac": {int(r["problem_id"]): bool(r["ever_ac"]) for r in problem_rows}}


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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://leetcode.cn/problemset/",
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


def leetcode_status(credentials: dict[str, str], timeout: int = 20) -> dict[str, object]:
    """测试力扣连接：调公开题目列表接口，校验登录态字段。"""
    import urllib.request
    import urllib.error

    if not credentials.get("leetcode_session"):
        return {"connected": False, "reason": "no-session", "message": "尚未保存 LEETCODE_SESSION"}
    # 探测原理：公开题目列表接口在登录态下会带 user_name —— 用户名非空即视为会话生效
    # （num_solved 仅作附加展示）；401/403 → 会话过期，其余 HTTP/网络/匿名数据分别归类提示。
    req = urllib.request.Request("https://leetcode.cn/api/problems/all/", headers=_leetcode_headers(credentials))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
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


def leetcode_sync(credentials: dict[str, str], db_path: Path = DB_PATH, limit: int = 100, full: bool = False) -> dict[str, object]:
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
        req = urllib.request.Request("https://leetcode.cn/api/problems/all/", headers=headers)
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ValueError(f"同步失败：力扣返回 HTTP {exc.code}（会话可能过期）")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"同步失败：{type(exc).__name__}")

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
    while True:
        page += 1
        if page > max_pages:
            fetch_errors.append(f"已达分页上限（{max_pages} 页），如有更多历史请再次全量同步")
            break
        try:
            req = urllib.request.Request(
                f"https://leetcode.cn/api/submissions/?offset={offset}&limit={min(int(limit), 100)}",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            fetch_errors.append(f"第 {page} 页拉取失败：{type(exc).__name__}: {exc}")
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
        if not payload.get("has_next"):
            break
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
    return results


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        # 本地学习站始终返回最新内容，静态页面/脚本/样式一律禁止缓存，避免浏览器拿旧版。
        if self.path.split("?", 1)[0].lower().endswith((".html", ".js", ".css", ".webmanifest", ".json")):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # CORS：仅放行本机（浏览器扩展/书签脚本跨源到 localhost 提交记录）。
        origin = self.headers.get("Origin", "")
        if origin in ("http://localhost", "http://127.0.0.1", "http://localhost:8765", "http://127.0.0.1:8765"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CSRFToken")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

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

    def do_GET(self) -> None:
        # GET 路由总览：安全过滤 → 根路径/API 特判 → 浏览埋点 → 兜底静态文件服务。
        parsed = urlparse(self.path)
        decoded_path = unquote(parsed.path)
        # 敏感目录一律 403：data/（数据库与凭证）、tools/（服务端脚本）、.git/（版本库）。
        if decoded_path.startswith(("/data", "/tools", "/.git")):
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        # 根路径 302 重定向到书架首页 library/index.html："打开学习站"直达内容而非目录列表。
        if parsed.path == "/":
            self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
            self.send_header("Location", "/library/index.html")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        # /api/dashboard：仪表盘聚合 —— 今日概览/每题进度/近 14 天/最近活动/365 天热力图/标记与提交统计。
        if parsed.path == "/api/dashboard":
            self.send_json(dashboard_data())
            return
        # /api/health：健康检查 —— 返回 ok 与库文件名，供前端探测服务是否存活。
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "database": DB_PATH.name})
            return
        # /api/library：书架进度 —— 各模块 total/completed 进度条 + 每章节轮次与最近活动。
        if parsed.path == "/api/library":
            self.send_json(library_data())
            return
        # /api/daily：今日待复习 —— 到期日 <= 今天 的题目与章节；?module= 指定只筛某模块的章节。
        if parsed.path == "/api/daily":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            self.send_json(daily_data(module_id=params.get("module", "")))
            return
        # /api/settings：读全部设置 KV（前端初始化时填充每日目标等）。
        if parsed.path == "/api/settings":
            self.send_json(get_settings())
            return
        # /api/pick：今日推荐 —— 未完成优先、按最久未碰排序；?random=1 随机抽（"换一题"）。
        if parsed.path == "/api/pick":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            try:
                self.send_json(pick_problem(
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
                count = 10
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
                count = 3
            self.send_json(today_plan(count=count, randomize=params.get("random", "") == "1"))
            return
        # /api/weaklist：薄弱题清单 —— 带轮次/首次浏览/标记时间，按标记时间排序。
        if parsed.path == "/api/weaklist":
            self.send_json(weaklist())
            return
        # /api/submissions：单题提交记录 —— 按 id 倒序最近 limit 条；problem_id 缺失/非法 → 400。
        if parsed.path == "/api/submissions":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            try:
                problem_id = int(params.get("problem_id", ""))
            except ValueError:
                self.send_json({"error": "缺少合法 problem_id"}, HTTPStatus.BAD_REQUEST)
                return
            self.send_json({"problem_id": problem_id, "items": submissions_for_problem(problem_id)})
            return
        # /api/leetcode/status：力扣连接状态 —— 凭证是否已保存 + 实测登录态是否生效，合并成一个响应。
        if parsed.path == "/api/leetcode/status":
            self.send_json({"credentials_saved": bool(get_credentials().get("leetcode_session")), **leetcode_status(get_credentials())})
            return
        # /api/export：数据导出 —— kind=anki/weak/records/weekly 走 export_data；kind=db 走整库快照。
        if parsed.path == "/api/export":
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            if params.get("kind") == "db":
                # db 备份：sqlite3 backup API 在线快照到 data/ 下临时文件（对正在写的库也安全），发送后即删。
                try:
                    with tempfile.NamedTemporaryFile(suffix=".db", delete=False, dir=str(DATA_DIR)) as tmp:
                        tmp_path = Path(tmp.name)
                    source = sqlite3.connect(DB_PATH)
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
                content_type, filename, data = export_data(params.get("kind", ""))
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
                    record_view(int(filename[:4]))
            except (ValueError, OSError, sqlite3.Error):
                pass
        # 书架章节埋点：manifest routes 表映射 library/* 路径 → content_id 记章节浏览；
        # 其余路径落到 super().do_GET() 走静态文件服务。
        route = load_library_manifest().get("routes", {}).get(decoded_path)
        if route:
            try:
                record_content_view(str(route["module_id"]), str(route["content_id"]))
            except (ValueError, OSError, sqlite3.Error):
                pass
        super().do_GET()

    def do_POST(self) -> None:
        # POST 路由白名单：只放行这 8 个 /api/* 动作，未知路径直接 404（不会误入静态文件服务）。
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/complete", "/api/content/complete", "/api/mark", "/api/settings", "/api/submit", "/api/leetcode/connect", "/api/leetcode/sync", "/api/leetcode/clear"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            # 请求体约束：必须是 JSON 且 1~4096 字节，空体/超大直接拒绝（防滥用与内存占用）。
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 4096:
                raise ValueError("请求大小不正确")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            # /api/complete：题目完成一轮 —— 轮次自增落库 + 联动书架进度 + 推算下次到期日。
            if parsed.path == "/api/complete":
                result = complete_round(int(payload["problem_id"]))
            # /api/content/complete：书架章节完成一轮（独立的事件表与轮次序列）。
            elif parsed.path == "/api/content/complete":
                result = complete_content(str(payload["module_id"]), str(payload["content_id"]))
            # /api/mark：设置/清除标记 —— mastered/reviewing/weak，'' 表示删除标记。
            elif parsed.path == "/api/mark":
                result = set_mark(str(payload["target_type"]), str(payload["target_id"]), str(payload.get("mark", "")))
            # /api/submit：记录一次力扣提交结果（ac/wa + 语言/耗时/内存，来自手动/书签/扩展）。
            elif parsed.path == "/api/submit":
                result = record_submission(
                    problem_id=int(payload["problem_id"]),
                    status=str(payload["status"]),
                    lang=str(payload.get("lang", "")),
                    runtime_ms=payload.get("runtime_ms"),
                    memory_kb=payload.get("memory_kb"),
                    source=str(payload.get("source", "manual")),
                )
            # /api/leetcode/connect：保存力扣凭证（session/csrf）并立刻实测连接状态后返回。
            elif parsed.path == "/api/leetcode/connect":
                set_credentials({
                    "leetcode_session": str(payload.get("leetcode_session", "")),
                    "leetcode_csrf": str(payload.get("leetcode_csrf", "")),
                })
                result = {"saved": True, **leetcode_status(get_credentials())}
            # /api/leetcode/sync：拉取力扣提交历史入库 —— full=1 全量翻页，否则增量最近 100 条。
            elif parsed.path == "/api/leetcode/sync":
                result = {"ok": True, **leetcode_sync(get_credentials(), full=str(payload.get("full", "0")) in ("1", "true", "True"))}
            # /api/leetcode/clear：一键清空凭证（等价"退出力扣连接"，不影响已同步记录）。
            else:
                clear_credentials()
                result = {"cleared": True}
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            # 参数缺失/类型错/校验失败/JSON 非法 → 400（请求本身有问题，业务层抛 ValueError）。
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except sqlite3.Error:
            # 数据库层故障 → 500（请求没问题但写入失败）。
            self.send_json({"error": "数据库写入失败"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        # POST 创建/更新资源成功统一回 201 Created；send_json 内部附加 CORS 头。
        self.send_json(result, HTTPStatus.CREATED)

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
    args = parser.parse_args()
    QUIET = args.quiet
    # 首次连接即触发建表（幂等 DDL）；--init-only 到此为止 = 只初始化数据库。
    with closing(connect()):
        pass
    if args.init_only:
        print(f"Database ready: {DB_PATH}")
        return
    address = f"http://{args.host}:{args.port}/"
    # ThreadingHTTPServer 每请求一线程；daemon_threads 保证 Ctrl+C 后线程随主进程一起退出。
    server = ThreadingHTTPServer((args.host, args.port), StudyHandler)
    server.daemon_threads = True
    if args.open:
        # 延迟 0.5 秒再开浏览器：等服务就绪，避免浏览器首请求落空。
        threading.Timer(0.5, lambda: webbrowser.open(address)).start()
    print(f"Interview Forge：{address}")
    print("学习记录数据库：" + str(DB_PATH))
    print("按 Ctrl+C 停止服务。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
