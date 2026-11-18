"""Build supplement solutions with the Hot 100 reader and interactive example kit."""

import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import quote

MODULE_ID = "hot200-extra"
FENCE = re.compile(r"^```([\w+#-]*)[^\S\n]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)


def sections(markdown):
    """Split authoring sections without mistaking comments inside code for headings."""
    result = {}
    lines = []
    heading = ""
    fence = False
    for line in markdown.splitlines():
        if line.startswith("```"):
            fence = not fence
        if not fence and line.startswith("### "):
            result[heading] = "\n".join(lines).strip()
            heading, lines = line[4:].strip(), []
        else:
            lines.append(line)
    result[heading] = "\n".join(lines).strip()
    return result


def prepare_body(markdown, problem, existing_path):
    parts = sections(markdown)
    sources = parts["来源"].replace("](/library/hot200-extra/", "](").replace(
        "](/books/company-solutions/", "](../../books/company-solutions/")
    if existing_path and "../../books/company-solutions/" not in sources:
        href = quote(existing_path.with_suffix(".html").as_posix(), safe="/")
        sources += f' · [本站企业高频题解](../../{href})'
    intro = [
        f"# {problem['id']}. {problem['title']}",
        ("| 题目信息 | 内容 |\n| --- | --- |\n"
        f"| 难度 | {problem['difficulty']} |\n| 专题 | {problem['topic']} |\n"
        f"| 题单位置 | 第 {problem['position']} 位 |"),
    ]
    for language in ("Java", "Python"):
        method = re.search(r"^#### (.+)$", parts[language], re.MULTILINE)
        if not method:
            raise ValueError(f"LC {problem['id']}: missing {language} method heading")
        intro.append(
            f'<div class="meta-badges problem-meta" data-lang-scope="true" data-lang="{language.lower()}">'
            f'<span class="mb"><span class="mb-k">{language} 主方法</span><b>{html.escape(method[1].replace(chr(96), ""))}</b></span>'
            f'<span class="mb"><span class="mb-k">复杂度</span><b>{html.escape(parts["复杂度"].splitlines()[0].replace(chr(96), ""))}</b></span></div>'
        )
    intro.extend(["## 题目与约束", parts["题意"], parts["输入与约束"], "### 示例", parts["示例"],
                  f"[🔗 前往力扣原题验证 →](https://leetcode.cn/problems/{problem['slug']}/)"])
    for language in ("Java", "Python"):
        lang = language.lower()
        text = parts[language]
        fences = list(FENCE.finditer(text))
        if len(fences) != 1 or fences[0][1].lower() != lang:
            raise ValueError(f"LC {problem['id']}: expected one {language} implementation")
        code = fences[0]
        before = text[:code.start()].strip()
        after = text[code.end():].strip()
        if not before:
            raise ValueError(f"LC {problem['id']}: missing {language} derivation")
        intro.extend([
            f'<section class="language-panel {lang}-solution-panel" data-lang="{lang}" markdown="1">',
            f"## {language} 完整推导", "### 核心不变量", parts["核心不变量"],
            "### 思路推导", parts["思路"], before,
            f"### {language} 实现", code.group(), after,
            "### 复杂度", parts["复杂度"], "### 易错点", parts["边界检查"],
            "### 反例推演", parts["反例推演"],
            "### 面试追问", parts["面试追问"], "</section>",
        ])
    intro.extend(["## 力扣原题", sources])
    return "\n\n".join(filter(None, intro)), parts["示例"]


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
    def versioned(path):
        content = (root / path).read_text(encoding="utf-8")
        stamp = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
        return f"../../../{path}?v={stamp}"

    kit = versioned("books/hot100/05-可视化/assets/demo-kit.js")
    player = versioned("assets/hot200-example.js")
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
        manuscript = source.read_text(encoding="utf-8-sig")
        body, example = prepare_body(manuscript, entry,
                            company.relative_to(root) if company else None)
        trace_path = root / f"books/hot200-extra/traces/{number}.json"
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        if not isinstance(trace, list) or len(trace) < 3 or not all(
            isinstance(frame, dict)
            and all(isinstance(frame.get(k), str) and frame[k].strip() for k in ("label", "state", "why"))
            and isinstance(frame.get("cells"), list) and frame["cells"]
            and all(isinstance(cell, str) and cell.strip() for cell in frame["cells"])
            for frame in trace
        ):
            raise ValueError(f"LC {number}: incomplete example trace")
        lines = FENCE.search(sections(manuscript)["Python"])[2].splitlines()
        numbered = {f"{i:>2}  {line}" for i, line in enumerate(lines, 1) if line.strip()}
        for frame in trace:
            if not isinstance(frame.get("code"), list) or not frame["code"] or any(
                line not in numbered for line in frame["code"]
            ):
                raise ValueError(f"LC {number}, {frame['label']}: stale Python source excerpt")
        chapters.append({
            "title": f"LC {number} · {entry['title']}", "body": body, "category": entry["topic"],
            "difficulty": entry["difficulty"], "position": entry["position"],
            "trace": trace, "example": example, "number": number,
            "demo_scripts": [kit, versioned(f"books/hot200-extra/executions/{number}.js"), player],
            "content_id": f"{MODULE_ID}:{number:04d}",
        })
        modified = max(modified, source.stat().st_mtime)
    digest = hashlib.sha256(json.dumps(chapters, ensure_ascii=False).encode())
    for renderer in (Path(__file__), Path(__file__).with_name("build_html_site.py")):
        digest.update(renderer.read_text(encoding="utf-8").encode())
    return chapters, digest.hexdigest(), modified


def render_demo(module_dir, chapter):
    number = chapter["number"]
    demo_dir = module_dir / "demos"
    demo_dir.mkdir(exist_ok=True)
    demo_name = f"{number}.html"
    payload = json.dumps({"no": str(number), "title": chapter["title"].split(" · ", 1)[1], "tag": chapter["category"],
                          "example": chapter["example"], "frames": chapter["trace"]}, ensure_ascii=False)
    payload = payload.replace("<", "\\u003c")
    demo = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{html.escape(chapter["title"])} · 交互演示</title></head><body>'
        '<div id="app"></div><script type="application/json" id="problemExample">'
        + payload + '</script>'
        + ''.join(f'<script src="{html.escape(url)}"></script>' for url in chapter["demo_scripts"])
        + '</body></html>'
    )
    (demo_dir / demo_name).write_text(demo, encoding="utf-8")
    return demo_name


def render_problem(root, module_dir, chapters, index):
    from scripts.build.build_html_site import SolutionCollectionPage, render_markdown

    chapter = chapters[index]
    number = chapter["number"]
    source = root / f"books/hot200-extra/solutions/{number}.md"
    filename = f"chapter-{index + 1:02d}.html"
    demo_name = render_demo(module_dir, chapter)
    siblings = [(f"chapter-{j + 1:02d}.html", other["title"], j == index)
                for j, other in enumerate(chapters) if other["category"] == chapter["category"]]
    nav = ['<a href="index.html">返回题目面板</a>']
    for step, label in ((-1, "上一题"), (1, "下一题")):
        j = index + step
        if 0 <= j < len(chapters):
            nav.append(f'<a href="chapter-{j+1:02d}.html">{label} · {html.escape(chapters[j]["title"])}</a>')
    controls = '<!--bottom-nav--><div class="problem-nav">' + "".join(nav) + '</div><!--/bottom-nav-->'
    collection = SolutionCollectionPage(MODULE_ID, "Hot 200 面板", chapter["category"], number,
                                        chapter["content_id"], "java python", siblings, f"demos/{demo_name}?embed=1")
    render_markdown(source, output=module_dir / filename, raw=chapter["body"] + "\n\n" + controls,
                    collection=collection)
