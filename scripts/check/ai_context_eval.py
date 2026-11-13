"""Compare context projections against any checkout using the same synthetic input."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sys
import tempfile


def evaluate(source_root: Path) -> dict:
    # Choose the implementation before importing project modules so a baseline
    # checkout can use the exact same fixture as the candidate in a fresh process.
    sys.path.insert(0, str(source_root.resolve()))
    from interview_forge.ai.chat.context_builder import ContextBuilder
    from interview_forge.ai.chat.page_context import PageContext
    from interview_forge.ai.chat.token_budget import ChatTokenBudget
    from interview_forge.core.runtime import server_runtime

    clause = "必须先让我自己回答，再给提示。"
    stamp = "2026-11-14T12:12:12+08:00"
    initial = [
        ("user", "准备算法面试。" * 24 + clause + "复习动态规划。" * 28),
        ("assistant", "下次继续。" * 15), ("user", "继续"), ("assistant", "明白"),
    ]
    insert = "INSERT INTO chat_messages(session_id,role,content,created_at) VALUES('abc',?,?,?)"
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / "fixture.db"
        with closing(server_runtime.connect(db)) as conn:
            conn.execute("INSERT INTO chat_sessions VALUES('abc','测试',?,?)", (stamp, stamp))
            conn.executemany(insert, [(role, text, stamp) for role, text in initial])
            conn.commit()
        builder = ContextBuilder(budget=ChatTokenBudget(recent_tokens=45))
        small = builder.build(user_db=db, session_id="abc", current_message="回顾之前的要求")

        with closing(server_runtime.connect(db)) as conn:
            conn.executemany(insert, [(role, "线程池 " + "消息" * 220 + str(i), stamp)
                                      for i in range(256) for role in ("user", "assistant")])
            conn.commit()
        builder.build(user_db=db, session_id="abc", current_message="请回顾之前的线程池")
        stats = builder.last_build
        with closing(server_runtime.connect(db)) as conn:
            stored = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]

    selection = "开头" + "背景" * 1600 + "不能提前公布答案"
    page = PageContext.from_payload({"path": "/example", "title": "页面", "selected_text": selection})
    return {
        "saved_constraint_in_summary": any(clause in message["content"] for message in small),
        "source_message_id": any("#1 " in message["content"] for message in small),
        "loaded_message_rows": stats["history_message_count"] - stats.get("history_archived_count", 0),
        "stored_messages": stored,
        "selection_tail_retained": page.selected_text.endswith("不能提前公布答案"),
        "estimated_prompt_tokens": stats["estimated_prompt_tokens"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(evaluate(args.source_root), ensure_ascii=False, indent=2))
