from __future__ import annotations


# ============================================================================
# 文件角色：书架目录登记表 —— 整个学习站唯一的“人工维护层”。
# 三层架构中本文件的位置：
#   ① 本文件（library_catalog.py）  人工维护：决定哪些课程能上架、叫什么、
#                                   归哪类、源文件在哪、课程简介怎么写。
#   ② 自动生成层（build_library.py）读取本登记表，按 source 读 Markdown，
#                                   经 split_chapters() 拆章并渲染成 library/ 下的
#                                   模块页/章节页/manifest.json/search-index.json；
#                                   hot100 模块则由 build_hot100.py 单独生成。
#   ③ 校验与运行时（check_hot100.py / study_server.py）
#                                   check_hot100.py 断言生成结果与本表一致
#                                   （模块数 = 本表条数 + 1、mermaid 图数量核对、
#                                   路由与清单完整性）；study_server.py 用
#                                   manifest.json 校验 module/content id，把
#                                   浏览/完成事件写入 content_events，驱动进度与复习。
# 一句话：生成器和校验器都是机器，“要不要上线、长什么样、简介怎么写”只有这张表说了算。
# 研究阅读建议：先读本表 → 再看 build_library.build() 消费本表的位置 → 最后对照
# check_hot100.py 与 study_server.py 看校验与学习记录链路，三处共同定义“登记”的全部含义。
# ============================================================================


# 只登记适合连续阅读的权威 Markdown 源。临时稿、demo README、二进制副本
# 和包含凭据的文本文件不会被自动扫描或发布。
# `about` 是面向学习者的模块简介（人工维护），生成器优先使用它；
# 未登记时才回退到从源笔记开头自动提取。

# ----------------------------------------------------------------------------
# 每条记录（一个 dict）登记一个课程模块，字段约定如下（均为必填，除非注明可选）：
#   id        稳定英文标识，全表唯一。它决定模块目录名 library/<id>/、
#             manifest 里的 module_id、以及每章学习记录键 content_id=<id>:NN；
#             study_server 的 valid_content() 与 content_events 都按它记账，
#             发布后不应改动（会切断既有学习记录与旧路由的对应关系）。
#   title     书架卡片与页头的课程标题（人工整理，优先于源文件标题；
#             源标题只作兜底，见 build_library.build() 的 `title or book_title`）。
#   category  书架分类（首页筛选按钮按它分组）；新模块建议沿用既有分类名。
#   source    源 Markdown 相对于“笔记根目录”(NOTES_ROOT) 的相对路径。
#             生成器按它读文件，再经 split_chapters() 以 `## ` 二级标题拆章，
#             同时用于站内本地链接重写与 mermaid 图数量核对；
#             路径无效会直接导致构建失败。
#   about     人工维护的课程简介。生成器取 `definition.get("about") or
#             module_about(...)`：登记了就用人工版，未登记才自动从源笔记开头抽取。
#             新模块建议第一时间写好 about，否则页面简介是不可控的自动摘要
#             （曾有“视频简介 / 整理自原笔记”等元信息被自动摘要泄漏，
#             见 报告/学习站审查报告.md 的处置记录）。
#   unit      （可选）章节计量单位，默认 "章"；仅 hot100 登记为 "题"。
# ----------------------------------------------------------------------------
# 新增模块的标准流程与校验点：
#   1. 在 LIBRARY_MODULES 末尾追加一条记录：先定 id/title/category，再核对 source
#      真实指向一份可连续阅读的 Markdown（临时稿、demo README、含凭据文件一律不登记）。
#   2. 运行 python build_library.py 重建 library/（生成模块页与 manifest）。
#   3. 运行 python check_hot100.py 校验：它断言
#          len(library_modules) == len(LIBRARY_MODULES) + 1   （+1 是 hot100 模块），
#      并对每条登记的 source 统计 ```mermaid 数量、与生成章节页逐条核对；
#      新增模块后该等式与 mermaid 数量必须仍成立，否则校验失败。
#   4. 运行时链路：study_server.py 的 record_content_view() / complete_content()
#      先经 valid_content() 对照 manifest（即本表的产物）校验 module_id/content_id，
#      才会把 view/complete 事件与 round_no 写进 content_events；
#      因此本表就是“哪些内容能记学习进度”的唯一开关。
# ----------------------------------------------------------------------------
LIBRARY_MODULES = [
    {"id": "java-core", "title": "Java 核心：语言根基", "category": "Java 语言", "source": "Java校招/01-Java核心.md",
     "about": "从 JDK/JVM 与字节码讲起，覆盖类型系统、面向对象、枚举、String 与集合源码（ArrayList/HashMap 精读）、泛型擦除、反射与动态代理、异常、IO/NIO、序列化，再到 Java 8/17/21 新特性，最后以 52 道自测题收尾。建议按章节顺序通读，每章先答“面试追问”再对答案；本课不含并发原语、JMM、类加载与 GC，这些由后续课程展开。"},
    {"id": "java-concurrency", "title": "Java 并发编程：线程、锁与高并发", "category": "Java 语言", "source": "Java校招/02-Java并发编程.md",
     "about": "从线程状态、JMM 与 happens-before 讲起，深入 volatile、synchronized 锁升级、CAS、AQS、ReentrantLock、并发集合、线程池七参数、ThreadLocal 内存泄漏，再到并发工具、CompletableFuture、死锁排查与 JDK 21 虚拟线程，最后以 53 道自测题收尾；建议先读完《Java 核心》再学本课，每个知识点用“五连问”（解决什么问题、底层实现、怎么用、代价、坑）过一遍。"},
    {"id": "jvm", "title": "JVM：内存区域、垃圾回收与类加载", "category": "Java 语言", "source": "Java校招/03-JVM.md",
     "about": "从运行时数据区与对象生命周期讲起，深入 GC 算法与收集器（Parallel/CMS/G1/ZGC）、类加载与双亲委派，再到 JVM 工具、OOM 排查与调优流程，最后以分主题自测题收尾；建议先读完《Java 核心》与《Java 并发编程》。"},
    {"id": "operating-system", "title": "操作系统：进程线程、内存与 IO 模型", "category": "计算机基础", "source": "Java校招/04-操作系统.md",
     "about": "覆盖操作系统基础、进程线程与调度、IPC、同步与死锁、虚拟内存与页面置换、五种 IO 模型与 select/poll/epoll、零拷贝，以及 Linux 常用排查命令，最后以分主题自测题收尾。"},
    {"id": "computer-network", "title": "计算机网络：TCP/IP、HTTP 与 WebSocket", "category": "计算机基础", "source": "Java校招/05-计算机网络.md",
     "about": "从 OSI/TCP/IP 分层与 IP 基础讲起，深入 TCP 三次握手四次挥手、可靠传输与拥塞控制、HTTP/HTTPS 版本演进、DNS 与 WebSocket，最后以分主题自测题收尾。"},
    {"id": "mysql", "title": "MySQL：索引、事务、MVCC 与优化", "category": "数据存储", "source": "Java校招/06-MySQL.md",
     "about": "以 InnoDB 为主线，覆盖架构与存储引擎、B+ 树索引与覆盖索引、事务 ACID、隔离级别、MVCC 与 ReadView、行锁与间隙锁、三大日志与两阶段提交、SQL 优化与分库分表，最后以分主题自测题收尾。"},
    {"id": "redis", "title": "Redis：数据结构、缓存与高可用", "category": "数据存储", "source": "Java校招/07-Redis.md",
     "about": "覆盖五种数据结构与底层编码、单线程模型、事务与 Lua、RDB/AOF 持久化、缓存穿透/击穿/雪崩与一致性方案、分布式锁与 Redisson、主从/哨兵/Cluster 高可用，最后以分主题自测题收尾。"},
    {"id": "java-web", "title": "Java Web 基础：Servlet、Tomcat、Maven、Git 与前后端分离", "category": "Web 与框架", "source": "Java校招/08-JavaWeb基础.md",
     "about": "从一次请求的完整链路讲起，覆盖 Cookie/Session、Servlet 生命周期与 Filter、Tomcat 架构与线程模型，再到 Maven 坐标/依赖/生命周期、Git 三区与回滚、RESTful 设计与 JWT/CORS，最后以 34 道自测题收尾；建议先读完《Java 核心》再进入本课，是 Spring 家族的直接前置。"},
    {"id": "spring-family", "title": "Spring 家族：IoC/AOP、Boot 自动装配、MVC 与 MyBatis", "category": "Web 与框架", "source": "Java校招/09-Spring家族.md",
     "about": "从 IoC/DI 与 Bean 生命周期讲起，深入三级缓存解决循环依赖、AOP 动态代理、Spring Boot 自动装配原理，再到 Spring MVC 请求流程、统一异常处理、MyBatis 缓存与 MyBatis-Plus 增强，最后以 36 道自测题收尾；建议先读完《Java Web 基础》。"},
    {"id": "design-patterns", "title": "设计模式：23 种模式与框架源码体现", "category": "Web 与框架", "source": "Java校招/10-设计模式.md",
     "about": "先讲七大设计原则，再按创建型（单例/工厂/建造者/原型）、结构型（代理/适配器/装饰器/组合/外观）、行为型（模板/策略/观察者/责任链/迭代器）逐类展开，最后用对照表梳理 Spring/MyBatis/Netty 等框架源码中的体现，以 28 道自测题收尾。"},
    {"id": "message-queue", "title": "消息队列：Kafka/RocketMQ/RabbitMQ 选型、可靠性与高可用", "category": "分布式与工程", "source": "Java校招/11-消息队列.md",
     "about": "从为什么用 MQ 与核心模型讲起，对比 Kafka/RocketMQ/RabbitMQ 选型，深入消息可靠性三段保证、顺序消息、重复消费与幂等、积压排查、高可用副本机制，最后精读 Kafka 存储与消费者组原理，以 30 道自测题收尾。"},
    {"id": "distributed-basics", "title": "分布式基础：CAP、分布式事务、分布式 ID 与幂等", "category": "分布式与工程", "source": "Java校招/12-分布式基础.md",
     "about": "从分布式挑战讲起，覆盖 CAP/BASE、2PC/3PC、TCC/SAGA/Seata 四种模式、分布式 ID（雪花/号段）、接口幂等、一致性哈希与分布式锁对比，最后以 30 道自测题收尾；建议先读完《消息队列》。"},
    {"id": "microservices-highconcurrency", "title": "微服务与高并发：Spring Cloud、限流熔断与秒杀设计", "category": "分布式与工程", "source": "Java校招/13-微服务与高并发.md",
     "about": "从微服务拆分原则讲起，覆盖 Nacos 注册配置中心、Gateway 网关、OpenFeign 与负载均衡，再到限流四算法、熔断降级与 Sentinel，最后以秒杀系统分层设计收尾并落地缓存一致性，以 32 道自测题收尾；建议先读完《分布式基础》。"},
    {"id": "devops", "title": "部署与运维：Linux、Docker、Kubernetes 与 CI/CD", "category": "分布式与工程", "source": "Java校招/14-部署与运维.md",
     "about": "从 Linux 常用命令与性能排查讲起，覆盖 Docker 镜像/容器/Dockerfile、Kubernetes 核心对象与滚动更新回滚、CI/CD 流水线与发布策略、日志与监控体系，最后以 28 道自测题收尾，完成从代码到线上的闭环。"},
    {"id": "interview-sprint", "title": "校招面试冲刺：八股自测、项目总结与系统设计", "category": "校招冲刺", "source": "Java校招/15-校招面试冲刺.md",
     "about": "全部课程收尾课：40 道全科八股自测总表定位薄弱点，STAR 法准备项目与简历，系统设计答题框架与秒杀/短链/IM 三母题，模拟面试高频问答与一周冲刺计划，最后给出完整学习闭环与参考资料。"},
    {"id": "python", "title": "Python 实用入门与 AI 开发", "category": "编程基础", "source": "Python/Python实用入门与AI开发：语法、API、并发及工程实践.md",
     "about": "从语法、容器与类型标注讲到调用大模型 API、FastAPI 服务和并发，最后落到完整 AI 项目结构；想用 Python 做 AI 开发可一路顺读。"},
    {"id": "machine-learning", "title": "机器学习快速入门", "category": "模型与训练", "source": "机器学习/机器学习快速入门：从基本概念到完整实践.md",
     "about": "从问题定义、样本与标签讲起，走通回归、分类、无监督、模型评估与调参，并以鸢尾花案例收尾，附最小数学基础与工程陷阱附录。"},
    {"id": "deep-learning", "title": "深度学习与 Transformer", "category": "模型与训练", "source": "机器学习/深度学习快速入门：从神经网络到 Transformer.md",
     "about": "以 PyTorch 为主线，从神经网络如何学习讲到 CNN、Transformer、迁移学习、生成模型与部署，附学习路线与一页速记。"},
    {"id": "lora", "title": "LoRA 微调实践", "category": "模型与训练", "source": "单行本/lora微调.md",
     "about": "六步走通大模型微调链路：需求与技术选型、整体流程、模型微调、部署暴露接口，再到 Web 后端调用。"},
    {"id": "rag", "title": "RAG：从检索原理到生产实践", "category": "大模型应用", "source": "单行本/RAG技术完整学习笔记：从检索原理到生产实践.md",
     "about": "从文档接入、分块与 Embedding 讲到检索、重排与答案生成，再进入 Agentic RAG、GraphRAG 以及评测、故障诊断与生产工程。"},
    {"id": "langchain", "title": "LangChain 入门与工程实践", "category": "大模型应用", "source": "langchain/LangChain入门学习笔记.md",
     "about": "从第一次调用模型到消息与 Runnable、工具调用、Agent、RAG 与 LangGraph，覆盖记忆、评估、生产部署和常见误区。"},
    {"id": "agent-development", "title": "Agent 开发：从原理到落地", "category": "Agent 工程", "source": "单行本/Agent 开发学习笔记：从原理、技术栈到工程落地.md",
     "about": "从模型调用到 Agent Loop、工具与 MCP，逐步覆盖 Planning、多 Agent、人工介入、安全与可观测性，最后给完整开发流程与示例。"},
    {"id": "mcp", "title": "Function Calling 与 MCP", "category": "Agent 工程", "source": "0816MCP/Function Calling 与 MCP 协议：设计原理与工程实践.md",
     "about": "先给结论再讲机制：Function Calling 的局限、MCP 的 Host/Client/Server 与两层协议，并用 Python 实现最小 Server、配置调试与生产安全。"},
    {"id": "agent-cli", "title": "Hermes、OpenClaw、Codex 与 Claude Code", "category": "Agent 工程", "source": "20260419_Hermes_Agent/Hermes、OpenClaw、Codex 与 Claude Code：Agent 与 CLI 学习笔记.md",
     "about": "横向比较四类主流 Agent 工具：Agent Loop、指令文件、Skills、Subagents、记忆与安全边界，再到选型与四个典型工作流。"},
    {"id": "deepseek-harness", "title": "DeepSeek Harness 插件化架构", "category": "Agent 工程", "source": "20260419_Hermes_Agent/DeepSeek Harness 学习笔记：一切皆插件的 Agent Harness.md",
     "about": "以事实基线逐层验证「一切皆插件」：插件内核、Profile/Bundle/Patch、内置插件地图、省 Token 机制与自进化，并客观列出风险与不足。"},
    {"id": "ai-infra", "title": "AI Infra：训练、推理与 MLOps", "category": "系统与基础设施", "source": "单行本/AI Infra完整学习笔记：从GPU、分布式训练到大模型推理与MLOps.md",
     "about": "从 Linux、GPU 与 CUDA 基础到分布式训练与大模型并行，再到推理服务、K8s 调度与可观测性，含完整项目、面试问题与学习路线。"},
    {"id": "compiler-interview", "title": "AI 编译器岗位面试速记", "category": "系统与基础设施", "source": "单行本/仓颉 AI 编译器岗位面试速记：编译器基础、AI Coding Agent 与工程实践.md",
     "about": "面向仓颉 AI 编译器岗位面试：一条编译流水线、核心概念、AI 编译器与 Codex/Trae 的关系，含高频问答与一周准备路线。"},
    {"id": "ai-basics", "title": "AI 通识与大模型基础", "category": "基础认知", "source": "langchain/第1章. AI通识与基础/第1章. AI通识与基础 副本.md",
     "about": "从模型、数据与算力三大要素出发，讲解大模型训练与 API 调用规范，覆盖 DeepSeek、百炼等平台、本地部署与开发环境准备。"},
]


# ----------------------------------------------------------------------------
# 为什么 HOT100_MODULE 不放进 LIBRARY_MODULES，而是单独定义？
#   · 章节来源不同：LIBRARY_MODULES 每条都对应一份可拆章的 Markdown 源文件，
#     而 hot100 没有单一源文档——build_hot100.PROBLEMS 的题目目录本身就是章节
#     清单，每道题即一章，由 build_hot100_module() 直接生成章节列表。
#   · 渲染方式不同：普通模块对 Markdown 走 split_chapters + 渲染，章节页是新生成
#     的 chapter-NN.html；hot100 的章节页直接复用 03-题解/ 下已有的题解 HTML
#     （章节 url 指向 ../03-题解/<题目目录>/…），不经过拆章与渲染流水线。
#   · source 必须是 None：build_library.build() 对 LIBRARY_MODULES 逐条执行
#     NOTES_ROOT / definition["source"] 去读文件，hot100 走独立分支
#     build_hot100_module()；一旦给它登记了 source，构建器就会误当普通模块读取。
#   · 进度与复习共用同一套记账：题目浏览与“完成一轮”由 study_server.py 以
#     module_id="hot100" 写入 content_events（view/complete + round_no），
#     因此书架模块页与 Hot 100 面板的进度始终一致——这正是保留独立 dict、
#     并固定 id="hot100" 的原因。
#   · unit="题"：卡片上显示“100 题”而不是“100 章”。
# ----------------------------------------------------------------------------

# Hot 100 不按 Markdown 章节拆分，而是由 build_hot100 的题目目录生成：
# 每道题即一个章节，章节页直接复用 03-题解 下的题解 HTML，
# 打开题目和完成一轮的记录会同步到书架的 content_events。
HOT100_MODULE = {
    "id": "hot100",
    "title": "Hot 100 算法刷题精讲",
    "category": "算法刷题",
    "unit": "题",
    "source": None,
}

# ----------------------------------------------------------------------------
# 以后往登记表里加字段时的注意点：
#   · 消费方全部按字面键名读取，about/source/category/id/title/unit 一字不能改名；
#     新增可选字段（如自定 unit）也必须同步更新 build_library.py 的消费处——
#     模块页模板与 manifest 用的是 **definition 展开，新字段会原样进入
#     manifest.json 并流向 study_server 的 valid_content() 等下游，不更新消费处
#     就会出现“登记了却没生效”或“生成正常但校验失败”两类问题。
#   · 改动 id 会切断 manifest → content_events 的历史关联与旧路由；删除条目会
#     让 check_hot100.py 的模块数断言（条数 + 1）翻车。两类改动都要连同重建与
#     全量校验一起做。
# ----------------------------------------------------------------------------
