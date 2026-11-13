"""Load and render the reviewed Python Hot 100 curriculum.

The JSON files under ``tools/`` are the source of truth.  This module deliberately
has no dependency on ``build_hot100`` so tests and builders can load the curriculum
without evaluating the larger site build module.
"""
from __future__ import annotations

import ast
import html
import json
import re
from pathlib import Path
from typing import Any

from interview_forge.core.paths import ROOT

SCHEMA_VERSION = 1
PROBLEMS_PATH = ROOT / "tools" / "python_hot100.json"
TOPICS_PATH = ROOT / "tools" / "python_hot100_topics.json"
BASICS_PATH = ROOT / "tools" / "python_hot100_basics.json"


class PythonCurriculumError(ValueError):
    """Raised when the reviewed Python curriculum violates its own schema."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PythonCurriculumError(f"missing Python curriculum: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PythonCurriculumError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PythonCurriculumError(f"top-level JSON object required: {path}")
    return payload


def load_problem_curriculum() -> dict[int, dict[str, Any]]:
    payload = _load_json(PROBLEMS_PATH)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise PythonCurriculumError("python_hot100.json schema_version must be 1")
    if payload.get("language") != "python":
        raise PythonCurriculumError("python_hot100.json language must be python")
    raw = payload.get("problems")
    if not isinstance(raw, dict):
        raise PythonCurriculumError("python_hot100.json problems must be an object")
    result: dict[int, dict[str, Any]] = {}
    for raw_id, item in raw.items():
        if not re.fullmatch(r"[1-9][0-9]*", str(raw_id)):
            raise PythonCurriculumError(f"invalid problem id: {raw_id!r}")
        if not isinstance(item, dict):
            raise PythonCurriculumError(f"problem {raw_id} must be an object")
        result[int(raw_id)] = item
    return result


def load_topic_curriculum() -> dict[str, dict[str, Any]]:
    payload = _load_json(TOPICS_PATH)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise PythonCurriculumError("python_hot100_topics.json schema_version must be 1")
    if payload.get("language") != "python":
        raise PythonCurriculumError("python_hot100_topics.json language must be python")
    categories = payload.get("categories")
    if not isinstance(categories, dict):
        raise PythonCurriculumError("python_hot100_topics.json categories must be an object")
    return {
        str(name): detail
        for name, detail in categories.items()
        if isinstance(detail, dict)
    }


def load_basics_curriculum() -> dict[str, dict[str, Any]]:
    payload = _load_json(BASICS_PATH)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise PythonCurriculumError("python_hot100_basics.json schema_version must be 1")
    if payload.get("language") != "python":
        raise PythonCurriculumError("python_hot100_basics.json language must be python")
    basics = payload.get("basics")
    if not isinstance(basics, dict):
        raise PythonCurriculumError("python_hot100_basics.json basics must be an object")
    return {
        str(name): detail
        for name, detail in basics.items()
        if isinstance(detail, dict)
    }


def _annotated_variable_names(source: str, filename: str) -> list[str]:
    """Return variable annotations that should stay out of teaching templates."""
    tree = ast.parse(source, filename=filename)
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        if isinstance(node.target, ast.Name):
            names.append(node.target.id)
        else:
            names.append(ast.unparse(node.target))
    return names


def validate_topic_curriculum(
    topics: dict[str, dict[str, Any]],
    categories: list[str],
    problems: dict[int, dict[str, Any]],
) -> list[str]:
    """Validate all 17 topic panels and their per-problem coverage."""
    errors: list[str] = []
    expected = set(categories)
    actual = set(topics)
    if actual != expected:
        if expected - actual:
            errors.append(f"missing Python topics: {sorted(expected - actual)}")
        if actual - expected:
            errors.append(f"unknown Python topics: {sorted(actual - expected)}")

    required_strings = (
        "summary",
        "invariant_reason",
        "why_python",
        "teaching_markdown",
        "explanation_markdown",
        "template_source",
        "template_note",
        "template",
        "template_name",
    )
    seen_problem_ids: list[int] = []
    for category, item in topics.items():
        label = f"topic {category}"
        for field in required_strings:
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{label}: {field} must be a non-empty string")
        for field in ("workflow", "api_hints", "pitfalls"):
            value = item.get(field)
            if not isinstance(value, list) or len(value) < 2:
                errors.append(f"{label}: {field} needs at least two entries")
        template = item.get("template")
        if isinstance(template, str):
            try:
                compile(template, f"<python-topic-{category}>", "exec")
            except SyntaxError as exc:
                errors.append(f"{label}: template does not compile: {exc}")
            else:
                annotated = _annotated_variable_names(
                    template, f"<python-topic-{category}>"
                )
                if annotated:
                    errors.append(
                        f"{label}: use ordinary local assignments instead of annotations: "
                        f"{', '.join(annotated)}"
                    )
        rows = item.get("problem_focus")
        if not isinstance(rows, list) or not rows:
            errors.append(f"{label}: problem_focus must cover its catalog problems")
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"{label}: problem_focus[{index}] must be an object")
                continue
            try:
                problem_id = int(row["id"])
            except (KeyError, TypeError, ValueError):
                errors.append(f"{label}: problem_focus[{index}] has invalid id")
                continue
            seen_problem_ids.append(problem_id)
            if not isinstance(row.get("title"), str) or not row["title"].strip():
                errors.append(f"{label}: problem {problem_id} has no title")
            if not isinstance(row.get("focus"), str) or not row["focus"].strip():
                errors.append(f"{label}: problem {problem_id} has no focus")
            if problem_id not in problems:
                errors.append(f"{label}: problem {problem_id} is outside Python curriculum")
            elif row.get("title") != problems[problem_id].get("title"):
                errors.append(f"{label}: problem {problem_id} title does not match curriculum")
    if sorted(seen_problem_ids) != sorted(problems):
        missing = sorted(set(problems) - set(seen_problem_ids))
        duplicates = sorted({value for value in seen_problem_ids if seen_problem_ids.count(value) > 1})
        if missing:
            errors.append(f"Python topics miss problems: {missing}")
        if duplicates:
            errors.append(f"Python topics duplicate problems: {duplicates}")
    return errors


def validate_basics_curriculum(basics: dict[str, dict[str, Any]]) -> list[str]:
    """Validate the five Python basic panels and their executable examples."""
    errors: list[str] = []
    required_strings = (
        "title",
        "summary",
        "teaching_markdown",
        "explanation_markdown",
        "template_name",
        "template",
    )
    for name, item in basics.items():
        label = f"basic {name}"
        for field in required_strings:
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{label}: {field} must be a non-empty string")

        concepts = item.get("concepts")
        if not isinstance(concepts, list) or len(concepts) < 3:
            errors.append(f"{label}: concepts needs at least three entries")
        else:
            for index, concept in enumerate(concepts):
                if not isinstance(concept, dict):
                    errors.append(f"{label}: concepts[{index}] must be an object")
                    continue
                for field in ("heading", "body"):
                    value = concept.get(field)
                    if not isinstance(value, str) or not value.strip():
                        errors.append(f"{label}: concepts[{index}].{field} is empty")

        hints = item.get("api_hints")
        if not isinstance(hints, list) or len(hints) < 2:
            errors.append(f"{label}: api_hints needs at least two entries")
        else:
            for index, hint in enumerate(hints):
                if not isinstance(hint, dict):
                    errors.append(f"{label}: api_hints[{index}] must be an object")
                    continue
                for field in ("symbol", "syntax", "use"):
                    value = hint.get(field)
                    if not isinstance(value, str) or not value.strip():
                        errors.append(f"{label}: api_hints[{index}].{field} is empty")

        pitfalls = item.get("pitfalls")
        if not isinstance(pitfalls, list) or len(pitfalls) < 2 or not all(
            isinstance(value, str) and value.strip() for value in pitfalls
        ):
            errors.append(f"{label}: pitfalls needs at least two non-empty entries")

        template = item.get("template")
        if isinstance(template, str):
            try:
                compile(template, f"<python-basic-{name}>", "exec")
            except SyntaxError as exc:
                errors.append(f"{label}: template does not compile: {exc}")
            else:
                annotated = _annotated_variable_names(template, f"<python-basic-{name}>")
                if annotated:
                    errors.append(
                        f"{label}: use ordinary local assignments instead of annotations: "
                        f"{', '.join(annotated)}"
                    )
    return errors


def validate_problem_curriculum(
    curriculum: dict[int, dict[str, Any]],
    catalog: list[dict[str, object]],
) -> list[str]:
    """Return schema/coverage errors without importing third-party validators."""
    errors: list[str] = []
    expected = {int(problem["id"]): problem for problem in catalog}
    missing = sorted(set(expected) - set(curriculum))
    extra = sorted(set(curriculum) - set(expected))
    if missing:
        errors.append(f"missing Python curriculum ids: {missing}")
    if extra:
        errors.append(f"unknown Python curriculum ids: {extra}")

    required_strings = (
        "title",
        "method",
        "time",
        "space",
        "invariant",
        "why_this_approach",
        "complexity_reason",
        "code",
        "teaching_markdown",
        "explanation_markdown",
        "source",
        "source_note",
    )
    for problem_id, item in curriculum.items():
        label = f"problem {problem_id}"
        for field in required_strings:
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{label}: {field} must be a non-empty string")
        revision_notes = item.get("revision_notes")
        if not isinstance(revision_notes, list) or not revision_notes or not all(
            isinstance(note, str) and note.strip() for note in revision_notes
        ):
            errors.append(f"{label}: revision_notes must record the source review")
        catalog_problem = expected.get(problem_id)
        if catalog_problem and item.get("title") != catalog_problem.get("title"):
            errors.append(f"{label}: title does not match the canonical catalog")
        derivation = item.get("derivation")
        if not isinstance(derivation, list) or len(derivation) < 3:
            errors.append(f"{label}: derivation needs at least three steps")
        pitfalls = item.get("pitfalls")
        if not isinstance(pitfalls, list) or len(pitfalls) < 2:
            errors.append(f"{label}: pitfalls needs at least two entries")
        api_hints = item.get("api_hints")
        if not isinstance(api_hints, list) or len(api_hints) < 2:
            errors.append(f"{label}: api_hints needs at least two entries")
        else:
            code = str(item.get("code", ""))
            for index, hint in enumerate(api_hints):
                if not isinstance(hint, dict):
                    errors.append(f"{label}: api_hints[{index}] must be an object")
                    continue
                for field in ("symbol", "syntax", "use"):
                    value = hint.get(field)
                    if not isinstance(value, str) or not value.strip():
                        errors.append(f"{label}: api_hints[{index}].{field} is empty")
                symbol = str(hint.get("symbol", "")).split(".")[-1].strip("()<>[]")
                # Identifiers can be checked mechanically. Operators, syntax forms,
                # and descriptive constructs (for example "slice assignment") are
                # validated through their non-empty syntax field instead; treating
                # those labels as identifiers would reject useful Python teaching.
                if (
                    re.fullmatch(r"[A-Za-z_]\w*", symbol)
                    and symbol not in code
                    and symbol not in {"for", "if", "with", "in"}
                ):
                    errors.append(f"{label}: API symbol {symbol!r} is absent from code")
        tests = item.get("tests")
        if not isinstance(tests, list) or len(tests) < 2:
            errors.append(f"{label}: tests needs at least two executable cases")
        else:
            for index, test in enumerate(tests):
                if not isinstance(test, dict):
                    errors.append(f"{label}: tests[{index}] must be an object")
                    continue
                if test.get("kind") not in {"method", "mutate", "design"}:
                    errors.append(f"{label}: tests[{index}] has invalid kind")
                elif test.get("kind") == "design":
                    if not isinstance(test.get("operations"), list):
                        errors.append(f"{label}: design test needs operations")
                else:
                    if not isinstance(test.get("call"), str):
                        errors.append(f"{label}: method test needs call")
                    if not isinstance(test.get("expected"), str):
                        errors.append(f"{label}: method test needs expected")
    return errors


def language_panel(language: str, markdown_body: str, extra_class: str = "") -> str:
    """Return an explicit DOM language container parsed as Markdown."""
    classes = "language-panel" + (f" {extra_class}" if extra_class else "")
    return (
        f'<section class="{html.escape(classes, quote=True)}" '
        f'data-lang-scope="true" data-lang="{html.escape(language, quote=True)}" markdown="1">\n\n'
        + markdown_body.strip()
        + "\n\n</section>"
    )


def legacy_teaching_panel(markdown_body: str, extra_class: str = "") -> str:
    """Wrap Java-derived teaching shared by Java/C++/Go/C, hidden only in Python.

    This intentionally has no data-lang: the language runtime sees it as legacy
    teaching outside the switchable code panels.  Java implementation headings
    inside it are still wrapped as data-lang="java" later by the HTML builder.
    """
    classes = "legacy-solution-panel" + (f" {extra_class}" if extra_class else "")
    return (
        f'<section class="{html.escape(classes, quote=True)}" '
        'data-hide-in-language="python" data-legacy-scope="true" markdown="1">\n\n'
        + markdown_body.strip()
        + "\n\n</section>"
    )


def _badge(key: str, value: str, class_name: str = "mb") -> str:
    return (
        f'<span class="{class_name}"><span class="mb-k">{html.escape(key)}</span>'
        f'<b>{html.escape(value)}</b></span>'
    )


def problem_metadata_html(problem: dict[str, object], python: dict[str, Any]) -> str:
    """Render common difficulty plus Java/Python method metadata groups."""
    difficulty = str(problem.get("difficulty", "中等"))
    common = (
        '<div class="meta-badges problem-meta-common" aria-label="公共题目信息">'
        + _badge("难度", difficulty, f"mb diff-{difficulty}")
        + "</div>"
    )
    legacy = (
        '<div class="meta-badges problem-meta legacy-problem-meta" '
        'data-hide-in-language="python" aria-label="Java 及同源语言解题信息">'
        + _badge("Java 主方法", str(problem["method"]))
        + _badge("时间", str(problem["time"]))
        + _badge("空间", str(problem["space"]))
        + "</div>"
    )
    python_meta = (
        '<div class="meta-badges problem-meta" data-lang-scope="true" data-lang="python" '
        'aria-label="Python 解题信息">'
        + _badge("Python 主方法", str(python["method"]))
        + _badge("时间", str(python["time"]))
        + _badge("空间", str(python["space"]))
        + "</div>"
    )
    return "\n\n".join((common, legacy, python_meta))


def render_python_problem_panel(item: dict[str, Any]) -> str:
    # Keep the authored example and its sequence of state changes intact.
    # Short metadata remains available for catalogs and validation, rather than
    # forcing each explanation into the same three-sentence template.
    source = html.escape(str(item["source"]).strip())
    source_note = "\n".join(
        "> " + html.escape(line) for line in str(item["source_note"]).strip().splitlines()
    )
    markdown = f"""## Python 完整推导

{str(item['teaching_markdown']).strip()}

### Python 实现

> 参考来源：{source}
>
{source_note}

```python
{str(item['code']).rstrip()}
```

{str(item['explanation_markdown']).strip()}

### 复杂度

- 时间复杂度：`{str(item['time'])}`。
- 空间复杂度：`{str(item['space'])}`。

{str(item['complexity_reason']).strip()}"""
    return language_panel("python", markdown)


def render_python_topic_panel(
    category: str,
    item: dict[str, Any],
    problem_curriculum: dict[int, dict[str, Any]] | None = None,
    problem_links: dict[int, str] | None = None,
) -> str:
    teaching_markdown = str(item.get("teaching_markdown", "")).strip()
    if not teaching_markdown:
        workflow = "\n".join(
            f"{index}. {str(step).strip()}"
            for index, step in enumerate(item["workflow"], start=1)
        )
        teaching_markdown = (
            "### 解题框架\n\n"
            + str(item["summary"]).strip()
            + "\n\n### 推导重点\n\n"
            + f"- **状态语义**：{str(item['invariant_reason']).strip()}\n"
            + f"- **Python 取舍**：{str(item['why_python']).strip()}\n\n"
            + "### 下笔顺序\n\n"
            + workflow
        )
    explanation_markdown = str(item.get("explanation_markdown", "")).strip()
    template_source = str(item.get("template_source", "")).strip()
    template_note = str(item.get("template_note", "")).strip()
    if problem_curriculum:
        problem_rows = [
            "| 题目 | Python 主方法 | 时间 | 空间 | 本题抓手 |",
            "|---|---|---|---|---|",
        ]
        for row in item.get("problem_focus", []):
            problem_id = int(row["id"])
            curriculum = problem_curriculum[problem_id]
            href = (problem_links or {}).get(problem_id)
            label = f"{problem_id}. {str(row['title'])}"
            linked = f"[{label}]({href})" if href else label
            problem_rows.append(
                f"| **{linked}** | {curriculum['method']} | {curriculum['time']} | "
                f"{curriculum['space']} | {str(row['focus']).strip()} |"
            )
        problem_lines = "\n".join(problem_rows)
    else:
        problem_lines = "\n".join(
            f"- **{int(row['id'])}. {str(row['title'])}**：{str(row['focus']).strip()}"
            for row in item.get("problem_focus", [])
        )
    source_line = f"> 参考来源：{template_source}\n" if template_source else ""
    note_block = f"{template_note}\n\n" if template_note else ""
    explanation_block = f"\n\n{explanation_markdown}" if explanation_markdown else ""
    markdown = f"""## Python 模式：{category}

{str(item['summary']).strip()}

{teaching_markdown}

### Python 模板：{str(item['template_name']).strip()}

{note_block}{source_line}

```python
{str(item['template']).rstrip()}
```
{explanation_block}

### 本专题逐题抓手

{problem_lines}"""
    return language_panel("python", markdown, extra_class="python-topic-panel")


def render_python_template_markdown(topic_curriculum: dict[str, dict[str, Any]]) -> str:
    parts = [
        "## Python 算法模板",
        (
            "下列 17 段模板各自对应一个可执行的代表例子。"
            "模板用于对照变量如何移动；换题时要按题意重新定义键、区间和状态，"
            "不能只替换函数名。"
        ),
    ]
    for category, item in topic_curriculum.items():
        parts.extend(
            [
                f"### {category}：{str(item['template_name'])}",
                "",
                str(item["summary"]).strip(),
                "",
                f"> 参考来源：{str(item['template_source']).strip()}",
                "",
                str(item["template_note"]).strip(),
                "",
                "```python",
                str(item["template"]).rstrip(),
                "```",
            ]
        )
    return "\n".join(parts)


def render_python_basic_panel(item: dict[str, Any]) -> str:
    teaching_markdown = str(item.get("teaching_markdown", "")).strip()
    if not teaching_markdown:
        concepts = []
        for concept in item["concepts"]:
            concepts.extend(
                [
                    f"### {str(concept['heading']).strip()}",
                    "",
                    str(concept["body"]).strip(),
                    "",
                ]
            )
        teaching_markdown = "\n".join(concepts).strip()
    explanation_markdown = str(item.get("explanation_markdown", "")).strip()
    api_rows = [
        "| 操作 | 示例 | 在示例中的用途 |",
        "|---|---|---|",
    ]
    api_rows.extend(
        f"| `{str(hint['symbol'])}` | `{str(hint['syntax'])}` | {str(hint['use'])} |"
        for hint in item["api_hints"]
    )
    explanation_block = f"\n\n{explanation_markdown}" if explanation_markdown else ""
    markdown = f"""## Python 模式：{str(item['title'])}

{str(item['summary']).strip()}

{teaching_markdown}

### 可运行示例：{str(item['template_name'])}

```python
{str(item['template']).rstrip()}
```
{explanation_block}

### 常用操作

{chr(10).join(api_rows)}"""
    return language_panel("python", markdown, extra_class="python-basic-panel")
