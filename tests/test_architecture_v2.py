import asyncio
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ArchitectureV2Tests(unittest.TestCase):
    def test_domain_modules_have_no_http_server_reverse_import(self):
        for directory in ("services", "analytics", "ai"):
            for path in (ROOT / "interview_forge" / directory).glob("*.py"):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("_runtime()", source, path.name)
                self.assertNotIn("from interview_forge.server", source, path.name)

    def test_fastapi_openapi_health_and_task_backends(self):
        from fastapi.testclient import TestClient
        from interview_forge.api.app import app
        from interview_forge.runtime.task_manager import task_manager

        paths = app.openapi()["paths"]
        self.assertIn("/api/health", paths)
        self.assertIn("/api/me", paths)
        self.assertIn("/api/weather", paths)
        with TestClient(app) as client:
            response = client.get("/api/health", headers={"X-Request-ID": "architecture-test"})
            unauthenticated = client.get("/api/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertEqual(response.headers["x-request-id"], "architecture-test")
        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(unauthenticated.json(), {"error": "未登录"})
        self.assertEqual(task_manager.kinds(), ("ai", "leetcode"))

    def test_async_client_lifecycle_and_sse(self):
        from interview_forge.core.async_http import AsyncHttpClient
        from interview_forge.runtime.streaming import sse_events

        async def source():
            yield {"ok": True}

        async def exercise():
            client = AsyncHttpClient()
            await client.start()
            self.assertIsNotNone(client._client)
            frames = [item async for item in sse_events(source())]
            await client.close()
            return frames, client._client

        frames, closed_client = asyncio.run(exercise())
        self.assertEqual(frames, [b'data: {"ok":true}\n\n'])
        self.assertIsNone(closed_client)
