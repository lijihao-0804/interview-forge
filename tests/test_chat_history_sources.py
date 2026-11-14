import asyncio
from contextlib import closing

from fastapi.testclient import TestClient

from interview_forge.ai.chat.history_sources import cited_history_sources
from interview_forge.ai.chat.service import ChatService
from interview_forge.ai.chat.tool_orchestrator import ToolOrchestrator
from interview_forge.ai.tools.contracts import ToolExecutionContext
from interview_forge.api import support
from interview_forge.api.app import app
from interview_forge.api.routers import chat
from interview_forge.core.runtime import server_runtime
from tests.test_ai_tool_orchestrator import FakeChunk, ScriptedModel, _collect


def test_cited_recall_links_open_scoped_source_and_survive_reload(tmp_path, monkeypatch):
    db = tmp_path / "alice.db"
    source = "🙂当时的原话是「先讲直觉，再画图」。"
    with closing(server_runtime.connect(db)) as connection:
        connection.execute("INSERT INTO chat_sessions VALUES ('thread','测试','2026-11-14','2026-11-14')")
        connection.execute("INSERT INTO chat_messages(session_id,role,content,created_at) VALUES ('thread','user',?,'2026-11-14')", (source,))
        connection.commit()
    engine = ToolOrchestrator()
    model = ScriptedModel([
        [FakeChunk(tool_calls=[{"id":"r","name":"recall_chat_history","args":{"message_id":1,"offset":1}}])],
        [FakeChunk("你的原话是「先讲直觉，再画图」。来源：消息 #1。")],
    ])
    asyncio.run(_collect(engine, model, ToolExecutionContext(db, "thread", "round", 2, "我之前说了什么？")))
    refs = engine.last_result.history_sources
    ref, = refs
    assert ref["message_id"] == 1 and ref["offset"] == 1
    assert "excerpt" not in ref
    result = ChatService._save_assistant_message(user_db=db, session_id="thread", content="见 #1",
                                                 stream_message_id="round", usage={}, history_sources=refs)
    assert result["history_sources"] == ChatService.list_messages(user_db=db, session_id="thread")[-1]["metadata"]["history_sources"]
    endpoint = "/api/chat/sessions/thread/messages/1/excerpt"
    params = {k: ref[k] for k in ("offset", "length", "sha256")}
    with closing(TestClient(app)) as client:
        assert client.get(endpoint, params=params).status_code == 401
        monkeypatch.setattr(support, "current_user", lambda request: {"username":"alice"})
        monkeypatch.setattr(chat, "user_db", lambda user: db)
        received = client.get(endpoint, params=params)
        assert received.status_code == 200 and received.json()["excerpt"] == source[1:]
        assert "no-store" in received.headers["Cache-Control"]
        assert client.get(endpoint.replace("thread", "other"), params=params).status_code == 404
        assert client.get(endpoint, params={**params,"offset":0}).status_code == 404
        monkeypatch.setattr(chat, "user_db", lambda user: tmp_path / "bob.db")
        assert client.get(endpoint, params=params).status_code == 404


def test_only_admitted_and_cited_ids_get_an_original_text_link():
    visible = [{"message_id": 1, "offset": 0, "excerpt": "第一条"},
               {"message_id": 11, "offset": 3, "excerpt": "第十一条"}]
    assert [item["message_id"] for item in cited_history_sources("见消息 #11 和捏造的 #25", visible)] == [11]
    assert not cited_history_sources("你的原话是某某。", visible)
    assert not cited_history_sources("来源：消息 #11", [])
