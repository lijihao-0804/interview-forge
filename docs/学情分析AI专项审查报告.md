# InterviewForge 学情分析 AI 专项审查报告

审查日期：2026-09-08

审查范围：学情分析 AI（确定性学习分析、上下文编译、异步任务、结构化结果、降级、额度、可观测性与权限边界）

审查约束：不调用真实大模型，不把模型质量或供应商可用性表述为已验证事实；本报告只记录代码审查和本地自动化测试证据。

## 1. 结论摘要

当前实现是一条“规则分析 → 上下文筛选 → 可选模型调用 → 本地结构校验 → 持久化任务结果”的受控链路。AI 被设计为可选能力：关闭、未配置、依赖缺失或调用失败时，原有学习功能与规则分析仍可用。

本轮专项修复只涉及调试日志：今后的 `AI_DEBUG_LOG_PATH` 日志不再写入完整 context、用户请求/profile、题目明细、模型原始输出或公开结果，只保留哈希、长度/条数、耗时、usage、状态和错误分类等运行元数据。权威实现位于 `tools/ai_coach.py` 的 `debug_ai_event`、`_debug_content_metadata`、`generate_ai_insight`，以及 `tools/study_server.py` 的 `request_prepared` 事件调用点。

修复不改变模型选择、Prompt、额度、缓存复用、任务状态、队列并发或前端交互。

## 2. 功能边界

### 2.1 AI 负责什么

- 对服务端已经计算、筛选和脱敏后的学习事实进行解释；
- 在结构化字段中给出 strengths、weaknesses、actions、confidence 和 data_gaps；
- 通过 `support_refs` 关联服务端允许暴露的证据引用；
- 将生成结果保存为当前用户学习库中的 AI 任务/洞察，供页面刷新后恢复。

### 2.2 AI 不负责什么

- 不直接读取 auth.db，不决定用户身份或数据库路径；
- 不执行 Shell、SQL、HTML、JavaScript 或站内写操作；
- 不自行发现候选课程、修改复习计划或替用户提交力扣代码；
- 不把用户输入、题目标题或未来材料当作系统指令；
- 不替代确定性统计，也不能把样本外推为全量事实。

系统提示中的边界约束见 `tools/ai_coach.py:118-156`；上下文编译器的不可信数据边界见 `tools/context_compiler.py:260-275`。

## 3. 数据流与生命周期

```text
当前登录会话
  ↓
  user_db_path(username)                  study_server.py:user_db_path
  ↓
  analytics_cached(db)                    study_server.py:analytics_cached
  ↓
build_learning_analytics(...)           learning_analytics.py:709-732,789-825
  ↓
  compile_learning_context(..., small)    study_server.py:/api/coach/analyze
  ↓
  create_ai_task(...)                     ai_coach.py:1920-2010
  ↓
ai_tasks（queued/running/...）
  ↓
后台 worker + 可选 ChatModel              ai_coach.py:1551-1581,1762-1862
  ↓
本地 validate_insight_payload            ai_coach.py:638-733
  ↓
ai_insights + 页面可读结果
```

### 3.1 确定性分析

`build_learning_analytics` 只打开传入学习库的 SQLite 只读连接，设置 `query_only`，只读取 `study_events`、`submissions`、`content_events` 和 `marks`（`tools/learning_analytics.py:433-460,498-529,789-825`）。缺表、空库、无效时间戳会进入数据质量/数据不足结果，而不是强行生成结论。

规则分析版本和输出上限有显式常量（`tools/learning_analytics.py:21-23,39-61`），上下文编译器再按 small/medium/large 预算裁剪（`tools/context_compiler.py:44-87`）。一键分析当前固定使用 small 预算（`tools/study_server.py:3674-3687`）。

### 3.2 上下文投影

上下文编译器采用正向白名单，不复制整个 analytics 对象；它区分事实、信号、证据、数据质量和省略项，且不执行用户材料中的命令（`tools/context_compiler.py:3-7,260-275`）。模型侧再次构造 LLM projection，仅发送允许字段（`tools/ai_coach.py:868-929`）。

### 3.3 异步任务与持久化

AI 表追加在每个用户的学习库中，而不是 auth.db（`tools/ai_coach.py:75-115`）。`create_ai_task` 通过快照哈希、Prompt 版本和模型键复用相同结果，并在事务内预留额度（`tools/ai_coach.py:1905-1951`）。worker 启动后更新 queued/running 状态，成功才写入 `ai_insights`（`tools/ai_coach.py:1762-1857`）。服务重启后遗留任务会收敛为可见的失败状态（`tools/ai_coach.py:1589-1612`）。

## 4. 权限隔离与安全边界

- 路由先通过 `StudyHandler.do_POST` 的登录门禁，再由 `user_db_path` 从当前会话用户名解析学习库；客户端不能指定 username、db_path 或快照。
- 分析路径在 `USERS_DIR` 内做 realpath 约束，防止传入库路径越界（`tools/study_server.py:469-483`；`tools/learning_analytics.py:408-430`）。
- 每个用户的 `ai_tasks`、`ai_insights` 和额度表在其独立数据库内；任务 ID 查询只发生在当前用户库中（`tools/ai_coach.py:1981-2004`）。
- context API 只接受明确字段白名单，`/api/coach/analyze` 拒绝任何请求参数（`StudyHandler.do_POST`）。
- 模型输出必须通过字段、长度、support_ref 和引用闭包校验，校验失败不会被当作成功洞察（`tools/ai_coach.py:638-733`）。

## 5. 失败降级、额度与并发

### 5.1 确定性降级

AI 关闭、未配置或可选依赖缺失时，能力接口仍报告规则分析可用；模型调用前后均保留规则 fallback（`ai_capability`、`generate_ai_insight`、后台 worker）。超时、429、供应商错误、非法 JSON 和结构校验失败会转换为受控错误，不向用户回显密钥、路径或底层异常（`AIServiceError` 与 `StudyHandler.do_POST` 的受控异常分支）。

### 5.2 额度

普通用户额度按 `Asia/Shanghai` 自然日计算，当前固定为每日 3 次（`tools/ai_coach.py:49-51,366-374,377-395`）。任务入队先预留名额，首次外部请求前消费；缓存复用、前置失败、排队取消和队列失败不应计入已消费次数（`tools/ai_coach.py:406-483,1945-1950`）。管理员不受普通用户每日额度限制，但管理员重置普通用户额度的接口会写最小审计记录（`tools/study_server.py:1040-1070,3823-3829`）。

### 5.3 并发与恢复

worker 数量与调用槽受配置限制，调用槽在进程内全局约束（`tools/ai_coach.py:1535-1548,1574-1581`）。任务持久化后才入队，避免短暂的插入窗口被恢复逻辑误判（`tools/ai_coach.py:1924-1965`）。

## 6. 隐私与本次日志修复

### 6.1 修复前风险

修复前，`study_server.py` 的 `request_prepared` 事件将整个 context 作为字段传入；模型响应事件还会记录 `raw_output`，验证成功事件记录公开结果。这会使调试日志保存用户请求、profile、题目标签、学习统计及模型输出，即使日志文件不在 Git 中，也构成服务器或备份介质上的学习数据副本。

本地审查时发现 `.maintenance/ai-debug.jsonl` 已存在历史调试数据（80 条事件、约 196,927 字节）；本轮没有删除或改写该历史文件。部署前应按运维流程安全轮转/清理，并检查备份、压缩包和日志采集端是否含旧内容。

### 6.2 修复后行为

- `debug_ai_event` 在写文件前丢弃内容字段 deny-list（`tools/ai_coach.py:56-82`）；
- `request_prepared` 只写 snapshot/context 哈希、字符数和事实/信号/证据条数（`StudyHandler.do_POST` 的 `/api/coach/analyze` 分支）；
- `model_response` 只写原始响应的字符数与 SHA-256，不写原文（`tools/ai_coach.py:1494-1500`）；
- `validation_succeeded` 只写验证结果字符数与 SHA-256，不写结果对象（`tools/ai_coach.py:1515-1522`）；
- 其它事件仅保留时间、任务/请求关联 ID、调用次数、耗时、usage、配置哈希、状态和错误分类。
- `AI_DEBUG_LOG_PATH` 未开启时跳过这些内容的序列化/哈希计算；只有显式开启调试日志才计算相关元数据，避免给默认线上请求增加不必要开销。

哈希用于同一次请求的关联，不用于恢复原文；日志中仍不应记录密钥、完整 endpoint、用户身份或模型原始名称。

## 7. 可观测性现状

当前可观测字段覆盖：任务生命周期、worker 状态、调用槽等待时间、模型准备耗时、首 token/生成耗时、usage 状态、响应解析与校验耗时、错误类别和总耗时（`tools/ai_coach.py:1344-1512,1781-1862`）。这足以定位“排队慢、模型慢、解析失败、校验失败、服务商错误”等类别，但不提供内容级调试。

仍需补充的运维能力：

- `AI_DEBUG_LOG_PATH` 的文件权限、轮转、最大大小和保留期限；
- 日志写入失败的计数器或受控告警（当前写失败被静默吞掉，`tools/ai_coach.py:84-90`）；
- 线上端到端的请求量、错误率、P95/P99 延迟和额度拒绝率指标；
- 对历史调试文件的清理和备份排除检查。

## 8. 性能审查

已存在的优化：dashboard 与 analytics 都有 60 秒进程内缓存，写操作会按用户库失效（`_dashboard_cached`、`analytics_cached`、`_invalidate_learning_caches`）；上下文编译有严格预算；AI 任务使用异步 worker，HTTP 请求不会等待模型完成。

主要机会：

1. analytics/dashboard cache miss 时在锁外计算，多个并发请求可能重复全量计算；可增加 per-user single-flight 或短暂 future/promise。
2. analytics 当前将四张表全量 SELECT 到内存，输出 limits 不限制输入读取（`tools/learning_analytics.py:498-529,54-61`）；数据增长后应使用 SQL 聚合、按时间窗口读取或受控分页，同时保持历史统计语义。
3. `check_hot100.py` 的 Node 语法检查已改为有上限的并行执行，完整发布检查由约 96.6 秒降至约 50 秒，同时保留具体失败文件定位。
4. 生成器已清理已知题页/章节目录的 stale HTML；未来新增生成目录时仍需把安全清理规则纳入构建链。

## 9. 测试现状与明确未测试项

本地已执行且通过：

- analytics、analytics API 与后端硬化专项回归：69 项通过；
- 全量 `unittest discover`：124 项通过；
- `python -m compileall -q tools`：通过；
- `python tools/check_hot100.py`：`errors=0`、`warnings=0`。

测试均未调用真实模型；AI 单元测试中的模型均为 fake/mock，因此不能据此证明真实供应商响应格式、网络延迟、费用或线上可用性。公网健康检查属于部署验收，部署后会补记在综合审查报告中，不作为模型能力证据。

未覆盖或覆盖不足的回归：

- `AI_DEBUG_LOG_PATH` 写出内容的隐私断言；
- 旧 debug 文件轮转/清理；
- nginx 反代真实请求头与限流 IP；
- 多进程部署时的全局并发上限；
- 大历史数据库的 analytics 内存/延迟曲线；
- 进程崩溃、网络断开、真实 HTTP 429/500/超时；
- 新增生成目录时 stale 产物清理规则的持续覆盖。

## 10. 后续建议与验收清单

部署前建议：

- 将本次 `ai_coach.py` 日志修复与主代理其它服务端修复放在同一可回滚提交中；
- 在服务器安全轮转历史 `.maintenance/ai-debug.jsonl`，确认压缩备份和日志采集端无旧副本；
- 确认 `AI_DEBUG_LOG_PATH` 默认关闭，若临时开启则设置最小文件权限、轮转和过期清理；
- 先做确定性接口、登录隔离、健康检查和静态资源回归，再决定是否启用 AI 配置；
- 保持真实模型验证另行授权，不用它替代自动化测试。

验收条件：

- [ ] `debug_ai_event` 生成的每条 JSONL 不含 `context`、`raw_output`、`result`、`user_request`、`profile`、题目标题或模型回复正文；
- [ ] 日志仍含可关联的事件名、任务 ID、哈希、字符数/条数、耗时、usage、状态和错误分类；
- [ ] AI 关闭或依赖缺失时，规则分析与原有学习功能仍可用；
- [ ] 快照复用不重复消费额度，队列取消/前置失败不消费，供应商调用失败按既定策略计费；
- [ ] 当前用户只能读取自己的任务、洞察、上下文预览和反馈记录；
- [ ] analytics/context 只读且不越出 `USERS_DIR`；
- [x] 本地自动化测试与 `check_hot100.py` 通过；
- [ ] 未将“未测试真实模型”误写成“模型已验证可用”。
