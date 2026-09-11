# InterviewForge Python 结构说明

本文只记录源码目录职责，不改变运行时接口、页面路径或数据模型。

## 正式包

- `interview_forge/core/paths.py`：项目根目录和既有数据路径常量。
- `interview_forge/core/runtime.py`：唯一的 composition-root 依赖绑定；服务只依赖此运行时对象，不反向导入 HTTP 组装层。
- `interview_forge/core/async_http.py`：外部 HTTP 的可复用异步客户端，生命周期由 FastAPI app 管理。
- `interview_forge/server/study_server.py`：旧 HTTP 处理器、公开符号兼容 facade 与启动参数解析；默认启动 `interview_forge/api/app.py` 的 FastAPI/Uvicorn。`StudyHandler` 仅保留给旧单元测试/显式旧 CLI 兼容，不再由生产 FastAPI 路由调用。
- `interview_forge/api/`：FastAPI 应用、生命周期、请求可观测性、领域 Router 与受认证保护的 Web Root 静态 Router；Router 只做协议转换并调用 service/analytics/AI。
- `interview_forge/core/rate_limit.py`：登录/注册码的进程内滑动窗口状态；`server/rate_limit.py` 只 re-export 原函数名。
- `interview_forge/db/schema.py`：学习库 DDL；`db/ai_schema.py` 保存 AI 表 DDL 片段与幂等升级。
- `interview_forge/db/connection.py`：学习库连接、一次性 schema 初始化、旧学习事件兼容回填；旧 `study_server` 连接函数仍是兼容包装。
- `interview_forge/analytics/`：学习统计、确定性上下文编译与进程内 analytics cache。`models.py` 保存协议/规则/目录时间模型，`queries.py` 只负责只读 SQLite 访问，`metrics.py` 负责指标/信号/证据 ID 构造，`context_models.py`、`diagnosis.py`、`selection.py` 分别承载上下文协议、诊断摘要与有界原子选择；编译器输入输出、预算和规则版本保持原样。
- `interview_forge/ai/`：`prompts.py` 保存提示与输出契约，`validation.py` 负责 Pydantic/边界/引用闭包，`context_projection.py` 负责 LLMContext v2 投影，`generation.py` 负责 provider 调用与解析校验，`tasks.py` 负责任务队列/worker/持久化生命周期；`ai_coach.py` 作为 facade/re-export 保留旧符号、单例和补丁点。
- `interview_forge/services/study.py`：题目/章节事件、仪表盘聚合、书架与复习、标记/设置、计划、薄弱清单和导出等学习业务。
- `interview_forge/services/`：认证/会话/管理员、反馈/聊天室/搜索/资料、力扣、提交、天气、学习与复习等真实业务边界。
- `interview_forge/runtime/task_manager.py`：统一 submit/query/cancel 词汇的后端注册表；AI 与 LeetCode 继续各自持有原有任务状态，注册表不保存第二份状态。
- `interview_forge/runtime/streaming.py`：可取消的 SSE JSON 帧原语；当前只作为内部基础设施，不注册 Chat 产品接口。

## 兼容入口

`tools/` 和 `scripts/` 的公开命令路径保持不变。`tools/*.py` 是兼容入口，正式实现优先位于 `interview_forge/` 或对应的 `scripts/<用途>/`。

当前服务仍直接复用 `scripts.build.build_hot100` 的题库目录常量。它同时服务于构建和运行时，贸然移动会改变启动导入时序，因此保留为后续可单独验证的技术债，不通过反向兼容导入制造第二份目录数据。

## 拆分原则

每次职责移动都保留旧 import symbol，并在移动后立即执行相关单测、编译和启动导入检查。跨模块的可替换路径、时区、数据库和单例状态由 composition root 绑定到 `core.runtime`，服务、analytics 和 AI 不导入 `study_server`。当前仍保留 `study_server.py` 的兼容 HTTP assembly、`learning_analytics.py` 的主聚合循环和 `context_compiler.py` 的协议组装；它们需要共享大量规则与兼容导出，继续拆分前必须有明确边界与回归证据。

## 后端 V2 运行边界

- 服务入口：`python tools/study_server.py` 仍是公开命令，初始化参数和旧 `StudyHandler` 符号不变；安装 `requirements-server.txt` 后默认由 Uvicorn 启动 FastAPI，所有当前 API 与 Web Root 路径由领域 Router/静态 Router 处理。
- FastAPI 已按 auth、study、leetcode、analytics/AI、weather、community、admin 和 static 分组注册当前真实 URL；生产 app 不包含 catch-all legacy adapter，也不调用 `StudyHandler`。`StudyHandler` 只为旧测试、外部兼容代码和无 FastAPI 依赖时的旧 CLI fallback 保留。
- 外部网络等待可使用 `AsyncHttpClient` 与服务层 async adapter；SQLite、analytics CPU 和已有后台任务仍保持同步/进程内实现。
- `TaskManager` 只做后端注册与统一调用面，AI/LeetCode 的持久化任务状态仍只有原有的一份。
