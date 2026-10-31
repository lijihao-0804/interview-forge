"""年度报告数据组装：把分散在各表里的信息汇总成一份可直接渲染的报告数据。

设计原则：
- 只读，不写库；所有统计都基于现有表实时聚合
- 跨用户库汇总（全站视角），体育馆数据来自独立的 gym.db
- 缺失数据返回 0 / 空数组，前端不必做大量兜底
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date as date_cls
from datetime import datetime, timedelta
from pathlib import Path

from interview_forge.core.runtime import server_runtime

DB_PATH = server_runtime.DB_PATH


def _db_paths(db_paths: list[Path] | None) -> list[Path]:
    if db_paths is not None:
        return [Path(p) for p in db_paths]
    users_dir = DB_PATH.parent / "users"
    paths = sorted(users_dir.glob("*/hot100-study.db")) if users_dir.is_dir() else []
    if DB_PATH.exists():
        paths = [DB_PATH, *paths]
    return paths


def _connect(path: Path) -> sqlite3.Connection | None:
    try:
        conn = server_runtime.connect(path)
        return conn
    except Exception:  # noqa: BLE001
        return None


def _first_of(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> str | None:
    try:
        row = conn.execute(sql, args).fetchone()
        return str(row[0]) if row and row[0] else None
    except sqlite3.Error:
        return None


def _persona(stats: dict) -> list[dict]:
    """根据行为数据推导人格标签（规则简单可解释，避免黑箱）。"""
    tags: list[dict] = []

    hours = stats["hour_histogram"]
    if hours:
        night = sum(n for h, n in hours.items() if h >= 22 or h < 3)
        morning = sum(n for h, n in hours.items() if 5 <= h < 9)
        total = sum(hours.values()) or 1
        if night / total >= 0.35:
            tags.append({"key": "night_owl", "label": "夜猫子", "detail": "深夜是你的主场"})
        elif morning / total >= 0.35:
            tags.append({"key": "early_bird", "label": "早鸟", "detail": "天亮就开始学"})

    modules = stats["module_distribution"]
    if modules:
        total_events = sum(modules.values()) or 1
        top_share = next(iter(modules.values())) / total_events
        if top_share >= 0.4:
            tags.append({"key": "focused", "label": "专注型", "detail": "把力气用在一个方向上"})
        elif len(modules) >= 12:
            tags.append({"key": "explorer", "label": "广撒网", "detail": "什么都想学一点"})

    if stats["total_reviews"] >= 100:
        tags.append({"key": "reviewer", "label": "复习控", "detail": "该复习的一次没落下"})
    if stats["total_seconds"] >= 3600 * 20:
        tags.append({"key": "marathon", "label": "长跑选手", "detail": "累计投入超过 20 小时"})
    if stats["total_submissions"] >= 300:
        tags.append({"key": "grinder", "label": "刷题机器", "detail": "提交次数 300+"})
    if stats["favorites"] >= 20:
        tags.append({"key": "collector", "label": "收藏家", "detail": "攒了一堆好东西"})
    if stats["gym"]["total"] >= 10:
        tags.append({"key": "athlete", "label": "自律运动派", "detail": "学习和锻炼都没落下"})
    return tags


def build_annual_report(year: str | None = None, db_paths: list[Path] | None = None) -> dict:
    """组装年度报告所需的全部数据。"""
    year = str(year or datetime.now().year)
    prefix = f"{year}-%"
    paths = _db_paths(db_paths)

    daily: dict[str, int] = defaultdict(int)
    hours: Counter[int] = Counter()
    modules: Counter[str] = Counter()
    keywords: Counter[str] = Counter()
    totals = {"seconds": 0, "problems": 0, "contents": 0, "submissions": 0,
              "reviews": 0, "favorites": 0, "mock_exams": 0}
    subs_ac = 0
    subs_fastest: int | None = None
    langs: Counter[str] = Counter()
    stability: list[float] = []
    difficulty: list[float] = []
    firsts: dict[str, str | None] = {
        "first_view": None, "first_ac": None, "first_favorite": None,
        "first_review": None, "first_gym": None,
    }
    latest_activity: dict | None = None

    for path in paths:
        conn = _connect(path)
        if conn is None:
            continue
        try:
            # 每日活跃（题目 + 章节 + 时长 三个来源取并集）
            for table in ("study_events", "content_events", "study_duration"):
                try:
                    for row in conn.execute(
                            f"SELECT DISTINCT study_date FROM {table} WHERE study_date LIKE ?", (prefix,)):
                        daily[str(row[0])] += 1
                except sqlite3.Error:
                    pass

            # 学习时段分布
            try:
                for row in conn.execute(
                        "SELECT substr(studied_at, 12, 2) AS h, COUNT(*) AS n FROM study_events "
                        "WHERE studied_at LIKE ? GROUP BY h", (prefix,)):
                    if row[0] and str(row[0]).isdigit():
                        hours[int(row[0])] += int(row[1])
            except sqlite3.Error:
                pass

            # 模块分布
            try:
                for row in conn.execute(
                        "SELECT module_id, COUNT(*) AS n FROM content_events "
                        "WHERE study_date LIKE ? GROUP BY module_id", (prefix,)):
                    if row[0]:
                        modules[str(row[0])] += int(row[1])
            except sqlite3.Error:
                pass

            # 搜索高频词
            try:
                for row in conn.execute(
                        "SELECT keyword, COUNT(*) AS n FROM search_events "
                        "WHERE search_date LIKE ? GROUP BY keyword", (prefix,)):
                    keywords[str(row[0])] += int(row[1])
            except sqlite3.Error:
                pass

            def _sum(sql: str) -> int:
                try:
                    return int(conn.execute(sql, (prefix,)).fetchone()[0] or 0)
                except sqlite3.Error:
                    return 0

            totals["seconds"] += _sum("SELECT COALESCE(SUM(seconds),0) FROM study_duration WHERE study_date LIKE ?")
            totals["problems"] += _sum("SELECT COUNT(DISTINCT problem_id) FROM study_events WHERE study_date LIKE ?")
            totals["contents"] += _sum("SELECT COUNT(DISTINCT content_id) FROM content_events WHERE study_date LIKE ?")
            totals["submissions"] += _sum(
                "SELECT COUNT(*) FROM submissions WHERE date(submitted_at,'+8 hours') LIKE ?")
            totals["reviews"] += _sum(
                "SELECT COUNT(*) FROM review_logs WHERE date(reviewed_at,'+8 hours') LIKE ?")
            totals["favorites"] += _sum("SELECT COUNT(*) FROM favorites WHERE created_at LIKE ?")
            totals["mock_exams"] += _sum("SELECT COUNT(*) FROM mock_exam_records WHERE exam_date LIKE ?")

            # 提交战绩：AC 数、最快用时、语言分布
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS total, "
                    "SUM(CASE WHEN status='ac' THEN 1 ELSE 0 END) AS ac, "
                    "MIN(CASE WHEN status='ac' THEN runtime_ms END) AS fastest "
                    "FROM submissions WHERE submitted_at LIKE ?", (prefix,)).fetchone()
                if row:
                    subs_ac += int(row["ac"] or 0)
                    if row["fastest"] is not None:
                        fastest = int(row["fastest"])
                        if subs_fastest is None or fastest < subs_fastest:
                            subs_fastest = fastest
                for r in conn.execute(
                        "SELECT lang, COUNT(*) AS n FROM submissions "
                        "WHERE submitted_at LIKE ? AND lang != '' GROUP BY lang", (prefix,)):
                    # 规范化语言名：Java / java 视为同一个
                    raw = str(r[0]).strip()
                    if raw:
                        langs[raw.lower()] += int(r[1])
            except sqlite3.Error:
                pass

            # 记忆强度：FSRS 的 stability / difficulty
            try:
                for r in conn.execute(
                        "SELECT stability, difficulty FROM review_cards "
                        "WHERE stability IS NOT NULL"):
                    stability.append(float(r[0]))
                    if r[1] is not None:
                        difficulty.append(float(r[1]))
            except sqlite3.Error:
                pass

            # 第一次
            for key, sql in (
                ("first_view", "SELECT MIN(studied_at) FROM study_events WHERE studied_at LIKE ?"),
                ("first_ac", "SELECT MIN(submitted_at) FROM submissions WHERE status='ac' AND submitted_at LIKE ?"),
                ("first_favorite", "SELECT MIN(created_at) FROM favorites WHERE created_at LIKE ?"),
                ("first_review", "SELECT MIN(reviewed_at) FROM review_logs WHERE reviewed_at LIKE ?"),
            ):
                value = _first_of(conn, sql, (prefix,))
                if value and (firsts[key] is None or value < firsts[key]):
                    firsts[key] = value

            # 最晚打开
            try:
                row = conn.execute(
                    "SELECT activity_date, latest_at, target_type, target_title "
                    "FROM daily_latest_activity WHERE activity_date LIKE ? "
                    "ORDER BY substr(latest_at,12,8) DESC LIMIT 1", (prefix,)).fetchone()
                if row and (latest_activity is None or str(row[1])[11:19] > latest_activity["clock"]):
                    latest_activity = {
                        "date": str(row[0]), "clock": str(row[1])[11:19],
                        "type": str(row[2]), "title": str(row[3] or ""),
                    }
            except sqlite3.Error:
                pass
        finally:
            conn.close()

    # 体育馆（独立库）
    gym = {"total": 0, "favorite_slot": None, "venue": None, "success_rate": None}
    gym_db = DB_PATH.parent / "gym.db"
    if gym_db.exists():
        try:
            gconn = sqlite3.connect(gym_db)
            gconn.row_factory = sqlite3.Row
            rows = gconn.execute(
                "SELECT status, venue, result, created_at FROM gym_jobs WHERE created_at LIKE ?",
                (prefix,)).fetchall()
            succeeded = [r for r in rows if r["status"] == "succeeded"]
            gym["total"] = len(succeeded)
            if rows:
                gym["success_rate"] = round(len(succeeded) / len(rows) * 100)
            slots: Counter[str] = Counter()
            venues: Counter[str] = Counter()
            for r in succeeded:
                venues[str(r["venue"])] += 1
                try:
                    slot = json.loads(r["result"] or "{}").get("actual_slot")
                    if slot:
                        slots[str(slot)] += 1
                except Exception:  # noqa: BLE001
                    pass
            if slots:
                gym["favorite_slot"] = slots.most_common(1)[0][0]
                gym["favorite_slot_count"] = slots.most_common(1)[0][1]
            if venues:
                gym["venue"] = venues.most_common(1)[0][0]
            if succeeded:
                firsts["first_gym"] = str(min(str(r["created_at"]) for r in succeeded))
            gconn.close()
        except sqlite3.Error:
            pass

    # 连续学习天数
    sorted_days = sorted(daily)
    longest_streak = 0
    current = 0
    prev: date_cls | None = None
    for day in sorted_days:
        try:
            d = date_cls.fromisoformat(day)
        except ValueError:
            continue
        if prev is not None and (d - prev).days == 1:
            current += 1
        else:
            current = 1
        longest_streak = max(longest_streak, current)
        prev = d

    stats = {
        "active_days": len(sorted_days),
        "total_seconds": totals["seconds"],
        "total_hours": round(totals["seconds"] / 3600, 1),
        "total_problems": totals["problems"],
        "total_contents": totals["contents"],
        "total_submissions": totals["submissions"],
        "total_reviews": totals["reviews"],
        "favorites": totals["favorites"],
        "mock_exams": totals["mock_exams"],
        "hour_histogram": dict(sorted(hours.items())),
        "module_distribution": dict(modules.most_common(20)),
        "top_keywords": [{"keyword": k, "count": n} for k, n in keywords.most_common(20)],
        "gym": gym,
        "submission_stats": {
            "total": totals["submissions"],
            "ac": subs_ac,
            "ac_rate": round(subs_ac / totals["submissions"] * 100) if totals["submissions"] else None,
            "fastest_ms": subs_fastest,
            "languages": [{"name": k[:1].upper() + k[1:], "count": n}
                          for k, n in langs.most_common(5)],
        },
        "memory_stats": {
            "cards": len(stability),
            "avg_stability": round(sum(stability) / len(stability), 1) if stability else None,
            "max_stability": round(max(stability), 1) if stability else None,
            "avg_difficulty": round(sum(difficulty) / len(difficulty), 2) if difficulty else None,
        },
    }
    # 模块 id → 友好标题（书架 manifest 里的 title）
    try:
        from interview_forge.services.catalog import load_library_manifest
        manifest = load_library_manifest()
        titles = {str(m.get("id")): str(m.get("title") or m.get("id"))
                  for m in manifest.get("modules", [])}
        stats["module_titles"] = {k: titles.get(k, k) for k in stats["module_distribution"]}
    except Exception:  # noqa: BLE001
        stats["module_titles"] = {}

    stats["persona"] = _persona(stats)
    stats["longest_streak"] = longest_streak
    stats["daily_calendar"] = dict(sorted(daily.items()))
    stats["firsts"] = firsts
    stats["latest_activity"] = latest_activity
    stats["year"] = year
    return stats
