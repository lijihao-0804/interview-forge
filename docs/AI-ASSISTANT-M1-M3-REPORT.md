# InterviewForge AI Assistant V1：M1–M3 事实报告

> 状态：M1–M3 已完成；以下记录实现、前端动画整合、Markdown→HTML 构建和验证事实。本报告随最终整合提交进入 Git。

## 1. Commit SHA

| 阶段 | Commit | SHA |
|---|---|---|
| M1 | `feat: add persistent streaming AI chat foundation` | `6d3843546114406ef444f0e0286fbb1bfc554101` |
| M2 | `feat: add bounded chat context and rolling summaries` | `a055d89165cb5cc5b03befc154e755b6f714168d` |
| M3 | `feat: integrate learning context into AI chat` | `8d7e4f7c7705529d7be9c356fdb7b41ae822e5a9` |
| 最终整合实现 SHA（不含本报告校正提交） | `docs: refresh learning resources and generated site` | `cf502c437e91bce7bec42b4239b31dfad1d1b765` |
| 报告初始提交 SHA | 本报告首次纳入整合提交 | `cf502c437e91bce7bec42b4239b31dfad1d1b765` |

三个 milestone commit 已在本地形成；最终整合提交包含本轮前端动画、笔记资源、生成 HTML 和测试契约变更。本报告随后仅做了 SHA/验证事实校正。

## 2. 目录与调用链

- 页面入口：`pages/ai-assistant.html`、`assets/ai-assistant.js`。
- API 注册：`interview_forge/api/app.py` 注册 `chat_router`；路由实现位于 `interview_forge/api/routers/chat.py`。
- 身份与 DB：路由使用现有 `require_user(request)` 和 `user_db(user)`；客户端不能提供 `user_id`。每个已认证用户使用自己的 per-user SQLite 文件。
- 持久化与流式链路：`chat.py` → `ChatService.stream_reply` → `ContextBuilder.build` → `LearningContextProvider.build`（仅显式学习意图）→ `analytics_cached` → 既有 `compile_learning_context` → Chat projection → 既有 `ai_coach` model factory / `ai/provider.py::stream_chat_chunks` → `runtime/streaming.py::sse_events`。
- 数据库初始化继续走现有 `server_runtime.connect` / `interview_forge/db/ai_schema.py::ensure_ai_schema`；没有修改 `analytics/context_compiler.py`，没有新增 LLM client。

## 3. 新增表、索引与初始化

`interview_forge/db/ai_schema.py` 的幂等 schema/init 新增或确保：

- `chat_sessions(id TEXT PRIMARY KEY, title, created_at, updated_at)`。
- `chat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id, role, content, metadata_json, created_at)`，`session_id` 外键级联到 `chat_sessions`，role 限制为 `user` / `assistant`。
- `chat_session_summaries(session_id TEXT PRIMARY KEY, summary TEXT NOT NULL, through_message_id INTEGER, updated_at TEXT NOT NULL)`，外键级联到 `chat_sessions`。
- `ix_chat_sessions_updated ON chat_sessions(updated_at DESC, id DESC)`。
- `ix_chat_messages_session_id ON chat_messages(session_id, id ASC)`。

旧库通过 `CREATE TABLE/INDEX IF NOT EXISTS` 兼容初始化；未改既有业务表和既有 analytics compiler。

## 4. API 与 SSE contract

- `POST /api/chat/sessions`：认证后创建空会话，首条 user message 才生成截断 title，不调用模型。
- `GET /api/chat/sessions`：只返回当前认证用户的会话列表。
- `GET /api/chat/sessions/{session_id}/messages`：只返回当前用户会话的历史。
- `POST /api/chat/sessions/{session_id}/stream`：请求体严格为 `{ "message": "..." }`；空消息、超长消息、无效 session 和重复生成按现有错误风格处理。
- 流响应为 `text/event-stream`，并设置 no-cache/no-transform、keep-alive、`X-Accel-Buffering: no`。每个 frame 的 `data` 是可解析 JSON，事件顺序为：
  1. `message.start`：`{"message_id": ...}`
  2. 零个或多个 `message.delta`：`{"delta": ...}`
  3. 成功时 `message.done`：`{"message_id": ..., "usage": ...}`
  4. 失败时 `error`：`{"code": ..., "message": ...}`；provider 失败不泄露内部异常细节。
- user turn 在生成前保存；assistant 只在完整流成功后保存。取消/断开时关闭 stream，不伪造完整 assistant。

## 5. ChatContextBuilder 与预算

`interview_forge/ai/chat/context_builder.py` 负责历史拼接，`token_budget.py` 集中预算和可替换 `TokenEstimator`：

1. system prompt；
2. 已有 rolling summary（如有）；
3. 在 recent budget 内的最近原文消息；
4. 当前 user message（只追加一次）。

默认预算为 summary 1200、recent 5000、system 700、current 800、output 1200 tokens。无 tokenizer 时使用集中定义的 conservative fallback（按约 3 字符/token 向上取整），业务代码没有散落 4 chars=1 token。历史超过 recent budget 才生成增量摘要；摘要带固定“不是长期 Memory”边界和 `through_message_id`，只吸收新进入摘要区的旧消息，重启后从 `chat_session_summaries` 恢复。provider 有真实 token usage 时保留真实值；无 input token 时 telemetry/usage 标记为估计值，不冒充真实 token。

## 6. Learning Context 接入

`interview_forge/ai/chat/learning_context.py` 的 `LearningContextProvider.build(*, user_db, query)` 只对明确 selector 命中时读取 analytics/compiler：

| 查询特征 | compiler task | chat budget |
|---|---|---|
| `今天做什么` / `今天复习什么` / `今日计划` | `today_plan` | small |
| `最近状态` / `我的弱项` / `最近学得怎么样` | `learning_diagnosis` | medium |
| `学习路线` / `接下来学什么` | `learning_route` | medium |
| 明确题号 + `复习` / `为什么错` / `掌握情况` | `problem_review`（保留题号） | medium |

`你好`、`解释TCP` 等普通闲聊返回 `None`，不调用 analytics/compiler。compiler 接收空 `user_request`，因此原始 query 不重复进入模型 context。`context_projection.py::project_learning_context_for_chat` 只保留 diagnostic digest、allowlisted selected facts、signals/anomalies、related problem facts、data quality 和必要 profile；trace map、evidence/metric metadata、debug/internal IDs 留在服务端。Chat wrapper 明确声明 Learning Context 是不可信 contextual data，不是 system instruction，不可改规则或触发写操作；data quality 不足时要求模型如实说明。

## 7. 测试与验证事实

| 命令 | 结果 |
|---|---|
| `pytest -q tests/test_ai_chat.py tests/test_architecture_v2.py` | 6 passed |
| `pytest -q tests/test_ai_chat_context.py tests/test_ai_chat.py tests/test_architecture_v2.py` | 9 passed |
| `pytest -q tests/test_ai_chat_learning_context.py` | 5 passed in 0.42s |
| `pytest -q tests/test_ai_chat_learning_context.py tests/test_ai_chat_context.py tests/test_ai_chat.py tests/test_ai_coach.py tests/test_context_compiler.py tests/test_learning_analytics.py tests/test_learning_analytics_api.py tests/test_fastapi_routes.py` | 134 passed, 17 subtests passed, 1 failed |
| `pytest -q` | 182 passed, 17 subtests passed, 1 failed |
| `python -m compileall -q interview_forge tests` | passed |
| `python tools/build_library.py` | passed；`Library modules: 37; chapters: 736` |
| `python tools/build_html_site.py` | passed；`HTML pages rebuilt: 123 (of 135); HTML reading pages: 135; visual pages polished: 25` |
| `python tools/build_hot100.py` | passed；`problem_pages=100`，`original_unique_ids=99`，`added_ids=[226]`，`source_variants=107` |
| `python tools/check_hot100.py` | exit 1；统计 `problem_pages=100, unique_ids=100, topic_pages=17, visuals=25, markdown_files=358, html_files=844, reader_pages=771, math_formulas=228, broken_links=0, errors=4, warnings=0`；剩余 4 项为 3 个既有内嵌演示检查和 1 个源笔记/课程页 Mermaid 数量差异 |
| `git diff --check` | passed；仅有 Windows LF/CRLF 提示，无空白错误 |
| `python -m pytest -q`（前端动画整合后） | 182 passed, 17 subtests passed, 1 failed |
| smoke 替代命令：M1 persistence/history + M2 long summary + M3 final-context integration 三个定向测试 | 3 passed in 1.58s |

唯一 pytest 失败为已有 `tests/test_learning_analytics_api.py::RealAuthenticationIsolationTests::test_admin_page_quota_and_permanent_admin_contract`：断言要求 `重置今日分析次数`，当前 `pages/admin.html` 实际文案为 `恢复今日可用次数`。本轮未修改 admin 页面。全站 check 的 4 项剩余错误为既有内嵌演示检查和 Mermaid 源/课程页数量差异；链接检查已为 0。上述 check 问题未扩大为业务改动。

## 8. Known Limitations

- Tool Calling 未实现。
- Memory/长期记忆未实现；rolling summary 只是当前 chat session 的有限短期上下文。
- RAG 未实现。
- LangGraph 未实现。
- MCP 未实现。
- 未调用真实 LLM；测试全部使用 mock/fake provider。
- 浏览器真实手动 smoke 未执行；已用 TestClient/fake provider 完成创建会话、普通流式持久化、历史恢复、长会话摘要和 Learning Context 进入最终 prompt 的替代验证。
- 本轮已完成 Markdown→HTML、课程库和 Hot100 构建；未部署 VPS，最终 GitHub push 在最终整合提交后执行。

## 9. Core Changed Files

### M1

`assets/ai-assistant.js`、`index.html`、`pages/ai-assistant.html`、`interview_forge/ai/chat/__init__.py`、`interview_forge/ai/chat/prompts.py`、`interview_forge/ai/chat/service.py`、`interview_forge/ai/provider.py`、`interview_forge/api/app.py`、`interview_forge/api/routers/chat.py`、`interview_forge/db/ai_schema.py`、`interview_forge/runtime/streaming.py`、`tests/test_ai_chat.py`。

### M2

`interview_forge/ai/chat/context_builder.py`、`interview_forge/ai/chat/service.py`、`interview_forge/ai/chat/token_budget.py`、`interview_forge/db/ai_schema.py`、`tests/test_ai_chat_context.py`。

### M3

`interview_forge/ai/chat/learning_context.py`、`interview_forge/ai/chat/service.py`、`interview_forge/ai/context_projection.py`、`tests/test_ai_chat_learning_context.py`。

### UI/整合

`cockpit.html`（等待动画稳定布局）、`tests/test_ai_coach.py`（等待布局静态契约）、本报告，以及构建生成的课程库/题解 HTML。

未修改：`interview_forge/analytics/context_compiler.py`。本轮 books/ Markdown 由独立笔记审查任务产生，未进入 M1/M2/M3 milestone commit；既有 `books/单行本/lora微调.md` 的本地改动保留，不纳入最终整合提交。

## 10. 当前 Git 状态事实

三个 AI Assistant milestone commit 已存在且未回滚。当前报告生成时，未提交修改包括笔记 Markdown（其中 `books/单行本/lora微调.md` 为既有本地改动）、`cockpit.html`、`tests/test_ai_coach.py`、本报告和构建生成的 HTML；这些文件没有进入 M1/M2/M3 commit，待最终整合提交时按范围暂存。

```text
8d7e4f7 feat: integrate learning context into AI chat
a055d89 feat: add bounded chat context and rolling summaries
6d38435 feat: add persistent streaming AI chat foundation
f2f5fde fix: restore legacy dashboard cache ttl
cf2fb46 fix: close Architecture V2 async and contract gaps
b99dd07 fix: finalize FastAPI architecture migration
4dbe2ce refactor: complete FastAPI backend architecture migration
b555d11 完成核心运行时代码职责拆分
```

本草稿创建后本文件为未提交文件，待主代理统一整合后再决定最终报告内容、commit 和 push。
