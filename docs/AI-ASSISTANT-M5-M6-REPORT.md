# InterviewForge AI Assistant：M5–M6 完成报告

> 状态：M5 Long-term Memory 与 M6 Safe Action Tools 已按顺序完成。M1–M4 的既有架构保持冻结；本轮未部署 VPS、未引入 Vector DB/Redis/LangGraph/MCP/RAG，也未开发 Memory 以外的 Agent 能力。

## 1. 提交记录

| 阶段 | Commit | SHA |
|---|---|---|
| M5 Long-term Memory | `feat: add long-term assistant memory` | `80f7515` |
| M6 Safe Action Tools | `feat: add confirmed assistant action tools` | `561529e` |
| 最终报告提交 | 本报告 | 待提交 |

M5 与 M6 保持为两个独立 milestone commit。报告提交只包含文档，不回写或合并前两个 milestone。

## 2. M5 Long-term Memory

### 实现范围

- 新增 `user_memories` SQLite 表和 active-key 索引，按用户数据库隔离。
- 新增 `interview_forge/ai/memory/`：contracts、policy、extractor、store、retriever、context。
- 记忆类型为 preference、goal、constraint、learning_context；区分 explicit/inferred，并支持 active/superseded 生命周期。
- 同一 canonical key 更新时旧记录进入 superseded；用户删除记忆执行真实 DELETE，不只是隐藏。
- 提取前置 worthiness gate 与敏感信息策略，拒绝密码、API key、Cookie、Token、`LEETCODE_SESSION`、CSRF、Authorization、凭据和路径等内容。
- 使用现有 AI provider 的结构化输出能力作为补充提取路径；无必要时先走确定性低成本规则，失败时 graceful degradation。
- 检索不使用 embedding：采用确定性文本相关度、重要性、置信度和新鲜度排序，限制为少量条目和约 800 token 预算。
- 新增 `ContextBlock` 接缝，Learning Context 与 Memory 都作为不可信上下文注入，不能覆盖 system policy 或触发操作。
- 每轮成功对话后异步尝试记忆提取；记忆失败不影响正常回答，并只记录异常类别等安全 telemetry。

### API 与前端

- `GET /api/chat/memories`：查看当前用户的长期记忆。
- `DELETE /api/chat/memories/{memory_id}`：删除当前用户自己的记忆。
- AI Assistant 页面增加简单记忆查看与删除入口，不显示敏感原文，不允许客户端指定其他用户。

## 3. M6 Safe Action Tools

### 安全执行链路

- 新增 `chat_action_requests` SQLite 表，状态包括 pending、executing、succeeded、failed、cancelled、expired。
- 复用现有 ToolSpec/ToolKind/ToolRuntime；ACTION 工具先创建 pending request，模型调用阶段不执行 handler。
- `tool.confirmation_required` SSE 事件携带 action id、展示名称、确认文本和过期时间；不向前端展示原始参数。
- 确认接口只接受空 JSON，由服务端读取已保存的 canonical arguments；取消和确认均校验用户数据库、状态和过期时间。
- `pending → executing` 使用带状态条件的原子抢占；只有真正抢到请求的确认者可以执行，重复确认不会再次调用 handler。
- 当前唯一 ACTION 是 `sync_leetcode`，支持 `full: bool`，复用既有凭据和 `start_leetcode_sync_task`/TaskManager；测试不发起真实网络同步。
- 结果写回安全元数据和审计记录；ACTION 不使用 READ tool cache。

### API 与前端

- `GET /api/chat/sessions/{session_id}/actions?status=pending`：刷新会话时恢复待确认操作。
- `POST /api/chat/actions/{action_id}/confirm`：确认执行。
- `POST /api/chat/actions/{action_id}/cancel`：取消执行。
- 前端增加确认卡片、成功/失败/取消状态和刷新后待处理操作恢复；模型不能自行确认，也不能在确认前声称操作成功。

## 4. 测试与验证

| 命令 | 结果 |
|---|---|
| M5/M6 定向 AI、Memory、Action、Tool、Frontend 测试 | 38 passed |
| `python -m pytest -q` | 224 passed，17 subtests passed，1 个既有失败 |
| `python -m compileall -q interview_forge tests` | passed |
| `node --check assets/ai-assistant.js` | passed |
| `python -m scripts.build.build_html_site` | passed，无非预期工作区变更 |
| `python -m scripts.build.build_hot100` | passed，100 个题目页面保持最新 |
| `python -m scripts.check.check_hot100` | passed；`broken_links=0, errors=0, warnings=0` |
| `git diff --check` | passed；仅有 Windows 换行提示 |

全量测试唯一失败为既有的 `tests/test_learning_analytics_api.py::RealAuthenticationIsolationTests::test_admin_page_quota_and_permanent_admin_contract`：旧测试要求管理员页面包含“重置今日分析次数”，当前页面实际使用“恢复今日可用次数”。本轮没有修改管理员页面，该失败与 M5/M6 无关。

新增回归覆盖：记忆生命周期、替换、真实删除、敏感信息过滤、低价值门控、跨会话隔离、检索预算、记忆失败降级；ACTION pending 不执行、确认执行、取消、过期、参数篡改保护、跨用户隔离、重复确认 exactly-once、缺少 LeetCode 凭据安全失败；SSE confirmation event、前端确认卡片与待处理恢复。

## 5. 行为与边界确认

- 既有 M1–M4 Chat/SSE message contract 未改；新增的 memory/action API 与 `tool.confirmation_required` 事件是向后兼容的增量能力。
- 未修改既有业务表结构；只新增 AI Assistant 自有表，旧数据按幂等初始化兼容。
- 未改变现有 LeetCode 同步算法、TaskManager、AI provider、认证隔离或 READ tool 行为。
- 未引入 Tool Calling 之外的 Memory 以外能力：没有 Vector DB、Redis、LangGraph、MCP、RAG、AgentExecutor、多 Agent 或真实测试网络副作用。
- 本轮未部署 VPS；GitHub push 在最终报告提交后执行。

## 6. 结论

M5 完成了有边界、可删除、可隔离、预算受控的长期记忆；M6 完成了服务端确认、原子状态机和 exactly-once 语义的安全操作工具层。M1–M6 现已完成本轮开发目标，后续不自动扩展新的 Agent 能力。

## M5 Final Hardening

本次只收尾 M5，不重构 M5/M6，不修改 M6 Tool Runtime、Action state machine、`sync_leetcode`、Learning Context Compiler 或无关前端 UI。

### 修复项

- **ContextBlock priority admission**：`ContextBuilder` 在 system budget 内按 priority 降序做 block admission。Learning Context（90）先于 Memory（80）和其他普通上下文进入预算；低优先级 block 不会因为先 append 而挤掉高优先级 block，并在 `last_build` 中记录实际 admitted block。
- **Extractor routing**：保留 deterministic fast path，但仅处理可可靠解析的简单表达；复杂但 memory-worthy 的表达进入现有 structured extractor；普通消息不会调用 extractor。所有候选仍统一经过 `MemoryPolicy`。
- **canonical_key refinement**：确定性路径改用 `preference.explanation_order`、`preference.programming_language`、`constraint.daily_study_minutes`、`goal.target_role` 等具体语义 key；provider 粗粒度 key 会被策略层规范化，互不相关的长期事实不再无故互相 supersede。
- **Explicit persistence semantics**：识别显式“记住/忘记”请求后，先完成 candidate → policy → store，再允许模型回答。服务端以 `MemoryPersistenceResult` 和可信 ContextBlock 告知本轮持久化状态；保存失败时直接返回“这次没有成功保存该记忆”，禁止伪装已保存。显式 forget 成功也在回答前完成；inferred memory 仍保持 post-turn graceful degradation。

### 新增回归测试

- 高预算不足时 Learning Context 优先于 Memory。
- 不同 preference 同时 active；同一 canonical key 的新值仍 supersede 旧值。
- 复杂 memory-worthy 消息确实调用 structured extractor，普通消息跳过 extractor。
- explicit save 成功后才生成回答并把 `persistence_success=true` 注入模型上下文。
- explicit save 失败不得出现“已记住”；explicit forget 成功后记忆已删除；inferred extractor 失败不影响 Chat 完成。

### 验证与提交

| 命令 | 结果 |
|---|---|
| M5 定向 Memory/Context 测试 | 17 passed |
| M1–M4 AI + M5/M6 相关测试 | 127 passed，11 subtests passed |
| 全量 `python -m pytest -q` | 230 passed，17 subtests passed，1 个既有管理员文案失败 |
| `python -m compileall -q interview_forge tests` | passed |
| `node --check assets/ai-assistant.js` | passed |

M5 Final Hardening implementation SHA：`e7183fd`。
