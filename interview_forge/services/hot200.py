"""Learning projections for the supplement; never mix its events with Hot 100."""

import csv
import io
import json
import random
import re
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, timedelta
from functools import lru_cache

from interview_forge.core.paths import ROOT
from interview_forge.core.runtime import server_runtime as runtime
from interview_forge.services.submissions import submission_language_key

MODULE = "hot200-extra"


@lru_cache(maxsize=1)
def catalog():
    raw = json.loads((ROOT / "data/hot200-extra.json").read_text(encoding="utf-8"))
    return {
        p["id"]: {
            "id": p["id"],
            "slug": p["slug"],
            "title": p["title"],
            "category": p["topic"],
            "difficulty": p["difficulty"],
            "note": f"/library/{MODULE}/chapter-{i:02d}.html",
        }
        for i, p in enumerate(raw, 1)
    }


def content_key(pid):
    if pid not in catalog():
        raise ValueError("未知补充题")
    return f"{MODULE}:{pid:04d}"


def study_notes(pid):
    """Read bounded teaching facts from this catalog entry's published source."""
    content_key(pid)
    source = ROOT / f"books/hot200-extra/solutions/{pid}.md"
    if not source.is_file():
        return {}
    markdown = source.read_text(encoding="utf-8-sig")
    notes = {}
    for key, heading in (("method", "思路"), ("invariant", "核心不变量"), ("complexity", "复杂度")):
        match = re.search(r"^### " + heading + r"[ \t]*\r?\n\s*([^\r\n]+)", markdown, re.MULTILINE)
        if match:
            notes[key] = match[1].strip()[:240]
    return notes


def pin(db, pid):
    key = content_key(pid)
    tomorrow = (runtime.business_now().date() + timedelta(days=1)).isoformat()
    with closing(runtime.connect(db)) as con:
        con.execute(
            "INSERT OR REPLACE INTO supplement_plan_pins VALUES (?, ?)", (key, tomorrow)
        )
        con.commit()
    return {"for_date": tomorrow}


def record_synced(con, records, retention):
    """A dated, identified provider row is required; a solved flag alone is not an AC."""
    from interview_forge.services.study import _apply_review_rating

    added = 0
    latest = {}
    for r in sorted(records, key=lambda r: r["submitted_at"]):
        key = content_key(r["pid"])
        inserted = con.execute(
            "INSERT OR IGNORE INTO supplement_submissions VALUES (?,?,?,?,?,?,?)",
            (
                r["lc_id"],
                key,
                r["status"],
                r["lang"],
                r["submitted_at"],
                r["runtime_ms"],
                r["memory_kb"],
            ),
        ).rowcount
        added += inserted
        if r["status"] != "ac" or not inserted:
            continue
        day = r["submitted_at"][:10]  # importer converts to business timezone
        if not con.execute(
            "SELECT 1 FROM content_events WHERE content_id=? AND action='complete' AND study_date=?",
            (key, day),
        ).fetchone():
            con.execute(
                """INSERT INTO content_events(module_id,content_id,action,studied_at,study_date,round_no)
                           SELECT ?,?,'complete',?,?,coalesce(max(round_no),0)+1 FROM content_events WHERE content_id=?""",
                (MODULE, key, r["submitted_at"], day, key),
            )
        latest[key] = r["submitted_at"]
    for key, when in latest.items():
        prior = con.execute(
            "SELECT last_reviewed_at FROM review_cards WHERE target_type='content' AND target_id=?",
            (key,),
        ).fetchone()
        if not prior or not prior[0] or prior[0][:10] < when[:10]:
            _apply_review_rating(
                con,
                "content",
                key,
                3,
                when,
                desired_retention=retention,
                source="leetcode_ac",
            )
    return added


def snapshot(db):
    today = runtime.business_now().date()
    raw = catalog()
    events, attempts, languages = (
        defaultdict(list),
        defaultdict(list),
        defaultdict(list),
    )
    with closing(runtime.connect(db)) as con:
        con.execute("BEGIN")
        for r in con.execute(
            "SELECT * FROM content_events WHERE module_id=? ORDER BY studied_at",
            (MODULE,),
        ):
            events[r["content_id"]].append(dict(r))
        for r in con.execute(
            "SELECT * FROM hot200_learning_submissions ORDER BY submitted_at"
        ):
            attempts[r["content_id"]].append(dict(r))
        for r in con.execute("SELECT * FROM supplement_review_languages"):
            languages[r["content_id"]].append(dict(r))
        marks = dict(
            con.execute(
                "SELECT target_id,mark FROM marks WHERE target_type='content' AND target_id LIKE 'hot200-extra:%'"
            )
        )
        due = dict(
            con.execute(
                "SELECT target_id,due_date FROM review_cards WHERE target_type='content' AND target_id LIKE 'hot200-extra:%'"
            )
        )
        pins = dict(
            con.execute(
                "SELECT content_id,for_date FROM supplement_plan_pins WHERE for_date>=?",
                (today.isoformat(),),
            )
        )
        goal = con.execute(
            "SELECT value FROM settings WHERE key='hot200_daily_goal_rounds'"
        ).fetchone()

    info, daily_views, daily_rounds, daily_subs, daily_new = (
        {},
        defaultdict(set),
        Counter(),
        Counter(),
        Counter(),
    )
    lang_counts, weak, due_items = defaultdict(list), {}, []
    for pid, p in raw.items():
        key = content_key(pid)
        ev, sub, lang = events[key], attempts[key], languages[key]
        days = {e["study_date"] for e in ev if e["action"] == "complete"}
        days.update(s["submitted_at"][:10] for s in sub if s["status"] == "ac")
        if days:
            daily_new[min(days)] += 1
        for d in days:
            daily_rounds[d] += 1
        for e in ev:
            if e["action"] == "view":
                daily_views[e["study_date"]].add(pid)
        groups = defaultdict(lambda: {"dates": set(), "submits": 0, "ac_submits": 0})
        for s in sub:
            g = groups[submission_language_key(s["language"])]
            g["submits"] += 1
            g["last_submitted_at"] = s["submitted_at"]
            daily_subs[s["submitted_at"][:10]] += 1
            if s["status"] == "ac":
                g["ac_submits"] += 1
                g["dates"].add(s["submitted_at"][:10])
        for r in lang:
            groups[r["language"]]["dates"].add(r["study_date"])
        unattributed = days.difference(*(g["dates"] for g in groups.values()))
        if unattributed:
            groups["unknown"]["dates"].update(unattributed)
        for name, g in groups.items():
            g["rounds"] = len(g.pop("dates"))
            lang_counts[name].append(g["rounds"])
        dates = [e["studied_at"] for e in ev] + [s["submitted_at"] for s in sub]
        rounds = len(days)
        ac = sum(s["status"] == "ac" for s in sub)
        info[str(pid)] = {
            "rounds": rounds,
            "submits": len(sub),
            "ac_submits": ac,
            "by_language": dict(groups),
            "mark": marks.get(key, ""),
            "last_submitted_at": sub[-1]["submitted_at"] if sub else None,
            "last_activity_at": max(dates, default=None),
            "next_due": due.get(key),
        }
        if len(sub) >= 3 and ac * 2 < len(sub):
            weak[str(pid)] = True
        if due.get(key) and due[key] <= today.isoformat():
            due_items.append(dict(p, due_date=due[key], rounds=rounds))
    due_items.sort(key=lambda p: (p["due_date"], p["id"]))
    ds = today.isoformat()
    first = min([ds, *daily_views, *daily_rounds, *daily_subs])
    start = min(date.fromisoformat(first), today - timedelta(days=27))
    activity = []
    for i in range((today - start).days + 1):
        d = (start + timedelta(days=i)).isoformat()
        activity.append(
            {
                "date": d,
                "viewed": len(daily_views[d]),
                "rounds": daily_rounds[d],
                "submits": daily_subs[d],
                "newly_solved": daily_new[d],
            }
        )
    streak = 0
    anchor = today if daily_rounds[ds] else today - timedelta(days=1)
    while daily_rounds[(anchor - timedelta(days=streak)).isoformat()]:
        streak += 1
    values = list(info.values())
    stat = {
        "today_viewed": len(daily_views[ds]),
        "today_rounds": daily_rounds[ds],
        "completed_problems": sum(v["rounds"] > 0 for v in values),
        "total_rounds": min(v["rounds"] for v in values),
        "daily_goal": int(goal[0]) if goal else 3,
        "streak": streak,
    }
    forecast = [
        {
            "date": (today + timedelta(days=i)).isoformat(),
            "count": list(due.values()).count((today + timedelta(days=i)).isoformat()),
        }
        for i in range(1, 8)
    ]
    over = sum(p["due_date"] < ds for p in due_items)
    daily = {
        "today": ds,
        "problems": due_items,
        "contents": [],
        "summary": {
            "due": len(due_items),
            "overdue": over,
            "problems": len(due_items),
            "overdue_problems": over,
            "contents": 0,
            "upcoming_review": {
                "days": forecast, "total": sum(x["count"] for x in forecast)
            },
        },
    }
    subs = {
        "today_ac": sum(
            s["status"] == "ac" and s["submitted_at"][:10] == ds
            for group in attempts.values()
            for s in group
        ),
        "today_submits": daily_subs[ds],
        "total_ac": sum(v["ac_submits"] for v in values),
        "solved_ac": sum(bool(v["ac_submits"]) for v in values),
    }
    return {
        "dashboard": {
            "summary": stat,
            "activity": activity,
            "problems": info,
            "marks": {
                str(p): marks[content_key(p)] for p in raw if content_key(p) in marks
            },
            "submissions": {"summary": subs, "auto_weak": weak},
            "language_summary": {
                k: {
                    "completed_problems": sum(v > 0 for v in vs),
                    "total_rounds": min(vs) if len(vs) == len(raw) else 0,
                }
                for k, vs in lang_counts.items()
            },
        },
        "daily": daily,
        "settings": {},
        "pinnedTomorrow": {str(p): True for p in raw if pins.get(content_key(p), "") > ds},
        "pinnedToday": [p for p in raw if pins.get(content_key(p)) == ds],
    }


def progress(db, pid):
    key = content_key(pid)
    result = snapshot(db)["dashboard"]["problems"][str(pid)]
    with closing(runtime.connect(db)) as con:
        result["history"] = [
            dict(r)
            for r in con.execute(
                """
          SELECT action, studied_at, COALESCE((SELECT group_concat(language, ', ') FROM supplement_review_languages l
                      WHERE e.content_id=l.content_id AND e.study_date=l.study_date AND e.action='complete'),'') AS language
            FROM content_events e WHERE content_id=?
          UNION ALL SELECT status, submitted_at, language FROM hot200_learning_submissions WHERE content_id=?
          ORDER BY studied_at DESC LIMIT 50""",
                (key, key),
            )
        ]
    return result


def learning_fact(db, pid):
    from interview_forge.services.native_acm import submission_summary

    record = progress(db, pid)
    fact = {key: record.get(key) for key in (
        "rounds", "submits", "ac_submits", "mark", "last_submitted_at", "last_activity_at", "next_due",
    )}
    return dict(fact, problem_id=pid, title=catalog()[pid]["title"], catalog=MODULE,
                native_acm=submission_summary(db, f"hot200-{pid}"))


def plan(db, randomize):
    boot = snapshot(db)
    items = list(catalog().values())
    if randomize:
        random.shuffle(items)
    state = boot["dashboard"]

    def reason(p):
        pid, k = p["id"], str(p["id"])
        if pid in boot["pinnedToday"]:
            return "pinned"
        if any(q["id"] == pid for q in boot["daily"]["problems"]):
            return "due"
        if state["marks"].get(k) == "weak" or k in state["submissions"]["auto_weak"]:
            return "weak"
        return "new" if not state["problems"][k]["rounds"] else "low"

    order = ["pinned", "due", "weak", "new", "low"]
    items.sort(key=lambda p: order.index(reason(p)))
    return {
        "items": [
            dict(p, reason=reason(p)) for p in items[: max(3, len(boot["pinnedToday"]))]
        ]
    }


def mock(db, params):
    boot = snapshot(db)
    day = date.fromisoformat(boot["daily"]["today"])
    scope = params.get("scope", "all")
    lang = params.get("language", "")
    cutoff = (
        day - timedelta(days=max(1, min(30, int(params.get("days", 3)))) - 1)
    ).isoformat()
    pool = []
    for p in catalog().values():
        info = boot["dashboard"]["problems"][str(p["id"])]
        if any(params.get(k) and params[k] != p[k] for k in ("category", "difficulty")):
            continue
        if scope == "recent" and (info["last_activity_at"] or "")[:10] < cutoff:
            continue
        if scope == "stale" and not (
            info["next_due"] and info["next_due"] < day.isoformat()
        ):
            continue
        if scope == "unseen" and (
            info["by_language"].get(lang, {}).get("rounds")
            if lang
            else info["last_activity_at"]
        ):
            continue
        pool.append(p)
    n = min(len(pool), max(1, min(int(params.get("count", 5)), 20)))
    if not n and params.get("preview") != "1":
        raise ValueError("没有匹配的题目")
    return {
        "scope_pool": len(pool), "count": n, "problems": random.sample(pool, n), "scope": scope
    }


def export(db, kind):
    boot = snapshot(db)
    dash = boot["dashboard"]
    weak = [
        p
        for p in catalog().values()
        if dash["marks"].get(str(p["id"])) == "weak"
        or str(p["id"]) in dash["submissions"]["auto_weak"]
    ]
    if kind == "records":
        with closing(runtime.connect(db)) as con:
            con.execute("BEGIN")
            boot["content_events"] = [
                dict(r)
                for r in con.execute(
                    "SELECT * FROM content_events WHERE module_id=? ORDER BY studied_at",
                    (MODULE,),
                )
            ]
            boot["submissions"] = [
                dict(r)
                for r in con.execute(
                    "SELECT * FROM supplement_submissions ORDER BY submitted_at"
                )
            ]
            boot["review_languages"] = [
                dict(r)
                for r in con.execute(
                    "SELECT * FROM supplement_review_languages ORDER BY study_date"
                )
            ]
            boot["reviews"] = [
                dict(r)
                for r in con.execute(
                    "SELECT * FROM review_logs WHERE target_type='content' AND target_id LIKE 'hot200-extra:%' ORDER BY reviewed_at"
                )
            ]
        return json.dumps(boot, ensure_ascii=False, indent=2), "json"
    if kind == "weak":
        return "\n".join(
            f"{p['id']}. {p['title']}" for p in weak
        ) or "没有薄弱题", "txt"
    if kind == "anki":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            ["题号", "题名", "核心方法", "时间/空间复杂度", "题解链接", "力扣链接"]
        )
        for p in catalog().values():
            source = (ROOT / f"books/hot200-extra/solutions/{p['id']}.md").read_text(
                encoding="utf-8-sig"
            )

            def para(heading, source=source):
                match = re.search(rf"^### {heading}\s*\n+([^\n]+)", source, re.MULTILINE)
                return match[1].strip() if match else ""

            w.writerow(
                [
                    p["id"],
                    p["title"],
                    para("思路"),
                    para("复杂度"),
                    p["note"],
                    f"https://leetcode.cn/problems/{p['slug']}/",
                ]
            )
        return "\ufeff" + buf.getvalue(), "csv"
    if kind == "weekly":
        return "\n".join(
            f"{r['date']}：看 {r['viewed']} 题，完成 {r['rounds']} 轮，提交 {r['submits']} 次"
            for r in dash["activity"][-7:]
        ), "txt"
    raise ValueError("不支持的导出类型")
