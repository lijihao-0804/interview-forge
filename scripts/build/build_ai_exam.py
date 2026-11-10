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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.build.build_html_site import render_markdown  # noqa: E402

SRC = ROOT / "books" / "ai-exam"
CODING = ROOT / "assets" / "ai-exam-coding.json"
AGENT_DOC = ROOT / "books" / "外部面经参考" / "02-AI与Agent手撕代码题.md"
COMPANY_OJ = ROOT / "books" / "company-oj"

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

SEARCH_JS = """<script>(function(){var q=document.getElementById('q'),lang=document.getElementById('lang');
function apply(){var v=(q&&q.value.trim().toLowerCase())||'',lv=(lang&&lang.value)||'';
document.querySelectorAll('.exam-group').forEach(function(g){var n=0;
g.querySelectorAll('li[data-k]').forEach(function(li){
var ok=(!v||li.getAttribute('data-k').toLowerCase().indexOf(v)>=0)&&(!lv||li.getAttribute('data-lang')===lv);
li.style.display=ok?'':'none';if(ok)n++;});
var empty=g.querySelector('.exam-empty');if(empty)empty.hidden=!!n;
g.style.display=(v||lv)&&!n?'none':'';if((v||lv)&&n)g.open=true;});}
if(q)q.oninput=apply;if(lang)lang.onchange=apply;})();</script>"""


def esc(value: object) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def safe_name(value: str, limit: int = 34) -> str:
    value = re.sub(r'[\\/:*?"<>|#\n\r\t]', "", value).strip()
    value = re.sub(r"\s+", "-", value)
    return value[:limit] or "题目"


def write_problem(path: Path, title: str, meta: str, sections: list[dict]) -> None:
    lines = [f"# {title}", "", f"> {meta}", ""]
    for section in sections:
        heading = (section.get("heading") or "").strip()
        text = (section.get("text") or "").strip()
        code = (section.get("code") or "").strip()
        if not heading and not text and not code:
            continue
        if heading and heading not in ("题目说明",):
            lines += [f"## {heading}", ""]
        if text:
            lines += [text, ""]
        if code:
            if "代码" in heading or "实现" in heading:
                lines += ["### Python 实现", "", "```python", code, "```", ""]
            else:
                lines += ["```text", code, "```", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_ai_coding() -> list[dict]:
    data = json.loads(CODING.read_text(encoding="utf-8"))
    entries = []
    for problem in data["problems"]:
        company = problem["company"]
        date = problem["date"]
        role = problem["role"]
        file_dir = SRC / "ai-2026" / company
        filename = f"{len(entries) + 1:03d}-{safe_name(problem['title'])}.md"
        md_path = file_dir / filename
        meta = f"来源：{problem.get('source_url', '')} · {company} · {date or '日期未标注'} · {role or 'AI岗'}"
        write_problem(md_path, problem["title"], meta, problem.get("sections", []))
        entries.append({
            "group": "ai-2026",
            "title": problem["title"],
            "company": company,
            "date": date,
            "role": role,
            "lang": "Python",
            "url": f"ai-2026/{company}/{filename[:-3]}.html",
            "key": f"{company} {problem['title']} Python",
        })
    return entries


def build_agent_doc() -> list[dict]:
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
        path = SRC / "ai-agent" / f"{index:02d}-{safe_name(title)}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {title}\n\n> 来源：外部面经参考/02-AI与Agent手撕代码题.md · AI/Agent 手撕题\n\n{body}\n", encoding="utf-8")
        entries.append({
            "group": "ai-agent",
            "title": title,
            "company": "AI/Agent 手撕",
            "date": "",
            "role": "AI/Agent",
            "lang": "Python",
            "url": f"ai-agent/{index:02d}-{safe_name(title)}.html",
            "key": f"AI/Agent {title} Python",
        })
    return entries


def build_company_oj() -> list[dict]:
    entries = []
    for md in sorted(COMPANY_OJ.glob("*/*.md")):
        group = md.parent.name
        title = md.stem.split("-", 1)[-1]
        entries.append({
            "group": "company-oj",
            "title": title,
            "company": group,
            "date": "",
            "role": "企业机考",
            "lang": "Java",
            "url": f"../company-oj/{group}/{md.stem}.html",
            "key": f"{group} {title} Java",
        })
    return entries


def build_index(entries: list[dict]) -> None:
    groups = [
        ("ai-2026", "① 2026 大厂 AI 岗机试", "按公司分组，来源页披露的题干、思路与代码"),
        ("ai-agent", "② AI/Agent 手撕代码题", "模型基础算子、检索排序、工具/Agent 运行时、可观测与多 Agent"),
        ("company-oj", "③ 企业机考真题（Java）", "既有企业机考题库，Java 实现；点击进入原题页"),
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
                    f'<li data-k="{esc(entry["key"])}" data-lang="{esc(entry["lang"])}"><a href="{esc(entry["url"])}">{esc(entry["title"])}<span class="meta">{esc(entry["date"] or "")}</span></a></li>'
                    for entry in sorted(company_entries, key=lambda item: (item["date"], item["title"]))
                ]
        else:
            rows = [
                f'<li data-k="{esc(entry["key"])}" data-lang="{esc(entry["lang"])}"><a href="{esc(entry["url"])}">{esc(entry["title"])}<span class="meta">{esc(entry["company"])} · {esc(entry["lang"])}</span></a></li>'
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
        '<div class="exam-tools"><input id="q" class="exam-search" type="search" placeholder="搜索题目、公司或关键词（如 华为 / 动态规划 / Agent）"><select id="lang" class="exam-select"><option value="">全部语言</option><option value="Python">Python</option><option value="Java">Java</option></select></div>'
        '<div class="exam-layout"><nav class="exam-nav" aria-label="分组">' + ''.join(nav) + '</nav><div>' + ''.join(sections) + '</div></div></div>' + SEARCH_JS + '</body></html>'
    )
    (SRC / "index.html").write_text(page, encoding="utf-8")


def main() -> None:
    entries = build_ai_coding() + build_agent_doc() + build_company_oj()
    # 先渲染 AI/Agent 的 Markdown；company-oj 已有自己的生成页。
    for md in (sorted((SRC / "ai-2026").glob("*/*.md")) if (SRC / "ai-2026").exists() else []):
        render_markdown(md)
    for md in (sorted((SRC / "ai-agent").glob("*.md")) if (SRC / "ai-agent").exists() else []):
        render_markdown(md)
    build_index(entries)
    print("AI 岗机试题库：", len(entries), "题；页面已生成", SRC)


if __name__ == "__main__":
    main()
