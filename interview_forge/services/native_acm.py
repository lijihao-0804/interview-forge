"""Native practice catalog, authoritative output comparison and per-user submission records."""
import json
import math
from contextlib import closing
from functools import lru_cache

from interview_forge.core.paths import ROOT
from interview_forge.core.runtime import server_runtime
from interview_forge.db.connection import connect


@lru_cache(maxsize=2)
def _catalog(prefix):
    filename = {"hot100": "hot100.json", "hot200": "hot200-extra.json"}[prefix]
    rows = json.loads((ROOT / "data/acm" / filename).read_text(encoding="utf-8"))
    return {row["id"]: row for row in rows}


def problem(key):
    prefix, _, number = key.partition("-")
    if prefix not in {"hot100", "hot200"} or not number.isascii() or not number.isdecimal():
        return None
    return _catalog(prefix).get(key)


def same_json(a, b, abs_tol=0, rel_tol=0):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (float, int)) and isinstance(b, (float, int)):
        return a == b or ((abs_tol or rel_tol) and math.isclose(a, b, abs_tol=abs_tol, rel_tol=rel_tol))
    if type(a) is not type(b):
        return False
    if isinstance(a, list):
        return len(a) == len(b) and all(same_json(x, y, abs_tol, rel_tol) for x, y in zip(a, b))
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same_json(a[k], b[k], abs_tol, rel_tol) for k in a)
    return a == b


def matches(actual, expected, checker):
    mode = checker["mode"]
    if mode == "json":
        try:
            return same_json(json.loads(actual), json.loads(expected), checker.get("abs_tol", 0), checker.get("rel_tol", 0))
        except (ValueError, RecursionError, OverflowError):
            return False
    if mode == "tokens":
        return actual.split() == expected.split()
    if mode == "exact":
        def normalized(value):
            return "\n".join(line.rstrip(" \t") for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")).rstrip("\n")
        return normalized(actual) == normalized(expected)
    raise ValueError("未知输出校验方式")


def statuses(db):
    with closing(connect(db)) as conn:
        rows = conn.execute("SELECT problem_key, MAX(accepted) FROM acm_submissions GROUP BY problem_key")
        return {key.split("-")[1]: "accepted" if accepted else "attempted" for key, accepted in rows}


def practice_progress(db):
    """Count AC days from the full submission ledger, including pre-upgrade attempts."""
    with closing(connect(db)) as conn:
        rows = conn.execute("""
            WITH attempts AS (
                SELECT problem_key, language, date(submitted_at, '+8 hours') AS study_day, accepted
                FROM acm_submissions
            ), scopes AS (
                SELECT * FROM attempts
                UNION ALL SELECT problem_key, '', study_day, accepted FROM attempts
            )
            SELECT problem_key, language, MAX(accepted),
                   COUNT(DISTINCT CASE WHEN accepted THEN study_day END)
            FROM scopes GROUP BY problem_key, language
        """)
        problems = {}
        for key, language, accepted, rounds in rows:
            item = problems.setdefault(key, {"by_language": {}})
            summary = {"status": "accepted" if accepted else "attempted", "rounds": rounds}
            if language:
                item["by_language"][language] = summary
            else:
                item.update(summary)
        return problems


def submission_summary(db, key):
    """Per-account, per-problem summary; source code is never selected."""
    with closing(connect(db)) as conn:
        row = conn.execute(
            """SELECT count(*) OVER (), max(accepted) OVER (), language, submitted_at, accepted
               FROM acm_submissions WHERE problem_key=? ORDER BY submitted_at DESC, id DESC LIMIT 1""",
            (key,),
        ).fetchone()
    if row is None:
        return {"problem_key": key, "attempts": 0, "status": "unattempted"}
    return {
        "problem_key": key, "attempts": row[0], "status": "accepted" if row[1] else "attempted",
        "latest_language": row[2][:32], "latest_submitted_at_utc": row[3][:40],
        "latest_verdict": "accepted" if row[4] else "not_accepted",
    }


def save_submission(db, key, language, code, accepted):
    with closing(connect(db)) as conn, conn:
        conn.execute("INSERT INTO acm_submissions(problem_key,language,code,accepted) VALUES(?,?,?,?)",
                     (key, language, code, int(accepted)))
    server_runtime._invalidate_learning_caches(db)


def submission_history(db, key):
    with closing(connect(db)) as conn:
        rows = conn.execute(
            "SELECT id, language, accepted, strftime('%Y-%m-%dT%H:%M:%SZ', submitted_at) AS submitted_at "
            "FROM acm_submissions WHERE problem_key=? ORDER BY id DESC LIMIT 20", (key,)
        )
        return [{**dict(row), "accepted": bool(row["accepted"])} for row in rows]


def submission_code(db, key, submission_id):
    with closing(connect(db)) as conn:
        row = conn.execute("SELECT code FROM acm_submissions WHERE problem_key=? AND id=?",
                           (key, submission_id)).fetchone()
        return row["code"] if row else None
