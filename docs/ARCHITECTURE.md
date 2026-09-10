# InterviewForge Python 结构说明

本文只记录源码目录职责，不改变运行时接口、页面路径或数据模型。

## 正式包

- `interview_forge/core/paths.py`：项目根目录和既有数据路径常量。
- `interview_forge/server/study_server.py`：HTTP 处理器、路由编排以及仍与动态认证上下文紧密耦合的站点业务。
- `interview_forge/server/rate_limit.py`：登录/注册码的进程内滑动窗口状态；`study_server` 继续 re-export 原函数名。
- `interview_forge/db/schema.py`：学习库 DDL；`db/ai_schema.py` 保存原有 AI 表 DDL 片段。
- `interview_forge/db/connection.py`：学习库连接、一次性 schema 初始化、旧学习事件兼容回填；旧 `study_server` 连接函数仍是兼容包装。
- `interview_forge/analytics/`：学习统计与确定性上下文编译。编译器输入输出、预算和规则版本保持原样。
- `interview_forge/ai/config.py`：AI 进程环境配置、可选依赖探测和非敏感模型键；`ai/ai_coach.py` 保留旧导出及完整业务流程。
- `interview_forge/ai/ai_coach.py`：AI schema、provider、quota、task、校验、反馈与遥测等尚未跨边界搬动的真实职责。
- `interview_forge/services/review.py`：复习间隔计算；服务层保留旧函数名包装。

## 兼容入口

`tools/` 和 `scripts/` 的公开命令路径保持不变。`tools/*.py` 是兼容入口，正式实现优先位于 `interview_forge/` 或对应的 `scripts/<用途>/`。

当前服务仍直接复用 `scripts.build.build_hot100` 的题库目录常量。它同时服务于构建和运行时，贸然移动会改变启动导入时序，因此保留为后续可单独验证的技术债，不通过反向兼容导入制造第二份目录数据。

## 拆分原则

每次职责移动都保留旧 import symbol，并在移动后立即执行相关单测、编译和启动导入检查。认证/会话、天气、聊天、业务路由和缓存仍保留在服务模块中，因为它们依赖可被测试替换的模块级路径、时区、数据库和单例状态；继续拆分前必须先设计等价的依赖注入边界，不能仅为目录整齐复制状态。
