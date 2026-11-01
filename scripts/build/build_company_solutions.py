"""把企业题解的 Markdown 渲染成 HTML 页，并生成索引页。

输出：
  books/company-solutions/<分类>/<id>-<title>.html   （每题一页，render_markdown 生成）
  books/company-solutions/index.html                 （索引：按分类列出全部题，链接到各题解页）

用法：python scripts/build/build_company_solutions.py
（用系统 python 运行，需能 import markdown —— 构建脚本统一用系统 python）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.build.build_html_site import render_markdown  # noqa: E402

SRC = ROOT / "books" / "company-solutions"
DETAIL = SRC / "_meta" / "problems_detail.json"
INDEX = SRC / "index.html"


def esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def build_index(detail: list[dict], md_paths: dict[int, Path]) -> None:
    """按分类（tags[0]）分组，列出所有已生成题解。"""
    groups: dict[str, list[dict]] = {}
    for d in detail:
        if d["id"] not in md_paths:
            continue
        tag = (d.get("tags") or ["综合"])[0]
        groups.setdefault(tag, []).append(d)

    nav = "".join(
        f'<a href="#g-{esc(tag)}">{esc(tag)} <span>{len(items)}</span></a>'
        for tag, items in sorted(groups.items(), key=lambda kv: -len(kv[1]))
    )
    sections = []
    for tag, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        rows = []
        for d in sorted(items, key=lambda x: x["id"]):
            rel = md_paths[d["id"]].with_suffix(".html").relative_to(INDEX.parent).as_posix()
            diff = d.get("difficulty") or ""
            rows.append(
                f'<li><a href="{esc(rel)}">{d["id"]}. {esc(d["title"])}</a>'
                f'<span class="diff d-{esc(diff)}">{esc(diff)}</span></li>'
            )
        sections.append(
            f'<section id="g-{esc(tag)}"><h2>{esc(tag)}<small>{len(items)} 题</small></h2>'
            f'<ul class="sol-list">{"".join(rows)}</ul></section>'
        )

    total = sum(len(v) for v in groups.values())
    page = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>企业高频题解 · InterviewForge</title>
<link rel="stylesheet" href="../../assets/site.css">
<style>
  body{{background:var(--page-bg,#f4f6fb)}}
  .wrap{{width:calc(100% - 80px);max-width:1180px;margin:auto;padding:28px 0 64px}}
  .layout{{display:grid;grid-template-columns:190px minmax(0,1fr);gap:26px;align-items:start}}
  .cat-nav{{position:sticky;top:14px;display:flex;flex-direction:column;gap:3px;padding:12px;
    border:1px solid var(--line,#dfe4ee);border-radius:14px;background:#fff}}
  .cat-nav a{{display:flex;justify-content:space-between;padding:6px 9px;border-radius:7px;
    color:var(--text,#182235);text-decoration:none;font-size:13px}}
  .cat-nav a:hover{{background:var(--surface-soft,#f0f2fa);color:var(--brand,#5654d4)}}
  .cat-nav a span{{color:var(--muted,#66748a);font-variant-numeric:tabular-nums}}
  section{{margin:0 0 26px;padding:18px 20px;border:1px solid var(--line,#dfe4ee);border-radius:14px;background:#fff}}
  h2{{margin:0 0 12px;font-size:18px}} h2 small{{margin-left:8px;color:var(--muted,#66748a);font-size:12px;font-weight:400}}
  .sol-list{{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:2px 18px}}
  .sol-list li{{display:flex;justify-content:space-between;gap:8px;padding:5px 0;border-bottom:1px dashed #eef0f6}}
  .sol-list a{{color:var(--text,#182235);text-decoration:none;font-size:13.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .sol-list a:hover{{color:var(--brand,#5654d4)}}
  .diff{{font-size:11px;padding:1px 7px;border-radius:99px;white-space:nowrap;background:#eef0f6;color:#5b6478}}
  .d-简单{{background:#e5f5ec;color:#157a52}} .d-中等{{background:#fff3e0;color:#a85b00}} .d-困难{{background:#fbe9e7;color:#b3372f}}
  @media(max-width:900px){{.wrap{{width:calc(100% - 24px)}}.layout{{grid-template-columns:1fr}}.cat-nav{{position:static;flex-direction:row;flex-wrap:wrap}}.sol-list{{grid-template-columns:1fr}}}}
</style></head><body>
<div class="wrap">
  <nav class="page-nav" aria-label="面包屑"><a href="../../library/index.html">📚 学习书架</a><span aria-hidden="true">›</span><span aria-current="page">企业高频题解</span></nav>
  <header style="margin:8px 0 18px"><h1 style="margin:0 0 6px;font-size:26px">企业高频题解</h1>
    <p style="margin:0;font-size:13.5px;color:#66748a">按算法分类整理，共 {total} 题。每页含题目与约束、核心不变量、完整推导、Java/C++/Python 实现与复杂度分析。</p></header>
  <div class="layout">
    <nav class="cat-nav" aria-label="分类">{nav}</nav>
    <div>{''.join(sections)}</div>
  </div>
</div></body></html>
"""
    INDEX.write_text(page, encoding="utf-8")


def main() -> None:
    detail = json.loads(DETAIL.read_text(encoding="utf-8"))
    by_id = {d["id"]: d for d in detail}
    md_paths: dict[int, Path] = {}
    rendered = 0
    for md in sorted(SRC.rglob("*.md")):
        if md.parent.name == "_meta" or md.name.startswith("索引"):
            continue
        # 从文件名解析题号
        head = md.name.split("-", 1)[0]
        if not head.isdigit():
            continue
        pid = int(head)
        if pid not in by_id:
            continue
        render_markdown(md)
        md_paths[pid] = md
        rendered += 1
    build_index(detail, md_paths)
    print(f"渲染题解 {rendered} 页，索引已生成 {INDEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
