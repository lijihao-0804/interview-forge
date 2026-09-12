import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.api.routers import chat as chat_router
from interview_forge.ai.chat.service import ChatService
from interview_forge.core import default_runtime
from interview_forge.core.runtime import server_runtime
from interview_forge.services.auth import create_session, create_user


class FakeChunk:
    def __init__(self, content="", usage=None):
        self.content = content
        self.usage_metadata = usage or {}
        self.response_metadata = {}
        self.additional_kwargs = {}


class FakeAsyncModel:
    def __init__(self, chunks=None, error=None):
        self.chunks = list(chunks or [])
        self.error = error
        self.messages = None

    async def astream(self, messages):
        self.messages = messages
        if self.error is not None:
            raise self.error
        for chunk in self.chunks:
            yield chunk


def parse_sse(body: str):
    result = []
    for frame in body.split("\n\n"):
        if not frame.strip():
            continue
        event = "message"
        data = ""
        for line in frame.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        result.append((event, json.loads(data)))
    return result


class AIChatContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.auth_db = root / "auth.db"
        self.users_dir = root / "users"
        self.users_dir.mkdir()
        self.old_provider = server_runtime._provider
        self.old_values = dict(server_runtime._values)
        self.old_auth_ready = default_runtime._AUTH_READY
        self.old_last_purge = default_runtime._LAST_SESSION_PURGE
        default_runtime._AUTH_READY = False
        default_runtime._LAST_SESSION_PURGE = 0.0
        default_runtime.AUTH_DB_PATH = self.auth_db
        default_runtime.USERS_DIR = self.users_dir
        server_runtime.bind_provider(lambda: default_runtime)
        self.user = create_user("ChatAlice", "password-1")
        self.token = create_session(int(self.user["id"]))
        self.model = FakeAsyncModel([
            FakeChunk("你好，"),
            FakeChunk("InterviewForge！", {"input_tokens": 18, "output_tokens": 7}),
        ])
        self.service = ChatService(model_factory=lambda _config: self.model)
        self.service_patch = patch.object(chat_router, "chat_service", self.service)
        self.service_patch.start()
        self.env = patch.dict(os.environ, {
            "AI_ENABLED": "1",
            "AI_PROVIDER": "openai-compatible",
            "AI_MODEL": "test-model",
            "AI_API_KEY": "test-key",
            "AI_BASE_URL": "https://example.invalid/v1",
            "AI_BETA_USERS": "*",
        }, clear=False)
        self.env.start()
        self.client = TestClient(app)
        self.client.cookies.set("forge_session", self.token)

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.service_patch.stop()
        default_runtime._AUTH_READY = self.old_auth_ready
        default_runtime._LAST_SESSION_PURGE = self.old_last_purge
        server_runtime._provider = self.old_provider
        server_runtime._values = self.old_values
        self.temp.cleanup()

    def test_unauthenticated_and_session_history_persistence(self):
        with TestClient(app) as anonymous:
            response = anonymous.get("/api/chat/sessions")
        self.assertEqual(response.status_code, 401)

        created = self.client.post("/api/chat/sessions", json={})
        self.assertEqual(created.status_code, 201)
        session = created.json()
        self.assertEqual(session["title"], "新会话")
        streamed = self.client.post(
            f"/api/chat/sessions/{session['id']}/stream",
            json={"message": "请介绍一下 TCP"},
        )
        self.assertEqual(streamed.status_code, 200)
        self.assertTrue(streamed.headers["content-type"].startswith("text/event-stream"))
        events = parse_sse(streamed.text)
        self.assertEqual([name for name, _ in events], ["message.start", "message.delta", "message.delta", "message.done"])
        self.assertIn("message_id", events[0][1])
        self.assertEqual(events[1][1]["delta"], "你好，")
        self.assertEqual(events[-1][1]["message_id"], events[0][1]["message_id"])
        self.assertEqual(events[-1][1]["usage"]["input_tokens"], 18)
        self.assertEqual(events[-1][1]["usage"]["output_tokens"], 7)

        sessions = self.client.get("/api/chat/sessions").json()["items"]
        self.assertEqual(sessions[0]["title"], "请介绍一下 TCP")
        history = self.client.get(f"/api/chat/sessions/{session['id']}/messages")
        self.assertEqual(history.status_code, 200)
        self.assertEqual([item["role"] for item in history.json()["items"]], ["user", "assistant"])
        self.assertEqual(history.json()["items"][1]["content"], "你好，InterviewForge！")

        connection = sqlite3.connect(self.users_dir / "ChatAlice" / "hot100-study.db")
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("chat_sessions", tables)
            self.assertIn("chat_messages", tables)
        finally:
            connection.close()

    def test_provider_failure_emits_error_and_never_persists_partial_assistant(self):
        failing = FakeAsyncModel(error=RuntimeError("provider secret detail"))
        self.service.model_factory = lambda _config: failing
        created = self.client.post("/api/chat/sessions", json={}).json()
        response = self.client.post(
            f"/api/chat/sessions/{created['id']}/stream", json={"message": "测试失败"}
        )
        events = parse_sse(response.text)
        self.assertEqual([name for name, _ in events], ["message.start", "error"])
        self.assertEqual(events[-1][1]["code"], "provider_error")
        self.assertNotIn("secret detail", events[-1][1]["message"])
        history = self.client.get(f"/api/chat/sessions/{created['id']}/messages").json()["items"]
        self.assertEqual([item["role"] for item in history], ["user"])

    def test_cross_user_session_isolation_and_input_bounds(self):
        created = self.client.post("/api/chat/sessions", json={}).json()
        other = create_user("ChatBob", "password-2")
        other_token = create_session(int(other["id"]))
        self.client.cookies.set("forge_session", other_token)
        self.assertEqual(self.client.get(f"/api/chat/sessions/{created['id']}/messages").status_code, 404)
        self.assertEqual(self.client.post(f"/api/chat/sessions/{created['id']}/stream", json={"message": "越权"}).status_code, 404)
        self.assertEqual(self.client.post("/api/chat/sessions", json={"user_id": 1}).status_code, 400)
        self.assertEqual(self.client.post("/api/chat/sessions", json={}).status_code, 201)
        self.assertEqual(self.client.post(
            f"/api/chat/sessions/{created['id']}/stream", json={"message": "x" * 12_001}
        ).status_code, 400)


if __name__ == "__main__":
    unittest.main()
