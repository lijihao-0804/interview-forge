# AI 学习教练阶段 3 交接：LangChain 一键学习分析

> 状态：COMPLETE
>
> 完成日期：2026-09-07
>
> 是否部署：否
>
> 是否执行真实模型调用：否，等待安全环境配置

## 1. 完成内容

本阶段完成第一条真实 AI 功能的最小链路：

```text
analytics-v1
  → context-v1
  → 单一 LangChain ChatModel 适配入口
  → Pydantic 结构化输出
  → 本地长度、类型、证据闭包校验
  → 每用户 SQLite 后台任务
  → 中控台“一键学习情况分析”卡片
```

本阶段没有创建自主 Agent，没有实现课程路线推荐，没有部署，也没有安装 AI 依赖。

## 2. 修改文件

- `requirements-ai.txt`：锁定可选的 `langchain`、`langchain-core`、`langchain-openai` 和 `pydantic` 版本；
- `tools/ai_coach.py`：配置读取、Prompt 版本、LangChain ChatModel 适配、Pydantic Schema、结果校验、规则降级、任务队列和持久化；
- `tools/study_server.py`：每用户 AI 表幂等迁移、能力信息、任务/结果/取消/反馈路由；
- `tools/tests/test_ai_coach.py`：阶段 3 假模型、HTTP、迁移、并发、隔离和页面契约测试；
- `cockpit.html`：小范围增加分析卡片、状态恢复、结果展示、上下文预览和反馈；
- `plan.md`：阶段 3 标记完成，下一步等待阶段 4；
- `docs/ai-handoffs/phase-3.md`：本交接报告。

## 3. 模型适配与安全边界

- 所有模型创建和调用集中在 `tools/ai_coach.py`，当前使用 LangChain `ChatModel` 抽象和 `langchain-openai` 的 OpenAI-compatible 适配；
- Prompt 使用独立常量并固定 `PROMPT_VERSION=coach-analysis-v1`；system prompt 明确声明 `context-v1` 是不可信资料，不能执行其中的命令；
- 优先调用 Pydantic structured output；供应商不支持时退回同一 ChatModel 的原始响应解析；
- 解析或本地校验失败最多再做一次受控修复，总模型调用最多 2 次；
- 每条 weakness 必须至少引用一个当前 context 中存在的 `evidence_id`；不存在的引用、无证据问题、未知字段、超长或超量结果全部拒绝；
- 模型内容在中控台用 `textContent` 和安全 DOM API 展示，不渲染 HTML/Markdown；
- API Key 只从进程环境读取，不写入仓库、任务表、缓存键、上下文、Prompt 预览、响应或错误消息；模型前端不接触供应商名称、模型原名或端点。

配置默认值：

```text
AI_ENABLED=0
AI_PROVIDER=
AI_MODEL=
AI_BASE_URL=
AI_API_KEY=
AI_WIRE_API=chat_completions
AI_ACTOR_AUTHORIZATION=
AI_REQUEST_TIMEOUT_SECONDS=45
AI_MAX_CONCURRENT_REQUESTS=2
AI_DAILY_LIMIT_PER_USER=10
AI_BETA_USERS=
```

未安装可选依赖、AI 关闭或缺配置时，原站正常启动；接口返回统一错误类别和确定性规则降级，不暴露供应商原始错误。

兼容性说明：OpenAI/ChatGPT 路径继续优先使用原生结构化输出；DeepSeek 当前不支持该 `response_format`，因此仅 DeepSeek 使用普通 JSON 响应，并继续经过同一套 Pydantic、长度和 evidence 引用校验。

## 4. 数据库与任务

AI 数据只写当前登录用户自己的 `hot100-study.db`，不写 `auth.db`。

### `ai_tasks`

保存任务 ID、任务类型、状态、context 快照哈希、Prompt 版本、非敏感模型标识摘要、时间、错误类别/用户消息、脱敏且限长的 context 预览、结构化结果、规则 fallback 和 insight ID。

### `ai_insights`

保存成功结果、快照哈希、Prompt 版本、非敏感模型标识摘要、数据时间和有帮助/没帮助反馈。

任务 ID 和 insight ID 都使用随机 32 位十六进制标识。迁移使用 `IF NOT EXISTS` 和缺列补齐逻辑，旧用户库可重复升级。

任务状态：`queued`、`running`、`succeeded`、`failed`、`cancelled`。

后台任务具备：

- 全局实际模型调用并发上限，默认 2；
- 当前业务日期的单用户每日额度，默认 10；
- 相同用户、任务、快照、Prompt 版本和模型摘要的成功结果复用；
- 进程重启后遗留的 queued/running 任务在首次访问时收敛为可见失败，不会永久卡住；
- 只允许取消 queued 任务，running 明确返回不可取消；
- 已完成任务保留数量上限，内存队列有容量上限；
- 所有查询和反馈都由当前请求解析出的用户数据库完成，不能用 task ID 跨用户读取。

## 5. 接口

```text
POST /api/coach/analyze
GET  /api/coach/tasks/<id>
POST /api/coach/tasks/<id>/cancel
GET  /api/coach/insights/recent
POST /api/coach/insights/<id>/feedback
GET  /api/coach/capability
```

`/api/bootstrap` 同时返回当前账号的 `capabilities.ai_coach`。管理员在 AI 配置完整时始终允许；普通用户只有 `AI_BETA_USERS` 明确包含用户名或配置为明确全开放值时允许。beta 限制由后端执行，前端隐藏不是权限边界。

## 6. 中控台体验

- 打开页面只读取 capability 和最近任务，不自动调用模型；
- 用户点击后才创建任务，重复点击在前端去抖，后端按快照幂等复用；
- 页面刷新可以恢复 queued/running/succeeded/failed/cancelled；
- 展示摘要、优势、问题、依据、行动、置信度、数据缺口和 `data_as_of`；
- 折叠展示本次使用的脱敏 context-v1；
- 成功 insight 支持有帮助/没帮助反馈；
- AI 未配置、未开放或失败时展示规则分析和简洁原因；
- 沿用现有桌面/移动、深浅主题样式，没有改动其它页面。

## 7. 测试结果

- `python -m unittest tools.tests.test_ai_coach -v`：16 项通过；
- `python -m unittest discover -s tools/tests -p "test_*.py"`：77 项通过；
- `python -m py_compile tools/ai_coach.py tools/study_server.py tools/context_compiler.py tools/learning_analytics.py tools/tests/test_ai_coach.py tools/tests/test_context_compiler.py tools/tests/test_learning_analytics.py tools/tests/test_learning_analytics_api.py`：通过；
- `git diff --check`：通过；
- `python tools/check_hot100.py`：已按“修改了 cockpit 页面只运行一次”的约定执行。结果为 `errors=2, warnings=0, broken_links=2`，均为既有 `books/hot100/10-回溯.md` 指向当前机器 Typora 用户目录的图片链接；本阶段没有修改该 Markdown 文件，未扩大范围处理。

阶段 3 测试使用假模型，不使用真实网络。真实调用未执行，因为当前没有为本阶段安全提供的运行时 AI 配置；没有读取、复制或输出用户此前消息中的任何 token。

## 8. 集中审查与问题结论

按本阶段明确约定，未启动独立审查代理、未创建二级 agent，也未做开放式全仓安全审计；只进行了实施过程中的必要自测和 P0/P1 修复。

自测期间发现并修复一个并发成本控制问题：旧 worker 线程在测试配置缩小时不会自动退出。现在模型调用处另有全局条件槽位，实际并发数不会超过当前 `AI_MAX_CONCURRENT_REQUESTS`。

当前没有已知 P0/P1。保留的 P2/环境限制：

- 真实 LangChain provider 组合尚未在安全配置环境中做小调用；假模型已覆盖主要正常和失败路径；
- token 预算沿用阶段 2 的字符近似，未引入供应商 tokenizer；
- `check_hot100` 的两个 Typora 用户目录图片链接仍待独立处理，和本阶段代码无关。

## 9. 部署与回滚

- 是否部署：否；
- Git：未提交；
- 生产数据库：未迁移；
- 生产配置：未修改；
- 首次部署建议保持 `AI_ENABLED=0`，确认原站健康后再仅对管理员或 beta 用户配置；
- 快速关闭方式：设置 `AI_ENABLED=0` 并重启服务，原有学习、书架、聊天和管理功能不依赖 AI；
- 代码回滚不删除 `ai_tasks`/`ai_insights` 表，保留数据以便后续版本继续使用。

## 10. 下一阶段交接

阶段 4 才开始课程元数据盘点、规则候选召回和学习路线推荐。本阶段的 `learning_route` 仍然不可用；不要让阶段 3 的分析模型自行生成课程 ID、课程顺序或写入学习计划。

## 11. 阶段 3.1：上下文信息密度优化（2026-09-08）

### 11.1 目标与范围

本次只优化 `learning_diagnosis` 的确定性摘要、信号选择、模型投影、输出契约和可观测性；没有修改阶段 4 课程路线，没有部署，没有清空或覆盖 `.maintenance/ai-debug.jsonl`，没有读取或输出密钥，也没有创建子代理。

### 11.2 上下文编译器改动

- 在 `context-v1` 中新增白名单 `diagnostic_digest`，包含：overview、review_backlog、overdue_distribution、round_distribution、representative_cases、anomalies、coverage 和数据质量语义提示；所有数字由 `analytics-v1` 已有事实确定性聚合，不回读数据库、不让模型统计。
- 逾期分桶明确覆盖 `>90d`、`90d`、`60-89d`、`30-59d`、`8-29d`、`1-7d`、`due_today`，避免 90 天边界落空；Hot100 内容与题目复习队列不重复相加，内容范围单独展示。
- 诊断信号先按 `signal_type` 每类取最高优先级，再补足剩余槽位；有其它信号时 `due_overdue` 约束到约 40%，只有逾期类时也只保留最多 3 个代表病例，完整队列进入统计摘要。
- 近期 activity 但仍处于 due/overdue 的情况只输出 observation + possible_explanations，不断言系统故障或用户行为因果；`ignored_hot100_content_event_count` 只作为已知统计语义提示。
- `source_data_missing` 与 `context_budget_omitted` 分开；模型只能把后者称为未纳入本次上下文/omitted，不能称为原始数据缺失。

### 11.3 模型投影与输出改动

- DeepSeek/OpenAI/ChatGPT 共用的输出校验新增 action `basis: data|heuristic` 与 `confidence: low|medium|high`；`basis=data` 必须引用 evidence，`basis=heuristic` 必须明确标记为通用建议。OpenAI 原生结构化路径保留，DeepSeek 普通 JSON 路径和安全裁剪保留。
- 诊断模型投影对 facts/signals 去除重复 metric 元数据，但保留题目关键状态、信号和 evidence 引用；移除 `submission_source_distribution`，并在 Prompt 中禁止将采集来源当作学习优势。
- Prompt 明确禁止从“完成多 + 当前逾期”推断“最近持续推进新题”等无证据因果。
- 中控台安全展示行动依据类型“数据依据/通用建议”，旧 insight 中没有 `basis/confidence` 时仍按旧 JSON 读取并显示“旧结果未标注”，不会导致历史任务读取失败。

### 11.4 可观测性

`model_prepared` 继续追加写入 JSONL，并新增最终模型投影字符数、粗略 token 数、sections 计数、`prompt_hash`、`context_hash`、非敏感 `model_key` 以及未发送的 `selection_reasons`、`omitted`、`meta`。`request_prepared` 仍保留完整脱敏 context，`raw_output` 仍保留；未记录 key、headers、cookie、username 或 db_path。本次没有修改 `.maintenance/ai-debug.jsonl`。

### 11.5 真实快照密度对比

本机当前快照：analytics 有 178 个 signal/evidence，问题复习队列为 89 due、89 overdue、69 relearn；分布为 `>90d=33`、`60-89d=36`、`30-59d=20`。编译后的完整 context 为约 14,171 字符，最终发送给模型的诊断投影为约 7,711 字符，约 1.9K 个粗略 token；旧日志的模型 context 为 11,716 字符。现在仅发送 3 个逾期代表病例和异常案例，重复逾期主要由 digest 承载。

### 11.6 测试与限制

- 上下文编译器相关测试：15 项通过；覆盖 100+ due 不垄断、分桶边界、轮次分布、代表案例、异常措辞、Hot100 统计语义、source missing/预算 omitted、证据闭包和敏感字段。
- AI 教练相关测试：21 项通过；覆盖 action 契约、DeepSeek 单次安全裁剪、ChatGPT structured path、模型投影、日志字段、旧 insight 兼容、DOM 安全和任务隔离。
- 合并 analytics/AI 测试与编译检查在本次交接结束前执行一次。

非阻断限制：token 仍是字符近似；本阶段未进行真实供应商调用；规则 fallback 沿用同一 action 契约；`learning_route` 仍明确不可用。阶段 4 未启动，当前未部署。

## 12. 阶段 3.2：FullContext → DiagnosticDigest → LLMContext v2（2026-09-08）

### 12.1 三层上下文

- `FullContext` 继续按 `context-v1` 编译并持久化，完整保留 facts、signals、evidence、各类机器 ID、selection_reasons、data_quality、omitted 和 meta，供后端调试与追溯。
- `DiagnosticDigest` 升级为 `diagnostic-digest-v2`。代表案例改用稳定短 ref；同类异常聚合为 type、count、少量 example refs、一次 observation 和 possible_explanations。
- `LLMContext` 固定为 `learning-diagnosis-context-v2`，只发送任务、截止时间、诊断摘要、动态 `compact_facts`、聚合异常、语义化 coverage、必要的数据质量提示及非空用户请求/档案。summary 不再与 digest overview 重复。

### 12.2 后端追溯与公开边界

- 新增有界 `trace_map`：最多 12 个实体，每类真实 signal/evidence/metric ID 最多 6 个。它把短 ref 关联到实体、自然语言标签和真实追溯 ID，但不发送给模型、不返回普通 API、不在 UI 展示。
- 模型输出从 `evidence_ids` 改为 `support_refs`。本地严格校验 ref 必须存在于当前 FullContext 的 trace_map；校验后可在后端解析真实追溯链。
- 普通 API 会移除 support refs、机器 ID 和内部 trace，只返回自然语言 `support_labels`。旧 insight 的 evidence_ids 仍可读取，并尽可能从旧 FullContext 映射为自然语言标签。
- 中控台继续使用 `textContent`，依据展示改为“代表案例：题目名称”，不展示 p146 或 evidence/signal/metric 标识。

### 12.3 模型与日志契约

- DeepSeek 保留普通 JSON、本地校验和轻微越界单次裁剪；OpenAI/ChatGPT 原生 structured output 路径保留；最多两次真实调用不变。
- 模型投影递归删除空字符串、空数组和空对象，并拒绝包含 `evidence:`、`signal:`、`metric:`、trace_map、selection_reasons 或 rule_version。
- `model_prepared` 记录 v2 版本、最终字符/token 估算、included/excluded sections 和 hash。provider 原始输出若意外回显机器 ID，调试日志自动整段脱敏；正常 support refs 可保留。
- `request_prepared` 仍可追加记录完整脱敏 FullContext。本次没有清空或覆盖既有 `.maintenance/ai-debug.jsonl`；首次定向测试继承了本机已启用的 debug 环境变量，因而追加了合成测试事件，旧日志内容仍完整保留，后续测试已要求显式关闭该环境变量。

### 12.4 当前验证

- 当前真实本地学习快照：FullContext 约 13,565 字符，LLMContext v2 约 2,398 字符（按字符/4 粗估约 600 tokens）；3 个代表案例与 3 个 compact facts 一一对应，模型投影机器 ID 扫描为 0。
- 合成高负载快照：FullContext 约 9,827 字符，LLMContext v2 约 1,851 字符；signal 类型为 repeat_wa + due_overdue，引用对齐成立。
- 相关 context/AI 测试 39 项通过；一次 analytics/context/AI 组合测试 68 项通过；Python 编译检查与 `git diff --check` 通过。
- 阶段 3.2 没有数据库迁移、没有真实网络模型调用、没有部署，也没有启动阶段 4。

## 13. 阶段 3.3：DeepSeek 性能可观测性与真实基线（2026-09-08）

### 13.1 实现

- DeepSeek 普通 JSON 路径改为在服务端完整消费 LangChain stream，浏览器端仍维持任务完成后一次读取完整结果的既有语义，没有增加 UI streaming。
- 每个 attempt 追加 `model_request_started`、`model_first_token`、`model_last_token`、`model_response`、`model_response_parsed` 与验证事件；同一任务使用稳定 request_id，初次生成与 repair 使用独立 attempt。
- `model_response` 记录 TTFT、generation、model total、chunk_count、可用性明确的 usage、reasoning tokens 和吞吐率。usage 缺失时记录 unavailable，不估造供应商 token。
- 流式合并只拼接 answer content；`reasoning_content` 参与首 token 到达判断，但绝不混入最终 JSON。DeepSeek 仍使用普通 JSON + 本地 Pydantic/ref 校验；OpenAI/ChatGPT native structured output 路径未改。
- 公开响应现在也会把模型正文中偶然出现的短 ref 替换成 trace_map 的自然语言标签，避免 UI 正文泄漏 `p146` 一类内部引用。

### 13.2 一次真实基线

本次通过随机本机端口上的进程内 `ThreadingHTTPServer` 复用正式 `/api/coach/analyze` 路由。由于 auth.db 当前没有启用的普通用户，测试 fixture 将已有真实学习库映射为临时 `role=user` 会话对象；没有修改 auth.db、账号角色或密码，没有读取浏览器 Cookie。顶层请求恰好一次，返回成功，模型 attempt=1，未触发 repair。

| 阶段 | 耗时 | 占约 24.23s 端到端比例 |
|---|---:|---:|
| analytics | 193.03 ms | 0.80% |
| context compile | 79.04 ms | 0.33% |
| task create | 10.08 ms | 0.04% |
| model prepared | 2,574.69 ms | 10.63% |
| TTFT | 14,154.63 ms | 58.42% |
| generation | 7,185.64 ms | 29.66% |
| parse | 0.23 ms | <0.01% |
| validation | 5.09 ms | 0.02% |

- LLMContext v2：2,399 chars，本地粗估 600 tokens；供应商实际 input/prompt tokens 为 1,591（包含 system prompt、输出契约和上下文）。
- 模型总耗时：21,340.28 ms；TTFT 占模型耗时 66.33%，generation 占 33.67%。
- 输出 tokens：3,225，其中 reasoning tokens 1,612；chunk_count 3,226。
- 按供应商 output tokens 计算吞吐率：448.812 tokens/s。
- worker 总耗时：23,947.68 ms；应用 call slot 等待仅 0.06 ms。

结论：本次瓶颈明显更接近首 token 前阶段。TTFT 约为生成阶段的 1.97 倍，占模型耗时约三分之二；analytics、context compiler、解析和校验均不是瓶颈。相比旧基线约 110.23s 模型响应，本次为约 21.34s，但单次样本不能证明性能长期稳定或完全归因于上下文压缩。

### 13.3 尚未执行的候选优化

本阶段只建立证据，不实施以下优化：降低 thinking/reasoning effort、缩短输出契约、限制输出 tokens、切换模型、浏览器流式展示、连接预热或多次基准采样。后续若继续，应优先验证 TTFT 的服务端排队/推理波动，再评估这些选项。

没有部署 VPS，没有子代理，没有清空、覆盖或回删 `.maintenance/ai-debug.jsonl`，没有启动后续性能改造。

## 14. 阶段 3.4：reasoning/content 分段耗时诊断（2026-09-08）

### 14.1 定位与定义修正

代码集中在 `tools/ai_coach.py`：`study_server /api/coach/analyze → create_ai_task → _run_persisted_task → generate_ai_insight → _stream_deepseek_once → _extract_json_payload → validate_insight_payload`。`call_slot_acquired` 在 worker 调用模型前记录。

阶段 3.3 的 `ttft_ms` 实际由首个 reasoning 或正文块触发，但事件名称无法表达网络首包、reasoning 与首正文的差别；generation 从该点持续到 stream 结束。旧 throughput 使用全部 output tokens 除以正文阶段时长，而供应商 usage 把 reasoning tokens 放在 completion/output token details 中，因此该值会被 reasoning tokens 严重放大。

阶段 3.4 保留旧字段用于兼容，同时明确：

- `transport_ttft_ms`：请求开始到首个网络 stream chunk；
- `time_to_first_content_token_ms`：请求开始到首个可解析正文块；旧 `ttft_ms` 同值，并带 `ttft_definition=time_to_first_content_token`；
- `reasoning_ms`：仅在 SDK 真正暴露 reasoning 内容时，从首 reasoning 块计到首次正文切换，否则为 null；
- `content_generation_ms`：首正文块到最后正文块；
- `unattributed_pre_content_ms`：首网络块到首正文之间、无法在当前 SDK 精确归属的时间；
- `content_tokens=output_tokens-reasoning_tokens`：仅在 reasoning token 位于 completion/output details 且不超过 output tokens 时计算；
- `reasoning_tokens_per_sec` 和 `content_tokens_per_sec` 只有 token 与匹配阶段时长均可得时才计算，否则为 null。

新增稳定、脱敏的 `request_config` 与 SHA-256 `request_config_hash`。配置只含 model_key、stream、temperature/top_p/max_tokens、reasoning 开关/effort/budget、response format 和 prompt version；不含 key、header、Cookie 或完整 prompt。

### 14.2 SDK 可见性结论

本机 `langchain-openai 0.3.28` 的 Chat Completions `_convert_delta_to_message_chunk` 只复制 delta.content、function/tool calls，不复制 DeepSeek 的 delta.reasoning_content。因此 provider usage 可见 reasoning token 数，但 reasoning 文本和起止边界在当前 LangChain stream 层不可见。阶段 3.4 按契约将 `time_to_reasoning_start_ms`、`reasoning_ms`、`reasoning_tokens_per_sec` 记为 null，不用“首正文前时间”伪装成精确 reasoning 时间。

### 14.3 真实与模拟验证

两次顶层调用各一次，均 attempt=1、repair=false、成功完成。真实调用走正式 `/api/coach/analyze`、真实学习库和任务队列；模拟调用使用合成 analytics，经正式 Context Compiler 和同一 `generate_ai_insight` 入口调用真实 DeepSeek。

| 指标 | 真实数据 | 合成模拟 |
|---|---:|---:|
| LLMContext chars / 本地估算 | 2399 / 600 | 1852 / 463 |
| provider input tokens | 1591 | 1402 |
| transport TTFT | 160.12 ms | 69.02 ms |
| 首正文 | 70,885.26 ms | 73,278.30 ms |
| 首包至首正文未归属时间 | 70,725.14 ms | 73,209.28 ms |
| reasoning 精确耗时 | null | null |
| 正文生成 | 6,361.46 ms | 7,048.23 ms |
| 模型总耗时 | 77,305.65 ms | 80,384.64 ms |
| output / reasoning / content tokens | 10303 / 8892 / 1411 | 10406 / 8927 / 1479 |
| content TPS | 221.804 | 209.840 |
| reasoning TPS | null | null |
| chunks（总/可见reasoning/正文） | 10304 / 0 / 1410 | 10407 / 0 / 1478 |

两次 `request_config_hash` 完全一致：`724e89e30b0a99d8966aa4b13ca953887ffd984587fedfcd87c1458069158ef1`。请求参数没有差异；差异仅在输入资料与 prompt/context hash，导致 provider input tokens 相差 189。两次 reasoning tokens 都约占 output tokens 的 86%，首网络 chunk 都在 0.2 秒内，而首正文约 71–73 秒。

性能归因：可以排除“建立连接/首个网络包等待 70 秒”；长耗时发生在已开始接收 stream 到首正文之间。结合 usage 中约 8.9K reasoning tokens，瓶颈高度接近 reasoning/首正文前生成阶段，但由于 LangChain 丢弃 reasoning_content，精确 reasoning 起止时间仍不可得，不能把 70–73 秒全部断言为 reasoning。正文生成只约 6–7 秒，解析与 validation 均不足 4 ms。

阶段 3.4 没有改变 diagnosis API 数据结构、模型、thinking、输出契约、provider 或 UI；没有部署、没有子代理、没有清理日志，也没有启动后续优化。

## 15. 阶段 3.5：DeepSeek reasoning A/B benchmark（2026-09-08）

### 15.1 实验设计与隔离

本阶段从同一个既有普通用户学习库只读生成一次 analytics，编译并在进程内冻结一份 `LLMContext v2`。冻结投影为 2399 chars，SHA-256 为 `a847a18fb097a4fede6bad303be2be4526d1f5b256ed60f2976ff7ece757e21e`；10 个样本均记录相同 hash。实验严格按 `ABABABABAB` 执行 10 个顶层请求，每槽位一次调用、关闭自动 repair，失败不补跑。

- A：`deepseek-v4-flash`、`thinking.type=enabled`、`reasoning_effort=high`，配置 hash `676517b89b0d73eeb4c1d8e4a10ec4cf5202751781cd59c9029f6e3f7363d59c`。
- B：模型和其余生成参数不变，仅设 `thinking.type=disabled`，配置 hash `136d64822f3bb54fe11bfa5ac3f12b12133584bbfb3835f86cefd82348a99bc1`。DeepSeek 官方 Chat Completions 文档明确支持 `enabled|disabled`，因此未换模型、未做额外探测调用。
- 默认配置摘要在 benchmark 前后 hash 均为 A hash；脚本未修改环境、启动脚本或运行中服务。

原始结果保存在 `.maintenance/deepseek-reasoning-ab-ds-reasoning-ab-79cb52d29a53.json`，派生分析保存在同目录 `.analysis-v2.json`。两者均不入 Git，不含 key、Authorization、Cookie、用户名；`ai-debug.jsonl` 只追加了逐槽事件和最终摘要，未清空或覆盖。

### 15.2 十个样本

| 槽位 | 组 | model total ms | transport ms | first content ms | content gen ms | reasoning/content tokens | content TPS | validation |
|---:|:---:|---:|---:|---:|---:|---:|---:|:---|
| 1 | A | 12,195.74 | 168.65 | 638.10 | 11,530.36 | 7 / 1,574 | 136.509 | fail: support_refs |
| 2 | B | 8,633.12 | 64.18 | 348.85 | 8,255.62 | 0 / 1,256 | 152.139 | fail: bounds |
| 3 | A | 15,948.91 | 80.95 | 10,222.89 | 5,711.86 | 1,280 / 1,281 | 224.270 | pass |
| 4 | B | 10,551.13 | 69.76 | 183.45 | 10,360.66 | 0 / 1,354 | 130.687 | fail: schema |
| 5 | A | 79,409.13 | 73.51 | 72,631.59 | 6,693.18 | 9,184 / 1,573 | 235.015 | fail: schema |
| 6 | B | 8,651.95 | 128.82 | 300.25 | 8,347.23 | 0 / 1,096 | 131.301 | fail: support_refs |
| 7 | A | 123,597.55 | 68.58 | 113,886.54 | 9,621.95 | 13,510 / 1,727 | 179.485 | pass |
| 8 | B | 9,775.45 | 78.44 | 433.35 | 9,316.44 | 0 / 1,298 | 139.324 | fail: schema |
| 9 | A | 111,626.01 | 68.91 | 103,292.34 | 8,214.83 | 12,209 / 1,462 | 177.971 | pass |
| 10 | B | 10,132.90 | 64.13 | 173.39 | 9,933.22 | 0 / 1,341 | 135.002 | fail: schema |

B 明确关闭 thinking，供应商不返回 reasoning token 明细；据官方模式语义，派生统计将 B 的 provider `output_tokens` 全部计为 content tokens，并记录 derivation，未把缺失值伪造成供应商原生字段。

### 15.3 分组统计与口径

| 指标 | A min / median / mean / p90 / max | B min / median / mean / p90 / max |
|---|---|---|
| model total ms | 12,195.74 / 79,409.13 / 68,555.47 / 123,597.55 / 123,597.55 | 8,633.12 / 9,775.45 / 9,548.91 / 10,551.13 / 10,551.13 |
| first content ms | 638.10 / 72,631.59 / 60,134.29 / 113,886.54 / 113,886.54 | 173.39 / 300.25 / 287.86 / 433.35 / 433.35 |
| content gen ms | 5,711.86 / 8,214.83 / 8,354.44 / 11,530.36 / 11,530.36 | 8,255.62 / 9,316.44 / 9,242.63 / 10,360.66 / 10,360.66 |
| reasoning tokens | 7 / 9,184 / 7,238 / 13,510 / 13,510 | 0 / 0 / 0 / 0 / 0 |
| content tokens | 1,281 / 1,573 / 1,523.4 / 1,727 / 1,727 | 1,096 / 1,298 / 1,269 / 1,469 / 1,469 |
| content TPS | 136.509 / 179.485 / 190.650 / 235.015 / 235.015 | 130.687 / 135.002 / 137.691 / 152.139 / 152.139 |

P90 使用 nearest-rank：排序后取 `ceil(0.90*n)`，所以 n=5 时等于该组最大值。A 的平均总耗时约为 B 的 7.18 倍，中位数约为 8.12 倍；差异几乎都在首正文之前。transport 两组都低于 0.2 秒，正文生成时长反而接近，因此此前“主要成本来自 reasoning/首正文前阶段”的判断得到直接 A/B 支持。A 的 reasoning 消耗高度不稳定（7–13,510 tokens），也解释了其总耗时方差。

### 15.4 严格校验与确定性质量比较

- A 首答通过 3/5（60%）；失败为 support_refs 1、schema 1。B 首答通过 0/5（0%）；失败为 bounds 1、schema 3、support_refs 1。两组均无 JSON parse 失败，且均未触发 repair。
- 所有可解析原始 JSON 的主题覆盖基本一致：复习积压、完成度、活跃度均为 5/5；错题主题均为 2/5，数据质量主题均为 4/5。
- A 平均条目数为 strengths 3.6、weaknesses 3.0、actions 3.6、data gaps 5.4；B 为 4.8、2.6、3.8、5.2。B 更短（原始输出 chars 中位数 2770 vs A 3206），但并未因此满足严格契约。
- A 的 support ref 有效率为 91.84%，B 为 51.11%；A/B action 必要字段完整率分别为 100%/94.74%。B 常把 `diagnostic_digest.*` 或 `anomalies[0]` 当作引用，而契约只允许代表案例短 ref；另有多个样本输出 null 可选字段，触发严格 string schema 校验。
- 两组标题均未出现组内单份输出的精确重复。代表性内容差异是：A 更常围绕“69 项需重学、89 项逾期、代表题第二轮复习”建立带案例的行动；B 也覆盖同一事实，但更容易生成“检查系统同步”等泛化动作或引用摘要路径，证据闭包明显较弱。

结论：B 的速度优势很大，但当前 0% 首答严格通过率使其不具备直接替换默认 A 的条件。下一步值得做的是在不改默认配置前提下，针对非 reasoning 模式收紧 JSON schema 提示、明确仅允许 compact fact refs、将可选字符串要求改为“缺省用空字符串且禁止 null”，再做小样本复测；也可评估服务端对轻微 null/引用格式的确定性安全归一化，但不能放宽未知证据引用。阶段 3.5 未自动实施这些优化。

## 16. 独立小阶段：等待动效、每日额度与管理员重置（2026-09-08）

一键学习分析增加前端模拟百分比进度和五阶段等待提示，不代表后端真实进度。动效最短可见 2.8 秒，真实结果到达前最高为 97%；成功后平滑收尾到 100% 再展示结果，失败、取消或页面离开时直接停止且不伪装成功。按钮在等待期间禁用，读屏仅播报阶段和最终状态，`prefers-reduced-motion` 下取消明显位移并降低更新频率。

普通用户额度固定为 Asia/Shanghai 自然日 3 次，API 统一返回 `quota={limit,used,remaining,reset_at}`；管理员分析不受该额度限制。额度落在每用户学习库的新表 `ai_daily_quota`，任务补充 `quota_day/quota_state`。入队事务先预留名额，从而并发第四个请求立即 429；worker 取得全局调用槽、完成模型本地构造和上下文准备后，在首次外部请求前将预留原子转为已用。缓存复用、本地前置失败、排队取消和队列失败不消耗；供应商超时/错误、JSON/Schema/引用校验失败仍消耗。跨上海午夜时在实际调用前把旧日预留迁移到调用发生日，不能突破新日上限。

管理后台用户列表显示普通用户今日已用/剩余，并提供“重置今日分析次数”。后端仅允许管理员操作普通用户，目标身份由 auth.db 查询，客户端不能提交 user id。重置只清零已消费次数，仍在队列中的预留继续占位，避免免费调用竞态。auth.db 新表 `ai_quota_reset_audit` 只记录操作者管理员 id、目标用户 id、重置时间和重置前已用次数，不含 prompt、结果或凭证。所有 DDL/ALTER 均幂等兼容旧 SQLite；历史任务和 insight 不变。

本阶段未改变模型、thinking、Context Compiler、输出 schema、3.5 benchmark 和 AI debug 日志；未部署。

### 16.1 部署前题页入口与用户公告

题页生成器现在从每题 `LEETCODE_SLUGS` 和统一 `LEETCODE_BASE` 只生成一次 `leetcode_link`，在“题目与约束”区块末尾和原有“力扣原题”文末区块各复用一次。未登记 slug 的题目仍不显示入口；HTML 构建继续统一给外链添加 `target=_blank` 与 `rel="noopener noreferrer"`。100 份题页 Markdown 和对应 HTML 已重新生成。

沿用 cockpit 既有的 `forge-ann-seen` 版本化公告弹层，公告版本更新为 `2026-09-08-analysis-quota-leetcode`，只向用户说明动态进度与处理阶段提示、每日三次与联系管理员重置、题面后新增原题入口且文末入口保留，不包含内部实现信息。
