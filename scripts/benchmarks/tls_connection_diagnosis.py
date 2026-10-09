"""Bounded curl probe: explicit no proxy, per-transfer errors and timings."""
import argparse
import json
import socket
import subprocess
from pathlib import Path


def probe(binary, vus, http1=False, immediate=False, resolve=False):
    config = "".join('url = "https://hot100.xyz/api/health"\noutput = "' +
                     ("NUL" if "Windows" in binary else "/dev/null") + '"\n'
                     for _ in range(vus * 2))
    command = [binary, "--noproxy", "*", "--parallel", "--parallel-max", str(vus),
               "--silent", "--show-error", "--max-time", "10", "--write-out",
               "\nPROBE %{json}\n", "--config", "-"]
    if http1:
        command.append("--http1.1")
    if immediate:
        command.append("--parallel-immediate")
    if resolve:
        address = socket.gethostbyname("hot100.xyz")
        command.extend(["--resolve", "hot100.xyz:443:" + address])
    process = subprocess.run(command, input=config, text=True, capture_output=True, timeout=35, check=False)
    rows = [json.loads(line[6:]) for line in process.stdout.splitlines() if line.startswith("PROBE ")]
    fields = ("http_code", "exitcode", "errormsg", "time_total", "time_connect",
              "time_namelookup", "time_appconnect", "time_starttransfer", "http_version", "num_connects")
    safe = [{key: row.get(key) for key in fields} for row in rows]
    ordered = sorted(row["time_total"] * 1000 for row in rows)
    return {"vus": vus, "http1": http1, "immediate": immediate, "resolve": resolve, "exit": process.returncode,
            "count": len(rows), "errors": sum(row["http_code"] != 200 for row in rows),
            "p50_ms": round(ordered[len(ordered)//2]) if ordered else None,
            "p95_ms": round(ordered[int(len(ordered)*.95)]) if ordered else None,
            "error_examples": list(dict.fromkeys(row.get("errormsg") for row in rows if row.get("errormsg")))[:5],
            "transfers": safe}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--curl", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--vus", nargs="+", type=int, default=[10, 50, 100])
    parser.add_argument("--http1", action="store_true")
    parser.add_argument("--immediate", action="store_true")
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args()
    results = []
    for vus in args.vus:
        row = probe(args.curl, vus, args.http1, args.immediate, args.resolve)
        results.append(row)
        print(json.dumps({key: value for key, value in row.items() if key != "transfers"}), flush=True)
        if row["errors"] > row["count"] * .05:
            break
    Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
