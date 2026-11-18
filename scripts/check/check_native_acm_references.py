"""Run both volumes' published primary solutions with the real ACM stdin and output checker.

    python -m scripts.check.check_native_acm_references --report results.jsonl
    python -m scripts.check.check_native_acm_references --id hot100-5 --language java

On the Linux judge host, --engine sandbox calls the production runner in a separate
process without making a submission, using an account, or taking the live service lock.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from functools import cache
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from interview_forge.services import native_acm
from tools import practice_runner

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VOLUMES = {"hot100": "hot100.json", "hot200": "hot200-extra.json"}
DESIGNS = {
    146: ("LRUCache", ""), 155: ("MinStack", ""), 208: ("Trie", ""), 295: ("MedianFinder", ""),
    244: ("WordDistance", "shortest"), 251: ("Vector2D", ""), 271: ("Codec", ""),
    281: ("ZigzagIterator", ""), 288: ("ValidWordAbbr", "isUnique"), 308: ("NumMatrix", ""),
    346: ("MovingAverage", "next"), 348: ("TicTacToe", "move"), 353: ("SnakeGame", "move"),
    359: ("Logger", "shouldPrintMessage"), 362: ("HitCounter", ""), 379: ("PhoneDirectory", ""),
    428: ("Codec", ""), 431: ("Codec", ""), 716: ("MaxStack", ""),
}


class PublishedCode(HTMLParser):
    """Collect highlighted code in its enclosing language scope, including legacy unlabelled fences."""

    def __init__(self):
        super().__init__()
        self.stack = []
        self.blocks = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag not in {"div", "section", "pre", "code"}:
            return
        attrs = dict(attrs)
        lang, highlighted = self.stack[-1][1:] if self.stack else (None, False)
        lang = attrs.get("data-lang", lang)
        highlighted = highlighted or "codehilite" in attrs.get("class", "").split()
        self.stack.append((tag, lang, highlighted))
        if tag == "code" and highlighted:
            self.current = (lang, [])

    def handle_data(self, text):
        if self.current is not None:
            self.current[1].append(text)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1][0] != tag:
            return
        self.stack.pop()
        if tag == "code" and self.current is not None:
            lang, chunks = self.current
            self.blocks.append((lang, "".join(chunks).strip()))
            self.current = None


def published_sources(row):
    parser = PublishedCode()
    parser.feed((ROOT / row["solution_url"].lstrip("/")).read_text(encoding="utf-8"))
    pid = int(row["id"].split("-")[1])
    cls = DESIGNS.get(pid, ("Solution", ""))[0]
    patterns = {
        "java": rf"(?m)^(?:(?:public|final|abstract)\s+)*class\s+{cls}\b[^{{;]*\{{",
        "python": rf"(?m)^class\s+{cls}\b[^\n]*:\s*$",
    }
    codes = {}
    for lang, pattern in patterns.items():
        for scope, code in parser.blocks:
            if scope in (None, lang) and re.search(pattern, code):
                codes[lang] = code
                break
        else:
            raise ValueError(f"{row['id']}: no published {lang} implementation")
    return codes


@cache
def adapter_text(name):
    return (HERE / name).read_text(encoding="utf-8")


def python_program(code, volume, pid):
    # Judge-supplied types precede the solution. Future imports must remain at the top of the file.
    futures = re.findall(r"(?m)^from __future__ import .+$", code)
    body = re.sub(r"(?m)^from __future__ import .+$", "", code)
    adapter = adapter_text("native_acm_python.py")
    function = "hot100_reference" if volume == "hot100" else "run_reference"
    return "\n".join([*futures, adapter, "TreeNode = Node", body, "import json, sys",
                      "args = [json.loads(line) for line in sys.stdin if line.strip()]",
                      f"print(json.dumps({function}({pid}, globals(), args), allow_nan=False))", ""])


JAVA_IMPORT = re.compile(r"(?m)^import\s+[^;\n]+;[ \t]*$")


def java_program(code, pid):
    model = adapter_text("Hot200Judge.java")
    adapter = adapter_text("NativeAcmInput.java")
    imports = sorted(set(JAVA_IMPORT.findall("\n".join((model, adapter, code)))) - {"import judge.Hot200Judge;"})
    model = JAVA_IMPORT.sub("", model).replace("package judge;", "").replace("public class Hot200Judge", "class Hot200Judge")
    adapter = JAVA_IMPORT.sub("", adapter)
    # The original algorithm and method bodies are intact. Nest the published classes so their
    # source and the supplied judge types fit in the runner's one Main.java compilation unit.
    body = re.sub(r"(?m)^((?:(?:public|abstract|final) +)*)class ", r"\1static class ", JAVA_IMPORT.sub("", code))
    cls, operation = DESIGNS.get(pid, ("Solution", ""))
    if cls == "Solution":
        declarations = re.sub(r"/\*.*?\*/|//[^\n]*", "", code, flags=re.S)
        solution = declarations[declarations.index("class Solution"):]
        signature = re.search(r"\bpublic\s+[\w<>\[\],]+\s+(\w+)\s*\(", solution)
        if not signature:
            raise ValueError(f"{pid}: missing public Java solution method")
        operation = signature[1]
    main = (
        "public class Main extends NativeAcmInput {\n"
        "    public static void main(String[] argv) throws Exception {\n"
        f'        System.out.println(output({pid}, solve({pid}, "{cls}", "{operation}", readArguments())));\n'
        "    }\n" + body + "\n}\n"
    )
    return "\n".join([*imports, main, model, adapter, ""])


def run_process(command, folder, stdin, timeout):
    try:
        proc = subprocess.run(command, cwd=folder, input=stdin.encode("utf-8"), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "stdout": "", "stderr": f"Timed out after {timeout}s"}
    size = len(proc.stdout) + len(proc.stderr)
    status = "output_limit" if size > practice_runner.MAX_OUTPUT_BYTES else ("ok" if proc.returncode == 0 else "runtime_error")
    return {"status": status, "stdout": proc.stdout.decode("utf-8", "replace"), "stderr": proc.stderr.decode("utf-8", "replace")}


def local_command(folder, lang, program):
    if lang == "python":
        (folder / "main.py").write_text(program, encoding="utf-8")
        return [sys.executable, "-X", "utf8", "main.py"], None
    (folder / "Main.java").write_text(program, encoding="utf-8")
    options = practice_runner._JVM_OPTIONS
    built = run_process(["javac", *("-J" + o for o in options), "--release", "17", "-encoding", "UTF-8", "Main.java"],
                        folder, "", 45)
    if built["status"] != "ok":
        built["status"] = "compile_error"
        return [], built
    return ["java", *options, "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8", "-cp", ".", "Main"], None


def verify(job):
    row, lang, code, engine = job
    volume, number = row["id"].split("-")
    pid = int(number)
    program = java_program(code, pid) if lang == "java" else python_program(code, volume, pid)
    if len(program.encode("utf-8")) > practice_runner.MAX_CODE_BYTES:
        raise ValueError(f"{row['id']} {lang}: exceeds the runner's source size limit")
    digest = hashlib.sha256(program.encode("utf-8")).hexdigest()
    rows = []
    context = tempfile.TemporaryDirectory(prefix="native-acm-") if engine == "local" else nullcontext(None)
    with context as tmp:
        if engine == "local":
            folder = Path(tmp)
            command, compile_error = local_command(folder, lang, program)
        for i, sample in enumerate(row["samples"], 1):
            stdin = sample["input"]
            if len(stdin.encode("utf-8")) > practice_runner.MAX_STDIN_BYTES:
                raise ValueError(f"{row['id']} case {i}: exceeds the runner's stdin size limit")
            if engine == "sandbox":
                result = practice_runner.run_code(lang, program, stdin)
            else:
                # Host process/virus-scanner startup on Windows is outside the production sandbox budget.
                result = compile_error or run_process(command, folder, stdin, 15)
            verdict = "output_limit" if result.get("output_truncated") else result["status"]
            if verdict == "ok":
                verdict = "pass" if native_acm.matches(result["stdout"], sample["expected"], row["checker"]) else "wrong_answer"
            rows.append({"id": row["id"], "language": lang, "case": i, "name": sample["name"], "engine": engine,
                         "verdict": verdict, "program_sha256": digest, "input": stdin, "expected": sample["expected"],
                         "stdout": result["stdout"], "stderr": result.get("stderr", "")})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", choices=("local", "sandbox"), default="local")
    parser.add_argument("--volume", choices=(*VOLUMES, "both"), default="both")
    parser.add_argument("--language", choices=("python", "java", "both"), default="both")
    parser.add_argument("--id", action="append", default=[], help="Exact problem key (repeatable)")
    parser.add_argument("--workers", type=int, help="Concurrent programs locally; sandbox runs sequentially")
    parser.add_argument("--report", type=Path, help="Write one JSON line per evaluated case")
    args = parser.parse_args()
    workers = args.workers if args.workers is not None else (min(4, os.cpu_count() or 1) if args.engine == "local" else 1)
    if workers < 1 or (args.engine == "sandbox" and workers != 1):
        parser.error("Use positive workers locally and one worker in the sandbox")
    if args.engine == "sandbox" and not sys.platform.startswith("linux"):
        parser.error("The production bubblewrap sandbox requires Linux")
    selected = set(args.id)
    found = set()
    jobs = []
    for volume, filename in VOLUMES.items():
        if args.volume not in (volume, "both"):
            continue
        catalog = json.loads((ROOT / "data/acm" / filename).read_bytes())
        if len(catalog) != 100 or len({row["id"] for row in catalog}) != 100:
            raise ValueError(f"{volume}: incomplete or duplicate problem catalog")
        for row in catalog:
            if selected and row["id"] not in selected:
                continue
            if not row["samples"] or native_acm.problem(row["id"]) != row:
                raise ValueError(f"{row['id']}: unavailable in the production catalog")
            found.add(row["id"])
            for language, code in published_sources(row).items():
                if args.language in ("both", language):
                    jobs.append((row, language, code, args.engine))
    if selected - found:
        parser.error(f"Unknown problem keys in selected volume: {sorted(selected - found)}")
    counts = Counter()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
    report = args.report.open("w", encoding="utf-8") if args.report else nullcontext(None)
    with report as output, ThreadPoolExecutor(max_workers=workers) as pool:
        for results in pool.map(verify, jobs):
            for entry in results:
                counts[entry["verdict"]] += 1
                if output:
                    output.write(json.dumps(entry, ensure_ascii=False) + "\n")
                if entry["verdict"] != "pass":
                    print(f"{entry['id']} {entry['language']} [{entry['case']}] {entry['verdict']}: "
                          f"{entry['stderr'][:500] or entry['stdout'][:300]}", flush=True)
            if output:
                output.flush()
    expected = sum(len(row["samples"]) for row, *_ in jobs)
    print(json.dumps({"engine": args.engine, "problems": len(found), "programs": len(jobs), "cases": expected,
                      "verdicts": counts}, ensure_ascii=False))
    return int(counts["pass"] != expected)


if __name__ == "__main__":
    sys.exit(main())
