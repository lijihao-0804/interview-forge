import json
from pathlib import Path

import pytest

from scripts.build.acm_samples import append_cases, checked_checker, merge_reviewed_cases


def test_append_preserves_statement_and_deduplicates():
    practice = {"samples": [{"input": "1", "expected": "2"}]}
    append_cases(practice, [{"input": "1", "expected": "2"}, {"input": "0", "expected": "1", "name": "零边界"}], source="supplemental")
    assert len(practice["samples"]) == 2
    assert practice["samples"][1]["name"] == "零边界"
    assert practice["samples"][1]["source"] == "supplemental"


def test_conflicting_answers_fail_build():
    with pytest.raises(ValueError, match="Conflicting"):
        append_cases({"samples": [{"input": "1", "expected": "2"}]}, [{"input": "1", "expected": "3"}], source="supplemental")


@pytest.mark.parametrize("value", [{"mode": "oops"}, {"mode": "float"}, {"mode": "manual"}, {"mode": "float", "reason": "x", "abs_tol": -1}, {"mode": "json", "abs_tol": float('nan')}])
def test_bad_checker_fails_build(value):
    with pytest.raises(ValueError):
        checked_checker(value)


def test_merge_and_counts(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"version": 1, "items": {"one.html": {"checker": {"mode": "tokens"}, "samples": [{"input": "0", "expected": "0"}]}}}), encoding="utf-8")
    entries = [{"url": "one.html", "practice": {"samples": [{"input": "1", "expected": "1"}]}}]
    merge_reviewed_cases(entries, [path])
    assert entries[0]["practice"]["sample_counts"] == {"statement": 1, "supplemental": 1}
    assert entries[0]["practice"]["checker"] == {"mode": "tokens"}
    with pytest.raises(ValueError, match="unknown"):
        merge_reviewed_cases([], [path])


def test_exclusion_requires_exact_input_and_reason(tmp_path):
    path = tmp_path / "cases.json"
    record = {"checker": {"mode": "tokens"}, "samples": [{"input": "2", "expected": "2"}],
              "exclude_statement_inputs": ["broken"], "exclusion_reason": "Recovered explanatory text, not input"}
    path.write_text(json.dumps({"version": 1, "items": {"one.html": record}}), encoding="utf-8")
    entries = [{"url": "one.html", "practice": {"samples": [{"input": "broken", "expected": "1"}, {"input": "1", "expected": "1"}]}}]
    merge_reviewed_cases(entries, [path])
    assert [row["input"] for row in entries[0]["practice"]["samples"]] == ["1", "2"]
    with pytest.raises(ValueError, match="no longer matches"):
        merge_reviewed_cases(entries, [path])


def test_generated_catalog_preserves_all_problem_entries():
    root = Path(__file__).resolve().parents[1]
    items = json.loads((root / "books/ai-exam/practice-meta.json").read_text(encoding="utf-8"))
    assert len(items) == 147
    assert len({item["id"] for item in items}) == len(items)
    from scripts.build.acm_samples import MODES
    assert all(item.get("checker", {}).get("mode") in MODES for item in items)
    assert all(item.get("sample_counts", {}).get("supplemental", 0) >= 1 for item in items if item.get("checker", {}).get("mode") != "manual")


def test_java_overrides_keep_literal_escapes(tmp_path, monkeypatch):
    from scripts.build import build_ai_exam
    folder = tmp_path / "data/ai_exam"
    folder.mkdir(parents=True)
    target = tmp_path / "demo.md"
    target.write_text('```java\nold\n```\n', encoding='utf-8')
    program = r'''class Main { String value = "a\nb"; char newline = '\n'; }'''
    (folder / "java_standardized.json").write_text(json.dumps({"items": {"demo.md": program}}), encoding="utf-8")
    monkeypatch.setattr(build_ai_exam, "ROOT", tmp_path)
    build_ai_exam.apply_java_overrides()
    assert build_ai_exam.parse_markdown_code(target.read_text(encoding='utf-8'), 'java') == program


def test_parse_all_statement_examples_without_crossing_into_solution():
    from scripts.build.build_ai_exam import parse_markdown_samples
    text = '## 示例 1\n输入：\n```\n1\n```\n输出：\n```\n2\n```\n## 示例 2\n输入：\n```\n3\n```\n输出：\n```\n4\n```\n## 解题代码\n输入：\n```\n5\n```\n输出：\n```\n6\n```'
    assert parse_markdown_samples(text) == [{"input": "1", "expected": "2"}, {"input": "3", "expected": "4"}]
    assert parse_markdown_samples('## 示例\n输入：\n```\nbad\n```\n## 解题代码\n输出：\n```\nnot-an-output\n```') == []
