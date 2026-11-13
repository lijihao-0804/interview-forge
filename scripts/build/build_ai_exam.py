"""生成 AI 岗机试真题库：索引页 + 每道题独立阅读页。

数据来源：
  1) assets/ai-exam-coding.json —— 2026 大厂 AI/算法岗机试 132 题；
  2) books/外部面经参考/02-AI与Agent手撕代码题.md —— 12 道 AI/Agent 手撕题；
  3) books/company-oj/*/*.md —— 既有企业机考真题（Java，索引只链到原页面）。

生成结构：
  books/ai-exam/index.html
  books/ai-exam/ai-2026/<company>/<NNN>-<title>.html
  books/ai-exam/ai-agent/<NN>-<title>.html
"""
from __future__ import annotations

import json
import re
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.build.build_html_site import render_markdown  # noqa: E402
from scripts.build.acm_samples import append_cases, merge_reviewed_cases  # noqa: E402
from scripts.build.acm_fixes import apply_reviewed_fixes  # noqa: E402

SRC = ROOT / "books" / "ai-exam"
CODING = ROOT / "assets" / "ai-exam-coding.json"
AGENT_DOC = ROOT / "books" / "外部面经参考" / "02-AI与Agent手撕代码题.md"
COMPANY_OJ = ROOT / "books" / "company-oj"
TRANSLATIONS = ROOT / "data" / "ai_exam" / "translations.json"
EXTRA_SAMPLES = ROOT / "data" / "ai_exam" / "practice-extra-samples.json"

STYLE = """
 body{background:var(--page-bg)}
 .exam-shell{width:calc(100% - 100px);max-width:1180px;margin:auto;padding:24px 0 64px}
 .exam-tools{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:0 0 14px}
 .exam-search{width:100%;max-width:380px;padding:9px 14px;border:1px solid var(--line);border-radius:10px;font:inherit;background:var(--surface)}
 .exam-select{padding:9px 12px;border:1px solid var(--line);border-radius:10px;font:inherit;background:var(--surface)}
 .exam-layout{display:grid;grid-template-columns:200px minmax(0,1fr);gap:26px;align-items:start}
 .exam-nav{position:sticky;top:14px;display:flex;flex-direction:column;gap:3px;padding:12px;border:1px solid var(--line);border-radius:14px;background:var(--surface)}
 .exam-nav a{display:flex;justify-content:space-between;padding:6px 9px;border-radius:7px;color:var(--text);text-decoration:none;font-size:13px}
 .exam-nav a:hover{background:var(--surface-soft);color:var(--brand)}
 .exam-nav a span{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
 details.exam-group{margin:0 0 12px;border:1px solid var(--line);border-radius:14px;background:var(--surface)}
 details.exam-group>summary{cursor:pointer;padding:14px 20px;font-size:16px;font-weight:650;list-style:none}
 details.exam-group>summary::-webkit-details-marker{display:none}
 details.exam-group>summary::before{content:"\\25B8";display:inline-block;margin-right:8px;color:var(--muted);transition:transform .15s}
 details.exam-group[open]>summary::before{transform:rotate(90deg)}
 details.exam-group>summary small{margin-left:8px;color:var(--muted);font-size:12px;font-weight:400}
 .exam-sub{font-size:13px;color:var(--muted);margin:0 20px 7px}
 .exam-list{list-style:none;margin:0;padding:0 20px 16px;display:grid;grid-template-columns:1fr 1fr;gap:2px 18px}
 .exam-list li{padding:6px 0;border-bottom:1px dashed #eef0f6;min-width:0}
 .exam-list a{color:var(--text);text-decoration:none;font-size:13.5px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .exam-list a:hover{color:var(--brand)}
 .exam-list .meta{font-size:11.5px;color:var(--muted);margin-left:5px}
 .exam-empty{padding:30px 0;text-align:center;color:var(--muted)}
 @media(max-width:900px){.exam-shell{width:calc(100% - 24px)}.exam-layout{grid-template-columns:1fr}.exam-nav{position:static;flex-direction:row;flex-wrap:wrap}details.exam-group .exam-list{grid-template-columns:1fr}}
"""

SEARCH_JS = """<script>(function(){var q=document.getElementById('q'),company=document.getElementById('company');
function apply(){var v=(q&&q.value.trim().toLowerCase())||'',cv=(company&&company.value)||'';
document.querySelectorAll('.exam-group').forEach(function(g){var n=0;
g.querySelectorAll('li[data-k]').forEach(function(li){
var ok=(!v||li.getAttribute('data-k').toLowerCase().indexOf(v)>=0)&&(!cv||li.getAttribute('data-company')===cv);
li.style.display=ok?'':'none';if(ok)n++;});
var empty=g.querySelector('.exam-empty');if(empty)empty.hidden=!!n;
g.style.display=(v||cv)&&!n?'none':'';if((v||cv)&&n)g.open=true;});}
if(q)q.oninput=apply;if(company)company.onchange=apply;})();</script>"""


def esc(value: object) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def safe_name(value: str, limit: int = 34) -> str:
    value = re.sub(r'[\\/:*?"<>|#\n\r\t]', "", value).strip()
    value = re.sub(r"\s+", "-", value)
    return value[:limit] or "题目"


def load_translations() -> dict[str, dict[str, str]]:
    """读取 data/ai_exam/translations.json；文件由翻译批次合并生成。"""
    if not TRANSLATIONS.exists():
        return {}
    raw = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "translations" in raw:
        entries = raw["translations"]
    elif isinstance(raw, list):
        entries = raw
    else:
        return {}
    result: dict[str, dict[str, str]] = {}
    for item in entries:
        key, lang, code = item.get("key"), item.get("target_lang"), item.get("code")
        if key and lang and code:
            result.setdefault(key, {})[lang] = code
    return result


def format_text(text: str) -> str:
    """把源数据里的显式换行变成 Markdown 分段，同时完整保留 \\[...\\] 公式块。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"(\\\[.*?\\\]|\\\(.*?\\\)|\$\$.*?\$\$)", text, flags=re.S)
    paragraphs: list[str] = []
    for part in parts:
        if not part:
            continue
        if re.fullmatch(r"\\\[.*?\\\]|\\\(.*?\\\)|\$\$.*?\$\$", part, flags=re.S):
            body = part.strip()
            if body.startswith("\\["):
                # Markdown 会转义 \[ 的反斜杠；改成同一行 $$...$$，交给统一公式渲染。
                body = body[2:-2]
                body = re.sub(r"\s+", " ", body).strip()
                paragraphs.append(f"$${body}$$")
            elif body.startswith("\\("):
                body = body[2:-2].strip()
                paragraphs.append(f"${body}$")
            else:
                paragraphs.append(body)
            continue
        for line in part.split("\n"):
            line = re.sub(r"[ \t]+", " ", line).strip()
            if line:
                paragraphs.append(line)
    return "\n\n".join(paragraphs)


def format_java_code(code: str) -> str:
    """部分远程题解只给出一行压缩 Java；这里补上换行和缩进。

    只处理明显压缩成单行的 Java，保留已经是多行的代码原样。
    """
    code = code.strip()
    if not code or code.count("\n") >= 2:
        return code
    out: list[str] = []
    indent = 0
    paren = 0
    i = 0
    n = len(code)

    def newline() -> None:
        while out and out[-1] in (" ", "\t"):
            out.pop()
        out.append("\n" + "    " * indent)

    while i < n:
        ch = code[i]
        if ch in ('"', "'"):
            quote = ch
            out.append(ch)
            i += 1
            while i < n:
                out.append(code[i])
                if code[i] == "\\" and i + 1 < n:
                    out.append(code[i + 1])
                    i += 2
                    continue
                if code[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if ch == "/" and i + 1 < n and code[i + 1] == "/":
            while i < n and code[i] != "\n":
                out.append(code[i])
                i += 1
            newline()
            continue
        if ch == "{":
            while out and out[-1] in (" ", "\t"):
                out.pop()
            if out and out[-1] not in (" ", "\n"):
                out.append(" ")
            out.append("{")
            indent += 1
            i += 1
            while i < n and code[i] in " \t":
                i += 1
            newline()
            continue
        if ch == "}":
            while out and out[-1] in (" ", "\t"):
                out.pop()
            indent = max(0, indent - 1)
            if out and out[-1] != "\n":
                newline()
            out.append("}")
            i += 1
            while i < n and code[i] in " \t":
                i += 1
            if re.match(r"(else|catch|finally)\b", code[i:]):
                out.append(" ")
            else:
                newline()
            continue
        if ch == ";":
            out.append(";")
            i += 1
            if paren == 0:
                newline()
            continue
        if ch == "(":
            paren += 1
            out.append(ch)
            i += 1
            continue
        if ch == ")":
            paren = max(0, paren - 1)
            out.append(ch)
            i += 1
            continue
        if ch in " \t\r\n":
            if out and out[-1] not in (" ", "\n"):
                out.append(" ")
            i += 1
            continue
        out.append(ch)
        i += 1
    text = "".join(out)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]*\n+", "\n", text)
    return text.strip()


def infer_algorithm(code: str) -> str:
    low = code.lower()
    if "pre" in low and "prev" in low and "cur" in low:
        return "动态规划（前缀和 + 滚动数组）"
    if "prev" in low and "cur" in low:
        return "动态规划（滚动数组）"
    if "dp[" in low or "dp =" in low or "memo" in low:
        return "动态规划"
    if "heapq" in low or "priorityqueue" in low:
        return "堆 / 优先队列"
    if "deque" in low and ("bfs" in low or "queue" in low):
        return "BFS / 队列"
    if "dfs" in low:
        return "DFS / 回溯"
    if "bisect" in low:
        return "二分查找"
    if "sort" in low or "sorted" in low:
        return "排序 + 扫描"
    return "按题意模拟"


def annotate_code(code: str, lang: str, title: str) -> str:
    """在关键语句前补行内注释，避免只有文件头注释。"""
    marker = "#" if lang == "python" else "//"
    special = {}
    if "最优流水线并行切分" in title:
        if lang == "python":
            special = {
                "pre = [0]": "前缀和：pre[i] 表示前 i 层计算耗时之和",
                "prev = [inf]": "prev[b]：前 b 层分成 j-1 段时的最小瓶颈",
                "cur = [inf]": "当前阶段 j 的 DP 行",
                "for j in range": "枚举阶段数 j",
                "for i in range": "枚举前 i 层",
                "comm = s[i - 1]": "当前段末尾需要支付的通信耗时",
                "for b in range": "枚举最后一段的起点 b",
                "candidate = max": "当前切法的瓶颈 = max(前缀瓶颈, 最后一段耗时)",
                "return prev[n]": "返回恰好 K 段覆盖 N 层的最优值",
            }
        else:
            special = {
                "long[] pre=new long": "前缀和：pre[i] 表示前 i 层计算耗时之和",
                "long[] prev=new long": "prev[b]：前 b 层分成 j-1 段时的最小瓶颈",
                "long[] cur=new long": "当前阶段 j 的 DP 行",
                "for(int j=": "枚举阶段数 j",
                "for(int i=": "枚举前 i 层",
                "int comm=": "当前段末尾需要支付的通信耗时",
                "for(int b=": "枚举最后一段的起点 b",
                "long cand=Math.max": "当前切法的瓶颈 = max(前缀瓶颈, 最后一段耗时)",
                "return prev[n]": "返回恰好 K 段覆盖 N 层的最优值",
            }
    out = []
    for line in code.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(marker):
            out.append(line)
            continue
        indent = line[: len(line) - len(line.lstrip())]
        comment = ""
        for needle_text, text in special.items():
            if needle_text in stripped:
                comment = text
                break
        if not comment and lang == "python":
            m = re.match(r"def\s+(\w+)", stripped)
            if m:
                if m.group(1) != "solve":
                    comment = f"核心函数：{m.group(1)}"
            elif re.match(r"for\s+(\w+)\s+in", stripped):
                var = re.match(r"for\s+(\w+)", stripped).group(1)
                comment = {"i": "枚举位置 i", "j": "枚举阶段 j", "b": "枚举分割点 b"}.get(var, f"遍历 {var}")
            elif re.match(r"while\s", stripped):
                comment = "循环处理"
            elif re.match(r"(if|elif)\s", stripped) and not stripped.startswith("if __name__"):
                comment = "条件判断"
            elif stripped.startswith("return"):
                comment = "返回结果"
        elif not comment:
            m = re.match(r"(?:public\s+)?static\s+[^\n]+?\s+(\w+)\s*\(", stripped)
            if m and m.group(1) != "main":
                comment = f"核心方法：{m.group(1)}"
            elif re.match(r"for\s*\(", stripped):
                mvar = re.search(r"for\s*\(\s*(?:int|long|var)\s+(\w+)", stripped)
                var = mvar.group(1) if mvar else ""
                comment = {"i": "枚举位置 i", "j": "枚举阶段 j", "b": "枚举分割点 b"}.get(var, "循环处理")
            elif re.match(r"while\s*\(", stripped):
                comment = "循环处理"
            elif re.match(r"if\s*\(", stripped):
                comment = "条件判断"
            elif stripped.startswith("return"):
                comment = "返回结果"
        if comment:
            out.append(indent + marker + " " + comment)
        out.append(line)
    return "\n".join(out)


def add_code_comments(code: str, lang: str, title: str, sections: list[dict]) -> str:
    """给题解代码加简短、准确的 ACM/算法/复杂度注释，不改动原有代码逻辑。"""
    marker = "#" if lang == "python" else "//"
    complexity = ""
    for section in sections:
        if "复杂度" in (section.get("heading") or ""):
            complexity = re.sub(r"\s+", " ", (section.get("text") or "").strip())
            break
    def clean_comment(value: str) -> str:
        value = re.sub(r"\\\[|\\\]|\\\(|\\\)", "", value)
        value = re.sub(r"\\[A-Za-z]+", "", value)
        value = re.sub(r"[{}]", "", value)
        return re.sub(r"\s+", " ", value).strip()

    time_part = space_part = ""
    m = re.search(r"时间复杂度\s*[：:]\s*([^。\n]+)", complexity)
    if m:
        time_part = clean_comment(m.group(1).replace("$", ""))
    m = re.search(r"空间复杂度\s*[：:]\s*([^。\n]+)", complexity)
    if m:
        space_part = clean_comment(m.group(1).replace("$", ""))
    lines = [f"{marker} 题目：{title}", f"{marker} 算法：{infer_algorithm(code)}", f"{marker} 模式：ACM（stdin/stdout）"]
    if time_part:
        suffix = f"；空间 {space_part}" if space_part else ""
        lines.append(f"{marker} 复杂度：时间 {time_part}{suffix}")
    header = "\n".join(lines) + "\n\n"
    if lang == "java":
        code = code.replace("public static void main", "// 主函数：读取输入并输出答案\n    public static void main", 1)
    else:
        code = re.sub(r"(?m)^(def solve\()", lambda m: "# 读取输入并输出答案\n" + m.group(1), code, count=1, flags=re.M)
    return header + annotate_code(code, lang, title)


def write_problem(path: Path, title: str, meta: str, sections: list[dict], translation: dict[str, str] | None = None) -> None:
    lines = [f"# {title}", "", f"> {meta}", ""]
    for section in sections:
        heading = (section.get("heading") or "").strip()
        text = format_text(section.get("text") or "")
        code = (section.get("code") or "").strip()
        if not heading and not text and not code:
            continue
        if heading and heading not in ("题目说明",):
            lines += [f"## {heading}", ""]
        if text:
            lines += [text, ""]
        if code:
            if "代码" in heading or "实现" in heading:
                lines += ["### Python 实现", "", "```python", add_code_comments(code, "python", title, sections), "```", ""]
            else:
                lines += ["```text", code, "```", ""]
    if translation and translation.get("java"):
        java_code = add_code_comments(format_java_code(translation["java"]), "java", title, sections)
        lines += ["### Java 实现", "", "```java", java_code, "```", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def solution_text(problem: dict) -> str:
    for section in problem.get("sections", []):
        heading = section.get("heading", "")
        if ("题解代码" in heading or "Python 代码" in heading or "代码" in heading) and section.get("code"):
            return section["code"].strip()
    codes = [section.get("code", "") for section in problem.get("sections", [])
             if section.get("code") and "样例" not in section.get("heading", "")]
    return max(codes, key=len).strip() if codes else ""


def split_practice_samples(codes: object) -> list[dict[str, str]]:
    """把数据里的 [输入, 输出, 输入, 输出, ..., 题解代码] 拆成样例对。

    只相信明确的成对结构；数量不足或无法成对时返回空列表，绝不虚构样例。
    """
    if not isinstance(codes, list):
        return []
    values = [str(item) for item in codes if isinstance(item, str)]
    if len(values) < 3 or len(values) % 2 == 0:
        return []
    pairs = values[:-1]
    result = []
    for index in range(0, len(pairs) - 1, 2):
        inp, out = pairs[index], pairs[index + 1]
        if inp.strip() or out.strip():
            result.append({"input": inp, "expected": out})
    return result


def practice_entry(entry: dict, *, python_code: str, java_code: str, samples: list[dict[str, str]]) -> dict:
    codes = {}
    if python_code.strip():
        codes["python"] = python_code.strip()
    if java_code.strip():
        codes["java"] = java_code.strip()
    return {
        "id": entry["url"].replace("/", ":"),
        "url": entry["url"],
        "title": entry["title"],
        "codes": codes,
        "samples": samples,
    }


def parse_markdown_samples(text: str) -> list[dict[str, str]]:
    """提取每个示例节的明确输入/输出对，不跨到题解代码中配对。"""
    result = []
    sections = re.finditer(r"^##\s*(?:示例|样例)[^\n]*\n(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    for section in sections:
        pairs = re.finditer(
            r"输入[：:]\s*```[^\n]*\n(.*?)```\s*输出[：:]\s*```[^\n]*\n(.*?)```",
            section.group(1), re.S,
        )
        for match in pairs:
            result.append({"input": match.group(1).strip("\n"), "expected": match.group(2).strip("\n")})
    return result


def parse_markdown_code(text: str, language: str) -> str:
    match = re.search(r"```" + language + r"\s*\n(.*?)```", text, flags=re.S)
    return match.group(1).strip() if match else ""


def write_practice_meta(entries: list[dict]) -> None:
    items = [entry["practice"] for entry in entries if entry.get("practice") and entry["practice"].get("samples")]
    # The reviewed Java overrides are applied to Markdown before rendering.
    # Carry exactly those published programs, rather than stale translations.
    for item in items:
        text = (SRC / item["url"]).with_suffix(".md").read_text(encoding="utf-8")
        for language in ("python", "java"):
            code = parse_markdown_code(text, language)
            if code:
                item["codes"][language] = code
    (SRC / "practice-meta.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def apply_extra_samples(entries: list[dict]) -> None:
    """追加人工样例，保留题面样例；相同输入输出只收录一次。"""
    if not EXTRA_SAMPLES.exists():
        return
    data = json.loads(EXTRA_SAMPLES.read_text(encoding="utf-8"))
    extras = data.get("items", data)
    if not isinstance(extras, dict):
        return
    by_url = {entry["url"]: entry for entry in entries}
    for url, samples in extras.items():
        entry = by_url.get(url)
        if not entry or not entry.get("practice") or not isinstance(samples, list):
            continue
        append_cases(entry["practice"], samples, source="supplemental")



def build_ai_coding(translations: dict[str, dict[str, str]]) -> list[dict]:
    data = json.loads(CODING.read_text(encoding="utf-8"))
    entries = []
    for problem in data["problems"]:
        code = solution_text(problem)
        # 少量页面把“选择题答案 print("C")”误当成了编程题；ACM 题库不收录这种伪代码。
        if not code or (not re.search(r"(?m)^\s*(def|class|import|from|if __name__)", code) and len(code) < 40):
            continue
        company = problem["company"]
        date = problem["date"]
        role = problem["role"]
        file_dir = SRC / "ai-2026" / company
        filename = f"{len(entries) + 1:03d}-{safe_name(problem['title'])}.md"
        md_path = file_dir / filename
        source_url = (problem.get("source_url") or "").strip()
        source_link = (
            f'<a href="{escape(source_url)}" target="_blank" rel="noopener noreferrer">原题解析</a>'
            if source_url else "来源：未标注"
        )
        meta = f"{source_link} · {company} · {date or '日期未标注'} · {role or 'AI岗'} · ACM 模式（stdin/stdout）"
        translation = translations.get(problem["key"], {})
        write_problem(md_path, problem["title"], meta, problem.get("sections", []), translation)
        languages = "Python/Java" if translation.get("java") else "Python"
        entry = {
            "group": "ai-2026",
            "title": problem["title"],
            "company": company,
            "date": date,
            "role": role,
            "lang": languages,
            "url": f"ai-2026/{company}/{filename[:-3]}.html",
            "key": f"{company} {problem['title']} {languages}",
        }
        entry["practice"] = practice_entry(
            entry,
            python_code=solution_text(problem),
            java_code=str(translation.get("java") or ""),
            samples=split_practice_samples(problem.get("codes")),
        )
        entries.append(entry)
    return entries


def build_agent_doc(translations: dict[str, dict[str, str]]) -> list[dict]:
    text = AGENT_DOC.read_text(encoding="utf-8")
    matches = list(re.finditer(r"(?m)^### 题目\s*(\d+)[：:]\s*(.+?)\s*$", text))
    entries = []
    for index, match in enumerate(matches, 1):
        start = match.end()
        end = matches[index].start() if index < len(matches) else text.find("\n## 出处与许可", start)
        if end < start:
            end = len(text)
        body = text[start:end].strip()
        title = match.group(2).strip()
        if "```python" in body and not re.search(r"(?m)^###\s+\w+\s*实现", body):
            body = body.replace("```python", "### Python 实现\n\n```python", 1)
        # 手撕题的源码通常是函数片段；至少补上题目和接口说明注释。
        if "```python" in body:
            body = body.replace("```python\n", "```python\n" + add_code_comments("", "python", title, []), 1)
        translation = translations.get(f"ai-agent:{index}", {})
        if translation.get("java"):
            body += "\n\n### Java 实现\n\n```java\n" + add_code_comments(format_java_code(translation["java"]), "java", title, []) + "\n```"
        path = SRC / "ai-agent" / f"{index:02d}-{safe_name(title)}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {title}\n\n> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题\n\n{body}\n", encoding="utf-8")
        languages = "Python/Java" if translation.get("java") else "Python"
        entries.append({
            "group": "ai-agent",
            "title": title,
            "company": "AI/Agent 手撕",
            "date": "",
            "role": "AI/Agent",
            "lang": languages,
            "url": f"ai-agent/{index:02d}-{safe_name(title)}.html",
            "key": f"AI/Agent {title} {languages}",
        })
    return entries


def build_company_oj(translations: dict[str, dict[str, str]]) -> list[dict]:
    entries = []
    for md in sorted(COMPANY_OJ.glob("*/*.md")):
        group = md.parent.name
        title = md.stem.split("-", 1)[-1]
        text = md.read_text(encoding="utf-8")
        # 企业 OJ 原文件使用 class Solution；ACM 机考统一使用 public class Main。
        text = text.replace("public class Solution", "public class Main").replace("class Solution", "class Main")
        # 原企业 OJ 页面只有 Java 代码块；补一个语言小节，交给 site.js 做切换。
        text = re.sub(r"(?m)^##\s*解题代码\s*$\n+```java", "## 解题代码\n\n### Java 实现\n\n```java", text, count=1)
        key = f"company-oj:{group}:{md.stem}"
        translation = translations.get(key, {})
        text = re.sub(r"```java\n", "```java\n" + add_code_comments("", "java", title, []), text, count=1)
        if translation.get("python"):
            text += "\n\n### Python 实现\n\n```python\n" + add_code_comments(translation["python"], "python", title, []) + "\n```\n"
        out = SRC / "company-oj" / group / f"{md.stem}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        languages = "Java/Python" if translation.get("python") else "Java"
        entry = {
            "group": "company-oj",
            "title": title,
            "company": group,
            "date": "",
            "role": "企业机考",
            "lang": languages,
            "url": f"company-oj/{group}/{md.stem}.html",
            "key": f"{group} {title} {languages}",
        }
        entry["practice"] = practice_entry(
            entry,
            python_code=parse_markdown_code(text, "python") or str(translation.get("python") or ""),
            java_code=parse_markdown_code(text, "java"),
            samples=parse_markdown_samples(text),
        )
        entries.append(entry)
    return entries


def build_index(entries: list[dict]) -> None:
    runnable = [entry["practice"] for entry in entries if entry.get("practice", {}).get("samples")]
    total_cases = sum(len(item["samples"]) for item in runnable)
    suite_note = (
        f'<p class="exam-suite-note">{len(runnable)} 道题可运行，共 {total_cases} 组公开用例。'
        '进入题目后点击代码旁的「运行代码」即可测试。'
        '<a href="acm-playground.html">练习 ACM 输入输出模板</a></p>'
    )
    def case_label(entry: dict) -> str:
        practice = entry.get("practice", {})
        samples = practice.get("samples", [])
        if not samples:
            return ""
        label = f" · {len(samples)} 组用例"
        if practice.get("checker", {}).get("mode") == "manual":
            label += " · 需核对"
        return label
    groups = [
        ("ai-2026", "① 2026 大厂 AI 岗机试", "按公司分组，来源页披露的题干、思路与代码"),
        ("ai-agent", "② AI/Agent 手撕代码题", "模型基础算子、检索排序、工具/Agent 运行时、可观测与多 Agent"),
        ("company-oj", "③ 企业机考真题（Java/Python）", "既有企业机考题库，补 Python 实现；每道题独立页面"),
    ]
    names = {"ai-2026": {}, "ai-agent": {}, "company-oj": {}}
    for entry in entries:
        names[entry["group"]][entry["company"]] = names[entry["group"]].get(entry["company"], 0) + 1

    nav = []
    sections = []
    for group_key, label, desc in groups:
        group_entries = [entry for entry in entries if entry["group"] == group_key]
        nav.append(f'<a href="#g-{group_key}">{esc(label)}<span>{len(group_entries)}</span></a>')
        rows = []
        if group_key == "ai-2026":
            for company in sorted({entry["company"] for entry in group_entries}):
                company_entries = [entry for entry in group_entries if entry["company"] == company]
                rows.append(f'<li class="exam-sub"><b>{esc(company)}</b> · {len(company_entries)} 题</li>')
                rows += [
                    f'<li data-k="{esc(entry["key"])}" data-company="{esc(entry["company"])}" data-lang="{esc(entry["lang"])}"><a href="{esc(entry["url"])}">{esc(entry["title"])}<span class="meta">{esc(entry["date"] or "")} · {esc(entry["lang"])}{case_label(entry)}</span></a></li>'
                    for entry in sorted(company_entries, key=lambda item: (item["date"], item["title"]))
                ]
        else:
            rows = [
                f'<li data-k="{esc(entry["key"])}" data-company="{esc(entry["company"])}" data-lang="{esc(entry["lang"])}"><a href="{esc(entry["url"])}">{esc(entry["title"])}<span class="meta">{esc(entry["company"])} · {esc(entry["lang"])}{case_label(entry)}</span></a></li>'
                for entry in sorted(group_entries, key=lambda item: item["title"])
            ]
        sections.append(
            f'<details class="exam-group" id="g-{group_key}"{" open" if group_key == "ai-2026" else ""}>'
            f'<summary>{esc(label)}<small>{len(group_entries)} 题</small></summary>'
            f'<p class="exam-sub">{esc(desc)}</p><ul class="exam-list">{"".join(rows)}</ul><p class="exam-empty" hidden>没有匹配题目</p></details>'
        )

    page = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>AI 岗机试真题库 · InterviewForge</title><link rel="stylesheet" href="../../assets/site.css"><style>' + STYLE + '</style></head><body>'
        '<header class="site-topbar" style="max-width:1180px;width:calc(100% - 100px);margin:16px auto 6px"><a class="site-brand" href="../../index.html">Hot 100 深度学习库</a><nav aria-label="主导航" class="site-nav"><a href="../../index.html">题目面板</a><a href="../../cockpit.html">中控台</a><a href="../../library/index.html">学习书架</a><a href="../../books/hot100/00-总览/01-学习路线.html">学习路线</a><a href="../../books/hot100/00-总览/02-算法模式地图.html">模式地图</a><a href="../../books/hot100/00-总览/03-复习清单.html">复习清单</a><a href="../../pages/leetcode-connect.html">力扣连接</a></nav></header>'
        '<div class="exam-shell"><nav class="page-nav" aria-label="面包屑"><a href="../../library/index.html">📚 学习书架</a><span aria-hidden="true">›</span><span aria-current="page">AI 岗机试真题库</span></nav>'
        '<header style="margin:8px 0 18px"><h1 style="margin:0 0 6px;font-size:26px">AI 岗机试真题库</h1><p style="margin:0;font-size:13.5px;color:var(--muted)">共 ' + str(len(entries)) + ' 题：2026 大厂 AI/算法岗机试 + AI/Agent 手撕题 + 企业机考真题。每道题有独立页面与目录；代码语言按题目可用项显示。</p></header>'
        + suite_note + '<div class="exam-tools"><input id="q" class="exam-search" type="search" placeholder="搜索题目、公司或关键词（如 华为 / 动态规划 / Agent）"><select id="company" class="exam-select"><option value="">全部公司</option>' + ''.join(f'<option value="{esc(name)}">{esc(name)}</option>' for name in sorted({entry["company"] for entry in entries})) + '</select></div>'
        '<div class="exam-layout"><nav class="exam-nav" aria-label="分组">' + ''.join(nav) + '</nav><div>' + ''.join(sections) + '</div></div></div>' + SEARCH_JS + '</body></html>'
    )
    (SRC / "index.html").write_text(page, encoding="utf-8")


def apply_java_overrides() -> None:
    """应用 data/ai_exam/java_standardized.json 中的标准 ACM Java 实现。"""
    path = ROOT / "data" / "ai_exam" / "java_standardized.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    overrides = data.get("items", data) if isinstance(data, dict) else {}
    for rel, code in overrides.items():
        target = ROOT / rel
        if not target.exists():
            continue
        text = target.read_text(encoding="utf-8")
        # A string replacement interprets Java '\\n' as an actual newline,
        # corrupting character/string literals. A callable preserves source.
        text = re.sub(r"```java\n.*?```", lambda _match: "```java\n" + code.strip() + "\n```", text, count=1, flags=re.S)
        target.write_text(text, encoding="utf-8")


def cleanup_stale(entries: list[dict]) -> None:
    """删除上一次生成但已不在索引里的旧题页，避免旧的 print("C") 页面残留。"""
    expected = {str((SRC / entry["url"]).resolve()) for entry in entries}
    keep = {str((SRC / "index.html").resolve()), str((SRC / "acm-playground.html").resolve())}
    for path in list(SRC.rglob("*.html")):
        if str(path.resolve()) in keep:
            continue
        if str(path.resolve()) not in expected:
            path.unlink()
    expected_md = {str(Path(item).with_suffix(".md").resolve()) for item in expected}
    for path in list(SRC.rglob("*.md")):
        if str(path.resolve()) not in expected_md:
            path.unlink()


def main() -> None:
    translations = load_translations()
    entries = build_ai_coding(translations) + build_agent_doc(translations) + build_company_oj(translations)
    apply_extra_samples(entries)
    merge_reviewed_cases(entries)
    apply_java_overrides()
    apply_reviewed_fixes(entries)
    cleanup_stale(entries)
    # 先渲染 AI/Agent/企业 OJ 的 Markdown；页内的语言小节由 build_html_site 处理。
    for md in (sorted((SRC / "ai-2026").glob("*/*.md")) if (SRC / "ai-2026").exists() else []):
        render_markdown(md)
    for md in (sorted((SRC / "ai-agent").glob("*.md")) if (SRC / "ai-agent").exists() else []):
        render_markdown(md)
    for md in (sorted((SRC / "company-oj").glob("*/*.md")) if (SRC / "company-oj").exists() else []):
        render_markdown(md)
    build_index(entries)
    write_practice_meta(entries)
    print("AI 岗机试题库：", len(entries), "题；页面已生成", SRC)


if __name__ == "__main__":
    main()
