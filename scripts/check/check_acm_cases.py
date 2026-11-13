"""Execute the repository's trusted ACM reference programs against every public case.

This is a maintainer regression command, not a sandbox for arbitrary submissions.
The website continues to execute user code only in its existing isolated runner.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.practice_runner import _sandbox_environment


def run_problem(item: dict, language: str, timeout: float) -> list[dict]:
    code = item["codes"].get(language)
    if not code:
        return []
    rows = []
    env = {**_sandbox_environment(), "PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0"}
    with tempfile.TemporaryDirectory(prefix="forge-acm-qa-") as folder:
        work = Path(folder)
        compile_error = ""
        if language == "python":
            source = work / "main.py"
            source.write_text(code, encoding="utf-8")
            command = [sys.executable, "-I", str(source)]
        else:
            found = re.search(r"\bpublic\s+(?:final\s+)?class\s+([A-Za-z_$][\w$]*)", code) or re.search(r"\bclass\s+([A-Za-z_$][\w$]*)", code)
            name = found.group(1) if found else "Main"
            source = work / f"{name}.java"
            source.write_text(code, encoding="utf-8")
            try:
                compiled = subprocess.run([shutil.which("javac") or "javac", "-J-Duser.language=en", "-J-Dfile.encoding=UTF-8", "--release", "17", "-encoding", "UTF-8", str(source)], cwd=work, capture_output=True, timeout=30)
                if compiled.returncode:
                    compile_error = compiled.stderr.decode("utf-8", errors="replace")[:3000]
            except (OSError, subprocess.TimeoutExpired) as exc:
                compile_error = str(exc)
            command = [shutil.which("java") or "java", "-Dfile.encoding=UTF-8", "-Xmx256m", "-cp", str(work), name]
        for index, sample in enumerate(item["samples"]):
            row = {"id": item["id"], "url": item["url"], "language": language, "case": index + 1,
                   "name": sample.get("name", "题面样例"), "source": sample.get("source", "statement"),
                   "input": sample["input"], "expected": sample["expected"], "checker": item.get("checker", {"mode": "exact"})}
            start = time.monotonic()
            if compile_error:
                row.update(status="compile_error", stdout="", stderr=compile_error)
            else:
                try:
                    result = subprocess.run(command, input=sample["input"].encode("utf-8"), capture_output=True, cwd=work, env=env, timeout=timeout)
                    row.update(status="ok" if result.returncode == 0 else "runtime_error", stdout=result.stdout.decode("utf-8", errors="replace")[:65536], stderr=result.stderr.decode("utf-8", errors="replace")[:3000])
                except subprocess.TimeoutExpired:
                    row.update(status="timeout", stdout="", stderr="Reference program exceeded maintainer timeout")
                except OSError as exc:
                    row.update(status="service_error", stdout="", stderr=str(exc))
            row["wall_ms"] = round((time.monotonic() - start) * 1000)
            rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=["python", "java", "both"], default="python")
    parser.add_argument("--id", default="", help="Substring of the problem id")
    parser.add_argument("--catalog", type=Path, default=ROOT / "books/ai-exam/practice-meta.json")
    parser.add_argument("--timeout", type=float, default=8)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--report", type=Path, default=ROOT / "logs/acm-case-expansion/reference-results.json")
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 8 or args.timeout <= 0:
        parser.error("workers must be 1..8 and timeout positive")
    catalog_bytes = args.catalog.read_bytes()
    items = json.loads(catalog_bytes)
    items = [item for item in items if args.id in item["id"]]
    if not items:
        parser.error("No matching problem")
    languages = ["python", "java"] if args.language == "both" else [args.language]
    tasks = [(item, lang) for item in items for lang in languages]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        batches = pool.map(lambda task: run_problem(*task, args.timeout), tasks)
        rows = [row for batch in batches for row in batch]
    node = shutil.which("node") or (r"C:\Program Files\nodejs\node.exe" if os.name == "nt" else "node")
    matcher = "const fs=require('fs');const {check}=require('./assets/practice-checker.js');let rows=JSON.parse(fs.readFileSync(0,'utf8'));for(const r of rows)r.verdict=r.status==='ok'?check(r.stdout,r.expected,r.checker,r.input).verdict:r.status;process.stdout.write(JSON.stringify(rows));"
    verdicts = subprocess.run([node, "-e", matcher], cwd=ROOT, input=json.dumps(rows, ensure_ascii=False).encode("utf-8"), capture_output=True, check=True)
    rows = json.loads(verdicts.stdout)
    counts = {key: sum(row["verdict"] == key for row in rows) for key in sorted({row["verdict"] for row in rows})}
    report = {"problems": len(items), "languages": languages, "executions": len(rows), "counts": counts,
              "catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
              "checker_sha256": hashlib.sha256((ROOT / "assets/practice-checker.js").read_bytes()).hexdigest(),
              "numeric_threads": 1,
              "python_version": sys.version, "rows": rows}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}, ensure_ascii=False))
    return int(any(row["verdict"] not in {"pass", "review"} for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
