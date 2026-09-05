# InterviewForge 手机端视觉体验改进报告（Codex 执行稿）

> 目标读者：执行端 AI（Codex）。本报告只描述"改什么、改哪里、怎么改、怎么验"，
> 不含设计讨论。所有改动点均已在本仓库内核实到文件与锚点。
> 症状来源：手机端阅读章节页/题解页需要左右滑动，体验差；目标视口 375px（iPhone 标准屏）。

---

## 1. 目标与验收标准

1. **页面级横向滚动归零**：375px 视口下，所有阅读页 `document.documentElement.scrollWidth === window.innerWidth`（禁止用裁切掩盖，见第 7 节红线）。
2. **代码块移动端可读**：长行代码在手机上不再必须左右拖动（自动换行或一键切换"原样/换行"）。
3. **宽表格移动端可用**：表格字号/内边距收缩，容器内横向滚动可接受但页面不滚。
4. **桌面端零回归**：≥1280px 时代码块不换行、表格/Mermaid/面板趋势图布局与现状一致。
5. **深色模式与 reduced-motion 不受影响**：新规则只使用现有 CSS 变量，不硬编码色值。

---

## 2. 必须先知道的架构事实（防止改错地方）

### 2.1 三套页面体系与样式来源

| 体系 | 页面范围 | 样式来源 | 修改入口（生成链路） |
|---|---|---|---|
| 学习书架 | `library/` 全部章节/模块页、`search.html` | `library/assets/library.css`、`library/assets/library-mermaid.js` | `tools/build_library.py` 的 `LIBRARY_CSS` 常量（第 97 行起，至约 279 行闭合）与 `MERMAID_JS` 常量（约第 283 行起） |
| Hot100 阅读页 | `books/`、`guide.html`、`maintenance.html`、`QA-REPORT.html` | `assets/site.css`、`assets/site.js` | `tools/build_html_site.py` 的 `SITE_CSS` 常量（第 153 行起）与 `SITE_JS` 常量（第 413 行起） |
| 数据面板 | 根 `index.html` | 内联 `<style>`（含 `assets/uplot.min.css`） | `tools/build_html_site.py` 中生成面板样式的代码（含 1607 行附近的 dashboard-nav 注入） |
| 力扣连接 | `leetcode-connect.html` | 页内内联 `<style>` | 手写文件，**本轮不动** |

**证据**：`build_library.py:1053-1054` 把 `LIBRARY_CSS`/`MERMAID_JS` 常量原样写入 `library/assets/`；`build_html_site.py:1732` 附近把 `SITE_CSS`/`SITE_JS` 写入 `assets/`。

### 2.2 构建链（改动后必须整体重跑）

构建链严格串行，`build_hot100.py` 的 `build()` 末尾自动依次调用 `build_library.py`（1764 行）与 `build_html_site.py`（1780 行）。标准命令：

```bat
cd /d E:\interview-forge
python tools\build_hot100.py     :: 自动串联 build_library.py -> build_html_site.py
python tools\check_hot100.py     :: 校验脚本：errors 非空则退出码 1（发布不通过）
```

**警告**：`check_hot100.py` 会反向断言 `assets/` 产物与常量完全一致——**直接手改 `library/assets/library.css`、`assets/site.css`、`assets/site.js` 会被校验失败或被下次构建覆盖，是无效修改**。所有样式改动必须落在 Python 常量里。

### 2.3 缓存版本号（改样式后必翻）

- `tools/build_library.py` 第 89 行：`ASSET_VERSION = "20260830-module3"`（书架页 `?v=` 参数）
- `tools/build_html_site.py` 第 76 行：`ASSET_VERSION = "20260830-v2"`（阅读页 `?v=` 参数）
- `service-worker.js` 第 2 行：`const VERSION = "hot100-v2"`（PWA 缓存命名空间，网络优先策略）

三处需同步递增，否则手机端拿到旧 CSS。

---

## 3. 问题清单（现象、根因、证据）

### P0-1 书架章节页「整页」横向滚动
- **现象**：手机上打开书架章节，整页可以左右拖动（不是代码块内部滚动）。
- **根因**：`LIBRARY_CSS` 中正文阅读区无任何 `overflow-wrap`/`word-break`（全常量仅 `.chapter-card .method` 一处有 `overflow-wrap:anywhere`）。行内代码、长链接、标题中的长英文串（如 `ScopedProxyMode.TARGET_CLASS`、`TypeReference<List<String>>`）无断行机会，直接撑破 `.reader` 容器。
- **对比**：`site.css` 体系有 `.markdown-body{overflow-wrap:break-word}`（108 行）和 `a{overflow-wrap:anywhere}`（60 行），所以书架是重灾区。
- **实例**：`library/spring-family/chapter-02.html` 中 `@Scope(value = "prototype", proxyMode = ScopedProxyMode.TARGET_CLASS)`；`library/java-core/chapter-06.html` 中 `new PriorityQueue<>(Comparator.reverseOrder())`。

### P0-2 书架阅读页移动断点不足
- **根因**：`LIBRARY_CSS` 仅有 `@media(max-width:860px)`（阅读页 padding 24px）与 `@media(max-width:560px)`（壳宽、章节列表、topbar）两条；**没有任何针对代码块/表格/按钮的移动端字号与触控适配**。`.reader` 在 860px 以下 padding 仍为 24px，360px 屏内容区只剩约 294px。

### P0-3 代码块横滚且无换行手段
- **根因**：两体系都是 `pre{overflow:auto}` 容器内横滚：
  - `site.css` 阅读页 `pre code{font-size:14px}` 固定（156 行），`@media(max-width:720px)` 里**没有**代码字号收缩；
  - `LIBRARY_CSS` `.reader pre` 无移动端字号收缩；
  - 均无"自动换行/原样"切换。
- **注**：Hot100 体系已有"复制代码"按钮（`site.js`），换行后仍可取原文；书架体系没有复制按钮，见 Task 2 的取舍说明。

### P0-4 宽表格
- `site.css`：`.markdown-body table{min-width:540px}`（159 行），移动端仅降到 500px（221 行），靠 JS 包一层 `.table-wrap` 内部横滚；
- `LIBRARY_CSS`：`.reader table{width:max-content;...;display:block;overflow:auto}`（「表格居中」注释块），**无任何移动端字号/内边距收缩**。

### P1-1 Mermaid 与公式容器内横滚无提示
- `.mermaid-diagram`、`.math-display-wrap` 均 `overflow-x:auto`；Mermaid 节点间距固定（`nodeSpacing:34/rankSpacing:44`），手机上宽图必须横拖。

### P1-2 数据面板用 `overflow-x:hidden` 掩盖溢出
- 根 `index.html` 内联样式 `body{overflow-x:hidden}`：一旦内部元素超宽（如 `assets/uplot.min.css` 的 `.uplot{width:min-content}`），图表会被**静默裁切**而非提示滚动。

### P2-1 断点碎片化
- 720（site.css）/ 860、560、760、520（library）/ 980、760、520、680、620（面板），同一项目三种档位体系，后续维护易漏。

### P2-2 触控目标偏小
- `.copy-code{padding:4px 9px}`、书架 `.complete-button{padding:5px 12px}` 等接近或低于 40px 触控标准。

---

## 4. 修改任务（按顺序执行）

> 通用写法说明：所有 CSS 补丁以「追加到常量末尾、闭合三引号之前」为主（CSS 后置覆盖，避免去改 LIBRARY_CSS 中 105 行那个超长单行，降低误改风险）；需要插入 JS 的用精确字符串替换。

### Task 1（P0）LIBRARY_CSS：页面级防溢出

**文件**：`tools/build_library.py`，`LIBRARY_CSS = r"""`（97 行）… 闭合 `"""`（约 279 行）之间，追加在常量最末尾（`/* Java 专属配色 */` 深色块之后）。

```css

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
```

**注意**：`overflow-wrap` 在 `white-space:pre` 下本就失效，`pre code{overflow-wrap:normal}` 是双保险；`.reader pre.mermaid` 是流程图容器，本轮不动它（见红线）。

### Task 2（P0）LIBRARY_CSS：移动端阅读适配（≤640px）

接在 Task 1 补丁之后追加：

```css

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
```

**取舍说明（书架体系无"复制代码"按钮）**：移动端代码默认软换行（`pre-wrap`+`break-all`）会改变长行的原始排版，但缩进保留、文本仍可长按选择复制；对比"必须左右拖动"的现状，阅读收益大得多。若产品上不接受，可去掉 `.reader pre:not(.mermaid){...}` 一行，仅保留字号收缩——但这样 P0-3 只解决一半。

### Task 3（P0）SITE_CSS：移动端适配补齐

**文件**：`tools/build_html_site.py`，`SITE_CSS = r"""`（153 行）… 闭合处。改动两处：

① 常量末尾（闭合三引号前）追加兜底与按钮开关样式：

```css

/* ===== 移动端改进补丁（MOBILE-UX-REPORT Task 3-4） ===== */
body{overflow-x:clip}
/* 代码块换行开关（配合 SITE_JS 的按钮） */
.code-block pre.code-wrap{white-space:pre-wrap;word-break:break-all;overflow-x:hidden}
.code-toolbar{flex-wrap:wrap;gap:6px}
```

② 在现有 `@media (max-width: 720px) { ... }` 块（对应产物 site.css 212-226 行的内容）内部追加：

```css
  html{-webkit-text-size-adjust:100%}
  .markdown-body pre{font-size:12.5px;padding:16px 14px}
  .markdown-body pre:not(.code-nowrap){white-space:pre-wrap;word-break:break-all;overflow-x:hidden}
  .markdown-body table{min-width:440px;font-size:13px}
  .markdown-body th,.markdown-body td{min-width:84px;padding:7px 8px}
  .copy-code{padding:6px 10px;min-height:36px}
```

（原 720px 块中已有表格行 `table{min-width:500px;font-size:14px}` 与 `th,td{min-width:94px;padding:8px 9px}`，直接替换这两行即可。）

### Task 4（P0）SITE_JS：代码块"换行/原样"切换按钮

**文件**：`tools/build_html_site.py`，`SITE_JS = r"""`（413 行）常量。SITE_JS 中有创建工具栏的循环（对应产物 `assets/site.js` 25-54 行，核心语句是 `toolbar.append(label, button);`）。

① 将 `toolbar.append(label, button);` 替换为：

```js
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
```

② 同步确认回退按钮逻辑：当用户点"换行"（桌面默认未换行）→ 加 `.code-wrap`；当移动端媒体查询默认已换行时 → 点"原样"加 `.code-nowrap`（媒体规则用 `:not(.code-nowrap)`，见 Task 3）。两个类互斥逻辑正确即可。

### Task 5（P1）宽表格：粘性首列（可选增强）

在 Task 3 的 720px 块内追加（书架体系如需同款，把选择器换成 `.reader th/.reader td`，背景用 `var(--panel)`）：

```css
  .table-wrap{position:relative}
  .markdown-body th:first-child,.markdown-body td:first-child{
    position:sticky;left:0;z-index:1;
    background:var(--surface);
    box-shadow:1px 0 0 var(--line);
  }
```

注意：sticky 首列会覆盖斑马纹（`.markdown-body tr:nth-child(even) td` 同源竞争，后定义者胜）。若视觉不可接受则跳过本 Task，不影响其他验收项。

### Task 6（P1）Mermaid 移动端收缩

**文件**：`tools/build_library.py`，`MERMAID_JS = r"""` 常量。在 `mermaid.initialize({...})` 前插入窄屏判断，并改两处配置值：

```js
  const narrow = window.innerWidth < 640;
  window.mermaid.initialize({
    ...
    flowchart: { htmlLabels: true, useMaxWidth: true, curve: 'basis', nodeSpacing: narrow ? 18 : 34, rankSpacing: narrow ? 26 : 44, padding: narrow ? 10 : 14 },
    sequence: { useMaxWidth: true, wrap: true, actorMargin: narrow ? 34 : 46, messageMargin: narrow ? 24 : 32, diagramMarginX: narrow ? 12 : 24, diagramMarginY: narrow ? 12 : 18 },
```

（保留原值不动会更好维护时，也可只改 `nodeSpacing/rankSpacing` 两项。）

### Task 7（P2）数据面板图表防裁切

**文件**：`tools/build_html_site.py` 中生成根 `index.html` 内联 `<style>` 的代码（搜索 `overflow-x:hidden` 与 `max-width:520px` 定位；dashboard-nav 注入在 1607 行附近）。

- 把面板 `body{overflow-x:hidden}` 保留为最后防线（不要删），但要消除超宽来源：给图表容器加约束，例如在面板内联样式中追加：

```css
.history{min-width:0}
.history .uplot,.history .u-wrap{width:100%;max-width:100%}
```

- 改完必须验证桌面趋势图正常显示（见第 6 节第 4 条）。

### Task 8（P0，必做）版本号递增

| 位置 | 现值 | 改为 |
|---|---|---|
| `tools/build_library.py:89` | `"20260830-module3"` | `"20260830-mobile1"` |
| `tools/build_html_site.py:76` | `"20260830-v2"` | `"20260830-mobile1"` |
| `service-worker.js:2` | `"hot100-v2"` | `"hot100-v3"` |

---

## 5. 重建与发布步骤

```bat
cd /d E:\interview-forge
python tools\build_hot100.py
python tools\check_hot100.py
```

- `check_hot100.py` 退出码 0 = 通过；出现 ERROR 必须修复后重跑（它会验证 assets 与常量一致、页面入口存在等）。
- 若重建后产物看起来未更新（`library/assets/library.css` 等仍旧），检查 `.build-cache.json` / `tools/build_cache.py` 的增量缓存是否需要清理后重跑。
- 本报告文件 `MOBILE-UX-REPORT.md` 不会被渲染成页面（`build_html_site.py` 只处理 README/MAINTENANCE/QA-REPORT 与 CONTENT_DIRS）；若 `check_hot100` 对根目录新增文件报 WARN，忽略即可，不阻塞发布。

## 6. 验证清单

1. **页面级无横向滚动**：DevTools 375px 视口（iPhone 12 档），对以下页面执行 `document.documentElement.scrollWidth === window.innerWidth` 应全部为 `true`：
   - `library/spring-family/chapter-02.html`（长行内代码）
   - `library/redis/chapter-01.html`（表格 + Mermaid）
   - `library/java-core/chapter-06.html`（代码/公式）
   - `library/devops/` 任一章（长命令代码块）
   - `books/hot100/` 任一章、`guide.html`
2. **代码块**：375px 下长行自动换行、高亮不破块；点"换行/原样"来回切换生效；"复制代码"仍复制原始文本；书架页 mermaid 图正常渲染且未被换行规则误伤。
3. **表格**：375px 下字号 13px，页面不滚，容器内部滚动正常。
4. **桌面回归**：1280px 下 pre 默认不换行、表格布局、Mermaid 布局、面板趋势图均与改动前一致。
5. **深色模式**：`prefers-color-scheme:dark` 下复核新增区域（无硬编码色值即应通过）。
6. **缓存**：Network 面板确认 CSS/JS 链接 `?v=20260830-mobile1`；SW 更新后（hot100-v3）强刷一次再离线打开正常。
7. **reduced-motion**：`prefers-reduced-motion:reduce` 下页面无动画异常。

## 7. 红线（禁止事项）

1. **不改生成产物**：`library/assets/library.css`、`assets/site.css`、`assets/site.js` 由常量生成，手改无效且会被 `check_hot100.py` 抓包。
2. **反对只用 `overflow-x:hidden` 交差**：它裁切内容、掩盖问题；本方案以断行修复为根，`overflow-x:clip` 仅作兜底。
3. **禁止误伤 `.reader pre.mermaid`**：换行/断词规则必须 `:not(.mermaid)`（它是流程图源码容器，已有 `pre-wrap` 行为）。
4. **禁止硬编码浅/深色值**：新规则一律使用现有 CSS 变量（`--panel/--soft/--brand/--muted/--line` 等）。
5. **禁止改 `tools/vendor/` 与 `assets/uplot.min.css`/`uplot.min.js`**：图表覆盖规则放在面板生成端内联样式。
6. **不改 `prefers-reduced-motion` 现有规则、不动 README/QA-REPORT 等文档内容**。
7. **不动 `leetcode-connect.html`**（手写页，本轮范围外；如后续要统一，另行立项）。

## 8. 完成定义（Definition of Done）

- [ ] Task 1-8 全部落地，改动均在 `tools/` 常量与 `service-worker.js` 内
- [ ] `python tools/build_hot100.py` 成功，`python tools/check_hot100.py` 退出码 0 且无 ERROR
- [ ] 第 6 节验证清单 1-7 全过（桌面回归至少抽查 3 个典型页）
- [ ] 三个版本号已递增且页面链接带新 `?v=`