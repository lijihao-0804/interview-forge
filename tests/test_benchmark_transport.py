import asyncio
import unittest
from typing import ClassVar
from unittest.mock import patch

import httpx

from scripts.benchmarks.http_load import ShardedTransport, build_client


class RecordingTransport(httpx.AsyncBaseTransport):
    instances: ClassVar[list] = []

    def __init__(self, **kwargs):
        self.closed = False
        self.calls = 0
        self.instances.append(self)

    async def handle_async_request(self, request):
        self.calls += 1
        return httpx.Response(200, content=b"ok", request=request)

    async def aclose(self):
        self.closed = True


class BenchmarkTransportTests(unittest.TestCase):
    def test_budget_is_preserved(self):
        async def check():
            for count in (1, 24, 25, 64, 150, 300):
                transport = ShardedTransport(count)
                self.assertEqual(sum(transport.budgets), count)
                self.assertLessEqual(len(transport.budgets), 8)
                await transport.aclose()
        asyncio.run(check())

    def test_dispatch_and_close_all_pools(self):
        async def check():
            RecordingTransport.instances = []
            with patch("httpx.AsyncHTTPTransport", RecordingTransport):
                async with await build_client("http://localhost", 150) as client:
                    client.cookies.set("test_session", "local-only")
                    for _ in range(12):
                        response = await client.get("/api/health")
                        self.assertEqual(response.status_code, 200)
                    self.assertEqual(client.cookies.get("test_session"), "local-only")
                self.assertEqual([t.calls for t in RecordingTransport.instances], [2]*6)
                self.assertTrue(all(t.closed for t in RecordingTransport.instances))
        asyncio.run(check())

    def test_invalid_budget(self):
        with self.assertRaises(ValueError):
            ShardedTransport(0)
