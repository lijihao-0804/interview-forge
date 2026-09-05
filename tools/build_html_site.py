# =============================================================================
# build_html_site.py —— HTML 站点生成器（阅读页渲染层）
# -----------------------------------------------------------------------------
# 模块职责（按构建顺序）：
#   1. 渲染阅读页：把 ROOT 下 README/MAINTENANCE/QA-REPORT 以及
#      CONTENT_DIRS（00-总览/01-基础/02-专题/03-题解/04-模板）里的全部 Markdown
#      转换为“完整离线 HTML 阅读页”（render_markdown：面包屑 + 目录 + 正文 +
#      题解内嵌可视化；公式转原生 MathML）。
#   2. 生成公共资源：把 SITE_CSS / SITE_JS 常量原样写入 assets/site.css|site.js，
#      并从 tools/vendor 复制 uPlot 离线图表库到 assets（供学习面板趋势图用）。
#   3. 增补学习面板：update_dashboard 把面板题卡的 note 字段 .md→.html 并注入
#      快捷导航；render_notebook 生成错题本页（数据运行时取自 /api/weaklist）。
#   4. 润色可视化页：polish_visual 给 05-可视化 的独立演示页注入统一样式、统一
#      导航与可访问性增强，并支持被阅读页 iframe 内嵌（VISUAL_EMBEDS 绑定）。
# -----------------------------------------------------------------------------
# 与其它构建步骤的执行关系（每一步都是上一步产物的消费者）：
#   build_hot100.py    —— 先生成题解/专题/路线/复习清单的 Markdown 源、学习面板
#                          index.html、05-可视化 各演示页（含 Hot 100 题库数据）；
#   build_library.py   —— 再生成学习书架课程页（library/），并复用本模块的
#                          render_math_in_markdown 渲染公式，保证两处公式一致；
#   build_html_site.py —— 最后把全部 Markdown“发布”成阅读页，并连接面板、书架、
#                          可视化三大入口（即本文件）；
#   check_hot100.py    —— 之后运行的校验脚本：import 本模块的 VISUAL_EMBEDS，
#                          反向断言阅读页/可视化页的面板格式与入口，并要求
#                          assets 与常量区保持一致（因此常量内一个字符都不能动）。
# 任何 .md 或常量改动后，应完整重跑四步：build_hot100 → build_library →
# build_html_site → check_hot100，保证离线站点与源稿同步。
# =============================================================================
from __future__ import annotations

import html
import os
import re
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import markdown

import build_cache

# 并行渲染进程数：8（或按 CPU 核数自动收敛）。渲染是 CPU+IO 混合，进程池
# 不受 GIL 限制；仅在逐文件渲染（render_markdown）阶段并行，聚合产物仍串行。
PARALLEL_WORKERS = min(8, os.cpu_count() or 4)

# markdown：python-markdown 库，负责 Markdown→HTML；代码高亮经其 codehilite
# 扩展调用 Pygments（render_markdown 中启用）。build_library.py 使用同一环境，
# 因此本阅读页与学习书架的渲染行为一致。
# from __future__ import annotations：把类型注解推迟为字符串求值，使
# dict[str, tuple[str, dict[str, str]]] 这类 PEP 585 注解在旧解释器下也合法。


# ROOT：仓库根目录（本文件所在 tools 目录的上一级）。刻意用 __file__ 固定根
# 而非 os.getcwd()——构建可在任意工作目录下启动，固定根可避免相对路径漂移；
# 全站所有输出、链接换算都以 ROOT 为基准（与 check_hot100.py 的 ROOT 相同）。
ROOT = Path(__file__).resolve().parents[1]
# CONTENT_DIRS：需要渲染成阅读页的内容目录白名单（即“学习站主体”）。名单外的
# 目录不会被渲染：library/（学习书架，归 build_library.py 管）、05-可视化/
# （演示页只被 polish_visual 润色、不重渲染）、06-扩展题源/、99-原稿归档/
# （历史归档保持 .md 源稿状态）。根级 README/MAINTENANCE 等由 build() 单独加入。
CONTENT_DIRS = ["books/hot100/00-总览", "books/hot100/01-基础", "books/hot100/02-专题", "books/hot100/03-题解", "books/hot100/04-模板"]


def _render_markdown_worker(job: tuple[str, str]) -> str:
    """子进程执行：渲染单个 Markdown 源为 HTML 阅读页，返回源文件绝对路径。"""
    src_abs, _ = job
    render_markdown(Path(src_abs))
    return src_abs

# ASSET_VERSION 的数据流：该值拼进每张阅读页 <link>/<script> 的 ?v= 查询串
# （render_markdown 里 css_href/js_href 引用），浏览器把它当作全新 URL 重新拉取，
# 从而绕开旧缓存；与 manifest.webmanifest / service-worker.js 的缓存策略配合，
# 离线站升级后可强制刷新。改值后必须重跑 build() 重建全部阅读页才会生效。
# 阅读页公共资源版本号：引用带 ?v= 防止浏览器缓存旧 site.css/site.js
# （新交互依赖最新脚本；升级实现后应递增此值并重建）。
ASSET_VERSION = "20260830-mobile1"

# VISUAL_EMBEDS：题解 → 可视化面板的绑定表（“可视化绑定 03-题解”的实现载体）。
# 键：题解 Markdown 相对 ROOT 的正斜杠路径；值：(05-可视化 下的 HTML 文件名,
# 内嵌查询参数)。render_visual_embed 按当前渲染源路径查表：命中则生成 iframe，
# src 带 embed=1&panel=N 或 embed=1&mode=...——可视化页内的
# VISUAL_EMBED_BOOTSTRAP 与 VISUAL_A11Y_SCRIPT 读这些参数进入对应的内嵌态
# （单面板 / 指定模式），从而“一个演示页按需呈现为某道题的方法演示”。
# 为什么用文件名而非 URL：演示页由 build_hot100.py 生成，文件名即稳定标识；
# 为什么刻意逐题绑定而非按专题自动关联：要求面板/模式与题目方法严格一致
# （如 0004-中位数用 median-two、0084-柱状图用 histogram），同专题不同方法的
# 题必须各绑各的。check_hot100.py 会反向校验：绑定表内题解的阅读页必须渲染出
# embed=1 的 iframe，表外题解不得出现交互演示，且“困难题”必须全部有绑定。
# 可视化只作为题解页底部的交互组件出现。每个绑定项选择一个确实与
# 题目方法一致的面板/模式；不要仅因为专题相同就绑定泛化演示。
VISUAL_EMBEDS: dict[str, tuple[str, dict[str, str]]] = {
    "books/hot100/03-题解/01-哈希表/0001-两数之和.md": ("01-哈希表.html", {"panel": "0"}),
    "books/hot100/03-题解/01-哈希表/0049-字母异位词分组.md": ("01-哈希表.html", {"panel": "1"}),
    "books/hot100/03-题解/01-哈希表/0128-最长连续序列.md": ("01-哈希表.html", {"panel": "2"}),
    "books/hot100/03-题解/02-双指针/0283-移动零.md": ("02.双指针.html", {"panel": "0"}),
    "books/hot100/03-题解/02-双指针/0011-盛最多水的容器.md": ("02.双指针.html", {"panel": "1"}),
    "books/hot100/03-题解/02-双指针/0015-三数之和.md": ("02.双指针.html", {"panel": "2"}),
    "books/hot100/03-题解/02-双指针/0042-接雨水.md": ("02.双指针.html", {"panel": "3"}),
    "books/hot100/03-题解/03-滑动窗口/0003-无重复字符的最长子串.md": ("滑动窗口与前缀和.html", {"mode": "window"}),
    "books/hot100/03-题解/04-子串/0076-最小覆盖子串.md": ("困难题核心状态实验室.html", {"mode": "min-window"}),
    "books/hot100/03-题解/04-子串/0239-滑动窗口最大值.md": ("困难题核心状态实验室.html", {"mode": "window-max"}),
    "books/hot100/03-题解/04-子串/0560-和为 K 的子数组.md": ("滑动窗口与前缀和.html", {"mode": "prefix"}),
    "books/hot100/03-题解/05-普通数组/0041-缺失的第一个正数.md": ("困难题核心状态实验室.html", {"mode": "first-missing"}),
    "books/hot100/03-题解/07-链表/0023-合并 K 个升序链表.md": ("困难题核心状态实验室.html", {"mode": "merge-k"}),
    "books/hot100/03-题解/07-链表/0025-K 个一组翻转链表.md": ("困难题核心状态实验室.html", {"mode": "reverse-k"}),
    "books/hot100/03-题解/07-链表/0206-反转链表.md": ("链表指针实验室.html", {}),
    "books/hot100/03-题解/08-二叉树/0124-二叉树中的最大路径和.md": ("困难题核心状态实验室.html", {"mode": "max-path"}),
    "books/hot100/03-题解/09-图论/0200-岛屿数量.md": ("网格搜索实验室.html", {"mode": "dfs"}),
    "books/hot100/03-题解/09-图论/0208-实现 Trie.md": ("树形查找算法可视化.html", {"panel": "4"}),
    "books/hot100/03-题解/09-图论/0994-腐烂的橘子.md": ("网格搜索实验室.html", {"mode": "bfs"}),
    "books/hot100/03-题解/10-回溯/0046-全排列.md": ("10-回溯.html", {"panel": "0"}),
    "books/hot100/03-题解/10-回溯/0078-子集.md": ("10-回溯.html", {"panel": "1"}),
    "books/hot100/03-题解/10-回溯/0017-电话号码的字母组合.md": ("10-回溯.html", {"panel": "2"}),
    "books/hot100/03-题解/10-回溯/0039-组合总和.md": ("10-回溯.html", {"panel": "3"}),
    "books/hot100/03-题解/10-回溯/0022-括号生成.md": ("10-回溯.html", {"panel": "4"}),
    "books/hot100/03-题解/10-回溯/0079-单词搜索.md": ("10-回溯.html", {"panel": "5"}),
    "books/hot100/03-题解/10-回溯/0051-N 皇后.md": ("10-回溯.html", {"panel": "6"}),
    "books/hot100/03-题解/11-二分查找/0035-搜索插入位置.md": ("查找算法可视化.html", {"panel": "1"}),
    "books/hot100/03-题解/11-二分查找/0004-寻找两个正序数组的中位数.md": ("困难题核心状态实验室.html", {"mode": "median-two"}),
    "books/hot100/03-题解/12-栈/0084-柱状图中最大的矩形.md": ("困难题核心状态实验室.html", {"mode": "histogram"}),
    "books/hot100/03-题解/12-栈/0739-每日温度.md": ("单调栈实验室.html", {}),
    "books/hot100/03-题解/13-堆/0295-数据流的中位数.md": ("困难题核心状态实验室.html", {"mode": "median-stream"}),
    "books/hot100/03-题解/15-动态规划/0032-最长有效括号.md": ("困难题核心状态实验室.html", {"mode": "valid-parentheses"}),
    "books/hot100/03-题解/15-动态规划/0416-分割等和子集.md": ("15-动态规划-0-1 背包问题：倒序遍历演示.html", {}),
    "books/hot100/03-题解/16-多维动态规划/0062-不同路径.md": ("动态规划状态转移.html", {"mode": "paths"}),
    "books/hot100/03-题解/16-多维动态规划/0072-编辑距离.md": ("困难题核心状态实验室.html", {"mode": "edit-distance"}),
    "books/hot100/03-题解/16-多维动态规划/1143-最长公共子序列.md": ("动态规划状态转移.html", {"mode": "lcs"}),
}


# =============================================================================
# SITE_CSS：阅读页全局样式（生成源常量，build() 原样写入 assets/site.css）。
# 内容区块（按出现顺序，均为“区块说明”——字符串内部不允许增删字符）：
#   ① 设计令牌：CSS 变量 + color-scheme，浅色/深色两套色板（prefers-color-scheme
#      切换）；滚动条、盒模型、基础排版与 :focus-visible 焦点样式；
#   ② 页面壳与导航：.site-shell 居中容器、.site-topbar 顶栏、.site-nav 导航链接
#      （含 .skip-link 无障碍跳转）；
#   ③ 阅读卡 .reader-card / .markdown-body 正文排版：标题层级、段落、引用块、
#      列表、分隔线、代码块（深色 .code-block + 复制工具栏）、表格（横向滚动
#      .table-wrap）、图片、任务列表、强调；
#   ④ MathML 公式样式：.math-inline-wrap / .math-display-wrap 滚动容器 +
#      <math> 的 display:inline math / block math——长公式在小范围内横向滚动，
#      不撑破阅读卡；
#   ⑤ 题解内嵌可视化：.reader-visual 区块与 .reader-visual-frame iframe；
#   ⑥ Pygments codehilite 类配色（Material 风格）——与 render_markdown 的
#      css_class="codehilite" 对应；
#   ⑦ 三个媒体查询：≤720px 窄屏重排 / prefers-reduced-motion 关闭动画 /
#      @media print 打印版（隐藏顶栏/目录/可视化，正文无边框铺满）。
# 约束：本常量内所有字符都是“生成源”，注释只能写在本赋值行上方或下一个常量
# 之间；改动需重跑 build() 才写进 assets/site.css，check_hot100.py 会按站点
# 规则校验该产物（含“无沉浸模式残留”断言）。
# =============================================================================
SITE_CSS = r"""
:root {
  color-scheme: light dark;
  --page-bg: #f4f6fb;
  --surface: #ffffff;
  --surface-soft: #f8f9fd;
  --surface-softer: #fbfcff;
  --text: #182235;
  --text-strong: #111a2c;
  --muted: #66748a;
  --line: #dfe4ee;
  --brand: #5654d4;
  --brand-strong: #4543bd;
  --brand-soft: #eeedff;
  --success: #157a52;
  --warning: #a85b00;
  --inline-code: #443fb0;
  --inline-code-bg: #f0efff;
  --shadow: 0 16px 44px rgba(33, 45, 73, .08);
}

@media (prefers-color-scheme: dark) {
  :root {
    --page-bg: #0f131b;
    --surface: #181e29;
    --surface-soft: #141a24;
    --surface-softer: #1b222e;
    --text: #eaf0fa;
    --text-strong: #f6f8ff;
    --muted: #a3afc2;
    --line: #313b4c;
    --brand: #b1afff;
    --brand-strong: #c4c2ff;
    --brand-soft: #292955;
    --success: #79d8a8;
    --warning: #ffc174;
    --inline-code: #cfcdff;
    --inline-code-bg: #272751;
    --shadow: 0 18px 48px rgba(0, 0, 0, .24);
  }
}

* { scrollbar-width: thin; scrollbar-color: color-mix(in srgb, var(--muted) 45%, transparent) transparent; }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: color-mix(in srgb, var(--muted) 45%, transparent); border-radius: 8px; border: 2px solid transparent; background-clip: padding-box; }
::-webkit-scrollbar-thumb:hover { background: color-mix(in srgb, var(--muted) 72%, transparent); border: 2px solid transparent; background-clip: padding-box; }

* { box-sizing: border-box; }
html { background: var(--page-bg); scroll-behavior: smooth; }
body {
  margin: 0;
  min-width: 0;
  color: var(--text);
  background:
    radial-gradient(circle at 12% 0%, color-mix(in srgb, var(--brand) 10%, transparent), transparent 34rem),
    var(--page-bg);
  font: 16px/1.9 system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
}

a { color: var(--brand); text-decoration: none; overflow-wrap: anywhere; }
a:hover { text-decoration: underline; }
:focus-visible { outline: 3px solid color-mix(in srgb, var(--brand) 48%, transparent); outline-offset: 3px; }
.skip-link {
  position: absolute;
  left: 12px;
  top: -60px;
  z-index: 20;
  padding: 8px 12px;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.skip-link:focus { top: 12px; }

.site-shell { width: min(100% - 32px, 1040px); margin: 0 auto; padding: 20px 0 56px; }
.site-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  padding: 12px 15px;
  margin-bottom: 18px;
  color: var(--text);
  background: color-mix(in srgb, var(--surface) 93%, transparent);
  border: 1px solid var(--line);
  border-radius: 15px;
  box-shadow: 0 8px 28px rgba(33, 45, 73, .055);
}
.site-brand { color: var(--text); font-weight: 760; letter-spacing: .01em; }
.site-nav { display: flex; gap: 6px; flex-wrap: wrap; }
.site-nav a { padding: 6px 9px; border-radius: 8px; color: var(--muted); font-size: 14px; }
.site-nav a:hover { color: var(--brand); background: var(--brand-soft); text-decoration: none; }
.site-nav a.lc-button { background: var(--brand); color: #fff; font-weight: 650; }
.site-nav a.lc-button:hover { background: var(--brand-strong); color: #fff; }

.reader-card {
  width: min(100%, 980px);
  min-width: 0;
  margin: 0 auto;
  padding: clamp(32px, 6vw, 72px);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 20px;
  box-shadow: var(--shadow);
}
.markdown-body { width: min(100%, 880px); min-width: 0; margin: 0 auto; overflow-wrap: break-word; }
.page-kicker { color: var(--muted); font-size: 13px; margin-bottom: 10px; }
.toc-box {
  margin: 30px 0 40px;
  padding: 0 17px;
  background: var(--surface-soft);
  border: 1px solid var(--line);
  border-radius: 13px;
}
.toc-box summary { cursor: pointer; padding: 12px 0; color: var(--brand); font-weight: 700; }
.toc-box summary:hover { color: var(--brand-strong); }
.toc-box .toc { padding: 0 0 14px; }
.toc-box ul { margin: 4px 0; padding-left: 22px; }
.toc-box li { margin: 3px 0; }

.markdown-body > :first-child { margin-top: 0; }
.markdown-body h1 { margin: 0 0 30px; font-size: clamp(31px, 5vw, 46px); line-height: 1.2; letter-spacing: -.025em; }
.markdown-body h2 { margin: 58px 0 20px; padding-bottom: 9px; border-bottom: 1px solid var(--line); font-size: 27px; line-height: 1.35; }
.markdown-body h3 { margin: 42px 0 14px; font-size: 21px; line-height: 1.45; }
.markdown-body h4 { margin: 32px 0 12px; font-size: 17px; line-height: 1.5; }
.markdown-body p { margin: 17px 0; }
.markdown-body li { margin: 7px 0; }
.markdown-body ul, .markdown-body ol { padding-left: 1.7em; }
.markdown-body hr { margin: 42px 0; border: 0; border-top: 1px solid var(--line); }
.markdown-body blockquote {
  margin: 26px 0;
  padding: 16px 20px;
  color: var(--text);
  background: var(--brand-soft);
  border-left: 4px solid var(--brand);
  border-radius: 0 11px 11px 0;
}
.markdown-body blockquote p { margin: 0; }
.markdown-body code {
  padding: .16em .44em;
  color: var(--inline-code);
  background: var(--inline-code-bg);
  border: 1px solid color-mix(in srgb, var(--brand) 17%, var(--line));
  border-radius: 5px;
  font: .91em/1.5 ui-monospace, "Cascadia Code", Consolas, monospace;
  font-variant-ligatures: none;
}
.code-block { margin: 20px 0; border: 1px solid #303849; border-radius: 12px; overflow: hidden; background: #151a24; }
.code-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 12px; color: #b6c0d4; background: #202735; font-size: 13px; }
.copy-code { border: 1px solid #526079; border-radius: 7px; padding: 4px 9px; color: #f0f3ff; background: transparent; cursor: pointer; font: inherit; }
.copy-code:hover { background: #303a4d; }
.copy-code:focus-visible { outline-color: #b8b6ff; }
.markdown-body pre { margin: 0; padding: 22px 24px; max-width: 100%; overflow: auto; color: #e9edf7; background: #151a24; tab-size: 4; }
.markdown-body pre code { padding: 0; color: inherit; background: transparent; border: 0; font-size: 14px; }
.markdown-body pre { font-variant-ligatures: none; }
.table-wrap { max-width: 100%; margin: 28px 0; overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; }
.markdown-body table { width: 100%; min-width: 540px; border-collapse: collapse; margin: 0; }
.markdown-body th:first-child, .markdown-body td:first-child { width: 200px; }
.markdown-body th, .markdown-body td { min-width: 108px; padding: 13px 17px; border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
.markdown-body th:last-child, .markdown-body td:last-child { border-right: 0; }
.markdown-body tr:last-child td { border-bottom: 0; }
.markdown-body th { background: var(--surface-soft); font-weight: 700; }
.markdown-body tr:nth-child(even) td { background: var(--surface-softer); }
.markdown-body img { display: block; max-width: 100%; height: auto; margin: 30px auto; border-radius: 12px; box-shadow: 0 8px 24px rgba(33,45,73,.10); }
.markdown-body .task-list-item { list-style: none; margin-left: -1.2em; }
.markdown-body input[type="checkbox"] { margin-right: 8px; accent-color: var(--brand); }
.markdown-body strong { color: var(--text-strong); }
.problem-nav { display: flex; flex-wrap: wrap; gap: 10px; margin: 10px 0 4px; }
.problem-nav-btn { display: inline-flex; align-items: center; padding: 9px 14px; color: var(--text); background: var(--surface); border: 1px solid var(--line); border-radius: 9px; font-weight: 650; text-decoration: none; }
.problem-nav-btn:hover { color: var(--brand); background: var(--brand-soft); border-color: color-mix(in srgb, var(--brand) 35%, var(--line)); text-decoration: none; }
.problem-nav-btn.primary { color: #fff; background: var(--brand); border-color: var(--brand); }
.problem-nav-btn.primary:hover { color: #fff; background: var(--brand-strong); border-color: var(--brand-strong); }
.markdown-body math { color: var(--text); font-family: "Cambria Math", "STIX Two Math", serif; }
.math-inline-wrap { position: relative; display: inline-block; max-width: 100%; min-width: 0; contain: layout paint; margin: 0 .06em; overflow-x: auto; overflow-y: hidden; vertical-align: -.12em; line-height: 1.1; }
.markdown-body .math-inline { display: inline math; min-width: max-content; font-size: 1em; vertical-align: baseline; }
.plain-math { white-space: nowrap; }
.plain-math sup, .plain-math sub { font-size: .72em; line-height: 0; }
.math-display-wrap { position: relative; display: block; width: 100%; max-width: 100%; min-width: 0; contain: layout paint inline-size; margin: 18px 0; padding: 12px 14px; overflow-x: auto; overflow-y: hidden; background: var(--surface-soft); border: 1px solid var(--line); border-radius: 10px; text-align: center; }
.markdown-body .math-display { display: block math; min-width: max-content; margin: 0 auto; font-size: 1.08em; }
.reader-visual { margin-top: 52px; }
.reader-visual > h2 { margin-top: 0; }
.reader-visual-frame {
  display: block;
  width: 100%;
  height: 640px;
  min-height: 360px;
  margin: 0;
  overflow: hidden;
  background: var(--surface-soft);
  border: 1px solid var(--line);
  border-radius: 14px;
}
.site-footer { padding: 22px 4px 0; color: var(--muted); text-align: center; font-size: 13px; }

.codehilite .k, .codehilite .kd, .codehilite .kn { color: #c792ea; }
.codehilite .kt, .codehilite .kc, .codehilite .kp { color: #c792ea; }
.codehilite .s, .codehilite .s1, .codehilite .s2 { color: #c3e88d; }
.codehilite .sb, .codehilite .sc, .codehilite .dl, .codehilite .sx { color: #c3e88d; }
.codehilite .c, .codehilite .c1, .codehilite .cm { color: #8b98b2; font-style: italic; }
.codehilite .n, .codehilite .na { color: #e9edf7; }
.codehilite .nf, .codehilite .nc { color: #82aaff; }
.codehilite .nn, .codehilite .nb, .codehilite .bp { color: #82aaff; }
.codehilite .mi, .codehilite .mf { color: #f78c6c; }
.codehilite .il, .codehilite .m, .codehilite .mb { color: #f78c6c; }
.codehilite .o { color: #89ddff; }
.codehilite .ow, .codehilite .p { color: #89ddff; }
.codehilite .nv, .codehilite .vc, .codehilite .vg, .codehilite .vi, .codehilite .nl { color: #ffcb6b; }
.codehilite .err { color: #ff7b72; }

/* ===== 移动端改进补丁（MOBILE-UX-REPORT Task 3-4） ===== */
body{overflow-x:clip}
/* 代码块换行开关（配合 SITE_JS 的按钮） */
.code-block pre.code-wrap{white-space:pre-wrap;word-break:break-all;overflow-x:hidden}
.code-toolbar{flex-wrap:wrap;gap:6px}

@media (max-width: 720px) {
  .site-shell { width: min(100% - 18px, 1040px); padding-top: 9px; }
  .site-topbar { align-items: flex-start; padding: 10px 11px; border-radius: 12px; }
  .site-nav { width: 100%; }
  .site-nav a { padding: 5px 7px; }
  .reader-card { padding: 22px 16px 34px; border-radius: 15px; }
  .markdown-body h1 { font-size: 30px; }
  .markdown-body h2 { margin-top: 38px; font-size: 24px; }
  .markdown-body h3 { font-size: 20px; }
  html{-webkit-text-size-adjust:100%}
  .markdown-body pre{font-size:12.5px;padding:16px 14px}
  .markdown-body pre:not(.code-nowrap){white-space:pre-wrap;word-break:break-all;overflow-x:hidden}
  .markdown-body table { min-width: 440px; font-size: 13px; }
  .markdown-body th, .markdown-body td { min-width: 84px; padding: 7px 8px; }
  .copy-code{padding:6px 10px;min-height:36px}
  .toc-box { margin-bottom: 28px; padding-inline: 14px; }
  .reader-visual { margin-top: 40px; }
  .reader-visual-frame { border-radius: 11px; }
}

@media (prefers-reduced-motion: reduce) {
  * { scroll-behavior: auto !important; transition: none !important; }
}

@media print {
  :root { color-scheme: light; --page-bg:#fff; --surface:#fff; --text:#111; --text-strong:#000; --muted:#444; --line:#ccc; }
  body { background:#fff; }
  .site-topbar, .site-footer, .toc-box, .copy-code, .reader-visual { display:none !important; }
  .site-shell, .reader-card, .markdown-body { width:100%; max-width:none; margin:0; padding:0; border:0; box-shadow:none; }
  .code-block { break-inside:avoid; }
}

"""

# =============================================================================
# SITE_JS：阅读页公共脚本（生成源常量，build() 原样写入 assets/site.js，页面以
# <script src="...site.js" defer> 加载）。功能按出现顺序：
#   ① fallbackCopy：navigator.clipboard 不可用（file:// 或旧浏览器）时的兜底复制
#      （隐藏 textarea + document.execCommand('copy')）；
#   ② 表格自动包装：<table> 外套 .table-wrap 容器，获得横向滚动与 aria-label；
#   ③ 代码块自动包装：<pre> 外套 .code-block，读 language-* 类生成语言标签与
#      “复制代码”按钮（异步 clipboard + fallbackCopy 兜底，1.4s 恢复文案）；
#   ④ 内嵌可视化高度握手（与 05-可视化 页内的 VISUAL_A11Y_SCRIPT 配对）：
#      子页 postMessage({type:'hot100:visual-height', height}) → 父页按
#      event.source（contentWindow）匹配对应 iframe 并调整高度（高度 <240 丢弃，
#      避免异常值）；父页在 iframe load 后回发 'hot100:measure' 让子页立刻上报。
#      为什么必须消息握手而非固定高度：内嵌面板高度随面板/模式切换动态变化，
#      固定高度会留白或被裁切。
# 注意：与 SITE_CSS 相同，本常量是纯文本生成源，禁止在字符串内部增删字符；
# 分段说明只能写在字符串之外（此处与下一个常量之间）。
# =============================================================================

SITE_JS = r"""
function fallbackCopy(text) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  let copied = false;
  try { copied = document.execCommand('copy'); } catch (_) { copied = false; }
  textarea.remove();
  return copied;
}

document.querySelectorAll('.markdown-body table').forEach((table) => {
  if (table.parentElement?.classList.contains('table-wrap')) return;
  const wrapper = document.createElement('div');
  wrapper.className = 'table-wrap';
  wrapper.setAttribute('role', 'region');
  wrapper.setAttribute('aria-label', '数据表，可横向滚动');
  table.parentNode.insertBefore(wrapper, table);
  wrapper.appendChild(table);
});

document.querySelectorAll('.markdown-body pre').forEach((pre) => {
  if (pre.parentElement?.classList.contains('code-block')) return;
  const wrapper = document.createElement('div');
  wrapper.className = 'code-block';
  const toolbar = document.createElement('div');
  toolbar.className = 'code-toolbar';
  const code = pre.querySelector('code');
  const languageClass = [...(code?.classList || [])].find((item) => item.startsWith('language-'));
  const language = languageClass ? languageClass.replace('language-', '') : 'code';
  const label = document.createElement('span');
  label.textContent = language.toUpperCase();
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'copy-code';
  button.textContent = '复制代码';
  button.setAttribute('aria-label', `复制${language === 'code' ? '' : language + ' '}代码`);
  button.addEventListener('click', async () => {
    const text = code?.innerText || pre.innerText;
    let copied = false;
    if (navigator.clipboard?.writeText) {
      try { await navigator.clipboard.writeText(text); copied = true; } catch (_) { copied = false; }
    }
    if (!copied) copied = fallbackCopy(text);
    button.textContent = copied ? '已复制' : '请手动复制';
    setTimeout(() => button.textContent = '复制代码', 1400);
  });
  const wrapButton = document.createElement('button');
  wrapButton.type = 'button';
  wrapButton.className = 'copy-code';
  wrapButton.textContent = '换行';
  wrapButton.setAttribute('aria-pressed', 'false');
  wrapButton.setAttribute('aria-label', '切换代码长行自动换行');
  wrapButton.addEventListener('click', () => {
    const nowrap = pre.classList.toggle('code-nowrap');
    const wrapped = pre.classList.toggle('code-wrap', !nowrap);
    wrapButton.setAttribute('aria-pressed', String(wrapped));
    wrapButton.textContent = wrapped ? '原样' : '换行';
  });
  toolbar.append(label, button, wrapButton);
  pre.parentNode.insertBefore(wrapper, pre);
  wrapper.append(toolbar, pre);
});

const readerVisualFrames = [...document.querySelectorAll('iframe.reader-visual-frame')];
window.addEventListener('message', (event) => {
  if (event.data?.type !== 'hot100:visual-height') return;
  const frame = readerVisualFrames.find((item) => item.contentWindow === event.source);
  const height = Math.ceil(Number(event.data.height));
  if (!frame || !Number.isFinite(height) || height < 240) return;
  const nextHeight = height + 2;
  if (Math.abs(frame.getBoundingClientRect().height - nextHeight) > 2) frame.style.height = `${nextHeight}px`;
});
readerVisualFrames.forEach((frame) => {
  frame.addEventListener('load', () => {
    frame.contentWindow?.postMessage({ type: 'hot100:measure' }, '*');
  });
});
"""

# VISUAL_EMBED_BOOTSTRAP：内嵌启动脚本（由 polish_visual 放在可视化页 <head>
# 顶部、无 defer，保证最早执行）。在页面其余脚本运行前读取 URL 查询串：
# ?embed=1 时给根元素加 hot100-embedded 类（CSS 中隐藏题头/讲解区/复杂度等
# 冗余块，只保留交互状态、图例与控制器），?panel 存在时再加 hot100-single-panel
# （隐藏面板切换页签）。提到 <head> 是为了在样式与首帧渲染前生效，避免
# “先完整显示再切换”的闪烁（FOUC）。
# 分工说明：bootstrap 只做静态类标记；运行时的参数驱动（点击对应页签、设置
# mode 下拉）交给 VISUAL_A11Y_SCRIPT（body 末尾的脚本）。

VISUAL_EMBED_BOOTSTRAP = r"""
<script id="hot100-embed-bootstrap">
(() => {
  const params = new URLSearchParams(location.search);
  if (params.get('embed') !== '1') return;
  document.documentElement.classList.add('hot100-embedded');
  if (params.has('panel')) document.documentElement.classList.add('hot100-single-panel');
})();
</script>
"""

# =============================================================================
# VISUAL_POLISH：可视化页统一样式层（以 <style id="hot100-polish"> 注入 <head>，
# 由 polish_visual 幂等地替换/插入）。目的：05-可视化 下各演示页由 build_hot100.py
# 独立生成、样式各异，这里统一为 Hot100 站点的品牌视觉并修复旧演示的通病：
#   ① 独立 --hot-* 变量名空间：不覆盖演示页自身变量（如 --brand），避免冲突；
#   ② 布局统一：容器限宽居中、按钮/输入/页签/面板卡片化、渐变高对比题头
#      （.panel-header 前景/背景色对独立定义，见 578 行附近注释）；
#   ③ 动画安全区：柱状图 .bars/.lane 加高并留白、canvas 舞台 min-height，
#      指针/数值标签不再被裁切；高亮改用边框/阴影而非放大覆盖相邻格子；
#   ④ 状态配色成对定义：前景色与底色一起改（如 .val-box.found 用 success 底 +
#      深色文字），避免只改背景导致文字消失（649 行附近注释）；
#   ⑤ html.hot100-embedded / hot100-single-panel：内嵌模式下隐藏讲解区块、
#      面板边框归零、可视化区占满 iframe 宽度——阅读页里只呈现“纯交互台”。
# 校验联动：check_hot100.py 断言 #hot100-polish 存在且含内嵌隐藏区块、题头
# 色对、复杂度色点等指定片段——本常量 + polish_visual 的注入逻辑是可视化页
# 通过校验的唯一途径。
# =============================================================================

VISUAL_POLISH = r"""
<style id="hot100-polish">
:root {
  color-scheme: light dark;
  --hot-bg: #f4f6fb;
  --hot-surface: #ffffff;
  --hot-surface-soft: #f8f9fd;
  --hot-text: #182235;
  --hot-muted: #66748a;
  --hot-line: #dfe4ee;
  --hot-brand: #5654d4;
  --hot-brand-soft: #eeedff;
  --hot-on-brand: #ffffff;
  --hot-hero-start: #314fc7;
  --hot-hero-end: #5546ca;
  --hot-hero-text: #ffffff;
  --hot-hero-muted: #e7ebff;
  --hot-success: #167a52;
  --hot-success-soft: #def7e9;
  --hot-warning: #934b00;
  --hot-warning-soft: #fff0d8;
  --hot-danger: #b52b3a;
  --hot-danger-soft: #ffe5e9;
  --hot-canvas-bg: #f8fafc;
  --hot-canvas-line: #c9d2df;
  --hot-shadow: 0 12px 34px rgba(33,45,73,.075);
}
@media (prefers-color-scheme: dark) {
  :root {
    --hot-bg: #0f131b;
    --hot-surface: #181e29;
    --hot-surface-soft: #141a24;
    --hot-text: #eaf0fa;
    --hot-muted: #a3afc2;
    --hot-line: #313b4c;
    --hot-brand: #b1afff;
    --hot-brand-soft: #292955;
    --hot-on-brand: #111521;
    --hot-hero-start: #263677;
    --hot-hero-end: #39256f;
    --hot-hero-text: #f8f9ff;
    --hot-hero-muted: #dfe4ff;
    --hot-success: #79d8a8;
    --hot-success-soft: #183c2d;
    --hot-warning: #ffc174;
    --hot-warning-soft: #47311b;
    --hot-danger: #ff9ba6;
    --hot-danger-soft: #47242b;
    /* 旧 Canvas 内部仍使用深色文字，因此绘图区保持柔和浅底以确保可读。 */
    --hot-canvas-bg: #edf2f7;
    --hot-canvas-line: #bac5d2;
    --hot-shadow: 0 16px 42px rgba(0,0,0,.22);
  }
}
* { box-sizing: border-box; }
html { min-width: 0; background: var(--hot-bg) !important; }
body {
  width: 100% !important;
  max-width: none !important;
  min-width: 0 !important;
  margin: 0 !important;
  padding: 0 0 34px !important;
  color: var(--hot-text) !important;
  background: radial-gradient(circle at 12% 0%, color-mix(in srgb,var(--hot-brand) 9%,transparent), transparent 34rem), var(--hot-bg) !important;
}
:focus-visible { outline: 3px solid color-mix(in srgb,var(--hot-brand) 48%,transparent) !important; outline-offset: 3px; }
.hot100-topnav {
  width: min(100% - 24px, 1400px);
  margin: 12px auto 16px;
  padding: 10px 13px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  color: var(--hot-muted);
  background: color-mix(in srgb,var(--hot-surface) 94%,transparent);
  border: 1px solid var(--hot-line);
  border-radius: 13px;
  box-shadow: var(--hot-shadow);
  font: 14px/1.45 system-ui, "Microsoft YaHei", sans-serif;
}
.hot100-topnav .hot100-links { display: flex; gap: 7px; flex-wrap: wrap; }
.hot100-topnav a { padding: 6px 9px; color: var(--hot-brand); background: var(--hot-brand-soft); border-radius: 7px; text-decoration: none; }
.hot100-topnav a:hover { filter: brightness(.97); }
.hot100-topnav strong { min-width: 0; color: var(--hot-text); overflow-wrap: anywhere; }
body > .container, body > .shell, body > main, body > .wrap {
  width: min(100% - 24px, 1400px) !important;
  max-width: 1400px !important;
  margin-left: auto !important;
  margin-right: auto !important;
  padding-bottom: 44px;
}
body > h1, body > h2, body > h3, body > .info, body > .desc, body > .btn-group {
  width: min(100% - 24px, 1400px);
  margin-left: auto !important;
  margin-right: auto !important;
}
canvas, svg, img { max-width: 100% !important; }
button, input, select, textarea { max-width: 100%; }
body h1 {
  margin-top: 0;
  color: var(--hot-text) !important;
  font-size: clamp(28px, 3vw, 40px);
  line-height: 1.2;
  letter-spacing: -.02em;
}
body h2 { color: var(--hot-text); line-height: 1.3; }
body h3 { color: var(--hot-text); line-height: 1.4; }
button, input, select, textarea { font: inherit; }
button {
  min-height: 36px;
  padding: 8px 12px;
  color: var(--hot-text);
  background: var(--hot-surface);
  border: 1px solid var(--hot-line) !important;
  border-radius: 9px !important;
  box-shadow: 0 2px 8px rgba(33,45,73,.04);
  transition: transform .16s ease, border-color .16s ease, background-color .16s ease, box-shadow .16s ease;
}
button:hover:not(:disabled) {
  border-color: color-mix(in srgb,var(--hot-brand) 42%,var(--hot-line)) !important;
  background: color-mix(in srgb,var(--hot-brand-soft) 58%,var(--hot-surface));
  box-shadow: 0 5px 14px rgba(33,45,73,.08);
  transform: translateY(-1px);
}
button:active:not(:disabled) { transform: translateY(0); }
button:disabled { opacity: .52; cursor: not-allowed; box-shadow: none; }
button.primary, button.btn-primary, button.btn-apply, .primary, .btn-primary, .btn-apply {
  color: var(--hot-on-brand) !important;
  background: var(--hot-brand) !important;
  border-color: var(--hot-brand) !important;
}
input:not([type="range"]):not([type="checkbox"]):not([type="radio"]), select, textarea {
  min-height: 36px;
  padding: 7px 10px !important;
  color: var(--hot-text) !important;
  background: var(--hot-surface) !important;
  border: 1px solid var(--hot-line) !important;
  border-radius: 8px !important;
}
input[type="range"] { accent-color: var(--hot-brand); }
.controls, .toolbar, .input-row, .preset-row, .sort-tabs, .ds-tabs, .op-bar, .btn-group, .legend { flex-wrap: wrap !important; }
.controls, .toolbar, .input-row, .preset-row, .op-bar, .btn-group { gap: 9px !important; }
.sort-tabs, .ds-tabs {
  display: flex;
  gap: 7px !important;
  margin-block: 18px !important;
  padding: 4px !important;
  background: color-mix(in srgb,var(--hot-surface) 84%,transparent) !important;
  border: 1px solid var(--hot-line) !important;
  border-radius: 13px !important;
  box-shadow: 0 6px 20px rgba(33,45,73,.045);
}
.sort-tab, .ds-tab, .code-tab, .preset-btn {
  padding: 8px 11px !important;
  color: var(--hot-muted) !important;
  background: transparent !important;
  border: 1px solid transparent !important;
  border-radius: 9px !important;
  cursor: pointer;
  transition: color .16s ease, background-color .16s ease, border-color .16s ease;
}
.sort-tab:hover, .ds-tab:hover, .code-tab:hover, .preset-btn:hover {
  color: var(--hot-brand) !important;
  background: var(--hot-brand-soft) !important;
}
.sort-tab.active, .ds-tab.active, .code-tab.active, .preset-btn.active {
  color: var(--hot-brand) !important;
  background: var(--hot-brand-soft) !important;
  border-color: color-mix(in srgb,var(--hot-brand) 28%,var(--hot-line)) !important;
  box-shadow: 0 3px 10px rgba(33,45,73,.065);
}
.container, .shell, main, .wrap, .content, .layout, .code-section, .vis-section, .content > *, .layout > *, .wrap > * { min-width: 0 !important; }
.vis-canvas-wrap, .panel, .box, .table-responsive, .code-scroll, .notes-section { max-width: 100%; }
.table-responsive, .code-scroll, .notes-section { overflow: auto; }
.panel { overflow: hidden !important; }
.box { overflow: visible; }
.panel, .box {
  color: var(--hot-text);
  background-color: var(--hot-surface) !important;
  border: 1px solid var(--hot-line) !important;
  border-radius: 15px !important;
  box-shadow: var(--hot-shadow) !important;
}
.code-section { border-color: var(--hot-line) !important; }
.vis-section { background-color: var(--hot-surface-soft) !important; }
.vis-msg, .target-info, .algo-desc, .desc, .status, .log {
  color: var(--hot-text) !important;
  border-color: var(--hot-line) !important;
}
.vis-msg, .target-info, .algo-desc, .desc {
  background: color-mix(in srgb,var(--hot-brand-soft) 48%,var(--hot-surface)) !important;
}
.legend {
  color: var(--hot-muted) !important;
  background: var(--hot-surface) !important;
  border-color: var(--hot-line) !important;
}
.step-info, .size-info, .sub, .muted { color: var(--hot-muted) !important; }
/* 题头必须使用独立的前景/背景色对；不能继承正文的灰色文字。 */
.panel-header {
  color: var(--hot-hero-text) !important;
  background: linear-gradient(135deg,var(--hot-hero-start),var(--hot-hero-end)) !important;
}
.panel-header h1, .panel-header h2, .panel-header h3 {
  color: inherit !important;
}
.panel-header .sub, .panel-header p, .panel-header .info {
  max-width: 88ch;
  color: var(--hot-hero-muted) !important;
  opacity: 1 !important;
  line-height: 1.65;
  white-space: normal !important;
  overflow-wrap: anywhere;
}
/* 复杂度徽标中的色点不是第二层徽标，避免白块套白块。 */
.complexity .badge-time, .complexity .badge-space {
  display: inline !important;
  margin-right: 6px;
  padding: 0 !important;
  background: transparent !important;
  border: 0 !important;
  border-radius: 0 !important;
}
/* 动画安全区：标签、指针和高亮不再贴边或被相邻区域裁掉。 */
.lane { min-height: 220px !important; padding: 36px 6px !important; row-gap: 52px !important; overflow: visible !important; }
.lane .label.top { bottom: 66px !important; }
.lane .label.bottom { top: 66px !important; }
.bars { height: 300px !important; padding-top: 38px !important; padding-bottom: 34px !important; overflow: visible !important; }
.bars .col { min-width: 0; }
.bars .idx, .bars .answer { z-index: 2; }
.hot100-bar-stage {
  min-height: 300px !important;
  padding: 32px 12px 32px !important;
  overflow-x: auto !important;
  overflow-y: clip !important;
  scroll-padding-inline: 12px;
}
.hot100-bar-stage .bar-wrapper { z-index: 2; }
.hot100-bar-stage .water-rect { z-index: 1; }
.hot100-native-canvas {
  min-height: clamp(400px, 48vh, 540px) !important;
  padding: 0 !important;
  overflow: clip !important;
  isolation: isolate;
  background: var(--hot-canvas-bg) !important;
  border: 1px solid var(--hot-canvas-line);
}
.hot100-native-canvas > canvas { display: block; max-width: 100% !important; }
/* 高亮使用边框/阴影，不再放大后覆盖相邻格子。 */
.curr, .board-cell.current, .val-box.current, .val-box.found, .set-num.checking { transform: none !important; }
.curr, .board-cell.current { box-shadow: inset 0 0 0 2px color-mix(in srgb,var(--hot-brand) 58%,transparent) !important; }
.bar-label, .idx { color: var(--hot-muted) !important; }
pre { max-width: 100%; overflow: auto !important; }
table { max-width: 100%; }

@media (prefers-color-scheme: dark) {
  body > .container > h1, body > .shell > h1, body > main > h1, body > h1, body > h2 { color: var(--hot-text) !important; }
  .panel, .box, .code-section, .vis-section, .notes-section, .input-section, .top-tags,
  .controls, .complexity, .complexity-bar, .code-header, .code-tab, .legend, .algo-desc,
  .op-bar, .map-container, .formula-box, .desc, .false, .token, .status, .log {
    color: var(--hot-text) !important;
    background-color: var(--hot-surface) !important;
    border-color: var(--hot-line) !important;
  }
  .vis-canvas-wrap, .table-responsive { background-color: var(--hot-surface-soft) !important; }
  .sub, .muted, .info, .row-label, .step-info, .size-info { color: var(--hot-muted) !important; }
  input, select, textarea { color: var(--hot-text) !important; background: var(--hot-surface) !important; border-color: var(--hot-line) !important; }
  button:not(.primary):not(.btn-primary):not(.active) { color: var(--hot-text); background-color: var(--hot-surface); border-color: var(--hot-line); }
}
/* 状态配色：前景与底色成对定义，避免只改背景造成文字消失。 */
.code-line.highlight-line {
  color: var(--hot-text) !important;
  background: var(--hot-warning-soft) !important;
  box-shadow: inset 3px 0 var(--hot-warning);
}
.code-line.highlight-line .lineno { color: var(--hot-warning) !important; }
.code .active {
  display: inline-block;
  margin-inline: -4px;
  padding-inline: 4px;
  color: var(--hot-warning) !important;
  background: var(--hot-warning-soft) !important;
  border-radius: 4px;
}
.token, .pair, .node, .dp-cell, .cell:not(.wall) {
  color: var(--hot-text);
  background-color: var(--hot-surface-soft);
  border-color: color-mix(in srgb,var(--hot-text) 17%,var(--hot-line)) !important;
}
.header { color: var(--hot-muted) !important; background: transparent !important; border-color: transparent !important; }
.filled, .cell.in, .frontier {
  color: var(--hot-text) !important;
  background: var(--hot-brand-soft) !important;
  border-color: color-mix(in srgb,var(--hot-brand) 58%,var(--hot-line)) !important;
}
.true, .map-pair.found, .op-badge.found, .board-cell.matched, .queen-cell.safe, .cell.visited, .source {
  color: var(--hot-success) !important;
  background: var(--hot-success-soft) !important;
  border-color: color-mix(in srgb,var(--hot-success) 66%,var(--hot-line)) !important;
}
.false {
  color: var(--hot-muted) !important;
  background: var(--hot-surface-soft) !important;
  border-color: var(--hot-line) !important;
}
.curr, .board-cell.current, .val-tag.active, .str-token.current, .set-num.checking, .cell.current, .col.current .bar {
  color: var(--hot-warning) !important;
  background: var(--hot-warning-soft) !important;
  border-color: var(--hot-warning) !important;
  outline-color: color-mix(in srgb,var(--hot-warning) 56%,transparent) !important;
}
.val-box.current {
  color: var(--hot-on-brand) !important;
  background: var(--hot-warning) !important;
  border-color: color-mix(in srgb,var(--hot-warning) 78%,#000) !important;
}
.val-box.found {
  color: var(--hot-on-brand) !important;
  background: var(--hot-success) !important;
  border-color: color-mix(in srgb,var(--hot-success) 78%,#000) !important;
}
.board-cell.visited, .queen-cell.conflict, .set-num.active-check {
  color: var(--hot-danger) !important;
  background: var(--hot-danger-soft) !important;
  border-color: color-mix(in srgb,var(--hot-danger) 68%,var(--hot-line)) !important;
}
.wall { color: #fff !important; background: #465066 !important; border-color: #465066 !important; }
.saved { outline-color: var(--hot-warning) !important; background: var(--hot-warning-soft) !important; }
.hot100-native-canvas { background: var(--hot-canvas-bg) !important; }
/* 题解页内嵌模式：只保留交互状态、必要图例和控制器。 */
html.hot100-embedded { background: transparent !important; }
html.hot100-embedded body {
  padding: 12px !important;
  overflow-x: hidden !important;
  background: transparent !important;
  font-size: 15px;
}
html.hot100-embedded .hot100-topnav,
html.hot100-embedded body > h1,
html.hot100-embedded body > h2,
html.hot100-embedded body > .info,
html.hot100-embedded .container > h1,
html.hot100-embedded .shell > a:first-child,
html.hot100-embedded .shell > h1,
html.hot100-embedded .shell > h1 + .muted,
html.hot100-embedded .shell > h1 + div:not(.toolbar),
html.hot100-embedded .panel-header,
html.hot100-embedded .top-tags,
html.hot100-embedded .notes-section,
html.hot100-embedded .input-section,
html.hot100-embedded .complexity,
html.hot100-embedded .complexity-bar,
html.hot100-embedded .code-section,
html.hot100-embedded .algo-desc,
html.hot100-embedded .status > .code {
  display: none !important;
}
html.hot100-single-panel .container > .sort-tabs,
html.hot100-single-panel .container > .ds-tabs {
  display: none !important;
}
html.hot100-embedded body > .container,
html.hot100-embedded body > .shell,
html.hot100-embedded body > main,
html.hot100-embedded body > .wrap {
  width: 100% !important;
  max-width: none !important;
  margin: 0 !important;
  padding: 0 !important;
}
html.hot100-embedded .content { min-height: 0 !important; }
html.hot100-embedded .vis-section { width: 100% !important; flex: 1 1 100% !important; }
html.hot100-embedded .panel {
  border: 0 !important;
  border-radius: 0 !important;
  box-shadow: none !important;
}
html.hot100-embedded .sort-tabs,
html.hot100-embedded .ds-tabs { margin-top: 0 !important; }
@media (max-width: 760px) {
  .hot100-topnav { width: min(100% - 16px, 1400px); margin-top: 8px; padding: 9px 10px; align-items: flex-start; }
  .hot100-topnav .hot100-links { width: 100%; }
  body > .container, body > .shell, body > main, body > .wrap { width: min(100% - 12px, 1400px) !important; padding-left: 4px !important; padding-right: 4px !important; }
  body > h1, body > h2, body > h3, body > .info, body > .desc, body > .btn-group { width: min(100% - 20px, 1400px); }
  .content, .layout, .wrap { flex-direction: column !important; grid-template-columns: minmax(0,1fr) !important; }
  .box, .panel { width: 100% !important; min-width: 0 !important; }
  .code-section { width: 100% !important; border-right: 0 !important; }
  .vis-canvas-wrap:not(.hot100-native-canvas):not(.hot100-bar-stage) { padding-left: 10px !important; padding-right: 10px !important; }
  .hot100-native-canvas { min-height: 360px !important; }
  .hot100-bar-stage { min-height: 280px !important; padding: 30px 10px 30px !important; }
  .bar { min-width: 4px !important; }
  .code-line, pre, pre code { white-space: pre !important; }
  .step-info { width: 100%; margin-left: 0 !important; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; scroll-behavior: auto !important; } }
</style>
"""

# VISUAL_A11Y_SCRIPT：可视化页的可访问性增强 + 内嵌模式驱动（注入 </body> 前，
# 由 polish_visual 幂等地替换/插入）。两半职责：
#   ① a11y（无嵌入参数也执行）：tab 类控件补 role=button/tabindex/aria-pressed，
#      MutationObserver 同步 active 状态，支持 Enter/空格键触发；所有 button 显式
#      补 type=button 防误触发表单；无标签表单控件按 placeholder/name/id 兜底补
#      aria-label；canvas 标为 role=img 并取所在面板标题生成 aria-label，容器打上
#      hot100-native-canvas（被 VISUAL_POLISH 用作安全区样式钩子）；柱状舞台按是否
#      含 .bar-wrapper 打 hot100-bar-stage；日志/状态区补 aria-live=polite。
#   ② 内嵌驱动（embed=1 时）：按 ?panel 点击对应 .sort-tab/.ds-tab 页签、
#      按 ?mode 设置 #mode 下拉并派发 change（驱动可视化重绘）；随后由
#      ResizeObserver/MutationObserver/load/fonts.ready/message 多路触发
#      reportHeight：取 body 各可见子元素 bottom 最大值向上取整，postMessage
#      {type:'hot100:visual-height', height} 给父页——被阅读页 SITE_JS 的
#      message 监听者接收并调整 iframe 高度。
# 与 VISUAL_EMBED_BOOTSTRAP 的分工：bootstrap 只做静态类标记（head 顶部），
# 本脚本做交互级切换与持续测量（body 末尾），两者缺一不可。

VISUAL_A11Y_SCRIPT = r"""
<script id="hot100-a11y">
(() => {
  const tabLike = document.querySelectorAll('.sort-tab, .ds-tab, .code-tab, .preset-btn');
  const syncState = (item) => item.setAttribute('aria-pressed', item.classList.contains('active') ? 'true' : 'false');
  tabLike.forEach((item) => {
    if (!item.hasAttribute('role')) item.setAttribute('role', 'button');
    if (!item.hasAttribute('tabindex')) item.setAttribute('tabindex', '0');
    syncState(item);
    item.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); item.click(); }
    });
    new MutationObserver(() => syncState(item)).observe(item, { attributes: true, attributeFilter: ['class'] });
  });
  document.querySelectorAll('button').forEach((button) => { if (!button.type) button.type = 'button'; });
  document.querySelectorAll('input, select, textarea').forEach((control) => {
    if (control.matches('[aria-label], [aria-labelledby]')) return;
    if (control.id && document.querySelector(`label[for="${CSS.escape(control.id)}"]`)) return;
    if (control.closest('label')) return;
    const fallback = control.getAttribute('placeholder') || control.getAttribute('name') || control.id || (control.type === 'range' ? '播放速度' : '参数');
    control.setAttribute('aria-label', fallback);
  });
  document.querySelectorAll('canvas').forEach((canvas) => {
    if (!canvas.hasAttribute('role')) canvas.setAttribute('role', 'img');
    if (!canvas.hasAttribute('aria-label')) {
      const heading = canvas.closest('.panel')?.querySelector('h2, h3')?.textContent?.trim();
      canvas.setAttribute('aria-label', `${heading || document.title} 的算法状态图`);
    }
    canvas.parentElement?.classList.add('hot100-native-canvas');
  });
  document.querySelectorAll('.vis-canvas-wrap').forEach((stage) => {
    if (stage.querySelector('.bar-wrapper')) stage.classList.add('hot100-bar-stage');
  });
  document.querySelectorAll('.log, .status, .vis-msg, .desc').forEach((node) => {
    if (!node.hasAttribute('aria-live')) node.setAttribute('aria-live', 'polite');
  });
  const embedParams = new URLSearchParams(location.search);
  if (embedParams.get('embed') === '1') {
    const panelIndex = embedParams.get('panel');
    if (panelIndex !== null) {
      const panelTab = [...document.querySelectorAll('.sort-tab, .ds-tab')]
        .find((item) => item.dataset.idx === panelIndex);
      panelTab?.click();
    }
    const mode = embedParams.get('mode');
    const modeSelect = document.getElementById('mode');
    if (mode && modeSelect && [...modeSelect.options].some((option) => option.value === mode)) {
      modeSelect.value = mode;
      modeSelect.dispatchEvent(new Event('change', { bubbles: true }));
    }
    const reportHeight = () => requestAnimationFrame(() => {
      const bottoms = [...document.body.children]
        .filter((item) => getComputedStyle(item).display !== 'none')
        .map((item) => item.getBoundingClientRect().bottom);
      const height = Math.max(320, Math.ceil(Math.max(0, ...bottoms) + 12));
      parent.postMessage({ type: 'hot100:visual-height', height }, '*');
    });
    new ResizeObserver(reportHeight).observe(document.body);
    new MutationObserver(reportHeight).observe(document.body, { childList: true, subtree: true, attributes: true });
    window.addEventListener('message', (event) => {
      if (event.data?.type === 'hot100:measure') reportHeight();
    });
    window.addEventListener('load', reportHeight, { once: true });
    document.fonts?.ready.then(reportHeight);
    reportHeight();
  }
})();
</script>
"""


# 源 Markdown → 输出 HTML 的路径映射（全站唯一权威映射；链接改写、build()、
# check 的校验都依赖它）：
#   - 根级 README.md → guide.html：README 是“内容型总目录”，而 index.html 是
#     build_hot100.py 生成的数据驱动学习面板，职责不同，故 README 不进 index；
#     这也解释了 update_dashboard / polish_visual 里所有把 README 入口改成
#     guide.html 的替换操作；
#   - MAINTENANCE.md → maintenance.html：维护说明页；
#   - 其余一律 source.with_suffix(".html")：同目录同名换后缀。
# 每条 .md 因此都有确定的 .html 目标，rewrite_markdown_links 才能把链接换算成
# 相对路径，check_hot100.py 才能断言“生成的 HTML 不再指向 .md”。
def output_for_markdown(source: Path) -> Path:
    if source == ROOT / "README.md":
        return ROOT / "guide.html"
    if source == ROOT / "MAINTENANCE.md":
        return ROOT / "maintenance.html"
    return source.with_suffix(".html")


# 计算“从 from_path 所在目录”到 to_path 的相对 URL（统一正斜杠，兼容 Windows
# 的 os.sep）。页面内所有 href/src——assets、相邻阅读页、可视化文件、顶栏导航
# 目标——都用它生成相对路径。全站因此可在 file:// 或任意子目录下整体离线打开，
# 不依赖站点根路径；check_hot100.py 判定“失效本地链接”时也按同一换算基准解析。
def web_rel(from_path: Path, to_path: Path) -> str:
    return os.path.relpath(to_path, from_path.parent).replace(os.sep, "/")


# 公式转 MathML 的两张白名单表（MathMLParser.command 查表用）：
#   MATH_COMMANDS：\命令 → Unicode 字符的映射，覆盖本项目笔记实际用到的符号
#     子集（× · ⊕ → ≤ ≥ ⇒、希腊字母、求和/无穷/不等号等）；formula_label 也
#     复用键集合把 \命令还原成可读符号，生成公式的 aria-label。
#   MATH_FUNCTIONS：当作“正体函数名”原样输出的命令（非斜体变量），贴近数学
#     排印习惯。
# 未支持子集（设计取舍，不在表内，一律“容错降级”继续渲染、不抛错）：
#   \begin{cases} 等非 matrix/bmatrix 环境没有专用处理，降级为圆括号包裹的表格；
#   \left/\right 被静默忽略（不生成渐大定界符）；\binom、\over、\limits、
#   自定义宏、\text 内再嵌 LaTeX 均不支持；未知命令按正体文本输出。
#   上下限式排印不成立：\sum_{i=1}^{n} 的 i=1 与 n 只会贴成 ∑ 的上下标，
#   不会落到符号正下方/正上方（极限式）。白名单方案比通用转换器更可预测、
#   肉眼可校对，且全程离线完成。
MATH_COMMANDS = {
    "times": "×", "cdot": "·", "oplus": "⊕", "rightarrow": "→", "to": "→",
    "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "implies": "⇒",
    "alpha": "α", "Sigma": "Σ", "sum": "∑", "infty": "∞", "neq": "≠",
}
MATH_FUNCTIONS = {"log", "min", "max", "sin", "cos", "tan"}


# MathMLParser：手写递归下降解析器，把轻量 LaTeX 子集字符串编译成浏览器原生
# <math> 标记。三层文法对应三个方法：
#   parse()（顶层）  ：把剩余输入切成一个表达式序列——空白转 <mspace> 间距、
#                       ^/_ 把前一原子包成 <msup>/<msub>，其余逐原子累积；
#   atom()（单原子） ：读一个 {分组} / 命令 / 数字 / 字母串 / 省略号 / 符号；
#   command()（\命令）：查 MATH_COMMANDS / MATH_FUNCTIONS 表，或递归构造
#                       \frac \sqrt \text \begin{env} 等结构命令。
# 关键设计：每个分组/参数都用 MathMLParser(原文).parse() 独立递归解析——
# 上下文无关、天然支持任意嵌套；词法状态只有 self.pos 游标，raw_group() 负责
# 按花括号配平取出分组原文。产物是原生 <math>，Chrome/Safari/Firefox 均内建
# 支持，因此全站公式渲染不依赖任何在线库，满足完全离线约束。
class MathMLParser:
    """把本项目使用到的轻量 LaTeX 子集转换为浏览器原生 MathML。"""

    # 解析器状态：source 为去首尾空白后的输入串；pos 为当前游标。递归构造
    # 子解析器时传的就是“分组/参数原文”，各组互不共享状态。
    def __init__(self, source: str):
        self.source = source.strip()
        self.pos = 0

    # “读取并消费一个花括号分组”的底层原语：跳过空白后若当前字符不是 { 返回
    # 空串；否则从 { 起按配平深度扫描到匹配的 }，返回分组内部原文（不含花括号），
    # 并把游标推进到 } 之后。depth 计数支持 {a{b}c} 这类嵌套分组；若输入不配平
    # （缺闭括号）则吞掉剩余串——保证解析永不越界崩溃，属容错设计。
    def raw_group(self) -> str:
        while self.pos < len(self.source) and self.source[self.pos].isspace():
            self.pos += 1
        if self.pos >= len(self.source) or self.source[self.pos] != "{":
            return ""
        self.pos += 1
        start = self.pos
        depth = 1
        while self.pos < len(self.source) and depth:
            if self.source[self.pos] == "{":
                depth += 1
            elif self.source[self.pos] == "}":
                depth -= 1
                if depth == 0:
                    value = self.source[start:self.pos]
                    self.pos += 1
                    return value
            self.pos += 1
        return self.source[start:]

    # 处理 \ 开头的命令：命令名取最长字母串；无字母则取单个字符（如 \| 这类
    # 单字符命令）。分支依次为：
    #   \left/\right     —— 静默丢弃（不支持“尺寸放大的渐大定界符”子集）；
    #   , ; : 空格 quad qqquad —— 生成 <mspace> 水平间距（宽度按表取值）；
    #   \frac \sqrt \text —— 结构命令：对参数分组递归 parse 后包成 mfrac/msqrt/
    #                         mtext（mtext 内容做 html.escape）；
    #   \begin{env}..\end{env} —— 按 \\ 分行、& 分列生成 <mtable>；bmatrix 用
    #                         [] 定界，其余环境（含不支持的 cases）降级用 ()；
    #   MATH_COMMANDS     —— 查表输出符号（alpha/Sigma 用 <mi>，其余 <mo>）；
    #   MATH_FUNCTIONS    —— 正体函数名 <mi mathvariant="normal">；
    #   & | 与未知命令    —— 转义为普通正体 <mi>（容错降级，渲染不中断）。
    def command(self) -> str:
        self.pos += 1
        if self.pos >= len(self.source):
            return ""
        match = re.match(r"[A-Za-z]+", self.source[self.pos:])
        if match:
            name = match.group(0)
            self.pos += len(name)
        else:
            name = self.source[self.pos]
            self.pos += 1

        if name in {"left", "right"}:
            return ""
        if name in {",", ";", ":", " ", "quad", "qquad"}:
            widths = {"quad": "1em", "qquad": "2em", ";": ".28em", ":": ".22em"}
            return f'<mspace width="{widths.get(name, ".17em")}"/>'
        if name == "frac":
            numerator = MathMLParser(self.raw_group()).parse()
            denominator = MathMLParser(self.raw_group()).parse()
            return f"<mfrac><mrow>{numerator}</mrow><mrow>{denominator}</mrow></mfrac>"
        if name == "sqrt":
            return f"<msqrt><mrow>{MathMLParser(self.raw_group()).parse()}</mrow></msqrt>"
        if name == "text":
            return f"<mtext>{html.escape(self.raw_group())}</mtext>"
        if name == "begin":
            environment = self.raw_group()
            end_token = rf"\end{{{environment}}}"
            end = self.source.find(end_token, self.pos)
            if end >= 0:
                content = self.source[self.pos:end]
                self.pos = end + len(end_token)
                rows = re.split(r"\\\\", content)
                table_rows = []
                for row in rows:
                    cells = "".join(f"<mtd><mrow>{MathMLParser(cell).parse()}</mrow></mtd>" for cell in row.split("&"))
                    table_rows.append(f"<mtr>{cells}</mtr>")
                open_char, close_char = ("[", "]") if "bmatrix" in environment else ("(", ")")
                return f"<mrow><mo>{open_char}</mo><mtable>{''.join(table_rows)}</mtable><mo>{close_char}</mo></mrow>"
        if name in MATH_COMMANDS:
            symbol = MATH_COMMANDS[name]
            tag = "mi" if name in {"alpha", "Sigma"} else "mo"
            return f"<{tag}>{symbol}</{tag}>"
        if name in MATH_FUNCTIONS:
            return f'<mi mathvariant="normal">{name}</mi>'
        if name in {"&", "|"}:
            return f"<mo>{html.escape(name)}</mo>"
        return f'<mi mathvariant="normal">{html.escape(name)}</mi>'

    # 读取一个“原子”（单个可被 ^/_ 整体当作上下标参数的单元）：
    #   {..}分组 → <mrow>（递归解析）；\ → command()；数字 → <mn>；
    #   字母串 → <mi>，其中 O/PreSum/Sum/dp/target/capacity/numRows/rowIndex 等
    #   多字符“变量”刻意用 mathvariant="normal"（正体），与题目笔记的记法一致；
    #   "..." → 省略号 <mo>…；其余单字符 → <mo>（*→×，'→′ 两处替换）。
    def atom(self) -> str:
        while self.pos < len(self.source) and self.source[self.pos].isspace():
            self.pos += 1
        if self.pos >= len(self.source):
            return ""
        char = self.source[self.pos]
        if char == "{":
            return f"<mrow>{MathMLParser(self.raw_group()).parse()}</mrow>"
        if char == "\\":
            return self.command()
        if char.isdigit():
            match = re.match(r"\d+(?:\.\d+)?", self.source[self.pos:])
            assert match
            self.pos += len(match.group(0))
            return f"<mn>{match.group(0)}</mn>"
        if char.isalpha():
            match = re.match(r"[A-Za-z]+", self.source[self.pos:])
            if match is None:
                self.pos += 1
                return f'<mi mathvariant="normal">{html.escape(char)}</mi>'
            token = match.group(0)
            self.pos += len(token)
            variant = ' mathvariant="normal"' if token in {"O", "PreSum", "Sum", "dp", "target", "capacity", "numRows", "rowIndex"} else ""
            return f"<mi{variant}>{token}</mi>"
        if self.source.startswith("...", self.pos):
            self.pos += 3
            return "<mo>…</mo>"
        self.pos += 1
        replacements = {"*": "×", "'": "′"}
        return f"<mo>{html.escape(replacements.get(char, char))}</mo>"

    # 顶层循环：把输入序列编译为 MathML 片段串。行为：
    #   遇 } 提前终止——分组的闭合交给外层 raw_group，这里只解析到组边界；
    #   空白 → 追加 .18em <mspace>（若上一项已是 mspace 则跳过，避免间距叠加）；
    #   ^/_ → 以 atom() 读参数、以 items.pop() 取前一原子为基底，包装成
    #         <msup>/<msub>（无基底时用空 <mrow/> 兜底）；
    #   其余 → 累积 atom() 的产物。返回拼接后的完整片段，由 math_html 包进
    #   <math class="math-inline|math-display"> 并外套滚动容器。
    def parse(self) -> str:
        items: list[str] = []
        while self.pos < len(self.source):
            if self.source[self.pos] == "}":
                break
            if self.source[self.pos].isspace():
                self.pos += 1
                if items and (not items[-1].startswith("<mspace")):
                    items.append('<mspace width=".18em"/>')
                continue
            if self.source[self.pos] in {"^", "_"}:
                operator = self.source[self.pos]
                self.pos += 1
                argument = self.atom()
                base = items.pop() if items else "<mrow/>"
                tag = "msup" if operator == "^" else "msub"
                items.append(f"<{tag}>{base}{argument}</{tag}>")
                continue
            value = self.atom()
            if value:
                items.append(value)
        return "".join(items)


# 把公式源码浓缩成一行“人类可读标签”：削掉 \left/\right、把 MATH_COMMANDS 的
# 命令还原成符号、剥掉 \text/\begin/\end/\frac/\sqrt 等结构命令、去花括号与
# 转义空格、压缩连续空白。产物经 html.escape 后作为 <math> 的 aria-label——
# MathML 对不同读屏器的支持参差，显式文本标签是稳定的无障碍兜底
# （仅辅助读屏用，不参与视觉渲染）。
def formula_label(source: str) -> str:
    label = re.sub(r"\\(?:left|right)\b", "", source)
    for command, symbol in MATH_COMMANDS.items():
        label = re.sub(rf"\\{re.escape(command)}\b", symbol, label)
    label = re.sub(r"\\(?:text|begin|end|quad|qquad|frac|sqrt)\b", "", label)
    label = label.replace("{", "").replace("}", "").replace(r"\,", " ").replace(r"\ ", " ").replace("\\", "")
    return re.sub(r"\s+", " ", label).strip()


def is_plain_math(source: str) -> bool:
    """简单行内公式直接输出 HTML，避免 MathML 基线错位。"""
    text = source.strip()
    if not text:
        return False
    if any(token in text for token in ("\\frac", "\\sqrt", "\\text", "\\begin", "\\sum", "\\int", "\\left", "\\right")):
        return False
    cleaned = re.sub(r"\\(?:times|cdot|pm|le|ge|infty|log|dots|ldots)\b", "", text)
    return not re.search(r"[^A-Za-z0-9\s()\[\]{}+*/=.,:;<>≤≥×÷±∞^_\-]", cleaned)


def plain_math_html(source: str) -> str:
    text = source.strip()
    for command, symbol in (
        ("\\times", "×"),
        ("\\cdot", "·"),
        ("\\pm", "±"),
        ("\\le", "≤"),
        ("\\ge", "≥"),
        ("\\infty", "∞"),
        ("\\log", "log"),
        ("\\dots", "…"),
        ("\\ldots", "…"),
    ):
        text = re.sub(rf"\{command}\b", symbol, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\^\{([^}]+)\}", r"<sup>\1</sup>", text)
    text = re.sub(r"\^([A-Za-z0-9]+)", r"<sup>\1</sup>", text)
    text = re.sub(r"_\{([^}]+)\}", r"<sub>\1</sub>", text)
    text = re.sub(r"_([A-Za-z0-9]+)", r"<sub>\1</sub>", text)
    text = text.replace("{", "").replace("}", "")
    return f'<span class="plain-math" aria-label="{html.escape(source.strip(), quote=True)}">{text}</span>'


# 公式装配层：把 MathML 片段包成完整 <math>（inline/display 两种模式，display
# 带 display="block"）并加 aria-label；再外套 <span class="math-*-wrap"> 滚动
# 容器——公式过长时在卡片内小范围横向滚动而不撑破布局（对应 SITE_CSS 里
# .math-inline-wrap / .math-display-wrap 的样式钩子）。display 模式还带浅色底框，
# 视觉上区分行内公式与独立公式。
def math_html(source: str, display: bool = False) -> str:
    if not display and is_plain_math(source):
        return plain_math_html(source)
    mathml = MathMLParser(source).parse()
    label = html.escape(formula_label(source), quote=True)
    mode = ' display="block"' if display else ""
    markup = f'<math class="math-{"display" if display else "inline"}"{mode} aria-label="{label}"><mrow>{mathml}</mrow></math>'
    wrapper = "math-display-wrap" if display else "math-inline-wrap"
    return f'<span class="{wrapper}">{markup}</span>'


# 公式预处理（在 Markdown → HTML 之前，对整份源文本逐行执行）：
#   ① 围栏状态机：``` 或 ~~~ 开始/结束围栏（只认同种闭合标记），围栏内整行
#      原样放行——保证代码块里的 $、$$（Java/伪代码）绝不参与公式替换；
#   ② 行内代码剥离：把 `...` 用 split 切出为奇数位片段，只对偶数位“正文片段”
#      做 $ 替换，行内代码里的 $ 不受影响；
#   ③ 正文片段内先按 $$..$$（display，不跨行）再按 $..$（inline，前置 \ 转义
#      可豁免）替换为 math_html 产物；顺带把源稿中可能残留的空格实体（&#x20;）
#      还原为普通空格——否则经 Markdown 转义后会原样出现在 HTML，check_hot100
#      会把这种“空格实体残留”报为错误。
# 为什么在 Markdown 转换前做：替换后 <math> 内容是干净的标记，不会再经
# markdown 扩展二次转义或参与代码高亮；math_html 内部已自行 html.escape。
# 复用点：build_library.py 直接 import 本函数渲染学习书架的数学笔记，保证全站
# 公式输出完全一致（本文件中少有的被外部模块引用的函数之一）。
def render_math_in_markdown(text: str) -> str:
    """只处理代码围栏和行内代码之外的数学标记，保证 Java 代码中的 $ 不受影响。"""
    output: list[str] = []
    in_fence = False
    fence = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
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
        parts = re.split(r"(`+[^`]*?`+)", line)
        for index in range(0, len(parts), 2):
            part = parts[index].replace("&amp;#x20;", " ").replace("&#x20;", " ")
            part = re.sub(r"\$\$([^$]+?)\$\$", lambda match: math_html(match.group(1), display=True), part)
            part = re.sub(r"(?<!\\)\$([^$\r\n]+?)\$", lambda match: math_html(match.group(1)), part)
            parts[index] = part
        output.append("".join(parts))
    return "\n".join(output)


# 链接改写：把 Markdown 正文里的相对 .md 链接统一改写为 .html 链接（这是
# “.md → .html”发布的关键一步）。正则只匹配 markdown 链接目标（(…) 内以 .md
# 结尾、可带 #fragment，忽略大小写）；http(s):// 等绝对地址原样放行。
# 数据流（replace 闭包内）：raw_path 以当前源文件所在目录为基准 resolve 成
# 绝对路径 → 经 output_for_markdown 换算为目标 HTML（README.md 特判指向
# index.html——从任意页面点“完整使用指南”都回到学习面板）→ 用 web_rel 从
# “当前输出页所在目录”算相对 URL，fragment 原样保留。相对化使整站可整体
# 拷贝到任意目录离线打开；check_hot100 会反向断言阅读页里再没有 .md 链接。
def rewrite_markdown_links(text: str, source: Path, output: Path) -> str:
    pattern = re.compile(r"(?<=\()([^)]+?\.md)(#[^)]*)?(?=\))", re.I)

    # 单条匹配的替换逻辑（详见外层注释）。两点设计意图：
    # ① resolve() 后不在此处检查目标是否存在——坏链接统一交给 check_hot100.py
    #    的“失效本地链接”扫描兜底，而不是在构建期抛异常中止整站；
    # ② README.md 特判到 index.html，保证根级指南入口在任何页面深度下都稳定。
    def replace(match: re.Match[str]) -> str:
        raw_path = match.group(1)
        fragment = match.group(2) or ""
        if re.match(r"^[a-z]+://", raw_path, re.I):
            return match.group(0)
        target_md = (source.parent / raw_path).resolve()
        # 注意：Path 相等比较对盘符/分隔符敏感，务必两边都 resolve 后比较，
        # 否则 README.md 特判会漏命中（产物错误地写成 README.html）。
        target_html = (
            ROOT / "index.html"
            if target_md == (ROOT / "README.md").resolve()
            else output_for_markdown(target_md)
        )
        return web_rel(output, target_html) + fragment

    return pattern.sub(replace, text)


# 面包屑：取源文件相对 ROOT 的目录层级（去掉文件名），用 " / " 连接；根级
# 文件（README 等）返回“完整使用指南”。渲染进阅读页的 .page-kicker 行，让
# 读者随时知道自己处于目录结构的哪一层；不设链接，纯位置提示。
def breadcrumb(source: Path) -> str:
    rel = source.relative_to(ROOT)
    if len(rel.parts) <= 1:
        return "完整使用指南"
    return " / ".join(rel.parts[:-1])


# 题解内嵌可视化装配（仅 03-题解 下的题解页会命中 VISUAL_EMBEDS 绑定表）：
#   1) 用本页相对 ROOT 的正斜杠路径作 key 查表；未命中返回空串——该题解页
#      底部不出现演示区；
#   2) 命中后校验绑定文件存在于 05-可视化：缺失直接抛 FileNotFoundError，
#      把“配置指向不存在的演示”这类问题暴露在构建期，而不是生成死链；
#   3) 拼 iframe 的 src = web_rel 相对路径 + 'embed=1&panel=…&mode=…'，由子页的
#      bootstrap / a11y 脚本消费；iframe 开 loading="lazy"（长阅读页延迟加载）
#      与 scrolling="no"（防 iframe 内部 + 父页的双层滚动条——高度由
#      SITE_JS ↔ VISUAL_A11Y_SCRIPT 的消息握手动态适配）。
# 产物结构 <section class="reader-visual"> 被 check_hot100 用作校验锚点：
# 绑定表内的题解必须含 embed=1 的 iframe，表外的题解不得出现该 section。
def render_visual_embed(source: Path, output: Path, title: str) -> str:
    key = source.relative_to(ROOT).as_posix()
    spec = VISUAL_EMBEDS.get(key)
    if spec is None:
        return ""
    filename, options = spec
    visual_path = ROOT / "books" / "hot100" / "05-可视化" / filename
    if not visual_path.exists():
        raise FileNotFoundError(f"题解绑定的可视化不存在：{visual_path}")
    query = ["embed=1", *(f"{name}={value}" for name, value in options.items())]
    src = f"{web_rel(output, visual_path)}?{'&'.join(query)}"
    return f"""
        <section class="reader-visual" aria-labelledby="interactive-demo-title">
          <h2 id="interactive-demo-title">交互演示</h2>
          <iframe class="reader-visual-frame" src="{html.escape(src)}" title="{html.escape(title)}的交互演示" loading="lazy" scrolling="no"></iframe>
        </section>
    """


# =============================================================================
# render_markdown：单篇 Markdown → 完整离线阅读页的核心渲染函数
# （build() 对每个源文件调用一次）。完整数据流：
#   1. output_for_markdown 定输出路径；utf-8-sig 读入（容忍 BOM）；
#   2. 预处理一——删旧式“· [打开可视化] / [打开本专题演示](…) ”入口行：那是
#      旧信息架构的独立演示链接，视觉演示已统一改为题解页底部内嵌 iframe
#      （V2 信息架构：03-题解 内的演示只以内嵌形式存在）；
#   3. 预处理二——rewrite_markdown_links（.md→.html 链接改写）；
#      预处理三——render_math_in_markdown（公式→原生 MathML）；
#   4. python-markdown 转换：extensions=extra（表格/围栏/任务列表等）、
#      sane_lists（列表不混入段落）、toc（按 toc_depth=2-4 提取目录）、
#      codehilite（Pygments 高亮，css_class=codehilite，与 SITE_CSS 配色对应）；
#   5. 后处理——力扣原题链接补 target=_blank + rel="noopener noreferrer"
#      （新标签打开且防 tabnabbing 反向控制新页面）；
#   6. 结构切分——从转换结果剥出首个 <h1> 作 page_heading（页题不进目录），
#      其余为正文；无 h1 时用源文件名兜底；
#   7. 资源与导航定位——site.css/site.js 相对 href 拼 ?v=ASSET_VERSION（防缓存），
#      顶栏四个导航目标：学习书架 / 学习路线 / 模式地图 / 复习清单 + 根入口；
#   8. 组装页面骨架（在本函数内联完成，不依赖模板文件）：
#      <header class="site-topbar">（品牌 + <nav class="site-nav"> 导航注入）→
#      <main class="reader-card"> 内 <article class="markdown-body">：
#       .page-kicker 面包屑 → page_heading → <details class="toc-box">本页目录
#       （可折叠）→ 正文 → 可视化内嵌 → <footer>，<script defer> 载入 site.js；
#   9. utf-8 写回输出文件。
# 目录/层级约定：h1=页题（每阅读页恰好一个，且出现在目录之前——check 对此
# 有断言）；h2-h4 进 TOC，h5+ 不进。骨架与样式/脚本常量强耦合，故直接在此
# 拼装，保持单文件自包含、便于整体离线分发。
# =============================================================================
def render_markdown(source: Path) -> None:
    output = output_for_markdown(source)
    raw = source.read_text(encoding="utf-8-sig")
    # 独立演示链接属于旧信息架构；网页中统一在题解末尾内嵌交互组件。
    raw = re.sub(r"\s*·\s*\[打开(?:本专题)?可视化\]\([^)]*\)", "", raw)
    raw = re.sub(r"\s*·\s*\[打开本专题演示\]\([^)]*\)", "", raw)
    raw = rewrite_markdown_links(raw, source, output)
    # 运行期已对 maintenance.html 返回 404（开发者内容不对外），
    # 渲染页里指向它的链接降级为纯文本，避免站内死链。
    raw = re.sub(r'\[([^\]]+)\]\((?:MAINTENANCE\.html|maintenance\.html)\)', r"", raw)
    raw = render_math_in_markdown(raw)
    md = markdown.Markdown(
        extensions=["extra", "sane_lists", "toc", "codehilite"],
        extension_configs={
            "toc": {"toc_depth": "2-4", "permalink": False},
            "codehilite": {"guess_lang": False, "css_class": "codehilite"},
        },
    )
    body = md.convert(raw)
    # 题解页底部按钮：从正文提取，统一放到交互动画之后。
    bottom_nav = ""
    nav_match = re.search(r"<!--bottom-nav-->(.*?)<!--/bottom-nav-->", body, re.S)
    if nav_match:
        bottom_nav = nav_match.group(1).strip()
        body = body[: nav_match.start()] + body[nav_match.end() :]
    # 力扣原题链接在新标签页打开；rel 防 target=_blank 反向 tabnabbing。
    body = re.sub(
        r'<a href="(https://leetcode\.cn/problems/[^"]+)"(?![^>]*target=)',
        r'<a href="\1" target="_blank" rel="noopener noreferrer"',
        body,
    )
    toc = md.toc
    heading_match = re.match(r"(?is)\s*(<h1\b.*?</h1>)\s*(.*)", body)
    if heading_match:
        page_heading, body = heading_match.groups()
    else:
        page_heading = f"<h1>{html.escape(source.stem)}</h1>"
    css_href = web_rel(output, ROOT / "assets" / "site.css") + f"?v={ASSET_VERSION}"
    js_href = web_rel(output, ROOT / "assets" / "site.js") + f"?v={ASSET_VERSION}"
    root_href = web_rel(output, ROOT / "index.html")
    route_href = web_rel(output, ROOT / "books" / "hot100" / "00-总览" / "01-学习路线.html")
    map_href = web_rel(output, ROOT / "books" / "hot100" / "00-总览" / "02-算法模式地图.html")
    checklist_href = web_rel(output, ROOT / "books" / "hot100" / "00-总览" / "03-复习清单.html")
    lc_href = web_rel(output, ROOT / "pages" / "leetcode-connect.html")
    title_match = re.search(r"(?m)^#\s+(.+)$", raw)
    title = title_match.group(1).strip() if title_match else source.stem
    visual_embed = render_visual_embed(source, output, title)
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{html.escape(title)} · Hot 100</title>
  <link rel="stylesheet" href="{html.escape(css_href)}">
</head>
<body>
  <a class="skip-link" href="#main-content">跳到正文</a>
  <div class="site-shell">
    <header class="site-topbar">
      <a class="site-brand" href="{html.escape(root_href)}">Hot 100 深度学习库</a>
      <nav class="site-nav" aria-label="主导航">
        <a href="{html.escape(web_rel(output, ROOT / 'library' / 'index.html'))}">学习书架</a>
        <a href="{html.escape(route_href)}">学习路线</a>
        <a href="{html.escape(map_href)}">模式地图</a>
        <a href="{html.escape(checklist_href)}">复习清单</a>
        <a class="lc-button" href="{html.escape(lc_href)}">力扣连接</a>
      </nav>
    </header>
    <main id="main-content" class="reader-card">
      <article class="markdown-body">
        <div class="page-kicker">{html.escape(breadcrumb(source))}</div>
        {page_heading}
        <details class="toc-box">
          <summary>本页目录</summary>
          {toc}
        </details>
        {body}
        {visual_embed}
        {bottom_nav}
      </article>
    </main>
    <footer class="site-footer">Interview Forge · 本地离线阅读</footer>
  </div>
  <script src="{html.escape(js_href)}" defer></script>
</body>
</html>
"""
    output.write_text(page, encoding="utf-8")


# =============================================================================
# polish_visual：05-可视化 演示页的“统一样式注入”（对 build_hot100.py 生成的
# 旧式独立演示页做增量补丁，绝不重写它们的交互 JS）。所有注入都是幂等的——
# 每个注入物先查“是否已有标记”：已有则整段替换为最新常量内容（重复构建收敛，
# 旧版注入内容顺带升级），没有则插入到固定锚点：
#   <head> 后    —— viewport / color-scheme meta（缺省才补，移动端与深浅色适配）；
#   <head> 内    —— VISUAL_EMBED_BOOTSTRAP（内嵌静态类标记，最早执行）；
#   <head> 尾部  —— VISUAL_POLISH（统一样式层，#hot100-polish，替换/追加）；
#   <body> 后    —— nav 导航条（class="hot100-topnav" data-hot100-nav：页面标题
#                    + 返回学习面板/可视化中心两条链接，替换/追加）；
#   </body> 前   —— VISUAL_A11Y_SCRIPT（a11y + 内嵌驱动的运行脚本，替换/追加）。
# 另有两处源码级修复：
#   a) 柱状演示的 canvas 尺寸改为“内容盒尺寸”（clientWidth/clientHeight 减去
#      padding）——旧实现按含内边距的尺寸计算柱高，指针与数值标签会超出内容区
#      被裁切（check 对旧代码串有专门断言）；
#   b) <a href="../README.md"> 改为 ../guide.html——与 output_for_markdown 的
#      映射保持一致，演示页里的旧指南链接不再落到 Markdown 源稿。
# 校验联动：check_hot100.py 对每个可视化页断言 data-hot100-nav / #hot100-polish /
# #hot100-a11y / #hot100-embed-bootstrap 必须存在，并检查内嵌隐藏区块、
# canvas 安全区等指定片段——本函数是可视化页通过校验的唯一途径。
# =============================================================================
def polish_visual(path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig")
    title_match = re.search(r"(?is)<title>\s*(.*?)\s*</title>", text)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else path.stem
    nav = f'<nav class="hot100-topnav" data-hot100-nav aria-label="学习导航"><strong>{html.escape(title)}</strong><span class="hot100-links"><a href="../../../index.html">学习面板</a><a href="index.html">可视化中心</a></span></nav>'
    if not re.search(r"(?is)<meta\b[^>]*name=[\"']viewport[\"']", text):
        text = re.sub(r"(?is)(<head[^>]*>)", r'\1\n<meta name="viewport" content="width=device-width,initial-scale=1">', text, count=1)
    if not re.search(r"(?is)<meta\b[^>]*name=[\"']color-scheme[\"']", text):
        text = re.sub(r"(?is)(<head[^>]*>)", r'\1\n<meta name="color-scheme" content="light dark">', text, count=1)
    if 'id="hot100-embed-bootstrap"' in text:
        text = re.sub(r"(?is)<script id=\"hot100-embed-bootstrap\">.*?</script>", VISUAL_EMBED_BOOTSTRAP.strip(), text, count=1)
    else:
        text = re.sub(r"(?is)(<head[^>]*>)", r"\1\n" + VISUAL_EMBED_BOOTSTRAP.strip(), text, count=1)
    # 旧柱状演示使用含 padding 的 clientWidth/clientHeight 计算柱高，
    # 指针与数值标签会因此超出内容区。改为使用真实内容盒尺寸。
    text = re.sub(
        r"const W = canvas\.clientWidth \|\| 400;\s*const H = canvas\.clientHeight \|\| 240;",
        """const _hotCanvasStyle = getComputedStyle(canvas);
    const _hotPadX = (parseFloat(_hotCanvasStyle.paddingLeft) || 0) + (parseFloat(_hotCanvasStyle.paddingRight) || 0);
    const _hotPadY = (parseFloat(_hotCanvasStyle.paddingTop) || 0) + (parseFloat(_hotCanvasStyle.paddingBottom) || 0);
    const W = Math.max(240, canvas.clientWidth - _hotPadX);
    const H = Math.max(180, canvas.clientHeight - _hotPadY);""",
        text,
    )
    if 'id="hot100-polish"' in text:
        text = re.sub(r"(?is)<style id=\"hot100-polish\">.*?</style>", VISUAL_POLISH.strip(), text, count=1)
    else:
        text = text.replace("</head>", VISUAL_POLISH + "\n</head>", 1)
    if "data-hot100-nav" in text:
        text = re.sub(r"(?is)<nav class=\"hot100-topnav\" data-hot100-nav>.*?</nav>", nav, text, count=1)
        text = re.sub(r"(?is)<nav class=\"hot100-topnav\" data-hot100-nav\s+aria-label=\"[^\"]*\">.*?</nav>", nav, text, count=1)
    else:
        text = re.sub(r"(?is)(<body[^>]*>)", r"\1\n" + nav, text, count=1)
    if 'id="hot100-a11y"' in text:
        text = re.sub(r"(?is)<script id=\"hot100-a11y\">.*?</script>", VISUAL_A11Y_SCRIPT.strip(), text, count=1)
    else:
        text = re.sub(r"(?is)</body>", VISUAL_A11Y_SCRIPT + "\n</body>", text, count=1)
    text = text.replace('href="../README.md"', 'href="../guide.html"')
    path.write_text(text, encoding="utf-8")


# 学习面板（index.html，由 build_hot100.py 生成、含本地学习记录交互 JS）的
# 增量修补（“面板更新”职能）：
#   1. 题卡数据 note 字段 .md→.html（re.sub 只改 JSON 字符串里的文件后缀）：
#      题卡的“打开题解”由此指向阅读页而非 Markdown 源稿——与
#      output_for_markdown 的映射一致，check 会顺带扫描断言；
#   2. “打开 Markdown 总目录”入口替换为目标 guide.html 的“完整使用指南”
#      （与 README.md 特判规则一致）；
#   3. dashboard-nav 快捷导航条：缺失则连同配套 <style> 一起插入
#      （</header> 后插 nav、</style> 前插样式）；已存在则整段替换——
#      幂等，且导航链接始终跟随最新入口集；
#   4. 删除旧式“可视化中心”入口（演示改内嵌后，面板不再需要独立链接，
#      check 也断言面板不再出现 05-可视化 链接）。
# 设计意图：面板是动态应用（SQLite API / PWA / uPlot 等运行时代码），本函数
# 只做静态入口修补，绝不触碰面板的运行时代码——“入口更新”与“数据逻辑”解耦。
def update_dashboard() -> None:
    path = ROOT / "index.html"
    text = path.read_text(encoding="utf-8-sig")
    text = re.sub(r'("note"\s*:\s*"[^"]+)\.md"', r'\1.html"', text)
    text = text.replace('href="README.md">打开 Markdown 总目录</a>', 'href="guide.html">完整使用指南</a>')
    quick = '<nav class="dashboard-nav"><a href="library/index.html">学习书架</a><a href="books/hot100/00-总览/01-学习路线.html">学习路线</a><a href="books/hot100/00-总览/02-算法模式地图.html">模式地图</a><a href="books/hot100/00-总览/03-复习清单.html">复习清单</a><a href="books/hot100/04-模板/01-Hot100算法模板.html">算法模板</a><a href="pages/history.html">学习记录</a><a class="lc-button" href="pages/leetcode-connect.html">力扣连接</a></nav>'
    if 'class="dashboard-nav"' not in text:
        text = text.replace('</header>\n<div class="bar"', '</header>\n' + quick + '\n<div class="bar"', 1)
        text = text.replace('</style>', '.dashboard-nav{display:flex;gap:9px;flex-wrap:wrap;margin:18px 0 8px}.dashboard-nav a{padding:7px 11px;background:var(--panel);border:1px solid var(--line);border-radius:9px}.dashboard-nav a:hover{background:var(--soft);text-decoration:none}.dashboard-nav a.lc-button{background:var(--brand);border-color:var(--brand);color:#fff;font-weight:650}.dashboard-nav a.lc-button:hover{background:var(--brand-strong);color:#fff}@media(max-width:680px){.dashboard-nav{gap:7px}.dashboard-nav a{padding:6px 9px}}\n</style>', 1)
    else:
        text = re.sub(r'<nav class="dashboard-nav"[^>]*>.*?</nav>', quick, text, count=1)
        if '.dashboard-nav a.lc-button' not in text:
            text = text.replace(
                '.dashboard-nav a:hover{background:var(--soft);text-decoration:none}',
                '.dashboard-nav a:hover{background:var(--soft);text-decoration:none}.dashboard-nav a.lc-button{background:var(--brand);border-color:var(--brand);color:#fff;font-weight:650}.dashboard-nav a.lc-button:hover{background:var(--brand-strong);color:#fff}',
                1,
            )
    text = text.replace(' · <a href="books/hot100/05-可视化/index.html">可视化中心</a>', '')
    path.write_text(text, encoding="utf-8")


# 错题本页（00-总览/05-错题本.html）：完全自包含的静态页面（样式/脚本内联，
# 无外部依赖），数据在运行时从学习记录服务（tools/study_server.py 的
# /api/weaklist）拉取：按 category 计数归一化画“薄弱题专题分布”条形图 +
# “薄弱清单”表格（题号/题名/核心方法/轮次/最近复习/标记时间）+ “移除薄弱”
# 按钮（POST /api/mark 后重新 load）。因此构建期不需要数据库；页面在
# “启动学习站.cmd”启动的本地服务下才有数据。check 只断言页面存在且引用
# api/weaklist。
def render_notebook() -> None:
    """生成 00-总览/05-错题本.html：薄弱题专题分布 + 清单 + 移除操作（数据来自 /api/weaklist）。"""
    page = '''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>错题本 · Interview Forge</title>
<style>
:root{color-scheme:light dark;--bg:#f3f5fa;--panel:#fff;--soft:#f7f8fc;--text:#172033;--muted:#647188;--line:#dce2ec;--brand:#5755d4;--brand-soft:#eeedff;--danger:#c1363e;--danger-soft:#fdecec;--success:#13764b;--success-soft:#e7f6ee}
@media(prefers-color-scheme:dark){:root{--bg:#0f131b;--panel:#181e29;--soft:#141a24;--text:#edf2fb;--muted:#a7b2c4;--line:#313b4c;--brand:#b2b0ff;--brand-soft:#292955;--danger:#ff969d;--danger-soft:#47242b;--success:#79d8a8;--success-soft:#17382b}}
*{box-sizing:border-box}
body{margin:0;color:var(--text);background:var(--bg);font:15px/1.7 system-ui,"Microsoft YaHei",sans-serif}
.shell{width:min(100% - 32px,1080px);margin:auto;padding:26px 0 56px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:20px}
.top a{color:var(--brand);text-decoration:none}
h1{margin:0 0 6px;font-size:30px}
.sub{color:var(--muted);margin-bottom:18px}
.card{border:1px solid var(--line);border-radius:14px;background:var(--panel);padding:16px;margin-bottom:18px}
.card h2{margin:0 0 12px;font-size:18px}
.bars{display:grid;gap:8px}
.bar-row{display:grid;grid-template-columns:minmax(110px,1fr) minmax(120px,2fr) 36px;gap:10px;align-items:center;font-size:13px}
.bar-track{height:10px;border-radius:999px;background:var(--soft);overflow:hidden}
.bar-fill{height:100%;background:linear-gradient(90deg,var(--brand),var(--danger));border-radius:999px}
.bar-num{color:var(--muted);font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;margin-top:4px}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--muted);font-size:13px;font-weight:650}
td a{color:var(--brand)}
.pill{padding:2px 8px;border-radius:999px;font-size:12px;color:var(--danger);background:var(--danger-soft)}
.remove{border:1px solid var(--line);border-radius:7px;padding:3px 8px;color:var(--muted);background:transparent;cursor:pointer;font-size:12px}
.empty{padding:20px 6px;color:var(--muted)}
.notice{padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--soft);color:var(--muted);font-size:13px;margin-bottom:18px}
@media(max-width:620px){th,td{padding:7px 6px;font-size:13px}.bar-row{grid-template-columns:90px 1fr 30px}}
@media print{.top,.remove,.notice{display:none}body{background:#fff}}
</style>
</head>
<body>
<main class="shell">
  <div class="top"><a href="../../../index.html">← 学习面板</a><a href="../../../library/index.html">学习书架</a><a href="03-复习清单.html">复习清单</a></div>
  <h1>错题本</h1>
  <div class="sub">在面板题卡上标记“薄弱”后自动汇总到这里；可一键打印或导出薄弱清单。</div>
  <div id="notice" class="notice">正在读取学习记录…（请通过“启动学习站.cmd”访问）</div>
  <section class="card" aria-labelledby="distTitle"><h2 id="distTitle">薄弱题专题分布</h2><div id="bars" class="bars"></div></section>
  <section class="card" aria-labelledby="listTitle"><h2 id="listTitle">薄弱清单</h2>
    <table><thead><tr><th>题号</th><th>题名</th><th>核心方法</th><th>轮次</th><th>最近复习</th><th>标记时间</th><th>操作</th></tr></thead><tbody id="rows"></tbody></table>
  </section>
</main>
<script>
function esc(v){return String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function fmt(v){if(!v)return '—';return String(v).slice(0,10)}
async function load(){
  try{
    const r=await fetch('/api/weaklist',{cache:'no-store'});
    if(!r.ok)throw new Error();
    const data=await r.json();
    document.getElementById('notice').hidden=true;
    const bars=document.getElementById('bars');
    const counts={};
    data.items.forEach(item=>{counts[item.category]=(counts[item.category]||0)+1});
    const max=Math.max(1,...Object.values(counts));
    bars.innerHTML=Object.entries(counts).map(([name,n])=>`<div class="bar-row"><span>${esc(name)}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.round(n/max*100)}%"></div></div><span class="bar-num">${n}</span></div>`).join('')||'<div class="empty">还没有薄弱题。</div>';
    document.getElementById('rows').innerHTML=data.items.map(item=>`<tr><td>${item.id}</td><td><a href="${esc(item.note)}">${esc(item.title)}</a></td><td>${esc(item.method)}</td><td>${item.rounds}</td><td>${fmt(item.last_completed_at)}</td><td>${fmt(item.marked_at)}</td><td><button class="remove" type="button" data-remove="${item.id}">移除薄弱</button></td></tr>`).join('');
    document.querySelectorAll('[data-remove]').forEach(btn=>btn.addEventListener('click',async()=>{
      try{
        await fetch('/api/mark',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target_type:'problem',target_id:btn.dataset.remove,mark:''})});
        load();
      }catch(_){}
    }));
  }catch(_){
    document.getElementById('notice').textContent='无法读取学习记录，请通过“启动学习站.cmd”访问。';
  }
}
load();
</script>
</body>
</html>
'''
    target = ROOT / "books" / "hot100" / "00-总览" / "05-错题本.html"
    target.write_text(page, encoding="utf-8")


# =============================================================================
# build()：本生成器主流程（`python build_html_site.py` 的入口）。执行顺序：
#   1. 公共资源：确保 assets/ 存在；把 SITE_CSS / SITE_JS 常量原样
#      （strip 去首尾空行 + 补结尾换行）写入 assets/site.css / assets/site.js——
#      “assets 与生成器常量一致”就建立在这条写入路径上，所以常量区一个字符
#      都不能动；另从 tools/vendor 复制 uPlot 离线图表库到 assets（与书架
#      mermaid 的 vendor→dist 模式相同；源缺失直接抛错，避免生成半成品站）。
#   2. 阅读页：收集 sources = 根级 README/MAINTENANCE/QA-REPORT
#      + CONTENT_DIRS 各目录递归 .md（排序保证输出稳定、可重复构建），
#      逐篇 render_markdown。
#   3. 面板与错题本：update_dashboard（note 字段转向 .html + 快捷导航 +
#      guide.html 入口）、render_notebook（错题本页）。
#   4. 可视化润色：对 05-可视化/ 下所有 .html 执行 polish_visual。
#   5. 打印统计（阅读页数 / 润色页数）。
# 前置依赖：本脚本只“消费”build_hot100.py（面板/演示页/题解与专题 Markdown
# 源）和 build_library.py（书架章节页）的产物，三者须按
# build_hot100 → build_library → build_html_site 的顺序执行；
# 之后运行 check_hot100.py 做全站回归校验（errors=0 才算闭环）。
# =============================================================================
def build() -> None:
    assets = ROOT / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "site.css").write_text(SITE_CSS.strip() + "\n", encoding="utf-8")
    (assets / "site.js").write_text(SITE_JS.strip() + "\n", encoding="utf-8")
    # 离线图表库 uPlot：与 mermaid 同模式，构建时从 tools/vendor 复制。
    vendor = Path(__file__).resolve().parent / "vendor"
    for name in ("uplot.min.js", "uplot.min.css"):
        source = vendor / name
        if not source.exists():
            raise FileNotFoundError(f"缺少 uPlot 源文件：{source}")
        shutil.copy2(source, assets / name)

    sources = [ROOT / "README.md", ROOT / "MAINTENANCE.md", ROOT / "docs" / "QA-REPORT.md"]
    for folder in CONTENT_DIRS:
        sources.extend(sorted((ROOT / folder).rglob("*.md")))
    # 增量 + 并行渲染阅读页：源内容哈希未变且输出存在 → 跳过；需要重建的
    # 文件交给进程池并行渲染，全部完成后再写回缓存（聚合产物始终全量）。
    cache = build_cache.load_cache(ROOT)
    cache = build_cache.invalidate_on_tool_change(cache, Path(__file__).resolve())
    pending: list[tuple[Path, Path, str, str]] = []
    for source in sources:
        rel = source.relative_to(ROOT).as_posix()
        output = output_for_markdown(source)
        rel_out = output.relative_to(ROOT).as_posix()
        sha = build_cache.file_sha256(source)
        if not build_cache.needs_rebuild(cache, "html_page:" + rel, sha, [rel_out], ROOT):
            continue
        pending.append((source, output, rel, sha))
    if pending:
        with ProcessPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
            list(pool.map(_render_markdown_worker, [(str(src), str(out)) for src, out, _, _ in pending]))
        for source, output, rel, sha in pending:
            build_cache.mark_built(cache, "html_page:" + rel, sha, [output.relative_to(ROOT).as_posix()])
    build_cache.save_cache(ROOT, cache)
    if pending:
        print(f"HTML pages rebuilt: {len(pending)} (of {len(sources)})")

    update_dashboard()
    render_notebook()
    for visual in sorted((ROOT / "books" / "hot100" / "05-可视化").glob("*.html")):
        polish_visual(visual)

    print(f"HTML reading pages: {len(sources)}; visual pages polished: {len(list((ROOT / 'books' / 'hot100' / '05-可视化').glob('*.html')))}")


# 入口：直接运行时执行全量构建（python build_html_site.py）；被其它模块
# import 时（如 check_hot100.py 引入 VISUAL_EMBEDS、build_library.py 引入
# render_math_in_markdown）不会触发构建。
if __name__ == "__main__":
    build()
