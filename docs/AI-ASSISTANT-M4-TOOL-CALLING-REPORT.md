# InterviewForge AI Assistant M4 Tool Calling 报告

## 1. 范围与提交

M4 采用分阶段实现，每阶段独立提交并推送：

| 阶段 | 内容 | Commit |
|---|---|---|
| M4-A | Durable Tool Infrastructure：契约、注册表、策略、运行时、审计 | `2ea37e1` |
| M4-B | 三个只读内置工具与业务数据适配 | `abb353c` |
| M4-C | Chat 编排、LangChain tool binding、SSE 工具事件 | `9dbc54e` |
| M4-D | 安全边界、确定性评估、循环/并发 hardening | `9961f9d` |

本报告随后作为文档提交。最终仓库 HEAD 以报告提交后的 `git rev-parse HEAD` 为准，避免在报告中制造自引用 commit SHA。

本阶段未部署 VPS，未修改数据库 schema 以外的生产数据，未修改笔记、Hot100 或课程内容。

## 2. 最终架构

```text
ChatService
  └─ ToolOrchestrator
       ├─ LangChain adapter（bind_tools / chunk normalization）
       ├─ ToolRegistry（每个 ChatService 实例独立）
       ├─ ToolRuntime（参数校验、超时、缓存、审计）
       └─ ToolPolicy（轮次、次数、并发、结果大小上限）
             └─ builtins: problem / learning / weather
```

工具层不反向依赖 Router；工具通过 `ToolExecutionContext` 接收当前认证用户、会话、回合和服务端已准备的上下文。模型只能提出工具名和参数，不能注入 `user_id`、数据库路径、文件路径或任意执行入口。

LangChain 只负责模型绑定与消息形状适配，业务执行仍由 InterviewForge 自己的 `ToolRuntime` 管理。没有引入 AgentExecutor、LangGraph、MCP、RAG 或 Memory。

## 3. Durable Tool Infrastructure

`interview_forge/ai/tools/` 提供：

- `contracts.py`：`ToolKind.READ/ACTION`、`ToolSpec`、执行上下文、结果和审计结构。
- `registry.py`：显式注册、重复名称拒绝、模型 schema 导出。
- `policy.py`：默认轮次、调用次数、并发读工具数、结果 token 预算、重复调用上限。
- `runtime.py`：Pydantic 参数校验、未知字段拒绝、超时、结果大小限制、只读缓存、错误归一化和 metadata-only 审计。
- `langchain_adapter.py`：LangChain tool schema、`bind_tools`、流式 chunk 与 tool-call 累积，隔离第三方消息类型。
- `db/ai_schema.py`：`chat_tool_runs` 表及索引，仅持久化调用元数据和错误摘要。

当前默认策略的关键限制为：最多 3 轮、单回合最多 6 次工具调用、最多并行 3 个只读工具、重复相同调用最多 2 次、工具结果总预算 3500 token。同步工具 handler 通过线程池执行，避免阻塞事件循环；取消会向下传播并写入取消状态。

## 4. 当前只读工具

| 工具 | 类型 | 参数 | 数据来源 | 默认超时 | 结果预算 |
|---|---|---|---|---:|---:|
| `get_problem` | READ | `problem_id` 或查询文本 | 正式题目目录、站内链接映射 | 2 秒 | 700 |
| `get_learning_context` | READ | `task`、可选 `problem_id` | `LearningContextProvider` 与 Context Compiler | 6 秒 | 1500 |
| `get_weather` | READ | 可选城市 | 现有天气/geocoder 服务 | 8 秒 | 700 |

工具结果经过紧凑投影，不返回题解正文、完整学习原文、第三方天气原始 payload 或浏览器操作指令。`get_problem` 只返回题目元数据和链接，不打开浏览器、不执行命令、不访问任意 URL。

动作工具目前没有注册；`ToolKind.ACTION` 和 `requires_confirmation` 已存在于契约和运行时中，未来接入时必须经过确认边界，不能沿用只读工具的自动执行路径。

## 5. 安全边界

- 用户身份由当前服务端认证会话和 `ToolExecutionContext.user_db` 决定，模型不可自行传入身份或数据库位置。
- 参数模型统一使用额外字段拒绝，防止模型把未声明的控制字段混入工具参数。
- 工具执行异常只返回稳定的错误码和面向用户的摘要；审计不记录学习原文、完整工具结果、token、密码、Cookie 或 trace。
- 读取天气时，当前用户位置只来自服务端已加载的用户数据；显式城市仍会经过现有城市/geocoder 服务。
- 工具结果始终作为 `role=tool` 数据回填，回归测试确认结果中的提示注入文本不会升级为 system/user 指令。
- 达到调用、轮次、重复调用或结果预算上限后，编排器进入 tools-disabled 的最终回答阶段，不再继续请求工具。

## 6. Chat 编排与 SSE

`ToolOrchestrator` 在一次 Chat turn 内循环执行：

1. 绑定工具并流式读取模型输出。
2. 只把普通文本作为 `message.delta` 暴露给前端。
3. 对工具调用发出 `tool.start`，执行完成发出 `tool.done` 或 `tool.error`。
4. 将结构化工具消息回填模型，直到模型产生最终文本或触发预算上限。

已有事件合同保持不变：`message.start`、`message.delta`、`message.done`、`error`。M1-M3 的 SSE heartbeat `: ping` 仍保留，浏览器无需显示。工具完整结果不会直接发送到浏览器，浏览器只收到名称、状态和安全的显示摘要。

如果当前 provider 不支持 `bind_tools`，系统保留原有非工具流式路径，并加入明确的“工具不可用”约束，不伪造实时数据。该降级路径不删除未来 ChatGPT provider 的接入能力。

## 7. 确定性评估用例

新增 `tests/fixtures/ai_tool_selection_cases.json`，固定覆盖：

- 普通问候、TCP 学习问题：不应调用工具。
- “146 是什么题，给我站内链接”：选择 `get_problem`。
- “南京今天天气如何”：选择 `get_weather`。
- 学情概览已有预加载上下文：复用上下文，避免重复调用。
- “对比今天计划和整体弱项”：选择 `get_learning_context`。
- “打开146题”：只返回链接信息，不打开浏览器。

测试同时限制 fixture 查询长度，并检查题目工具源码没有浏览器、子进程或题解正文出口。循环上限、重复调用缓存、取消审计、超时、非法参数、工具结果提示注入和 action/confirmation 不进入普通只读并行批次均有回归覆盖。

## 8. 验证结果

### M4 定向测试

```text
134 passed, 17 subtests passed in 14.24s
```

覆盖 M4 工具契约、运行时、只读工具、编排器、Chat SSE、AI/Analytics、FastAPI contract、legacy compatibility 和 Architecture V2 检查。

### 全量 pytest

```text
206 passed, 17 subtests passed, 1 failed
```

唯一失败是仓库中已有的 `tests/test_learning_analytics_api.py::RealAuthenticationIsolationTests::test_admin_page_quota_and_permanent_admin_contract`：测试期待管理后台出现“重置今日分析次数”，当前页面已有文案为“恢复今日可用次数”。该失败与 M4 工具调用代码无关，本阶段没有越界修改管理后台。

### 其他检查

- `python -m compileall -q interview_forge tests`：通过。
- `.venv-ai` LangChain adapter smoke test：通过；项目专用环境已具备 `langchain`、`langchain-core`、`langchain-openai`、`pydantic`、`tzdata`，无需新增安装。
- `python tools/build_library.py`：通过，37 个模块、736 个章节。
- `python tools/build_html_site.py`：通过，135 个阅读页、25 个视觉页。
- `python tools/build_hot100.py`：通过，100 个题目页，增量构建无非预期页面 diff。
- `python tools/check_hot100.py`：退出码 1，报告仓库原有 4 个内容校验问题；broken links 为 0、warnings 为 0，未由 M4 引入。
- `git diff --check`：通过。

## 9. 已知限制

- 当前只启用三个 READ 工具，没有动作工具和确认 UI。
- 没有开发 Memory、RAG、LangGraph、MCP 或 Tool Calling 以外的 Agent 能力。
- 评估使用 deterministic fake model 和本机 adapter smoke test，没有把真实外部模型网络调用纳入测试。
- 全量测试和 Hot100 check 的既有不一致仍需后续由对应内容/管理后台任务单独处理，不属于本次 M4 收尾范围。

## 10. 变更文件与交接

核心实现位于：

- `interview_forge/ai/tools/`
- `interview_forge/ai/tools/builtins/`
- `interview_forge/ai/chat/tool_orchestrator.py`
- `interview_forge/ai/chat/service.py`
- `interview_forge/ai/chat/prompts.py`
- `interview_forge/ai/chat/learning_context.py`
- `interview_forge/services/weather.py`
- `interview_forge/db/ai_schema.py`

测试与评估位于：

- `tests/test_ai_tools.py`
- `tests/test_ai_tool_orchestrator.py`
- `tests/test_ai_tool_evaluation.py`
- `tests/fixtures/ai_tool_selection_cases.json`
- `tests/test_ai_chat.py`

后续开发者新增工具时，应先定义参数模型和 `ToolSpec`，再注册到独立 registry，并为身份边界、超时、结果预算、错误和 SSE 行为补回归测试；不要从 Router 或前端直接调用工具 handler。

## M4 Final Hardening

本次收尾没有改动 Tool Calling 架构，也没有引入 Memory、Action Tool、RAG、LangGraph 或 MCP。

### 修复项

- 工具调用被 `max_calls_per_turn`、`max_identical_calls` 拦截时，为 assistant 返回的每一个 `tool_call_id` 补齐一个 `role=tool` 安全错误结果；被拦截的调用不会进入 `ToolRuntime`，随后按 assistant tool calls → tool errors → tools-disabled notice → final model call 的顺序继续。
- `max_total_result_tokens` 改为真正的追加前准入预算。按工具返回顺序，只有完整结果适合剩余预算时才进入模型历史；超出预算的结果只进入安全错误消息，完整数据不进入模型消息。运行时审计与 `tool.done` 事件仍保留实际执行信息。
- AI Assistant 前端增加当前回答回合的天气、学习情况、题目信息工具状态；错误只显示后端安全消息，不显示原始 JSON、schema 或 call id。历史消息不回放工具状态，SSE heartbeat 仍被忽略，既有 message 事件合同不变。
- 增加 `scripts/check/ai_tool_smoke.py` 手动真实 provider 检查清单，不自动执行、不包含 API key；覆盖普通问候、题目、天气和学习上下文四条路径。

### 回归与验证

- M4 定向工具、Chat、前端解析测试：`25 passed`。
- AI/Analytics/FastAPI 相关测试：`126 passed, 17 subtests passed`；唯一失败为仓库既有的管理后台文案契约（测试期待“重置今日分析次数”，页面现有“恢复今日可用次数”），未修改本次范围外的管理后台。
- 全量 pytest：`211 passed, 17 subtests passed, 1 pre-existing failure`，失败同上。
- `python -m compileall -q interview_forge scripts tests`：通过。
- `node --check assets/ai-assistant.js`：通过。
- `python tools/build_hot100.py`：通过，100 个题目页保持最新。
- `python tools/check_hot100.py`：通过，broken links 0、errors 0、warnings 0。
- `git diff --check`：通过；build 未产生非预期页面差异。

实现 commit SHA：`816069e`；本报告更新作为紧随其后的文档提交。
