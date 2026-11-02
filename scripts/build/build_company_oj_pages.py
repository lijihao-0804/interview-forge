"""company-oj md → html + 按公司分组的索引页。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.build.build_html_site import render_markdown  # noqa: E402

SRC = ROOT / "books" / "company-oj"

STYLE = """
 body{background:var(--page-bg)}
 .oj-shell{width:calc(100% - 100px);max-width:1180px;margin:auto;padding:24px 0 64px}
 .oj-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}
 .oj-card{display:block;padding:16px 18px;border:1px solid var(--line);border-radius:14px;
   background:var(--surface);text-decoration:none;color:var(--text);transition:all .15s;box-shadow:0 6px 18px rgba(33,45,73,.05)}
 .oj-card:hover{transform:translateY(-2px);border-color:var(--brand);box-shadow:0 12px 28px rgba(86,84,212,.14)}
 .oj-card h3{margin:0 0 6px;font-size:16px} .oj-card .n{font-size:13px;color:var(--muted)}
 .oj-card ul{list-style:none;margin:10px 0 0;padding:0;font-size:13px}
 .oj-card li{padding:3px 0;border-top:1px dashed #eef0f6;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .oj-card li a{color:var(--text);text-decoration:none}
 .oj-card li a:hover{color:var(--brand)}
 @media(max-width:700px){.oj-shell{width:calc(100% - 24px)}}
"""


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def main():
    n = 0
    for md in sorted(SRC.glob("*/*.md")):
        render_markdown(md)
        n += 1
    print("渲染", n, "题")

    comps = sorted([d for d in SRC.iterdir() if d.is_dir()])
    cards = []
    total = 0
    for d in comps:
        files = sorted(d.glob("*.md"))
        total += len(files)
        items = "".join(
            '<li><a href="' + esc(d.name) + "/" + esc(m.stem) + '.html">' + esc(m.stem) + "</a></li>" for m in files)
        cards.append('<div class="oj-card"><h3>' + esc(d.name) + '</h3><div class="n">' + str(len(files)) +
                     ' 题</div><ul>' + items + "</ul></div>")

    page = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>企业机考真题 · InterviewForge</title>'
        '<link rel="stylesheet" href="../../assets/site.css"><style>' + STYLE + '</style></head><body>'
        '<div class="oj-shell"><nav class="page-nav" aria-label="面包屑">'
        '<a href="../../library/index.html">📚 学习书架</a><span aria-hidden="true">›</span>'
        '<span aria-current="page">企业机考真题</span></nav>'
        '<header style="margin:8px 0 18px"><h1 style="margin:0 0 6px;font-size:26px">企业机考真题</h1>'
        '<p style="margin:0;font-size:13.5px;color:var(--muted)">共 ' + str(total) + ' 题，来自语雀「大厂笔试真题汇总」'
        '公开分享（华为/阿里/网易/京东/小米/拼多多/携程等）。<b>均为 OCR 原文，可能存在识别误差</b>，仅供了解考点。</p></header>'
        '<div class="oj-grid">' + "".join(cards) + "</div></div></body></html>"
    )
    (SRC / "index.html").write_text(page, encoding="utf-8")
    print("索引已生成：", (SRC / "index.html").relative_to(ROOT))


if __name__ == "__main__":
    main()
