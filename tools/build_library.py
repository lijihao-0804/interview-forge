# =============================================================================
# build_library.py —— “学习书架”(Library) 静态站点生成器
#
# 【在构建链中的位置】
#   build_hot100.py 的 build() 末尾用 subprocess 调用本文件(见 build_hot100.py
#   第 1242-1244 行)，因此本文件是“Interview Forge → 书架”流水线的收尾环节：
#   它把 28 门课程模块的 Markdown 源(library_catalog.LIBRARY_MODULES 登记)与
#   Hot 100 题目目录(build_hot100.PROBLEMS)统一整理进 library/ 目录，产出
#   静态页面与离线索引；随后 build_html_site.py 再被调用生成可视化等剩余页面。
#
# 【书架体系数据流：模块登记 → 章节拆分 → 页面生成 → 搜索索引 → 资产版本】
#   1) 登记    ：library_catalog.LIBRARY_MODULES 人工登记“源笔记路径 → 模块
#                id/标题/分类/简介”，Hot 100 模块则由程序从题目目录生成；
#   2) 章节拆分：split_chapters() 按 “##” 二级标题把每份源笔记切成章节；
#   3) 净化    ：normalize_chapter_markdown() 修复阅读副本的结构标记(不改源笔记)，
#                rewrite_local_links() 改写跨模块 .md 互链并把本地图片拷入 assets；
#   4) 渲染    ：render_markdown() 输出 HTML(数学公式、Pygments 高亮、Mermaid 图表)；
#   5) 页面生成：每模块 index.html(模块首页) + chapter-NN.html(章节页) + assets/；
#   6) 搜索索引：search-index.json(离线全文索引) + search.html(客户端评分搜索页)；
#   7) 资产版本：ASSET_VERSION 作为 CSS/JS 链接的 ?v= 参数，改样式后递增即可刷新。
#
# 【与 study_server(学习记录服务)的关系】
#   本文件只生成“静态骨架”。学习进度、轮次、复习到期日期都由运行中的
#   study_server.py 提供(API：/api/library、/api/daily、/api/content/complete、
#   /api/complete)；页面 JS 启动时 fetch 这些接口，连不上时自动降级为
#   “静态浏览模式”(只读展示、按钮禁用)。
#   本文件写出的 library/manifest.json 中的 routes 表，正是 study_server 把
#   请求 URL 反查成 module_id / content_id、再写入 content_events 的关键契约，
#   因此“书架静态页”与“学习记录服务”是单向依赖：页面内容 ← 动态数据。
#
# 【维护提示】本文件只允许“新增注释/新增代码”，所有常量字符串(LIBRARY_CSS、
#   MERMAID_JS、MODULE_PAGE_JS)构建时按原样落盘，改动它们会改变线上产物。
# =============================================================================
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from urllib.parse import unquote

# ---- 渲染依赖 ----
# markdown：Python-Markdown，负责把章节 Markdown 转 HTML(extra/tables 等扩展)；
# pygments：代码高亮着色，与高亮函数配合产出带 data-lang 的 codehilite 结构。
import markdown
import build_cache
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.lexers.special import TextLexer
from pygments.util import ClassNotFound

# ---- 跨模块复用(仅构建期导入，运行期由 study_server 另行读取产物) ----
# build_html_site.render_math_in_markdown：数学公式($$…$$ / $…$)预处理函数，
#   三个构建脚本共用，能正确跳过代码围栏与行内代码里的 $；
# build_hot100.PROBLEMS / repair_indented_headings / safe_name：
#   - PROBLEMS：Hot 100 题目目录(build_hot100 模块级解析结果)——书架把每道题当成
#     一章来登记，因此要求 build_hot100 先于本文件执行(其 build() 末尾调本文件)；
#   - repair_indented_headings：修复“误嵌在列表/缩进块中的标题与代码围栏”，
#     与 build_hot100 共用的净化函数，拆章前先跑一遍，两边对标题的判定一致；
#   - safe_name：把标题里的文件非法字符替换成 “-”，用于生成题解章节文件名；
# library_catalog：人工维护的模块登记表(LIBRARY_MODULES)与 Hot 100 模块占位描述
#   (HOT100_MODULE)，是书架目录结构的唯一事实来源。
from build_html_site import render_math_in_markdown
from build_hot100 import PROBLEMS, repair_indented_headings, safe_name
from library_catalog import HOT100_MODULE, LIBRARY_MODULES, MODULE_ORDER

# 并行渲染进程数：8（或按 CPU 核数自动收敛）。章节正文渲染是纯函数
# （render_markdown(text) → str），进程池安全；元数据收集与聚合产物仍串行。
PARALLEL_WORKERS = min(8, os.cpu_count() or 4)


# ---- 目录与版本约定 ----
# HOT100_ROOT：仓库根目录(本文件所在 tools/ 的上一级)，项目代码与产物都挂在它下面，
#   同时是 Interview Forge 站点根，书架链接回站根用相对路径 ../ 本身；
# NOTES_ROOT：书籍笔记源根目录 <仓库根>/books，LIBRARY_MODULES 的 source 相对
#   它解析——全部课程源笔记统一归档在 books/（含 hot100 与单行本）；
# OUTPUT_ROOT：书架产物目录 <仓库根>/library，静态服务器把该目录挂载为 /library；
# ASSET_VERSION：资产版本号。所有页面把样式/脚本链接写成 ?v=ASSET_VERSION，
#   浏览器据此做缓存失效；每次改动 CSS/JS 常量后应递增该值再重新构建
#   (构建命令：tools/build_hot100.py 或直接运行本文件)。
HOT100_ROOT = Path(__file__).resolve().parents[1]
NOTES_ROOT = HOT100_ROOT / "books"
OUTPUT_ROOT = HOT100_ROOT / "library"
ASSET_VERSION = "20260830-mobile1"


# 书架全局样式常量，构建时写入 library/assets/library.css(见 build() 第 0 步)。
# 字符串内部按区块自组织：根变量与明暗主题 → 通用组件(顶栏/卡片/筛选) →
# 模块首页 → 章节阅读页 → 书架待复习 → Pygments 代码高亮(含 Java 专属配色) →
# Mermaid 图表；字符串内部已有的 /* … */ 就是各区块的分节注释，可顺读。
# 约束：常量内容构建时原样落盘(LIBRARY_CSS.strip() + "\n")，不得在生成时改写。
LIBRARY_CSS = r"""
:root{color-scheme:light dark;--bg:#f3f5fa;--panel:#fff;--soft:#f7f8fc;--text:#172033;--muted:#647188;--line:#dce2ec;--brand:#5755d4;--brand-soft:#eeedff;--success:#13764b;--success-soft:#e7f6ee;--warning:#a45a00;--shadow:0 14px 38px rgba(31,42,68,.075)}
@media(prefers-color-scheme:dark){:root{--bg:#0f131b;--panel:#181e29;--soft:#141a24;--text:#edf2fb;--muted:#a7b2c4;--line:#313b4c;--brand:#b2b0ff;--brand-soft:#292955;--success:#79d8a8;--success-soft:#17382b;--warning:#ffc474;--shadow:0 18px 46px rgba(0,0,0,.22)}}
*{scrollbar-width:thin;scrollbar-color:color-mix(in srgb,var(--muted) 45%,transparent) transparent}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:color-mix(in srgb,var(--muted) 45%,transparent);border-radius:8px;border:2px solid transparent;background-clip:padding-box}
::-webkit-scrollbar-thumb:hover{background:color-mix(in srgb,var(--muted) 72%,transparent);border:2px solid transparent;background-clip:padding-box}
*{box-sizing:border-box}html{background:var(--bg);scroll-behavior:smooth}body{margin:0;color:var(--text);background:radial-gradient(circle at 12% 0%,color-mix(in srgb,var(--brand) 10%,transparent),transparent 34rem),var(--bg);font:16px/1.78 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}a{color:var(--brand);text-decoration:none}a:hover{text-decoration:underline}:focus-visible{outline:3px solid color-mix(in srgb,var(--brand) 48%,transparent);outline-offset:3px}.shell{width:min(100% - 32px,1120px);margin:auto;padding:24px 0 56px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:22px;padding:11px 14px;border:1px solid var(--line);border-radius:13px;background:var(--panel);box-shadow:0 7px 24px rgba(31,42,68,.045)}.topbar nav{display:flex;gap:10px;flex-wrap:wrap}.brand{color:var(--text);font-weight:750}.hero{margin:30px 0}.hero h1{margin:0;font-size:clamp(30px,4vw,45px);line-height:1.2;letter-spacing:-.025em}.hero p{max-width:720px;margin:10px 0 0;color:var(--muted)}.filters{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 20px}.filters button{padding:7px 11px;border:1px solid var(--line);border-radius:9px;color:var(--text);background:var(--panel);cursor:pointer}.filters button.active{border-color:var(--brand);color:var(--brand);background:var(--brand-soft)}.module-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(280px,100%),1fr));gap:14px}.module-card{display:flex;min-width:0;flex-direction:column;padding:17px;border:1px solid var(--line);border-radius:15px;background:var(--panel);box-shadow:0 7px 22px rgba(31,42,68,.04)}.module-card h2{margin:0;font-size:18px;line-height:1.45}.module-meta{display:flex;justify-content:space-between;gap:12px;margin:8px 0;color:var(--muted);font-size:13px}.module-progress{height:7px;margin:7px 0 12px;overflow:hidden;border-radius:999px;background:var(--line)}.module-progress span{display:block;height:100%;background:linear-gradient(90deg,var(--brand),var(--success))}.module-link{margin-top:auto}.chapter-layout{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:20px;align-items:start}.chapter-list,.reader,.chapter-side{border:1px solid var(--line);border-radius:16px;background:var(--panel);box-shadow:var(--shadow)}.chapter-list{padding:18px}.chapter-list h1{margin:0 0 8px;font-size:28px}.chapter-list>p{color:var(--muted)}.chapters{list-style:none;margin:18px 0 0;padding:0}.chapters li{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:10px;align-items:center;padding:11px 0;border-bottom:1px solid var(--line)}.chapters li:last-child{border-bottom:0}.chapter-no{color:var(--muted);font-variant-numeric:tabular-nums}.rounds{padding:2px 7px;border-radius:999px;color:var(--success);background:var(--success-soft);font-size:12px}.reader{min-width:0;padding:clamp(24px,5vw,52px)}.reader h1{margin:0 0 27px;font-size:clamp(29px,5vw,42px);line-height:1.25}.reader h2{margin:42px 0 16px;padding-bottom:8px;border-bottom:1px solid var(--line);font-size:25px}.reader h3{margin:30px 0 12px;font-size:20px}.reader h4{margin:24px 0 9px;font-size:17px}.reader p{margin:13px 0}.reader ul,.reader ol{padding-left:1.55em}.reader li{margin:5px 0}.reader blockquote{margin:20px 0;padding:12px 16px;border-left:4px solid var(--brand);border-radius:0 10px 10px 0;background:var(--brand-soft)}.reader code{padding:.14em .36em;border-radius:5px;color:var(--brand);background:var(--brand-soft);font: .91em/1.5 ui-monospace,"Cascadia Code",Consolas,monospace;font-variant-ligatures:none}.reader pre{max-width:100%;overflow:auto;padding:17px;border-radius:11px;color:#e9edf7;background:#151a24}.reader pre code{padding:0;color:inherit;background:transparent;font-variant-ligatures:none}.reader table{width:100%;border-collapse:collapse;display:block;overflow:auto}.reader th,.reader td{padding:9px 11px;border:1px solid var(--line);text-align:left}.reader img,.reader video{display:block;max-width:100%;height:auto;margin:20px auto;border-radius:11px}.reader math{font-family:"Cambria Math","STIX Two Math",serif;vertical-align:baseline}.plain-math{white-space:nowrap}.plain-math sup,.plain-math sub{font-size:.72em;line-height:0}.math-inline-wrap{display:inline-block;overflow-x:auto;overflow-y:hidden;vertical-align:-.12em;line-height:1.1}.math-display-wrap{display:block;margin:18px 0;padding:12px;overflow:auto;border:1px solid var(--line);border-radius:10px;background:var(--soft);text-align:center}.mermaid-diagram{max-width:100%;margin:24px 0;overflow-x:auto;overflow-y:hidden;border:1px solid color-mix(in srgb,var(--brand) 18%,var(--line));border-radius:14px;background:linear-gradient(145deg,color-mix(in srgb,var(--brand) 5%,var(--panel)),var(--panel));box-shadow:0 9px 28px rgba(31,42,68,.05)}.reader pre.mermaid{display:flex;min-height:150px;align-items:center;justify-content:center;margin:0;padding:24px;overflow:visible;border-radius:0;color:var(--text);background:transparent;font-family:inherit;white-space:pre-wrap}.reader pre.mermaid svg{display:block;width:auto;max-width:100%!important;height:auto;margin:auto}.mermaid-diagram.is-rendered .mermaid{white-space:normal}.mermaid-error{display:none;margin:0;padding:12px 16px;border-top:1px solid var(--line);color:var(--warning);background:color-mix(in srgb,var(--warning) 7%,var(--panel));font-size:13px}.mermaid-diagram.is-error .mermaid-error{display:block}.chapter-side{padding:16px}.chapter-side h2{margin:0 0 10px;font-size:16px}.chapter-side p{color:var(--muted);font-size:13px}.complete-button{width:100%;padding:9px 12px;border:1px solid color-mix(in srgb,var(--brand) 34%,var(--line));border-radius:9px;color:var(--brand);background:var(--brand-soft);cursor:pointer}.complete-button:disabled{cursor:not-allowed;opacity:.5}.chapter-nav{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:34px;padding-top:20px;border-top:1px solid var(--line)}.chapter-nav .nav-toc{padding:6px 12px;border:1px solid color-mix(in srgb,var(--brand) 34%,var(--line));border-radius:8px;color:var(--brand);background:var(--brand-soft);font-weight:650}.chapter-nav .nav-toc:hover{text-decoration:none;border-color:var(--brand)}.breadcrumb{display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin:-8px 0 18px;color:var(--muted);font-size:13px}.breadcrumb a{color:var(--brand);font-weight:650}.breadcrumb a:hover{text-decoration:underline}.breadcrumb span[aria-current]{color:var(--text)}.notice{margin:12px 0;padding:10px 12px;border:1px solid color-mix(in srgb,var(--warning) 35%,var(--line));border-radius:10px;background:color-mix(in srgb,var(--warning) 7%,var(--panel));font-size:13px}.toast{min-height:24px;margin-top:10px;color:var(--success);font-size:13px}.empty{padding:38px 15px;color:var(--muted);text-align:center}@media(max-width:860px){.chapter-layout{grid-template-columns:1fr}.chapter-side{order:-1}.reader{padding:24px}.reader pre.mermaid{padding:18px}}@media(max-width:560px){.shell{width:min(100% - 18px,1120px);padding-top:14px}.chapters li{grid-template-columns:auto minmax(0,1fr)}.rounds{grid-column:2}.topbar{align-items:flex-start}.reader pre.mermaid{min-height:110px;padding:12px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}

/* 表格居中：按内容宽度自适应并居中，宽表内部横向滚动 */
.reader table{width:max-content;max-width:100%;margin:20px auto;border-collapse:collapse;display:block;overflow:auto}

/* Mermaid 统一视觉：普通步骤使用品牌紫，判断节点使用暖色；分组与连线保持中性。 */
:root{--diagram-surface:#fbfcff;--diagram-node:#f1f2ff;--diagram-node-border:#7775dc;--diagram-decision:#fff7e8;--diagram-decision-border:#dfa34c;--diagram-cluster:#f7f9fd;--diagram-cluster-border:#d4dbe7;--diagram-line:#8490a3;--diagram-label-bg:#fbfcff;--diagram-node-text:#344056}
@media(prefers-color-scheme:dark){:root{--diagram-surface:#fbfcff;--diagram-node:#f1f2ff;--diagram-node-border:#7775dc;--diagram-decision:#fff7e8;--diagram-decision-border:#dfa34c;--diagram-cluster:#f7f9fd;--diagram-cluster-border:#d4dbe7;--diagram-line:#8490a3;--diagram-label-bg:#fbfcff;--diagram-node-text:#344056}}
.mermaid-diagram{background:radial-gradient(circle at 18% 8%,#f1f2ff 0,transparent 43%),var(--diagram-surface)}
.reader pre.mermaid{color:var(--diagram-node-text)}
.mermaid-diagram[data-diagram-type="flowchart"] .node rect,.mermaid-diagram[data-diagram-type="flowchart"] .node circle,.mermaid-diagram[data-diagram-type="flowchart"] .node ellipse,.mermaid-diagram[data-diagram-type="flowchart"] .node path{fill:var(--diagram-node)!important;stroke:var(--diagram-node-border)!important;stroke-width:1.6px!important}
.mermaid-diagram[data-diagram-type="flowchart"] .node rect{rx:10px;ry:10px}
.mermaid-diagram[data-diagram-type="flowchart"] .node polygon{fill:var(--diagram-decision)!important;stroke:var(--diagram-decision-border)!important;stroke-width:1.7px!important}
.mermaid-diagram[data-diagram-type="flowchart"] .nodeLabel,.mermaid-diagram[data-diagram-type="flowchart"] .label text{color:var(--diagram-node-text)!important;fill:var(--diagram-node-text)!important;font-weight:500}
.mermaid-diagram .flowchart-link{stroke:var(--diagram-line)!important;stroke-width:1.65px!important}
.mermaid-diagram .marker{fill:var(--diagram-line)!important;stroke:var(--diagram-line)!important}
.mermaid-diagram .edgeLabel{color:var(--text)!important;background:var(--diagram-label-bg)!important}
.mermaid-diagram .edgeLabel .labelBkg{fill:var(--diagram-label-bg)!important;opacity:.96}
.mermaid-diagram .cluster rect{fill:var(--diagram-cluster)!important;stroke:var(--diagram-cluster-border)!important;stroke-width:1.2px!important;stroke-dasharray:5 4;rx:12px;ry:12px}
.mermaid-diagram .cluster-label text,.mermaid-diagram .cluster-label span{color:var(--muted)!important;fill:var(--muted)!important;font-weight:500}
.mermaid-diagram[data-diagram-type="sequenceDiagram"] .actor{rx:8px;ry:8px}
.mermaid-diagram svg text,.mermaid-diagram svg foreignObject{font-weight:400}
.module-card[hidden]{display:none}
.filters button:hover{border-color:color-mix(in srgb,var(--brand) 45%,var(--line));background:var(--brand-soft)}
.module-hero{display:flex;align-items:flex-end;justify-content:space-between;gap:22px;flex-wrap:wrap;margin:26px 0 8px}
.module-hero h1{margin:0;font-size:clamp(28px,4vw,42px);line-height:1.18}
.module-sub{margin-top:8px;color:var(--muted);font-size:15px}
.module-about{max-width:780px;margin:12px 0 0;color:var(--muted);font-size:14px;line-height:1.8}
.connection{display:inline-flex;align-items:center;gap:7px;margin-top:12px;color:var(--muted);font-size:13px}
.connection::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--warning)}
.connection.online::before{background:var(--success)}
.module-stats{display:grid;grid-template-columns:repeat(3,minmax(110px,1fr));gap:9px}
.module-stats .stat{min-width:0;padding:10px 13px;border:1px solid var(--line);border-radius:13px;background:var(--panel);box-shadow:0 5px 18px rgba(31,42,68,.035)}
.module-stats .stat span{color:var(--muted);font-size:12px}
.module-stats .stat strong{display:block;margin-top:1px;font-size:23px;line-height:1.25;font-variant-numeric:tabular-nums}
.module-progress{margin:0 0 20px}
.module-progress .progress-head{display:flex;justify-content:space-between;gap:12px;margin-bottom:7px;color:var(--muted);font-size:13px}
.module-progress .progress-head strong{color:var(--text)}
.module-progress .bar{height:9px;overflow:hidden;border-radius:999px;background:var(--line)}
.module-progress .bar>div{width:0;height:100%;background:linear-gradient(90deg,var(--brand),var(--success));transition:width .22s ease}
.module-controls{display:grid;grid-template-columns:minmax(200px,2fr) repeat(2,minmax(140px,1fr));gap:12px;margin:0 0 18px;padding:14px;border:1px solid var(--line);border-radius:15px;background:var(--panel);box-shadow:var(--shadow)}
.module-controls .field{display:grid;gap:6px;min-width:0}
.field[hidden]{display:none}
.module-controls .field label{color:var(--muted);font-size:13px;font-weight:650}
.module-controls input,.module-controls select{width:100%;min-width:0;padding:9px 10px;border:1px solid var(--line);border-radius:9px;color:var(--text);background:var(--soft)}
.chapter-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(270px,100%),1fr));gap:13px}
.chapter-card{min-width:0;padding:15px;border:1px solid var(--line);border-radius:14px;background:var(--panel);box-shadow:0 7px 22px rgba(31,42,68,.04);transition:border-color .18s,transform .18s,box-shadow .18s}
.chapter-card:hover{border-color:color-mix(in srgb,var(--brand) 38%,var(--line));transform:translateY(-1px);box-shadow:0 11px 27px rgba(31,42,68,.075)}
.chapter-card.studied{box-shadow:inset 4px 0 var(--success),0 7px 22px rgba(31,42,68,.04)}
.chapter-card .card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.chapter-card h2{min-width:0;margin:0;font-size:16px;line-height:1.45}
.chapter-card h2 a{color:var(--text)}
.chapter-card h2 a:hover{color:var(--brand)}
.chapter-card .round-count{flex:0 0 auto;padding:2px 7px;border-radius:999px;color:var(--success);background:var(--success-soft);font-size:12px;font-variant-numeric:tabular-nums}
.chapter-card .meta{display:flex;gap:7px;flex-wrap:wrap;margin:8px 0;color:var(--muted);font-size:13px}
.chapter-card .pill{padding:2px 8px;border-radius:999px;color:var(--brand);background:var(--brand-soft)}
.chapter-card .difficulty-简单{color:var(--success)}
.chapter-card .difficulty-中等{color:var(--warning)}
.chapter-card .difficulty-困难{color:var(--danger)}
.chapter-card .method{min-height:46px;color:var(--muted);overflow-wrap:anywhere}
.chapter-card .card-actions{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:12px;padding-top:11px;border-top:1px solid var(--line)}
.chapter-card .last-study{min-width:0;color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chapter-card .round-button{flex:0 0 auto;padding:6px 9px;border:1px solid color-mix(in srgb,var(--brand) 34%,var(--line));border-radius:8px;color:var(--brand);background:var(--brand-soft);cursor:pointer}
.chapter-card .round-button:hover:not(:disabled){border-color:var(--brand);color:var(--brand-strong)}
.chapter-card .round-button:disabled{cursor:not-allowed;opacity:.52}
@media(max-width:760px){.module-hero{align-items:flex-start}.module-stats{width:100%;grid-template-columns:repeat(3,1fr)}.module-controls{grid-template-columns:1fr;padding:12px}.chapter-card .method{min-height:0}}
@media(max-width:520px){.module-stats{grid-template-columns:repeat(2,1fr)}.chapter-card .card-actions{align-items:flex-end}.chapter-card .last-study{white-space:normal}}

/* 章节阅读页：学习记录状态条（替代原固定侧栏，阅读区恢复全宽） */
.chapter-status{display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px;margin:0 0 24px;padding:10px 14px;border:1px solid var(--line);border-radius:11px;background:var(--soft);color:var(--muted);font-size:13px}
.chapter-status .complete-button{width:auto;margin-left:auto;padding:5px 12px;border:1px solid color-mix(in srgb,var(--brand) 34%,var(--line));border-radius:999px;color:var(--brand);background:var(--brand-soft);font-size:12px;cursor:pointer}
.chapter-status .complete-button:disabled{cursor:not-allowed;opacity:.5}
.chapter-status .notice,.chapter-status .toast{margin:0}

/* 阅读排版宽松化：加大行距、段距与留白，页面够宽不必挤 */
.reader{line-height:1.9;padding:clamp(30px,6vw,64px)}
.reader p{margin:17px 0}
.reader h2{margin:56px 0 18px}
.reader h3{margin:40px 0 14px}
.reader h4{margin:30px 0 11px}
.reader ul,.reader ol{padding-left:1.7em}
.reader li{margin:7px 0}
.reader blockquote{margin:26px 0;padding:15px 19px}
.reader code{padding:.16em .44em}
.reader pre{padding:21px 24px}
.reader th,.reader td{padding:13px 17px}
.reader table{margin:28px auto}
.reader img,.reader video{margin:30px auto}
.math-display-wrap{padding:16px;margin:26px 0}
.reader h1{margin:0 0 18px}
.chapter-status{margin:0 0 30px}
.chapter-nav{margin-top:44px;padding-top:26px}
.demo-embed{margin:26px 0;border:1px solid color-mix(in srgb,var(--brand) 22%,var(--line));border-radius:14px;overflow:hidden;background:var(--panel);box-shadow:0 9px 28px rgba(31,42,68,.05)}
.demo-embed iframe{display:block;width:100%;height:560px;min-height:420px;border:0}

/* 书架待复习：总页汇总条 / 模块角标 / 模块页到期区块 / 章节卡徽标 */
.shelf-due-summary{margin:0 0 20px;padding:12px 16px;border:1px solid color-mix(in srgb,var(--brand) 26%,var(--line));border-radius:12px;background:linear-gradient(90deg,color-mix(in srgb,var(--brand) 8%,var(--panel)),var(--panel));display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.shelf-due-summary strong{color:var(--brand);font-variant-numeric:tabular-nums}
.shelf-due-summary .shelf-due-go{flex:0 0 auto;padding:6px 12px;border:1px solid color-mix(in srgb,var(--brand) 36%,var(--line));border-radius:999px;color:var(--brand);background:var(--brand-soft);font-size:13px;font-weight:650}
.shelf-due-summary .shelf-due-go:hover{text-decoration:none;border-color:var(--brand)}
.module-due-badge{flex:0 0 auto;margin-left:auto;padding:2px 8px;border-radius:999px;color:var(--warning);background:color-mix(in srgb,var(--warning) 14%,var(--panel));font-size:12px;font-variant-numeric:tabular-nums}
.module-due-badge.overdue{color:var(--danger);background:color-mix(in srgb,var(--danger) 12%,var(--panel))}
.module-card .card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
.module-card .card-head h2{min-width:0}
.module-due-badge[hidden]{display:none}
.module-due{margin:0 0 22px;padding:16px;border:1px solid var(--line);border-radius:15px;background:var(--panel);box-shadow:var(--shadow)}
.module-due h2{margin:0 0 10px;font-size:18px}
.due-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap}
.due-head h2{margin:0}
.due-summary{color:var(--muted);font-size:13px;margin:0 0 10px}
.due-summary strong{color:var(--warning)}
.due-list{display:grid;gap:8px}
.due-item{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 12px;border:1px solid var(--line);border-radius:10px;background:var(--soft)}
.due-item a{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text);font-weight:650}
.due-item a:hover{color:var(--brand)}
.due-item .due-date{flex:0 0 auto;padding:2px 8px;border-radius:999px;font-size:12px;color:var(--success);background:var(--success-soft);font-variant-numeric:tabular-nums}
.due-item.due-overdue .due-date{color:var(--danger);background:color-mix(in srgb,var(--danger) 12%,var(--panel))}
.due-empty{padding:10px 4px;color:var(--muted);font-size:13px}
.chapter-card .due-pill{flex:0 0 auto;padding:2px 7px;border-radius:999px;font-size:12px;color:var(--warning);background:color-mix(in srgb,var(--warning) 14%,var(--panel))}
.chapter-card .due-pill.overdue{color:var(--danger);background:color-mix(in srgb,var(--danger) 12%,var(--panel))}
.chapter-status .due-line{font-variant-numeric:tabular-nums}
.chapter-status .due-line.due-overdue{color:var(--danger);font-weight:650}

/* 代码高亮：Pygments 词法着色，浅色/深色双主题 */
:root{--code-bg:#f6f8fa;--code-text:#24292e}
@media(prefers-color-scheme:dark){:root{--code-bg:#151a24;--code-text:#e9edf7}}
.reader pre{color:var(--code-text);background:var(--code-bg)}
.reader .codehilite .k,.reader .codehilite .kd,.reader .codehilite .kn,.reader .codehilite .kt{color:#cf222e}
.reader .codehilite .s,.reader .codehilite .s1,.reader .codehilite .s2,.reader .codehilite .sb,.reader .codehilite .sc,.reader .codehilite .dl{color:#0a3069}
.reader .codehilite .c,.reader .codehilite .c1,.reader .codehilite .cm,.reader .codehilite .cs{color:#6e7781;font-style:italic}
.reader .codehilite .n,.reader .codehilite .p,.reader .codehilite .w{color:#24292e}
.reader .codehilite .na{color:#0550ae}
.reader .codehilite .nf,.reader .codehilite .nn{color:#8250df}
.reader .codehilite .nc,.reader .codehilite .nb,.reader .codehilite .bp{color:#953800}
.reader .codehilite .mi,.reader .codehilite .mf,.reader .codehilite .il,.reader .codehilite .m{color:#0550ae}
.reader .codehilite .o,.reader .codehilite .ow{color:#0550ae}
.reader .codehilite .nv,.reader .codehilite .vc,.reader .codehilite .vg,.reader .codehilite .vi,.reader .codehilite .nl{color:#953800}
.reader .codehilite .err{color:#cf222e}
@media(prefers-color-scheme:dark){
.reader .codehilite .k,.reader .codehilite .kd,.reader .codehilite .kn,.reader .codehilite .kt{color:#c792ea}
.reader .codehilite .s,.reader .codehilite .s1,.reader .codehilite .s2,.reader .codehilite .sb,.reader .codehilite .sc,.reader .codehilite .dl{color:#c3e88d}
.reader .codehilite .c,.reader .codehilite .c1,.reader .codehilite .cm,.reader .codehilite .cs{color:#8b98b2;font-style:italic}
.reader .codehilite .n,.reader .codehilite .p,.reader .codehilite .w{color:#e9edf7}
.reader .codehilite .na{color:#82aaff}
.reader .codehilite .nf,.reader .codehilite .nn,.reader .codehilite .nc,.reader .codehilite .nb,.reader .codehilite .bp{color:#82aaff}
.reader .codehilite .mi,.reader .codehilite .mf,.reader .codehilite .il,.reader .codehilite .m{color:#f78c6c}
.reader .codehilite .o,.reader .codehilite .ow{color:#89ddff}
.reader .codehilite .nv,.reader .codehilite .vc,.reader .codehilite .vg,.reader .codehilite .vi,.reader .codehilite .nl{color:#ffcb6b}
.reader .codehilite .err{color:#ff7b72}
}

/* Java 专属配色：关键字红、类名紫加粗、注解青、方法蓝、字符串琥珀 */
.reader .codehilite[data-lang="java"] .n,.reader .codehilite[data-lang="java"] .p{color:#3b4252}
.reader .codehilite[data-lang="java"] .k,.reader .codehilite[data-lang="java"] .kd,.reader .codehilite[data-lang="java"] .kc,.reader .codehilite[data-lang="java"] .kt{color:#c0392b}
.reader .codehilite[data-lang="java"] .nc,.reader .codehilite[data-lang="java"] .nn{color:#6c3483;font-weight:600}
.reader .codehilite[data-lang="java"] .nd,.reader .codehilite[data-lang="java"] .na{color:#0e7490}
.reader .codehilite[data-lang="java"] .nf{color:#1d4ed8}
.reader .codehilite[data-lang="java"] .s,.reader .codehilite[data-lang="java"] .s1,.reader .codehilite[data-lang="java"] .s2,.reader .codehilite[data-lang="java"] .sb,.reader .codehilite[data-lang="java"] .sc,.reader .codehilite[data-lang="java"] .dl{color:#a16207}
.reader .codehilite[data-lang="java"] .mi,.reader .codehilite[data-lang="java"] .mf,.reader .codehilite[data-lang="java"] .il,.reader .codehilite[data-lang="java"] .m{color:#b45309}
.reader .codehilite[data-lang="java"] .c,.reader .codehilite[data-lang="java"] .c1,.reader .codehilite[data-lang="java"] .cm,.reader .codehilite[data-lang="java"] .cs{color:#64748b;font-style:italic}
.reader .codehilite[data-lang="java"] .o,.reader .codehilite[data-lang="java"] .ow{color:#475569}
.reader .codehilite[data-lang="java"] .err{color:#dc2626}
@media(prefers-color-scheme:dark){
.reader .codehilite[data-lang="java"] .n,.reader .codehilite[data-lang="java"] .p{color:#d8dee9}
.reader .codehilite[data-lang="java"] .k,.reader .codehilite[data-lang="java"] .kd,.reader .codehilite[data-lang="java"] .kc,.reader .codehilite[data-lang="java"] .kt{color:#ff7b72}
.reader .codehilite[data-lang="java"] .nc,.reader .codehilite[data-lang="java"] .nn{color:#d2a8ff;font-weight:600}
.reader .codehilite[data-lang="java"] .nd,.reader .codehilite[data-lang="java"] .na{color:#79c0ff}
.reader .codehilite[data-lang="java"] .nf{color:#82aaff}
.reader .codehilite[data-lang="java"] .s,.reader .codehilite[data-lang="java"] .s1,.reader .codehilite[data-lang="java"] .s2,.reader .codehilite[data-lang="java"] .sb,.reader .codehilite[data-lang="java"] .sc,.reader .codehilite[data-lang="java"] .dl{color:#d29922}
.reader .codehilite[data-lang="java"] .mi,.reader .codehilite[data-lang="java"] .mf,.reader .codehilite[data-lang="java"] .il,.reader .codehilite[data-lang="java"] .m{color:#ffa657}
.reader .codehilite[data-lang="java"] .c,.reader .codehilite[data-lang="java"] .c1,.reader .codehilite[data-lang="java"] .cm,.reader .codehilite[data-lang="java"] .cs{color:#8b949e;font-style:italic}
.reader .codehilite[data-lang="java"] .o,.reader .codehilite[data-lang="java"] .ow{color:#b9c2d0}
.reader .codehilite[data-lang="java"] .err{color:#ff7b72}
}

/* ===== 移动端改进补丁（MOBILE-UX-REPORT Task 1-5） ===== */
/* 兜底：任何漏网内容不再撑破整页（clip 不产生滚动条、不裁切粘贴选区） */
body{overflow-x:clip}
/* 行内代码 / 链接 / 标题可断行 */
a{overflow-wrap:anywhere}
.reader code{overflow-wrap:anywhere;word-break:break-word}
.reader h1,.reader h2,.reader h3,.reader h4{overflow-wrap:break-word}
.reader blockquote p{overflow-wrap:anywhere}
/* pre 块内的 code 不受影响（保持代码原样，由 pre 自身横向滚动控制） */
.reader pre code{overflow-wrap:normal;word-break:normal}

/* 移动端阅读适配：内容区放宽、字号收缩、代码块软换行、表格紧凑 */
@media(max-width:640px){
  html{-webkit-text-size-adjust:100%}
  .shell{width:min(100% - 14px,1120px)}
  .reader{padding:22px 14px 34px}
  .reader h1{font-size:27px}
  .reader h2{font-size:21px;margin:40px 0 14px}
  .reader h3{font-size:18px}
  .reader pre{font-size:12.5px;padding:16px 14px}
  .reader pre:not(.mermaid){white-space:pre-wrap;word-break:break-all;overflow-x:hidden}
  .reader th,.reader td{padding:8px 9px}
  .reader table{font-size:13px;margin:18px auto}
  .chapter-status{font-size:12px;padding:8px 10px;gap:8px 10px}
  .chapter-status .complete-button{min-height:40px;padding:6px 14px}
  .chapter-nav a{padding:9px 14px}
  .math-display-wrap{padding:10px;font-size:.95em}
  .demo-embed iframe{height:420px;min-height:320px}
}
/* 触屏设备给可横滚容器加提示（桌面 hover 设备不显示） */
@media(hover:none){
  .mermaid-diagram::after{content:"↔ 左右滑动查看大图";display:block;padding:6px 10px;color:var(--muted);font-size:12px}
}
"""


# 章节页 Mermaid 图表的浏览器端渲染驱动，构建时写入 library/assets/library-mermaid.js。
# 原理：构建端不渲染 Mermaid，只把源码以 <pre class="mermaid"> 形式留在 HTML；
# 页面加载后本脚本调用全局 mermaid 逐图渲染(startOnLoad:false + 手动 run，
# 避免并发生成临时 ID 冲突)，单图语法失败只标记 .is-error，不阻断同页其余图。
MERMAID_JS = r"""
(async () => {
  const diagrams = [...document.querySelectorAll('.mermaid-diagram .mermaid')];
  if (!diagrams.length) return;
  const markFailed = (node) => {
    const figure = node.closest('.mermaid-diagram');
    if (figure) figure.classList.add('is-error');
  };
  if (!window.mermaid) {
    diagrams.forEach(markFailed);
    return;
  }
  const palette = {
    background: '#fbfcff', primaryColor: '#f1f2ff', primaryTextColor: '#344056',
    primaryBorderColor: '#7775dc', secondaryColor: '#edf9f8', tertiaryColor: '#f7f9fd',
    lineColor: '#8490a3', textColor: '#344056', mainBkg: '#f1f2ff', nodeBorder: '#7775dc',
    clusterBkg: '#f7f9fd', clusterBorder: '#d4dbe7', edgeLabelBackground: '#fbfcff',
    actorBkg: '#f1f2ff', actorBorder: '#7775dc', actorTextColor: '#344056',
    actorLineColor: '#b5becc', signalColor: '#758196', signalTextColor: '#344056',
    labelBoxBkgColor: '#edf9f8', labelBoxBorderColor: '#79b8ba', labelTextColor: '#344056',
    activationBkgColor: '#fff7e8', activationBorderColor: '#dfa34c', sequenceNumberColor: '#ffffff'
  };
  const narrow = window.innerWidth < 640;
  window.mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    theme: 'base',
    themeVariables: { ...palette, fontSize: '15px' },
    fontFamily: 'system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif',
    flowchart: { htmlLabels: true, useMaxWidth: true, curve: 'basis', nodeSpacing: narrow ? 18 : 34, rankSpacing: narrow ? 26 : 44, padding: narrow ? 10 : 14 },
    sequence: { useMaxWidth: true, wrap: true, actorMargin: narrow ? 34 : 46, messageMargin: narrow ? 24 : 32, diagramMarginX: narrow ? 12 : 24, diagramMarginY: narrow ? 12 : 18 },
    mindmap: { useMaxWidth: true }
  });
  // 逐图、按顺序渲染：某一张图语法异常时不会阻断同页其他图，
  // 同时避免并发生成 Mermaid 临时 ID 时发生冲突。
  for (const node of diagrams) {
    const figure = node.closest('.mermaid-diagram');
    figure?.classList.remove('is-error', 'is-rendered');
    try {
      await window.mermaid.run({ nodes: [node], suppressErrors: false });
      if (!node.querySelector('svg')) throw new Error('Mermaid did not create SVG');
      figure?.classList.add('is-rendered');
    } catch (_) {
      markFailed(node);
    }
  }
})();
"""


# ---------------------------------------------------------------------------
# 章节拆分：把整份课程 Markdown 源按 “##” 二级标题切成若干章节(数据流第 2 步)。
# 返回值 (title, chapters)：
#   - title：源里第一个 “# ” 一级标题(书名)；
#   - chapters：[{title, body}, …]，所有 chapter 正文拼接 ≈ 去掉书名后的全文，
#     顺序与源文件一致，后续按此顺序编章节号 chapter-NN.html。
# ---------------------------------------------------------------------------
def split_chapters(text: str, fallback_title: str) -> tuple[str, list[dict[str, str]]]:
    text = repair_indented_headings(text.replace("\u200b", ""))
    # 拆章前先做两步预处理：
    #   1) repair_indented_headings 把误缩进的标题/代码围栏恢复为块级结构
    #      (与 build_hot100 共用，保证两边对“缩进标题”的判定一致)；
    #   2) 删除零宽空格 \u200b(AI 整理稿常见的隐形字符，会打断正则与标题匹配)。
    lines = text.splitlines()
    title = fallback_title
    for line in lines:
        if re.match(r"^#\s+\S", line):
            title = re.sub(r"^#\s+", "", line).replace(r"\.", ".").strip()
            break
    # 一级标题 “# xxx” 视为书名，存在多个一级标题时取第一个；
    # .replace(r"\.", ".") 还原源里被转义的反斜杠点号(如 “1\. 简介”)。
    starts: list[int] = []
    # 扫描全部 “## ” 标题行，记下它们在整份文本里的行号作为章节起点。
    # in_fence/fence 状态机跟踪 ``` 与 ~~~ 围栏：围栏内部的 “##” 属于代码示例
    # 内容，不是章节标题，必须跳过(与 check_hot100 的围栏配对判定同思路)。
    in_fence = False
    fence = ""
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence = True, marker
            elif marker == fence:
                in_fence, fence = False, ""
            continue
        # (?!目录\s*$) 负向先行断言：把 “## 目录” 这类目录章节排除在章节列表外，
        # 目录信息由模块首页统一生成，不占章节号。
        if not in_fence and re.match(r"^##\s+(?!目录\s*$)\S", line):
            starts.append(index)
    chapters: list[dict[str, str]] = []
    if starts:
        # 章节区间 [starts[i], starts[i+1])：到下一个标题行之间的所有行都是本章正文；
        # 最后一章的右边界是文件末尾。enumerate(..., 1) 使章节号从 1 开始。
        for number, start in enumerate(starts, 1):
            end = starts[number] if number < len(starts) else len(lines)
            heading = re.sub(r"^##\s+", "", lines[start]).strip()
            # 课程目录已经单独显示统一的两位章节序号，因此去掉源标题自带的
            # “0.”、“1.”、“6.2”一类编号，避免出现“01  0. …”的重复视觉。
            display_heading = re.sub(r"^\d+(?:\.\d+)*[.、：:)]?\s*", "", heading).strip()
            # 目录展示处的两位序号是统一编排的，源标题自带的编号(“0.”、“1.”、
            # “6.2”)在此剥掉，避免卡片/面包屑出现 “01  0. …” 这类重复编号；
            # 若剥完后标题为空(标题本身就是编号)，回退用原标题。
            heading = display_heading or heading
            body = "\n".join(lines[start + 1:end]).strip()
            chapters.append({"title": heading, "body": body})
    else:
        # 源里没有任何 “## ” 章节头的兜底分支：整篇作为唯一一章，
        # 章节标题用书名 title 兜底，保证模块页至少有一张可点的卡片。
        body = "\n".join(line for line in lines if not re.match(r"^#\s+", line)).strip()
        chapters.append({"title": title, "body": body})
    return title, chapters


# ---------------------------------------------------------------------------
# 阅读副本净化(“normalize 系列”之一，数据流第 3 步)：
#   只修“章节页将看到的 Markdown 结构标记”，绝不动原始笔记文件——源文件是唯一
#   事实来源，净化损失可在下次构建时自动恢复。
# 与 build_hot100 的关系：repair_indented_headings / normalize_original_body 同属
# “源 → 展示”净化族，Hot 100 那边净化题解正文，书架这边净化章节正文；两边都遵循
# “源文件只读、产物可再生”的原则。
# ---------------------------------------------------------------------------
def normalize_chapter_markdown(text: str) -> str:
    """只修复阅读副本中的结构标记，不改动原始笔记。"""
    text = re.sub(r"(?im)^(\s*`{3,})\s*plain\s+text\s*$", r"\1text", text)
    # plain text 是 Python-Markdown 不认识的围栏语言名，统一改成 text，
    # 保证代码高亮路径一致(未知语言最终落回 TextLexer)。
    lines = text.splitlines()
    output: list[str] = []
    in_fence = False
    fence = ""
    in_math = False
    math_parts: list[str] = []
    # 数学块收集器：$$ 到 $$ 之间的所有行先攒进 math_parts，遇到结束符再合并成
    # 单行输出——数学公式要求“单行 $$…$$”，跨行内容会被 markdown 渲染时拆散。
    for line in lines:
        stripped = line.lstrip()
        if not in_math and stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence = True, marker
            elif marker == fence:
                in_fence, fence = False, ""
            output.append(line)
            continue
        if in_fence:
            output.append(line)
            continue
        if in_math:
            if "$$" in line:
                before, after = line.split("$$", 1)
                math_parts.append(before)
                output.append("$$" + " ".join(part.strip() for part in math_parts if part.strip()) + "$$" + after)
                math_parts = []
                in_math = False
            else:
                math_parts.append(line)
            continue
        # 只处理独占一行的块级 $$ 起始符(行内 $$x$$ 不在收集之列)，
        # 从该行第二个 $ 之后开始收集，直到出现另一个带 $$ 的行闭合。
        if stripped.startswith("$$") and stripped.count("$$") == 1:
            math_parts = [stripped[2:]]
            in_math = True
            continue
        # 一级标题降为二级：# 章节页的 H1 已被章节标题占用，正文里再出现 “# ”
        # 会打乱标题层级，故统一 # → ##，保持 H1→H2→H3 的语义顺序。
        if re.match(r"^#\s+\S", line):
            line = "## " + line[2:]
        # 行内代码中的 ``**kwargs`` / ``**data`` 不是 Markdown 强调符。
        # 只检查反引号代码区间之外的文本，避免在行尾错误补上 ``**``。
        # 按反引号把行切成“代码片段/普通文本”交替段，只统计普通文本里的 **，
        # 避免把 ``**kwargs`` 这类行内代码误判成未闭合的加粗符号。
        visible_parts = re.split(r"(`+[^`]*`+)", line)
        markdown_text = "".join(visible_parts[::2])
        # 偶数个 ** 意味着漏了闭合(源笔记/AI 整理稿常见)，行尾补一个 ** 兜底，
        # 否则 markdown 渲染时未闭合的加粗会从行尾吞掉后半行内容。
        if markdown_text.count("**") % 2 == 1:
            line = line.rstrip() + "**"
        output.append(line)
    if in_math:
        # 文件遍历完仍未遇到闭合 $$ 时，把攒下的内容原样追回，保证不丢正文。
        output.extend(["$$", *math_parts])
    return "\n".join(output)


# ---------------------------------------------------------------------------
# 本地链接改写(数据流关键环节之一，见 build() 调用处)：
#   - 指向其他课程 .md 的链接 → 改写为 ../<模块id>/index.html(跨模块互链)；
#   - 指向本地图片/附件/文件的链接 → 把文件复制进本模块 assets/，文件名加
#     sha1 前缀做内容寻址(天然去重 + 缓存失效)，链接改写为相对地址；
#   - http(s): / data: 外链与目标不存在的文件原样保留，不做任何处理。
# 参数：source 是当前源笔记的路径(决定相对链接的基准目录)；assets_dir 是当前
#       模块的资产目录；source_modules 是“源文件绝对路径 → 模块 id”映射，
#       由 build() 从登记表构建，供 .md 互链改写使用。
# ---------------------------------------------------------------------------
def rewrite_local_links(text: str, source: Path, assets_dir: Path, source_modules: dict[Path, str]) -> str:
    # Markdown 图片/链接语法统一形状：![alt](url) 或 [text](url)，
    # 只摘取 () 里的目标；尖括号包裹的 URL(<url>)一并剥掉。
    pattern = re.compile(r"(!?\[[^\]]*\]\()([^)]+)(\))")

    def replace(match: re.Match[str]) -> str:
        raw = match.group(2).strip().strip("<>")
        if re.match(r"^(?:https?:|data:)", raw, re.I):
            return match.group(0)
        # 先把 URL 做百分号解码(unquote：中文/空格文件名在源里常被编码)，
        # 再基于源文件所在目录解析出绝对路径，避免跨目录相对路径计算错误。
        target = (source.parent / unquote(raw)).resolve()
        # 兜底：单行本/ 等收纳层会让"以书籍根(books/)为基准书写的跨书相对链接"解析失败，
        # 此时改按 books 根再解一次（./ 或 ../ 点前缀剥掉一层后再拼）。
        if not source.parent.name == "books" and not target.is_file():
            books_root = next((p for p in source.parents if p.name == "books"), source.parent)
            rel_candidate = unquote(raw).lstrip("./").lstrip("../")
            # 候选①：books/<相对路径>（书的平铺时代写法）；候选②：books/单行本/<名>（单行本收纳层）。
            for base in (books_root, books_root / "单行本"):
                alt = (base / rel_candidate).resolve()
                if alt.is_file():
                    target = alt
                    break
        # 目标是另一门课程的 .md：链接指向目标模块的 index.html，
        # 让书架内章节之间可以互相跳转，而不是暴露源文件的相对路径。
        if target.suffix.lower() == ".md" and target in source_modules:
            return f"{match.group(1)}../{source_modules[target]}/index.html{match.group(3)}"
        if not target.is_file():
            return match.group(0)
        # 普通资源(图片/附件)：sha1(绝对路径)[:10] 做内容寻址前缀，同名不同内容
        # 的文件互不覆盖；非法字符替换后再拷入 assets，链接改写为 assets/<name>。
        digest = hashlib.sha1(str(target).encode("utf-8")).hexdigest()[:10]
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", target.name).strip("-") or f"asset{target.suffix}"
        destination = assets_dir / f"{digest}-{safe_name}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, destination)
        return f"{match.group(1)}assets/{destination.name}{match.group(3)}"

    return pattern.sub(replace, text)


# ---------------------------------------------------------------------------
# Mermaid 源码 → 统一图表 HTML。
# 职责：把源笔记里的 mermaid 围栏内容包成 <figure class="mermaid-diagram">。
# 为什么先转义：Mermaid 源码里可能含 HTML 特殊字符，直接内联会被浏览器当成
# 标签解析——先 html.escape 再放进 <pre>，渲染由浏览器端 MERMAID_JS 接管。
# data-diagram-type 取源码首词(flowchart/sequenceDiagram/mindmap/graph…)，
# 供 CSS 按图表类型定制配色；渲染失败时用户看到 figcaption 里的提示文案。
# ---------------------------------------------------------------------------
def mermaid_figure(source: str) -> str:
    """把 Mermaid 源码转成统一的图表 HTML，源码先转义防止注入。"""
    source = source.replace("\xa0", " ").strip()
    safe_source = html.escape(source, quote=False)
    diagram_type = source.split(None, 1)[0] if source else "diagram"
    label = {
        "flowchart": "流程图",
        "graph": "流程图",
        "sequenceDiagram": "时序图",
        "mindmap": "思维导图",
    }.get(diagram_type, "图表")
    return (
        f'<figure class="mermaid-diagram" data-diagram-type="{html.escape(diagram_type)}">'
        f'<pre class="mermaid" aria-label="{label}">{safe_source}</pre>'
        '<figcaption class="mermaid-error">图表未能渲染，请重新打开本页。</figcaption>'
        "</figure>"
    )


# 全局代码围栏匹配正则(跨函数复用)：捕获围栏语言(info 组)与围栏源码
# (source 组)，兼容 ``` 与 ~~~、允许围栏行带缩进；详见 render_markdown 的
# “围栏 → 占位符 → 还原”机制。
FENCE_BLOCK = re.compile(
    r"(?ms)^[ \t]*```([^\n`]*)\r?\n(?P<source>.*?)^[ \t]*```[ \t]*\r?\n?"
)


# ---------------------------------------------------------------------------
# 代码着色(“加色”环节)：用 Pygments 按语言选 lexer 高亮。
# 语言名写进 data-lang 属性，CSS 据此做专属配色(见 LIBRARY_CSS 里
# data-lang="java" 的整套 Java 配色规则)；未知语言/空语言用 TextLexer 兜底，
# 失败不抛异常，保证单个代码块异常不影响整页生成。
# ---------------------------------------------------------------------------
def highlight_code(lang: str, source: str) -> str:
    """用 Pygments 给代码上色，并带上语言标记，便于按语言定制配色。"""
    try:
        lexer = get_lexer_by_name(lang) if lang else TextLexer()
    except ClassNotFound:
        lexer = TextLexer()
    body = pygments_highlight(source, lexer, HtmlFormatter(nowrap=True))
    if lang:
        return (
            f'<div class="codehilite" data-lang="{html.escape(lang, quote=True)}">'
            f'<pre><code class="language-{html.escape(lang)}">{body}</code></pre></div>'
        )
    return f'<div class="codehilite"><pre><code>{body}</code></pre></div>'


# ---------------------------------------------------------------------------
# Markdown → HTML 主渲染管线(数据流第 4 步)：
#   数学预处理 → 围栏换占位符 → markdown.markdown() → 还原占位符。
# 占位符机制的原因：Python-Markdown 的 fenced_code 扩展会把代码块渲染成没有
# 语言标记的 <pre><code>，而我们需要 Pygments 上色(→@@CODE n@@)与 Mermaid
# 图表(→@@MMD n@@)的自定义 HTML；先把围栏整体替换成带编号的占位符文本，
# 渲染完成后再按编号还原，语言标记就不会在转换中丢失。
# ---------------------------------------------------------------------------
def render_markdown(text: str) -> str:
    prepared = render_math_in_markdown(text)
    # 渲染前把所有 ``` 围栏换成占位符：Mermaid 走图表，其余代码走 Pygments，
    # 这样既能给代码块标上语言（data-lang），又不会丢失 Mermaid 的语言标记。
    # 数学预处理先行：build_html_site.render_math_in_markdown 自带围栏/行内代码
    # 跳过逻辑，之后再统一处理 ``` 围栏，两个处理器的边界不会互相干扰。
    figures: list[str] = []
    code_blocks: list[tuple[str, str]] = []

    # protect_fence 是 FENCE_BLOCK.sub 的回调：mermaid 围栏进 figures 表，
    # 其余代码进 code_blocks 表，正文里只留一个 @@MMD n@@ / @@CODE n@@ 占位。
    def protect_fence(match: re.Match[str]) -> str:
        info = match.group(1).strip()
        lang = info.split(None, 1)[0] if info else ""
        source = match.group("source")
        if lang == "mermaid":
            figures.append(mermaid_figure(source))
            return f"\n\n@@MMD{len(figures) - 1}@@\n\n"
        code_blocks.append((lang, source))
        return f"\n\n@@CODE{len(code_blocks) - 1}@@\n\n"

    prepared = FENCE_BLOCK.sub(protect_fence, prepared)
    # 标准扩展组合；代码围栏此时已被占位符顶替，fenced_code 只兜底处理
    # 极少数没被正则捕获的裸围栏。
    rendered = markdown.markdown(
        prepared,
        extensions=["extra", "sane_lists", "fenced_code", "tables"],
    )
    # 还原阶段：markdown 会把占位符包进 <p>@@CODE0@@</p>，正则连同 <p> 一起换回
    # 渲染好的 <div class="codehilite"> / <figure>；编号越界说明索引错位、
    # 残留占位符说明 HTML 被解析吞掉——两种情况都直接抛错，宁可构建失败
    # 也不产出损坏页面。
    def restore_placeholders(rendered: str, kind: str, items: list[str]) -> str:
        pattern = re.compile(rf"<p>@@{kind}(\d+)@@</p>")
        restored = pattern.sub(lambda m: items[int(m.group(1))] if int(m.group(1)) < len(items) else m.group(0), rendered)
        leftovers = re.findall(rf"@@{kind}\d+@@", restored)
        if leftovers:
            raise RuntimeError(f"章节占位符未替换干净：{leftovers[:3]}")
        return restored

    rendered = restore_placeholders(
        rendered, "CODE", [highlight_code(lang, source) for lang, source in code_blocks]
    )
    rendered = restore_placeholders(rendered, "MMD", figures)
    return rendered


def _render_chapter_body_worker(job: tuple[str, str]) -> tuple[str, str]:
    """子进程执行：渲染单个章节正文 Markdown → HTML，返回 (chapter_id, html)。"""
    chapter_id, prepared = job
    return chapter_id, render_markdown(prepared)


# 公共顶栏(书架首页/搜索页/模块页/章节页共用)：prefix 是相对路径深度——
# 首页传 "."、二级页面传 ".."，据此拼出到书架首页/搜索页/Hot 100 站/维护指南的链接。
def topbar(prefix: str = "..") -> str:
    return f'<header class="topbar"><a class="brand" href="{prefix}/index.html">学习书架</a><nav aria-label="主导航"><a href="{prefix}/search.html">全文搜索</a><a href="{prefix}/../index.html">Hot 100</a><a href="{prefix}/../maintenance.html">维护指南</a></nav></header>'


# 页面 HTML 外壳：统一 lang/字符集/响应式 viewport/明暗色声明，标题做 HTML 转义，
# CSS 链接带 ?v=ASSET_VERSION 查询串(与常量注释里的缓存破坏约定一致)；
# scripts 参数追加页面尾部 JS(如章节页的 Mermaid 运行库与渲染驱动)。
def document(title: str, body: str, css_href: str, scripts: str = "") -> str:
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><title>{html.escape(title)} · 学习书架</title><link rel="stylesheet" href="{css_href}?v={ASSET_VERSION}"></head><body>{body}{scripts}</body></html>'''


# 摘要文本清洗(章节摘要/模块简介共用)：剥掉 markdown 图片语法、链接只留显示
# 文字、去掉 ` * _ > # 等强调/引用/标题符号，连续空白压成单空格——
# 保证摘要/简介是一句可读的纯文本，不会把语法符号漏进卡片。
def clean_summary_line(line: str) -> str:
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
    cleaned = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cleaned)
    cleaned = re.sub(r"[`*_>#]", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


# 摘要收尾：先去掉句尾的“连接性标点”(冒号/逗号等，避免整段以半截句结束)；
# 长度超限时在 limit 附近截断并补 “…”；若末尾不是句号类标点则补 “。”，
# 让卡片摘要读起来是完整的一句。
def finish_summary(text: str, limit: int) -> str:
    text = text.rstrip("，。、；：:,; ")
    if len(text) > limit:
        text = text[:limit].rstrip("，。、；：:,; ") + "…"
    if text and text[-1] not in "。！？!?…":
        text += "。"
    return text


# ---------------------------------------------------------------------------
# 章节摘要(模块页卡片的 intro 文案，默认 ≤56 字)。
# 提取规则与“坑”：
#   - 跳过标题行、代码围栏、表格行、分隔线；列表项只在“开头”被跳过
#     (先决条件清单常以列表开头，不适合当摘要)；
#   - 正文通常先是一两句导语再空行，故遇到第一个空行即截断；
#   - 首句太长时整句丢弃、继续看下一句(parts 为空时)，避免摘要从半句开始；
#   - 累计长度达标即停，整段拼接后统一去句尾冒号/逗号(见 finish_summary)。
# 与 clean_search_text 的差异：这里是“一句话”，那里是“全文”，
# 服务于不同 UI(卡片简介 vs 搜索命中文本)。
# ---------------------------------------------------------------------------
def chapter_summary(body: str, limit: int = 56) -> str:
    """从章节正文提取一句简短摘要；跳过分隔线、代码、表格与残缺半句。"""
    parts: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            if parts:
                break
            continue
        if stripped.startswith(("```", "~~~", "|", "#")):
            continue
        if re.fullmatch(r"[-*_]{3,}", stripped):
            continue
        if not parts and re.match(r"^[-*] |^\d+[.、]", stripped):
            continue
        cleaned = clean_summary_line(stripped)
        if not cleaned or len(cleaned) <= 1:
            continue
        parts.append(cleaned)
        if sum(len(part) for part in parts) >= limit:
            break
    # 拼接后统一去掉句尾冒号/逗号等连接性标点，避免整段被弹空。
    text = " ".join(parts).rstrip("，。、；：:,; ")
    return finish_summary(text, limit)


# ---------------------------------------------------------------------------
# 模块简介(模块首页的 about 文案)：从源笔记“开头的一段话”里自动提取，
# 规则比章节摘要宽松——直到第一个 “##” 之前的所有普通段落都算数。
# 数据流：登记表里人工维护的 about 优先级更高(见 build() 模块 dict 组装处)，
# 本函数只在未登记时兜底；这是“人工文案优先、自动提取兜底”的双轨设计。
# 坑：结尾为 “： , ;” 等连接性标点的行整行弹掉，防止简介以“核心内容：”
# 这类半截句收尾；一级标题行(“# xxx”)跳过，避免把书名重复进简介。
# ---------------------------------------------------------------------------
def module_about(text: str, fallback: str, limit: int = 88) -> str:
    """提取源笔记开头的一句话作为模块简介，失败时使用兜底文案。"""
    parts: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^#{2,}\s", stripped):
            break
        if stripped.startswith("#"):
            continue
        if not stripped:
            if parts:
                break
            continue
        if stripped.startswith(("```", "~~~", "|")):
            continue
        cleaned = clean_summary_line(stripped)
        if cleaned:
            parts.append(cleaned)
        if sum(len(part) for part in parts) >= limit:
            break
    while parts and parts[-1][-1] in "：:,，;；":
        parts.pop()
    text_summary = " ".join(parts)
    if not text_summary:
        return fallback
    return finish_summary(text_summary, limit)


# ---------------------------------------------------------------------------
# 模块首页前端脚本(module_index_page 把它注入模块页 <script>，并替换占位符)。
# 数据流与职责：
#   - 启动时并发 GET /api/library + /api/daily(module=…)，取模块/章节进度、
#     轮次、到期复习日程；接口不可达则降级为静态浏览模式(只读、按钮禁用、
#     提示经“启动学习站.cmd”进入)；
#   - renderCards：按 搜索词 / 专题下拉 / 轮次状态(新/一轮/多轮/待复习)过滤；
#   - 点“完成一轮”→ POST /api/content/complete；Hot 100 题解章节走
#     /api/complete 并带 problem_id(学习记录与 Hot 100 站共享)；
#   - renderDue：渲染“本模块待复习”清单，逾期标橙、含下次复习日期；
#   - state.data 结构 {modules:{…}, contents:{…}} 与 /api/library 的返回
#     结构一一对应，是前端与 study_server 之间的数据契约。
# 注入点：__MODULE_ID__ / __CHAPTERS_JSON__ / __TOPICS_JSON__。
# ---------------------------------------------------------------------------
MODULE_PAGE_JS = r"""<script>
const moduleId="__MODULE_ID__";
const chapters=__CHAPTERS_JSON__;
const topics=__TOPICS_JSON__;
const hasTopics=topics.length>0;
const grid=document.getElementById('chapterGrid');
const empty=document.getElementById('empty');
const search=document.getElementById('search');
const topic=document.getElementById('topic');
const status=document.getElementById('status');
const toast=document.getElementById('toast');
const topicWrap=document.getElementById('topicWrap');
const connection=document.getElementById('connection');
const serverNotice=document.getElementById('serverNotice');
const moduleDue=document.getElementById('moduleDue');
const moduleDueList=document.getElementById('moduleDueList');
const state={online:false,data:{modules:{},contents:{}},due:{today:'',items:{}}};
if(!hasTopics){topicWrap.hidden=true;topicWrap.style.display='none'}
topics.forEach(name=>{const option=document.createElement('option');option.value=name;option.textContent=name;topic.appendChild(option)});
function esc(value){return String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))}
function localTime(value){if(!value)return '尚无记录';const date=new Date(value);return `${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')} ${String(date.getHours()).padStart(2,'0')}:${String(date.getMinutes()).padStart(2,'0')}`}
function moduleInfo(){return state.data.modules[moduleId]||{completed:0,total:chapters.length}}
function contentInfo(id){return state.data.contents[id]||{rounds:0,last_activity_at:null}}
function dueInfo(id){return state.due.items[id]||null}
function renderDue(){
  if(!moduleDue)return;
  const due=state.due.items;
  const items=chapters.filter(c=>due[c.id]).map(c=>({...c,due:due[c.id],overdue:due[c.id]<state.due.today}));
  const overdueCount=items.filter(item=>item.overdue).length;
  const head=moduleDue.querySelector('.due-summary');
  if(head)head.textContent=items.length?`本模块 ${items.length} 章到期${overdueCount?`（逾期 ${overdueCount}）`:''}，完成一轮后自动推进下次复习。`:'';
  moduleDueList.innerHTML=items.length?items.map(item=>`<div class="due-item ${item.overdue?'due-overdue':''}"><a href="${esc(item.href)}" title="${esc(item.title)}">${esc(item.title)}</a><span class="due-date">${item.overdue?`逾期 ${esc(item.due)}`:`今日 ${esc(item.due)}`}</span></div>`).join(''):'<div class="due-empty">本模块暂无到期章节，完成一轮后会自动出现在这里。</div>';
}
function updateStats(){
  const info=moduleInfo();
  const rounds=chapters.reduce((sum,c)=>sum+Number(contentInfo(c.id).rounds||0),0);
  document.getElementById('completedCount').textContent=info.completed;
  document.getElementById('totalRounds').textContent=rounds;
  const percent=Math.round(info.completed/info.total*100);
  document.getElementById('progress').style.width=`${percent}%`;
  document.getElementById('progressText').textContent=`${info.completed} / ${info.total}`;
  document.getElementById('progressBar').setAttribute('aria-valuenow',String(info.completed));
}
function renderCards(){
  const query=search.value.trim().toLowerCase();
  const list=chapters.filter(c=>{
    const rounds=Number(contentInfo(c.id).rounds||0);
    const due=dueInfo(c.id);
    const isDue=Boolean(due);
    const text=`${c.title} ${c.intro||''} ${c.method||''} ${c.category||''}`.toLowerCase();
    const matchesText=!query||text.includes(query);
    const matchesTopic=!hasTopics||!topic.value||c.category===topic.value;
    const matchesStatus=!status.value||(status.value==='new'&&rounds===0)||(status.value==='once'&&rounds===1)||(status.value==='repeat'&&rounds>=2)||(status.value==='due'&&isDue);
    return matchesText&&matchesTopic&&matchesStatus;
  });
  grid.innerHTML=list.map(c=>{
    const info=contentInfo(c.id);const rounds=Number(info.rounds||0);
    const due=dueInfo(c.id);const overdue=due&&due<state.due.today;
    const meta=[];
    if(c.category)meta.push(`<span class="pill">${esc(c.category)}</span>`);
    if(c.difficulty)meta.push(`<span class="difficulty-${c.difficulty}">${esc(c.difficulty)}</span>`);
    const dueBadge=due?`<span class="due-pill ${overdue?'overdue':''}">${overdue?'逾期':'待复习'}</span>`:'';
    return `<article class="chapter-card ${rounds?'studied':''}"><div class="card-head"><h2><a href="${esc(c.href)}">${esc(c.title)}</a></h2><span class="round-count">${rounds} 轮</span>${dueBadge}</div>${meta.length?`<div class="meta">${meta.join('')}</div>`:''}<div class="card-actions"><span class="last-study">最近：${localTime(info.last_activity_at)}</span><button class="round-button" type="button" data-chapter="${esc(c.id)}">完成一轮</button></div></article>`;
  }).join('');
  empty.hidden=list.length!==0;
  grid.querySelectorAll('[data-chapter]').forEach(button=>button.addEventListener('click',()=>completeChapter(button)));
}
async function completeChapter(button){
  const chapter=chapters.find(item=>item.id===button.dataset.chapter);
  if(!chapter){button.disabled=false;return}
  button.disabled=true;button.textContent='记录中…';toast.textContent='';
  try{
    const isProblem=Boolean(chapter.problem_id);
    const payload=isProblem?{problem_id:Number(chapter.problem_id)}:{module_id:moduleId,content_id:chapter.id};
    const response=await fetch(isProblem?'/api/complete':'/api/content/complete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const result=await response.json();
    if(!response.ok)throw new Error(result.error||'记录失败');
    toast.textContent=`已记录「${chapter.title}」的第 ${result.round_no} 轮`;
    await refresh();
  }catch(error){toast.textContent=`记录失败：${error.message}`;button.disabled=false;button.textContent='完成一轮'}
}
async function refresh(){
  try{
    const [libraryResponse,dailyResponse]=await Promise.all([
      fetch('/api/library',{cache:'no-store'}),
      fetch(`/api/daily?module=${encodeURIComponent(moduleId)}`,{cache:'no-store'})
    ]);
    if(!libraryResponse.ok||!dailyResponse.ok)throw new Error('database unavailable');
    state.data=await libraryResponse.json();
    const daily=await dailyResponse.json();
    state.due.today=daily.today;
    state.due.items={};
    daily.contents.forEach(item=>{state.due.items[item.content_id]=item.due_date});
    state.online=true;
    connection.classList.add('online');connection.textContent='SQLite 数据库已连接';serverNotice.hidden=true;
  }catch(error){
    state.online=false;
    state.due.today='';state.due.items={};
    connection.classList.remove('online');connection.textContent='当前是静态浏览模式';serverNotice.hidden=false;
  }
  updateStats();renderDue();renderCards();
}
search.addEventListener('input',renderCards);
[topic,status].forEach(control=>control.addEventListener('change',renderCards));
refresh();
</script>"""


# ---------------------------------------------------------------------------
# 模块首页生成(数据流第 5 步的模块页半边)：
# 组成——统计徽标(章节数/已完成/累计轮次)、人工或自动简介、进度条、
# “本模块待复习”区块、搜索框/专题下拉/轮次下拉，以及章节卡片网格。
# 安全细节：chapters/topics 用 json.dumps 序列化后再把 "</" 替换成 "<\/"，
# 防止章节标题里含 “</script>” 时提前闭合页面脚本标签(JSON 注入防护)。
# 与 study_server 的契约：页面里的 JS(MODULE_PAGE_JS)靠 /api/library、/api/daily
# 填充完成数/轮次/到期，本函数只负责注入静态章节数据。
# ---------------------------------------------------------------------------
def module_index_page(module: dict[str, object], page_chapters: list[dict[str, object]]) -> str:
    """生成与 Interview Forge同风格的模块首页：统计、简介、进度、筛选与卡片。"""
    module_id = str(module["id"])
    unit = str(module.get("unit", "章"))
    count = len(page_chapters)
    # topics 用 dict.fromkeys 去重并保插入序(专题下拉选项顺序与源笔记顺序一致)；
    # 章节数据与专题数据分别序列化，喂给 MODULE_PAGE_JS 的两个 JSON 占位符。
    topics = list(dict.fromkeys(str(c.get("category")) for c in page_chapters if c.get("category")))
    chapters_json = json.dumps(page_chapters, ensure_ascii=False).replace("</", "<\\/")
    topics_json = json.dumps(topics, ensure_ascii=False).replace("</", "<\\/")
    script = (
        MODULE_PAGE_JS
        .replace("__MODULE_ID__", module_id)
        .replace("__UNIT__", unit)
        .replace("__CHAPTERS_JSON__", chapters_json)
        .replace("__TOPICS_JSON__", topics_json)
    )
    about = html.escape(str(module.get("about") or ""))
    # 简介来源优先级：登记表人工文案 > module_about 自动提取 > 兜底文案
    # (后者在 build() 组装模块 dict 时决定)；HTML 转义后放入模块页，防注入。
    return f'''<div class="shell">{topbar("..")}
<header class="module-hero">
  <div>
    <h1>{html.escape(str(module['title']))}</h1>
    <div class="module-sub">{html.escape(str(module['category']))} · {count} {unit} · 支持多轮学习记录</div>
    <div class="module-about">{about}</div>
    <div id="connection" class="connection">正在连接本地数据库</div>
  </div>
  <div class="module-stats">
    <div class="stat"><span>{unit}数</span><strong>{count}</strong></div>
    <div class="stat"><span>已完成</span><strong id="completedCount">0</strong></div>
    <div class="stat"><span>累计轮次</span><strong id="totalRounds">0</strong></div>
  </div>
</header>
<div id="serverNotice" class="notice" hidden>数据库没有启动。请通过根目录中的“启动学习站.cmd”进入，记录才会写入 SQLite。</div>
<section class="module-progress" aria-labelledby="progressLabel"><div class="progress-head"><span id="progressLabel">至少完成一轮的{unit}</span><strong id="progressText">0 / {count}</strong></div><div id="progressBar" class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="{count}" aria-valuenow="0"><div id="progress"></div></div></section>
<section id="moduleDue" class="module-due" aria-labelledby="moduleDueTitle"><div class="due-head"><h2 id="moduleDueTitle">本模块待复习</h2><span id="moduleDueSummary" class="due-summary">正在读取…</span></div><div id="moduleDueList" class="due-list"></div></section>
<section class="module-controls" aria-label="筛选章节">
  <div class="field"><label for="search">搜索</label><input id="search" type="search" placeholder="标题、方法或简介" autocomplete="off"></div>
  <div class="field" id="topicWrap"><label for="topic">专题</label><select id="topic"><option value="">全部专题</option></select></div>
  <div class="field"><label for="status">学习轮次</label><select id="status"><option value="">全部轮次</option><option value="due">待复习</option><option value="new">尚未完成</option><option value="once">完成 1 轮</option><option value="repeat">完成 2 轮以上</option></select></div>
</section>
<section class="chapter-grid" id="chapterGrid"></section>
<div id="empty" class="empty" hidden>没有匹配的内容，请调整搜索词或筛选条件。</div>
<div id="toast" class="toast" aria-live="polite"></div></div>
{script}'''


# ---------------------------------------------------------------------------
# Hot 100 模块(modules 列表的第 0 个)：不拆 Markdown，而是把 build_hot100 的
# 题目目录原样登记成书架章节——每道题 = 一章，章节页直接复用 build_hot100
# 生成的题解 HTML(URL 指向 ../03-题解/<folder>/<04d题号-题名>.html)，
# 书架与 Interview Forge因此共享同一套题解页面，互不重复渲染。
# 数据流/关系：
#   - PROBLEMS 是本文件从 build_hot100 import 的模块级解析结果(构建期快照)，
#     所以必须保证 build_hot100 先完成(其 build() 末尾 subprocess 调本文件)；
#   - content_id 统一为 "hot100:NNNN"(题号补 4 位)，与课程章节 "模块id:NN"
#     格式一致，study_server 写 content_events 时无需区分来源；
#   - routes 把 /03-题解/<folder>/<file> 的真实 URL 映射到该模块——服务器按
#     请求路径反查 module/content，再记录“完成一轮”事件；
#   - 本模块的 index.html 是 meta refresh 跳转页(0 秒跳回 ../../index.html，
#     即 Interview Forge首页)，点击卡片/记录完成都在 Hot 100 站内进行。
# ---------------------------------------------------------------------------
def build_hot100_module() -> tuple[dict[str, object], dict[str, dict[str, str]]]:
    """把 Hot 100 题目目录生成为书架模块，首页直接迁移到 Interview Forge。"""
    module_dir = OUTPUT_ROOT / "hot100"
    module_dir.mkdir(parents=True, exist_ok=True)
    chapters: list[dict[str, object]] = []
    routes: dict[str, dict[str, str]] = {}
    for problem in PROBLEMS:
        content_id = f"hot100:{int(problem['id']):04d}"
        filename = f"{int(problem['id']):04d}-{safe_name(str(problem['title']))}.html"
        chapter_url = f"../books/hot100/03-题解/{problem['folder']}/{filename}"
        chapters.append({
            "id": content_id,
            "title": f"{int(problem['id']):04d} {problem['title']}",
            "url": chapter_url,
            "difficulty": problem["difficulty"],
            "method": problem["method"],
        })
        routes[f"/books/hot100/03-题解/{problem['folder']}/{filename}"] = {"module_id": "hot100", "content_id": content_id}
    topics = sorted({p["category"] for p in PROBLEMS})
    module = {
        **HOT100_MODULE,
        "chapter_count": len(chapters),
        "chapters": chapters,
        "url": "../index.html",
        "about": f"{len(chapters)} 道高频算法题，覆盖 {len(topics)} 个专题；点击卡片直接进入对应题解，完成一轮会同步到书架进度。",
    }
    redirect_page = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><meta http-equiv="refresh" content="0; url=../../index.html"><title>{html.escape(module['title'])}</title><link rel="stylesheet" href="../assets/library.css?v={ASSET_VERSION}"></head><body><div class="shell" style="min-height:70vh;display:grid;place-items:center"><main class="chapter-list" style="text-align:center"><h1>{html.escape(module['title'])}</h1><p>正在打开 Interview Forge…</p><p><a href="../../index.html">如果未自动跳转，请点击这里</a></p></main></div></body></html>'''
    (module_dir / "index.html").write_text(redirect_page, encoding="utf-8")
    return module, routes


# ---------------------------------------------------------------------------
# 搜索索引文本清洗：把章节正文压成一行可检索纯文本——剥掉代码围栏(含内部内容，
# 代码不算可读正文)、标题符号、图片/链接语法、强调符号，然后整段截断到约
# limit=1400 字符，控制 search-index.json 的体积与检索量。
# 与 clean_summary_line 的差异：这里保留正文只去结构(“全文”)，那里提炼一句话
# (“摘要”)；前者喂 search-index.json，后者喂模块页卡片 intro。
# ---------------------------------------------------------------------------
def clean_search_text(body: str, limit: int = 1400) -> str:
    """把章节正文清洗成可检索的纯文本（去掉代码围栏、标题符号、Markdown 链接）。"""
    lines: list[str] = []
    in_fence = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        cleaned = re.sub(r"^#{1,6}\s+", "", line)
        cleaned = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", cleaned)
        cleaned = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cleaned)
        cleaned = re.sub(r"[`*_>|]", " ", cleaned)
        if cleaned.strip():
            lines.append(cleaned.strip())
    return " ".join(lines)[:limit]


# ---------------------------------------------------------------------------
# 全文搜索页(search.html)：
#   - 构建期：生成 search-index.json(全部章节的 id/标题/模块名/清洗后正文，
#     见 build() 末尾)，随书架一起落盘；
#   - 运行期：页面 JS fetch 该索引，纯客户端评分排序(不依赖后端，双击打开
#     静态文件也能搜索)：标题命中 3 分、模块名命中 2 分、正文命中 1 分，
#     降序取前 60 条；搜不到时提示换词；
#   - 索引加载失败的提示引导用户经“启动学习站.cmd”访问(HTTP 服务才提供
#     search-index.json 的 MIME 与缓存策略)。
# 架构含义：搜索 = 构建期离线索引 + 客户端打分，属于“无后端全文检索”。
# ---------------------------------------------------------------------------
def search_page(chapter_count: int) -> str:
    body = '''<div class="shell">__TOPBAR__
<section class="hero"><h1>全文搜索</h1><p>跨全部书架模块（__CHAPTER_COUNT__ 个章节）搜索标题与正文，离线索引由构建器生成。</p></section>
<div class="module-controls"><div class="field"><label for="searchInput">关键词</label><input id="searchInput" type="search" placeholder="输入关键词，如 循环依赖、MVCC、线程池、Kafka" autocomplete="off"></div></div>
<main id="results" class="chapter-grid" aria-live="polite"></main>
</div>
<script>
let entries=[];
const input=document.getElementById('searchInput');
const results=document.getElementById('results');
function esc(value){return String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))}
function score(entry,q){
  const title=entry.title.toLowerCase(),mod=entry.module_title.toLowerCase(),text=(entry.text||'').toLowerCase();
  if(title.includes(q))return 3;
  if(mod.includes(q))return 2;
  return text.includes(q)?1:0;
}
function render(){
  const q=input.value.trim().toLowerCase();
  if(!q){results.innerHTML='<p class="empty">输入关键词开始搜索。</p>';return}
  const hits=entries.map(e=>({e,s:score(e,q)})).filter(x=>x.s>0).sort((a,b)=>b.s-a.s).slice(0,60);
  results.innerHTML=hits.length?hits.map(({e})=>`<article class="chapter-card"><div class="card-head"><h2><a href="${esc(e.url)}">${esc(e.title)}</a></h2></div><div class="meta"><span class="pill">${esc(e.module_title)}</span></div></article>`).join(''):'<p class="empty">没有匹配结果，换个关键词试试。</p>';
}
input.addEventListener('input',render);
fetch('search-index.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error();return r.json()}).then(data=>{entries=data;render()}).catch(()=>{results.innerHTML='<p class="empty">索引加载失败（请通过 启动学习站.cmd 访问）。</p>'});
</script>'''
    body = body.replace("__TOPBAR__", topbar(".")).replace("__CHAPTER_COUNT__", str(chapter_count))
    return document("全文搜索", body, "assets/library.css")


# ---------------------------------------------------------------------------
# 主流程 build()：资产准备 → Hot 100 模块登记 → 逐模块“拆章 → 逐章渲染 →
# 模块页落盘” → manifest / 搜索索引 / 总页落盘。
# 触发方式：直接运行本文件，或被 build_hot100.build() 末尾的 subprocess 调用
# (build_hot100.py 1242-1244 行)；两处共用同一入口保证产物一致。
# ---------------------------------------------------------------------------
def build() -> None:
    # 第 0 步：固定资产落盘。library.css / library-mermaid.js 只 strip 首尾空白再写
    # (与常量内容逐字节一致，便于 check 脚本比对)；版本号 ?v= 在页面引用处统一。
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    # 增量构建缓存：脚本自身哈希或资源版本变化时整体失效（详见 build_cache）。
    cache = build_cache.load_cache(HOT100_ROOT)
    cache = build_cache.invalidate_on_tool_change(cache, Path(__file__).resolve())
    (OUTPUT_ROOT / "assets").mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "assets" / "library.css").write_text(LIBRARY_CSS.strip() + "\n", encoding="utf-8")
    (OUTPUT_ROOT / "assets" / "library-mermaid.js").write_text(MERMAID_JS.strip() + "\n", encoding="utf-8")
    # 【沉浸脚本下线说明】早期版本曾在 assets 里输出 immersive.js(沉浸阅读增强)，
    # 学习记录/沉浸交互已内联进各章节页的 <script>(见下方 reader 模板)，
    # 这里把历史遗留的旧文件删掉，避免 assets 残留无用脚本被检查脚本误报。
    old_immersive = OUTPUT_ROOT / "assets" / "immersive.js"
    if old_immersive.exists():
        old_immersive.unlink()
    # Mermaid 运行库从 tools/vendor 原样拷入 assets(体积大且无需构建处理，
    # 只做版本固定的复制)；源文件缺失直接抛错——构建失败比线上页面静默坏掉
    # 更好定位。
    mermaid_source = Path(__file__).resolve().parent / "vendor" / "mermaid-11.16.1.min.js"
    mermaid_vendor = OUTPUT_ROOT / "assets" / "mermaid-11.16.1.min.js"
    if not mermaid_source.exists():
        raise FileNotFoundError(f"缺少 Mermaid 源运行库：{mermaid_source}")
    shutil.copy2(mermaid_source, mermaid_vendor)
    # 模块列表以 Hot 100 模块打头(数据流第 1 步的“登记”对它是程序生成)：
    # 它没有源笔记，url 直接指向 Interview Forge首页；routes 先并入它的题目映射。
    hot100_module, hot100_routes = build_hot100_module()
    modules: list[dict[str, object]] = []
    routes: dict[str, dict[str, str]] = dict(hot100_routes)
    # Hot 100 章节的搜索条目：题解页由 build_hot100 维护，这里没有可清洗的正文，
    # 索引用 方法(method) + 难度(difficulty) 作为检索字段——搜“滑动窗口”能命中
    # 对应题解，再经 module_title / url 跳转到题解页。
    search_entries: list[dict[str, object]] = [
        {
            "id": str(chapter["id"]),
            "module_id": "hot100",
            "module_title": "Hot 100 算法刷题精讲",
            "title": str(chapter["title"]),
            "url": str(chapter["url"]),
            "text": f"{chapter.get('method', '')} {chapter.get('difficulty', '')}",
        }
        for chapter in hot100_module["chapters"]
    ]
    # source_modules：把登记表里的相对路径源笔记解析成“绝对路径 → 模块 id”映射，
    # rewrite_local_links 靠它把“指向其他课程 .md 的链接”改写为对应模块首页。
    source_modules = {(NOTES_ROOT / definition["source"]).resolve(): str(definition["id"]) for definition in LIBRARY_MODULES}
    # 逐个课程模块：读源(utf-8-sig 兼容带 BOM 的源文件)→ 拆章 → 建模块目录。
    for definition in LIBRARY_MODULES:
        source = NOTES_ROOT / definition["source"]
        text = source.read_text(encoding="utf-8-sig")
        # split_chapters 返回 (书名, 章节列表)；模块显示名优先用登记表 title，
        # 源里的一级标题只作登记表为空时的兜底(见下方模块 dict 组装处)。
        book_title, raw_chapters = split_chapters(text, definition["title"])
        module_dir = OUTPUT_ROOT / definition["id"]
        assets_dir = module_dir / "assets"
        module_dir.mkdir(parents=True, exist_ok=True)
        # chapters 是“书架侧”章节数据(id/标题/链接/intro)，后续喂给模块页 JS 与
        # manifest；章节页文件名统一 chapter-NN.html，章节 id 统一 “模块id:NN”。
        chapters: list[dict[str, object]] = []
        # 增量构建：整本书源哈希未变且该书全部章节输出都在 → 跳过章节正文渲染
        # （元数据、搜索索引仍照常收集）；需要渲染时该书所有章节并行渲染。
        rel_source = source.relative_to(HOT100_ROOT).as_posix()
        src_sha = build_cache.file_sha256(source)
        book_outputs = [
            f"library/{definition['id']}/chapter-{index:02d}.html"
            for index in range(1, len(raw_chapters) + 1)
        ]
        need_render = build_cache.needs_rebuild(cache, "book:" + rel_source, src_sha, book_outputs, HOT100_ROOT)
        prepared_map: dict[str, str] = {}
        for index, raw_chapter in enumerate(raw_chapters, 1):
            chapter_id = f"{definition['id']}:{index:02d}"
            # 章节正文流水线：净化+互链改写 → Markdown 渲染 → 演示内嵌 → 拼章节页模板。
            prepared_map[chapter_id] = normalize_chapter_markdown(
                rewrite_local_links(raw_chapter["body"], source, assets_dir, source_modules)
            )
        contents_map: dict[str, str] = {}
        if need_render and prepared_map:
            with ProcessPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
                for chapter_id, content in pool.map(_render_chapter_body_worker, list(prepared_map.items())):
                    contents_map[chapter_id] = content
            build_cache.mark_built(cache, "book:" + rel_source, src_sha, book_outputs)
        for index, raw_chapter in enumerate(raw_chapters, 1):
            chapter_id = f"{definition['id']}:{index:02d}"
            filename = f"chapter-{index:02d}.html"
            # 章节元数据进模块 chapters：id/标题/相对链接/intro(章节摘要)，
            # 供模块首页 JS 渲染卡片、筛选与搜索（不依赖章节正文渲染结果）。
            route = f"/library/{definition['id']}/{filename}"
            routes[route] = {"module_id": definition["id"], "content_id": chapter_id}
            chapters.append({
                "id": chapter_id,
                "title": raw_chapter["title"],
                "url": f"{definition['id']}/{filename}",
                "intro": chapter_summary(raw_chapter["body"]),
            })
            search_entries.append({
                "id": chapter_id,
                "module_id": definition["id"],
                "module_title": definition["title"] or book_title,
                "title": raw_chapter["title"],
                "url": f"{definition['id']}/{filename}",
                "text": clean_search_text(raw_chapter["body"]),
            })
            content = contents_map.get(chapter_id)
            if content is None:
                continue  # 增量跳过：该章输出已存在且源未变
            # —— 以下为渲染+拼装+落盘（仅 need_render 的章节执行）——
            # 【演示内嵌机制 <!--demo:文件名-->】章节源里出现该 HTML 注释占位时，
            # 把它替换为 <iframe src="../../05-可视化/<文件名>?embed=1">：
            # 交互演示页(由 build_html_site 生成)以嵌入模式套进章节正文，
            # 读者在阅读页里原地运行演示；iframe title 取文件名去掉扩展名的
            # stem，loading="lazy" 懒加载避免页面首屏被多个演示拖慢。
            content = re.sub(
                r"<!--demo:([^>]+?)-->",
                lambda match: (
                    '<div class="demo-embed">'
                    f'<iframe src="../../books/hot100/05-可视化/{html.escape(match.group(1).strip())}?embed=1" '
                    f'title="交互演示：{html.escape(Path(match.group(1).strip()).stem)}" '
                    'loading="lazy" scrolling="no"></iframe></div>'
                ),
                content,
            )
            # 章节导航(上一章/下一章)：首章没有“上一章”、末章没有“下一章”；
            # 链接为空时对应 HTML 片段为空串，整段不渲染。
            if index > 1:
                previous_link, previous_label = f"chapter-{index - 1:02d}.html", "← 上一章"
            else:
                previous_link, previous_label = "", ""
            if index < len(raw_chapters):
                next_link, next_label = f"chapter-{index + 1:02d}.html", "下一章 →"
            else:
                next_link, next_label = "", ""
            previous_html = f'<a href="{previous_link}">{previous_label}</a>' if previous_link else ""
            next_html = f'<a href="{next_link}">{next_label}</a>' if next_link else ""
            # 章节页 HTML 模板(reader)组成：
            #   面包屑 书架 › 模块 › 本章(aria 标注当前页)；状态条内嵌“学习记录
            #   轮次/下次复习日期/完成一章/导出本章”控件；正文由 render_markdown
            #   产出；页尾章节导航含 目录/上一章/下一章。
            # 内联 <script>：contentId/moduleId 由 json.dumps 注入；loadStatus
            # 并发 fetch /api/library + /api/daily 填充状态与复习日期，
            # “完成一轮”POST /api/content/complete(题解章节走 /api/complete +
            # problem_id)，导出本章按钮的处理逻辑也在其中；接口不可达时提示
            # 静态浏览模式。脚本内联在页面里是为了离线打开也能给出明确提示。
            reader = f'''<div class="shell">{topbar("..")}
<main class="reader"><nav class="breadcrumb" aria-label="面包屑"><a href="../index.html">学习书架</a><span aria-hidden="true">›</span><a href="index.html">{html.escape(definition['title'])}</a><span aria-hidden="true">›</span><span aria-current="page">{html.escape(raw_chapter['title'])}</span></nav><div class="module-meta">{html.escape(definition['category'])} · 第 {index} / {len(raw_chapters)} 章</div><h1>{html.escape(raw_chapter['title'])}</h1><div class="chapter-status" aria-label="学习记录"><span id="chapterStatus">正在读取本章记录</span><span id="chapterDue" class="due-line">下次复习：—</span><div id="chapterNotice" class="notice" hidden>请通过“启动学习站.cmd”进入，才能写入数据库。</div><button id="completeChapter" class="complete-button" type="button">完成本章一轮</button><button id="exportChapter" class="complete-button" type="button">导出本章</button><div id="chapterToast" class="toast" aria-live="polite"></div></div>{content}<nav class="chapter-nav" aria-label="章节导航"><a class="nav-toc" href="index.html">目录</a>{previous_html}{next_html}</nav></main></div>
<script>const contentId={json.dumps(chapter_id, ensure_ascii=False)},moduleId={json.dumps(definition['id'], ensure_ascii=False)};const button=document.getElementById('completeChapter'),status=document.getElementById('chapterStatus'),notice=document.getElementById('chapterNotice'),toast=document.getElementById('chapterToast'),dueLine=document.getElementById('chapterDue');const shortTime=(value)=>{{if(!value)return '';const d=new Date(value);return `${{String(d.getMonth()+1).padStart(2,'0')}}-${{String(d.getDate()).padStart(2,'0')}} ${{String(d.getHours()).padStart(2,'0')}}:${{String(d.getMinutes()).padStart(2,'0')}}`}};async function loadStatus(){{try{{const [libraryResponse,dailyResponse]=await Promise.all([fetch('/api/library',{{cache:'no-store'}}),fetch(`/api/daily?module=${{encodeURIComponent(moduleId)}}`,{{cache:'no-store'}})]);if(!libraryResponse.ok||!dailyResponse.ok)throw new Error();const data=await libraryResponse.json();const daily=await dailyResponse.json();const info=data.contents[contentId]||{{rounds:0,last_activity_at:null}};status.textContent=`已完成 ${{info.rounds||0}} 轮${{info.last_activity_at?' · 最近 '+shortTime(info.last_activity_at):''}}`;button.disabled=false;notice.hidden=true;const dueItem=daily.contents.find(item=>item.content_id===contentId);if(dueItem){{const overdue=dueItem.due_date<daily.today;dueLine.textContent=`下次复习：${{String(dueItem.due_date).slice(5)}}${{overdue?'（已逾期）':''}}`;dueLine.classList.toggle('due-overdue',overdue)}}else{{dueLine.textContent='下次复习：—';dueLine.classList.remove('due-overdue')}}}}catch(_){{status.textContent='当前是静态浏览模式';button.disabled=true;notice.hidden=false;dueLine.textContent='下次复习：—';dueLine.classList.remove('due-overdue')}}}}button.addEventListener('click',async()=>{{button.disabled=true;button.textContent='记录中…';try{{const response=await fetch('/api/content/complete',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{module_id:moduleId,content_id:contentId}})}});const result=await response.json();if(!response.ok)throw new Error(result.error||'记录失败');const next=result.next_due?`（下次复习 ${{String(result.next_due).slice(5)}}）`:'';toast.textContent=`已记录第 ${{result.round_no}} 轮${{next}}`;button.textContent='完成本章一轮';await loadStatus()}}catch(error){{toast.textContent=error.message;button.disabled=false;button.textContent='完成本章一轮'}}}});loadStatus();document.getElementById('exportChapter').addEventListener('click',async()=>{{try{{const css=await (await fetch('../assets/library.css?v={ASSET_VERSION}')).text();const reader=document.querySelector('main.reader');const html='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+document.title+'</title><style>'+css+'</style></head><body>'+reader.outerHTML+'</body></html>';const blob=new Blob([html],{{type:'text/html'}});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=document.title.replace(/[\\\\/:*?"<>|]/g,'_')+'.html';document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);toast.textContent='已导出本章 HTML'}}catch(_){{toast.textContent='导出失败，请通过启动学习站.cmd访问'}}}});</script>'''
            # Mermaid 依赖按需注入：只有正文含 .mermaid-diagram 的章节页才引入
            # mermaid 运行库与渲染驱动(library-mermaid.js)，其余页面零额外脚本；
            # 版本号统一带 ?v=ASSET_VERSION 便于缓存失效。
            diagram_scripts = ""
            if 'class="mermaid-diagram"' in content:
                diagram_scripts = f'<script src="../assets/mermaid-11.16.1.min.js?v={ASSET_VERSION}"></script><script src="../assets/library-mermaid.js?v={ASSET_VERSION}"></script>'
            chapter_scripts = diagram_scripts
            (module_dir / filename).write_text(document(raw_chapter["title"], reader, "../assets/library.css", chapter_scripts), encoding="utf-8")
        # 书架使用登记表中的人工整理标题，避免源文件里的临时标题、章节名或
        # “副本”等文件管理字样出现在课程卡片上。源标题只用于无登记标题时兜底。
        # 模块 dict 组装：显示名优先登记表 title、缺省回书名；about 优先登记表人工
        # 文案、缺省由 module_about 自动提取(双轨设计，见 module_about 注释)。
        module = {
            **definition,
            "title": definition["title"] or book_title,
            "chapter_count": len(chapters),
            "chapters": chapters,
            "url": f"{definition['id']}/index.html",
            "about": definition.get("about") or module_about(text, f"{definition['category']} · {len(chapters)} 章，按章节系统学习；每章都支持多轮复习记录。"),
        }
        modules.append(module)
        # 给每章补上相对模块首页的链接(chapter-NN.html)，模块页 JS 用它拼卡片；
        # 最后生成模块首页 index.html(模块页 = 统计/简介/进度/筛选/卡片)。
        page_chapters = [
            {**chapter, "href": f"chapter-{index:02d}.html"}
            for index, chapter in enumerate(chapters, 1)
        ]
        module_page = module_index_page(module, page_chapters)
        (module_dir / "index.html").write_text(document(module["title"], module_page, "../assets/library.css"), encoding="utf-8")
    modules.append(hot100_module)
    # 按显式学习顺序表重排模块卡片与分类按钮；未登记的新模块追加到末尾。
    module_order = MODULE_ORDER + [
        str(module["id"]) for module in modules if str(module["id"]) not in MODULE_ORDER
    ]
    modules.sort(key=lambda module: module_order.index(str(module["id"])))
    # manifest.json = modules + routes，是“静态生成 ↔ 动态服务”之间的唯一契约文件：
    #   - modules：全部模块信息(章节数/章节列表)，study_server 的 /api/library
    #     据此聚合完成数、轮次与进度条；
    #   - routes：URL → {module_id, content_id} 映射，/api/content/complete、
    #     /api/complete 记录事件时据此反查，写进 SQLite 的 content_events。
    manifest = {"modules": modules, "routes": routes}
    (OUTPUT_ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # 搜索资产：search-index.json 用紧凑分隔符(去掉多余空格)减小体积；
    # search.html 全文搜索页(见 search_page 的客户端评分说明)。
    (OUTPUT_ROOT / "search-index.json").write_text(
        json.dumps(search_entries, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    (OUTPUT_ROOT / "search.html").write_text(search_page(len(search_entries)), encoding="utf-8")
    # 书架总页 index.html(build_bookshelf)：
    #   模块卡片网格(标题/分类/章节数/进度条) + 分类筛选按钮(纯客户端切换
    #   显隐)；页面 JS 启动时 fetch /api/library 填进度条、/api/daily 填
    #   “全书架待复习”汇总与各模块角标上的待复习数；接口不可达时静默降级
    #   (进度条保持 0、汇总区保持提示文案)，保证静态打开也能浏览。
    module_cards = "".join(f'<article class="module-card" data-category="{html.escape(module["category"])}"><div class="card-head"><h2><a href="{html.escape(module["url"])}">{html.escape(module["title"])}</a></h2><span class="module-due-badge" data-module-due="{html.escape(str(module["id"]))}" hidden>待复习 0</span></div><div class="module-meta"><span>{html.escape(module["category"])}</span><span>{module["chapter_count"]} {module.get("unit", "章")}</span></div><div class="module-progress"><span data-module-progress="{module["id"]}" style="width:0%"></span></div><a class="module-link" href="{html.escape(module["url"])}">进入课程 →</a></article>' for module in modules)
    categories = ["全部", *dict.fromkeys(str(module["category"]) for module in modules)]
    filters = "".join(f'<button type="button" data-filter="{html.escape(category)}" class="{"active" if category == "全部" else ""}">{html.escape(category)}</button>' for category in categories)
    index_body = f'''<div class="shell">{topbar(".")}<section class="hero"><h1>学习书架</h1><p>算法、Python、模型训练、RAG、Agent 与基础设施统一分成可追踪课程；每个章节都支持多轮学习记录与到期复习。</p></section><section id="shelfDueSummary" class="shelf-due-summary" aria-label="全书架待复习"><span>正在读取全书架待复习…</span></section><div class="filters" aria-label="课程分类">{filters}</div><main class="module-grid" id="moduleGrid">{module_cards}</main></div><script>document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{{document.querySelectorAll('[data-filter]').forEach(item=>item.classList.toggle('active',item===button));const match=button.dataset.filter==='全部'?()=>true:card=>card.dataset.category===button.dataset.filter;document.querySelectorAll('.module-card').forEach(card=>{{card.hidden=!match(card);card.style.display=card.hidden?'none':''}});}}));fetch('/api/library',{{cache:'no-store'}}).then(r=>r.ok?r.json():Promise.reject()).then(data=>document.querySelectorAll('[data-module-progress]').forEach(bar=>{{const info=data.modules[bar.dataset.moduleProgress]||{{completed:0,total:1}};bar.style.width=`${{Math.round(info.completed/info.total*100)}}%`}})).catch(()=>{{}});fetch('/api/daily',{{cache:'no-store'}}).then(r=>r.ok?r.json():Promise.reject()).then(daily=>{{const summary=daily.summary||{{}};const total=summary.contents||0,overdue=summary.overdue_contents||0;const el=document.getElementById('shelfDueSummary');if(el){{el.innerHTML=total?`<span><strong>全书架待复习 ${{total}} 章</strong>${{overdue?`（逾期 ${{overdue}}）`:''}}，完成一轮后自动推进下次复习</span><a class="shelf-due-go" href="#moduleGrid">去各模块复习 →</a>`:`<span>今日全书架没有到期章节，可以继续学习新内容。</span>`}}document.querySelectorAll('[data-module-due]').forEach(badge=>{{const info=(summary.modules||{{}})[badge.dataset.moduleDue];if(info&&info.due){{badge.hidden=false;badge.textContent=`待复习 ${{info.due}}`;badge.classList.toggle('overdue',(info.overdue||0)>0)}}}})}}).catch(()=>{{}});</script>'''
    (OUTPUT_ROOT / "index.html").write_text(document("学习书架", index_body, "assets/library.css"), encoding="utf-8")
    build_cache.save_cache(HOT100_ROOT, cache)
    # 构建收尾统计(模块总数/章节总数)，供命令行确认与构建日志留痕；
    # modules 含 Hot 100 模块，章节总数恒 ≥ 题目数 + 课程章节数。
    print(f"Library modules: {len(modules)}; chapters: {sum(module['chapter_count'] for module in modules)}")


# 入口约定：直接运行本文件 = 只重建书架；
# 从 build_hot100.py 进入则先重建 Hot 100 站，再 subprocess 调本文件重建书架，
# 之后 build_html_site.py 重建可视化等页面——三者在构建链上严格串行。
if __name__ == "__main__":
    build()
