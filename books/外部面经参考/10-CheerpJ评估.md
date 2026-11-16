# 为什么不在 ACM Playground 里优先用网页版 CheerpJ

> 对比对象：`ranxi2001/zero2Leetcode` 的 Java 方案（CheerpJ 4.3 + 自定义 Java runner jar）与服务端 OpenJDK 17 方案。
>
> 结论：**CheerpJ 不是不能用，而是更适合“纯前端、个人/教育、零服务器”的场景；你既然允许在服务器安装 Java，服务端执行更稳、更可控。**

## 一、CheerpJ 的定位

CheerpJ 是 Leaning Technologies 的浏览器 Java 运行时：

- 用 WebAssembly/JavaScript 实现 JVM；
- 加载编译后的 JAR/class，不需要源码；
- 支持 Java 8/11/17/21（5.0 还预览 Java 25）；
- 官方说明支持 Chrome、Edge、Firefox、Safari，包括移动浏览器；
- 代码在浏览器沙箱里运行，不会上传到服务器。

所以它不是“假 Java”，确实是完整 OpenJDK 的浏览器版本。

## 二、原项目用 CheerpJ 的具体方式

`acm-playground` 的 Java 部分：

- `java-runner-worker.js` 在 Web Worker 中加载：
  - `https://cjrtnc.leaningtech.com/4.3/loader.js`
- 加载项目自带的 `zero2leetcode-java-runner-20260803.jar`；
- `cheerpjInit({ version: 17 })`；
- 调用自定义 runner 的 `run(code, stdin, maxOutputBytes)`；
- 有一段 `JAVA_INIT_TIMEOUT_MS = 90000`，也就是首次初始化最长等 90 秒。

## 三、主要缺点

### 1. 首次加载重、冷启动慢

CheerpJ 要把 JVM、OpenJDK 类库和编译器加载到浏览器里：

- 首次进入 Java 页面可能要等十几秒到几十秒；
- 原项目自己设置了 90 秒初始化超时；
- 移动端浏览器内存压力更大，低端手机可能直接卡顿或失败。

对“打开题解 → 马上运行”的自用体验不友好。

### 2. 授权是重点风险

CheerpJ 官方 licensing 说明：

- 个人、教育、爱好、技术评估免费；
- 一人公司、非商业开源项目可免费，但可能要求 “Built with CheerpJ” 署名；
- **商业产品、SaaS、面向客户的应用需要 Application/Desktop 商业授权**；
- 从自己的服务器/仓库提供 CheerpJ 运行时（self-hosting）通常属于付费能力，技术评估期除外。

如果 `hot100.xyz` 只是一个个人学习站，风险较小；如果是公开商业产品，就不能直接照搬。具体以 [CheerpJ Licensing](https://cheerpj.com/docs/licensing) 为准。

### 3. 浏览器资源限制

Java 在浏览器里编译和执行会吃内存和 CPU：

- 用户设备越弱，编译越慢；
- 大代码/复杂输入容易卡顿；
- Worker 崩溃或超时后要重建运行时；
- 原项目限制 Java 代码 48KB、stdin 16KB、输出 64KB，就是现实约束。

### 4. 依赖 CDN 和自定义 JAR

- CheerpJ loader 从 `cjrtnc.leaningtech.com` 加载；
- 项目还需要维护自己的 Java runner jar；
- 如果 CDN 不可用、企业网络拦截、浏览器策略限制，Java 功能就不可用；
- 离线/内网部署需要 CheerpJ 企业授权和自托管版本。

### 5. 调试和可观测性弱

- 代码在浏览器 Worker 里，服务端看不到运行日志；
- 编译错误、JVM 错误、Worker 崩溃的排查比服务端执行麻烦；
- 很难做统一日志、监控、限流、审计。

### 6. 和我们的页面结构不匹配

原项目 `acm-bridge.js` 针对它的 Jekyll 文章结构：

- `pre > code`
- `.doc-article`
- `**输入**` / `**输出**`

我们重构后的页面是：

- `div.codehilite > pre`
- 用 `h3: Java 实现 / Python 实现` 区分语言
- 样例结构也不同

所以不管用不用 CheerpJ，bridge 都要重写；CheerpJ 并不能省掉这层适配。

### 7. 并非真正的“服务器实跑”

CheerpJ 是浏览器运行，不是服务器 Java：

- 不能使用服务器上的 JDK、Maven 依赖、文件系统、环境变量；
- 不能复用服务器上的 Java 生态；
- 对带数据库/文件/本地库的 Java 题不友好；
- 只适合简单 stdin/stdout 算法题。

## 四、CheerpJ 仍然适合的场景

- 纯个人自用，不想写任何后端代码；
- 希望代码不上传服务器，隐私更好；
- 静态站点部署，没有服务器；
- 偶尔运行 Java 简单算法题，不介意外层启动等待；
- 可以接受 CheerpJ 免费授权条款。

## 五、为什么我们更推荐服务端 Java

你明确说服务器允许安装 Java，那么：

1. **OpenJDK 17 是真正 JVM**，没有浏览器兼容问题；
2. 首次运行只需 JVM 启动，不需要下载几十 MB 运行时；
3. 可以用 `javac`/`java` 标准工具链，支持真实 Java 17；
4. 输出、超时、内存、日志都在服务端可控；
5. 不需要 CheerpJ 授权，不需要维护自定义 runner jar；
6. 和现有 FastAPI / 登录体系更容易集成。

代价是要做安全隔离：

- 只允许自己/管理员；
- 限时、限内存、临时目录；
- 不要以 root 直接运行；
- 最好用独立低权限用户或容器。

## 六、最终选型

### 如果只是个人学习、代码不上传服务器

可以用 **CheerpJ 原方案**，但建议：

- 只抄 Python/Java playground 前端；
- 更新 CheerpJ 5.0 并核对授权；
- 自行验证移动端和首次加载时间；
- 注意 `acm-bridge` 仍需按我们页面重写。

### 如果希望稳定、可维护、和服务器环境结合

**推荐服务端 Java**：

- 前端抄 `acm-playground` 的 UI；
- Python 用现有 `.venv`；
- Java 安装 OpenJDK 17；
- 新增 `/api/practice/run`；
- 只允许自用/登录用户。

这也是我建议的最终施工方向。
