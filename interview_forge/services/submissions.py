"""Submission history and derived submission statistics."""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path

from interview_forge.core.paths import DB_PATH
from interview_forge.core.runtime import server_runtime

VALID_SUBMIT_SOURCES = ("manual", "bookmarklet", "extension", "sync")


def submission_language_key(lang: str | None) -> str:
    """Group provider aliases while keeping unattributed history in its own bucket."""
    name = (lang or "").strip().casefold()
    if name in ("", "unknown", "none", "null", "n/a", "-", "未注明"):
        return "unknown"
    compact = name.replace(" ", "")
    if re.fullmatch(r"(?:python|pypy|py)(?:[23](?:\.\d+)*)?", compact):
        return "python"
    if re.fullmatch(r"java(?:\d+)?", compact):
        return "java"
    if re.fullmatch(r"(?:c\+\+|cpp|gnu\+\+)(?:\d+)?", compact):
        return "cpp"
    return {"golang": "go", "csharp": "c#", "js": "javascript", "ts": "typescript"}.get(name, name)


def problem_language_progress(
    connection: sqlite3.Connection, problem_id: int | None = None,
) -> dict[int, dict[str, dict]]:
    """AC days and attempts by problem/language, from the caller's full SQL snapshot."""
    connection.create_function("submission_language", 1, submission_language_key, deterministic=True)
    where = "WHERE problem_id = ?" if problem_id is not None else ""
    rows = connection.execute(
        f"""SELECT problem_id, submission_language(lang) AS language,
                   COUNT(DISTINCT CASE WHEN status = 'ac' THEN date(submitted_at, '+8 hours') END) AS rounds,
                   COUNT(*) AS submits, SUM(status = 'ac') AS ac_submits,
                   strftime('%Y-%m-%dT%H:%M:%fZ', MAX(julianday(submitted_at))) AS last_submitted_at
            FROM submissions {where}
            GROUP BY problem_id, language""",
        (problem_id,) if problem_id is not None else (),
    )
    result: dict[int, dict[str, dict]] = {}
    for row in rows:
        stats = dict(row)
        pid = stats.pop("problem_id")
        language = stats.pop("language")
        result.setdefault(pid, {})[language] = stats
    return result


def record_submission(
    problem_id: int,
    status: str,
    lang: str = "",
    runtime_ms: int | None = None,
    memory_kb: int | None = None,
    source: str = "manual",
    db_path: Path = DB_PATH,
) -> dict[str, object]:
    runtime = server_runtime
    if problem_id not in runtime.PROBLEM_BY_ID:
        raise ValueError("未知题号")
    if status not in ("ac", "wa"):
        raise ValueError("未知提交状态")
    if not isinstance(lang, str):
        raise TypeError("lang 必须是字符串")
    if source not in runtime.VALID_SUBMIT_SOURCES:
        source = "manual"

    def optional_int(value: object, name: str) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError(f"{name} 必须是整数")

    runtime_ms = optional_int(runtime_ms, "runtime_ms")
    memory_kb = optional_int(memory_kb, "memory_kb")
    studied_at, _ = runtime.now_parts()
    with closing(runtime.connect(db_path)) as connection:
        connection.execute(
            """INSERT INTO submissions(problem_id, status, lang, runtime_ms, memory_kb, submitted_at, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (problem_id, status, lang.strip()[:40], runtime_ms, memory_kb, studied_at, source),
        )
        connection.commit()
    runtime._invalidate_learning_caches(db_path)
    return {"problem_id": problem_id, "status": status, "submitted_at": studied_at}


def submissions_for_problem(problem_id: int, limit: int = 50, db_path: Path = DB_PATH) -> list[dict[str, object]]:
    runtime = server_runtime
    rows = []
    with closing(runtime.connect(db_path)) as connection:
        for row in connection.execute(
            """SELECT id, problem_id, status, lang, runtime_ms, memory_kb, submitted_at, source
               FROM submissions WHERE problem_id = ? ORDER BY julianday(submitted_at) DESC, id DESC LIMIT ?""",
            (problem_id, min(max(limit, 1), 200)),
        ):
            rows.append({**dict(row), "language_key": submission_language_key(row["lang"])})
    return rows


def submission_summary(db_path: Path = DB_PATH) -> dict[str, object]:
    runtime = server_runtime
    today = runtime.business_now().date().isoformat()
    with closing(runtime.connect(db_path)) as connection:
        connection.execute("BEGIN")
        return submission_summary_from_connection(connection, today)


def submission_summary_from_connection(connection: sqlite3.Connection, today: str) -> dict[str, object]:
    row = connection.execute(
        """SELECT
             COALESCE(SUM(CASE WHEN status = 'ac' AND date(submitted_at, '+8 hours') = ? THEN 1 ELSE 0 END), 0) AS today_ac,
             COALESCE(SUM(CASE WHEN date(submitted_at, '+8 hours') = ? THEN 1 ELSE 0 END), 0) AS today_submits,
             COALESCE(SUM(CASE WHEN status = 'ac' THEN 1 ELSE 0 END), 0) AS total_ac,
             COUNT(DISTINCT CASE WHEN status = 'ac' THEN problem_id END) AS solved_ac,
             COUNT(*) AS total_submits
           FROM submissions""",
        (today, today),
    ).fetchone()
    problem_rows = connection.execute(
        """SELECT problem_id, MAX(status = 'ac') AS ever_ac, COUNT(*) AS submits,
                  SUM(status = 'ac') AS ac_submits
           FROM submissions GROUP BY problem_id"""
    ).fetchall()
    last_rows = connection.execute(
        """SELECT problem_id, status, submitted_at FROM (
               SELECT problem_id, status, submitted_at, ROW_NUMBER() OVER (
                   PARTITION BY problem_id ORDER BY julianday(submitted_at) DESC, id DESC
               ) AS newest FROM submissions
           ) WHERE newest = 1"""
    ).fetchall()
    summary = {key: int(value or 0) for key, value in dict(row).items()}
    summary["pass_rate"] = round(summary["total_ac"] / summary["total_submits"], 3) if summary["total_submits"] else None
    last_map = {int(item["problem_id"]): dict(item) for item in last_rows}
    problems: dict[int, dict[str, object]] = {}
    auto_weak: dict[str, bool] = {}
    for item in problem_rows:
        pid = int(item["problem_id"])
        submits = int(item["submits"] or 0)
        ac_submits = int(item["ac_submits"] or 0)
        pass_rate = round(ac_submits / submits, 3) if submits else None
        last = last_map.get(pid, {})
        problems[pid] = {
            "submits": submits, "ac_submits": ac_submits, "pass_rate": pass_rate,
            "last_submitted_at": str(last.get("submitted_at") or ""),
            "last_status": str(last.get("status") or ""),
        }
        if submits and pass_rate is not None and pass_rate < 0.5:
            auto_weak[str(pid)] = True
    return {
        "summary": summary,
        "ever_ac": {int(item["problem_id"]): bool(item["ever_ac"]) for item in problem_rows},
        "problems": problems,
        "auto_weak": auto_weak,
    }
