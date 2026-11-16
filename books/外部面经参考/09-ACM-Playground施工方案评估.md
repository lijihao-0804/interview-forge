# ACM Playground 施工方案评估（Python + Java，自用）

> 目标：参考 `ranxi2001/zero2Leetcode` 的 ACM Playground，给当前 `books/ai-exam` 题目页增加“运行 Python / Java 代码”的能力。
>
> 前提：自用、不比赛；服务器允许安装 Java 环境。
>
> 结论：**可以借鉴，但不建议原样整套拷贝。推荐“抄前端交互 + 服务端执行 Python/Java”的方案。**

## 一、原项目的实际架构

原项目 `acm-playground.html` 是纯前端：

- **Python**：Pyodide（WebAssembly）
- **Java 17**：CheerpJ（WebAssembly JVM）+ 自定义 `zero2leetcode-java-runner-*.jar`
- **Go**：Go Playground 远程 API
- **代码编辑**：CodeMirror 5
- **真题页跳转**：`acm-bridge.js` 把代码、stdin、expected 做 Base64，拼到 `acm-playground.html?language=...&code=...&input=...&expected=...`
- **判题**：只做 `actual.trim() === expected.trim()`，显示 `ACCEPTED / WRONG ANSWER`

它不是正式 OJ，没有隐藏测试、测试点、checker、榜单。

## 二、直接抄原项目 vs 推荐方案

| 方案 | 做法 | 优点 | 风险/缺点 |
|---|---|---|---|
| **A. 原样抄** | 复制 `acm-playground.html`、`acm-playground.js`、`acm-bridge.js`、`java-runner-worker.js`、Java runner jar | Python/Java 都在浏览器运行，不需要服务器 JDK | CheerpJ 体积大、首次加载慢；需要 CheerpJ 授权确认；jar 要一起维护；CDN 依赖；跟我们页面 DOM 不匹配 |
| **B. 推荐** | 抄前端 UI/交互；**服务端执行 Python + Java** | Java 用真正的 OpenJDK 17；速度快；依赖少；跟现有 FastAPI 集成；不需要 CheerpJ | 需要做代码执行安全隔离、超时、内存限制 |
| **C. 混合** | Python 用 Pyodide，Java 用服务端 | Python 不经过服务器；Java 稳定 | 两套运行时，复杂度和维护成本更高 |

## 三、推荐施工方案（方案 B）

### 目标架构

```text
books/ai-exam/*.html
        │ 点击「运行代码」
        ▼
acm-playground.html（抄自原项目，改品牌/导航）
        │ POST /api/practice/run
        ▼
FastAPI（现有 interview-forge 服务）
        ├─ Python：/opt/interview-forge/.venv/bin/python
        └─ Java：javac + java（OpenJDK 17）
```

### 1. 服务器准备

只读检查结果：

- Ubuntu 24.04.4，4 vCPU，15 GiB 内存，163 GB 可用磁盘
- Python 3.12.3 已存在
- `g++` 13.3 已存在
- **Java 当前未安装**
- apt 有 `openjdk-17-jdk` 候选：`17.0.21.0.3+1-1~24.04.1`
- 也有 `openjdk-21-jdk`，但建议装 **17**，和原项目 Java 17 对齐

安装：

```bash
apt-get update
apt-get install -y openjdk-17-jdk
```

不需要 Docker，不需要 MongoDB。

### 2. 前端复制范围

**建议复制并改造：**

- `acm-playground.html`
- `assets/css/acm-playground.css`
- `assets/js/acm-playground.js`
- `assets/js/acm-bridge.js`
- CodeMirror 5（可用 CDN，也可自托管）

**不要复制：**

- `ai-assistant.js`（体积大、依赖 AI 服务，和自用无关）
- `java-runner-worker.js` 和 CheerpJ jar（服务端 Java 不需要）
- Go runner（外部 Go Playground API，不稳定）
- 原项目导航、品牌、AI 面板

### 3. 改造 `acm-playground.js`

保留：

- 编辑器
- Python/Java 语言选择
- stdin / stdout / expected 三栏
- `ACCEPTED / WRONG ANSWER` 对比
- 超时选择
- localStorage 保存
- 导入/导出练习包

替换执行器：

```js
async function executePython(code, stdinText) {
  // 调用 POST /api/practice/run
  // body: { language: 'python', code, stdin }
  // 返回 { stdout, stderr, exit_code, time_ms }
}

async function executeJava(code, stdinText) {
  // 调用 POST /api/practice/run
  // body: { language: 'java', code, stdin }
}
```

删除或禁用：

- `loadPyodide`
- CheerpJ worker
- Go Playground API

### 4. 后端接口

新增：

```text
POST /api/practice/run
Content-Type: application/json

{
  "language": "python" | "java",
  "code": "....",
  "stdin": "...."
}
```

返回：

```json
{
  "stdout": "...",
  "stderr": "...",
  "exit_code": 0,
  "time_ms": 123,
  "timed_out": false
}
```

实现要点：

- Python：用现有 `.venv/bin/python`，临时目录执行；
- Java：`javac -encoding UTF-8 Main.java`，再 `java -Xmx256m -cp temp Main`；
- 自动检测 Java 公共类名（`public class Xxx` 就写 `Xxx.java`）；
- `timeout=3~10s`；
- 限制 stdout/stderr 大小（例如 64KB）；
- 临时目录自动清理；
- 只允许登录用户/管理员访问；
- 不要直接以 root 跑用户代码，建议使用独立低权限用户或至少做资源限制。

### 5. 页面桥接改造

原 `acm-bridge.js` 只适用于原项目结构。我们的页面是：

```html
<h2>样例</h2>
<div class="codehilite"><pre>样例输入/输出</pre></div>

<h2>题解代码</h2>
<h3>Java 实现</h3>
<div class="codehilite"><pre>Java 代码</pre></div>
<h3>Python 实现</h3>
<div class="codehilite"><pre>Python 代码</pre></div>
```

需要改：

- 把 `04_real_interviews` 判断改成 `books/ai-exam`；
- 选择器改成 `div.codehilite > pre`；
- 根据前面的 `h3` 或代码注释判断语言；
- 从 `h2 样例` 中提取 input/expected；
- 生成：

```text
acm-playground.html?language=python&code=...&input=...&expected=...
```

**更稳的做法**：在生成 `books/ai-exam` 页面时给每个代码块写入 `data-language`、`data-input`、`data-expected`，不要让前端靠 DOM 猜。

### 6. 分阶段施工

**Phase 1：MVP（1–2 天）**

- 安装 JDK 17；
- 抄 playground 页面 + CSS；
- 后端支持 Python / Java；
- 手工挑 5–10 道题验证；
- 不做批量桥接。

**Phase 2：页面接入（1 天）**

- 改 `acm-bridge.js` 适配我们的页面；
- 题目页每个 Python/Java 代码块加“运行代码”；
- 159 道页面由生成脚本批量注入，不手改 HTML。

**Phase 3：稳定性（1 天）**

- 超时、内存、输出上限；
- 编译错误/运行错误提示；
- localStorage 保存；
- 只允许登录用户访问。

**总计：2–4 个工作日可做出自用 MVP。**

## 四、关键风险

1. **Java 类名/文件名**
   - `javac` 要求 `public class Main` 对应 `Main.java`；
   - 需要从代码中提取 public class 名，或者统一包装成 `Main`。

2. **Java 内存/并发**
   - 每个 Java 进程设置 `-Xmx256m` 或 `-Xmx512m`；
   - 自用限制 1–2 个并发即可。

3. **安全**
   - 服务器是生产环境，不能把任意代码执行接口裸露公网；
   - 必须登录/管理员限制、超时、临时目录、禁止读取项目敏感文件；
   - 自用最好只绑定内网/本机，或加 IP 白名单。

4. **原项目许可**
   - `zero2Leetcode` 是 EPL-2.0；
   - 复制代码要保留 `LICENSE-EPL-2.0.txt` 和 `THIRD_PARTY_NOTICES.md`；
   - CheerpJ、Pyodide、CodeMirror 各有自己的许可/服务条款；
   - 推荐“参考架构重写核心逻辑”，不要整包照搬。

5. **原项目只比较样例**
   - 这是练习工具，不是正式判题；
   - 不要把它宣传成“正式 ACM 评测系统”。

## 五、最终建议

**推荐采用方案 B：**

- 前端抄 `acm-playground` 的交互和布局；
- Python / Java 都走现有 FastAPI 服务端执行；
- 服务器安装 **OpenJDK 17**；
- 不需要 Docker、MongoDB、HydroOJ；
- 先做 10 道题 MVP，再批量接入 159 道。

这样既保留原项目“打开题解 → 一键运行 → 对比样例”的体验，又避免 CheerpJ 的体积、授权和兼容性问题。

## 六、服务器只读检查记录

已确认：

- `python3 --version` → Python 3.12.3
- `g++ --version` → g++ 13.3
- `java` / `javac` → 当前未安装
- `apt-cache policy openjdk-17-jdk` → 17.0.21 可用
- `nproc` → 4
- `free -h` → 15 GiB（约 11 GiB 可用）
- `df -h /` → 163 GB 可用
- 未执行安装、未修改任何文件
