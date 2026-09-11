# 阶段 3 结构拆分补充交接

本轮只做行为保持的职责拆分，没有改变 AI provider、prompt、输出 schema、额度、
任务 API、analytics 规则或上下文协议。

## AI

- `ai/prompts.py`：版本、预算上限、system prompt 和输出契约；
- `ai/validation.py`：Pydantic schema、边界校验、support ref 闭包和规则 fallback；
- `ai/context_projection.py`：FullContext 到 LLMContext v2 的投影与可观测摘要；
- `ai/generation.py`：模型构造桥接、DeepSeek streaming、解析、一次 repair 与计时日志；
- `ai/tasks.py`：队列、worker、quota 消费、任务持久化、历史/公开投影和生命周期；
- `ai/ai_coach.py`：兼容 facade。它继续导出旧常量、函数、异常和单例对象，测试对
  `ai_coach` 的 patch 点仍有效。

## Analytics

- `analytics/models.py`：analytics-v1 协议常量、规则配置、目录/时间归一化和只读表 schema；
- `analytics/queries.py`：只读 SQLite 打开、schema 探测与兼容查询；
- `analytics/metrics.py`：指标、signal/evidence ID、来源分布和 snapshot hash；
- `analytics/context_models.py`：context-v1 协议与预算常量；
- `analytics/diagnosis.py`：诊断信号多样性、逾期/轮次分布、trace map、代表案例和异常摘要；
- `analytics/selection.py`：保持原 atomic group/预算回退语义的 `_SelectionBuilder`；
- `learning_analytics.py`、`context_compiler.py`：保留主聚合/协议组装入口与旧符号 facade。

## 验证口径

拆分使用惰性 facade lookup 保留既有 monkey-patch、模块级单例和导入时序。相关 analytics、
context、AI、server 测试以及新旧测试发现方式、编译、构建/检查、旧 CLI 和临时本地服务
smoke 应与基线比较；唯一允许保留的失败仍是历史后台页面缺少“重置今日分析次数”标记。

未部署、未改生产数据、未清理日志、未创建子代理。
