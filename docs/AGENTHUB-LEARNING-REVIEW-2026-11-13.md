# 从本机 AgentHub 借鉴的 Agent 优化（2026-11-13）

## 对照范围

参考仓库为本机 `E:\JAVA\AI+agent\AgentHub`，检查时 HEAD 为 `fd14bafc04979dcb43c1a21c23eb2750046f5797`。只读参考其源码和设计记录，没有修改或运行 AgentHub，没有访问其凭据与业务数据库。

本项目沿用 FastAPI、SQLite、现有模型适配器及操作确认流程。上一轮“新问题不带入无关前文”的相关性选择仍保留；本轮进一步检查上下文进入模型后的多轮工具执行链路。

## 值得迁移的机制

| AgentHub 机制与源码 | 本项目原有缺口 | 本轮选定的改进 |
|---|---|---|
| `packages/agent_runtime/context_budget.py`：mandatory 分类、工具定义计费、交换组准入 | 初次上下文有分区预算，但工具 schema、参数与后续模型请求没有统一最终准入 | 每次实际模型调用前统一计算请求预算，计入工具定义、调用参数、结果 envelope 和输出预留 |
| 同一模块的 `exchange_group` 原子性 | 简单截消息可能留下孤儿 tool observation，或破坏调用与结果的对应关系 | 历史按完整交流组淘汰，当前用户任务及本轮工具交互保留；必须内容放不下则安全拒绝 |
| mandatory current task 与受保护用户原话 | 当前问题还会在准备阶段被固定 token 分区静默截断，可能丢掉末尾的否定词或限制 | 当前问题保留完整原文；无法容纳时明确报告上下文预算不足，不能截掉用户约束后继续回答 |
| `packages/agent_runtime/runtime_config.py` 与工具运行时的有界执行 | 本项目已有轮次、调用数、并发数限制，但等价参数可能以不同文本绕过重复判定，取消时可能遗留并发 task | 重复身份使用服务端校验后的规范参数；取消或关闭时清理本批任务 |
| 显式工具绑定与最小权限 | 传入空 ToolRegistry 会因为布尔判断而被替换为默认全部工具 | 仅未提供 registry 时使用默认值；显式空目录保持禁用工具 |
| `docs/adr/ADR-007-agentversion-resolved-snapshot.md`、`packages/agent_runtime/frozen.py`：非敏感行为身份与规范哈希 | 原 trace 能看到模型、耗时和上下文选择数量，但不易比较两轮是否使用同一输入和配置 | 分开记录准备上下文指纹、非敏感配置指纹、每轮实际准入请求指纹 |
| 共享预算与可替换估算器 | 聊天已经使用多语言估算，但工具结果仍按字符除以三估算，两处语义不一致 | 共用估算实现，保留原公开接口，单工具与累计工具结果计数一致 |

本轮由三个写集互不重叠的编码子代理实现上述改进，主代理负责参考机制筛选、接口约束、代码复核和组合验收。

## 保留现有边界

- 工具模型只能提出操作；ACTION 继续经过现有服务端确认，不能由模型自行批准。
- 参数校验、用户数据库隔离、工具结果不可信、证据与结构化输出校验继续生效。
- 不改变 provider/model 选择、能力门槛、视觉回退或模型允许列表。
- 不因上下文不足切换模型，不增加模型自动重试，不自动重试有副作用操作。
- trace 仅扩展明确的元数据白名单，不记录聊天、工具参数或结果正文。

## 没有直接移植的内容

AgentHub 的 AgentVersion 发布、PostgreSQL checkpoint、租约、审批恢复、独立 worker、Qdrant 和完整实验冻结，适用于它的控制平面和长任务。将它们整体引入本项目会增加数据库、部署和运维复杂度，本轮没有这类需求。

尤其不能把“增加输入指纹”称为“保存了完整可重放快照”：本轮不会保存完整 prompt、秘密配置和工具结果，也没有构造跨进程 exactly-once 保证。

AgentHub 的 `run_budget_ledger.py` 明确描述持久预算原语与集成限制；不将该模块的存在当作其完整账单结算、端到端调用幂等或本项目已具备相同能力的证据。

本轮的 token 数量仍由离线近似估算器得出，不是 provider tokenizer 的严格上界。输出 token 是准入预留量，不表示增加了供应商输出硬限制。取消 asyncio task 也不意味着可以强制停止已经开始的同步线程或外部系统调用。

## 验证记录

实现文件：

- `interview_forge/ai/token_counting.py`：共用多语言估算、规范 JSON 与安全文本裁剪，保留原 token_budget 公开导入路径。
- `interview_forge/ai/chat/request_budget.py`：system/developer、当前任务及本轮完整工具交换属于必须保留的部分；旧历史按 user 轮整体淘汰，孤儿或不完整工具交换明确拒绝。
- `interview_forge/ai/tools/runtime.py`：单工具结果与审计按完整成功 envelope 估算，避免仅统计 data。
- `interview_forge/ai/chat/tool_orchestrator.py`：初轮、后续工具轮、最终工具禁用回答、tooling fallback 均调用准入模块；处理并发取消、默认参数归一与空工具目录。
- `interview_forge/ai/chat/context_builder.py`、`service.py`、`interview_forge/observability/ai_trace.py`：完整当前任务、准备/配置指纹、模型窗口与输出预留传递，以及元数据白名单。

新增行为测试分别位于 `tests/test_ai_request_budget.py`、`tests/test_ai_agent_runtime_governance.py`、`tests/test_ai_agent_input_identity.py`；同时扩展已有工具与编排测试。

最终使用 `E:\python\python.exe` 完成组合验收：

- 全部 `test_ai*.py`，另含聊天历史、操作追问、上下文编译、provider 能力目录/硬化和管理端可观测性：**279 passed，51 subtests passed**，耗时约 37 秒。
- `scripts/check/ai_agent_eval.py`：**51/51** 确定性工具路由 fixture 通过。这检查本地规则、参数和确认契约，不是 51 次真实模型的成功率。
- 全项目 Python `E9/F821` 检查、新模块/新测试的 `F401` 检查均通过。
- 本轮修改文件 `git diff --check`、新增文件尾随空白检查均通过。
- 仅有原有 Starlette TestClient/anyio 弃用警告；没有新增依赖、数据库表或迁移。

行为验收包括：长当前问题末尾约束保留、mandatory 溢出时不调用 provider、完整工具交换淘汰/保留、工具 schema 和完整结果计费、默认参数等价调用防循环、并发取消/异常清理及其他请求隔离、ACTION 串行待确认、显式空工具目录、极小裁剪预算、指纹规范性/变更敏感性与 trace 隐私。

本轮未部署生产，未调用真实付费模型，不以离线测试声称线上回答质量或费用已经改善。

### 输入身份的精确含义

`prepared_context_hash` 表示最终准备 messages 的规范 JSON 身份；`request_fingerprint` 表示当轮实际准入后的消息和工具 schema 身份，两者不能混称为相同阶段。

`config_fingerprint` 来自版本化的非敏感白名单。provider 绑定使用 provider ID、vendor 和能力版本等字段；不保存 endpoint URL。ENV 没有 provider ID 时，明确标记 endpoint 不在身份覆盖范围内。因此它可以辅助定位策略和输入变化，不能单凭该 hash 还原或唯一标识完整外部供应商配置。
