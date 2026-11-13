"""Merge reviewed ACM cases without replacing statement examples."""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASE_FILES = tuple(ROOT / "data/ai_exam" / f"practice-cases-{part}.json" for part in "abc")
MODES = {"exact", "tokens", "float", "json", "manual", "permutation-sum", "balanced-intervals", "window-distinct", "max-digit-sum"}


def checked_checker(value: object) -> dict:
    if not isinstance(value, dict) or value.get("mode") not in MODES:
        raise ValueError("ACM checker must declare a supported mode")
    result = dict(value)
    for name in ("abs_tol", "rel_tol"):
        if name in result:
            number = result[name]
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number < 0:
                raise ValueError(f"Invalid ACM checker {name}")
    if result["mode"] in {"float", "manual"} and not result.get("reason"):
        raise ValueError("Float/manual checker requires its statement rationale")
    return result


def append_cases(practice: dict, cases: list, *, source: str) -> None:
    samples = practice.setdefault("samples", [])
    seen = {(sample["input"].replace("\r\n", "\n"), sample["expected"].replace("\r\n", "\n")) for sample in samples}
    for sample in cases:
        if not isinstance(sample, dict) or not all(isinstance(sample.get(key), str) for key in ("input", "expected")):
            raise ValueError(f"Invalid ACM sample in {practice.get('url')}")
        if len(sample["input"].encode("utf-8")) > 16 * 1024:
            raise ValueError("ACM input exceeds execution limit")
        if len(sample["expected"].encode("utf-8")) > 64 * 1024:
            raise ValueError("ACM expected output exceeds execution limit")
        key = (sample["input"].replace("\r\n", "\n"), sample["expected"].replace("\r\n", "\n"))
        if key not in seen:
            if any(old_input == key[0] and old_expected.split() != key[1].split() for old_input, old_expected in seen):
                raise ValueError(f"Conflicting ACM answers: {practice.get('url')}")
            clean = {key: sample[key] for key in ("input", "expected", "name", "kind", "verification") if key in sample}
            clean["source"] = source
            samples.append(clean)
            seen.add(key)


def merge_reviewed_cases(entries: list[dict], paths=CASE_FILES) -> None:
    by_url = {entry["url"]: entry.get("practice") for entry in entries}
    assigned = set()
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("version") != 1 or not isinstance(data.get("items"), dict):
            raise ValueError(f"Invalid ACM case file: {path}")
        for url, record in data["items"].items():
            if url in assigned or not isinstance(by_url.get(url), dict):
                raise ValueError(f"Duplicate or unknown ACM problem: {url}")
            assigned.add(url)
            practice = by_url[url]
            excluded = record.get("exclude_statement_inputs", [])
            if excluded:
                if not isinstance(excluded, list) or not all(isinstance(value, str) for value in excluded) or not record.get("exclusion_reason"):
                    raise ValueError(f"ACM sample exclusion lacks evidence: {url}")
                original = practice.get("samples", [])
                if any(value not in [sample["input"] for sample in original] for value in excluded):
                    raise ValueError(f"Excluded ACM input no longer matches source: {url}")
                practice["samples"] = [sample for sample in original if sample["input"] not in excluded]
            practice["checker"] = checked_checker(record["checker"])
            if record.get("case_note"):
                if not isinstance(record["case_note"], str):
                    raise ValueError(f"Invalid ACM case note: {url}")
                practice["case_note"] = record["case_note"]
            if not isinstance(record.get("samples"), list):
                raise ValueError(f"Invalid ACM cases: {url}")
            append_cases(practice, record["samples"], source="supplemental")
    for practice in by_url.values():
        if practice is None:
            continue
        practice.setdefault("checker", {"mode": "exact"})
        practice["suite_version"] = "20261113-expanded-1"
        practice["sample_counts"] = {
            "statement": sum(s.get("source", "statement") == "statement" for s in practice["samples"]),
            "supplemental": sum(s.get("source") == "supplemental" for s in practice["samples"]),
        }
