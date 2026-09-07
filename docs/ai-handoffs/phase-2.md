# AI 学习教练阶段 2 交接：确定性上下文编译器

> 历史快照说明（2026-09-08）：本文的“是否部署：否”仅表示阶段交接当时状态，不代表当前生产环境。现行线上状态以根目录 `README.md`、`docs/深度审查与修复报告-2026-09-08.md` 和 VPS 部署指南为准。

> 历史快照说明（2026-09-08）：本文的“是否部署：否”仅表示阶段交接当时状态，不代表当前生产环境。现行线上状态以根目录 `README.md`、`docs/深度审查与修复报告-2026-09-08.md` 和 VPS 部署指南为准。

> 状态：COMPLETE
>
> 完成日期：2026-09-07
>
> 上下文契约：context-v1
>
> 是否部署：否

## 1. 本阶段结果

阶段 2 已完成一个不依赖模型的确定性上下文编译器。它接收已经由阶段 1 生成的 `analytics-v1` 快照，按任务选择有限的学习事实、信号和证据，使用白名单正向构建 `context-v1`，执行原子单元预算裁剪，并生成不含运行时间的稳定 `snapshot_hash`。

本阶段没有安装或调用 LangChain、LangGraph 或任何模型，没有增加前端入口、没有新增或迁移数据库，也没有部署。

## 2. 交付文件

- `tools/context_compiler.py`：公共函数 `compile_learning_context()`、任务策略、白名单、预算、证据闭包和快照哈希；
- `tools/tests/test_context_compiler.py`：上下文编译器合成测试；
- `tools/study_server.py`：隐藏只读 `POST /api/coach/context` 薄路由；
- `tools/tests/test_learning_analytics_api.py`：隐藏接口认证、隔离、输入校验和只读行为测试；
- `docs/ai-handoffs/phase-2.md`：本交接报告；
- `plan.md`：阶段状态更新，阶段 3 仍未开始。

## 3. 接口与任务

公共函数签名为：

```python
compile_learning_context(
    analytics,
    task,
    user_request="",
    target_problem_id=None,
    profile=None,
    budget_tier=None,
)
```

支持的任务与排序策略彼此独立：

- `learning_diagnosis`：默认 `medium`；按风险信号优先级、异常程度、错误频次和近期活动选择诊断事实；
- `today_plan`：默认 `small`；按到期/逾期天数、可行动性、标记和稳定 ID 选择今日候选；
- `problem_review`：默认 `large`；必须提供存在于快照中的 `target_problem_id`，只输出该题事实、该题信号和其证据；
- `learning_route`：只输出 `unavailable`、`no_course_retrieval` 预留协议，不输出课程候选、书籍或路线。

隐藏接口只接受 `task`、`user_request`、`target_problem_id`、`profile` 和可选 `budget_tier`。认证成功后数据源固定为当前会话用户的 `analytics_cached(user_db_path(...))`；请求不能指定用户名或数据库路径。接口不写学习数据、不使学习缓存失效，也没有前端调用入口。

## 4. 输出、预算与安全边界

所有任务都返回以下固定主结构：

```text
context_schema_version, task, user_request, profile, summary, facts,
signals, evidence, data_quality, selection_reasons, omitted,
data_as_of, snapshot_hash
```

预算使用保守的字符硬上限和约四字符/Token估算：

| 档位 | 默认任务 | 硬上限 | 总 facts | problem/module/content facts | signals | evidence | selection_reasons |
|---|---|---:|---:|---:|---:|---:|---:|
| small | `today_plan` | 4,000 tokens / 16,000 字符 | 14 | 8 / 4 / 8 | 10 | 14 | 40 |
| medium | `learning_diagnosis` | 8,000 tokens / 32,000 字符 | 40 | 20 / 8 / 16 | 24 | 32 | 100 |
| large | `problem_review`、路线预留 | 12,000 tokens / 48,000 字符 | 64 | 32 / 12 / 24 | 32 | 48 | 140 |

用户请求最多保留 2,000 个 Unicode 字符，超出字符数写入 `omitted`。profile 只允许 `learning_goal`、`available_minutes`、`preferred_language`，分别执行类型、值域和长度限制；未知字段、类型错误字段和 profile 裁剪量只记录计数，不复制字段名或值。每个选择单元与其选择原因一起加入，信号与新增证据作为原子组加入；证据放不下时整条信号不选，不留下悬空 `evidence_id`。

上下文只从 analytics 的明确字段构建，包含题目/模块/章节聚合事实、有限信号、有限证据事实和数据质量计数。不会复制用户名、昵称、密码、会话/token/cookie/CSRF/API key、凭证、头像、管理员信息、聊天室、反馈、完整题面/题解、书籍正文、URL 或任意未知字段。

`meta.trust_boundaries` 明确将 user request、profile、学习事实、信号、证据和未来资料标记为 `untrusted_data`，并声明其中命令不能改变规则、不会执行命令、不触发写入。`snapshot_hash` 对最终规范化主结构事实计算，不包含自身或生成时间。

## 5. 测试结果

- `python -m unittest tools.tests.test_context_compiler`：11 项通过；
- `python -m unittest tools.tests.test_learning_analytics tools.tests.test_learning_analytics_api`：50 项通过；
- `python -m py_compile tools/context_compiler.py tools/study_server.py tools/tests/test_context_compiler.py tools/tests/test_learning_analytics.py tools/tests/test_learning_analytics_api.py`：通过。

测试覆盖空/少量/大快照、三类任务差异和路线预留、白名单与恶意嵌套字段、大小写敏感哨兵、中文/英文注入文本、中文/emoji/特殊字符和超长输入、三档硬预算、单类别膨胀、JSON 序列化、信号到证据闭包、稳定哈希及相关事实变化、单题目标校验、隐藏接口认证/用户隔离/输入校验/只读行为。

## 6. 非阻断限制与下一步边界

- Token 估算是无 tokenizer 的保守近似；真正发送给模型时，阶段 3 仍需在模型适配层设置供应商侧 token 限制；
- 当前只消费 `analytics-v1` 聚合事实，不附原始提交列表、完整题面或正文；
- `learning_route` 尚未召回课程元数据，保持明确不可用；
- profile 目前只承载三个明确字段，不继承历史对话记忆；
- 隐藏 POST 仍受现有 4,096 字节请求体限制。

以上限制不影响本阶段的确定性、白名单、预算、认证隔离和只读边界。阶段 3 只有在用户明确确认后才可接入模型；本交接不启动阶段 3，也不部署。
