# InterviewForge AI Assistant M7：Tool Pack + Agent Evaluation

> 状态：M7 已在现有 M1–M6 ToolSpec / Registry / Runtime / Action confirmation 架构内完成。本轮没有引入新的 Agent 框架、RAG、Vector DB、LangGraph、MCP 或 M8 能力，也未部署 VPS。

## 1. 新增工具

M7 新增五个工具，均复用现有 `services`，没有在工具层复制 SQL 或学习算法：

| 工具 | 类型 | 用途 | 写操作 |
|---|---|---|---|
| `get_problem_progress` | READ | 查询单题轮次、提交次数、AC 次数、最近状态、下次复习日期 | 否 |
| `get_review_queue` | READ | 查询到期/逾期题目队列，支持 `limit` 1–30 | 否 |
| `mark_problem` | ACTION | 设置已掌握、复习中、薄弱或清除标记 | 需确认 |
| `pin_problem_for_tomorrow` | ACTION | 把题目加入明日学习计划 | 需确认 |
| `set_daily_goal` | ACTION | 设置每日学习目标轮数，遵循现有 1–50 的展示口径 | 需确认 |

既有 `get_problem`、`get_learning_context`、`get_weather` 和 `sync_leetcode` 保持不变。Registry 仍只有一个，ACTION 仍统一经过 `ActionRequestStore`、`ActionService` 和 `ToolRuntime`。

## 2. 工具边界与安全行为

- `get_problem` 只负责题目基础元数据和链接；单题进度由 `get_problem_progress` 负责。
- `get_review_queue` 直接使用 `services.study.daily_data` 的到期口径，并返回精简题目字段。
- 三个新 ACTION 在模型调用阶段只创建待确认请求，不执行 handler；确认后复用既有 exactly-once 状态机。
- 工具结果不包含密码、令牌、完整题解或内部审计字段。
- System Prompt 已补充工具区分、复习队列用途、ACTION 必须确认和禁止重复调用规则。

## 3. Recent Action Context

新增 `RecentActionContextProvider`，通过 `ActionRequestStore.list_recent()` 读取当前会话最近少量动作状态，支持 `executing`、`succeeded`、`failed`、`cancelled`。

它只向模型提供“操作名称 + 状态”的短摘要，例如“LeetCode 同步：已成功”，不会暴露原始参数、题号、action ID、凭据或完整 ToolResult。ContextBlock 优先级为 70，低于 Learning Context，高于普通会话摘要；异常时 graceful degradation，不影响普通 Chat。

## 4. Golden Agent Evaluation

- Fixture：`tests/fixtures/ai_agent_golden.json`
- 用例数：51
- 覆盖：普通问答、代码学习问题、基础题目查询、单题进度、复习队列、学习上下文、天气、三类新 ACTION、LeetCode 同步、安全拒绝、重复调用约束。
- 评估器：`scripts/check/ai_agent_eval.py`
- 默认模式不访问网络、不使用 API Key，验证 Registry、工具选择、禁止工具、确认要求和参数 schema。
- `--real` 只读取现有 AI 配置并输出人工 smoke 入口，不在 CI 或脚本运行时自动消耗真实模型额度。

确定性结果：

```text
mode=deterministic total=51 passed=51 failed=0 accuracy=1.000
```

人工真实 Provider checklist 已扩展到 `scripts/check/ai_tool_smoke.py`，包含五个新工具、确认一次性执行、重复读取和安全问题场景；脚本不包含 API Key，也不会自动发起真实请求。

## 5. 测试与验证

本轮新增 `tests/test_ai_m7.py`，覆盖：

- 五个工具的 Registry 注册和 READ/ACTION 分类。
- 单题进度使用真实提交统计且返回精简字段。
- 复习队列服务复用、逾期/今日分类和 limit。
- 三个新 ACTION 未确认不执行，确认后执行一次，重复确认安全重放。
- Recent Action Context 的状态投影以及参数、内部 ID、结果正文隐藏。
- 51 条 Golden fixture 全量通过。

最终验证结果将在提交前回填：

| 检查 | 结果 |
|---|---|
| M7 定向测试 | 11 passed |
| Golden deterministic eval | 51/51 PASS |
| AI / Memory / Action / Tool / Chat 回归 | 已包含在全量测试，245 passed，17 subtests passed |
| 全量 pytest | 245 passed，17 subtests passed，1 个既有管理员文案失败 |
| compile/import | `compileall` PASS；前端 `node --check` PASS |
| build / Hot100 check | HTML build PASS；Hot100 build PASS；check_hot100 PASS（broken_links=0, errors=0, warnings=0） |
| `git diff --check` | PASS（仅 Git 的 LF/CRLF 提示） |

## 6. 变更文件

- `interview_forge/ai/tools/builtins/progress.py`
- `interview_forge/ai/tools/builtins/review.py`
- `interview_forge/ai/tools/builtins/actions.py`
- `interview_forge/ai/tools/builtins/__init__.py`
- `interview_forge/ai/actions/store.py`
- `interview_forge/ai/chat/recent_action_context.py`
- `interview_forge/ai/chat/service.py`
- `interview_forge/ai/chat/prompts.py`
- `scripts/check/ai_agent_eval.py`
- `scripts/check/ai_tool_smoke.py`
- `tests/fixtures/ai_agent_golden.json`
- `tests/test_ai_m7.py`

## 7. 限制与结论

M7 的评估器是确定性 contract/routing evaluator，不把真实模型输出伪装成自动化指标；真实 Provider 调用仍由人工 smoke checklist 触发。工具只提供当前已有学习服务能可靠给出的数据，不推断不存在的轮次、提交或复习日期。

M7 完成后冻结 Tool Pack 与 Agent Evaluation 边界，不自动开始 M8。

全量 pytest 唯一失败为既有的 `tests/test_learning_analytics_api.py::RealAuthenticationIsolationTests::test_admin_page_quota_and_permanent_admin_contract`：旧测试仍要求管理员页面包含“重置今日分析次数”，当前页面已经使用“恢复今日可用次数”。本轮没有修改管理员页面，也没有因 M7 改变该行为。

实现提交 SHA：待提交。
