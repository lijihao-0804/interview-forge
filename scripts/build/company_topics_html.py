"""企业题库的独立页面生成（library/company/index.html）。

刻意不注册成书架模块：它只是查阅用的题库索引，不产生学习进度，
单独一个目录，从书架页入口进入。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML_OUT = ROOT / "library" / "company" / "index.html"

ROLES = [
    ("algorithm", "算法"),
    ("backend", "后端"),
    ("frontend", "前端"),
    ("client", "客户端"),
    ("data", "数据"),
    ("test", "测试"),
]


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def write_html(per_company: dict, hot100: dict, companies: list, top_n: int) -> None:
    nav_items: list[str] = []
    sections: list[str] = []

    for folder, cn in companies:
        per_role = per_company.get(cn) or {}
        if not per_role:
            continue
        anchor = f"c-{folder}"
        nav_items.append(f'<a href="#{anchor}">{_esc(cn)}</a>')
        blocks: list[str] = []
        for role_key, role_cn in ROLES:
            items = per_role.get(role_cn)
            if not items:
                continue
            # 只列 Hot 100 之外的题：Hot 100 已有题解，重复列出没有增量信息
            extra = [x for x in items if x["id"] not in hot100]
            covered_n = len(items) - len(extra)
            if not extra:
                blocks.append(
                    f'<h3>{_esc(cn)} · {role_cn}</h3>'
                    f'<p class="more">该岗位共 {len(items)} 题，全部已在 Hot 100 中覆盖，无需额外补题。</p>'
                )
                continue
            rows = []
            for item in extra[:top_n]:
                count = item["count"] if item["count"] is not None else "—"
                rows.append(
                    f'<tr><td class="pid">{item["id"]}</td>'
                    f'<td>{_esc(item["title"])}</td>'
                    f'<td class="cnt">{count}</td></tr>'
                )
            note = ""
            if covered_n:
                note = (f'<p class="more">该岗位共 {len(items)} 题，其中 {covered_n} 题已在 Hot 100 覆盖，'
                        f'下面只列剩下的 {len(extra)} 题。</p>')
            if len(extra) > top_n:
                note += f'<p class="more">其余 {len(extra) - top_n} 题略（只展示热度前 {top_n}）</p>'
            blocks.append(
                f'<h3>{_esc(cn)} · {role_cn}</h3>'
                '<table class="ct"><thead><tr><th>题号</th><th>题目</th>'
                '<th>热度</th></tr></thead><tbody>'
                + "".join(rows) + "</tbody></table>" + note
            )
        sections.append(
            f'<section id="{anchor}" class="company"><h2>{_esc(cn)}</h2>'
            + "".join(blocks) + "</section>"
        )

    style = """
  body{background:var(--bg)}
  .company-shell{width:calc(100% - 100px);max-width:1280px;margin:auto;padding:24px 0 64px}
  .company-layout{display:grid;grid-template-columns:200px minmax(0,1fr);gap:28px;align-items:start}
  .company-nav{position:sticky;top:14px;display:flex;flex-direction:column;gap:4px;padding:14px;
    border:1px solid var(--line);border-radius:14px;background:var(--panel)}
  .company-nav a{padding:7px 10px;border-radius:8px;color:var(--text);text-decoration:none;font-size:13px}
  .company-nav a:hover{background:var(--soft);color:var(--brand)}
  .company-nav .nav-title{font-size:11px;font-weight:700;color:var(--muted);margin:0 8px 6px}
  .company{margin:0 0 34px;padding:20px;border:1px solid var(--line);border-radius:16px;background:var(--panel)}
  .company h2{margin:0 0 4px;font-size:22px}
  .company h3{margin:20px 0 8px;font-size:14px;color:var(--muted)}
  .ct{width:100%;border-collapse:collapse;font-size:13px}
  .ct th{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);color:var(--muted);font-weight:600}
  .ct td{padding:6px 10px;border-bottom:1px solid color-mix(in srgb,var(--line) 60%,transparent)}
  .ct .pid{width:64px;color:var(--muted);font-variant-numeric:tabular-nums}
  .ct .cnt{width:64px;text-align:right;font-variant-numeric:tabular-nums}
  .ct .hit-cell{width:80px;text-align:center}
  .more{margin:8px 0 0;font-size:12px;color:var(--muted)}
  @media(max-width:900px){
    .company-shell{width:calc(100% - 24px)}
    .company-layout{grid-template-columns:1fr;gap:16px}
    .company-nav{position:static;flex-direction:row;flex-wrap:wrap}
    .company-nav .nav-title{width:100%}
  }
"""

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>企业高频算法题库 · InterviewForge</title>
<link rel="stylesheet" href="../assets/library.css">
<style>{style}</style>
</head>
<body>
<div class="company-shell">
  <nav class="page-nav" aria-label="面包屑"><a href="../index.html">📚 学习书架</a><span aria-hidden="true">›</span><span aria-current="page">企业高频算法题库</span></nav>
  <header style="margin:8px 0 18px">
    <h1 style="margin:0 0 6px;font-size:26px">企业高频算法题库</h1>
    <p class="muted" style="margin:0;font-size:13.5px;max-width:820px">
      按公司汇总互联网技术岗考察的 LeetCode 题目热度，数据来自
      <a href="https://github.com/huangzhangting/LeetcodeTop" target="_blank" rel="noopener noreferrer">LeetcodeTop</a> /
      <a href="https://codetop.cc" target="_blank" rel="noopener noreferrer">CodeTop</a> 的社区面经整理，仅供安排刷题优先级参考。
      这里<b>只列 Hot 100 之外的题</b>——Hot 100 已经覆盖的题不再重复，避免重复刷。
    </p>
  </header>
  <div class="company-layout">
    <nav class="company-nav" aria-label="公司导航"><p class="nav-title">公司</p>{''.join(nav_items)}</nav>
    <div>{''.join(sections)}</div>
  </div>
</div>
</body>
</html>
"""
    HTML_OUT.parent.mkdir(parents=True, exist_ok=True)
    HTML_OUT.write_text(page, encoding="utf-8")
