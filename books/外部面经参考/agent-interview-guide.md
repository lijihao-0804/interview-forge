# Agent 面试路线图与资源索引

> 来源：[Zchary1106/agent-interview-hub](https://github.com/Zchary1106/agent-interview-hub)（MIT License）。仅作个人本地学习使用。
>
> 整理原则：**只调整章节层级与排序，问题、答案、代码与追问正文保持原样未改**。

## 导读

从宏观建立备考框架：12 周路线、最新面经索引、海外攻略、GitHub 资源与其他公司面经。

### 出处与许可

- 原始仓库：[Zchary1106/agent-interview-hub](https://github.com/Zchary1106/agent-interview-hub)，许可证 MIT License，仅作个人本地学习使用。
- 本次整合只做层级重组与排序，未改写任何问题、答案与代码正文；原始内容由社区整理，关键结论请回到官方文档或论文核实。

| 章 | 收录内容 |
|---|---|
| 12 周进阶路线 | 12周Agent工程师进阶路线 |
| 面经索引与海外攻略 | 最新AI-Agent面经索引、海外顶级AI公司面试攻略-2026、其他公司面经-快手携程等 |
| GitHub 热门 Agent 资源 | GitHub热门Agent资源整理 |

## 12 周进阶路线

> 面向已经会基础编程、想在 3 个月内补齐 AI Agent / 大模型应用工程能力的人。目标不是“看完资料”，而是每周交付一个可验证产物，最后形成可写进简历、可用于面试答辩的作品集。

---

### 路线总览

| 阶段 | 周期 | 目标 | 交付物 |
|---|---:|---|---|
| 基础夯实 | 第 1-2 周 | 补齐 LLM、Prompt、Tool Calling、RAG 基础 | 个人知识卡片 + 10 个核心概念答案 |
| RAG 工程化 | 第 3-4 周 | 做出可评估、可溯源的 RAG 系统 | 文档问答 Demo + 评估报告 |
| Agent 编排 | 第 5-6 周 | 掌握 ReAct、Plan-and-Execute、LangGraph 状态图 | ReAct Agent + LangGraph 多步任务 |
| 工具与协议 | 第 7-8 周 | 掌握 Function Calling、MCP、权限与沙箱 | 自建 MCP Server + 安全工具调用 |
| 生产化能力 | 第 9-10 周 | 补齐可观测性、评估、成本、部署、安全 | Agent 服务化 + trace + guardrails |
| 面试作品集 | 第 11-12 周 | 完成项目打磨、答辩材料和模拟面试 | 项目 README + 架构图 + 10 分钟答辩稿 |

---

### 第 1 周：LLM 与 Prompt 基础

**学习重点**

- Transformer、Token、Context Window、KV Cache 的基本概念
- System Prompt、Few-shot、结构化输出、JSON schema
- 幻觉、temperature、top-p、模型路由的基本取舍

**必做任务**

1. 用一页纸解释：LLM 为什么会幻觉？RAG 为什么能缓解？
2. 写 5 个结构化输出 prompt：JSON、表格、评分、拒答、引用格式。
3. 准备 10 个常见追问答案：Token、KV Cache、温度、上下文压缩、Prompt 注入。

**验收标准**

- 能不用背稿讲清楚“模型生成不是查库，而是条件概率采样”。
- 能解释结构化输出失败时如何兜底：重试、schema 校验、parser repair、函数调用。

---

### 第 2 周：Tool Calling 与基础 Agent Loop

**学习重点**

- Function Calling / Tool Use 的参数 schema、工具描述、错误处理
- ReAct：Thought → Action → Observation 循环
- 工具权限、危险操作确认、工具结果压缩

**必做任务**

1. 写一个最小 ReAct Agent：支持 `search`、`calculator`、`read_file` 三个工具。
2. 给工具加权限分级：只读、需确认、高危禁止。
3. 记录 5 个失败 case，并写出原因归因。

**验收标准**

- 能说明 Tool Description 为什么影响工具选择准确率。
- 能讲清楚工具失败后的重试、降级和停止条件。

---

### 第 3 周：RAG 最小可用系统

**学习重点**

- 文档解析、chunking、embedding、向量库、检索、生成
- 引用溯源、上下文拼接、TopK 选择

**必做任务**

1. 用 20 篇 Markdown/PDF 做一个本地知识库问答。
2. 输出答案时带引用片段和来源文件。
3. 做 30 条问题的人工测试集。

**验收标准**

- 每个答案能追溯到原文片段。
- 能解释 chunk size / overlap 对召回和幻觉的影响。

---

### 第 4 周：RAG 优化与评估

**学习重点**

- Hybrid Search：BM25 + Dense Retrieval
- RRF 融合、Rerank、Query Rewrite、HyDE
- RAGAS、Recall@K、MRR、NDCG、Faithfulness

**必做任务**

1. 加 BM25 + Dense 双路召回。
2. 加 reranker，并对比 Top5 命中率。
3. 输出一份评估报告：召回、延迟、成本、失败样例。

**验收标准**

- 能说明“召回不到”和“生成不对”如何分层排查。
- 能用指标证明优化是否有效，而不是只说“效果更好”。

---

### 第 5 周：LangGraph 状态图

**学习重点**

- State、Node、Edge、Conditional Edge、Checkpoint
- Graph vs Chain vs Agent Loop 的边界

**必做任务**

1. 用 LangGraph 改写第 2 周 ReAct Agent。
2. 加 `max_iterations`、失败重试、人工确认节点。
3. 让任务中断后可以从 checkpoint 恢复。

**验收标准**

- 能画出 StateGraph 并解释每个节点的输入输出。
- 能说明 checkpoint 恢复如何保证幂等。

---

### 第 6 周：多 Agent 协作

**学习重点**

- Supervisor / Worker、角色分工、共享状态、A2A 通信
- 多 Agent 的协调成本、循环风险、一致性问题

**必做任务**

1. 做一个三角色协作系统：Researcher、Coder、Writer。
2. Supervisor 根据状态决定下一步派谁。
3. 加成本上限、轮次上限和任务完成判断。

**验收标准**

- 能解释什么时候用多 Agent，什么时候单 Agent + 多工具更好。
- 能定位多 Agent 循环、重复工作、上下文污染问题。

---

### 第 7 周：MCP 与工具生态

**学习重点**

- MCP Host / Client / Server / Transport
- MCP 与 Function Calling、Plugin、A2A 的关系

**必做任务**

1. 自建一个 MCP Server：暴露 `search_docs`、`get_doc`、`summarize` 三个工具。
2. 写工具 schema、错误返回格式和权限说明。
3. 用 Claude Desktop / 支持 MCP 的客户端连通。

**验收标准**

- 能解释 MCP 解决的是“工具接入标准化”问题。
- 能说明 MCP Server 的安全边界和认证方式。

---

### 第 8 周：Agent 安全与权限

**学习重点**

- Prompt 注入、工具误调用、数据泄露、越权访问
- Sandbox、policy engine、audit log、human approval

**必做任务**

1. 给工具调用加 policy check。
2. 为危险操作加“先生成计划、用户确认、再执行”的流程。
3. 设计 10 个红队 prompt 并记录拦截结果。

**验收标准**

- 能讲清楚“输入过滤、工具前置检查、输出校验”三道防线。
- 能说明如何审计 Agent 的每次 tool call。

---

### 第 9 周：可观测性与评估

**学习重点**

- Trace、Run replay、日志、指标、告警
- Task success rate、first-pass success、verified success、recovery success
- tool accuracy、路径震荡率、latency、cost、hallucination rate

**必做任务**

1. 给 Agent 加 trace id 和每步状态快照。
2. 输出一次任务执行的 timeline。
3. 构建 50 条回归测试集，统计任务成功率和首次成功率。
4. 注入一次工具超时和进程重启，验证能否从 checkpoint 恢复且不重复执行副作用。

**验收标准**

- 能回答“线上 bad case 怎么定位到是哪一层的问题”。
- 能展示 trace、日志、恢复证据和评估数据。
- 能区分“模型自述完成”和“经过独立验证后完成”。

---

### 第 10 周：部署与成本优化

**学习重点**

- FastAPI 服务化、Docker、队列、缓存、限流、降级
- 模型路由、语义缓存、上下文压缩、batching
- Agent Runtime、任务状态机、租约、幂等键和补偿操作
- 大规模工具注册表、权限过滤、候选检索和 Schema 版本化

**必做任务**

1. 把 Agent 包装成 HTTP API。
2. 加 Redis 语义缓存和限流。
3. 输出延迟、token 成本、缓存命中率三项指标。
4. 将一个有副作用的工具改造成“幂等键 + 执行结果日志 + 安全重试”。
5. 不把全部工具放进 Prompt，先从工具注册表检索 Top-K 候选再交给模型选择。

**验收标准**

- 能说明如何把 demo 变成可运行服务。
- 能解释哪些请求走大模型，哪些走小模型或缓存。
- 能解释 Agent、Orchestrator、Harness 和 Runtime 的责任边界。

---

### 第 11 周：作品集打磨

**学习重点**

- README、架构图、部署说明、评估报告、失败案例复盘

**必做任务**

1. 为项目写一份面试官友好的 README。
2. 准备 3 张图：系统架构图、数据流图、评估闭环图。
3. 写“项目亮点 / 难点 / trade-off / 下一步优化”四段。

**验收标准**

- 面试官不看代码，也能通过 README 明白你的贡献。
- 项目亮点有指标，不只是“用了 LangChain / RAG / Agent”。

---

### 第 12 周：模拟面试与补短板

**学习重点**

- 项目答辩、系统设计、八股追问、代码题

**必做任务**

1. 准备 10 分钟项目答辩稿。
2. 做 3 次模拟面试：项目深挖、系统设计、RAG/Agent 专项。
3. 根据失败题补一页“错题复盘”。

**验收标准**

- 能讲清楚你为什么这么设计，而不是只讲“我用了什么框架”。
- 能回答：效果如何评估？失败怎么办？成本多少？如何上线？

---

### 推荐每周复盘模板

```text
本周主题：
完成产物：
最难的技术点：
遇到的 bad case：
指标结果：
下周改进：
可写进简历的一句话：
```

### 最终作品集清单

- 一个 RAG 知识问答系统
- 一个 LangGraph 多 Agent 协作系统
- 一个带安全护栏和可观测性的生产级 Agent 服务
- 一份项目 README
- 一份评估报告
- 一份 10 分钟项目答辩稿
## 面经索引与海外攻略

> 最近核对：2026-09-11。本文整理自公开网页搜索结果，用作面经入口和复习优先级索引。为避免搬运平台原文，本文只保留来源链接、摘要和考点标签。结构化数据见 [`data/interviews.json`](https://github.com/Zchary1106/agent-interview-hub/blob/main/data/interviews.json)。

### 采集概况

| 来源 | 高质量候选 | 说明 |
|---|---:|---|
| 小红书 | 13 | 时效强，覆盖字节、腾讯、美团、快手、阿里、百度、小红书等一面/二面 |
| GitHub | 14 | 高质量题库和学习资料，适合作为系统复习资料 |
| 牛客 | 24 | 国内大厂面经密度高，适合补充真实面试流程和追问 |
| CSDN / 博客园 / 掘金 | 8 | 适合作为 Agent/RAG 高频题和专题归纳来源 |
| 知乎 | 2 | 适合作为大模型算法实习和海外 AI 面试补充 |
| 海外研究 | 1 | 汇总 OpenAI / Anthropic 公开候选人经历，适合做流程与考察重点对比 |

> 注：小红书搜索结果链接依赖登录态和平台签名，公开静态站直链容易失效。因此本文只保留小红书原标题，阅读时请在小红书站内搜索对应标题。

### 2026-09 最新补充

| 日期 | 公司 | 来源类型 | 标题 | 新增考点 |
|---|---|---|---|---|
| 2026-09-07 | 快手 | 一手复盘（中等置信） | [AI 全栈开发二面凉经（Agent 应用方向）](https://www.nowcoder.com/discuss/926274020192841728) | Agent 项目深挖、Skill、工具使用、全栈交付 |
| 2026-09-04 | 字节跳动 | 一手复盘 | [9.3 Agent 开发一面面经](https://www.nowcoder.com/discuss/925342611194286080) | Harness、长任务延迟、工具可靠性、上下文压缩、结构化评分 |
| 2026-09-03 | 快手 | 一手复盘 | [AI 应用开发 / Agent 开发一面](https://www.nowcoder.com/discuss/925163549431742464) | AI Coding 质量、工具结果缓存、长期偏好、隐私、并发基础 |
| 2026-08-31 | 阿里 | 汇总题源 | [Agent 开发近期面经汇总](https://www.nowcoder.com/discuss/923740641878646784) | MCP Server 评测、Agent Trace、超长任务续跑、Skill 渐进加载、推理基础设施 |
| 2026-08-28 | 字节跳动 | 汇总题源 | [Agent 开发近期面经汇总](https://www.nowcoder.com/discuss/922659050167226368) | Harness/Orchestrator、路径震荡、工具检索、Coding Agent 并发、首次成功率 |
| 2026-08-24 | 字节跳动 | 一手复盘 | [Agent 开发一面（8.12）](https://www.nowcoder.com/discuss/921444774287003648) | RAG、AI Coding 质量、SSE/WebSocket、高并发、索引与线程安全 |

本轮新增考点已整理成独立专题：[2026 AI Agent 工程化新考点](https://github.com/Zchary1106/agent-interview-hub/blob/main/2026-Agent工程化新考点.md)。它只补充本仓库此前缺少或覆盖不足的 Runtime、可恢复执行、路径震荡、规模化工具路由、Trace 和生产级评测，不重复已有 RAG/MCP 基础。

### 2026-08 最新补充

| 日期 | 公司 | 来源 | 标题 | 核心考点 |
|---|---|---|---|---|
| 2026-08-07 | 小红书 | 牛客 | [大模型平台 Agentic 全栈研发练习生一面凉经](https://www.nowcoder.com/feed/main/detail/e5e9311a623940eead6ec98c65e7f9e8) | Harness、编排层、Skill/Tool、LangGraph、模型一致性、扩容 |
| 2026-08-09 | 米哈游 | 牛客 | [AI Agent 开发提前批一面面经分享](https://www.nowcoder.com/discuss/916476300372500480) | AI coding、幻觉治理、Skill/MCP、项目深挖、Agent 评估 |
| 2026-07-22 | 阿里淘天 | 牛客 | [Agent 社招一面面经分享](https://www.nowcoder.com/discuss/909920471301226496) | 多任务冲突、DPO/GRPO、Memory、Skill、多步轨迹奖励 |
| 2026-07-07 | 字节/蚂蚁/腾讯 | 牛客 | [Agent 实习面经](https://www.nowcoder.com/discuss/904029765160497152) | Transformer、RAG、LoRA、训练参数、算法与场景题 |
| 2026-08-06 | OpenAI/Anthropic | Blanked | [28 份公开面试经历对比](https://www.blanked.work/blog/openai-vs-anthropic-interviews) | OpenAI 的规模/可靠性，Anthropic 的安全/价值判断 |

### P0：优先阅读的真实面经

### 字节跳动

| 来源 | 标题 | 核心考点 |
|---|---|---|
| 小红书 | 字节跳动Agent开发岗二面（贼难）（小红书站内搜索原标题） | 多Agent、LangGraph、Skills、上下文工程、Agent评估、SFT |
| 小红书 | 字节 agent开发 1-3面面经 5月（小红书站内搜索原标题） | 豆包场景、长会话、多Agent A2A、Memory、RAG、幻觉治理 |
| 小红书 | 字节跳动AI开发 一面（小红书站内搜索原标题） | AI 应用开发一面 |
| 牛客 | [字节 AI 应用岗面试真题](https://www.nowcoder.com/discuss/882634966025175040) | 法律RAG、工具路由、评测、chunking、rerank |
| 牛客 | [4轮拿下字节Offer！LLM面试题合集](https://www.nowcoder.com/discuss/746382064101908480) | RAG召回排序、Prompt评测、ReAct、LoRA、SFT、Attention、幻觉 |
| 博客园 | [字节 AI Agent 二面（飞连）面试题与参考解答](https://www.cnblogs.com/tuaran/p/20164742) | Tool Calling、bad case、Memory、RAG优化、Agentic RAG |
| CSDN | [字节跳动大模型实习面经：从 Agent 记忆到 RAG 优化](https://gitcode.csdn.net/6a2ccdca10ee7a33f27c07bf.html) | 长短期记忆、Query Rewrite、Hybrid Retrieval、RRF、Rerank、HyDE |
| CSDN | [双非本｜字节跳动飞书团队 RAG 面经](https://devpress.csdn.net/v1/article/detail/151567056) | BGE-M3、Qwen3-Embedding、LoRA、多路召回、父子文档 |
| 牛客 | [字节 Agent 开发一面 90 分钟凉经](https://www.nowcoder.com/feed/main/detail/91c5394e57c14927841d7a86bfe427c2) | 代码 Agent、覆盖率/插桩、查询改写、上下文工程、Skills |
| 牛客 | [字节 Agent 开发实习一面](https://www.nowcoder.com/feed/main/detail/6506d4b4addf447c9a3ae73570c5d00b6) | Memory、上下文压缩、MCP、Skill、OpenClaw、A2A |

### 腾讯

| 来源 | 标题 | 核心考点 |
|---|---|---|
| 小红书 | 腾讯ai应用一面面经（小红书站内搜索原标题） | 多Agent协作、AgentContext、Run Trace、Skills、上下文注入、风控Agent |
| 小红书 | 腾讯 Agent二面凉经带答案（小红书站内搜索原标题） | Agent 二面深挖 |
| 小红书 | 腾讯 ai 应用开发 一面（小红书站内搜索原标题） | AI 应用开发一面 |
| 牛客 | [大模型、Agent面经总结【04/28】腾讯 / 百度 总结](https://www.nowcoder.com/discuss/878600528970735616) | Agent编排、RAG热更新、失败重试、金融安全、LoRA/DPO |
| 牛客 | [腾讯 AI Agent 应用开发一面凉经](https://www.nowcoder.com/feed/main/detail/28edcddf0c204c08b6562a3e6e6b73ae) | Coding Agent、SubAgent、上下文管理、GRPO/QLoRA、AI 工具边界 |

### 阿里 / 蚂蚁 / 淘天

| 来源 | 标题 | 核心考点 |
|---|---|---|
| 小红书 | 淘天AI Agent一面 问麻了（小红书站内搜索原标题） | RAG、BM25、OCR、多Agent State、Checkpoint、MCP、LangGraph、SSE |
| 牛客 | [阿里淘宝闪购 · Agent 算法工程师 · 27届实习一面](https://www.nowcoder.com/discuss/879393838081597440) | Agent框架选型、HITL、风险控制、Memory、AI Coding |
| 牛客 | [5月20日，蚂蚁智能体与大模型应用 一面](https://www.nowcoder.com/discuss/888874988554448896) | 幻觉治理、Skill、Spring AI、Claude Code、混合检索 |
| 牛客 | [Agent 开发面经总结【04/24】阿里巴巴 / 蚂蚁 / 字节跳动 总结](https://www.nowcoder.com/discuss/877151327091027968) | Multi-Agent、RAG、MCP、Function Calling、LangChain/LangGraph |
| 牛客 | [蚂蚁秋招时间线+面经](https://www.nowcoder.com/discuss/800426409796624384) | RAG vs Fine-tuning、Rerank、NDCG、Agent评测、MCP/A2A |
| 牛客 | [淘天 Agent 社招一面面经分享](https://www.nowcoder.com/discuss/909920471301226496) | 多任务训练、DPO/GRPO、Memory、Skill、轨迹奖励 |
| 牛客 | [淘天 Agent 开发日常实习一面](https://www.nowcoder.com/feed/main/detail/566fa6594dcc446a82bd203f139c45c2) | 状态机/Workflow、动态上下文、MCP/Skill、AI coding |
| 牛客 | [淘天大模型 Agent 校招面经](https://www.nowcoder.com/feed/main/detail/78d6c8c30f1741e6b0a1a02d7b4bbfab) | SFT、RAG 评估、DPO/GRPO、工具调度、延迟优化 |

### 美团 / 快手 / 百度 / 京东 / 小红书

| 公司 | 来源 | 标题 | 核心考点 |
|---|---|---|---|
| 美团 | 小红书 | 美团 AI Agent开发 一面面经（小红书站内搜索原标题） | PDF RAG、RAGAS、MCP、ReAct、Rerank、JSON工具调用 |
| 美团 | 小红书 | 美团AI-Agent工程师面经，看看难度（小红书站内搜索原标题） | AI-Agent 工程师面经 |
| 美团 | 知乎 | [Meituan Large Model Algorithm Intern questions](https://www.zhihu.com/en/article/688624199) | RAG项目、指标、Qwen、LoRA、PDF/表格解析 |
| 快手 | 小红书 | 快手AI Agent开发一面（小红书站内搜索原标题） | 父子索引、BM25、Rerank、Memory、Prompt注入防御、RAG评测 |
| 快手 | 小红书 | 快手AI Agent开发实习生面经2026.6.12（小红书站内搜索原标题） | ReAct、多模型API、单/多Agent、RAG优化、算法题 |
| 百度 | 小红书 | 百度 大模型应用开发 一面面经（小红书站内搜索原标题） | 多模态RAG、表格切片、Memory总结、Function Call、语义缓存 |
| 京东 | 牛客 | [京东 Agent开发 暑期一面](https://www.nowcoder.com/discuss/876932752833077248) | 电商RAG、意图识别、Redis向量检索、HNSW、幻觉兜底 |
| 小红书 | 小红书 | 小红书 AI Agent开发一面（小红书站内搜索原标题） | 电商Agent、主从架构、Tool调用、RAG索引、Prompt调试 |
| 小红书 | 牛客 | [大模型平台 Agentic 全栈研发练习生一面凉经](https://www.nowcoder.com/feed/main/detail/e5e9311a623940eead6ec98c65e7f9e8) | Harness、编排层、Skill、模型一致性、LangGraph、扩容 |
| 米哈游 | 牛客 | [AI Agent 开发提前批一面面经分享](https://www.nowcoder.com/discuss/916476300372500480) | AI coding、幻觉治理、Skill/MCP、项目深挖、现场编码 |
| 理想汽车 | 知乎 | [Li Auto Large Model Algorithm Intern experience](https://www.zhihu.com/en/article/680860432) | RAG、数据集规模、SFT、CoT/ToT、部署、vLLM |

### P1：专题题库与高频考点

| 来源 | 标题 | 建议用途 |
|---|---|---|
| CSDN | [AI Agent开发面试高频题曝光！从203篇面经提炼](https://blog.csdn.net/Trb701012/article/details/162102884) | 提炼 Agent 高频题，补充通用题库 |
| 掘金 | [RAG大厂面试题汇总：向量检索、混合检索、Rerank、幻觉处理](https://juejin.cn/post/7652557621874409522) | 补充 RAG 专项题 |
| 掘金 | [2026 最新 AI Agent 岗面试复盘：拿到三个 offer](https://juejin.cn/post/7625576464485842979) | 做 Agent 岗准备策略 |
| 博客园 | [面试 AI Agent 工程师会被问什么？40+ 真题 + 知识图谱全梳理](https://www.cnblogs.com/itech/p/20111938) | 通用 Agent 知识图谱 |
| CSDN | [大模型应用开发面试宝典：22家公司真实面试经验与技术考点总结](https://devpress.csdn.net/v1/article/detail/151832648) | 多公司 LLM 应用岗总结 |

### P2：外部高质量 GitHub 资料

> 这些资源更适合作为“参考资料索引”，不应标记为真实面经。

| 资源 | 价值 |
|---|---|
| [AgentGuide](https://github.com/adongwanai/AgentGuide) | AI Agent开发指南、LangGraph、高级RAG、大模型面试 |
| [ai-agent-interview-guide](https://github.com/bcefghj/ai-agent-interview-guide) | AI Agent 面试全攻略，含题库、项目、简历和系统设计 |
| [LLMForEverybody](https://github.com/luhengshiwo/LLMForEverybody) | 大模型知识与面试准备 |
| [FAQ_Of_LLM_Interview](https://github.com/aceliuchanghong/FAQ_Of_LLM_Interview) | 大模型算法岗面试题含答案 |
| [LLM-Agent-Interview-Guide](https://github.com/Lau-Jonathan/LLM-Agent-Interview-Guide) | 300+ Q&A，字节/阿里/腾讯真题 |
| [AngleMAXIN/llm-application-interview](https://github.com/AngleMAXIN/llm-application-interview) | 多家大厂真实 LLM 应用面试问题 |
| [JavaGuide docs/ai](https://github.com/Snailclimb/JavaGuide/tree/main/docs/ai) | 高可信中文 AI 面试体系 |
| [toBeBetterJavaer AI section](https://github.com/itwanger/toBeBetterJavaer/tree/master/docs/src/sidebar/itwanger/ai) | Agent 258题、大模型333题、RAG+Agent+MCP |
| [wdndev/llm_interview_note](https://github.com/wdndev/llm_interview_note) | 中文 LLM 面试笔记 |
| [RAG-Interview-Questions-and-Answers-Hub](https://github.com/KalyanKS-NLP/RAG-Interview-Questions-and-Answers-Hub) | 英文 RAG 100+ Q&A |
| [Agent Engineering Handbook · 2026](https://github.com/EmberRavager/agent-interview) | Runtime、Durable Execution、Harness、Sandbox、HITL、Tracing 与 Evals |
| [KeepKeen Agent 工程研究笔记](https://github.com/keepkeen/keepkeen.github.io) | 面经证据等级、岗位分型、Coding Agent 源码对比、Benchmark、失败分类与 Agentic RL |
| [kaomian](https://github.com/smile-struggler/kaomian) | 高频题排序、项目拷打链、LeetCode 与 AI 模型手撕题；仅借鉴结构，不复制无许可内容 |
| [AIGC-Interview-Book](https://github.com/WeThinkIn/AIGC-Interview-Book) | AgentOS、AgentOps、企业平台、自进化 Agent 与 Agentic RL；直接复用需遵守 GPL-3.0 |

### 复习优先级

1. **先看公司面经**：字节、腾讯、阿里/蚂蚁、美团、快手、百度。
2. **再刷 RAG 专项**：Chunk、混合检索、Rerank、RAGAS、语义缓存、表格/PDF。
3. **补 Agent 工程化**：LangGraph、State/Checkpoint、Skills、MCP、Tool safety、Run trace。
4. **补 2026 新考点**：Runtime、恢复与幂等、路径震荡、工具检索、Verified Success、Coding Agent 并发冲突。
5. **最后补 LLM 基础**：LoRA/SFT/DPO、KV Cache、推理框架、量化、上下文压缩。

### 入库原则

- 只保留摘要、问题要点和来源链接，不大段复制原文。
- 带明确日期、轮次和个人项目追问的一手复盘优先作为真实面经来源。
- 汇总型文章只用于发现趋势，必须标记为 `aggregation`，不能包装成一手面经。
- CSDN、掘金、知乎中推广内容较多，优先作为题目种子和专题归纳来源。
- GitHub 资源标记为 `reference`，单独作为外部资料索引。
> 覆盖 OpenAI / Anthropic / Google / Meta 等顶级 AI 公司，聚焦 Agent 工程师岗位

---

### 一、各公司特点速览

| 公司 | 岗位重心 | 面试难度 | 特色考察 |
|---|---|---|---|
| **OpenAI** | Agent 产品化，API 生态 | ⭐⭐⭐⭐ | Work Trial + Mission Alignment |
| **Anthropic** | Safety-first Agent | ⭐⭐⭐⭐⭐ | Values 专轮 + Context Engineering |
| **Google DeepMind** | 研究 + 大规模基础设施 | ⭐⭐⭐⭐ | 强算法 + MLOps |
| **Meta AI** | 超大规模系统 + Llama 生态 | ⭐⭐⭐⭐ | 极端规模系统设计 |
| **Microsoft (Azure AI)** | 企业 AI / Copilot 落地 | ⭐⭐⭐ | 工程落地 + 产品感 |
| **初创公司（Cohere/AI21/Mistral等）** | 快速迭代 + 全栈能力 | ⭐⭐⭐ | 广度 + 快速上手 |

---

### 二、2025-2026 最新考察趋势

### 🔥 新增高频考点（2025年后出现）

1. **Context Engineering**（Anthropic 发起，全行业扩散）
   - 不再只考"写好 Prompt"，考察上下文信息架构设计能力
   - 重点：Token Budget 管理、动态上下文组装、信息优先级排序

2. **MCP（Model Context Protocol）**
   - Anthropic 发布后迅速成为行业标准
   - 考察：MCP 架构（Host/Client/Server）、工具标准化、与 Function Calling 的关系

3. **Agentic Coding / AI-Assisted Development**
   - 面试官会问你是否用过 Claude Code / Cursor / Copilot，使用深度
   - 考察：Agent Hooks 机制、Sub-agent 并发、权限管理

4. **Agent Reliability & Determinism（确定性保障）**
   - 企业客户要求 Agent 行为可预测，结果可复现
   - 考察：Guardrails 设计、Structured Output、重试策略、幂等性

5. **Multi-Agent Orchestration**
   - 从单 Agent 到多 Agent 系统
   - 考察：A2A 协议、Supervisor-Worker 模式、状态同步、冲突解决

6. **Loop Engineering（循环工程）**
   - 2026 年新热点：自动化向 Agent 发送指令并迭代验证的系统
   - 考察：如何设计自动化的 Agent 开发-评估-改进循环

### 📉 权重下降的考点

- 基础 Prompt Engineering（已是入门要求，不再单独深考）
- LangChain 基础用法（框架知识降为加分项，原理和设计更重要）
- 单纯的模型微调（产品化 Agent 岗更重视工程能力）

---

### 2026-08 公开候选人经历对比

> 来源：[I collected 28 OpenAI and Anthropic interview experiences](https://www.blanked.work/blog/openai-vs-anthropic-interviews)。该研究汇总了 15 份 OpenAI 与 13 份 Anthropic 公开候选人经历，属于二手研究，不代表官方固定流程。

| 对比项 | OpenAI | Anthropic |
|---|---|---|
| 共同基础 | 生产约束下的编码、调试、测试与系统设计 | 生产约束下的编码、调试、测试与系统设计 |
| 高频延伸 | 规模、失败模式、API 边界、运行可靠性 | 安全、滥用风险、价值判断、不确定条件下的决策 |
| 准备重点 | 说明系统哪里先失败、如何监控和恢复 | 说明技术选择带来的风险、护栏和取舍 |
| 流程观察 | 公开样本中的轮次数分布较分散 | 公开样本中七轮流程出现频率较高 |

**使用建议：**
1. OpenAI 系统设计回答要主动覆盖容量、重试、正确性、可观测性和故障恢复。
2. Anthropic 除工程方案外，要准备安全、使命、滥用风险和意见分歧场景。
3. 不要只刷算法题，应练习在真实约束下实现、调试和解释系统。

---

### 三、OpenAI 面试攻略

### 核心差异化考点

**Work Trial（付费实战）**
- OpenAI 独特环节：给你 $200-500 报酬，完成 5-8 小时真实任务
- 典型任务：实现一个 mini Agent 工具调用系统，或优化现有 Agent Pipeline
- 评估维度：代码质量 > 功能完成度；错误处理 > 路径覆盖

**Mission Alignment（使命对齐）**
必须能回答：
- 你为什么想加入 OpenAI？
- 你怎么理解"确保 AGI 造福全人类"这个使命？
- 你遇到过 AI 安全 vs 用户体验的冲突吗？如何处理？

### 技术备考清单

```
✅ OpenAI Agents SDK 源码阅读（handoff、tracing 机制）
✅ Responses API vs Chat Completions API 差异
✅ Reasoning Models（o-series）：何时用，成本/质量权衡
✅ Realtime API：语音 Agent 的架构设计
✅ 系统设计：高并发 Agent 推理服务
✅ LeetCode 算法：每天1-2题，Medium 为主
```

---

### 四、Anthropic 面试攻略

### 核心差异化考点

**Values Interview（独立1小时）**
Anthropic 是唯一将 Safety 作为独立面试环节的公司。不是考察你背了多少安全知识，而是看你是否真的深入思考过：

- 阅读必读：[Constitutional AI](https://arxiv.org/abs/2212.08073)、[Responsible Scaling Policy](https://www.anthropic.com/rsp-policy)
- 形成自己的观点（不需要与官方完全一致，但要能阐述和辩护）
- 举实际工程中遇到的安全 vs 功能权衡案例

**Context Engineering 深度考察**
- 面试可能会让你在白板上设计一个 System Prompt 的信息架构
- 需要能量化地讨论 Token 分配（例："给 RAG 结果预留 2000 tokens，对话历史最多 5000 tokens..."）

### 技术备考清单

```
✅ Claude API Tool Use 实操（XML 格式 vs JSON Schema）
✅ Extended Thinking：何时启用，对 Agent 决策的影响
✅ MCP 协议全流程：自己实现一个简单的 MCP Server
✅ Context Window 压缩策略：能编码实现
✅ Constitutional AI 论文：理解核心思路，能解释
✅ Claude Code SDK：实际跑一个任务感受 Agent Loop
```

---

### 五、Google（DeepMind / Google AI）面试攻略

### 核心差异化考点

**"Reason with AI"（2025年新要求）**
Google 面试官不只考你手写代码，还会考你如何用 AI 辅助解决工程问题：
- 你会用 Gemini/Copilot 来加速开发哪些部分？
- AI 生成的代码你如何做质量把关？

**MLOps / LLMOps 考察**
Google 规模大，运维是核心：
- 模型 Drift 检测：如何发现模型行为在线上逐渐变化？
- Inference 成本优化：批处理、缓存、模型分级调用
- A/B 测试框架：如何安全发布新 Agent 版本？

**Googleyness 2.0（含 AI Ethics）**
- 行为问题中会加入 Ethical AI 场景题
- 例："你的 Agent 帮用户完成了某个请求，但你后来意识到这可能被用于歧视，你会怎么做？"

### 技术备考清单

```
✅ Gemini API：Function Calling、Grounding（Google Search）
✅ Vertex AI Agent Builder / Agent Engine 基本了解
✅ 强算法基础（比 OpenAI/Anthropic 更强调）
✅ ML System Design：推理服务、特征工程、监控
✅ TensorFlow/JAX 至少了解（Google 内部用得多）
✅ LLMOps：评估、监控、灰度发布方法论
```

---

### 六、Meta（Meta AI）面试攻略

### 核心差异化考点

**极端规模 + Compute Awareness**
Meta 的 AI 产品服务数十亿用户，面试官非常关注：
- 你设计的系统能扩展到多大？
- 每个 LLM 调用的成本是多少？如何优化？
- 如何在 AR 眼镜等边缘设备上运行 Agent？

**Llama 生态深度**
- 了解 Llama 4 系列（Mixture-of-Experts 架构、多模态能力）
- Meta 开源策略：为什么 Meta 要开源模型？对 Agent 生态的影响
- 边缘推理：量化、蒸馏、on-device LLM

**"Design Hybrids"（特有题型）**
- 结合传统数据结构 + AI 增强的系统设计
- 例：设计一个 Thread-safe LRU Cache，然后追问"如果用 LLM 来动态调整缓存策略呢？"

### 技术备考清单

```
✅ Llama 系列模型架构了解（MoE、多模态）
✅ LeetCode：Hard 级别也要能做（Meta 算法考察较难）
✅ 极大规模系统设计：10亿用户的 AI 推荐/助手系统
✅ 边缘 AI：量化、蒸馏基本原理
✅ Meta 产品线了解：WhatsApp AI、Instagram AI、Ray-Ban Meta
```

---

### 七、国内外对比：关键差异

| 维度 | 国内大厂（阿里/字节/腾讯） | 海外顶级（OpenAI/Anthropic） |
|---|---|---|
| **算法考察** | 偏中等，LeetCode Medium | 更难，Medium-Hard，但 Work Trial 实际代码更重要 |
| **系统设计** | 注重工程落地和业务价值 | 注重 AI 特有挑战（推理成本、Safety）|
| **安全理念** | 合规和业务风险为主 | AI Alignment 哲学层面深度考察 |
| **面试风格** | 结构化，八股文成分多 | 开放讨论，考察思考过程 |
| **薪资结构** | 月薪+年终，股权少 | 高 base + 高 RSU，期权潜力大 |
| **工作节奏** | 快，产品迭代压力大 | 快，但更注重质量和安全 |

---

### 八、30天冲刺备考计划（海外公司版）

### 第1-2周：补基础
- 每天 1 道 LeetCode（Medium，Python）
- 读 OpenAI Agents SDK 文档 + 跑 examples
- 实现一个完整的 RAG Agent（向量检索 + 工具调用 + 流式输出）

### 第3周：系统设计
- 每天1道系统设计题（AI Infrastructure 方向）
- 深读 Anthropic 博客：Context Engineering、MCP
- 实现一个简单的 MCP Server

### 第4周：公司定向准备
- OpenAI：研究 Work Trial 典型题型，准备 Mission Alignment 回答
- Anthropic：阅读 Constitutional AI + RSP，准备 Values 面试
- Google/Meta：复习 ML 基础，准备 Googleyness/Behavioral 题

### 每天：
- 保持对 AI Agent 行业新闻的关注（Hacker News、Twitter/X AI 频道）
- 记录1个新学到的 Agent 设计模式或技巧
> 补充：非五大厂的真实面经，扩大求职面

---

### 📌 快手 AI Agent 开发二面
**来源**: 牛客网 2025-03-21

**面试问题（8 道 + 手撕）：**
1. 做 RAG 项目的时候，是怎么评测效果的？有哪些评测维度，具体用到了哪些指标？
2. 项目里的数据集包含什么内容，数据来源、数据格式是怎样的？
3. 如果让你对 RAG 的相关度和回答效果做优化，有什么思路？有没有更体系化的优化方案？
4. 有一千条数据需要做求和处理，这种数据处理场景怎么设计实现？
5. RAG 的性能怎么提升（工程层面或算法层面）？
6. 项目里的上下文是怎么处理的？上下文过长、冗余等问题有什么优化方向？
7. **Agent 的长记忆和短记忆之间，怎么做到协同工作的？两者的衔接逻辑是什么？**
8. 有什么思路能让自己做的 Agent 更智能？

**手撕代码**：全排列

---

### 📌 携程 AI Agent 开发二面
**来源**: 牛客网 2025-03-23

**面试重点**：
1. Agent 项目完整链路讲解：用户问题 → 意图识别 → query 改写 → 判断走纯 RAG / RAG+Tool / 多 Agent workflow → 混合召回 → rerank → LLM 生成 → 附引用和置信度
2. 二面追问：每一层为什么这么设计？哪一层最容易出问题？

---

### 📌 比心 Agent 一面
**来源**: 牛客网 2025-03-20

**考察内容**：
- AI 技术理解：Skill 概念、MCP vs Function Calling、Transformer QKV
- RAG 向量库：PGVector vs Milvus 选择
- 文档转向量库流程
- 怎么把文档转换成向量库？

---

### 📌 京东 Agent 开发暑期一面（2026）
**来源**: [牛客公开页面](https://www.nowcoder.com/discuss/876932752833077248)

**核心考点：**
1. Agent workflow 如何拆分和编排
2. 电商 RAG 知识库怎么设计
3. 意图识别如何评估
4. Redis 向量检索、HNSW 索引如何解释
5. 幻觉兜底和转人工策略

---

### 📌 理想汽车大模型算法实习面经
**来源**: [知乎公开页面](https://www.zhihu.com/en/article/680860432)

**核心考点：**
1. 完整 RAG 输入输出链路
2. 数据集规模、SFT 与部署效率
3. CoT / ToT 的适用边界
4. vLLM 等推理框架如何提升部署效率
5. RAG 项目上线后遇到的问题如何复盘

---

### 📌 米哈游 AI Agent 开发提前批一面（2026-08）

**来源**：[牛客公开页面](https://www.nowcoder.com/discuss/916476300372500480)

**核心考点：**
1. AI coding 如何划分人机边界并设置质量门禁
2. 模型幻觉、事实性和忠实度如何分层治理
3. Skill 与 MCP 的职责边界和组合方式
4. Agent 项目如何说明状态、工具、可靠性与评估指标
5. Memory、RAG、工具调用和多步奖励如何设计
6. Python 装饰器与数据筛选类现场编码

> 该来源包含较完整的答题解析，适合作为复习材料；阅读时仍需结合自身项目经验组织答案。

---

### 💡 关键观察

当前 Agent 岗位已不限于大厂，携程、快手、比心等公司都在招。面试核心一致：
- **RAG 全链路**是必考
- **Agent 记忆机制**是高频难点
- **项目实操能力**比理论更重要
## GitHub 热门 Agent 资源

> 整理于 2026-03-28，收录 GitHub 上与 AI Agent 开发、面试、学习最相关的高星仓库。

---

### 一、面试 & 面经专项仓库

### 1. datawhalechina/hello-agents ⭐ 31.7K
- **链接**：https://github.com/datawhalechina/hello-agents
- **简介**：《从零开始构建智能体》，DataWhale 出品的智能体原理与实践教程
- **亮点**：从基础到进阶，附带面试问题总结和参考答案（Extra-Chapter 目录下）
- **适合**：系统学习 Agent 开发 + 面试复习

### 2. adongwanai/AgentGuide ⭐ 3.0K
- **链接**：https://github.com/adongwanai/AgentGuide
- **简介**：AI Agent 开发 × 面试求职一站式解决方案，对标 JavaGuide
- **亮点**：LangGraph 实战、高级 RAG、1000+ 面试题、真实面经案例集锦、大厂面经分类
- **适合**：Agent 工程师求职的"圣经级"仓库

### 3. Lau-Jonathan/LLM-Agent-Interview-Guide ⭐ 153
- **链接**：https://github.com/Lau-Jonathan/LLM-Agent-Interview-Guide
- **简介**：大模型 & Agent 面试八股文完全指南
- **亮点**：包含字节、阿里、腾讯等大厂真题，结构化整理
- **适合**：快速过一遍面试八股

### 4. summerjava/Awesome_Agent_Dev ⭐ 184
- **链接**：https://github.com/summerjava/Awesome_Agent_Dev
- **简介**：AI Agent 工程师学习面试大全（Agent Dev Roadmap）
- **亮点**：作者亲自面试获取的第一手面经，含学习路线图
- **适合**：想看真实面试反馈的同学

### 5. llmgenai/LLMInterviewQuestions ⭐ 1.7K
- **链接**：https://github.com/llmgenai/LLMInterviewQuestions
- **简介**：100+ 道 LLM 面试题，来自头部公司
- **亮点**：覆盖 Transformer、微调、RAG、推理优化等核心考点
- **适合**：LLM 基础知识快速复习

### 6. alexeygrigorev/ai-engineering-field-guide ⭐ 1.9K
- **链接**：https://github.com/alexeygrigorev/ai-engineering-field-guide
- **简介**：AI 工程面试实战指南，覆盖面试流程、笔试题、系统设计
- **亮点**：真实公司的 take-home 挑战和面试流程拆解
- **适合**：了解海外 AI 工程师面试流程

### 7. alirezadir/machine-learning-interviews ⭐ 8.0K
- **链接**：https://github.com/alirezadir/machine-learning-interviews
- **简介**：ML/AI 技术面试指南
- **亮点**：2025 新增 Agentic AI Systems 专题，系统设计部分很强
- **适合**：ML 基础 + Agent 方向双修

---

### 二、Agent 知识库 & 学习资源

### 8. NirDiamant/genai_agents ⭐ 20.8K
- **链接**：https://github.com/NirDiamant/genai_agents
- **简介**：各类 GenAI Agent 技术的教程和实现合集
- **亮点**：每个 Agent 模式都有完整教程 + 代码实现，从 ReAct 到多 Agent 协作
- **适合**：边学边写代码，面试前快速上手各种 Agent 模式

### 9. e2b-dev/awesome-ai-agents ⭐ 26.9K
- **链接**：https://github.com/e2b-dev/awesome-ai-agents
- **简介**：AI 自主 Agent 项目大全
- **亮点**：收录了几乎所有主流 Agent 项目，按类别分类（编程、研究、数据分析等）
- **适合**：了解 Agent 生态全貌，面试时聊行业认知

### 10. ashishpatel26/500-AI-Agents-Projects ⭐ 27.4K
- **链接**：https://github.com/ashishpatel26/500-AI-Agents-Projects
- **简介**：500 个跨行业 AI Agent 用例集合
- **亮点**：按行业分类（金融、医疗、教育、客服等），每个都有开源链接
- **适合**：找项目灵感、了解 Agent 的实际落地场景

### 11. VoltAgent/awesome-ai-agent-papers ⭐ 399
- **链接**：https://github.com/VoltAgent/awesome-ai-agent-papers
- **简介**：2026 年 AI Agent 研究论文精选
- **亮点**：覆盖多 Agent 协调、记忆与 RAG、工具使用、评估、安全等核心主题
- **适合**：面试前看几篇论文提升深度

---

### 三、核心框架（面试必知必会）

| 框架 | Stars | 一句话定位 | 面试重点 |
|------|-------|-----------|---------|
| [LangChain](https://github.com/langchain-ai/langchain) | 131K | Agent 工程平台，最主流的 LLM 应用框架 | Chain/Agent/Tool 架构、LCEL、与 LangGraph 的区别 |
| [AutoGen](https://github.com/microsoft/autogen) | 56K | 微软多 Agent 对话框架 | 多 Agent 编排、对话模式、代码执行沙箱 |
| [CrewAI](https://github.com/crewAIInc/crewAI) | 47K | 角色扮演式多 Agent 协作 | Agent/Task/Crew 三层抽象、角色定义、任务分配 |
| [LangGraph](https://github.com/langchain-ai/langgraph) | 10K+ | 基于图的 Agent 编排框架 | State/Node/Edge、循环控制、Human-in-the-loop |
| [Dify](https://github.com/langgenius/dify) | 114K+ | 生产级 Agent 工作流平台 | 可视化编排、RAG 集成、API 部署 |
| [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) | 18K | OpenAI 官方 Agent SDK | Handoff、Guardrails、Tracing |
| [Google ADK](https://github.com/google/adk-python) | 16.8K | Google Agent 开发套件 | 与 Gemini 集成、多 Agent 协调 |

---

### 四、推荐学习路径

### 面试冲刺（1-2 周）
1. **AgentGuide** → 过一遍面试题库和大厂面经
2. **hello-agents** → 看面试问题总结 + 参考答案
3. **LLM-Agent-Interview-Guide** → 八股文查漏补缺
4. 我们的 **agent-interview-hub** → 9 家大厂真实面经 + 300 道题

### 深度学习（3-4 周）
1. **genai_agents** → 每个 Agent 模式写一遍代码
2. **awesome-ai-agent-papers** → 精读 3-5 篇核心论文
3. 动手用 LangGraph + CrewAI 各做一个项目
4. 看 **500-AI-Agents-Projects** 找行业场景灵感

---

### 五、我们的优势对比

| 维度 | agent-interview-hub（本仓库） | AgentGuide | hello-agents |
|------|------|-----------|-------------|
| 大厂覆盖 | 9 家（阿里/字节/百度/腾讯/小红书/美团/蚂蚁/华为/快手） | 多家但非系统化 | 无 |
| 真实面经 | ✅ 牛客实录 | ✅ 案例集 | ❌ |
| 项目实战模板 | ✅ 3 个完整项目（RAG/多Agent/生产级） | ✅ LangGraph 实战 | ✅ 教程项目 |
| 答案完整度 | ✅ 300+ 题全带答案 | ✅ | 部分 |
| 学习路线 | ✅ 16 周计划 | ✅ | ✅ |
| 在线浏览 | ✅ GitHub Pages | ✅ 文档站 | ❌ |

---

> 💡 **建议**：把 AgentGuide 和 hello-agents 作为补充资料，它们在 LangGraph 实战教程和基础原理讲解上比我们更详细；我们的强项是大厂针对性面经和系统设计题。
