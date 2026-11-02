"""华为题库 md → html + 索引页（折叠分组 + 搜索，复用 render_markdown 与题解页样式）。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.build.build_html_site import render_markdown  # noqa: E402

SRC = ROOT / "books" / "huawei-od"
GROUPS = [("01-精选100分题", "① 精选 100 分题（建议先做）"), ("02-200分题", "② 200 分题（进阶）"), ("03-其他100分题", "③ 其他 100 分题（补充练习）")]

STYLE = """
 body{background:var(--page-bg)}
 .hw-shell{width:calc(100% - 100px);max-width:1180px;margin:auto;padding:24px 0 64px}
 .hw-search{width:100%;max-width:420px;padding:9px 14px;border:1px solid var(--line);
   border-radius:10px;font:inherit;background:var(--surface);margin-bottom:14px}
 .hw-layout{display:grid;grid-template-columns:200px minmax(0,1fr);gap:26px;align-items:start}
 .hw-nav{position:sticky;top:14px;display:flex;flex-direction:column;gap:3px;padding:12px;
   border:1px solid var(--line);border-radius:14px;background:var(--surface)}
 .hw-nav a{display:flex;justify-content:space-between;padding:6px 9px;border-radius:7px;
   color:var(--text);text-decoration:none;font-size:13px}
 .hw-nav a:hover{background:var(--surface-soft);color:var(--brand)}
 .hw-nav a span{color:var(--muted);font-variant-numeric:tabular-nums}
 details.hw-group{margin:0 0 12px;border:1px solid var(--line);border-radius:14px;background:var(--surface)}
 details.hw-group>summary{cursor:pointer;padding:14px 20px;font-size:16px;font-weight:650;list-style:none}
 details.hw-group>summary::-webkit-details-marker{display:none}
 details.hw-group>summary::before{content:"\\25B8";display:inline-block;margin-right:8px;color:var(--muted);
   transition:transform .15s}
 details.hw-group[open]>summary::before{transform:rotate(90deg)}
 details.hw-group>summary small{margin-left:8px;color:var(--muted);font-size:12px;font-weight:400}
 details.hw-group .qlist{list-style:none;margin:0;padding:0 20px 16px;display:grid;
   grid-template-columns:1fr 1fr;gap:2px 18px}
 details.hw-group .qlist li{padding:5px 0;border-bottom:1px dashed #eef0f6}
 details.hw-group .qlist a{color:var(--text);text-decoration:none;font-size:13.5px;
   display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 details.hw-group .qlist a:hover{color:var(--brand)}
 @media(max-width:900px){.hw-shell{width:calc(100% - 24px)}.hw-layout{grid-template-columns:1fr}
   .hw-nav{position:static;flex-direction:row;flex-wrap:wrap}
   details.hw-group .qlist{grid-template-columns:1fr}}
"""

SEARCH_JS = """<script>(function(){var q=document.getElementById('q');if(!q)return;
q.oninput=function(){var v=q.value.trim().toLowerCase();
document.querySelectorAll('.hw-group').forEach(function(g){var n=0;
g.querySelectorAll('li[data-k]').forEach(function(li){
var ok=!v||li.getAttribute('data-k').toLowerCase().indexOf(v)>=0;
li.style.display=ok?'':'none';if(ok)n++;});
g.style.display=(v&&!n)?'none':'';if(v&&n)g.open=true;});};})();</script>"""


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def main():
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
            '<li data-k="' + esc(m.stem) + '"><a href="' + esc(d) + "/" + esc(m.stem) + '.html">' +
            esc(m.stem) + "</a></li>" for m in files)
        open_attr = " open" if not secs else ""
        secs.append('<details class="hw-group" id="g-' + esc(d) + '"' + open_attr + '><summary>' + esc(label) +
                    '<small>' + str(len(files)) + ' 题</small></summary><ul class="qlist">' + rows + "</ul></details>")

    page = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>华为 OD 机试题库 · InterviewForge</title>'
        '<link rel="stylesheet" href="../../assets/site.css">'
        '<style>' + STYLE + '</style></head><body><div class="hw-shell">'
        '<nav class="page-nav" aria-label="面包屑"><a href="../../library/index.html">📚 学习书架</a>'
        '<span aria-hidden="true">›</span><span aria-current="page">华为 OD 机试题库</span></nav>'
        '<header style="margin:8px 0 18px"><h1 style="margin:0 0 6px;font-size:26px">华为 OD 机试题库</h1>'
        '<p style="margin:0;font-size:13.5px;color:var(--muted)">共 ' + str(total) +
        ' 题，源自 Datawhale 整理的华为 OD 机考真题（含题目描述 / 示例 / 解题思路 / Python 代码）。'
        '建议先做精选 100 分题，再练 200 分题。</p></header>'
        '<input id="q" class="hw-search" type="search" placeholder="搜索题目关键词（如 处理器 / 字符串）">'
        '<div class="hw-layout"><nav class="hw-nav" aria-label="分组">' + "".join(nav) +
        '</nav><div>' + "".join(secs) + "</div></div></div>" + SEARCH_JS + "</body></html>"
    )
    (SRC / "index.html").write_text(page, encoding="utf-8")
    print("索引已生成:", (SRC / "index.html").relative_to(ROOT))


if __name__ == "__main__":
    main()
