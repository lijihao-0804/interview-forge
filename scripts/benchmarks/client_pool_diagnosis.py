"""Isolate load-generator pool overhead; never patches the target service."""
import argparse
import asyncio
import json
import runpy
import time
from pathlib import Path

import httpcore
import httpx


async def measure(target, pools):
    bench = runpy.run_path(str(Path(__file__).with_name("http_load.py")), run_name="bench_import")
    original = httpcore.AsyncConnectionPool._assign_requests_to_connections
    calls = [0, 0.0]

    def counted(self):
        started = time.perf_counter()
        try:
            return original(self)
        finally:
            calls[0] += 1
            calls[1] += time.perf_counter() - started

    httpcore.AsyncConnectionPool._assign_requests_to_connections = counted
    clients = [httpx.AsyncClient(base_url=target, timeout=10, trust_env=False,
                                limits=httpx.Limits(max_connections=180, max_keepalive_connections=180))
               for _ in range(pools)]
    latencies, errors, statuses, size = [], [], {}, [0]
    wall, cpu = time.perf_counter(), time.process_time()
    stop_at = time.monotonic() + 6
    lag = []

    async def ticker():
        while time.monotonic() < stop_at:
            start = time.monotonic()
            await asyncio.sleep(.01)
            lag.append(max(0, time.monotonic() - start - .01) * 1000)

    try:
        await asyncio.gather(ticker(), *[
            bench["hammer"](clients[i % pools], "/api/health", stop_at, latencies, errors, statuses, size)
            for i in range(150)])
        duration = time.perf_counter() - wall
        result = bench["summarize"](latencies, len(errors), statuses, duration, size[0])
        result.update(pools=pools, vus=150, target=target, client_cpu_s=round(time.process_time()-cpu,3),
                      pool_assignment_s=round(calls[1],3), pool_assignment_calls=calls[0],
                      event_loop_lag_max_ms=round(max(lag, default=0)))
        return result
    finally:
        httpcore.AsyncConnectionPool._assign_requests_to_connections = original
        await asyncio.gather(*(client.aclose() for client in clients))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="http://127.0.0.1:8765")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    results = []
    for pools in (1, 6):
        row = asyncio.run(measure(args.target, pools))
        print(json.dumps(row), flush=True)
        results.append(row)
    Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
