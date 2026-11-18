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


def test_text_quoted_from_another_message_cannot_select_a_second_range():
    items = [dict(message_id=4, offset=0, excerpt="先写测试"),
             dict(message_id=4, offset=25, excerpt="先画图"),
             dict(message_id=9, offset=0, excerpt="先画图")]
    refs = cited_history_sources("#4「先写测试」\n#9「先画图」", items)
    assert [(ref['message_id'], ref['offset']) for ref in refs] == [(4, 0), (9, 0)]


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


def test_same_message_id_does_not_attach_unrelated_excerpt():
    visible = [{"message_id": 4, "offset": 0, "excerpt": "当时讨论了二叉树遍历"},
               {"message_id": 4, "offset": 400, "excerpt": "原先约定先写出边界条件"}]
    refs = cited_history_sources("消息 #4 里写着「先写出边界条件」。", visible)
    assert [ref["offset"] for ref in refs] == [400]
    assert not cited_history_sources("详见消息 #4。", visible)


def test_multiple_sources_in_one_sentence_keep_their_own_quotes():
    items = [dict(message_id=4, offset=0, excerpt="先写测试"),
             dict(message_id=4, offset=25, excerpt="先画图"),
             dict(message_id=9, offset=0, excerpt="先提问题")]
    for answer in ("消息 #4「先写测试」，消息 #9「先提问题」。",
                   "「先写测试」（消息 #4），「先提问题」（消息 #9）。"):
        refs = cited_history_sources(answer, items)
        assert [(r["message_id"], r["offset"]) for r in refs] == [(4, 0), (9, 0)]


def test_single_excerpt_cannot_substantiate_an_incorrect_quote_or_an_id_inside_a_quote():
    items = [dict(message_id=4, offset=0, excerpt="请翻看消息 #9。"),
             dict(message_id=9, offset=0, excerpt="先写测试")]
    for answer in ("消息 #9 写的是「直接给代码」。", "消息 #9 写的是‘直接给代码’。"):
        assert not cited_history_sources(answer, items)
    refs = cited_history_sources("消息 #4 写的是「请翻看消息 #9。」", items)
    assert [r["message_id"] for r in refs] == [4]
    refs = cited_history_sources("上次刷的是 LeetCode #4，参见消息 #9。", items)
    assert [r["message_id"] for r in refs] == [9]
    assert [r["message_id"] for r in cited_history_sources("详见消息 #9。", items)] == [9]


def test_a_quoted_label_elsewhere_is_not_a_claim_by_the_cited_message():
    items = [dict(message_id=4, offset=0, excerpt="待办"), dict(message_id=4, offset=12, excerpt="先写测试")]
    for answer in ("「待办」是个分类；消息 #4 的原话是「先写测试」。",
                   "「待办」是个分类。消息 #4 的原话是「先写测试」。",
                   "「待办」分类里消息 #4 的原话是「先写测试」。",
                   "「先写测试」（消息 #4）属于「待办」分类。",
                   "「待办」是个分类；当时的原话是「先写测试」。\n来源：消息 #4。",
                   "消息 #4 写道：\n「先写测试」。"):
        assert [r["offset"] for r in cited_history_sources(answer, items)] == [12]
    assert not cited_history_sources("「待办」是个分类；消息 #4 的原话是「已经做完」。", items)


def test_ambiguous_shared_citation_does_not_bind_quotes_to_individual_messages():
    items = [dict(message_id=4, offset=0, excerpt="先测试"), dict(message_id=9, offset=0, excerpt="先绘图")]
    assert not cited_history_sources("「先测试」和「先绘图」见消息 #4 和消息 #9。", items)
