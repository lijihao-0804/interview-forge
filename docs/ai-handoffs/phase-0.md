# AI 学习教练阶段 0 交接：数据盘点与指标契约

> 历史快照说明（2026-09-08）：本文记录阶段完成时的实现与部署状态，不代表当前生产环境。现行线上状态以根目录 `README.md`、`docs/深度审查与修复报告-2026-09-08.md` 和 VPS 部署指南为准。

> 历史快照说明（2026-09-08）：本文记录阶段完成时的实现与部署状态，不代表当前生产环境。现行线上状态以根目录 `README.md`、`docs/深度审查与修复报告-2026-09-08.md` 和 VPS 部署指南为准。

> 状态：COMPLETE
>
> 完成日期：2026-09-07
>
> 契约版本：analytics-v1-draft
>
> 本阶段性质：只读盘点与设计，不包含业务代码施工

## 1. 完成内容

本阶段已经完成：

- 核对学习库、账户库、题库和书架目录的真实代码来源；
- 建立数据字典和数据边界；
- 固化 Hot 100、书架、提交、标记和计划的现有统计语义；
- 定义指标契约 v1 和首批风险信号；
- 定义 indicator → signal → action → outcome 追溯协议；
- 建立第一版技能/知识点词表和题目映射协议；
- 编写 14 个合成数据验收场景；
- 执行现有全站静态检查并记录基线；
- 识别 3 项应在阶段 1 处理或规避的数据质量风险。

本阶段没有：

- 修改 Python、HTML、CSS、JavaScript 或测试代码；
- 安装 LangChain 或任何依赖；
- 调用模型 API；
- 读取任何真实用户数据库的数据行；
- 创建或迁移数据库；
- 修改配置、Git 忽略规则或部署脚本；
- 部署到 VPS。

## 2. 核查范围与事实基线

### 2.1 代码来源

| 范围 | 权威来源 |
|---|---|
| 学习库路径、Schema、迁移、指标与 API | `tools/study_server.py` |
| 书架模块定义和顺序 | `tools/library_catalog.py` |
| Hot 100 题目、分类和元数据 | `tools/build_hot100.py` |
| 生成后的模块/章节清单 | `library/manifest.json` |
| 当前全站检查 | `tools/check_hot100.py` |
| 分阶段实施边界 | `plan.md` |

### 2.2 已验证规模

- Hot 100：100 道题；
- Hot 100 算法分类：17 个；
- 书架：37 个模块；
- 书架 manifest：709 个章节；
- 当前重复 `content_id`：0；
- `python .\tools\check_hot100.py`：`errors: 0`、`warnings: 0`；
- 检查脚本生成的临时目录已清理。

这些数字是 2026-09-07 的快照，不应硬编码进后续分析器。运行时应从题库和 manifest 计算总数。

## 3. 数据库边界

### 3.1 每用户学习库

真实多用户路径为：

```text
data/users/<username>/hot100-study.db
```

依据：

- `tools/study_server.py:69-76`：默认库、`auth.db` 和用户库根目录；
- `tools/study_server.py:79-81`：用户名路径白名单；
- `tools/study_server.py:512-516`：`user_db_path()`。

学习分析只允许接收认证层已经解析出的当前用户数据库路径。分析函数不得接收前端提交的用户名、任意文件路径或用户 ID。

### 3.2 账户库

`data/auth.db` 包含：

- `users`、`sessions`、`invite_codes`；
- `feedback`、`chat_messages`、`avatars`。

依据：`tools/study_server.py:392-444`。

`auth.db` 不是学习分析数据源。用户名、昵称、角色、密码哈希、会话、反馈、聊天室和头像均不得进入个人学习上下文。

## 4. 学习库数据字典

Schema 来源：`tools/study_server.py:128-205`；初始化和幂等迁移：`tools/study_server.py:220-247`。

### 4.1 `study_events`

| 字段 | 含义 | 契约 |
|---|---|---|
| `id` | 本地事件流水号 | 仅用于稳定排序，不代表业务时间 |
| `problem_id` | Hot 100 题号 | 必须存在于 `PROBLEM_BY_ID` |
| `action` | `view` / `complete` | 当前有效新逻辑只使用 view；complete 是旧兼容路径 |
| `studied_at` | 带偏移 ISO 时间 | 事件时间 |
| `study_date` | 写入时的本地日期 | 旧统计字段 |
| `round_no` | 手动完成轮次 | view 必须为空；complete 必须非空 |
| `source` | 事件来源 | 默认 `learning-site` |

题目浏览由 `record_view()` 写入，同题 60 秒内重复浏览不落库：`tools/study_server.py:1136-1165`。

### 4.2 `submissions`

| 字段 | 含义 | 契约 |
|---|---|---|
| `id` | 本地流水号 | 不能代替真实提交时间 |
| `problem_id` | Hot 100 题号 | 必须存在于题库 |
| `status` | `ac` / `wa` | 第一版仅有两态 |
| `lang` | 语言 | 最长 40 字符 |
| `runtime_ms` | 运行时间 | 可空，不用于第一版掌握判断 |
| `memory_kb` | 内存 | 可空，不用于第一版掌握判断 |
| `submitted_at` | 带偏移 ISO 时间 | 提交事实的权威时间 |
| `source` | manual/bookmarklet/extension/sync | 分析必须保留来源 |
| `lc_id` | 力扣提交 ID | 非空时全库唯一；同步去重依据 |

手工提交入口：`tools/study_server.py:2181-2219`；汇总：`tools/study_server.py:2235-2289`；同步去重和写入：`tools/study_server.py:2514-2603`。

### 4.3 `content_events`

| 字段 | 含义 | 契约 |
|---|---|---|
| `id` | 本地事件流水号 | 仅作为同时间戳的次级排序 |
| `module_id` | 书架模块 ID | 必须存在于 manifest |
| `content_id` | 章节 ID | 当前隐含要求全 manifest 全局唯一 |
| `action` | `view` / `complete` | 浏览和完成必须分开 |
| `studied_at` | 带偏移 ISO 时间 | 事件时间 |
| `study_date` | 写入时本地日期 | 旧统计字段 |
| `round_no` | 章节完成轮次 | complete 必填、view 为空 |

`valid_content()` 同时验证模块与章节：`tools/study_server.py:1460-1468`；浏览 60 秒去重：`tools/study_server.py:1471-1492`；章节完成：`tools/study_server.py:1495-1523`。

### 4.4 `marks`

主键为 `(target_type, target_id)`，标记值为：

- `mastered`；
- `reviewing`；
- `weak`。

人工标记是用户表达，不等同于统计结论。分析结果必须同时保留“用户标记”和“行为证据”，冲突时不能静默覆盖。

### 4.5 `settings`

键值配置表。当前允许的学习设置只有 `daily_goal_rounds`，服务端限制为 1～50，异常值回落为 3。依据：`tools/study_server.py:1360-1363`、`tools/study_server.py:1765-1783`。

### 4.6 `plan_pins`

| 字段 | 含义 |
|---|---|
| `problem_id` | 被排期题号，同时是主键 |
| `for_date` | 生效日期 |
| `created_at` | 创建时间 |

今日计划读取时会删除 `for_date < today` 的旧 pin，当日 pin 可重复读取：`tools/study_server.py:1951-1963`。因此它只能表示当前显式排期，不能用于还原完整历史计划。

### 4.7 `credentials`

保存力扣会话与 CSRF 等连接凭证。该表永远禁止进入统计响应、日志、模型上下文、测试夹具和缓存键。

## 5. 现有业务口径

### 5.1 Hot 100 轮次

权威口径：

```text
problem_rounds = COUNT(DISTINCT local_date(submitted_at))
WHERE status = 'ac'
```

- 同一题同一自然日多次 AC 只增加一轮；
- 同一题跨自然日 AC 分别增加轮次；
- WA 不增加轮次；
- `study_events.complete` 是旧兼容数据，不与 AC 轮次相加；
- 实现依据：`dashboard_data()`，`tools/study_server.py:1224-1296`；`ac_problem_progress()`，`tools/study_server.py:1526-1541`。

全站“总体轮次”不是所有题轮次求和：

- 第 1 轮：至少 90 道题各达到 1 轮；
- 第 k>1 轮：已完成题目中超过一半达到第 k 轮；
- 阈值：`ROUND_COMPLETE_THRESHOLD = 90`，见 `tools/study_server.py:951`、`1253-1271`。

后续 API 必须分别命名：

- `problem_round_count`：单题 AC 自然日数；
- `completed_problem_count`：至少一次 AC 的题数；
- `curriculum_round`：上述全站总体轮次；
- `round_actions`：某窗口内题目轮次事件数量。

不得统一叫含义不清的 `rounds`。

### 5.2 书架轮次和进度

- 非 Hot100 章节：每条 `content_events.complete` 增加一轮；
- 模块进度：有至少一轮的章节数 / manifest 当前章节总数；
- Hot100 书架模块：由题目 AC 日期推导，不读取旧手动 complete；
- 实现依据：`tools/study_server.py:1575-1600`。

章节浏览不等于完成，完成不等于掌握。

### 5.3 浏览

- 同一对象 60 秒内重复 view 不写入；
- 60 秒去重是采集降噪，不是用户“只看了一次”的证明；
- view 数量用于参与度和“浏览未通过”信号，不可独立证明掌握或不会。

### 5.4 复习到期

题目间隔：1、3、7、15、30、60 天，之后封顶 60 天。

章节间隔：3、7、15、30、60、90 天，之后封顶 90 天。

依据：`tools/study_server.py:90-125`。

定义：

```text
due_date = local_date(last_completed_at) + interval(round_count)
due       = due_date <= as_of_date
overdue   = due_date < as_of_date
overdue_days = max(0, as_of_date - due_date)
```

当前题目逾期超过 60 天会进入“需重学”集合：`tools/study_server.py:1648-1691`。

### 5.5 活跃和连续学习

活跃日来自以下集合的日期并集：

- 题目 view；
- 任意提交；
- 非 Hot100 章节 view/complete。

连续学习：

- 今天有活动，从今天向前连续计数；
- 今天没有活动，则允许从昨天开始；
- 中间缺一天即停止。

依据：`tools/study_server.py:1317-1359`。

现有 `summary.active_days` 是全部历史活跃日数，不是最近 7/14/30 天。

### 5.6 提交来源与去重

- 同步记录：`lc_id` 非空时唯一；
- 手工、书签和扩展记录：允许同题同时间附近多条，不主动去重；
- 指标默认统计实际存储的合法提交；
- 同步和手工记录可能描述同一次现实提交，v1 不擅自合并，只在 `data_quality` 标记潜在重复；
- 任何掌握结论都应带来源分布。

## 6. 时间与窗口契约

### 6.1 业务时区

v1 明确使用 `Asia/Shanghai` 作为业务时区。吉隆坡 VPS 与上海目前同为 UTC+8 且无夏令时，因此当前自然日一致，但实现不能继续依赖操作系统偶然配置。

已有记录为带数值偏移的 ISO 时间。阶段 1 应先解析 `submitted_at/studied_at`，转换到业务时区后再取日期；不能长期依赖 `substr(timestamp, 1, 10)`。无法解析的记录不参与时间窗口，并进入 `data_quality.invalid_timestamp_count`。

### 6.2 窗口

- `7d`：as_of 当日及之前 6 个本地自然日；
- `14d`：as_of 当日及之前 13 日；
- `30d`：as_of 当日及之前 29 日；
- 使用闭区间本地日期，未来时间不计入；
- “最近 N 条”按 `event_time DESC, id DESC`；
- 所有响应包含 `data_as_of` 和 `timezone`。

## 7. 指标契约 v1

每个指标输出至少包含：

```json
{
  "metric_id": "problem.1.wa_count.30d",
  "value": 3,
  "unit": "submissions",
  "window": "30d",
  "as_of": "2026-09-07T17:00:00+08:00",
  "source": ["submissions"],
  "sample_count": 3,
  "confidence": "high"
}
```

### 7.1 总体指标

| 指标 | 公式 | 空数据 |
|---|---|---|
| `completed_problem_count` | 至少一次 AC 的不同题号数 | 0 |
| `problem_completion_ratio` | completed / 当前题库总数 | 总数为 0 时 null |
| `curriculum_round` | 现有 90 题首轮、后续过半规则 | 0 |
| `active_days.{7,14,30}d` | 窗口内活跃日期去重数 | 0 |
| `current_streak_days` | 现有连续日规则 | 0 |
| `today_problem_round_actions` | 今日不同题 AC 数 | 0 |
| `today_content_round_actions` | 今日非 Hot100 complete 行数 | 0 |
| `due_problem_count` | due_date <= today | 0 |
| `overdue_problem_count` | due_date < today | 0 |
| `due_content_count` | 章节 due_date <= today | 0 |
| `last_learning_at` | 所有允许学习事件最大时间 | null |

### 7.2 单题指标

| 指标 | 公式 |
|---|---|
| `view_count.all` | 去重采集后 view 行数 |
| `view_days.all` | view 本地日期去重数 |
| `submit_count.all/30d` | 合法提交行数 |
| `ac_count.all/30d` | AC 提交行数 |
| `wa_count.all/30d` | WA 提交行数 |
| `ac_day_count` | AC 本地自然日数，即题目轮次 |
| `ever_ac` | 是否存在 AC |
| `last_submission_status` | 按 submitted_at、id 排序后的最后状态 |
| `last_submitted_at` | 最大合法提交时间 |
| `last_ac_at` / `last_wa_at` | 对应状态最大时间 |
| `wa_after_latest_ac_count` | 时间严格晚于最近 AC 的 WA 数 |
| `mark` | 用户当前人工标记 |
| `next_due_date` | 最近 AC 日期与轮次推导 |
| `overdue_days` | 严格按第 5.4 节 |

`pass_rate = ac_count / submit_count`；无提交时为 null，不能返回 0。

### 7.3 模块与章节指标

| 指标 | 公式 |
|---|---|
| `module_total_contents` | 当前 manifest 章节数 |
| `module_started_contents` | 有 view 或 complete 的不同章节数 |
| `module_completed_contents` | 至少一轮的不同章节数 |
| `module_completion_ratio` | completed / total |
| `module_last_activity_at` | 模块 view/complete 最大时间 |
| `content_round_count` | 非 Hot100 complete 行数；Hot100 使用 AC 日数 |
| `content_due_date` | 章节专用间隔计算 |

manifest 中已删除但数据库仍存在的章节不计入当前完成比例，数量写入 `data_quality.orphan_content_count`。

### 7.4 置信度

第一版不声称计算统计学置信区间，只使用可解释等级：

- `high`：直接事实或样本达到信号最低要求；
- `medium`：证据存在但样本较少、来源混合或较旧；
- `low`：只能提示观察，不允许下掌握结论；
- `insufficient`：不满足最低数据量。

响应必须同时给出 `sample_count` 和原因，不能只给一个主观置信度。

## 8. 风险信号契约 v1

以下阈值都是**初始可配置假设**，用于阶段 1 测试，不代表教育学定论。阈值必须集中配置并带 `rule_version`。

| 信号 | v1 初始条件 | 默认级别 | 排除/降级 |
|---|---|---|---|
| `repeat_wa` | 30 天内 WA ≥3 且历史从未 AC | high | 1～2 次 WA 不触发；潜在重复数据降置信度 |
| `wa_after_ac` | 曾 AC，且最近 AC 之后存在 WA | medium；30 天内 ≥2 次为 high | 必须按时间而非 id 判断 |
| `view_without_ac` | 30 天内 view ≥3、跨 ≥2 个自然日，且从未 AC | medium | 单日刷新或不足 3 次不触发 |
| `due_overdue` | 已完成且 due_date <= today | due today 为 low；1～7 天 medium；8～60 天 high；>60 天 relearn | 未完成对象不算“逾期复习” |
| `stalled_module` | 模块 completed>0、completed<total，且连续 14 天无活动 | medium；30 天 high | 总章节为 0、已完成或数据时间无效不触发 |
| `data_insufficient` | 无学习事件，或目标分析所需样本不足 | informational | 必须返回具体 reason codes |

`data_insufficient.reason_codes` 至少包括：

- `no_learning_data`；
- `no_submission_data`；
- `too_few_attempts`；
- `skill_unmapped`；
- `invalid_timestamps`；
- `mixed_source_possible_duplicate`。

信号只说明“值得关注”，不直接声明用户“不会”“退步”或“掌握”。

## 9. 追溯和稳定 ID 协议

链路固定为：

```text
indicator → signal/insight → action → outcome
```

### 9.1 ID 格式

```text
metric:<schema_version>:<entity_type>:<entity_id>:<metric_name>:<window>
evidence:<snapshot_hash>:<source_table>:<normalized_primary_key_or_fact_hash>
signal:<rule_version>:<signal_type>:<entity_type>:<entity_id>:<window_end>
action:<signal_id>:<action_type>:<ordinal>
outcome:<action_id>:<measurement_window>
```

示例：

```text
metric:analytics-v1:problem:1:wa_count:30d
signal:rules-v1:repeat_wa:problem:1:2026-09-07
action:signal:rules-v1:repeat_wa:problem:1:2026-09-07:review_solution:1
```

实现时 ID 内不放用户名、昵称、Cookie 或数据库路径。完整 ID 可使用规范 JSON 的 SHA-256 短摘要，响应同时保留可读字段。

### 9.2 可追溯要求

- signal 必须引用一个或多个 metric/evidence ID；
- action 必须引用 signal ID；
- outcome 必须引用 action ID，并记录用户采纳、完成或忽略状态；
- AI 不能创建不存在的 evidence ID；
- 阈值变化生成新的 `rule_version`，不得重写旧结果含义；
- outcome 的指标变化只表示相关性，不自动声称由建议导致。

## 10. 技能/知识点模型草案

### 10.1 第一层：算法技能

根据 `tools/build_hot100.py:73-90` 的 17 个现有分类建立：

```text
algo.hash-table
algo.two-pointers
algo.sliding-window
algo.substring
algo.array
algo.matrix
algo.linked-list
algo.binary-tree
algo.graph
algo.backtracking
algo.binary-search
algo.stack
algo.heap
algo.greedy
algo.dynamic-programming
algo.multidimensional-dp
algo.techniques
```

现有 100 题都具有一个 category，因此“算法分类粗粒度映射”当前可达到 100%。这不等于更细知识点已覆盖。

### 10.2 第一层：课程技能

根据 `tools/library_catalog.py:63-136` 和 manifest，为每个当前模块建立：

```text
module.<module_id>
```

例如 `module.java-core`、`module.java-concurrency`、`module.rag`、`module.langchain`。当前 37 个模块、709 个章节都能通过所属模块得到一个粗粒度技能节点，因此“模块级映射”当前可达到 100%。

阶段 0 不从章节正文自动生成细粒度技能，不把模块简介中的词直接当作权威前置关系。细粒度技能必须人工审核后增加。

### 10.3 技能 Schema

```json
{
  "schema_version": "skills-v1",
  "skill_id": "algo.sliding-window",
  "name": "滑动窗口",
  "aliases": ["双指针窗口", "sliding window"],
  "parent_ids": ["domain.algorithms"],
  "status": "active",
  "source": {
    "type": "hot100_category",
    "value": "滑动窗口"
  },
  "review_status": "human_verified"
}
```

### 10.4 `problem_skill_map` 协议

```json
{
  "schema_version": "problem-skill-map-v1",
  "problem_id": 3,
  "skills": [
    {
      "skill_id": "algo.substring",
      "weight": 1.0,
      "mapping_source": "existing_category",
      "review_status": "human_verified"
    }
  ]
}
```

规则：

- `problem_id` 必须存在；
- `skill_id` 必须来自同版本词表；
- 同题权重总和建议为 1.0；
- `mapping_source` 只允许 existing_category/manual_review/imported_reviewed；
- AI 建议的映射必须先标 `proposed`，不能参与生产分析；
- 无映射返回 `skill_unmapped`，不得让模型猜测。

覆盖率：

```text
problem_mapping_coverage = 有至少一个 human_verified skill 的题数 / 当前题目总数
content_module_coverage = 有合法 module skill 的当前章节数 / 当前章节总数
fine_skill_coverage = 有至少一个非粗粒度人工技能的对象数 / 当前对象总数
```

粗粒度和细粒度覆盖率必须分开报告。

## 11. 合成测试场景与预期

所有场景使用临时 SQLite、固定 `as_of=2026-09-07T12:00:00+08:00`，不得复制真实用户库。

### 场景 1：新用户空数据

输入：六张学习表为空。

预期：所有计数为 0；比率和最后时间为 null；触发 `data_insufficient/no_learning_data`；无 weakness 结论。

### 场景 2：只有浏览没有提交

输入：题 1 在 9 月 1、3、7 日各一条有效 view，无 submission。

预期：view_count=3、view_days=3、ever_ac=false、pass_rate=null；触发 `view_without_ac`，不触发 `repeat_wa`。

### 场景 3：多次 WA 从未 AC

输入：题 2 在 30 天内 3 次 WA，无 AC。

预期：wa_count.30d=3、ac_day_count=0；触发 high `repeat_wa`；不增加轮次。

### 场景 4：WA 后 AC

输入：题 3 先 2 次 WA，后 1 次 AC。

预期：ever_ac=true、轮次=1、last_status=ac；不触发 `repeat_wa` 或 `wa_after_ac`。

### 场景 5：AC 后再次 WA

输入：题 4 于 9 月 1 AC，9 月 3 WA。

预期：轮次=1、wa_after_latest_ac_count=1、last_status=wa；触发 medium `wa_after_ac`。

### 场景 6：同日多次 AC

输入：题 5 同一本地自然日 3 次 AC。

预期：ac_count=3、ac_day_count/round=1、今日轮次动作只按不同题计 1。

### 场景 7：跨日多次 AC

输入：题 6 在 9 月 5、6、7 日分别 AC。

预期：ac_count=3、round=3；按题目间隔第 3 档计算 next_due=9 月 14 日。

### 场景 8：人工标记与表现冲突

输入：题 7 标记 mastered，但最近 AC 后出现 2 次 WA。

预期：保留 mark=mastered，同时触发 high `wa_after_ac`；输出 conflict 标志，不自动改用户标记。

### 场景 9：章节完成后到期

输入：普通章节 9 月 4 完成第 1 轮。

预期：章节间隔为 3 天，due_date=9 月 7，今日 due；不得使用题目第 1 轮的 1 天间隔。

### 场景 10：大量旧数据但近期无活动

输入：一万条记录均早于 90 天，最近 30 天为空。

预期：历史总量正常；7/14/30 天活跃均为 0；若模块部分完成且 30 天无活动，触发 high `stalled_module`；查询结果有硬上限。

### 场景 11：手工与同步记录混合

输入：同题一条 manual AC、两条相同 `lc_id` 的 sync AC 尝试写入。

预期：数据库只接受一条该 `lc_id`；manual 保留；来源分布正确；可能现实重复时标 `mixed_source_possible_duplicate`，v1 不静默删除 manual。

### 场景 12：时区跨日

输入：`2026-09-06T16:30:00+00:00` 和 `2026-09-07T00:40:00+08:00`。

预期：转换到 Asia/Shanghai 后均属于 9 月 7 日；同题均 AC 时只计一轮。

### 场景 13：章节 ID 冲突

输入：测试 manifest 中两个模块使用同一个 `content_id`。

预期：目录/契约校验失败，拒绝进入分析；不能把两个模块的记录合并。

### 场景 14：本地 ID 与提交时间逆序

输入：id 较大的提交时间更早，id 较小的提交时间更晚。

预期：`last_submission_status` 取 submitted_at 更晚者；`wa_after_ac` 按提交时间判断，不能按 MAX(id)。

## 12. 数据质量风险

### R1：章节完成接口返回的 next_due 口径不一致

`complete_content()` 的注释称使用章节间隔，但返回值在 `tools/study_server.py:1522` 调用的是 `due_after()`；`daily_data()` 在 `tools/study_server.py:1710-1712` 使用 `due_after_content()`。

影响：完成章节后即时显示的日期可能比日清单中的日期早。

阶段 1 要求：新增分析器统一使用 `due_after_content()`；是否修复现有接口作为单独兼容性修复处理。

### R2：章节 ID 全局唯一是隐含前提

`uq_content_round` 为 `(content_id, round_no)`，部分查询和索引也只按 `content_id`，见 `tools/study_server.py:157-171`、`1477-1485`、`1504-1507`。

当前 manifest 的 709 个章节 ID 实测无重复，因此现状可用。但阶段 1 前应增加 manifest 契约检查，明确禁止跨模块重复 ID；否则应整体迁移为复合键，不能只改一条 SQL。

### R3：last_status 的顺序依据不可靠

`submission_summary()` 使用每题 `MAX(id)` 选择最后状态，见 `tools/study_server.py:2258-2262`，但 `last_submitted_at` 按时间取最大值。同步批次写入顺序不应被当作事件时间保证。

影响：历史同步或导入逆序时，最后状态和 `wa_after_ac` 可能误判。

阶段 1 要求：所有时序指标按 `submitted_at DESC, id DESC`；增加场景 14。

## 13. 多用户、安全与隐私

1. 只从当前认证用户的 `user_db_path(username)` 读取；
2. 不读取默认库来替代找不到的用户库；
3. 不允许请求参数指定其他用户名或数据库路径；
4. 不连接 `auth.db` 获取昵称、聊天、反馈、角色或会话；
5. 永不选择 `credentials.value`；
6. 缓存键至少包含不可逆用户作用域、schema_version 和数据版本；
7. evidence ID 不包含用户名和磁盘路径；
8. 日志只记录任务 ID、耗时、数量和错误类别，不记录完整上下文；
9. 合成测试使用临时库；
10. 统计响应默认不返回完整提交历史，证据采用有限字段和硬上限。

## 14. 集中自审

### 14.1 已检查

- 数据字典是否来自真实 Schema；
- Hot100 和非 Hot100 是否使用不同轮次来源；
- 同日 AC 是否去重；
- 浏览是否错误等同掌握；
- 题目和章节间隔是否分开；
- 多用户学习库是否与 auth.db 分离；
- 阈值是否明确标为初始假设；
- 技能映射是否禁止 AI 未审核猜测；
- 合成样本是否覆盖空值、时区、来源、冲突和逆序；
- 是否存在本阶段越界施工。

### 14.2 审查后修订

- 将模糊的“最近活跃”拆成 7/14/30 天窗口；
- 将单题轮次、总体轮次和窗口轮次动作改为不同名称；
- 将 last_status 的权威顺序改为事件时间；
- 将章节 ID 全局唯一从隐含假设提升为显式契约；
- 将技能覆盖率拆为粗粒度和细粒度；
- 将信号阈值标为可配置初始假设；
- 增加来源混合、无效时间和孤儿章节数据质量字段。

### 14.3 子代理执行记录

按用户要求，两次调用 `gpt-5.6-luna`、`reasoning_effort=max` 子代理执行阶段 0。两个实例均长时间保持 running，未返回错误、文件或最终结果，在多次收敛后仍无产出，最终被关闭。为避免把未完成代理结果冒充交付，本报告由主代理依据实际代码核查完成。

后续继续使用 Luna 时，先用单函数或单表的 5～10 分钟有界任务验证通道，再扩大任务；子代理结果必须经过主代理逐项验收。

## 15. 测试结果

- `python .\tools\check_hot100.py`：通过；
- 结果：100 题、17 个题目专题页、37 个书架模块、709 个章节、无坏链；
- `errors: 0`；
- `warnings: 0`；
- manifest 章节 ID 重复检查：0；
- 未运行真实模型测试；
- 未运行真实用户数据测试；
- 本阶段没有新增代码，因此没有新增自动测试文件。

## 16. 阶段 1 交接建议

阶段 1 只实现确定性学习分析，推荐顺序：

1. 先把本文件第 7～9 节转成纯函数和 Pydantic/dataclass 之外的普通结构；
2. 使用临时 SQLite 实现第 11 节金标准测试；
3. 统一时间解析和业务时区；
4. 按提交时间实现 last_status 和 wa_after_ac；
5. 为 manifest 增加 content_id 全局唯一检查；
6. 实现只读 `analytics-v1` 响应和稳定 evidence ID；
7. 测试多用户路径隔离、缓存失效和 10,000 条记录性能；
8. 保持无 LangChain、无模型调用、无前端入口；
9. 一次集中代码审查后再决定是否部署隐藏接口。

阶段 1 不应提前实现：

- AI 文案；
- Prompt；
- LangChain/LangGraph；
- 长期记忆；
- 向量数据库；
- 课程路线；
- 写计划工具。

## 17. 部署与回滚

- 是否部署：否；
- 数据库变化：无；
- 配置变化：无；
- 回滚：删除本交接文档即可，不涉及运行系统；
- 下一阶段开始条件：用户确认进入阶段 1。
