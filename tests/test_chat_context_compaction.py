from contextlib import closing
import json

from fastapi.testclient import TestClient

from interview_forge.ai.chat.context_builder import ContextBuilder, HISTORY_FETCH_LIMIT
from interview_forge.ai.chat.learning_context import learning_projection_block
from interview_forge.ai.chat.page_context import PageContext, PageContextProvider
from interview_forge.ai.chat.token_budget import ChatTokenBudget, DEFAULT_TOKEN_ESTIMATOR
from interview_forge.api.app import app
from interview_forge.core.runtime import server_runtime


def seed(db, messages):
    timestamp = "2026-11-14T09:30:00+08:00"
    with closing(server_runtime.connect(db)) as conn:
        conn.execute("INSERT INTO chat_sessions VALUES('thread','session',?,?)", (timestamp, timestamp))
        conn.executemany(
            "INSERT INTO chat_messages(session_id,role,content,created_at) VALUES('thread',?,?,?)",
            [(role, content, timestamp) for role, content in messages],
        )
        conn.commit()


def test_window_recall_boundary_and_raw_history(tmp_path):
    db = tmp_path / "learning.db"
    messages = [(role, f"TCP 学习计划 step {i}") for i in range(260) for role in ("user", "assistant")]
    seed(db, messages + [("user", "未来消息不能被较早的请求看到")])
    builder = ContextBuilder()
    projected = builder.build(user_db=db, session_id="thread", current_message="回顾之前的 TCP 计划",
                              current_message_id=len(messages)+1)
    stats = builder.last_build
    assert stats["history_archived_count"] == len(messages) - HISTORY_FETCH_LIMIT
    assert stats["history_message_count"] == len(messages)
    assert "recall_chat_history" in str(projected)
    assert "未来消息" not in str(projected)
    with closing(server_runtime.connect(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == len(messages)+1
        # An independently selected tail must not replace an all-session checkpoint.
        assert conn.execute("SELECT COUNT(*) FROM chat_session_summaries").fetchone()[0] == 0


def test_constraints_keep_source_and_checkpoints_are_monotonic(tmp_path):
    db = tmp_path / "learning.db"
    old = "复习时我会先给你一些背景。" * 10 + "必须先让我自己回答，再给提示。" + "其余练习会在稍后讨论。" * 10
    seed(db, [("user", old), ("assistant", "了解，稍后继续。" * 15), ("user","继续"), ("assistant","好")])
    builder = ContextBuilder(budget=ChatTokenBudget(recent_tokens=45))
    view = builder.build(session_id="thread", user_db=db, current_message="回顾之前的要求")
    assert "必须先让我自己回答，再给提示。" in str(view)
    assert "#1 " in str(view)
    builder._save_summary(user_db=db, session_id="thread", summary="newer", through_message_id=4)
    builder._save_summary(user_db=db, session_id="thread", summary="stale", through_message_id=2)
    with closing(server_runtime.connect(db)) as conn:
        assert tuple(conn.execute("SELECT summary,through_message_id FROM chat_session_summaries").fetchone()) == ("newer",4)


def test_followup_keeps_source_of_oversized_latest_reply(tmp_path):
    db = tmp_path / "chat.db"
    messages = [(role, f"TCP 线索 {n} 的背景。" * 10)
                for n in range(8) for role in ("user", "assistant")]
    seed(db, [*messages, ("user", "TCP 例题呢"), ("assistant", "TCP 回答。" * 200 + "务必保留最终答案。")])
    builder = ContextBuilder(budget=ChatTokenBudget(recent_tokens=20, summary_tokens=195))
    view = builder.build(session_id="thread", user_db=db, current_message="请继续解释刚才最后给我的答案")
    assert builder.last_build["recent_message_count"] == 0
    assert "#18 结论/建议" in str(view) and "务必保留最终答案。" in str(view)
    assert "#17 目标/问题" in str(view)
    assert builder.last_build["summary_through_message_id"] < 18


def test_explicit_recall_keeps_archived_checkpoint_without_mixing_other_topics(tmp_path):
    db = tmp_path / "chat.db"
    seed(db, [(role, f"TCP 例题 {n}")
              for n in range(HISTORY_FETCH_LIMIT) for role in ("user", "assistant")])
    builder = ContextBuilder()
    builder._save_summary(user_db=db, session_id="thread", summary="#1 目标/问题：ORBIT-V6 约定", through_message_id=1)
    def view(query):
        return str(builder.build(session_id="thread", user_db=db, current_message=query))
    assert "ORBIT-V6" in view("回顾之前的约定")
    assert "ORBIT-V6" not in view("换个话题，讲一下排序")


def test_json_and_selection_remain_well_formed_under_pressure():
    fact = {"title": "线程池"*180, "overdue": True}
    data = {"data_quality":{"status":"partial"}, "task":"today_plan", "selected_facts":[fact]*3}
    block = learning_projection_block(data)
    short = block.fit(130, DEFAULT_TOKEN_ESTIMATOR)
    packed = json.loads(short.split("Learning Context: ")[1])
    assert packed["data_quality"] == data["data_quality"]
    assert packed["coverage"] and "selected_facts" not in packed
    assert block.fit(4, DEFAULT_TOKEN_ESTIMATOR) == ""
    page = PageContext.from_payload({"path":"/x","title":"并发","selected_text":"开头"+"前"*4000+"不能提前公布答案"})
    assert page.selected_text.endswith("不能提前公布答案")
    block = PageContextProvider().build(page)
    assert block.fit(350, DEFAULT_TOKEN_ESTIMATOR).endswith("不能提前公布答案")


def test_context_inspector_owner_boundary_and_field_filter(tmp_path, monkeypatch):
    db = tmp_path / "alice.db"
    seed(db, [])
    from interview_forge.api import support
    from interview_forge.api.routers import chat
    client = TestClient(app)
    url = "/api/chat/sessions/thread/turns/turn42/context"
    assert client.get(url).status_code == 401
    monkeypatch.setattr(support, "current_user", lambda request: {"username":"alice"})
    monkeypatch.setattr(chat, "user_db", lambda user: db)
    with closing(server_runtime.connect(db)) as conn:
        for kind, name, idx, values, usage in [
            ("context","context_selection",None,{"context_blocks":["learning","DO_NOT_PUBLISH"],"history_selected_count":1},None),
            ("context","request_admission",1,{"original_prompt_tokens":900,"admitted_prompt_tokens":550,"tool_result_tokens_saved":350},None),
            ("llm","model_round",1,{},510),
        ]:
            conn.execute("""INSERT INTO ai_trace_events(trace_id,session_id,event_type,name,status,round_index,
                         started_at,metadata_json,input_tokens) VALUES('turn42','thread',?,?,'success',?,'2026-11-14',?,?)""",
                         (kind,name,idx,json.dumps({**values,"prompt":"DO_NOT_PUBLISH"}),usage))
        conn.commit()
    resp = client.get(url)
    assert resp.status_code == 200, resp.text
    assert "DO_NOT_PUBLISH" not in resp.text
    rounds = resp.json()["rounds"]
    assert rounds == [{"round":1,"admitted":True,"original_prompt_tokens":900,"admitted_prompt_tokens":550,
                       "provider_input_tokens":510,"tool_result_tokens_saved":350}]
    assert client.get(url.replace("thread/", "elsewhere/")).status_code == 404
    monkeypatch.setattr(chat,"user_db",lambda user:tmp_path/"bob.db")
    assert client.get(url).status_code == 404
    client.close()

def test_active_session_conflict_precedes_daily_charge(tmp_path, monkeypatch):
    from interview_forge.ai.chat.service import claim_chat_session, release_chat_session
    from interview_forge.api import support
    from interview_forge.api.routers import chat
    from unittest.mock import Mock

    db = tmp_path / "owner.db"
    seed(db, [])
    monkeypatch.setattr(support, "current_user", lambda request: {"username":"alice","role":"user"})
    monkeypatch.setattr(chat, "user_db", lambda user: db)
    monkeypatch.setattr(chat.chat_service, "preflight", lambda: None)
    charge = Mock()
    monkeypatch.setattr(chat, "consume_chat_quota", charge)
    assert claim_chat_session(db, "thread")
    try:
        with closing(TestClient(app)) as client:
            resp = client.post("/api/chat/sessions/thread/stream",json={"message":"继续"})
        assert resp.status_code == 409 and resp.json()["error_category"] == "chat_in_progress"
        charge.assert_not_called()
    finally:
        release_chat_session(db, "thread")


def test_local_workers_exclude_only_same_owner_and_session(tmp_path, monkeypatch):
    import subprocess
    import sys
    from interview_forge.ai.chat.service import claim_chat_session, release_chat_session

    monkeypatch.setenv("IF_SHARED_RUNTIME", "1")
    monkeypatch.setenv("IF_RUNTIME_DIR",str(tmp_path/'locks'))
    db = tmp_path / "account.db"
    assert claim_chat_session(db, "thread")
    command = [sys.executable, "-c", """
from pathlib import Path
import sys
from interview_forge.ai.chat.service import claim_chat_session,release_chat_session
db=Path(sys.argv[1])
if claim_chat_session(db,'thread'):
    release_chat_session(db,'thread')
    print('available')
else:
    print('busy')
""", str(db)]
    try:
        assert subprocess.check_output(command,text=True).strip() == "busy"
        assert claim_chat_session(db,"another")
        release_chat_session(db,"another")
        other = tmp_path/"other.db"
        assert claim_chat_session(other,"thread")
        release_chat_session(other,"thread")
    finally:
        release_chat_session(db,"thread")
    assert subprocess.check_output(command,text=True).strip() == "available"
