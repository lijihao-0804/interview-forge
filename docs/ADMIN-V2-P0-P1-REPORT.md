# Admin V2 P0/P1 Report

## 1. Commits

- P0 Backend SHA: `874c72d` — `feat: add admin observability backend`
- P0 UI SHA: `6b0cd99` — `feat: add admin observability dashboard`
- P1 Backend SHA: `fa3bc12` — `feat: add admin operations backend`
- P1 UI SHA: `02bde66` — `feat: complete admin operations dashboard`
- Final SHA: `a8c8dae`（包含最终日志读取侧脱敏修复）

## 2. Architecture

本轮保持 Architecture V2：

```text
API Router → Admin Service → DB / Runtime / Observability
```

- `interview_forge/observability/`：JSONL 日志、AI metadata trace、运行指标、可选价格估算。
- `interview_forge/services/admin_observability.py`：日志、Overview、AI Usage、AI Trace 聚合。
- `interview_forge/services/admin_operations.py`：任务、Action、用户详情、Memory 汇总、系统信息和诊断。
- `interview_forge/api/routers/admin_observability.py`、`admin_operations.py`：只负责认证、参数边界和 Response。
- `assets/admin-observability.*`、`assets/admin-operations.*`：后台新增视图，使用 `textContent` 渲染。

现有 `admin.py` 继续负责账号、邀请码、反馈、密码和 AI 配额功能。

## 3. P0

- Overview：用户活跃统计、请求错误率/P95、AI 轮次/Token/工具错误、任务和存储。
- Logs：项目自有 JSONL rotating log，支持级别、模块、事件、request ID 和 bounded limit 筛选。
- AI Usage：按窗口、用户、模型聚合轮次、成功率、延迟、Token、工具、Memory 写入和可选成本。
- AI Trace：per-user `ai_trace_events` metadata-only 表，聚合 LLM rounds、既有 tool runs 和 action requests。
- Chat middleware 统一写入 `request.state.request_id`；Chat/Tool 只增加 trace hook，不改变工具决策逻辑。

## 4. P1

- Tasks：聚合现有 `ai_tasks` 与 process-local LeetCode sync task；未新增 Task DB。
- Actions：读取既有 `chat_action_requests` 的安全列，不返回 arguments/result metadata。
- User Detail：账号、学习计数、AI 计数、工具/Action 计数和 Memory 计数，不返回正文。
- Memory Summary：只返回 active/superseded、kind、source_type 和近期写入统计。
- Cost：由 `AI_MODEL_PRICING_JSON` 配置；未配置价格时费用为 `null`，同时返回覆盖率。
- System Info：版本、运行时、工具注册数量、任务后端、AI 配置摘要和存储信息。
- Diagnostics：只执行本地无副作用检查，不请求 LLM、LeetCode、天气，不运行 shell，不重启服务。

## 5. API

新增接口均要求 `require_admin()`：

| Method | Path | Filters / body | 返回内容 |
|---|---|---|---|
| GET | `/api/admin/logs` | level/module/event/request_id/limit | 脱敏结构化日志 |
| GET | `/api/admin/overview` | — | 系统、用户、请求、AI、任务、存储总览 |
| GET | `/api/admin/ai/usage` | window/username/model | AI 用量和成本 |
| GET | `/api/admin/ai/traces` | username/status/model/window/limit | metadata-only Trace 列表 |
| GET | `/api/admin/ai/traces/{trace_id}` | username | Trace/LLM/Tool/Action 时间线 |
| GET | `/api/admin/tasks` | kind/status/username/limit | 安全任务投影 |
| GET | `/api/admin/actions` | username/tool/status/window/limit | Action 审计安全列 |
| GET | `/api/admin/users/{username}/detail` | — | 单用户脱敏统计 |
| GET | `/api/admin/memory/summary` | username | Memory 聚合统计 |
| GET | `/api/admin/system/info` | — | 运行时和配置摘要 |
| POST | `/api/admin/system/diagnostics` | — | 本地诊断结果 |

## 6. Observability Data

- `logs/app.jsonl`：InterviewForge 自有结构化请求日志，5 MB × 5 rotating；路径可由 `INTERVIEW_FORGE_LOG_PATH` 指定，否则使用项目 `logs/app.jsonl`。日志目录已加入 `.gitignore`。
- Admin 日志读取阶段再次执行字段脱敏，避免历史 JSONL 中的敏感字段绕过展示边界。
- `ai_trace_events`：telemetry only，保存 trace/request/session、provider/model、round、状态、耗时、Token 和错误类别。
- `chat_tool_runs`：Tool source of truth，Trace Detail 只聚合安全列。
- `chat_action_requests`：Action source of truth，Trace/Action Audit 不复制参数和结果正文。
- 不修改现有业务表含义；新增表为 per-user SQLite AI metadata 表。

## 7. Privacy

日志、Trace 和 Admin API 均不保存或返回 password、token、cookie、Authorization、LEETCODE_SESSION、csrf、API key、聊天正文、Memory 正文、完整 Learning Context、Tool Result 正文、Action arguments 或 result metadata。异常只记录异常类别等有限元数据，不记录 `repr`、locals 或 prompt。

## 8. Cost

通过环境变量 `AI_MODEL_PRICING_JSON` 配置：

```json
{"model-name":{"input_per_1m":1.0,"output_per_1m":2.0}}
```

价格无法解析或未配置时 `estimated_cost_usd=null`；`cost_coverage_percent` 表示有价格覆盖的 Chat Trace 比例。

## 9. Tests

| Command | Result |
|---|---|
| `python -m pytest -q` | **273 passed, 25 subtests passed**, 1 existing deprecation warning |
| `python -m pytest -q tests/test_admin_v2.py` | passed |
| `python -m compileall -q interview_forge tests scripts` | passed |
| `node --check assets/admin-observability.js` | passed |
| `node --check assets/admin-operations.js` | passed |
| `python -m scripts.build.build_hot100` | passed；100 problem pages up to date |
| `python -m scripts.check.check_hot100` | passed；broken_links=0, errors=0, warnings=0 |
| `git diff --check` | passed |

## 10. Known Limitations

- LeetCode sync task 仍是 process-local，服务重启后历史不可恢复。
- 结构化日志只覆盖 InterviewForge 自己的应用事件，不读取 journalctl。
- 未引入外部 observability stack。
- 成本估算依赖管理员配置模型价格。
- Admin V2 仅提供元数据和诊断，不提供用户聊天/Memory 正文审查入口。

## 11. Changed Files

- `interview_forge/observability/`
- `interview_forge/services/admin_observability.py`
- `interview_forge/services/admin_operations.py`
- `interview_forge/api/routers/admin_observability.py`
- `interview_forge/api/routers/admin_operations.py`
- `interview_forge/db/ai_schema.py`
- `interview_forge/ai/chat/service.py`
- `interview_forge/ai/chat/tool_orchestrator.py`
- `interview_forge/api/app.py`
- `interview_forge/api/routers/chat.py`
- `interview_forge/services/leetcode.py`
- `assets/admin-observability.*`
- `assets/admin-operations.*`
- `pages/admin.html`
- `tests/test_admin_v2.py`
- `tests/test_ai_coach.py`
- `.gitignore`

本轮未部署 VPS，未修改 systemd/nginx，未开发 AI Chat/Memory/Tool Calling 新功能，也未修改笔记、Hot100、课程内容。
