"""华为题库 md → html + 索引页（复用 render_markdown 与题库页样式）。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.build.build_html_site import render_markdown  # noqa: E402

SRC = ROOT / "books" / "huawei-od"
GROUPS = [("01-精选100分题", "精选 100 分题"), ("02-200分题", "200 分题"), ("03-其他100分题", "其他 100 分题")]


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


n = 0
for md in sorted(SRC.glob("*/*.md")):
    render_markdown(md)
    n += 1
print("渲染", n, "题")

nav, secs, total = [], [], 0
for d, label in GROUPS:
    gd = SRC / d
    if not gd.is_dir():
        continue
    files = sorted(gd.glob("*.md"))
    total += len(files)
    nav.append('<a href="#g-' + esc(d) + '">' + esc(label) + '<span>' + str(len(files)) + "</span></a>")
    rows = "".join(
        '<li><a href="' + esc(d) + "/" + esc(m.stem) + '.html">' + esc(m.stem) + "</a></li>" for m in files)
    secs.append('<section id="g-' + esc(d) + '"><h2>' + esc(label) + "<small>" + str(len(files)) +
                ' 题</small></h2><ul class="qlist">' + rows + "</ul></section>")

style = """
 body{background:var(--bg,#f4f6fb)}
 .hw-shell{width:calc(100% - 100px);max-width:1180px;margin:auto;padding:24px 0 64px}
 .hw-layout{display:grid;grid-template-columns:200px minmax(0,1fr);gap:26px;align-items:start}
 .hw-nav{position:sticky;top:14px;display:flex;flex-direction:column;gap:3px;padding:12px;
   border:1px solid var(--line,#dfe4ee);border-radius:14px;background:var(--panel,#fff)}
 .hw-nav a{display:flex;justify-content:space-between;padding:6px 9px;border-radius:7px;
   color:var(--text,#182235);text-decoration:none;font-size:13px}
 .hw-nav a:hover{background:var(--soft,#f0f2fa);color:var(--brand,#5654d4)}
 .hw-nav a span{color:var(--muted,#66748a);font-variant-numeric:tabular-nums}
 section{margin:0 0 24px;padding:18px 20px;border:1px solid var(--line,#dfe4ee);border-radius:14px;background:#fff}
 h2{margin:0 0 12px;font-size:18px} h2 small{margin-left:8px;color:var(--muted,#66748a);font-size:12px;font-weight:400}
 .qlist{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:2px 18px}
 .qlist li{padding:5px 0;border-bottom:1px dashed #eef0f6}
 .qlist a{color:var(--text,#182235);text-decoration:none;font-size:13.5px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .qlist a:hover{color:var(--brand,#5654d4)}
 @media(max-width:900px){.hw-shell{width:calc(100% - 24px)}.hw-layout{grid-template-columns:1fr}
   .hw-nav{position:static;flex-direction:row;flex-wrap:wrap}.qlist{grid-template-columns:1fr}}
"""

page = "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">" \
       "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">" \
       "<title>华为 OD 机试题库 · InterviewForge</title>" \
       "<link rel=\"stylesheet\" href=\"../../assets/site.css\">" \
       "<style>" + style + "</style></head><body><div class=\"hw-shell\">" \
       "<nav class=\"page-nav\" aria-label=\"面包屑\"><a href=\"../../library/index.html\">📚 学习书架</a>" \
       "<span aria-hidden=\"true\">›</span><span aria-current=\"page\">华为 OD 机试题库</span></nav>" \
       "<header style=\"margin:8px 0 18px\"><h1 style=\"margin:0 0 6px;font-size:26px\">华为 OD 机试题库</h1>" \
       "<p style=\"margin:0;font-size:13.5px;color:#66748a\">共 " + str(total) + \
       " 题，源自 Datawhale 整理的华为 OD 机考真题（含题目描述 / 示例 / 解题思路 / Python 代码）。" \
       "建议先做精选 100 分题，再练 200 分题。</p></header>" \
       "<div class=\"hw-layout\"><nav class=\"hw-nav\" aria-label=\"分组\">" + "".join(nav) + \
       "</nav><div>" + "".join(secs) + "</div></div></div></body></html>"

(SRC / "index.html").write_text(page, encoding="utf-8")
print("索引已生成:", (SRC / "index.html").relative_to(ROOT))
