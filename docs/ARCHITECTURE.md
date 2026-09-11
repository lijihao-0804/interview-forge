# InterviewForge Python 结构说明

本文只记录源码目录职责，不改变运行时接口、页面路径或数据模型。

## 正式包

- `interview_forge/core/paths.py`：项目根目录和既有数据路径常量。
- `interview_forge/server/study_server.py`：HTTP 处理器、路由编排、启动组装与旧符号兼容 facade；业务实现通过服务层导入。
- `interview_forge/server/rate_limit.py`：登录/注册码的进程内滑动窗口状态；`study_server` 继续 re-export 原函数名。
- `interview_forge/db/schema.py`：学习库 DDL；`db/ai_schema.py` 保存 AI 表 DDL 片段与幂等升级。
- `interview_forge/db/connection.py`：学习库连接、一次性 schema 初始化、旧学习事件兼容回填；旧 `study_server` 连接函数仍是兼容包装。
- `interview_forge/analytics/`：学习统计、确定性上下文编译与进程内 analytics cache。`models.py` 保存协议/规则/目录时间模型，`queries.py` 只负责只读 SQLite 访问，`metrics.py` 负责指标/信号/证据 ID 构造，`context_models.py`、`diagnosis.py`、`selection.py` 分别承载上下文协议、诊断摘要与有界原子选择；编译器输入输出、预算和规则版本保持原样。
- `interview_forge/ai/`：`prompts.py` 保存提示与输出契约，`validation.py` 负责 Pydantic/边界/引用闭包，`context_projection.py` 负责 LLMContext v2 投影，`generation.py` 负责 provider 调用与解析校验，`tasks.py` 负责任务队列/worker/持久化生命周期；`ai_coach.py` 作为 facade/re-export 保留旧符号、单例和补丁点。
- `interview_forge/services/study.py`：题目/章节事件、仪表盘聚合、书架与复习、标记/设置、计划、薄弱清单和导出等学习业务。
- `interview_forge/services/`：认证/会话/管理员、反馈/聊天室/搜索/资料、力扣、提交、天气、学习与复习等真实业务边界。

## 兼容入口

`tools/` 和 `scripts/` 的公开命令路径保持不变。`tools/*.py` 是兼容入口，正式实现优先位于 `interview_forge/` 或对应的 `scripts/<用途>/`。

当前服务仍直接复用 `scripts.build.build_hot100` 的题库目录常量。它同时服务于构建和运行时，贸然移动会改变启动导入时序，因此保留为后续可单独验证的技术债，不通过反向兼容导入制造第二份目录数据。

## 拆分原则

每次职责移动都保留旧 import symbol，并在移动后立即执行相关单测、编译和启动导入检查。跨模块的可替换路径、时区、数据库和单例状态由服务通过惰性 assembly lookup 复用，避免复制状态。当前仍保留 `study_server.py` 的 HTTP assembly、`learning_analytics.py` 的主聚合循环和 `context_compiler.py` 的协议组装；它们需要共享大量可替换运行时符号，继续拆分前必须有明确边界与回归证据。
