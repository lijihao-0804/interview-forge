"""Build the super-admin-only bookshelf book for AgentHub full study notes.

Reads the archived Markdown source, removes archive comments / raw anchor tags /
ChatGPT tracking reference links, splits into one-section-per-page bookshelf HTML
under ``library/agenthub-study/`` with left chapter rail, right in-page TOC,
Pygments syntax highlighting, copy buttons, and Mermaid diagram rendering.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build.build_library import (  # noqa: E402
    ASSET_VERSION,
    LIBRARY_CSS_VERSION,
    LIBRARY_MERMAID_VERSION,
    render_markdown,
)

DEFAULT_SOURCE = Path(r"C:\Users\20303\Downloads\AgentHub_学习讲解原文完整归档 (5).md")
# Reference-link definitions that the interview bank (C/D) still cites but whose
# original definitions lived inside the retired 第 21–27 讲 bodies. The new source
# keeps the interview answers verbatim but no longer carries those definitions, so
# we restore them from a checked-in snapshot of the previous archive.
SUPPLEMENTAL_REFS = Path(__file__).with_name("agenthub_study_legacy_refs.json")
OUTPUT_DIR = ROOT / "library" / "agenthub-study"

BOOK_TITLE = "AgentHub 从 0 到 1 深度课程"
BOOK_CATEGORY = "项目学习笔记"
BOOK_ABOUT = (
    "基于《AgentHub 学习讲解原文完整归档（2026-11-23 去重重构版）》整理："
    "含版本同步、第 1–11 讲原始实战主线、技术演进需求清单、第 12 讲工程地图、"
    "第 13–20 讲源码深化课程以及 220 道带项目落点与追问的面试问答。"
    "一节一页，支持左右双目录、代码高亮与流程图渲染。"
)

# Section boundaries: (start_line_1based, title, topic, drop_leading_patterns)
# Lines are sliced [start-1 : next_start-1], except archive-history (5094-5136)
# which is moved to the end as an appendix so Lesson 7 flows directly into Lesson 8.
SECTION_SPECS: list[tuple[int, int | None, str, str]] = [
    (1, 60, "导读与全书课程导航", "导读与版本同步"),
    (61, 233, "2026-11-20 版本同步：新旧结论对照", "导读与版本同步"),
    (273, 575, "第 1 讲：项目总览、学习路线与工具调用入门", "核心课程（第 1–11 讲）"),
    (576, 1050, "第 2 讲：把工具调用接成完整的 Agent 循环", "核心课程（第 1–11 讲）"),
    (1051, 1955, "第 3 讲：前端、后端分层与数据库操作", "核心课程（第 1–11 讲）"),
    (1956, 2562, "第 4 讲：工具审批与恢复执行", "核心课程（第 1–11 讲）"),
    (2563, 3404, "第 5 讲：数据库选型、业务分工、事务与崩溃恢复", "核心课程（第 1–11 讲）"),
    (3405, 4206, "第 6 讲：数据库表结构设计与面试", "核心课程（第 1–11 讲）"),
    (4207, 5093, "第 7 讲：异步任务与后台 Worker", "核心课程（第 1–11 讲）"),
    (5137, 6322, "第 8 讲：完整 RAG——从文档分块到带引用的回答", "核心课程（第 1–11 讲）"),
    (6323, 7132, "第 8 讲补充：上下文投影与 RAG 文档局部修改", "核心课程（第 1–11 讲）"),
    (7133, 8493, "第 9 讲：上下文、Memory 与 Wiki", "核心课程（第 1–11 讲）"),
    (8494, 9833, "第 10 讲：前端与异步执行", "核心课程（第 1–11 讲）"),
    (9834, 10746, "技术演进需求清单与版本校正", "核心课程（第 1–11 讲）"),
    (10747, 11508, "第 11 讲：评测与独立修改", "核心课程（第 1–11 讲）"),
    (11509, 11616, "第 12 讲：工程地图、依赖方向与发布版本", "源码深化（第 12–20 讲）"),
    (11617, 11852, "第 13 讲：身份、会话和多租户——把“已登录”落实到每一次资源操作", "源码深化（第 12–20 讲）"),
    (11853, 12100, "第 14 讲：模型网关、计费账本与 KV 友好上下文——从一次回答追到每次实际调用", "源码深化（第 12–20 讲）"),
    (12101, 12324, "第 15 讲：MCP 接入与远程执行边界——“发现一个工具”到“可信调用一次工具”", "源码深化（第 12–20 讲）"),
    (12325, 12551, "第 16 讲：从 AI 聊天到真实产品——Artifact、工单、人工接管和反馈的业务闭环", "源码深化（第 12–20 讲）"),
    (12552, 12803, "第 17 讲：评测系统自身怎样可靠运行——Runner、失败分类、指标快照与上线门禁", "源码深化（第 12–20 讲）"),
    (12804, 13035, "第 18 讲：把项目真正部署并运维起来——配置、迁移、健康检查与恢复演练", "源码深化（第 12–20 讲）"),
    (13036, 13302, "第 19 讲：数据库性能与并发定位——从一次慢请求找到真正的瓶颈", "源码深化（第 12–20 讲）"),
    (13303, 13633, "第 20 讲：真正值得研究的下一步——Memory、Wiki 与 RAG 的质量工程", "源码深化（第 12–20 讲）"),
    (13634, 13650, "全书工程阅读指南：从旧课到新课怎样衔接", "导读与版本同步"),
    (13655, 13950, "面试问答总览与 220 题索引", "面试问答（220 题）"),
    (13951, 14446, "面试问答 A：架构、数据库、认证与交付（SYS01–SYS60）", "面试问答（220 题）"),
    (14447, 14985, "面试问答 B：模型网关、异步可靠性与审批（RT01–RT50）", "面试问答（220 题）"),
    (14986, 15473, "面试问答 C：知识摄取、RAG、Memory 与 Wiki（KG01–KG60）", "面试问答（220 题）"),
    (15474, None, "面试问答 D：前端、业务闭环与可信评测（FE01–FE50）", "面试问答（220 题）"),
    (5094, 5136, "附录：整理请求与当时的归档进度", "历史归档附录"),
]

REF_DEF_RE = re.compile(r'^\[([^\]]+)\]:\s*(\S+)(?:\s+"([^"]*)")?\s*$')
ANCHOR_LINE_RE = re.compile(r'^<a\s+id="([^"]+)"></a>\s*$')
HTML_COMMENT_RE = re.compile(r'<!--.*?-->')
HEADING_TAG_RE = re.compile(r'<(h[23])([^>]*)>(.*?)</\1>', re.S | re.I)
INLINE_CODE_SPLIT_RE = re.compile(r'(`[^`]*`)')


def _clean_url(url: str) -> str:
    """Strip ChatGPT UTM tracking parameters while keeping all other query params."""
    parts = urlsplit(url)
    if not parts.query:
        return url
    filtered = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "utm_source"]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(filtered), parts.fragment))


def _collect_ref_defs(lines: list[str]) -> dict[str, tuple[str, str]]:
    """Collect all Markdown reference-link definitions outside fenced code blocks."""
    defs: dict[str, tuple[str, str]] = {}
    in_code = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = REF_DEF_RE.match(line)
        if m:
            key = m.group(1).strip().lower()
            defs[key] = (_clean_url(m.group(2).strip()), (m.group(3) or "").strip())
    return defs


def _replace_outside_inline_code(line: str, fn) -> str:
    parts = INLINE_CODE_SPLIT_RE.split(line)
    for idx in range(0, len(parts), 2):
        parts[idx] = fn(parts[idx])
    return "".join(parts)


def _inline_ref_links(line: str, ref_defs: dict[str, tuple[str, str]]) -> str:
    def repl(m: re.Match[str]) -> str:
        label = m.group(1)
        key = m.group(2).strip().lower()
        if key not in ref_defs:
            return m.group(0)
        url, _ = ref_defs[key]
        return f"[{label}]({url})"

    return re.sub(r'\[([^\]]+)\]\[([^\]]+)\]', repl, line)


def _rewrite_internal_anchors(
    line: str,
    current_file: str,
    anchor_map: dict[str, tuple[str, str | None]],
) -> str:
    """Rewrite [text](#anchor) links to cross-chapter chapter-NN.html(#id) links."""
    def _sub(segment: str) -> str:
        def repl(m: re.Match[str]) -> str:
            label, anchor = m.group(1), m.group(2)
            target = anchor_map.get(anchor)
            if not target:
                return m.group(0)
            target_file, target_id = target
            if target_file == current_file:
                return f"[{label}](#{target_id})" if target_id else f"[{label}](#)"
            if target_id:
                return f"[{label}]({target_file}#{target_id})"
            return f"[{label}]({target_file})"

        return re.sub(r'\[([^\]]+)\]\(#([^)]+)\)', repl, segment)

    return _replace_outside_inline_code(line, _sub)


def _normalize_section_markdown(
    raw_lines: list[str],
    ref_defs: dict[str, tuple[str, str]],
    current_file: str,
    anchor_map: dict[str, tuple[str, str | None]],
) -> tuple[str, dict[str, str]]:
    """Clean abnormal markers, inline ref links, normalize headings, capture heading IDs.

    Returns (cleaned_markdown, heading_anchor_overrides) where heading_anchor_overrides
    maps a unique marker token or normalized heading text to an explicit anchor id
    (e.g. ``qa-sys01``).
    """
    cleaned: list[str] = []
    heading_id_markers: dict[str, str] = {}
    pending_anchor: str | None = None
    in_code = False

    # Pass 1: strip comments, ref defs, raw <a id=...> lines; capture qa-* anchors
    for line in raw_lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            cleaned.append(line)
            continue
        if in_code:
            cleaned.append(line)
            continue

        # Remove HTML comments (BEGIN/END ORIGINAL TURN, APPENDED, 固定源码引用, etc.)
        if HTML_COMMENT_RE.search(line):
            line = HTML_COMMENT_RE.sub("", line)
            if not line.strip():
                continue
            stripped = line.strip()

        # Remove reference-style link definitions
        if REF_DEF_RE.match(line):
            continue

        # Capture or drop <a id="..."></a>
        m_anchor = ANCHOR_LINE_RE.match(stripped)
        if m_anchor:
            aid = m_anchor.group(1)
            target = anchor_map.get(aid)
            if target and target[1]:
                pending_anchor = target[1]
            continue

        # Inline reference links and rewrite internal #anchors
        line = _inline_ref_links(line, ref_defs)
        line = _rewrite_internal_anchors(line, current_file, anchor_map)

        # Clean utm_source on any direct inline links too
        if "utm_source=chatgpt.com" in line:
            line = re.sub(r'\?utm_source=chatgpt\.com\b', '', line)
            line = re.sub(r'&utm_source=chatgpt\.com\b', '', line)

        # Attach pending heading anchor via harmless comment-free marker token
        if pending_anchor and re.match(r'^#{1,6}\s+', line):
            token = f"ANCHORID_{pending_anchor.replace('-', '_')}_END"
            heading_id_markers[token] = pending_anchor
            line = f"{line.rstrip()} {token}"
            pending_anchor = None

        cleaned.append(line)

    # Trim leading/trailing blank lines and horizontal rules
    while cleaned and (not cleaned[0].strip() or cleaned[0].strip() == "---"):
        cleaned.pop(0)
    while cleaned and (not cleaned[-1].strip() or cleaned[-1].strip() == "---"):
        cleaned.pop()

    # Pass 2: strip redundant top-level chapter title / archive wrapper headings
    # (page template already renders <h1>{title}</h1>).
    if cleaned and re.match(r'^#\s+', cleaned[0]):
        cleaned.pop(0)
        while cleaned and not cleaned[0].strip():
            cleaned.pop(0)

    # For appended lessons that start with `## 追加记录：...` + blockquote + `### 用户提问` + `### 讲解原文` + `# 第 N 讲...`
    if cleaned and re.match(r'^##\s+追加记录[：:]', cleaned[0]):
        cleaned.pop(0)
        while cleaned and not cleaned[0].strip():
            cleaned.pop(0)

    # For interview B/C/D that start with `## 面试问答专题：...` or `## 面试题库：...`
    if cleaned and re.match(r'^##\s+(?:面试问答专题|面试题库)[：:]', cleaned[0]):
        cleaned.pop(0)
        while cleaned and not cleaned[0].strip():
            cleaned.pop(0)

    # For Lesson 12 which starts with `# 第二部分：...` + quote + `# 第 12 讲：...`
    if cleaned and cleaned[0].startswith("> 以下各讲统一核验"):
        cleaned.pop(0)
        while cleaned and not cleaned[0].strip():
            cleaned.pop(0)
        if cleaned and re.match(r'^#\s+第\s*12\s*讲', cleaned[0]):
            cleaned.pop(0)
            while cleaned and not cleaned[0].strip():
                cleaned.pop(0)

    # Remove duplicate H1 subtitle right inside the first ~18 lines (e.g. `# 第二节：...`, `# 第 8 讲：...`, `# 异步任务与后台 Worker：...`)
    deduped: list[str] = []
    in_code = False
    for idx, line in enumerate(cleaned):
        if line.strip().startswith("```"):
            in_code = not in_code
            deduped.append(line)
            continue
        if not in_code and idx < 22 and re.match(
            r'^#\s+(?:第二节|第\s*\d+\s*讲|异步任务与后台\s*Worker)[：:—]', line
        ):
            continue
        deduped.append(line)
    cleaned = deduped

    # Pass 3: normalize any remaining internal H1 headings (`# ...`) to H2 (`## ...`)
    # If a chapter has internal H1 headings, shift all headings inside by +1 level
    # (H1->H2, H2->H3, H3->H4) so hierarchy stays intact and right TOC captures everything.
    in_code = False
    has_internal_h1 = False
    for line in cleaned:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code and re.match(r'^#\s+', line):
            has_internal_h1 = True
            break

    if has_internal_h1:
        shifted: list[str] = []
        in_code = False
        for line in cleaned:
            if line.strip().startswith("```"):
                in_code = not in_code
                shifted.append(line)
                continue
            if not in_code:
                m_h = re.match(r'^(#{1,5})(\s+.*)$', line)
                if m_h:
                    line = "#" + m_h.group(1) + m_h.group(2)
            shifted.append(line)
        cleaned = shifted

    # Collapse 3+ consecutive blank lines into 2
    text = "\n".join(cleaned)
    text = re.sub(r'\n{3,}', '\n\n', text).strip() + "\n"
    return text, heading_id_markers


def _extract_intro(md_text: str) -> str:
    """Extract a clean one-sentence intro for the module index card."""
    in_code = False
    for raw in md_text.splitlines():
        s = raw.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not s:
            continue
        if s.startswith(("#", "|", "---", "![", "<")):
            continue
        s = s.lstrip(">*-• ").strip()
        # Strip markdown formatting
        s = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', s)
        s = re.sub(r'[*_`]+', '', s)
        s = re.sub(r'ANCHORID_[a-zA-Z0-9_]+_END', '', s).strip()
        if len(s) >= 14:
            return s[:72] + ("…" if len(s) > 72 else "")
    return "一节一页完整讲解与源码梳理。"


def _apply_heading_anchors_and_build_toc(
    body_html: str,
    heading_id_markers: dict[str, str],
) -> tuple[str, str]:
    """Apply explicit heading IDs (e.g. qa-sys01) and build right-side TOC HTML."""
    toc_items: list[tuple[int, str, str]] = []
    used_ids: set[str] = set()

    def _strip_tags(fragment: str) -> str:
        return html.unescape(re.sub(r'<[^>]+>', '', fragment)).strip()

    def repl(m: re.Match[str]) -> str:
        tag = m.group(1).lower()
        attrs = m.group(2)
        inner = m.group(3)

        explicit_id = None
        for token, aid in heading_id_markers.items():
            if token in inner:
                inner = inner.replace(token, "").strip()
                explicit_id = aid
                break

        id_match = re.search(r'\bid="([^"]+)"', attrs)
        hid = explicit_id or (id_match.group(1) if id_match else f"sec-{len(toc_items) + 1}")
        base_id = hid
        suffix = 2
        while hid in used_ids:
            hid = f"{base_id}-{suffix}"
            suffix += 1
        used_ids.add(hid)

        if id_match:
            attrs = re.sub(r'\bid="[^"]+"', f'id="{html.escape(hid, quote=True)}"', attrs, count=1)
        else:
            attrs = f' id="{html.escape(hid, quote=True)}"' + attrs

        level = 2 if tag == "h2" else 3
        label = _strip_tags(inner)
        if label:
            toc_items.append((level, hid, label))
        return f"<{tag}{attrs}>{inner}</{tag}>"

    updated_html = HEADING_TAG_RE.sub(repl, body_html)

    if not toc_items:
        toc_html = '<p class="muted" style="font-size:13px;margin:8px 0">本节无二级小节</p>'
    else:
        lis = "".join(
            f'<li class="lv{lv}"><a href="#{html.escape(hid, quote=True)}">{html.escape(label)}</a></li>'
            for lv, hid, label in toc_items
        )
        toc_html = f"<ul>{lis}</ul>"
    return updated_html, toc_html


def _topbar_html() -> str:
    return (
        '<header class="topbar">'
        '<a class="topbar-back" href="../../cockpit.html">← 中控台</a>'
        '<a class="brand" href="../index.html" aria-current="page">学习书架</a>'
        '<nav aria-label="主导航">'
        '<a href="../../pages/favorites.html">我的收藏</a>'
        '<a href="../search.html">全文搜索</a>'
        '<a href="../../index.html">Hot 100</a>'
        '</nav></header>'
    )


def _render_chapter_page(
    chapter: dict,
    all_chapters: list[dict],
    body_html: str,
    toc_html: str,
) -> str:
    idx = chapter["index"]
    total = len(all_chapters)
    title = chapter["title"]
    topic = chapter["topic"]

    # Left sidebar: full section catalog
    rail_links = []
    for item in all_chapters:
        is_current = item["index"] == idx
        cls = "shelf-topic-link current" if is_current else "shelf-topic-link"
        aria = ' aria-current="page"' if is_current else ""
        rail_links.append(
            f'<a class="{cls}" href="{item["href"]}"{aria}>'
            f'<span class="shelf-topic-number">{item["index"]:02d}</span>'
            f'<span class="shelf-topic-label">{html.escape(item["title"])}</span></a>'
        )
    left_rail = (
        f'<details class="shelf-topic-rail" open>'
        f'<summary><span>本专题目录</span><span class="shelf-topic-count">{total} 节</span></summary>'
        f'<nav class="shelf-topic-links" aria-label="本专题章节">{"".join(rail_links)}</nav>'
        f'</details>'
    )

    # Bottom chapter navigation
    prev_link = (
        f'<a class="nav-prev" data-chapter-nav="prev" href="{all_chapters[idx - 2]["href"]}">← 上一节</a>'
        if idx > 1 else ""
    )
    next_link = (
        f'<a class="nav-next" data-chapter-nav="next" href="{all_chapters[idx]["href"]}">下一节 →</a>'
        if idx < total else ""
    )
    chapter_nav = (
        f'<nav class="chapter-nav" aria-label="章节导航">'
        f'{prev_link}<a class="nav-toc" href="index.html">目录</a>{next_link}'
        f'</nav>'
    )

    # Right sidebar: in-page TOC
    right_rail = (
        f'<aside class="sol-rail sol-rail-right shelf-page-rail" aria-label="本页目录">'
        f'<div class="sol-rail-title">本页目录</div>'
        f'<div class="toc">{toc_html}</div>'
        f'</aside>'
    )

    # Optional Mermaid scripts
    diagram_scripts = ""
    if 'class="mermaid-diagram"' in body_html:
        diagram_scripts = (
            f'<script src="../assets/mermaid-11.16.1.min.js?v={LIBRARY_MERMAID_VERSION}"></script>'
            f'<script src="../assets/library-mermaid.js?v={LIBRARY_MERMAID_VERSION}"></script>'
        )

    long_chapter_head = ""
    if body_html.count('<div class="codehilite"') >= 45:
        long_chapter_head = (
            "<style>"
            ".reader-body .codehilite{content-visibility:auto;contain-intrinsic-size:auto 310px;margin:16px 0;}"
            ".reader-body .codehilite pre{margin:0;}"
            "@media(max-width:560px){.reader-body .codehilite{contain-intrinsic-size:auto 520px;}}"
            "</style>"
        )

    page_js = """<script>
(function(){
  var topicRail=document.querySelector('.shelf-topic-rail');
  if(topicRail&&window.matchMedia('(max-width: 1280px)').matches)topicRail.open=false;
  var rail=document.querySelector('.shelf-topic-links');
  if(rail){
    var focusCurrent=function(){
      var cur=rail.querySelector('.shelf-topic-link.current');
      if(!cur)return;
      var rr=rail.getBoundingClientRect(),cr=cur.getBoundingClientRect();
      rail.scrollTop=Math.max(0,rail.scrollTop+(cr.top-rr.top)-rr.height/2+cr.height/2);
    };
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',focusCurrent);
    else focusCurrent();
    window.addEventListener('load',focusCurrent);
  }
  document.querySelectorAll('.reader-body pre:not(.mermaid)').forEach(function(pre){
    pre.style.position='relative';
    var btn=document.createElement('button');
    btn.type='button';btn.className='copy-btn';btn.textContent='复制';
    btn.addEventListener('click',function(){
      var code=pre.querySelector('code');
      var text=(code||pre).innerText;
      var done=function(ok){btn.textContent=ok?'已复制':'复制失败';setTimeout(function(){btn.textContent='复制';},1200);};
      if(navigator.clipboard&&navigator.clipboard.writeText){
        navigator.clipboard.writeText(text).then(function(){done(true);},function(){done(false);});
      }else{
        var ta=document.createElement('textarea');ta.value=text;document.body.appendChild(ta);ta.select();
        var ok=document.execCommand('copy');ta.remove();done(ok);
      }
    });
    pre.appendChild(btn);
  });
  var otpLinks=[].slice.call(document.querySelectorAll('.sol-rail-right .toc a[href^="#"]'));
  if(otpLinks.length){
    var otpMap=new Map(otpLinks.map(function(a){return [a.getAttribute('href').slice(1),a];}));
    var io=new IntersectionObserver(function(es){
      es.forEach(function(e){
        if(e.isIntersecting){
          otpLinks.forEach(function(a){a.classList.remove('active');});
          var a=otpMap.get(e.target.id);
          if(a)a.classList.add('active');
        }
      });
    },{rootMargin:'-12% 0px -78% 0px'});
    otpMap.forEach(function(a,id){var h=document.getElementById(id);if(h)io.observe(h);});
  }
  document.addEventListener('keydown',function(e){
    if(!(e.ctrlKey||e.metaKey)||e.altKey||e.shiftKey)return;
    if(e.key!=='ArrowLeft'&&e.key!=='ArrowRight')return;
    var el=document.activeElement;
    if(el&&(/^(input|textarea|select)$/i.test(el.tagName)||el.isContentEditable))return;
    var link=document.querySelector('[data-chapter-nav="'+(e.key==='ArrowRight'?'next':'prev')+'"]');
    if(!link||!link.getAttribute('href'))return;
    e.preventDefault();link.click();
  });
})();
</script>"""

    return (
        '<!doctype html><html lang="zh-CN"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        f'<title>{html.escape(title)} · {html.escape(BOOK_TITLE)} · InterviewForge</title>'
        f'<link rel="stylesheet" href="../assets/library.css?v={LIBRARY_CSS_VERSION}">'
        f'<script src="../../assets/ui.js?v={ASSET_VERSION}" defer></script>'
        f'{long_chapter_head}'
        '</head><body>'
        '<div class="shell chapter-shell site-shell-cols">'
        f'{_topbar_html()}\n'
        f'{left_rail}\n'
        f'<main class="reader" data-page-type="library/chapter" data-content-id="agenthub-study:{idx:02d}">'
        '<nav class="breadcrumb" aria-label="章节导航">'
        '<a href="../../cockpit.html">🎛️ 中控台</a><span aria-hidden="true">›</span>'
        '<a href="../index.html">学习书架</a><span aria-hidden="true">›</span>'
        f'<a href="index.html">{html.escape(BOOK_TITLE)}</a><span aria-hidden="true">›</span>'
        f'<span aria-current="page">{html.escape(title)}</span></nav>'
        f'<div class="module-meta">{html.escape(BOOK_CATEGORY)} · {html.escape(topic)} · 第 {idx} / {total} 节 · <span class="muted">仅永久管理员可见</span></div>'
        f'<h1>{html.escape(title)}</h1>'
        f'<div class="reader-grid"><div class="reader-body">{body_html}</div></div>'
        f'{chapter_nav}'
        '</main>'
        f'{right_rail}'
        '</div>'
        f'{page_js}'
        f'{diagram_scripts}'
        '</body></html>\n'
    )


def _render_index_page(chapters: list[dict], topics: list[str]) -> str:
    total = len(chapters)
    chapters_json = json.dumps(
        [
            {
                "index": c["index"],
                "title": c["title"],
                "topic": c["topic"],
                "intro": c["intro"],
                "href": c["href"],
            }
            for c in chapters
        ],
        ensure_ascii=False,
    )
    topics_options = "".join(
        f'<option value="{html.escape(t, quote=True)}">{html.escape(t)}</option>'
        for t in topics
    )

    index_js = f"""<script>
const chapters={chapters_json};
const grid=document.getElementById('chapterGrid');
const empty=document.getElementById('empty');
const search=document.getElementById('search');
const topic=document.getElementById('topic');
function esc(v){{return String(v).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));}}
function renderCards(){{
  const q=(search.value||'').trim().toLowerCase();
  const t=topic.value||'';
  const items=chapters.filter(c=>{{
    if(t&&c.topic!==t)return false;
    if(q&&!(c.title+' '+c.topic+' '+c.intro).toLowerCase().includes(q))return false;
    return true;
  }});
  empty.hidden=items.length>0;
  grid.innerHTML=items.map(c=>`
    <article class="chapter-card">
      <div class="chapter-head">
        <span class="chapter-num">${{String(c.index).padStart(2,'0')}}</span>
        <span class="chapter-topic">${{esc(c.topic)}}</span>
      </div>
      <h2><a href="${{esc(c.href)}}">${{esc(c.title)}}</a></h2>
      <p class="chapter-intro">${{esc(c.intro)}}</p>
      <div class="chapter-foot">
        <a class="chapter-link" href="${{esc(c.href)}}">开始阅读 →</a>
      </div>
    </article>
  `).join('');
}}
search.addEventListener('input',renderCards);
topic.addEventListener('change',renderCards);
renderCards();
</script>"""

    return (
        '<!doctype html><html lang="zh-CN"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        f'<title>{html.escape(BOOK_TITLE)} · InterviewForge</title>'
        f'<link rel="stylesheet" href="../assets/library.css?v={LIBRARY_CSS_VERSION}">'
        f'<script src="../../assets/ui.js?v={ASSET_VERSION}" defer></script>'
        '<style>'
        '.chapter-head{display:flex;align-items:center;gap:8px;margin-bottom:8px}'
        '.chapter-num{font:700 12px/1 var(--mono,monospace);padding:3px 7px;border-radius:6px;background:var(--brand-soft);color:var(--brand)}'
        '.chapter-topic{font-size:12px;color:var(--muted)}'
        '.chapter-foot{margin-top:auto;padding-top:10px}'
        '.chapter-link{font-size:13px;font-weight:600;color:var(--brand);text-decoration:none}'
        '.chapter-link:hover{text-decoration:underline}'
        '</style>'
        '</head><body>'
        '<div class="shell">'
        f'{_topbar_html()}\n'
        '<header class="module-hero">'
        '<div>'
        f'<h1>{html.escape(BOOK_TITLE)}</h1>'
        f'<div class="module-sub">{html.escape(BOOK_CATEGORY)} · {total} 节 · 仅永久管理员可见</div>'
        f'<div class="module-about">{html.escape(BOOK_ABOUT)}</div>'
        '</div>'
        '<div class="module-stats">'
        f'<div class="stat"><span>节数</span><strong>{total}</strong></div>'
        '<div class="stat"><span>课程</span><strong>20 讲</strong></div>'
        '<div class="stat"><span>面试题</span><strong>220 题</strong></div>'
        '</div>'
        '</header>'
        '<section class="module-controls" aria-label="筛选章节">'
        '<div class="field"><label for="search">搜索</label><input id="search" type="search" placeholder="标题、讲次或简介" autocomplete="off"></div>'
        f'<div class="field"><label for="topic">专题</label><select id="topic"><option value="">全部专题</option>{topics_options}</select></div>'
        '</section>'
        '<section class="chapter-grid" id="chapterGrid"></section>'
        '<div id="empty" class="empty" hidden>没有匹配的内容，请调整搜索词或筛选条件。</div>'
        '</div>'
        f'{index_js}'
        '</body></html>\n'
    )


def build(source_path: Path = DEFAULT_SOURCE, output_dir: Path = OUTPUT_DIR) -> dict:
    raw_text = source_path.read_text(encoding="utf-8")
    all_lines = raw_text.splitlines()
    ref_defs = _collect_ref_defs(all_lines)
    if SUPPLEMENTAL_REFS.is_file():
        for key, value in json.loads(SUPPLEMENTAL_REFS.read_text(encoding="utf-8")).items():
            url, title = value[0], value[1]
            ref_defs.setdefault(key.lower(), (url, title))

    # First pass: slice lines per section & build global anchor_map
    sections: list[dict] = []
    anchor_map: dict[str, tuple[str, str | None]] = {}

    for idx, (start_line, end_line, title, topic) in enumerate(SECTION_SPECS, 1):
        href = f"chapter-{idx:02d}.html"
        slice_lines = all_lines[start_line - 1 : end_line] if end_line is not None else all_lines[start_line - 1 :]
        sections.append(
            {
                "index": idx,
                "href": href,
                "title": title,
                "topic": topic,
                "raw_lines": slice_lines,
            }
        )
        in_code = False
        for line in slice_lines:
            s = line.strip()
            if s.startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            m = ANCHOR_LINE_RE.match(s)
            if m:
                aid = m.group(1)
                if aid.startswith("qa-"):
                    anchor_map[aid] = (href, aid)
                else:
                    anchor_map[aid] = (href, None)

    # historical-course anchor (line 241) lives right before Lesson 1 -> point to Lesson 1
    anchor_map.setdefault("historical-course", ("chapter-03.html", None))

    output_dir.mkdir(parents=True, exist_ok=True)
    # Remove any stale chapter-*.html if section count ever changes
    for old_file in output_dir.glob("chapter-*.html"):
        old_file.unlink()

    topics: list[str] = []
    for sec in sections:
        if sec["topic"] not in topics:
            topics.append(sec["topic"])

    rendered_chapters: list[tuple[dict, str, str]] = []
    total_code_blocks = 0
    total_mermaid = 0

    for sec in sections:
        cleaned_md, heading_id_markers = _normalize_section_markdown(
            sec["raw_lines"], ref_defs, sec["href"], anchor_map
        )
        sec["intro"] = _extract_intro(cleaned_md)
        body_html = render_markdown(cleaned_md)
        body_html, toc_html = _apply_heading_anchors_and_build_toc(body_html, heading_id_markers)

        # Sanity assertions: no leftover abnormal archive markers
        assert "<!-- BEGIN" not in body_html and "<!-- END" not in body_html, f"Leftover comment in {sec['href']}"
        assert "<a id=" not in body_html, f"Leftover raw anchor tag in {sec['href']}"
        assert "ANCHORID_" not in body_html, f"Leftover anchor token in {sec['href']}"

        total_code_blocks += body_html.count('<div class="codehilite"')
        total_mermaid += body_html.count('class="mermaid-diagram"')
        rendered_chapters.append((sec, body_html, toc_html))

    for sec, body_html, toc_html in rendered_chapters:
        page_html = _render_chapter_page(sec, sections, body_html, toc_html)
        (output_dir / sec["href"]).write_text(page_html, encoding="utf-8")

    index_html = _render_index_page(sections, topics)
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")

    return {
        "chapters": len(sections),
        "code_blocks": total_code_blocks,
        "mermaid_diagrams": total_mermaid,
        "ref_defs_inlined": len(ref_defs),
        "anchors_mapped": len(anchor_map),
        "output_dir": str(output_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AgentHub private study bookshelf pages.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Source Markdown file path")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR, help="Output directory")
    args = parser.parse_args()
    stats = build(args.source, args.output)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
