import asyncio
import hashlib
import json
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

from interview_forge.ai.token_counting import canonical_json, estimate_json_tokens
from interview_forge.ai.tools.builtins import observations as obs
from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolResult
from interview_forge.ai.tools.langchain_adapter import NormalizedToolCall
from interview_forge.ai.tools.registry import build_default_tool_registry, ToolRegistry
from interview_forge.ai.tools.runtime import ToolRuntime
from interview_forge.core.runtime import server_runtime
from interview_forge.services import native_acm


def context(db, session="a", mid=1):
    with closing(server_runtime.connect(db)) as conn, conn:
        conn.execute("INSERT OR IGNORE INTO chat_sessions VALUES (?, 'chat', 'now', 'now')", (session,))
        conn.execute("INSERT OR IGNORE INTO chat_messages(id,session_id,role,content,created_at) VALUES(?,?,'user','fixture','now')",
                     (mid, session))
    return ToolExecutionContext(db, session, f"turn-{mid}", mid, "")


def execute(runtime, ctx, name, **args):
    return asyncio.run(runtime.execute(call=NormalizedToolCall(uuid4().hex, name, args), context=ctx))


def test_cached_progress_is_immutable_and_owner_scoped(tmp_path):
    db = tmp_path / "alice.db"
    runtime = ToolRuntime(build_default_tool_registry())
    first = context(db)
    source = "get_problem_progress"
    original = execute(runtime, first, source, problem_id=1)
    assert original.status == "ok"
    data = dict(original.result.data)
    ref = data.pop("observation")["id"]
    cached = execute(runtime, first, source, problem_id=1)
    assert cached.status == "cache_hit" and cached.result.data["observation"]["id"] == ref
    native_acm.save_submission(db, "hot100-1", "python", "PRIVATE SOURCE", True)
    second = execute(runtime, context(db, mid=2), source, problem_id=1)
    assert second.result.data["problem"]["native_acm"]["attempts"] == 1
    later = context(db, mid=3)
    name = "recall_learning_observation"
    latest = execute(runtime, later, name, problem_id=1, source_tool=source).result.data
    assert latest["observation_id"] == second.result.data["observation"]["id"]
    assert latest["previous_observation_id"] == ref
    historic = execute(runtime, later, name, observation_id=ref).result.data
    assert json.loads(historic["excerpt"]) == data
    assert historic["sha256"] == hashlib.sha256(canonical_json(data).encode()).hexdigest()
    for wrong in (first, context(db, "other", 3), context(tmp_path / "bob.db", mid=3)):
        assert not execute(runtime, wrong, name, observation_id=ref).result.data["found"]
    with closing(server_runtime.connect(db)) as conn:
        rows = conn.execute("SELECT data_json FROM chat_learning_observations").fetchall()
        assert len(rows) == 2 and all("PRIVATE SOURCE" not in row[0] for row in rows)


def test_public_samples_roundtrip_every_character_and_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(obs, "PAGE_CHARS", 45)
    registry = build_default_tool_registry()
    runtime = ToolRuntime(registry)
    ctx = context(tmp_path / "samples.db")
    stored = execute(runtime, ctx, "get_acm_examples", problem_id=1, count=2)
    assert stored.status == "ok"
    expected = dict(stored.result.data)
    ref = expected.pop("observation")["id"]
    later = context(ctx.user_db, mid=5)
    offset = 0
    chunks = []
    while offset is not None:
        result = execute(runtime, later, "recall_learning_observation", observation_id=ref, offset=offset)
        assert estimate_json_tokens(result.model_payload()) <= registry.get("recall_learning_observation").max_result_tokens
        page = result.result.data
        assert page["offset"] == offset
        chunks.append(page["excerpt"])
        offset = page["next_offset"]
    assert len(chunks) > 1 and "".join(chunks) == canonical_json(expected)
    assert json.loads("".join(chunks))["examples"][0]["input"] == "[2,7,11,15]\n9\n"


def test_limits_failure_and_schema_upgrade(tmp_path, monkeypatch):
    monkeypatch.setattr(obs, "SESSION_LIMIT", 2)
    monkeypatch.setattr(obs, "ACCOUNT_LIMIT", 3)
    db = tmp_path / "legacy.db"
    ctx = context(db)
    from interview_forge.db.ai_schema import ensure_ai_schema
    with closing(server_runtime.connect(db)) as conn:
        conn.execute("DROP TABLE chat_learning_observations")
        ensure_ai_schema(conn)
        ensure_ai_schema(conn)
    for mid, session in enumerate(("a", "b"), start=1):
        owner = context(db, session, mid)
        for _ in range(3):
            assert "id" in obs.save_observation(owner, "get_problem_progress", 1, {"found": False}, uuid4().hex)
    with closing(server_runtime.connect(db)) as conn, conn:
        counts = dict(conn.execute("SELECT session_id,count(*) FROM chat_learning_observations GROUP BY session_id"))
        assert counts == {"a": 1, "b": 2}
        conn.execute("UPDATE chat_learning_observations SET created_at=0")
    params = obs.RecallLearningObservationArgs(problem_id=1, source_tool="get_problem_progress")
    missing = obs.recall_learning_observation(context(db, mid=3), params).data
    assert missing["reason"] == "missing_or_expired" and missing["account_limit"] == 3
    assert obs.save_observation(ctx,"get_problem_progress",1,{"problem":{"code":"private"}}, uuid4().hex)["status"] == "unsupported_fields"
    assert obs.save_observation(ctx,"get_weather",1,{}, uuid4().hex)["status"] == "unsupported_fields"
    spec = build_default_tool_registry().get("get_acm_examples")
    oversized = replace(spec, handler=lambda *_: ToolResult({"title": "过长" * 4000}))
    result = execute(ToolRuntime(ToolRegistry([oversized])), ctx, spec.name, problem_id=1)
    assert result.error_code == "result_too_large"
    with closing(server_runtime.connect(db)) as conn:
        assert conn.execute("SELECT count(*) FROM chat_learning_observations WHERE created_at>0").fetchone()[0] == 0


def test_rolled_back_source_turn_removes_its_receipts_and_rejects_a_late_callback(tmp_path):
    from interview_forge.ai.chat.request_ledger import delete_failed_user

    db = tmp_path / "rolled-back.db"
    ctx = context(db)
    ref = uuid4().hex
    assert obs.save_observation(ctx, "get_problem_progress", 1, {"found": False}, ref) == {"id": ref}
    with closing(server_runtime.connect(db)) as conn, conn:
        delete_failed_user(conn, ctx.session_id, ctx.user_message_id)
    assert obs.save_observation(ctx, "get_problem_progress", 1, {"found": False}, uuid4().hex) == {"status": "source_unavailable"}
    with closing(server_runtime.connect(db)) as conn:
        assert conn.execute("SELECT count(*) FROM chat_learning_observations").fetchone()[0] == 0
