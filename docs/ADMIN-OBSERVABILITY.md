# Admin Observability

管理员后台按以下主题组织，原有管理员能力仍由原路由和服务提供：

- Overview：当前摘要、活跃用户、请求/AI/任务健康状态
- Traffic：请求趋势、状态码、5xx 错误率、P50/P95/P99、Endpoint 排名
- AI：AI turn、成功率、延迟、TTFT、token、模型和成本摘要
- Tools：工具调用、Action 审计和任务状态
- System：运行时、资源、数据库和诊断
- Logs：脱敏 JSONL 过滤与 request_id 排障入口
- Users：用户、角色、配额、反馈、邀请码和运营活跃指标

## Snapshot 与 Historical Metrics

`/api/admin/overview` 只提供当前摘要，不作为历史趋势查询入口。历史接口为：

- `GET /api/admin/metrics/requests?window=24h|7d|30d`
- `GET /api/admin/metrics/ai?window=24h|7d|30d`
- `GET /api/admin/metrics/users?window=24h|7d|30d`
- `GET /api/admin/metrics/tools?window=24h|7d|30d`

请求聚合写入 `data/observability.db`，与用户学习库分离。请求路由优先使用 FastAPI route template，动态路径只作为保守 fallback 归一化为 `{id}`，避免高基数。

请求延迟同时记录固定上界直方图（50、100、250、500、1000、2000、5000、10000、30000、60000 ms 和 `inf`）。P50/P95/P99 根据直方图累计计数计算，不使用平均值冒充百分位。观测写入是 best-effort，SQLite 短暂锁定或磁盘异常不会让业务请求失败。

AI Trace 继续保存在各用户学习库的 `ai_trace_events` 中，后台只读取状态、耗时、token、模型、错误类别和安全元数据。TTFT 从 Chat turn 开始到首个可见 `message.delta` 记录到 Trace 的 `metadata_json.ttft_ms`；普通 Tool Calling 不会把工具事件误当作首 token。

## 隐私边界

原始 JSONL 仍用于日志排障并沿用脱敏逻辑。后台接口和聚合表不保存或展示 prompt、聊天正文、Memory 正文、Tool 参数/结果、Cookie、密码或 API key。`request_id → AI Trace → Tool/Action` 通过安全 ID 和状态字段串联。

系统资源指标采用可选 `psutil` 或 Linux `/proc` fallback；Windows 上不可用的指标返回 `available=false`，不会使管理员接口失败。所有 Byte 字段 API 保留原始数值，页面统一格式化为 KB/MB/GB。
