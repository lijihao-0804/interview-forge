"""Bounded connection diagnosis; aggregate output only, no account writes."""
import argparse
import asyncio
import json
import runpy
from pathlib import Path


async def main(args):
    bench = runpy.run_path(str(Path(__file__).with_name("http_load.py")), run_name="probe_import")
    results = []
    for target in args.targets:
        for vus in (50, 100, 150):
            async with await bench["build_client"](target, 180) as client:
                item = await bench["run_stage"](client, "/api/health", vus, 6)
                item["target"] = target
                results.append(item)
                print(json.dumps(item), flush=True)
                if item["error_rate"] > 0.05 or item["p95_ms"] > 5000:
                    print("circuit_breaker", flush=True)
                    break
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", nargs="+", default=["https://hot100.xyz"])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    results = asyncio.run(main(args))
    Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
