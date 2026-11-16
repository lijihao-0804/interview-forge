# zero2Leetcode `acm-playground` 实现拆解与借鉴评估

> 参考项目：[ranxi2001/zero2Leetcode](https://github.com/ranxi2001/zero2Leetcode)
> 在线页面：[acm-playground.html](https://onefly.top/zero2Leetcode/acm-playground.html)
> 相关文件：`acm-playground.html`、`assets/js/acm-playground.js`、`assets/js/acm-bridge.js`、`assets/js/java-runner-worker.js`、`assets/js/playground-languages.js`

## 一、它到底怎么运行的

**结论：这是纯前端方案，不是服务器判题系统。**

### 1. Python：Pyodide（浏览器里的 Python）

- 页面加载 `https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js`；
- 代码在浏览器里的 Pyodide（WebAssembly CPython）运行；
- 通过 `pyodide.setStdin(...)` 把页面左侧的 stdin 喂给 `input()`；
- 用 `sys.stdout` / `sys.stderr` 重定向捕获输出；
- `pyodide.loadPackagesFromImports(code)` 自动尝试加载 `numpy`、`scipy` 等包；
- 超时后标记 Pyodide 损坏并重新初始化，避免下一次运行污染状态。

相关代码大致在 `acm-playground.js` 的 `executePython()`。

### 2. Java：CheerpJ（浏览器里的 Java 17）

- `java-runner-worker.js` 在 Web Worker 里加载 CheerpJ：
  - `https://cjrtnc.leaningtech.com/4.3/loader.js`
- 加载项目自带 jar：`assets/vendor/zero2leetcode-java-runner-20260803.jar`
- 通过 `cheerpjRunLibrary` 调用自定义 Java runner 的 `run(code, stdin, maxOutputBytes)`；
- 代码编译与执行都在浏览器里完成，不经过后端。

代价：CheerpJ 体积大、初始化慢，且商用授权需要单独确认。

### 3. Go：Go Playground 远程 API

- 调用 `https://play.golang.org/compile`；
- 把代码和 stdin 打包成 txtar，POST 给 Go 官方 Playground；
- 依赖外部服务可用性，不是本地运行。

### 4. 页面如何从真题跳到 IDE

`acm-bridge.js` 做的是“注入按钮”：

1. 只在 `04_real_interviews` 真题页生效；
2. 找到 `pre > code` 代码块；
3. 根据 class 判断语言（python/go/java）；
4. 向上查找同一道题的 `**输入**` / `**输出**` 代码块；
5. 把 `code`、`input`、`expected` 做 Base64；
6. 生成链接：

```text
acm-playground.html?language=python&code=...&input=...&expected=...
```

7. 用户点击“▶ 在 ACM IDE 中运行”，新标签页打开 playground。

`acm-playground.js` 启动时读取这些 URL 参数，填入编辑器、stdin、expected 三个区域。

### 5. 判题逻辑

`compareOutput()` 只做：

```js
actual.trim() === expected.trim()
```

- 相等：显示 `ACCEPTED`
- 不等：显示 `WRONG ANSWER`

它不是正式 OJ：没有隐藏测试数据、没有多测试点、没有 checker、没有榜单、没有防作弊。

### 6. 页面其他功能

- CodeMirror 5 编辑器；
- Python/Go/Java 模板；
- stdin、stdout、expected 三个文本区；
- 运行快捷键 `Ctrl+Enter`；
- Python 调试（逐行执行、断点状态）；
- localStorage 保存代码/输入/期望输出；
- 导出/导入练习包 JSON；
- 可选的 AI 教练面板。

## 二、哪些值得借鉴

### 很值得借鉴

1. **浏览器内运行代码**
   - 不需要 Docker、MongoDB、OJ 后端；
   - 对“自己练习”非常合适。

2. **真题代码块 → 一键打开 IDE**
   - `acm-bridge.js` 的注入思路很好：题解页保持静态，点击按钮把代码和样例带到独立 playground；
   - URL 用 Base64 传 `code/input/expected`，不需要后端存储。

3. **单页 IDE 的交互**
   - CodeMirror、stdin/stdout、expected 对比、AC/WRONG 提示、保存/导出；
   - 这些都可以单独复用，不必上 HydroOJ。

4. **Python 超时与隔离处理**
   - Pyodide 在浏览器里，天然不会碰服务器文件系统；
   - 对自用练习足够。

### 不建议照搬

1. **Java/CheerpJ**
   - 依赖体积大、初始化慢；
   - CheerpJ 商用授权要确认；
   - 我们服务器当前也没有 Java，若只自用 Python，可先不做 Java。

2. **Go Playground API**
   - 依赖外部服务，不适合作为稳定自用环境。

3. **完整 debugger / AI 教练**
   - 代码量大，维护成本高；先把“运行 + 对比”做稳。

4. **把它当正式判题**
   - 它只比较样例输出，不能防硬编码，不适合正式考试。

## 三、能否直接套到我们重构后的页面

可以借鉴，但不能直接复制粘贴运行，原因是 DOM 不同：

我们的题目页目前是：

```html
<h2>样例</h2>
<div class="codehilite"><pre>...</pre></div>

<h2>题解代码</h2>
<h3>Java 实现</h3>
<div class="codehilite"><pre>...</pre></div>
<h3>Python 实现</h3>
<div class="codehilite"><pre>...</pre></div>
```

而 `acm-bridge.js` 期待：

```html
pre > code
.doc-article
**输入** / **输出** 的 <p><strong>
```

所以需要写一个**适配版 bridge**：

- 把 `04_real_interviews` 改成我们的 `books/ai-exam`；
- 把 `pre > code` 改成 `div.codehilite > pre`；
- 根据前面的 `h3`（Java 实现 / Python 实现）判断语言，或给代码块加 `data-language`；
- 从题目页的样例区域提取 stdin/expected；
- 生成同样的 `acm-playground.html?language=python&code=...&input=...&expected=...` 链接。

## 四、最适合我们的落地方案

### 方案 A：Python-only Pyodide（最推荐）

- 直接引入/改写 `acm-playground.html` + `acm-playground.js`；
- 只保留 Python 3；
- 用适配版 bridge 给题目页加“▶ 运行代码”；
- 全部静态，不经过服务器，不需要 Docker。

适合：

- AI/Agent 手撕题；
- 纯 Python 题；
- 自用练习、快速验证样例。

限制：

- 纯 Python；numpy/scipy 可尝试，sklearn 等 ML 库不一定完整；
- 不适合 Java/C++；
- 只比较样例，不是真正隐藏测试。

### 方案 B：服务器轻量 runner（Python + C++）

- 现有 FastAPI 加 `/api/practice/run`；
- Python 用 `.venv`，C++ 用 `g++`；
- 前端加代码编辑器和运行按钮；
- 适合 ML/Python 题和 C++ 题，能做真实进程执行。

限制：

- 要自己做超时/内存/安全隔离；
- 当前服务器没有 Java，要支持 Java 需安装 JDK；
- 不要对公网开放任意代码执行。

### 方案 C：Hybrid

- Python 用 Pyodide 浏览器运行（零后端）；
- C++/ML 题走服务器 runner；
- Java 暂不做，或以后用 CheerpJ。

这是最平衡的自用方案。

## 五、建议

**先借鉴它的“静态 IDE + URL 桥接 + 样例对比”模式，不要照搬 Java/Go 和完整 debugger。**

如果目标是自用、只刷我们自己的题：

1. 先做 **Python-only Pyodide 版**，最快落地；
2. 题目页加“▶ 运行代码”按钮；
3. 只比较样例输出；
4. 后续遇到 C++/ML 需求，再补服务器 runner。

这样既不需要 HydroOJ，也不需要 Docker/MongoDB。

## 六、许可提醒

`zero2Leetcode` 仓库带 `LICENSE-EPL-2.0.txt`，直接复制其中代码需要按 EPL-2.0 保留许可和声明；Pyodide、CheerpJ、Go Playground 也各有自己的许可/服务条款。更稳妥的做法是**参考架构自己重写核心逻辑**，而不是整包拷贝。
