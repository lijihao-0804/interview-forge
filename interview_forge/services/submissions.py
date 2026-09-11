"""Submission history and derived submission statistics."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path

from interview_forge.core.paths import DB_PATH


def _runtime():
    from interview_forge.server import study_server

    return study_server


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
    runtime = _runtime()
    if problem_id not in runtime.PROBLEM_BY_ID:
        raise ValueError("未知题号")
    if status not in ("ac", "wa"):
        raise ValueError("未知提交状态")
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
            (problem_id, status, lang[:40], runtime_ms, memory_kb, studied_at, source),
        )
        connection.commit()
    runtime._invalidate_learning_caches(db_path)
    return {"problem_id": problem_id, "status": status, "submitted_at": studied_at}


def submissions_for_problem(problem_id: int, limit: int = 50, db_path: Path = DB_PATH) -> list[dict[str, object]]:
    runtime = _runtime()
    rows = []
    with closing(runtime.connect(db_path)) as connection:
        for row in connection.execute(
            """SELECT id, problem_id, status, lang, runtime_ms, memory_kb, submitted_at, source
               FROM submissions WHERE problem_id = ? ORDER BY id DESC LIMIT ?""",
            (problem_id, min(max(limit, 1), 200)),
        ):
            rows.append(dict(row))
    return rows


def submission_summary(db_path: Path = DB_PATH) -> dict[str, object]:
    runtime = _runtime()
    today = runtime.business_now().date().isoformat()
    with closing(runtime.connect(db_path)) as connection:
        row = connection.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN status = 'ac' AND date(submitted_at, '+8 hours') = ? THEN 1 ELSE 0 END), 0) AS today_ac,
                 COALESCE(SUM(CASE WHEN date(submitted_at, '+8 hours') = ? THEN 1 ELSE 0 END), 0) AS today_submits,
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
            "last_submitted_at": str(item["last_submitted_at"]) if item["last_submitted_at"] else "",
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
