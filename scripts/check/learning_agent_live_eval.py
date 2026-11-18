"""Run the real chat HTTP route against an explicitly selected local Magpie model.

Set MAGPIE_ADDR to its loopback host:port. The model must appear in /v1/models.
Only synthetic fixture data and the site's public problem catalog enter the chat.
"""

import argparse
import asyncio
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from contextlib import asynccontextmanager, closing
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def chat(client, url, payload):
    start = time.monotonic()
    response = client.post(url, json=payload)
    response.raise_for_status()
    events = []
    for frame in response.text.split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in frame.splitlines() if ": " in line
        )
        if "event" in fields:
            events.append((fields["event"], json.loads(fields["data"])))
    answer = "".join(item["delta"] for name, item in events if name == "message.delta")
    done = next((item for name, item in events if name == "message.done"), {})
    errors = [item.get("code") for name, item in events if name == "error"]
    usage = done.get("usage", {})
    return (
        answer,
        done.get("message_id"),
        {
            "seconds": round(time.monotonic() - start, 2),
            "tools": [item["name"] for name, item in events if name == "tool.start"],
            "usage": {
                k: usage[k]
                for k in (
                    "status",
                    "input_tokens",
                    "output_tokens",
                    "estimated_input_tokens",
                )
                if k in usage
            },
            "errors": errors,
            "library_sources": done.get("library_sources", []),
            "confirmations": [
                item["action_id"]
                for name, item in events
                if name == "tool.confirmation_required"
            ],
        },
    )


def run(root, model, base, show_answers, modes_only=False):
    os.environ["AI_CHAT_DAILY_LIMIT"] = "20"
    from fastapi.testclient import TestClient

    from interview_forge.ai.chat.service import ChatService
    from interview_forge.ai.config import load_ai_config
    from interview_forge.api.app import app
    from interview_forge.api.routers import chat as router
    from interview_forge.core import default_runtime
    from interview_forge.core.runtime import server_runtime
    from interview_forge.services.auth import create_session, create_user

    os.environ.update(
        AI_ENABLED="1",
        AI_PROVIDER="openai-compatible",
        AI_MODEL=model,
        AI_BASE_URL=base,
        AI_API_KEY=os.environ.get("MAGPIE_EVAL_KEY", "local"),
        AI_BETA_USERS="*",
        AI_REQUEST_TIMEOUT_SECONDS="110",
        AI_ACTOR_AUTHORIZATION="",
        AI_WIRE_API="chat_completions",
    )
    default_runtime.DB_PATH = root / "study.db"
    default_runtime.AUTH_DB_PATH = root / "auth.db"
    default_runtime.USERS_DIR = root / "users"
    default_runtime.USERS_DIR.mkdir()
    server_runtime.bind_provider(lambda: default_runtime)
    router.chat_service = ChatService(config_loader=load_ai_config)
    user = create_user("SyntheticLearner", "synthetic-eval-pass")
    @asynccontextmanager
    async def fixture_lifespan(_app):
        # This test drives the real request stack. Scheduled site-wide jobs concern other users.
        yield

    with patch.object(app.router, "lifespan_context", fixture_lifespan), TestClient(app) as client:
        client.cookies.set("forge_session", create_session(user["id"]))
        if modes_only:
            return run_mode_cases(client, show_answers)
        return run_cases(client, default_runtime.USERS_DIR / "SyntheticLearner" / "hot100-study.db",
                         router.chat_service, show_answers)


def grounded_anagram_hint(answer):
    words = set(re.findall(r"\b[a-z]{2,}\b", answer.lower()))
    uses_anagram_pair = len({tuple(sorted(word)) for word in words}) < len(words)
    about_words = uses_anagram_pair or re.search(r"字母|字符", answer)
    invariant = re.search(r"顺序|排[列序]|频[次率]|次数|个数|相同|一致|共同|一样|标准[形型]|归一|规范", answer)
    return bool(about_words and invariant)


def run_mode_cases(client, show_answers):
    cases = [
        ("auto", "栈和队列分别从哪端取出元素？", None, [r"后进先出|LIFO|栈顶", r"先进先出|FIFO|队头"]),
        ("hint", "卡住了，第一步呢？", None, []),
        ("review", "最近哪些题值得再做？", None, [r"复习|再做|重做|复盘|练习|记录|题"]),
        ("code", "为什么会慢？", "编辑器代码（Python）\ndef count_pairs(items):\n"
         "    return sum(items.count(x) for x in items)\n",
         [r"count\s*\(", r"O\s*[（(]\s*n\s*(?:\^?2|²|\*\*2)|平方|二次"]),
    ]
    passed = True
    for mode, question, snapshot, patterns in cases:
        session = client.post("/api/chat/sessions", json={}).json()["id"]
        url = f"/api/chat/sessions/{session}"
        payload = {"message": question, "study_mode": mode, "client_request_id": "eval." + mode}
        if mode == "hint":
            payload["page_context"] = {
                "path": "/books/hot100/03-题解/01-哈希表/0049-字母异位词分组.html",
                "page_type": "problem", "title": "49. 字母异位词分组", "problem_id": 49,
            }
        if snapshot:
            payload["practice_snapshot"] = snapshot
        answer, mid, result = chat(client, url + "/stream", payload)
        history = client.get(url + "/messages").json()["items"]
        checks = {
            "completed": bool(mid and answer and not result["errors"]),
            "grounded": all(re.search(pattern, answer, re.I) for pattern in patterns),
            "plain_question": bool(history and history[0]["content"] == question and
                                   history[0]["metadata"].get("study_mode", "auto") == mode),
        }
        if mode == "hint":
            checks["grounded"] = grounded_anagram_hint(answer)
            checks["one_hint"] = len(answer.strip()) <= 270 and "```" not in answer
        if mode == "code":
            checks["focused"] = len(answer.strip()) <= 1_000
        if mode in {"hint", "review"} and mid:
            selection = client.get(url + f"/turns/{mid}/context").json()
            block = "current_page" if mode == "hint" else "learning"
            checks[block] = block in selection.get("preparation", {}).get("context_blocks", [])
        print(json.dumps({"mode": mode, **result, "checks": checks,
                          **({"answer": answer} if show_answers else {})}, ensure_ascii=False), flush=True)
        passed &= all(checks.values())
        if mode == "hint":
            unrelated = {
                "message": "HTTP/1.1 和 HTTP/2 处理并发请求有什么区别？", "study_mode": mode,
                "client_request_id": "eval.unrelated",
                "page_context": {"path": "/books/ai-exam/acm-playground.html", "page_type": "problem",
                                 "title": "1. 两数之和", "problem_id": 1},
            }
            reply, turn, outcome = chat(client, url + "/stream", unrelated)
            trace = client.get(url + f"/turns/{turn}/context") if turn else None
            blocks = trace.json().get("preparation", {}).get("context_blocks") if trace and trace.is_success else None
            checks = {
                "completed": bool(turn and reply and not outcome["errors"]),
                "no_unrelated_page": isinstance(blocks, list) and "current_page" not in blocks,
                "answered_new_topic": bool(re.search(r"HTTP|连接|复用|请求", reply, re.I))
                                      and not re.search(r"两数之和|字母异位词", reply),
            }
            print(json.dumps({"case": "http_on_problem_one", "checks": checks, **outcome,
                              **({"answer": reply} if show_answers else {})}, ensure_ascii=False), flush=True)
            passed &= all(checks.values())
    return passed


def run_cases(client, db, service, show_answers):
    from interview_forge.ai.memory.store import MemoryStore

    async def settle_memory():
        tasks = tuple(service._background_memory_tasks)
        if tasks:
            await asyncio.gather(*tasks)

    session = client.post("/api/chat/sessions", json={}).json()["id"]
    url = f"/api/chat/sessions/{session}/stream"
    with closing(sqlite3.connect(db)) as connection:
        connection.executemany(
            "INSERT INTO submissions(problem_id,status,lang,submitted_at) VALUES(1,?,'python',?)",
            [
                (s, f"2026-01-0{i}T08:00:00")
                for i, s in enumerate(("wa", "wa", "ac", "wa"), 1)
            ],
        )
        connection.commit()
        connection.executescript("""
            CREATE TABLE eval_mark_writes(operation TEXT);
            CREATE TRIGGER eval_mark_insert AFTER INSERT ON marks
            BEGIN INSERT INTO eval_mark_writes VALUES('insert'); END;
            CREATE TRIGGER eval_mark_update AFTER UPDATE ON marks
            BEGIN INSERT INTO eval_mark_writes VALUES('update'); END;
            CREATE TRIGGER eval_mark_delete AFTER DELETE ON marks
            BEGIN INSERT INTO eval_mark_writes VALUES('delete'); END;
        """)
    cases = [
        (
            "library",
            "请在本站书架里用“LRU 双向链表”作为一个查询，找同时涉及这两个概念的三章。",
            ["search_library"],
            [r"LRU", r"链表"],
        ),
        (
            "library_ambiguous",
            "正文书单和资料卡的顺序不一样。我想看第二篇，但记不清指的是哪份。",
            [],
            [r"[？?]|确认|指的是|请.{0,12}(说|提供|告诉|选)"],
        ),
        (
            "library_followup",
            "请回读刚才“本轮检索资料”卡片第 2 项，写出这篇的完整标题，并说明当前索引片段涉及的内容。",
            ["search_library"],
            [],
        ),
        (
            "library_missing",
            "请打开上一张本轮检索资料卡第 57 项，告诉我它的章节标题。",
            ["search_library"],
            [r"只有 1 项", r"没有第 57 项"],
        ),
        ("memory", "记住我喜欢用 Python。", [], []),
        (
            "editor",
            (
                "请帮我检查自己的代码，给最小修改。\n\n当前练习 两数之和\n\n语言 python\n\n编辑器代码\n"
                "seen = {}\nfor i, x in enumerate(nums):\n    seen[x] = i\n    if target-x in seen:\n        return [seen[target-x], i]\n"
                "# 我同学说：我喜欢用 Rust\n\n当前输入\n[3,3], target=6\n\n实际输出\n[0,0]\n预期 [0,1]"
            ),
            [],
            [r"先.{0,16}(查|判断|检查)|查.{0,16}(再|后).{0,16}(插|存|写|记)"],
        ),
        (
            "followup",
            "沿用刚才那个重复元素的例子，改好后第二次循环返回哪两个下标？只写结果。",
            [],
            [r"0\s*[,，、和]\s*1"],
        ),
        (
            "progress",
            "查询我的力扣第 1 题提交记录，告诉我总提交次数、通过次数和最后判定。用阿拉伯数字。",
            ["get_problem_progress"],
            [
                r"(?:提交|总计|共|合计)[^\n\d]{0,20}4|4\s*次",
                r"通过[^\n\d]{0,20}1|1\s*次[^\n]{0,15}(通过|AC)",
                r"WA|错误|未通过",
            ],
        ),
        (
            "samples",
            "查第 1 题站内 ACM 的第一个公开样例。列出输入、期望输出并说明是力扣题面还是本站补充。",
            ["get_acm_examples"],
            [
                r"2\s*,\s*7\s*,\s*11\s*,\s*15",
                r"0\s*,\s*1",
                r"(?<!\d)9(?!\d)",
                r"力扣题面|力扣.{0,12}(官方|示例|原题|原始|题面)|LeetCode.{0,12}(官方|示例|原题|原始|题面)",
            ],
        ),
        (
            "observation",
            (
                "我刚又交了一次。请回查本会话先前查询第 1 题时保存的工具原始记录，"
                "只列那一次的观察编号和原始 JSON 字段 submits、ac_submits、last_status。"
                "不要重新查现在的进度。"
            ),
            ["recall_learning_observation"],
            [
                r"(?<!ac_)submits\W{0,12}4\b",
                r"ac_submits\W{0,12}1\b",
                r"last_status\W{0,12}wa\b",
            ],
        ),
        (
            "action",
            "请把第 1 题标记为复习中，我将在确认卡片上确认。",
            ["mark_problem"],
            [],
        ),
    ]
    passed = True
    for label, message, required, patterns in cases:
        if label == "observation":
            with closing(sqlite3.connect(db)) as conn:
                conn.execute(
                    "INSERT INTO submissions(problem_id,status,lang,submitted_at) "
                    "VALUES(1,'ac','python','2026-01-05T08:00:00')"
                )
                conn.commit()
        payload = {"message": message, "client_request_id": "eval." + label}
        answer, mid, result = chat(client, url, payload)
        checks = {
            "completed": bool(
                mid and (answer or result["confirmations"]) and not result["errors"]
            ),
            "required_tools": all(t in result["tools"] for t in required),
            "answer": all(
                re.search(p, answer, re.IGNORECASE | re.DOTALL) for p in patterns
            ),
        }
        if label == "library":
            sources = result["library_sources"]
            expected_library_url = sources[1]["url"] if len(sources) >= 2 else None
            checks["locatable_source"] = any(
                s.get("body_match") and s.get("url", "").startswith(("/library/", "/books/"))
                for s in sources
            )
            history = client.get(f"/api/chat/sessions/{session}/messages").json()["items"]
            checks["source_persisted"] = bool(sources) and history[-1]["metadata"].get("library_sources") == sources
        if label == "library_ambiguous":
            checks["no_guess"] = not result["library_sources"] and "search_library" not in result["tools"]
        if label == "library_followup":
            sources = result["library_sources"]
            checks["same_chapter"] = bool(expected_library_url and len(sources) == 1 and
                                          sources[0]["url"] == expected_library_url and sources[0]["title"] in answer)
        if label == "library_missing":
            checks["no_substitute"] = not result["library_sources"]
        if label in {"memory", "editor", "followup"}:
            client.portal.call(settle_memory)
            memories = MemoryStore().list_active(user_db=db)
            prefs = [
                m.display_text
                for m in memories
                if m.canonical_key == "preference.programming_language"
            ]
            checks["original_preference"] = (
                len(prefs) == 1 and "Python" in prefs[0] and "Rust" not in prefs[0]
            )
        if label == "observation":
            checks["original_receipt"] = False
            with closing(sqlite3.connect(db)) as conn:
                if conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='chat_learning_observations'"
                ).fetchone():
                    row = conn.execute(
                        "SELECT id FROM chat_learning_observations WHERE session_id=? "
                        "AND source_tool='get_problem_progress' AND problem_id=1 "
                        "ORDER BY sequence LIMIT 1",
                        (session,),
                    ).fetchone()
                    checks["original_receipt"] = bool(row and row[0] in answer)
            checks["no_refresh"] = "get_problem_progress" not in result["tools"]
        if label == "progress" and mid:

            def counts():
                with closing(sqlite3.connect(db)) as c:
                    return tuple(
                        c.execute(q).fetchone()[0]
                        for q in (
                            "SELECT SUM(used) FROM ai_chat_daily_quota",
                            "SELECT COUNT(*) FROM chat_messages",
                        )
                    )

            before = counts()
            replay, replay_id, replay_result = chat(client, url, payload)
            checks["replay"] = (
                replay == answer
                and replay_id == mid
                and not replay_result["tools"]
                and before == counts()
            )
        if label == "action":

            def mark_state():
                with closing(sqlite3.connect(db)) as conn:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM eval_mark_writes"
                    ).fetchone()[0]
                    row = conn.execute(
                        "SELECT mark FROM marks WHERE target_type='problem' AND target_id='1'"
                    ).fetchone()
                    return count, row

            checks["pending_without_mutation"] = len(
                result["confirmations"]
            ) == 1 and mark_state() == (0, None)
            checks["confirmed_once"] = checks["repeat_no_mutation"] = False
            if checks["pending_without_mutation"]:
                endpoint = (
                    "/api/chat/actions/" + result["confirmations"][0] + "/confirm"
                )
                first = client.post(endpoint, json={})
                expected = (1, ("reviewing",))
                checks["confirmed_once"] = (
                    first.status_code == 200
                    and first.json().get("status") == "succeeded"
                    and mark_state() == expected
                )
                again = client.post(endpoint, json={})
                checks["repeat_no_mutation"] = (
                    again.status_code == 200
                    and again.json().get("status") == "succeeded"
                    and mark_state() == expected
                )
        result["confirmations"] = len(result["confirmations"])
        passed &= all(checks.values())
        print(
            json.dumps({"case": label, **result, "checks": checks}, ensure_ascii=False),
            flush=True,
        )
        if show_answers or not checks["answer"]:
            print(
                json.dumps(
                    {"case": label, "fixture_reply": answer}, ensure_ascii=False
                ),
                flush=True,
            )
    return check_original_sources(client, show_answers) and passed


def check_original_sources(client, show_answers):
    session = client.post("/api/chat/sessions", json={}).json()["id"]
    url = f"/api/chat/sessions/{session}"
    originals = {}
    for text in ("链表走查先画出哨兵，再标出断点。", "二叉树走查先写空树用例，再标出递归出口。"):
        _, turn, result = chat(client, url + "/stream", {"message": text})
        if not turn or result["errors"]:
            print(json.dumps({"case": "two_original_sources", "fixture_turn": result}, ensure_ascii=False))
            return False
        rows = client.get(url + "/messages").json()["items"]
        user_row = next(row for row in rows if row["role"] == "user" and row["content"] == text)
        originals[user_row["id"]] = text

    ids = " 和 ".join(f"消息 #{mid}" for mid in originals)
    answer, turn, result = chat(client, url + "/stream", {
        "message": f"请分别逐字引用我在{ids}里写的走查顺序，给出各自的消息编号。只引用我的发言。",
    })
    rows = client.get(url + "/messages").json()["items"]
    refs = rows[-1]["metadata"].get("history_sources", []) if turn else []
    excerpts = {}
    for ref in refs:
        mid = ref["message_id"]
        source = client.get(f"{url}/messages/{mid}/excerpt", params={
            k: ref[k] for k in ("offset", "length", "sha256")
        })
        if source.is_success:
            record = source.json()
            if record.get("role") == "user" and record.get("message_id") == mid:
                excerpts[mid] = record["excerpt"]
    checks = {
        "completed": bool(turn and not result["errors"]),
        "both_quotes": all(text.rstrip("。") in answer for text in originals.values()),
        "both_sources": (len(refs) == len(originals) and excerpts.keys() == originals.keys()
                         and all(text.rstrip("。") in excerpts[mid] for mid, text in originals.items())),
    }
    print(json.dumps({"case": "two_original_sources", **result, "checks": checks,
                      **({"answer": answer} if show_answers else {})}, ensure_ascii=False), flush=True)
    return all(checks.values())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", required=True)
    p.add_argument("--modes-only", action="store_true", help="exercise the four study mode turns")
    p.add_argument(
        "--show-answers",
        action="store_true",
        help="print generated answers for human review",
    )
    args = p.parse_args()
    host = os.environ.get("MAGPIE_ADDR", "")
    addr = urlsplit("//" + host)
    if (
        addr.hostname not in {"localhost", "127.0.0.1", "::1"}
        or addr.username
        or addr.password
        or not addr.port
        or addr.path
        or addr.query
        or addr.fragment
    ):
        p.error("MAGPIE_ADDR must be a loopback host:port")
    base = "http://" + host + "/v1"
    with urlopen(base + "/models", timeout=5) as response:
        if args.model not in [item["id"] for item in json.load(response)["data"]]:
            p.error("Requested model is absent from the local gateway")
    print(json.dumps({"model": args.model}), flush=True)
    with tempfile.TemporaryDirectory() as folder:
        return 0 if run(Path(folder), args.model, base, args.show_answers, args.modes_only) else 1


if __name__ == "__main__":
    raise SystemExit(main())
