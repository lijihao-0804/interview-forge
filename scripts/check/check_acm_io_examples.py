"""Run the complete Java/Python programs printed in the ACM I/O course.

Only standard-library dependencies are needed. Run with the project's Python:
    python scripts/check/check_acm_io_examples.py
Fixture locations use heading paths rather than copies of the example code.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/acm_io_examples.json"


def extract_programs(text: str) -> list[dict]:
    """Identify fenced programs, ignoring headings inside any fenced block."""
    headings: dict[int, str] = {}
    occurrences: Counter = Counter()
    programs = []
    fence = None
    code = []
    location = None
    for number, line in enumerate(text.splitlines(), 1):
        if fence:
            if re.fullmatch(re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*", line):
                if location:
                    programs.append({**location, "code": "\n".join(code) + "\n"})
                fence, location, code = None, None, []
            else:
                code.append(line)
            continue
        match = re.match(r"^(`{3,}|~{3,})(\w*)\s*$", line)
        if match:
            fence, language = match.groups()
            if language in {"java", "python"}:
                path = tuple(headings[level] for level in sorted(headings) if level >= 2)
                key = (path, language)
                occurrences[key] += 1
                location = {"headings": list(path), "language": language,
                            "ordinal": occurrences[key], "line": number}
            continue
        match = re.match(r"^(#{2,6})\s+(.+?)\s*$", line)
        if match:
            level, title = len(match[1]), match[2]
            headings = {depth: value for depth, value in headings.items() if depth < level}
            headings[level] = title
    if fence:
        raise ValueError("Unclosed Markdown fence")
    return programs


def location_key(example: dict) -> tuple:
    return tuple(example["headings"]), example["language"], example["ordinal"]


def normalized(value: str) -> str:
    return value.replace("\r\n", "\n")


def run_check(fixtures: Path, python: str, javac: str, java: str) -> dict:
    suite = json.loads(fixtures.read_text(encoding="utf-8"))
    programs = extract_programs((ROOT / suite["source"]).read_text(encoding="utf-8-sig"))
    actual = {location_key(program): program for program in programs}
    examples = suite["examples"]
    expected = {location_key(example) for example in examples}
    if len(expected) != len(examples) or len({item["id"] for item in examples}) != len(examples):
        raise ValueError("Duplicate fixture IDs or program locations")
    if expected != actual.keys():
        raise ValueError(f"Program coverage mismatch: missing={actual.keys() - expected}, orphan={expected - actual.keys()}")
    counts = Counter()
    with tempfile.TemporaryDirectory(prefix="acm-io-") as temporary:
        for index, example in enumerate(examples):
            program = actual[location_key(example)]
            folder = Path(temporary) / str(index)
            folder.mkdir()
            if program["language"] == "python":
                source = folder / "main.py"
                source.write_text(program["code"], encoding="utf-8")
                command = [python, "-X", "utf8", str(source)]
            else:
                source = folder / "Main.java"
                source.write_text(program["code"], encoding="utf-8")
                compile_result = subprocess.run(
                    [javac, "--release", "17", "-encoding", "UTF-8", str(source)],
                    capture_output=True, encoding="utf-8", timeout=30,
                )
                if compile_result.returncode:
                    raise AssertionError(f'{example["id"]}: compilation failed\n{compile_result.stderr}')
                # JDK 25 on Windows uses native pipe encodings independently of
                # file.encoding; JDK 17 simply ignores these newer properties.
                command = [java, "-Dfile.encoding=UTF-8", "-Dstdin.encoding=UTF-8",
                           "-Dstdout.encoding=UTF-8", "-Dstderr.encoding=UTF-8", "-Duser.language=de",
                           "-Duser.country=DE", "-cp", str(folder), "Main"]
            if not example["cases"]:
                raise ValueError(f'{example["id"]}: no cases')
            for case_index, case in enumerate(example["cases"], 1):
                result = subprocess.run(command, input=case["stdin"], capture_output=True,
                                        encoding="utf-8", timeout=10, cwd=folder)
                label = f'{example["id"]} case {case_index} (source line {program["line"]})'
                if result.returncode != case.get("exit_code", 0):
                    raise AssertionError(f'{label}: exit {result.returncode}\n{result.stderr}')
                if normalized(result.stdout) != normalized(case["stdout"]):
                    raise AssertionError(f'{label}: expected {case["stdout"]!r}, got {result.stdout!r}')
                if case.get("stderr_contains") not in (None, ""):
                    if case["stderr_contains"] not in result.stderr:
                        raise AssertionError(f'{label}: missing expected error {case["stderr_contains"]!r}')
                elif result.stderr:
                    raise AssertionError(f'{label}: unexpected stderr {result.stderr}')
                counts[program["language"] + "_cases"] += 1
                counts["intentional_errors"] += bool(case.get("exit_code", 0))
            counts[program["language"] + "_programs"] += 1
    return dict(counts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--javac", default=shutil.which("javac"))
    parser.add_argument("--java", default=shutil.which("java"))
    args = parser.parse_args()
    if not args.javac or not args.java:
        parser.error("A JDK supporting --release 17 is required")
    print(json.dumps(run_check(args.fixtures, args.python, args.javac, args.java), ensure_ascii=False))


if __name__ == "__main__":
    main()
