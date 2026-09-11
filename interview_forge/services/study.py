"""Learning and review domain services extracted from the HTTP assembly.

The implementation remains behavior-compatible with the historical study
server. Runtime lookups intentionally resolve through the server facade so
existing callers and tests that patch its public symbols keep working.
"""
from __future__ import annotations

import json
import os
import operator
import random
import re
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from interview_forge.core.paths import DB_PATH, ROOT
from interview_forge.core.runtime import server_runtime



class _RuntimeLookup:
    def __init__(self, name: str):
        self.name = name

    def _value(self):
        return getattr(server_runtime, self.name)

    def __call__(self, *args, **kwargs):
        return self._value()(*args, **kwargs)

    def __getattr__(self, attr):
        return getattr(self._value(), attr)

    def __getitem__(self, key):
        return self._value()[key]

    def __setitem__(self, key, value):
        self._value()[key] = value

    def __contains__(self, item):
        return item in self._value()

    def __iter__(self):
        return iter(self._value())

    def __len__(self):
        return len(self._value())

    def __bool__(self):
        return bool(self._value())

    def __enter__(self):
        return self._value().__enter__()

    def __exit__(self, exc_type, exc, tb):
        return self._value().__exit__(exc_type, exc, tb)

    def __fspath__(self):
        return os.fspath(self._value())

    def __truediv__(self, other):
        return self._value() / other

    def __str__(self):
        return str(self._value())

    def __int__(self):
        return int(self._value())

    def __index__(self):
        return operator.index(self._value())

    def __eq__(self, other):
        return self._value() == other

    def __lt__(self, other):
        return self._value() < other

    def __le__(self, other):
        return self._value() <= other

    def __gt__(self, other):
        return self._value() > other

    def __ge__(self, other):
        return self._value() >= other

    def __add__(self, other):
        return self._value() + other

    def __radd__(self, other):
        return other + self._value()

    def __sub__(self, other):
        return self._value() - other

    def __rsub__(self, other):
        return other - self._value()


PROBLEM_BY_ID = _RuntimeLookup("PROBLEM_BY_ID")
LEETCODE_SLUGS = _RuntimeLookup("LEETCODE_SLUGS")
problem_filename = _RuntimeLookup("problem_filename")
ROUND_COMPLETE_THRESHOLD = _RuntimeLookup("ROUND_COMPLETE_THRESHOLD")
BUSINESS_TZ = _RuntimeLookup("BUSINESS_TZ")
_DASH_CACHE: dict[str, tuple[float, dict[str, object]]] = {}
_DASH_CACHE_LOCK = threading.Lock()
_DASH_CACHE_GENERATIONS: dict[str, int] = {}
_DASH_TTL = _RuntimeLookup("_DASH_TTL")

def record_view(problem_id: int, db_path: Path = DB_PATH) -> bool:
    """记录一次题目浏览（view 事件）：60 秒内对同一题去重，防止翻页/刷接口产生垃圾记录。"""
    if problem_id not in PROBLEM_BY_ID:
        # 未知题号直接忽略 —— 浏览埋点属"尽力而为"，不因脏请求而报错。
        return False
    studied_at, study_date = server_runtime.now_parts()
    with closing(server_runtime.connect(db_path)) as connection:
        # Serialize the read-check-write sequence so concurrent page loads
        # cannot both pass the 60-second de-duplication window.
        connection.execute("BEGIN IMMEDIATE")
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
    server_runtime._invalidate_learning_caches(db_path)
    return True


def complete_round(problem_id: int, db_path: Path = DB_PATH) -> dict[str, object]:
    """兼容旧面板的手动完成接口，并写入 AC 语义的 submissions 读模型。

    The legacy study event is retained for old exports, while the submission
    row makes dashboard/daily/analytics (which use AC submissions) observe the
    same completion.  Multiple completions on one business day share one
    round, matching the canonical AC round definition.
    """
    if problem_id not in PROBLEM_BY_ID:
        raise ValueError("未知题号")
    studied_at, study_date = server_runtime.now_parts()
    with closing(server_runtime.connect(db_path)) as connection:
        # BEGIN IMMEDIATE：立刻拿写锁，"取下一轮次 + 插入"在同一事务内原子完成，
        # 并发双击也不会开出重复轮次（配合唯一索引 uq_problem_round 双保险）。
        connection.execute("BEGIN IMMEDIATE")
        event_rows = connection.execute(
            "SELECT round_no, date(studied_at, '+8 hours') AS study_date "
            "FROM study_events WHERE problem_id = ? AND action = 'complete'",
            (problem_id,),
        ).fetchall()
        submission_rows = connection.execute(
            "SELECT submitted_at FROM submissions WHERE problem_id = ? AND status = 'ac'",
            (problem_id,),
        ).fetchall()
        completed_dates = {str(row["study_date"]) for row in event_rows}
        for row in submission_rows:
            try:
                completed_dates.add(
                    datetime.fromisoformat(str(row["submitted_at"]))
                    .astimezone(BUSINESS_TZ).date().isoformat()
                )
            except (TypeError, ValueError, OverflowError):
                # Invalid historical timestamps are excluded by analytics and
                # must not make the compatibility endpoint fail.
                continue
        existing_today = [
            int(row["round_no"]) for row in event_rows
            if str(row["study_date"]) == study_date and row["round_no"] is not None
        ]
        date_already_completed = study_date in completed_dates
        if existing_today:
            round_no = max(existing_today)
        elif date_already_completed:
            round_no = sorted(completed_dates).index(study_date) + 1
        else:
            max_event_round = max((int(row["round_no"] or 0) for row in event_rows), default=0)
            # Preserve any historical duplicate-day round numbering while
            # still accounting for AC dates that have no legacy event row.
            round_no = max(max_event_round, len(completed_dates)) + 1
        if not date_already_completed:
            connection.execute(
                """INSERT INTO study_events(problem_id, action, studied_at, study_date, round_no)
                   VALUES (?, 'complete', ?, ?, ?)""",
                (problem_id, studied_at, study_date, round_no),
            )
        # AC is the canonical Hot100 completion read model.  Keep each call as
        # a submission history row; analytics deduplicates same-day ACs into a
        # single round while preserving the attempt count.
        connection.execute(
            """INSERT INTO submissions(
                   problem_id, status, lang, runtime_ms, memory_kb, submitted_at, source
               ) VALUES (?, 'ac', '', NULL, NULL, ?, 'manual')""",
            (problem_id, studied_at),
        )
        connection.commit()
    # Hot100 library progress is derived from AC submissions; no separate
    # content-event mirror is needed and avoiding it keeps this endpoint atomic.
    server_runtime._invalidate_learning_caches(db_path)
    # next_due：前端用它展示"下次复习时间"（= 完成时间 + 轮次对应间隔）。
    return {
        "problem_id": problem_id,
        "round_no": round_no,
        "studied_at": studied_at,
        "next_due": server_runtime.due_after(studied_at, round_no),
    }


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
    data = server_runtime.dashboard_data(db_path)
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
    today = server_runtime.business_now().date().isoformat()
    with closing(server_runtime.connect(db_path)) as connection:
        view_rows = connection.execute(
            """SELECT problem_id, MAX(studied_at) AS last_viewed_at
               FROM study_events WHERE action = 'view' GROUP BY problem_id"""
        ).fetchall()
        # 题目完成轮次 = 出现过 AC 的自然日数量；同日多提交只计一轮。
        ac_rows = connection.execute(
            """SELECT problem_id,
                      COUNT(DISTINCT date(submitted_at, '+8 hours')) AS rounds,
                      MAX(submitted_at) AS last_completed_at,
                      MAX(date(submitted_at, '+8 hours')) AS last_ac_date
               FROM submissions WHERE status = 'ac' GROUP BY problem_id"""
        ).fetchall()
        study_summary = connection.execute(
            """SELECT
                 COUNT(DISTINCT CASE WHEN date(studied_at, '+8 hours') = ? AND action = 'view' THEN problem_id END) AS today_viewed
               FROM study_events WHERE action = 'view'""",
            (today,),
        ).fetchone()
        ac_summary = connection.execute(
            """SELECT
                 COUNT(DISTINCT CASE WHEN date(submitted_at, '+8 hours') = ? THEN problem_id END) AS today_rounds,
                 COUNT(DISTINCT problem_id) AS completed_problems
               FROM submissions WHERE status = 'ac'""",
            (today,),
        ).fetchone()
        # 累计轮次 = 完整刷题遍数：每题按"AC 过的不同天数"计轮，
        # 轮次 k 达成 = 有 ≥ ROUND_COMPLETE_THRESHOLD 道题的轮数 ≥ k
        per_problem_rounds = [int(r["rd"]) for r in connection.execute(
            """SELECT problem_id, COUNT(DISTINCT date(submitted_at, '+8 hours')) AS rd
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
                      date(submitted_at, '+8 hours') AS study_date,
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
            """SELECT date(studied_at, '+8 hours') AS study_date,
                       COUNT(DISTINCT problem_id) AS viewed
               FROM study_events WHERE action = 'view' GROUP BY study_date"""
        ).fetchall()
        ac_days = connection.execute(
            """SELECT date(submitted_at, '+8 hours') AS study_date,
                      COUNT(DISTINCT problem_id) AS rounds
               FROM submissions WHERE status = 'ac' GROUP BY study_date"""
        ).fetchall()
        content_days = connection.execute(
            """SELECT date(studied_at, '+8 hours') AS study_date,
                       COUNT(DISTINCT CASE WHEN action = 'view' THEN content_id END) AS viewed,
                       SUM(CASE WHEN action = 'complete' THEN 1 ELSE 0 END) AS rounds
               FROM content_events WHERE module_id <> 'hot100' GROUP BY study_date"""
        ).fetchall()
        submission_days = connection.execute(
            """SELECT date(submitted_at, '+8 hours') AS study_date, COUNT(1) AS submits
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
    base = server_runtime.business_now().date() - timedelta(days=364)
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
    cursor = server_runtime.business_now().date()
    if cursor.isoformat() not in active_dates:
        cursor -= timedelta(days=1)
    while cursor.isoformat() in active_dates:
        streak += 1
        cursor -= timedelta(days=1)
    try:
        daily_goal = max(1, min(50, int(server_runtime.get_settings(db_path).get("daily_goal_rounds", "3") or "3")))
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
            item["next_due"] = server_runtime.due_after(last_completed, rounds)
        problems_payload[str(pid)] = item
    submissions_payload = server_runtime.submission_summary(db_path)
    with closing(server_runtime.connect(db_path)) as connection:
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
        "marks": server_runtime.problem_marks(db_path),
        "submissions": submissions_payload,
    }


def record_content_view(module_id: str, content_id: str, db_path: Path = DB_PATH) -> bool:
    """书架章节浏览事件：与题目 record_view 完全同构（含 60 秒去重），写进 content_events。"""
    if not server_runtime.valid_content(module_id, content_id):
        return False
    studied_at, study_date = server_runtime.now_parts()
    with closing(server_runtime.connect(db_path)) as connection:
        # Serialize the read-check-write sequence for the same 60-second
        # de-duplication guarantee as record_view().
        connection.execute("BEGIN IMMEDIATE")
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
    server_runtime._invalidate_learning_caches(db_path)
    return True


def complete_content(module_id: str, content_id: str, db_path: Path = DB_PATH) -> dict[str, object]:
    """书架章节"完成一轮"：轮次自增 + 写库（事务内原子完成），返回下次到期日。"""
    if not server_runtime.valid_content(module_id, content_id):
        raise ValueError("未知课程章节")
    studied_at, study_date = server_runtime.now_parts()
    with closing(server_runtime.connect(db_path)) as connection:
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
    server_runtime._invalidate_learning_caches(db_path)
    # next_due：按章节专用间隔表（REVIEW_INTERVALS_CONTENT）推算的到期日，前端展示"下次复习"。
    return {
        "module_id": module_id,
        "content_id": content_id,
        "round_no": round_no,
        "studied_at": studied_at,
        "next_due": server_runtime.due_after_content(studied_at, round_no),
    }


def ac_problem_progress(db_path: Path = DB_PATH) -> dict[int, dict[str, object]]:
    """按 AC 日期统计 Hot100 题目轮次：同一天多次 AC 只算一轮。"""
    with closing(server_runtime.connect(db_path)) as connection:
        rows = connection.execute(
            """SELECT problem_id,
                      COUNT(DISTINCT date(submitted_at, '+8 hours')) AS rounds,
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
    ac = server_runtime.ac_problem_progress(db_path)
    with closing(server_runtime.connect(db_path)) as connection:
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
    manifest = server_runtime.load_library_manifest()
    with closing(server_runtime.connect(db_path)) as connection:
        # 非 Hot100 章节仍按手动“完成一轮”；Hot100 题目由 AC 日期自动推进。
        rows = connection.execute(
            """SELECT content_id,
                      SUM(CASE WHEN action = 'complete' THEN 1 ELSE 0 END) AS rounds,
                      MAX(studied_at) AS last_activity_at
               FROM content_events WHERE module_id <> 'hot100' GROUP BY content_id"""
        ).fetchall()
    contents = {str(row["content_id"]): dict(row) for row in rows}
    for pid, progress in server_runtime.ac_problem_progress(db_path).items():
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
    today = server_runtime.business_now().date().isoformat()
    ac_progress = server_runtime.ac_problem_progress(db_path)
    with closing(server_runtime.connect(db_path)) as connection:
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
            due = server_runtime.due_after(str(progress["last_completed_at"]), rounds)
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

    manifest = server_runtime.load_library_manifest()
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
        due = server_runtime.due_after_content(row["last_completed_at"], rounds)
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
    with closing(server_runtime.connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT target_id, mark FROM marks WHERE target_type = 'problem'"
        ).fetchall()
    return {str(row["target_id"]): str(row["mark"]) for row in rows}


def get_settings(db_path: Path = DB_PATH) -> dict[str, str]:
    """读取 settings 表全部 KV → {key: value} 字典。"""
    with closing(server_runtime.connect(db_path)) as connection:
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
    with closing(server_runtime.connect(db_path)) as connection:
        connection.execute(
            """INSERT INTO settings(key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )
        connection.commit()
    server_runtime._invalidate_learning_caches(db_path)
    return {"key": key, "value": value}


def valid_content_id(content_id: str) -> bool:
    """仅校验 content_id 是否存在于书架（不区分模块），set_mark 打章节标记时用。"""
    manifest = server_runtime.load_library_manifest()
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
    elif not server_runtime.valid_content_id(target_id):
        raise ValueError("未知章节")
    studied_at, _ = server_runtime.now_parts()
    with closing(server_runtime.connect(db_path)) as connection:
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
    server_runtime._invalidate_learning_caches(db_path)
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
    info = server_runtime.problem_review_state(db_path)
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
    today = server_runtime.business_now().date().isoformat()
    daily = server_runtime.daily_data(db_path)
    due_ids = {int(item["id"]) for item in daily["problems"]}
    relearn_ids = {int(item["id"]) for item in daily.get("relearn", [])}
    info = server_runtime.problem_review_state(db_path)
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
    with closing(server_runtime.connect(db_path)) as connection:
        connection.execute("DELETE FROM plan_pins WHERE for_date < ?", (today,))
        # The default sqlite isolation level starts a transaction for DELETE;
        # commit explicitly so stale pins are actually removed on close.
        connection.commit()
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
    with closing(server_runtime.connect(db_path)) as connection:
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
        for pid, progress in server_runtime.ac_problem_progress(db_path).items()
    }
    first_view = {int(row["problem_id"]): str(row["first_view"]) for row in view_rows}
    submissions = server_runtime.submission_summary(db_path)
    all_marks = server_runtime.problem_marks(db_path)
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
        marks = server_runtime.problem_marks(db_path)
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
        with closing(server_runtime.connect(db_path)) as connection:
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
        now = server_runtime.business_now()
        monday = (now - timedelta(days=now.weekday())).date()
        monday_iso = monday.isoformat()
        today_iso = now.date().isoformat()
        with closing(server_runtime.connect(db_path)) as connection:
            problem_rounds = int(connection.execute(
                """SELECT COUNT(*) AS n FROM (
                    SELECT problem_id, date(submitted_at, '+8 hours') AS d
                    FROM submissions WHERE status = 'ac' AND date(submitted_at, '+8 hours') >= ?
                    GROUP BY problem_id, d
                )""",
                (monday_iso,),
            ).fetchone()["n"] or 0)
            content_rounds = int(connection.execute(
                "SELECT COUNT(*) AS n FROM content_events "
                "WHERE action='complete' AND module_id <> 'hot100' "
                "AND date(studied_at, '+8 hours') >= ?",
                (monday_iso,),
            ).fetchone()["n"] or 0)
            active_days = int(connection.execute(
                """SELECT COUNT(DISTINCT study_date) AS n FROM (
                    SELECT date(studied_at, '+8 hours') AS study_date
                    FROM study_events
                    WHERE action = 'view' AND date(studied_at, '+8 hours') >= ?
                    UNION
                    SELECT date(submitted_at, '+8 hours') FROM submissions WHERE date(submitted_at, '+8 hours') >= ?
                    UNION
                    SELECT date(studied_at, '+8 hours') AS study_date
                    FROM content_events
                    WHERE module_id <> 'hot100' AND date(studied_at, '+8 hours') >= ?
                )""",
                (monday_iso, monday_iso, monday_iso),
            ).fetchone()["n"] or 0)
            active_dates_all = {str(r["study_date"]) for r in connection.execute(
                """SELECT date(studied_at, '+8 hours') AS study_date
                   FROM study_events WHERE action = 'view'
                   UNION SELECT date(submitted_at, '+8 hours') AS study_date FROM submissions
                   UNION SELECT date(studied_at, '+8 hours') AS study_date
                   FROM content_events WHERE module_id <> 'hot100'"""
            )}
        streak = 0
        cursor = now.date()
        if cursor.isoformat() not in active_dates_all:
            cursor -= timedelta(days=1)
        while cursor.isoformat() in active_dates_all:
            streak += 1
            cursor -= timedelta(days=1)
        marks = server_runtime.problem_marks(db_path)
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
