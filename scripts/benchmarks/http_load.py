"""HTTP 负载测试（k6 风格的闭环阶梯压测，纯 httpx 实现，无外部依赖）。

用途：为 InterviewForge 产出可复现的性能数据（P50/P95/P99、RPS、错误率、
并发拐点）。默认自带熔断：某阶段错误率超过 --abort-threshold 即停止后续
加压阶段，避免对目标服务持续施压。

场景（--scenario）：
  baseline   单并发顺序请求，测各端点干净延迟（含 304 重验证对比）
  ramp       对单个路径阶梯加压（--ramp "5:40,25:40,..."）
  mixed      多路径混合读写比例加压（只读：不产生任何写请求）

安全约定：
  - 只读压测：本脚本绝不发送任何写请求（POST/PUT/PATCH/DELETE 仅限
    --login 的一次认证请求）。
  - 测试 UA 标记，便于服务端在日志中识别。
  - 凭据经环境变量 BENCH_USER/BENCH_PASS 传入，不写入任何报告。

用法示例：
  python scripts/benchmarks/http_load.py baseline --target https://hot100.xyz
  python scripts/benchmarks/http_load.py ramp --target https://hot100.xyz \
      --path /api/bootstrap --ramp "5:40,25:40,50:40,100:40" \
      --user "$BENCH_USER" --password "$BENCH_PASS" --out bench-bootstrap.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[2]
TEST_UA = "InterviewForge-Bench/1.0 (owner self-test; read-only)"
SOLUTION_PATH = quote("/books/hot100/03-题解/01-哈希表/0001-两数之和.html", safe="/")


# ---------------------------------------------------------------- 统计 ----
def percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, round(p / 100 * (len(sorted_values) - 1))))
    return sorted_values[index]


def summarize(latencies_ms: list[float], errors: int, status_counts: dict[int, int],
              duration_s: float, bytes_total: int) -> dict[str, object]:
    ordered = sorted(latencies_ms)
    total = len(ordered)
    return {
        "requests": total,
        "errors": errors,
        "error_rate": round(errors / total, 4) if total else 0.0,
        "rps": round(total / duration_s, 1) if duration_s > 0 else 0.0,
        "p50_ms": round(percentile(ordered, 50)),
        "p90_ms": round(percentile(ordered, 90)),
        "p95_ms": round(percentile(ordered, 95)),
        "p99_ms": round(percentile(ordered, 99)),
        "max_ms": round(ordered[-1]) if ordered else 0,
        "mean_ms": round(statistics.mean(ordered)) if ordered else 0,
        "status": {str(code): count for code, count in sorted(status_counts.items())},
        "bytes_total": bytes_total,
    }


# ---------------------------------------------------------------- 客户端 ----
class ShardedTransport(httpx.AsyncBaseTransport):
    """Bound each httpcore pool; keep one client/cookie jar and a fixed budget.

    One large httpcore pool spends excessive CPU scanning connections on every
    assignment. Sharding improves the generator, not the target's capacity.
    The generator is still single-process and must be independently calibrated.
    """
    def __init__(self, max_connections: int):
        if max_connections < 1:
            raise ValueError("max_connections must be positive")
        shards = min(8, math.ceil(max_connections / 25))
        base, remainder = divmod(max_connections, shards)
        self.budgets = [base + (index < remainder) for index in range(shards)]
        self.transports = [httpx.AsyncHTTPTransport(
            trust_env=False, limits=httpx.Limits(max_connections=budget,
                                              max_keepalive_connections=budget))
            for budget in self.budgets]
        self.cursor = 0

    async def handle_async_request(self, request):
        transport = self.transports[self.cursor % len(self.transports)]
        self.cursor += 1
        return await transport.handle_async_request(request)

    async def aclose(self):
        await asyncio.gather(*(transport.aclose() for transport in self.transports))


async def build_client(target: str, max_connections: int) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=target, transport=ShardedTransport(max_connections),
                             trust_env=False, timeout=httpx.Timeout(15.0),
                             headers={"User-Agent": TEST_UA}, follow_redirects=False)


async def login(client: httpx.AsyncClient, user: str, password: str) -> bool:
    response = await client.post("/api/login",
                                 json={"username": user, "password": password},
                                 headers={"Origin": str(client.base_url),
                                          "Content-Type": "application/json"})
    if response.status_code in (200, 201) and "forge_session" in response.headers.get("set-cookie", ""):
        return True
    detail = response.text[:120].replace(password, "***")
    print(f"login failed: {response.status_code} {detail}", file=sys.stderr)
    return False


# ---------------------------------------------------------------- 执行 ----
async def hammer(client: httpx.AsyncClient, path: str, stop_at: float,
                 latencies: list[float], errors: list[int], statuses: dict[int, int],
                 bytes_counter: list[int], headers: dict[str, str] | None = None) -> None:
    """闭环worker：不断请求直到阶段结束。"""
    request_headers = headers or {}
    while time.monotonic() < stop_at:
        started = time.perf_counter()
        try:
            response = await client.get(path, headers=request_headers)
            elapsed = (time.perf_counter() - started) * 1000
            latencies.append(elapsed)
            statuses[response.status_code] = statuses.get(response.status_code, 0) + 1
            bytes_counter[0] += len(response.content)
            # 非 2xx/3xx/304 一律算错误
            if not (200 <= response.status_code < 400):
                errors.append(1)
        except Exception:  # noqa: BLE001 - 压测需把任何网络异常计为错误并继续
            elapsed = (time.perf_counter() - started) * 1000
            latencies.append(elapsed)
            errors.append(1)
            statuses[0] = statuses.get(0, 0) + 1


async def run_stage(client: httpx.AsyncClient, path: str, vus: int, seconds: float,
                    headers: dict[str, str] | None = None) -> dict[str, object]:
    latencies: list[float] = []
    errors: list[int] = []
    statuses: dict[int, int] = {}
    bytes_counter = [0]
    started = time.monotonic()
    cpu_started = time.process_time()
    stop_at = started + seconds
    await asyncio.gather(*[
        hammer(client, path, stop_at, latencies, errors, statuses, bytes_counter, headers)
        for _ in range(vus)
    ])
    duration = time.monotonic() - started
    summary = summarize(latencies, len(errors), statuses, duration, bytes_counter[0])
    summary["vus"] = vus
    summary["duration_s"] = round(duration, 1)
    summary["generator_cpu_s"] = round(time.process_time() - cpu_started, 3)
    summary["generator_one_core_pct"] = round((time.process_time() - cpu_started) / duration * 100, 1)
    return summary


async def hammer_mixed(client: httpx.AsyncClient, choices: list[str], stop_at: float,
                       latencies: list[float], errors: list[int], statuses: dict[int, int],
                       bytes_counter: list[int], etag_by_path: dict[str, str]) -> None:
    """混合场景闭环worker：按 choices 轮询路径，带 304 重验证头。"""
    counter = 0
    while time.monotonic() < stop_at:
        counter += 1
        path = choices[counter % len(choices)]
        headers = {"If-None-Match": etag_by_path[path]} if etag_by_path.get(path) else None
        req_started = time.perf_counter()
        try:
            response = await client.get(path, headers=headers)
            latencies.append((time.perf_counter() - req_started) * 1000)
            statuses[response.status_code] = statuses.get(response.status_code, 0) + 1
            bytes_counter[0] += len(response.content)
            if not (200 <= response.status_code < 400):
                errors.append(1)
        except Exception:  # noqa: BLE001 - 压测需把任何网络异常计为错误并继续
            latencies.append((time.perf_counter() - req_started) * 1000)
            errors.append(1)
            statuses[0] = statuses.get(0, 0) + 1


async def scenario_baseline(args: argparse.Namespace) -> dict[str, object]:
    """单并发干净延迟：各端点 30 次顺序请求 + 200/304 对比。"""
    results: dict[str, object] = {}
    async with await build_client(args.target, 8) as client:
        if args.user and not await login(client, args.user, args.password):
            raise SystemExit("登录失败（连续失败会触发锁定，请核对账号后重试）")

        probes = [
            ("health", "/api/health", None),
            ("login_page", "/pages/login.html", None),
            ("asset_css", "/assets/site.css?v=bench", None),
            ("cockpit_html", "/cockpit.html", None),
            ("dashboard_html", "/index.html", None),
            ("solution_page", SOLUTION_PATH, None),
            ("api_bootstrap", "/api/bootstrap", None),
            ("api_search", "/api/search?q=%E7%BA%BF%E7%A8%8B%E6%B1%A0", None),
            ("api_daily", "/api/daily", None),
            ("api_plan", "/api/plan", None),
            ("api_weaklist", "/api/weaklist", None),
            ("api_me", "/api/me", None),
            ("guide_html", "/guide.html", None),
        ]
        for name, path, _ in probes:
            latencies: list[float] = []
            errors = 0
            statuses: dict[int, int] = {}
            etag = ""
            stage_started = time.monotonic()
            for _ in range(args.probes):
                started = time.perf_counter()
                try:
                    response = await client.get(path)
                    elapsed = (time.perf_counter() - started) * 1000
                    latencies.append(elapsed)
                    statuses[response.status_code] = statuses.get(response.status_code, 0) + 1
                    if response.status_code >= 400:
                        errors += 1
                    etag = response.headers.get("etag", etag)
                except Exception:  # noqa: BLE001 - 压测需把任何网络异常计为错误并继续
                    latencies.append((time.perf_counter() - started) * 1000)
                    errors += 1
                    statuses[0] = statuses.get(0, 0) + 1
                await asyncio.sleep(0.05)
            results[name] = summarize(latencies, errors, statuses, time.monotonic() - stage_started, 0)

            # 304 重验证对比：用拿到的 ETag 重发同一请求
            if etag:
                lat304: list[float] = []
                statuses304: dict[int, int] = {}
                stage304_started = time.monotonic()
                for _ in range(args.probes):
                    started = time.perf_counter()
                    try:
                        response = await client.get(path, headers={"If-None-Match": etag})
                        lat304.append((time.perf_counter() - started) * 1000)
                        statuses304[response.status_code] = statuses304.get(response.status_code, 0) + 1
                    except Exception:  # noqa: BLE001 - 压测需把任何网络异常计为错误并继续
                        lat304.append((time.perf_counter() - started) * 1000)
                        statuses304[0] = statuses304.get(0, 0) + 1
                    await asyncio.sleep(0.05)
                results[name + "_revalidate304"] = summarize(lat304, 0, statuses304, time.monotonic() - stage304_started, 0)
    return results


async def scenario_ramp(args: argparse.Namespace) -> dict[str, object]:
    """闭环阶梯加压：--ramp "VU:秒,VU:秒,..."，带错误率熔断。"""
    stages = [(float(part.split(":")[0]), float(part.split(":")[1]))
              for part in args.ramp.split(",") if part.strip()]
    results: list[dict[str, object]] = []
    async with await build_client(args.target, max(64, int(max(v for v, _ in stages)) * 2)) as client:
        if args.user and not await login(client, args.user, args.password):
            raise SystemExit("登录失败（连续失败会触发锁定，请核对账号后重试）")
        headers = {"If-None-Match": args.etag} if args.etag else None
        for vus, seconds in stages:
            stage = await run_stage(client, args.path, int(vus), seconds, headers)
            results.append(stage)
            print(f"  {args.path} VU={vus:>4}  RPS={stage['rps']:>7}  "
                  f"P50={stage['p50_ms']:>5}ms P95={stage['p95_ms']:>6}ms P99={stage['p99_ms']:>6}ms "
                  f"err={stage['error_rate']:.2%}", flush=True)
            if float(stage["error_rate"]) > args.abort_threshold:
                print(f"  !! 错误率 {stage['error_rate']:.2%} 超过阈值 {args.abort_threshold:.0%}，停止后续加压", file=sys.stderr)
                break
    return {"path": args.path, "stages": results}


async def scenario_mixed(args: argparse.Namespace) -> dict[str, object]:
    """混合只读场景：bootstrap/search/题解304/登录页 按 --mix 权重分配。"""
    weights = [(part.split(":")[0], float(part.split(":")[1]))
               for part in args.mix.split(",") if part.strip()]
    known_paths = {
        "bootstrap": "/api/bootstrap",
        "search": "/api/search?q=%E7%BA%BF%E7%A8%8B%E6%B1%A0",
        "solution": SOLUTION_PATH,
        "content": "/books/hot100/00-%E6%80%BB%E8%A7%88/01-%E5%AD%A6%E4%B9%A0%E8%B7%AF%E7%BA%BF.html",
        "login": "/pages/login.html",
        "daily": "/api/daily",
        "plan": "/api/plan",
        "weaklist": "/api/weaklist",
        "me": "/api/me",
        "health": "/api/health",
        "css": "/assets/site.css?v=20260919-reliability",
        "guide": "/guide.html",
    }
    total = sum(weight for _, weight in weights)
    choices: list[str] = []
    for name, weight in weights:
        path = known_paths.get(name.strip("/"), name if name.startswith("/") else "/" + name)
        choices.extend([path] * round(weight / total * 100))
    stages = [(float(part.split(":")[0]), float(part.split(":")[1]))
              for part in args.ramp.split(",") if part.strip()]
    results: list[dict[str, object]] = []

    async with await build_client(args.target, max(64, int(max(v for v, _ in stages)) * 2)) as client:
        if args.user and not await login(client, args.user, args.password):
            raise SystemExit("登录失败（连续失败会触发锁定，请核对账号后重试）")
        # 预取书籍页 ETag 供 304 重验证（取 choices 中第一个 /books/ 路径）
        etag_by_path: dict[str, str] = {}
        for path in dict.fromkeys(choices):
            if path.startswith("/books/"):
                first = await client.get(path)
                if first.status_code == 200:
                    etag_by_path[path] = first.headers.get("etag", "")

        for vus, seconds in stages:
            latencies: list[float] = []
            errors: list[int] = []
            statuses: dict[int, int] = {}
            bytes_counter = [0]
            started = time.monotonic()
            stop_at = started + seconds

            await asyncio.gather(*[
                hammer_mixed(client, choices, stop_at, latencies, errors, statuses, bytes_counter, etag_by_path)
                for _ in range(int(vus))
            ])
            duration = time.monotonic() - started
            stage = summarize(latencies, len(errors), statuses, duration, bytes_counter[0])
            stage["vus"] = vus
            stage["duration_s"] = round(duration, 1)
            results.append(stage)
            print(f"  mixed VU={vus:>4}  RPS={stage['rps']:>7}  "
                  f"P50={stage['p50_ms']:>5}ms P95={stage['p95_ms']:>6}ms P99={stage['p99_ms']:>6}ms "
                  f"err={stage['error_rate']:.2%}", flush=True)
            if float(stage["error_rate"]) > args.abort_threshold:
                print("  !! 错误率超阈值，停止后续加压", file=sys.stderr)
                break
    return {"path": "mixed", "stages": results}


async def measure_decompose_path(client: httpx.AsyncClient, path: str, vus: int,
                                 duration: float, psutil_module) -> dict[str, object]:
    """对单路径做 TTFB/正文两段分解采样（参数显式绑定，无跨迭代闭包）。"""
    ttfbs: list[float] = []
    bodies: list[float] = []
    errors: list[int] = []
    statuses: dict[int, int] = {}
    cpu_samples: list[float] = []
    stop_at = time.monotonic() + duration

    async def cpu_sampler() -> None:
        if psutil_module is None:
            return
        # cpu_percent(interval=1) 是同步阻塞调用，会独占事件循环饿死 worker；
        # 必须用非阻塞模式（interval=None 读上次以来的均值）+ asyncio.sleep。
        psutil_module.cpu_percent(interval=None)
        while time.monotonic() < stop_at:
            await asyncio.sleep(1)
            cpu_samples.append(psutil_module.cpu_percent(interval=None))

    async def worker() -> None:
        while time.monotonic() < stop_at:
            started = time.perf_counter()
            try:
                async with client.stream("GET", path) as response:
                    ttfb = (time.perf_counter() - started) * 1000
                    await response.aread()
                total = (time.perf_counter() - started) * 1000
                ttfbs.append(ttfb)
                bodies.append(max(0.0, total - ttfb))
                statuses[response.status_code] = statuses.get(response.status_code, 0) + 1
                if not (200 <= response.status_code < 400):
                    errors.append(1)
            except Exception:  # noqa: BLE001 - 压测需把任何网络异常计为错误并继续
                ttfbs.append((time.perf_counter() - started) * 1000)
                bodies.append(0.0)
                errors.append(1)
                statuses[0] = statuses.get(0, 0) + 1

    sampler = asyncio.create_task(cpu_sampler())
    await asyncio.gather(*[worker() for _ in range(vus)])
    await sampler
    ordered_t = sorted(ttfbs)
    ordered_b = sorted(bodies)
    return {
        "vus": vus,
        "requests": len(ttfbs),
        "rps": round(len(ttfbs) / duration, 1),
        "ttfb_p50_ms": round(percentile(ordered_t, 50)),
        "ttfb_p95_ms": round(percentile(ordered_t, 95)),
        "body_p50_ms": round(percentile(ordered_b, 50)),
        "body_p95_ms": round(percentile(ordered_b, 95)),
        "errors": len(errors),
        "status": {str(code): count for code, count in sorted(statuses.items())},
        "client_cpu_avg_pct": round(statistics.mean(cpu_samples), 1) if cpu_samples else None,
        "client_cpu_max_pct": round(max(cpu_samples), 1) if cpu_samples else None,
    }


async def scenario_decompose(args: argparse.Namespace) -> dict[str, object]:
    """瓶颈分层诊断：固定 VU 下逐路径把总延迟分解为 TTFB（排队+服务端处理+网络）
    与正文传输两段；同时采样客户端 CPU 排除客户端瓶颈。

    判读方法：若各路径 TTFB 随路径重量（health < css < HTML注入 < DB API）单调
    上升且 RPS 平台期一致，瓶颈在服务端处理链（而非网络/客户端）；若 health 的
    TTFB 也陡增，则瓶颈在连接层（nginx/uvicorn/客户端）。
    """
    names = [name.strip() for name in args.paths.split(",") if name.strip()]
    known_paths = {
        "bootstrap": "/api/bootstrap",
        "search": "/api/search?q=%E7%BA%BF%E7%A8%8B%E6%B1%A0",
        "content": "/books/hot100/00-%E6%80%BB%E8%A7%88/01-%E5%AD%A6%E4%B9%A0%E8%B7%AF%E7%BA%BF.html",
        "login": "/pages/login.html",
        "daily": "/api/daily",
        "me": "/api/me",
        "health": "/api/health",
        "css": "/assets/site.css?v=20260919-reliability",
    }
    results: dict[str, object] = {}
    try:
        import psutil
    except ImportError:
        psutil = None

    async with await build_client(args.target, max(64, args.vus * 2)) as client:
        if args.user and not await login(client, args.user, args.password):
            raise SystemExit("登录失败（连续失败会触发锁定，请核对账号后重试）")
        for name in names:
            path = known_paths.get(name, name if name.startswith("/") else "/" + name)
            entry = await measure_decompose_path(client, path, args.vus, args.duration, psutil)
            results[name] = entry
            print(f"  {name:<12} RPS={entry['rps']:>7}  TTFB P50={entry['ttfb_p50_ms']:>5}ms P95={entry['ttfb_p95_ms']:>6}ms  "
                  f"Body P50={entry['body_p50_ms']:>4}ms  err={entry['errors']}", flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", choices=["baseline", "ramp", "mixed", "decompose"])
    parser.add_argument("--target", default="https://hot100.xyz")
    parser.add_argument("--path", default="/api/bootstrap", help="ramp 场景的目标路径")
    parser.add_argument("--ramp", default="5:40,25:40,50:40,100:40", help='"VU:秒" 逗号分隔的阶梯')
    parser.add_argument("--mix", default="api/bootstrap:4,api/search:3,solution:2,login:1",
                        help='mixed 场景 "路径前缀:权重"')
    parser.add_argument("--user", default=os.environ.get("BENCH_USER", ""))
    parser.add_argument("--password", default=os.environ.get("BENCH_PASS", ""))
    parser.add_argument("--probes", type=int, default=30, help="baseline 每端点请求数")
    parser.add_argument("--abort-threshold", type=float, default=0.05, help="错误率熔断阈值")
    parser.add_argument("--etag", default="", help="ramp 场景附带 If-None-Match（304 压测用）")
    parser.add_argument("--paths", default="health,css,login,content,daily,bootstrap,search",
                        help="decompose 场景的路径名列表（逗号分隔）")
    parser.add_argument("--vus", type=int, default=20, help="decompose 场景并发数")
    parser.add_argument("--duration", type=float, default=30, help="decompose 每路径持续秒数")
    parser.add_argument("--out", default="", help="结果 JSON 输出路径")
    args = parser.parse_args()
    print("注意：这是客户端闭环测量，不是服务容量证明；需校准发压端CPU、连接池及网络。", file=sys.stderr)

    runner = {"baseline": scenario_baseline, "ramp": scenario_ramp, "mixed": scenario_mixed,
              "decompose": scenario_decompose}[args.scenario]
    results = asyncio.run(runner(args))
    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"results -> {args.out}")
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
