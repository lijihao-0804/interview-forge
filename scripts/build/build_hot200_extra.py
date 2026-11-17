"""Prepare the Hot 200 supplement for the regular library chapter renderer."""

import hashlib
import html
import json
import re
from urllib.parse import quote


MODULE_ID = "hot200-extra"
LIST_URL = "https://leetcode.cn/problem-list/qg88wci/"
FENCE = re.compile(r"^```([\w+#-]*)[^\S\n]*\n(.*?)^```[ \t]*$", re.M | re.S)
IMPLEMENTATION_HEADING = re.compile(
    r"(?im)^#{2,6}\s+(?:Java(?!Script)|Python|C\+\+|Go|C|Rust|JavaScript)\b[^\n]*\n*\Z"
)


def prepare_body(markdown, problem, existing_path):
    """Keep explanatory prose and the two actual implementations, with source links."""
    markdown = re.sub(r"\]\(/(?:books|library)/hot200-extra/LICENSE-walkccc\.txt\)",
                      "](LICENSE-walkccc.txt)", markdown)
    # Authored source citations are site-root links; chapters also work via file://.
    markdown = markdown.replace("](/books/company-solutions/", "](../../books/company-solutions/")
    markdown, _, attribution = markdown.partition("\n### 来源\n")
    code = {}
    parts = []
    cursor = 0
    for match in FENCE.finditer(markdown):
        before = markdown[cursor:match.start()]
        lang = match[1].lower()
        if lang in {"java", "python", "cpp", "go", "c", "rust", "javascript"}:
            before = IMPLEMENTATION_HEADING.sub("", before)
            if lang in {"java", "python"}:
                if lang in code or not match[2].strip():
                    raise ValueError(f"LC {problem['id']}: ambiguous or empty {lang} solution")
                code[lang] = match.group()
            parts.append(before)
        else:
            parts.extend([before, match.group()])
        cursor = match.end()
    if set(code) != {"java", "python"}:
        raise ValueError(f"LC {problem['id']}: both Java and Python implementations are required")
    parts.append(markdown[cursor:])
    prose = re.sub(r"(?m)^# [^\n]+\n", "", "".join(parts), count=1).strip()
    prose, _, complexity = prose.partition("\n### 复杂度\n")
    panels = []
    for lang, label in (("java", "Java"), ("python", "Python")):
        panels.append(f'<section class="language-panel" data-lang="{lang}" markdown="1">\n\n'
                      f'### {label} 实现\n\n{code[lang]}\n\n</section>')
    original = f"https://leetcode.cn/problems/{problem['slug']}/"
    sources = [attribution.strip()] if attribution.strip() else []
    if original not in attribution:
        sources.append(f'[力扣原题 · {problem["title"]}]({original})')
    if existing_path and "../../books/company-solutions/" not in attribution:
        href = quote(existing_path.with_suffix(".html").as_posix(), safe="/")
        sources.append(f'<a href="../../{href}">本站企业高频题解</a>')
    return "\n\n".join([prose.strip(), "## 参考实现", *panels, "### 复杂度", complexity.strip(),
                       "## 题目来源", "\n\n".join(sources)])


def load_chapters(root, hot100_ids):
    manifest = root / "data/hot200-extra.json"
    problems = json.loads(manifest.read_text(encoding="utf-8"))
    ids = [entry["id"] for entry in problems]
    if len(ids) != 100 or len(set(ids)) != 100 or set(ids) & set(hot100_ids):
        raise ValueError("Hot 200 supplement must contain 100 distinct additions to the original Hot 100")
    if [entry["position"] for entry in problems] != list(range(101, 201)):
        raise ValueError("Expected positions 101–200 in official list order")
    company_dir = root / "books/company-solutions"
    company_sources = {
        int(path.name.split("-", 1)[0]): path
        for path in company_dir.glob("*/*.md") if re.match(r"^\d+-", path.name)
    }
    chapters = []
    modified = manifest.stat().st_mtime
    for entry in problems:
        number = entry["id"]
        if (type(number) is not int or number < 1 or not re.fullmatch(r"[a-z0-9-]+", entry["slug"])
                or not entry["title"].strip() or not entry["topic"].strip()
                or entry["difficulty"] not in {"简单", "中等", "困难"}):
            raise ValueError(f"Invalid Hot 200 entry: {entry!r}")
        company = company_sources.get(number)
        source = root / f"books/hot200-extra/solutions/{number}.md"
        if company and not company.with_suffix(".html").is_file():
            raise FileNotFoundError(company.with_suffix(".html"))
        body = prepare_body(source.read_text(encoding="utf-8-sig"), entry,
                            company.relative_to(root) if company else None)
        chapters.append({
            "title": f"LC {number} · {entry['title']}", "body": body, "category": entry["topic"],
            "difficulty": entry["difficulty"], "position": entry["position"],
            "content_id": f"{MODULE_ID}:{number:04d}",
        })
        modified = max(modified, source.stat().st_mtime)
    digest = hashlib.sha256(json.dumps(chapters, ensure_ascii=False).encode()).hexdigest()
    return chapters, digest, modified


def reader_content(content, chapter):
    meta = (f'原题单第 {chapter["position"]} 题 · {html.escape(chapter["category"])}'
            f' · {html.escape(chapter["difficulty"])}')
    return (f'<p class="problem-meta">{meta}</p><div class="markdown-body" '
            f'data-solution-languages="java python">{content}</div>')


DIRECTORY_SOURCE = (
    '<p><a href="../../index.html">← Hot 100 题目面板</a>'
    f' · <a href="{LIST_URL}">力扣精选算法 200 题 · 官方题单</a>'
    ' · <a href="LICENSE-walkccc.txt">参考代码许可</a></p>'
)
