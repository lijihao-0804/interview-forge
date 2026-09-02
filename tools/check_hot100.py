# ============================================================================
# check_hot100.py —— 学习站发布前全站回归校验脚本（研究向注释）
#
# 【脚本定位：生成→校验 闭环的“校验端”】
#   学习站的页面不是手写的，而是由构建脚本生成：
#     - build_hot100.py   ：按 PROBLEMS（题目清单）与 LEETCODE_SLUGS（slug 登记表）
#                           生成 03-题解/ 的题目页 Markdown 与 HTML；
#     - build_html_site.py：生成 05-可视化/ 页面、index.html 学习面板与 PWA 外壳，
#                           并导出 VISUAL_EMBEDS——“题解页路径 → 应内嵌演示资源”绑定表；
#     - build_library.py  ：把 library_catalog.LIBRARY_MODULES 里的源笔记渲染成
#                           library/ 下的书架课程页。
#   本脚本对应“校验端”：跑完生成脚本之后，用它确认产物满足发布约定。工作流是
#   “改源码 → 重新生成 → 运行本脚本 → errors=0 才允许发布”，因此它必须紧跟
#   生成脚本执行，不能单独运行或跳过。
#
# 【执行方式】
#   在 学习站 根目录执行：python tools/check_hot100.py
#   （脚本内部 `from build_hot100 import ...` 直接引用生成脚本模块并读取仓库文件，
#    所以必须在项目根目录运行，不能把单文件挪走执行。）
#   发布前先做语法自检：python -m py_compile tools/check_hot100.py
#
# 【errors 数组用途与退出码语义】
#   - errors  ：发布阻断项列表。任何一条成立都说明产物不合格，必须修复后重新生成；
#   - warnings：软告警列表。只提示环境缺失（如未安装 Node.js），不阻断发布。
#   脚本末尾 sys.exit(1 if errors else 0)：errors 非空 → 退出码 1（CI 判失败），
#   否则 → 退出码 0（通过）。warnings 不参与退出码，只被打印出来知会。
# ============================================================================
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup
from build_html_site import VISUAL_EMBEDS
from build_hot100 import LEETCODE_SLUGS, PROBLEMS
from library_catalog import LIBRARY_MODULES


ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []
warnings: list[str] = []


# ============================================================================
# ① 题目页 Markdown 检查（03-题解/）
#   逐页做 5 组静态断言：①H1 题号标题；②代码围栏闭合性；③必需章节；④整理痕迹
#   （旧标题/emoji/施工文案）；⑤题号集合与 PROBLEMS 清单一致性。本段之后
#   还有独立的力扣 slug 链接断言（见“力扣原题链接覆盖”注释段）。任何一条
#   失败都会登记一条对应文案的 error。
# ============================================================================
problem_files = sorted((ROOT / "books" / "hot100" / "03-题解").rglob("*.md"))
ids: list[int] = []
for path in problem_files:
    # 标题行约定：页面里必须是 “# 编号.” 形式的 H1（(?m) 表示按行匹配，
    # ^#\s+(\d+)\.\s+ 要求“井号+空格+数字+点”）。题号同时是目录锚点与后续
    # “题号集合对齐检查”的数据来源，缺它则页面无法被目录正常索引。
    text = path.read_text(encoding="utf-8-sig")
    # 注：utf-8-sig 会剥掉 BOM，避免 BOM 混进标题首字符导致正则失配的假阴性。
    match = re.search(r"(?m)^#\s+(\d+)\.\s+", text)
    if not match:
        errors.append(f"题目页缺少题号标题：{path}")
    else:
        ids.append(int(match.group(1)))
    if text.count("```") % 2:
        errors.append(f"代码围栏不成对：{path}")
    if "本题正文待补充" in text:
        errors.append(f"题目没有正文：{path}")
    # ---- 代码围栏闭合性（双层校验，防“围栏未闭合把正文吞进代码块”）----
    # 第一层：全文字符串计数。``` 出现奇数次 ⇒ 必有一处未闭合；偶数只说明“数量
    # 成对”，不能排除 ``` 与 ~~~ 混用造成的跨标记误配，所以需要第二层逐行状态机。
    in_fence = False
    fence = ""
    # 第二层：逐行跟踪当前处于哪种围栏（``` 或 ~~~）、是否在围栏内。只有配对
    # 正确的围栏才会让 in_fence 复位，否则后续正文全被当成“围栏内”处理。
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence = True, marker
            elif marker == fence:
                in_fence, fence = False, ""
            continue
        # 缩进标题陷阱：CommonMark 规定缩进 ≥2 空格的标题会被当作代码块内容，
        # 不会渲染成标题——作者以为生效了，实际发布后是普通文字。故只在“围栏外”
        # （!in_fence）检查这种行，命中即报错并给出行号便于定位。
        if not in_fence and re.match(r"^ {2,}#{1,6}\s+\S", line):
            errors.append(f"题目页存在会显示为正文的缩进标题：{path}:{line_number}")
    # ---- 必需章节断言 ----
    # 发布模板约定每题固定具备这 4 部分：题目与约束、核心不变量（想清楚维护的量）、
    # 时间/空间复杂度。缺任何一项都说明该页没有按模板撰写完毕，属于“半成品页面”，
    # 直接阻断发布。
    for required in ("## 题目与约束", "## 核心不变量", "时间复杂度", "空间复杂度"):
        if required not in text:
            errors.append(f"缺少 {required}：{path}")
    # ---- 整理痕迹（模板演进残留）----
    # 站点经历过多次模板改版，旧模板会给页面打上“施工期”标记：旧标题“先记住”、
    # emoji 分类标题（📌🧠🛠️⏱️）、以及四句整理说明（“保留原方法”“仅做结构和
    # 措辞整理”“来源：`”“完整推导与代码”）。这些是面向作者自己的待办/溯源文案，
    # 正式发布后不应出现在读者面前，因此一律视为残留错误。
    if "先记住" in text:
        errors.append(f"题目页仍使用旧标题“先记住”：{path}")
    if re.search(r"📌|🧠|🛠️|⏱️", text):
        errors.append(f"题目页残留 emoji 整理标题：{path}")
    for stale in ("保留原方法", "仅做结构和措辞整理", "来源：`", "完整推导与代码"):
        if stale in text:
            errors.append(f"题目页残留整理痕迹文案“{stale}”：{path}")

# ---- 题号集合与 PROBLEMS 清单对齐 ----
# expected_problem_ids 是构建脚本登记的全部题号（权威清单）。用集合差集找出
# “多余”（页面上有、清单里没有 → 删题时页面没跟着删）与“缺失”（清单里有、
# 页面没有 → 生成失败或文件丢失）；len(ids)!=len(set(ids)) 则捕获“两个页面
# 共用一个题号”（目录里出现两篇同号页面的脏数据）。
expected_problem_ids = {int(p["id"]) for p in PROBLEMS}
if set(ids) != expected_problem_ids:
    errors.append(
        "题目页题号与题目清单不一致："
        f"多余 {sorted(set(ids) - expected_problem_ids)}、"
        f"缺失 {sorted(expected_problem_ids - set(ids))}"
    )
if len(ids) != len(set(ids)):
    errors.append("题号重复")

# 力扣原题链接覆盖：每道题都必须登记 slug，且生成后的题目页必须包含对应链接。
# ---- 力扣原题链接覆盖（slug 双向断言）----
# 第 71 行现有注释说明“每道题必须登记 slug + 题面必须含对应链接”，这里展开
# 实现细节：第一步只查登记表本身（PROBLEMS 的 id 是否都在 LEETCODE_SLUGS），
# 第二步逐个题目页做反向断言——有 slug 的页面正文里必须真的出现
# “leetcode.cn/problems/<slug>/” 链接（防御“登记了但生成时漏注入”的脱节）。
missing_slugs = sorted(int(p["id"]) for p in PROBLEMS if int(p["id"]) not in LEETCODE_SLUGS)
if missing_slugs:
    errors.append(f"题目缺少力扣 slug：{', '.join(map(str, missing_slugs))}")
for path in problem_files:
    text = path.read_text(encoding="utf-8-sig")
    match = re.search(r"(?m)^#\s+(\d+)\.\s+", text)
    if not match:
        # 无题号标题的页面跳过链接断言（前面已登记过“缺标题”错误，避免重复报）。
        continue
    slug = LEETCODE_SLUGS.get(int(match.group(1)))
    if slug and f"leetcode.cn/problems/{slug}/" not in text:
        errors.append(f"题目页缺少力扣原题链接：{path}")


# ============================================================================
# ② 链接完整性扫描（全站 md + html）
#   全站发布最常见的翻车点是“链接指向不存在”，来源包括：文件名大小写写错、
#   目录改名、误删文件。这里用两条正则分别抽取 Markdown 链接/图片目标
#   （[..](url)）与 HTML 的 href/src 目标，再对每个“本地相对链接”做存在性校验，
#   不存在即登记 error。扫描范围是所有 .md / .html 文件（含 _rglob_ 子目录）。
# ============================================================================
markdown_link = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
html_link = re.compile(r"(?i)(?:href|src)=[\"']([^\"']+)[\"']")
for path in ROOT.rglob("*"):
    if not path.is_file() or path.suffix.lower() not in {".md", ".html"}:
        continue
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    # Markdown 文件按行扫链接并跳过代码围栏（``` 块内的文本不是链接语法，
    # 否则 print(ops["square"](4)) 之类代码会被误判为指向文件"4"的失效链接）；
    # HTML 文件直接整文取 href/src。
    if path.suffix.lower() == ".md":
        links = []
        in_fence = False
        for line in text.splitlines():
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if not in_fence:
                links.extend(markdown_link.findall(line))
    else:
        links = html_link.findall(text)
    # ---- 链接归一化与跳过规则 ----
    # 三类链接无需校验：① 99-原稿归档/ 历史稿——归档区允许残链，不算发布问题；
    # ② 含 ${...} 的模板占位——路径要到构建期才被替换，源码阶段必然“不存在”；
    # ③ 外部协议（http/https/mailto/data/javascript）——不归本站文件系统管。
    # 路径提取：先按 #（锚点）和 ?（查询串）切掉后缀只留文件路径，unquote 把
    # %20 之类的百分号转义还原成真实字符，再 strip 掉首尾空白。
    for raw in links:
        if "99-原稿归档" in path.parts:
            continue
        if "${" in raw:
            continue
        link = unquote(raw.split("#", 1)[0].split("?", 1)[0]).strip()
        if not link or re.match(r"^(?:https?:|mailto:|data:|javascript:)", link, re.I):
            continue
        target = (path.parent / link).resolve()
        try:
            exists = target.exists()
        except OSError:
            exists = False
        if not exists:
            errors.append(f"失效本地链接：{path.relative_to(ROOT)} -> {raw}")


# ============================================================================
# ③ HTML 结构检查（全站 *.html）
#   按四层静态检查：A) 基础结构（页脚残留、lang/title/viewport、重复 id、
#   指向 md 的本地链接）；B) 阅读页正文（.markdown-body/.reader 容器里的
#   Markdown 残留与结构顺序）；C) 可视化页（05-可视化/）专属约束；D) 学习面板
#   dashboard（index.html）功能区与后端契约断言。同时顺手统计 reader_pages 与
#   math_formulas 两个发布度量（含义见末尾 summary 注释）。
# ============================================================================
html_files = sorted(ROOT.rglob("*.html"))
# 页脚残留：如果正式阅读页的脚注还写着“Markdown 保留作可编辑源稿”，说明该页
# 仍是“面向作者的临时过渡版”模板，没有切换成面向读者的正式版式。
stale_footer = "Markdown 保留作可编辑源稿"
for path in html_files:
    if stale_footer in path.read_text(encoding="utf-8-sig", errors="replace"):
        errors.append(f"阅读页残留整理痕迹页脚：{path.relative_to(ROOT)}")
reader_pages = 0
math_formulas = 0
for path in html_files:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    rel = path.relative_to(ROOT)

    # --- 基础结构三连查 ---
    # ① <html lang>：声明页面语言是无障碍与 SEO 的基础，缺失即报错；
    # ② <title>：浏览器标签页/搜索引擎结果标题，缺失或为空字符串等于没有标题；
    # ③ viewport：meta 里必须含 width=device-width（去掉空格后小写比较），
    #    否则移动端显示宽度错误、页面无法自适应。
    if soup.html is None or not soup.html.get("lang"):
        errors.append(f"HTML 缺少 lang：{rel}")
    title = soup.find("title")
    if title is None or not title.get_text(strip=True):
        errors.append(f"HTML 缺少 title：{rel}")
    viewport = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})
    if viewport is None or "width=device-width" not in viewport.get("content", "").replace(" ", "").lower():
        errors.append(f"HTML 缺少有效 viewport：{rel}")

    # 重复 id：用 Counter 统计所有带 id 的标签属性。HTML 规范要求 id 全文档唯一，
    # 重复会让 getElementById / CSS 选择器行为不确定（浏览器取第一个匹配），是硬性错误。
    id_counts = Counter(tag.get("id") for tag in soup.find_all(attrs={"id": True}))
    duplicate_ids = sorted(item for item, count in id_counts.items() if count > 1)
    if duplicate_ids:
        errors.append(f"HTML 存在重复 id：{rel} -> {', '.join(duplicate_ids)}")

    # 正式页面不应再指向 “*.md” 的本地链接——读者点击会得到源码文本而不是阅读页。
    # 排除两种情况：外部 http(s) 链接，以及页面本身位于归档区（99-原稿归档）。
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").split("#", 1)[0].split("?", 1)[0]
        if href.lower().endswith(".md") and not re.match(r"^https?://", href, re.I) and "99-原稿归档" not in rel.parts:
            errors.append(f"HTML 仍会打开 Markdown：{rel} -> {href}")

    # ---------- B. 阅读页正文级别检查 ----------
    # .markdown-body / .reader 是渲染后的正文容器：只有带它的页面才算“阅读页”
    # （计入 reader_pages），并对正文做结构性检查。math 标签计数用于度量全站
    # 公式渲染量（summary.math_formulas）。
    markdown_body = soup.select_one(".markdown-body, .reader")
    if markdown_body is not None:
        reader_pages += 1
        math_formulas += len(markdown_body.find_all("math"))
        # H1 唯一性：阅读页约定只有一个 <h1>（即题号标题），多个 H1 说明页面把
        # 正文里的 Markdown H1 也渲染成了页面级标题，破坏标题层级。
        headings = markdown_body.find_all("h1")
        if len(headings) != 1:
            errors.append(f"阅读页 H1 数量异常：{rel} -> {len(headings)}")
        # 目录顺序：.toc-box（目录）必须出现在第一个 H1 之前——用户在标题位置
        # 期望先看到目录，目录后置说明构建脚本的插入顺序反了。
        toc_box = markdown_body.select_one(".toc-box")
        if headings and toc_box and list(markdown_body.descendants).index(headings[0]) > list(markdown_body.descendants).index(toc_box):
            errors.append(f"阅读页目录出现在标题之前：{rel}")
        # ---- 可见文本残留语法扫描 ----
        # 把正文转成“面向读者的可见文本”再查残留：先剥掉 script/style/pre/code
        # （这些标签里的内容本来就是代码，不算作者残留），再取 get_text(" ")。
        # 然后逐个 <p> 看其第一个子节点的文本开头：若形如 “# 标题” 或 “- 列表项”，
        # 说明 Markdown 标题/列表被渲染成了 <p> 普通段落（转换器漏实现，读者会
        # 看到一串带井号/连字符的“正文文字”）。最后用正则扫整段可见文本，捕获
        # 渲染后未处理干净的 Markdown 记号：**强调**、``` / ~~~ 围栏、` 行内代码、
        # ![]() 链接或图片、$..$ LaTeX 美元符、以及 &#x20; 空格实体（HTML 转义
        # 后残留的空格占位，直接显示会破坏排版）。
        visible = BeautifulSoup(str(markdown_body), "html.parser")
        for tag in visible.select("script, style, pre, code"):
            tag.decompose()
        visible_text = visible.get_text(" ", strip=True)
        for paragraph in visible.find_all("p"):
            paragraph_text = paragraph.get_text(" ", strip=True)
            first_child = paragraph.contents[0] if paragraph.contents else ""
            leading_text = str(first_child).strip() if isinstance(first_child, str) else ""
            if re.match(r"^#{1,6}\s+\S", leading_text):
                errors.append(f"阅读页把 Markdown 标题显示成普通文字：{rel} -> {paragraph_text[:80]}")
            if re.match(r"^(?:[-+*]\s+|\d+[.)]\s+)\S", leading_text):
                errors.append(f"阅读页把 Markdown 列表显示成普通文字：{rel} -> {paragraph_text[:80]}")
        if "**" in visible_text or r"\*\*" in visible_text:
            errors.append(f"阅读页残留 Markdown 强调符：{rel}")
        if "```" in visible_text or "~~~" in visible_text:
            errors.append(f"阅读页残留 Markdown 代码围栏：{rel}")
        if "`" in visible_text:
            errors.append(f"阅读页残留 Markdown 行内代码符：{rel}")
        if re.search(r"!?\[[^\]\r\n]+\]\([^)\r\n]+\)", visible_text):
            errors.append(f"阅读页残留 Markdown 链接或图片语法：{rel}")
        if re.search(r"\$[^$\r\n]+\$", visible_text) or "$$" in visible_text:
            errors.append(f"阅读页残留 LaTeX 美元符：{rel}")
        if "&#x20;" in visible_text or "&amp;#x20;" in visible_text:
            errors.append(f"阅读页残留空格实体：{rel}")
        # ---------- 题解页（03-题解/）× 交互演示绑定 ----------
        # VISUAL_EMBEDS 是“题解页路径 → 应内嵌的交互演示”绑定表（build_html_site
        # 导出）。这里做双向断言：绑定过的页面必须有 iframe.reader-visual-frame
        # 且 src 含 embed=1（内嵌模式）且 scrolling=no（防止 iframe 与页面自身
        # 出现双层滚动条）；反之，没绑定的页面若出现 .reader-visual 演示区，
        # 说明演示被意外混入了普通题解。
        if "03-题解" in rel.parts:
            source_rel = rel.with_suffix(".md").as_posix()
            visual_section = markdown_body.select_one(".reader-visual")
            expected = VISUAL_EMBEDS.get(source_rel)
            if expected is None and visual_section is not None:
                errors.append(f"未绑定题解意外出现交互演示：{rel}")
            if expected is not None:
                frame = visual_section.select_one("iframe.reader-visual-frame") if visual_section else None
                if frame is None or "embed=1" not in frame.get("src", ""):
                    errors.append(f"已绑定题解缺少内嵌交互演示：{rel}")
                elif frame.get("scrolling") != "no":
                    errors.append(f"内嵌交互演示仍可能出现双层滚动条：{rel}")
        # 正文里若还有指向 05-可视化 的链接 = “独立演示入口”，说明该题解仍停留在
        # “另开独立演示页”的旧方案；新约定是演示直接内嵌进题解正文（上一条
        # 绑定断言的对象），二者只能取其一。
        for anchor in markdown_body.find_all("a", href=True):
            if "05-可视化" in anchor.get("href", ""):
                errors.append(f"阅读页仍提供独立演示入口：{rel}")

    # ---------- C. 可视化页（05-可视化/）专属约束 ----------
    # 四个必备锚点分别对应：统一导航条（[data-hot100-nav]）、响应式样式
    # （#hot100-polish）、键盘/可访问性增强（#hot100-a11y）与题解内嵌启动逻辑
    # （#hot100-embed-bootstrap）。缺任何一个都说明该页是从旧模板直接复制过来、
    # 没有接入当前可视化框架的组件体系。
    if "05-可视化" in rel.parts:
        if soup.select_one("[data-hot100-nav]") is None:
            errors.append(f"可视化页缺少统一导航：{rel}")
        if soup.select_one("#hot100-polish") is None:
            errors.append(f"可视化页缺少响应式样式：{rel}")
        if soup.select_one("#hot100-a11y") is None:
            errors.append(f"可视化页缺少键盘/可访问性增强：{rel}")
        if soup.select_one("#hot100-embed-bootstrap") is None:
            errors.append(f"可视化组件缺少题解内嵌启动逻辑：{rel}")
        # 内嵌模式（html.hot100-embedded）下，讲解类区域（笔记/输入/复杂度/代码/
        # 算法说明）必须被 CSS 隐藏——否则题解页内嵌演示时会把编辑控件一起显示。
        for hidden_block in (
            "html.hot100-embedded .notes-section",
            "html.hot100-embedded .input-section",
            "html.hot100-embedded .complexity-bar",
            "html.hot100-embedded .code-section",
            "html.hot100-embedded .algo-desc",
        ):
            if hidden_block not in text:
                errors.append(f"题解内嵌模式仍可能显示冗余讲解区：{rel} -> {hidden_block}")
        # ---- 动画/样式“源码指纹”防回归 ----
        # 这类检查直接用关键字符串在 HTML 源码里做子串匹配（源码指纹），而不是
        # 解析 CSS：约定一旦被重构掉，视觉风险是“标签被裁切、对比度不足、徽标
        # 错位、复杂度色点被渲染成嵌套徽标”等肉眼问题，回归测试难以覆盖，所以
        # 用指纹字符串兜底。例如：canvas 高度兜底 240、native-canvas/bar-stage
        # 安全区、.lane .label.top 指针标签偏移、高对比度标题色与复杂度色点规则。
        if "const H = canvas.clientHeight || 240;" in text:
            errors.append(f"柱状动画仍按含内边距高度绘制，可能裁切标签：{rel}")
        if '<canvas' in text and "hot100-native-canvas" not in text:
            errors.append(f"Canvas 演示缺少防裁切安全区：{rel}")
        if "bar-wrapper" in text and "hot100-bar-stage" not in text:
            errors.append(f"柱状演示缺少标签安全区：{rel}")
        if ".lane .label.top { bottom: 54px" in text:
            errors.append(f"链表指针标签位置可能遮挡节点：{rel}")
        if "panel-header" in text:
            if "--hot-hero-text" not in text or ".panel-header h1, .panel-header h2, .panel-header h3" not in text:
                errors.append(f"彩色题头未固定高对比度标题色：{rel}")
            if ".panel-header .sub, .panel-header p, .panel-header .info" not in text:
                errors.append(f"彩色题头说明文字可能继承灰色并失去对比度：{rel}")
            if ".complexity .badge-time, .complexity .badge-space" not in text:
                errors.append(f"复杂度色点可能被渲染成嵌套徽标：{rel}")

# ---------- D. 学习面板 dashboard（index.html）----------
# 面板是整个学习站的门面：缺失直接报错并用空文档占位（避免下面代码因
# dashboard 为 None 崩溃）；存在时断言“不再提供独立演示入口”与“不再保留
# 重复的‘阅读题解’入口”（这些是旧交互残留）。
dashboard_path = ROOT / "index.html"
if not dashboard_path.exists():
    errors.append("学习面板缺失：index.html")
    dashboard = BeautifulSoup("", "html.parser")
else:
    dashboard = BeautifulSoup(dashboard_path.read_text(encoding="utf-8-sig"), "html.parser")
if dashboard.find("a", href=re.compile(r"05-可视化")) is not None or "打开演示" in dashboard.get_text(" ", strip=True):
    errors.append("学习面板仍存在独立演示入口")
if "阅读题解" in dashboard.get_text(" ", strip=True):
    errors.append("学习面板题卡仍保留重复的“阅读题解”入口")
# 由 VISUAL_EMBEDS 的键（形如 “03-题解/…/0128-….html”）反推“已绑定演示的
# 题号集合”（取文件名开头数字）：困难题必须有题解内嵌演示，否则读者看关键题
# 时缺少可视化辅助，属于发布阻断项（missing_hard_visuals）。
bound_problem_ids: set[int] = set()
for key in VISUAL_EMBEDS:
    filename = key.rsplit("/", 1)[-1]
    prefix_match = re.match(r"(\d+)", filename)
    if prefix_match:
        bound_problem_ids.add(int(prefix_match.group(1)))
missing_hard_visuals = sorted(int(problem["id"]) for problem in PROBLEMS if problem["difficulty"] == "困难" and int(problem["id"]) not in bound_problem_ids)
if missing_hard_visuals:
    errors.append(f"困难题缺少题解内嵌演示：{', '.join(map(str, missing_hard_visuals))}")
# 控件可访问性：搜索/分类/状态三个控件必须配 <label for>（点击文字即聚焦，
# 屏幕阅读器才能读出控件用途）；状态下拉还必须有 value="due"（待复习）选项，
# 否则复习筛选功能不完整。
for control_id in ("search", "category", "status"):
    control = dashboard.find(id=control_id)
    if control is None or dashboard.find("label", attrs={"for": control_id}) is None:
        errors.append(f"学习面板控件缺少标签：{control_id}")
status_select = dashboard.find(id="status")
if status_select is not None and status_select.find("option", value="due") is None:
    errors.append("学习面板筛选缺少“待复习”状态")
# 面板挂载点完整性：JS 用 getElementById 找这一批 id，缺任何一个都会让对应
# 功能（今日统计、轮次、连续天数、目标编辑、抽卡、错题、限时模拟等）静默失效
# ——页面不报错但功能没渲染，所以必须逐个显式断言。
for element_id in ("todayViewed", "todayRounds", "completedCount", "totalRounds", "streakCount", "goalText", "goalInput", "reviewList", "reviewSummary", "remindButton", "pickCard", "pickAgain", "weakList", "mockStart", "mockStatus", "mockTimer", "mockList", "mockReport"):
    if dashboard.find(id=element_id) is None:
        errors.append(f"学习站缺少数据库状态区域：{element_id}")
# 学习记录已拆到独立页面 history.html，最近学习日/最近活动挂载点改在那里校验。
history_text = (ROOT / "history.html").read_text(encoding="utf-8")
for element_id in ("dayList", "eventList"):
    if f'id="{element_id}"' not in history_text:
        errors.append(f"学习记录页缺少数据库状态区域：{element_id}")
# ---- 面板 JS × 后端 API 的源码字符串契约 ----
# 面板内嵌的 JS 必须引用本地学习记录 API（/api/dashboard、/api/complete、
# /api/daily、/api/mark、/api/export、/api/settings、/api/mock、/api/plan、
# data-export="weekly" 与错题本页 05-错题本.html），缺任何一个都说明面板与
# 服务端脱节。顺带的字符串断言：PWA（serviceWorker.register + manifest）、
# uPlot 趋势图（uPlot + id="trend"）、限时模拟“计入轮次”开关、书架待复习
# 入口与折叠区、力扣提交统计/连接状态（acTodayText/ac-pill/lcStatus）；最后
# 是反向断言：data-submit/recordSubmit/submit-ac 这类“手动已 AC/WA 按钮”
# 已废弃（提交状态必须以力扣同步数据为准，不允许手动改）。
dashboard_source = (ROOT / "index.html").read_text(encoding="utf-8-sig")
if "/api/dashboard" not in dashboard_source or "/api/complete" not in dashboard_source or "/api/daily" not in dashboard_source or "/api/mark" not in dashboard_source or "/api/export" not in dashboard_source or "/api/settings" not in dashboard_source or "/api/mock" not in dashboard_source or "/api/plan" not in dashboard_source or 'data-export="weekly"' not in dashboard_source or "05-错题本.html" not in dashboard_source:
    errors.append("学习站没有连接本地学习记录 API")
if "serviceWorker.register" not in dashboard_source or "manifest.webmanifest" not in dashboard_source:
    errors.append("学习面板缺少 PWA 注册或 manifest 链接")
if "uPlot" not in dashboard_source or 'id="trend"' not in dashboard_source:
    errors.append("学习面板缺少近 28 天趋势图（uPlot）")
if 'id="mockCountRounds"' not in dashboard_source:
    errors.append("限时模拟缺少“计入学习轮次”开关")
if 'id="shelfDueLink"' not in dashboard_source or "review_include_contents" not in dashboard_source:
    errors.append("学习面板缺少书架待复习入口或设置折叠区")
if "...daily.contents.map" in dashboard_source:
    errors.append("学习面板“今日待复习”仍在与书架章节混排")
if 'id="acTodayText"' not in dashboard_source or "ac-pill" not in dashboard_source or "lcStatus" not in dashboard_source:
    errors.append("学习面板缺少力扣提交统计或连接状态（AC 徽标/统计/力扣状态）")
if 'data-submit="' in dashboard_source or "recordSubmit" in dashboard_source or "submit-ac" in dashboard_source:
    errors.append("题卡仍残留手动已 AC/WA 按钮（应以同步数据为准）")
# 力扣连接向导页：既要有独立页面，页内还必须带“全量同步”按钮（syncFullBtn），
# 否则用户无法一次性拉取全部历史提交（只能增量同步）。
if not (ROOT / "leetcode-connect.html").exists():
    errors.append("学习站缺少力扣连接向导页 leetcode-connect.html")
if "syncFullBtn" not in (ROOT / "leetcode-connect.html").read_text(encoding="utf-8-sig"):
    errors.append("力扣连接页缺少“全量同步”入口")
# ============================================================================
# ④ 学习站运行骨架与“生成脚本/模板/服务端/力扣功能”断言
#   前面三段检查的是“产物页面长什么样”，这一段检查“支撑物齐不齐、契约签没签”：
#   必需文件（服务端/template/启动脚本）是否在；服务端关键设计与前端约定字符串
#   （REVIEW_INTERVALS_CONTENT 内容复习间隔、/api/daily 的 module 过滤、
#   submissions/lc_id 全量去重、CORS 头等）是否实现；书架清单与各类本地资产
#   （Mermaid / uPlot / PWA / 搜索索引 / 错题页）是否齐全且与构建源一致。
# ============================================================================
for required_path in (
    ROOT / "tools" / "study_server.py",
    ROOT / "tools" / "templates" / "dashboard.tpl",
    ROOT / "启动学习站.cmd",
):
    if not required_path.exists():
        errors.append(f"学习站缺少必需文件：{required_path.relative_to(ROOT)}")
# 学习记录服务 study_server.py = 本地 SQLite + HTTP API 的数据后端，
# 是面板所有数据功能（打卡、复习、错题、模拟）的支撑，缺失即全线失效。
server_path = ROOT / "tools" / "study_server.py"
if server_path.exists():
    server_source = server_path.read_text(encoding="utf-8-sig")
    # ---- 服务端契约字符串字典（每个字符串 = 一项必须存在的设计）----
    #   CREATE TABLE study/content_events : 刷题事件表与内容学习事件表；
    #   'view'/'complete' 与 round_no     : 轮次复习模型（查看/完成 + 轮次号）；
    #   /api/content/complete、due_after_content、REVIEW_INTERVALS_CONTENT:
    #                                   书架内容复习间隔配置（背记类内容用）；
    #   def daily_data、module_id: str   : 按模块聚合的每日数据；
    #   submissions / credentials、/api/submit、/api/leetcode/connect:
    #                                   力扣提交记录、凭据存储与连接接口；
    #   Access-Control-Allow-Origin     : CORS 响应头（浏览器放行本地前端）。
    for required_text in ("CREATE TABLE IF NOT EXISTS study_events", "CREATE TABLE IF NOT EXISTS content_events", "'view'", "'complete'", "round_no", "/api/content/complete", "127.0.0.1", "REVIEW_INTERVALS_CONTENT", "due_after_content", "def daily_data", "module_id: str", "CREATE TABLE IF NOT EXISTS submissions", "CREATE TABLE IF NOT EXISTS credentials", "/api/submit", "/api/leetcode/connect", "Access-Control-Allow-Origin"):
        if required_text not in server_source:
            errors.append(f"学习记录服务缺少关键设计：{required_text}")
    # /api/daily 必须支持 ?module= 参数：书架“本模块今日待复习”列表靠它过滤，
    # 少了这个过滤条件，书架模块页/章节页的复习区块拿不到模块级数据。
    if "module_id=params.get(\"module\", \"\")" not in server_source:
        errors.append("学习记录服务缺少 /api/daily?module= 模块过滤")
    # 力扣全量同步设计三要素：full: bool 参数（分页全量拉取开关）、lc_id 提交 ID
    # 字段、uq_submissions_lc 唯一索引——三者配合才能按提交 ID 去重，
    # 重复点击“全量同步”不会插入脏数据。
    if "lc_id" not in server_source or "full: bool" not in server_source or "uq_submissions_lc" not in server_source:
        errors.append("力扣同步缺少全量分页或按提交 ID 去重（lc_id）")
# ---- 学习书架模块清单（library/manifest.json）----
# 书架总页/模块页/章节页的数据来源。断言三层：模块数必须等于 LIBRARY_MODULES
# 的模块数 + 1（多出的 1 个是约定的附加模块，例如“全部”或汇总模块，改清单
# 人数时必须同步改这里）；每个章节的 url 对应的文件必须存在；每个章节必须在
# routes 里有匹配的记录路由（module_id + content_id 双键），且路由指向的页面
# 文件真实存在——否则“看题记录”点进去是 404。JSON 本身损坏（解析异常/缺键/
# 类型错）时整体登记一条错误。
library_manifest_path = ROOT / "library" / "manifest.json"
if not library_manifest_path.exists():
    errors.append("学习书架缺少模块清单")
else:
    try:
        library_manifest = json.loads(library_manifest_path.read_text(encoding="utf-8"))
        library_modules = library_manifest.get("modules", [])
        library_routes = library_manifest.get("routes", {})
        if len(library_modules) != len(LIBRARY_MODULES) + 1:
            errors.append(f"学习书架模块数量异常：{len(library_modules)}（应为 {len(LIBRARY_MODULES) + 1}）")
        # 逐模块逐章节做“文件存在 + 路由存在 + 路由文件存在”三连查；
        # matching_routes 用列表推导按 module_id/content_id 配对过滤 routes。
        for module in library_modules:
            for chapter in module.get("chapters", []):
                chapter_path = (ROOT / "library" / chapter["url"]).resolve()
                matching_routes = [
                    route for route, meta in library_routes.items()
                    if meta.get("module_id") == module["id"] and meta.get("content_id") == chapter["id"]
                ]
                if not chapter_path.exists():
                    errors.append(f"学习书架章节缺失：{chapter['url']}")
                if not matching_routes:
                    errors.append(f"学习书架章节没有看题记录路由：{chapter['url']}")
                elif not (ROOT / matching_routes[0].lstrip("/")).exists():
                    errors.append(f"学习书架章节路由指向的文件缺失：{matching_routes[0]}")
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        errors.append(f"学习书架模块清单损坏：{exc}")

# ---- Mermaid 11.16.1 本地化（离线可用，禁用 CDN）----
# tools/vendor 是构建源运行库，library/assets 是复制到站点的产物。两者都要存在
# 且 ≥1MB（完整运行库约 3-4MB，＜1MB 说明被替换成了精简版或占位文件），
# 逐字节一致性比对见后文（library 产物与 tools/vendor 构建源的 read_bytes 比较）。
mermaid_vendor = ROOT / "library" / "assets" / "mermaid-11.16.1.min.js"
mermaid_source = ROOT / "tools" / "vendor" / "mermaid-11.16.1.min.js"
mermaid_bootstrap = ROOT / "library" / "assets" / "library-mermaid.js"
if not mermaid_source.exists() or mermaid_source.stat().st_size < 1_000_000:
    errors.append("构建工具缺少 Mermaid 11.16.1 源运行库")
if not mermaid_vendor.exists() or mermaid_vendor.stat().st_size < 1_000_000:
    errors.append("学习书架缺少完整的本地 Mermaid 11.16.1 运行库")

# ---- 题解页公共资产与沉浸模式清理 ----
# assets/site.js 与 site.css 是所有题解页的公共外壳，缺失则页面样式/脚本
# 直接加载失败；反向断言：若其中残留字符串 “immersive”，说明旧的沉浸模式
# 功能没有被清理干净（该功能已下线，不允许再出现）。
site_js_path = ROOT / "assets" / "site.js"
site_css_path = ROOT / "assets" / "site.css"
if not site_js_path.exists() or not site_css_path.exists():
    errors.append("题解页公共脚本或样式缺失")
for asset_path in (site_js_path, site_css_path):
    if asset_path.exists() and "immersive" in asset_path.read_text(encoding="utf-8", errors="replace"):
        errors.append(f"沉浸功能残留：{asset_path.relative_to(ROOT)}")
# 题解页与书架章节页的沉浸残留抽查：只取前 3 页做代价可控的采样（全量做
# 字符串扫描太慢），检查旧的沉浸按钮 id 与旧脚本引用是否仍混进生成产物——
# 生成脚本若漏掉清理步骤，旧模板的痕迹会原样带进所有新页面。
problem_pages = sorted((ROOT / "books" / "hot100" / "03-题解").rglob("*.html"))
if not problem_pages:
    errors.append("题解页目录为空")
for problem_path in problem_pages[:3]:
    problem_source = problem_path.read_text(encoding="utf-8", errors="replace")
    if 'id="immersiveToggle"' in problem_source:
        errors.append(f"题解页残留沉浸按钮：{problem_path.relative_to(ROOT)}")
# 书架章节页同样抽查前 3 页：不允许残留 immersive.js 引用或沉浸按钮；且必须带
# “下次复习”行（#chapterDue + /api/daily?module= 请求）——这是书架与普通题解页
# 不同的核心功能点（章节级复习状态）。
library_chapter_pages = sorted((ROOT / "library").rglob("chapter-*.html"))
if not library_chapter_pages:
    errors.append("学习书架章节页为空")
for chapter_path in library_chapter_pages[:3]:
    chapter_source = chapter_path.read_text(encoding="utf-8", errors="replace")
    if "assets/immersive.js" in chapter_source or 'id="immersiveToggle"' in chapter_source:
        errors.append(f"书架章节页残留沉浸引用：{chapter_path.relative_to(ROOT)}")
    if 'id="chapterDue"' not in chapter_source or "/api/daily?module=" not in chapter_source:
        errors.append(f"书架章节页缺少“下次复习”行：{chapter_path.relative_to(ROOT)}")
# 旧沉浸产物文件本身一旦还在仓库（library/assets/immersive.js），说明清理任务
# 没跑或失败——“产物化存在”本身就足以证明状态脏，直接阻断。
library_immersive_path = ROOT / "library" / "assets" / "immersive.js"
if library_immersive_path.exists():
    errors.append("沉浸产物未清理：library/assets/immersive.js")
# 书架总页：必须有“全书架待复习汇总条”（#shelfDueSummary）与模块到期角标机制
# （data-module-due 属性），否则总览页起不到“今天该复习什么”的入口作用。
library_index_path = ROOT / "library" / "index.html"
if not library_index_path.exists():
    errors.append("学习书架总页缺失")
else:
    library_index_source = library_index_path.read_text(encoding="utf-8", errors="replace")
    if 'id="shelfDueSummary"' not in library_index_source or "data-module-due" not in library_index_source:
        errors.append("学习书架总页缺少全书架待复习汇总条或模块到期角标")
# 每个书架模块页（library/*/index.html）抽查前 5 个：必须带本模块待复习区块
# （#moduleDue）、due 筛选选项与 /api/daily?module= 请求，三者缺一即模块页的
# 复习功能不完整。
library_module_pages = sorted((ROOT / "library").glob("*/index.html"))
if not library_module_pages:
    errors.append("学习书架模块页为空")
for module_path in library_module_pages[:5]:
    module_source = module_path.read_text(encoding="utf-8", errors="replace")
    if 'id="moduleDue"' not in module_source or '<option value="due">' not in module_source or "/api/daily?module=" not in module_source:
        errors.append(f"书架模块页缺少本模块待复习区块：{module_path.relative_to(ROOT)}")
# 逐字节比对：站点资产必须与构建源完全一致（构建过程是直接复制），任何一字节
# 不同都说明产物不是由当前版本构建源生成的，可能是手工改过或旧缓存残留。
if mermaid_source.exists() and mermaid_vendor.exists() and mermaid_source.read_bytes() != mermaid_vendor.read_bytes():
    errors.append("生成的 Mermaid 运行库与构建源文件不一致")
if not mermaid_bootstrap.exists():
    errors.append("学习书架缺少 Mermaid 初始化脚本")

# ---- 书架全文搜索 ----
# 离线搜索由 search.html + search-index.json 组成：两文件缺一不可，且页面必须
# 引用 “search-index.json” 才会加载索引（否则搜索结果永远是空）。
search_page_path = ROOT / "library" / "search.html"
search_index_path = ROOT / "library" / "search-index.json"
if not search_page_path.exists():
    errors.append("学习书架缺少全文搜索页")
if not search_index_path.exists():
    errors.append("学习书架缺少离线搜索索引")
elif search_page_path.exists():
    search_text = search_page_path.read_text(encoding="utf-8-sig")
    if "search-index.json" not in search_text:
        errors.append("搜索页没有加载离线索引")
# ---- 抽样断言（仅在样例章节存在时检查，避免页面尚未生成时的误报）----
# java-core/chapter-01 必须给出全文搜索入口与“导出本章”按钮；再抽查三门课的
# 特定章节内嵌演示：Java 并发锁升级（.demo-embed）、计网 TCP 握手挥手、
# MySQL ReadView 版本链——这些是课程内容的关键可视化，丢了说明演示迁移失败。
chapter_sample = ROOT / "library" / "java-core" / "chapter-01.html"
if chapter_sample.exists() and "search.html" not in chapter_sample.read_text(encoding="utf-8-sig"):
    errors.append("书架章节页导航缺少全文搜索入口")
if chapter_sample.exists() and "exportChapter" not in chapter_sample.read_text(encoding="utf-8-sig"):
    errors.append("书架章节页缺少导出本章按钮")
concurrency_chapter = ROOT / "library" / "java-concurrency" / "chapter-05.html"
if concurrency_chapter.exists() and 'class="demo-embed"' not in concurrency_chapter.read_text(encoding="utf-8-sig"):
    errors.append("Java 并发章节缺少锁升级内嵌演示")
for chapter_path, demo_name in (
    (ROOT / "library" / "computer-network" / "chapter-03.html", "TCP握手挥手可视化"),
    (ROOT / "library" / "mysql" / "chapter-06.html", "ReadView版本链可视化"),
):
    if chapter_path.exists() and demo_name not in chapter_path.read_text(encoding="utf-8-sig"):
        errors.append(f"书架章节缺少内嵌演示：{chapter_path.relative_to(ROOT)} -> {demo_name}")
# ---- PWA 骨架与错题本 ----
# manifest.webmanifest + service-worker.js 是 PWA 可安装/可离线的必要条件；
# 错题本页必须调用 /api/weaklist（薄弱清单 API），否则面板的错题入口只是空壳。
for required_path in (ROOT / "manifest.webmanifest", ROOT / "service-worker.js"):
    if not required_path.exists():
        errors.append(f"PWA 缺少必需文件：{required_path.relative_to(ROOT)}")
notebook_path = ROOT / "books" / "hot100" / "00-总览" / "05-错题本.html"
if not notebook_path.exists():
    errors.append("学习站缺少错题本页")
elif "api/weaklist" not in notebook_path.read_text(encoding="utf-8-sig"):
    errors.append("错题本页没有连接薄弱清单 API")

# ---- uPlot 图库本地化（同 Mermaid 策略）----
# tools/vendor 存构建源、assets 存站点产物，双份都要在且 ≥1000 字节
# （完整 uPlot 源约 30KB+，过小即为占位文件）；两份逐字节比对必须一致。
uplot_vendor = ROOT / "tools" / "vendor" / "uplot.min.js"
uplot_asset = ROOT / "assets" / "uplot.min.js"
if not uplot_vendor.exists() or uplot_vendor.stat().st_size < 1000:
    errors.append("构建工具缺少 uPlot 源运行库")
if not uplot_asset.exists() or uplot_asset.stat().st_size < 1000:
    errors.append("学习面板缺少 uPlot 运行库")
elif uplot_vendor.exists() and uplot_vendor.read_bytes() != uplot_asset.read_bytes():
    errors.append("生成的 uPlot 运行库与构建源文件不一致")

# ---- Mermaid 图数量闭环：源笔记 vs 课程页 ----
# 先统计“应有的图”：LIBRARY_MODULES 定义每个模块的 source 笔记文件路径
# （位于仓库根目录的上层），用 (?im)^```mermaid\s*$ 数出 Mermaid 围栏个数。
# “应有值”与后面的“实际渲染值”必须相等，数量对不上说明有图没渲染或渲染多。
expected_mermaid = 0
for definition in LIBRARY_MODULES:
    source_path = ROOT / "books" / definition["source"]
    source_text = source_path.read_text(encoding="utf-8-sig")
    expected_mermaid += len(re.findall(r"(?im)^```mermaid\s*$", source_text))

# 再统计“实际的图”：数课程页里 figure.mermaid-diagram 节点。挨页检查四件事：
# ① 图不能以代码块形式展示（code.language-mermaid —— 说明渲染器漏处理）；
# ② 含图页必须加载本地 Mermaid 脚本（mermaid-11.16.1.min.js + library-mermaid.js）
#    且不得引用任何 https?:// 在线脚本（离线站禁用 CDN）；
# ③ 每张图的 pre.mermaid 源码必须存在且非空（否则图上没有可渲染内容）；
# ④ 图内不得残留 &#x20; 空格实体。最后 rendered != expected 时给出双方数量。
rendered_mermaid = 0
for chapter_path in sorted((ROOT / "library").glob("*/chapter-*.html")):
    chapter_text = chapter_path.read_text(encoding="utf-8-sig")
    chapter_soup = BeautifulSoup(chapter_text, "html.parser")
    figures = chapter_soup.select("figure.mermaid-diagram")
    rendered_mermaid += len(figures)
    if chapter_soup.select("code.language-mermaid"):
        errors.append(f"课程页仍把 Mermaid 显示为代码：{chapter_path.relative_to(ROOT)}")
    if figures:
        scripts = [script.get("src", "").split("?", 1)[0] for script in chapter_soup.find_all("script", src=True)]
        if "../assets/mermaid-11.16.1.min.js" not in scripts or "../assets/library-mermaid.js" not in scripts:
            errors.append(f"含图课程页没有加载本地 Mermaid：{chapter_path.relative_to(ROOT)}")
        if any(re.match(r"^https?://", src, re.I) for src in scripts):
            errors.append(f"含图课程页错误引用在线脚本：{chapter_path.relative_to(ROOT)}")
        for figure in figures:
            source = figure.select_one("pre.mermaid")
            if source is None or not source.get_text(strip=True):
                errors.append(f"Mermaid 图缺少可渲染源码：{chapter_path.relative_to(ROOT)}")
            if "&#x20;" in figure.get_text() or "&amp;#x20;" in str(figure):
                errors.append(f"Mermaid 图残留空格实体：{chapter_path.relative_to(ROOT)}")
if rendered_mermaid != expected_mermaid:
    errors.append(f"Mermaid 图数量不一致：源笔记 {expected_mermaid}，课程页 {rendered_mermaid}")
# ---- 章节页导航骨架 ----
# 约定每章页面必需三件套：.chapter-nav 里要有返回课程目录（index.html）的链接；
# main.reader > .breadcrumb 面包屑要有课程目录链接；标题下要有学习记录状态条
# （#chapterStatus）。反向断言：.chapter-layout 固定双栏是已废弃的旧布局
# （新版是响应式单栏），出现即报错。
for chapter_path in sorted((ROOT / "library").glob("*/chapter-*.html")):
    chapter_text = chapter_path.read_text(encoding="utf-8-sig")
    chapter_soup = BeautifulSoup(chapter_text, "html.parser")
    nav = chapter_soup.select_one(".chapter-nav")
    if nav is None:
        errors.append(f"课程章节页缺少章节导航：{chapter_path.relative_to(ROOT)}")
    elif not any(a.get("href", "").split("?", 1)[0] == "index.html" for a in nav.find_all("a", href=True)):
        errors.append(f"课程章节页缺少返回课程目录入口：{chapter_path.relative_to(ROOT)}")
    breadcrumb = chapter_soup.select_one("main.reader > .breadcrumb")
    if breadcrumb is None:
        errors.append(f"课程章节页缺少面包屑：{chapter_path.relative_to(ROOT)}")
    elif not breadcrumb.find("a", href="index.html"):
        errors.append(f"课程章节页面包屑缺少课程目录链接：{chapter_path.relative_to(ROOT)}")
    if chapter_soup.select_one(".chapter-layout") is not None:
        errors.append(f"课程章节页仍使用固定侧栏双栏布局：{chapter_path.relative_to(ROOT)}")
    reader_main = chapter_soup.select_one("main.reader")
    if reader_main is None or reader_main.select_one("#chapterStatus") is None:
        errors.append(f"课程章节页缺少标题下学习记录状态条：{chapter_path.relative_to(ROOT)}")
# 面板进度条可访问性：role="progressbar" 必须携带 aria-valuemin / aria-valuemax
# / aria-valuenow 三件套，否则屏幕阅读器读不出“当前进度”的语义。
progressbar = dashboard.select_one('[role="progressbar"]')
if progressbar is None or not all(progressbar.has_attr(name) for name in ("aria-valuemin", "aria-valuemax", "aria-valuenow")):
    errors.append("学习面板进度条缺少完整 ARIA 状态")

# 定点回归：0128 题正文以“给定一个未排序的整数数组…”开头，历史上曾被渲染器
# 误判为 <pre> 代码块（整段变成等宽字体）。这里对该已知缺陷保留定点检查——
# 只要这段文字仍出现在任何 <pre> 里就说明回归了。
longest_page = ROOT / "books" / "hot100" / "03-题解" / "01-哈希表" / "0128-最长连续序列.html"
if longest_page.exists():
    longest = BeautifulSoup(longest_page.read_text(encoding="utf-8-sig"), "html.parser")
    if any("给定一个未排序的整数数组" in pre.get_text() for pre in longest.find_all("pre")):
        errors.append("128 最长连续序列正文被误渲染为代码块")


# ============================================================================
# ⑤ JavaScript 语法检查（借助 Node.js）
#   BeautifulSoup 只验证 HTML 结构，页面里的 <script> 内联脚本与生成的 *.js
#   资产有没有语法错误，只能交给 JS 引擎兜底。
#   实现要点（临时目录机制）：在站点根目录下建临时目录（前缀 hot100-js-，
#   随 with 语句自动清理），把每个内联脚本按“页面名-序号.js”落盘，再逐文件
#   执行 `node --check`（只做语法解析、不执行代码），返回码非 0 即语法错误并
#   登记 error。用临时文件而不是管道传 stdin，是为了拿到 Node 带文件名/行列号
#   的报错文本，便于定位到具体页面；落盘前 mkdir(parents=True) 是为了防止并行
#   清理进程抢先删除目录导致写文件失败（见下面 temp.mkdir 行上的原注释）。
#   无法使用 node 的环境（未安装/不在 PATH）不阻断发布：降级为一条 WARN，
#   提示“本环境跳过了 JS 语法检查”这一层。
# ============================================================================
node = shutil.which("node")
if node:
    with tempfile.TemporaryDirectory(prefix="hot100-js-", dir=ROOT) as temp_dir:
        temp = Path(temp_dir)
        temp.mkdir(parents=True, exist_ok=True)  # 防止并行清理进程删掉目录后写文件失败
        # 收集三类含脚本的页面：05-可视化 页 + 全部书架页 + 面板首页。
        # 提取内联脚本的正则：(?is) 忽略大小写并让 . 匹配换行；(?!…\bsrc=) 是
        # 负向前瞻，排除带 src（外部文件引用）的 <script>——外部文件不进这里，
        # 单独当作一个 JS 文件整体 --check（见下面 generated_scripts）。
        script_pages = sorted((ROOT / "books" / "hot100" / "05-可视化").glob("*.html")) + sorted((ROOT / "library").rglob("*.html")) + [ROOT / "index.html"]
        for html_path in script_pages:
            source = html_path.read_text(encoding="utf-8-sig")
            scripts = re.findall(r"(?is)<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", source)
            for index, script in enumerate(scripts):
                js_path = temp / f"{html_path.stem}-{index}.js"
                js_path.write_text(script, encoding="utf-8")
                result = subprocess.run([node, "--check", str(js_path)], capture_output=True, text=True)
                if result.returncode:
                    errors.append(f"JavaScript 语法错误：{html_path.name}：{result.stderr.strip()}")
        # 生成脚本资产：assets/*.js 与 library/assets/*.js 是构建产物（独立文件，
        # 不是从 HTML 提取的），直接整体 --check；报错信息带相对路径便于定位。
        generated_scripts = list((ROOT / "assets").glob("*.js")) + list((ROOT / "library" / "assets").glob("*.js"))
        for js_path in sorted(generated_scripts):
            result = subprocess.run([node, "--check", str(js_path)], capture_output=True, text=True)
            if result.returncode:
                errors.append(f"JavaScript 语法错误：{js_path.relative_to(ROOT)}：{result.stderr.strip()}")
else:
    warnings.append("未找到 Node.js，跳过 JavaScript 语法检查")


# ============================================================================
# ⑥ 汇总输出与退出码
#   summary 字典逐字段含义——
#     problem_pages : 03-题解 下的题目页 md 数量（全量基线应为 100 页）；
#     unique_ids    : 页面标题里解析出的独立题号个数（配合 ① 的重复题号检查，
#                     正常应等于 problem_pages）；
#     topic_pages   : 02-专题 下的专题 md 页数；
#     visuals       : 05-可视化 下的演示页数；
#     markdown_files: 全站 .md 文件总数；
#     html_files    : 全站 .html 文件总数；
#     reader_pages  : 带 .markdown-body/.reader 容器的阅读页数（③-B 的检查对象）；
#     math_formulas : 阅读页 <math> 标签总数（站点公式渲染量的度量）；
#     broken_links  : errors 中以“失效本地链接”开头的错误条数（② 的专用统计，
#                     单独归口便于发布报告里单列链接健康度）；
#     errors        : 发布阻断项总数——>0 即退出码 1，CI/批处理据此判失败；
#     warnings      : 软告警总数（如缺 Node.js 跳过了 JS 检查），只提示不阻断。
#   输出顺序：先打印一行 summary 字典（JSON 风格），再逐条打印 “ERROR …” 与
#   “WARN …” 详情，最后以退出码收尾，供外部脚本直接判断成败。
# ============================================================================
summary = {
    "problem_pages": len(problem_files),
    "unique_ids": len(set(ids)),
    "topic_pages": len(list((ROOT / "books" / "hot100" / "02-专题").glob("*.md"))),
    "visuals": len(list((ROOT / "books" / "hot100" / "05-可视化").glob("*.html"))),
    "markdown_files": len(list(ROOT.rglob("*.md"))),
    "html_files": len(html_files),
    "reader_pages": reader_pages,
    "math_formulas": math_formulas,
    "broken_links": sum(1 for e in errors if e.startswith("失效本地链接")),
    "errors": len(errors),
    "warnings": len(warnings),
}
# 打印阶段：summary 一行总览 + errors/warnings 的逐条明细；
# 退出码语义再强调一次：errors 非空 → 1（发布不通过），否则 → 0（通过）；
# warnings 不参与退出码，外部脚本可用“退出码 + WARN 行数”区分硬失败与软提示。
print(summary)
for item in errors:
    print("ERROR", item)
for item in warnings:
    print("WARN", item)
# errors 为空 → 退出码 0（成功）；非空 → 退出码 1（失败）。
sys.exit(1 if errors else 0)
