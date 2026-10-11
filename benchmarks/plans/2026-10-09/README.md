# AI 后端实习简历性能基准：方案与预检验收

日期：2026-10-09。状态：**仅方案、只读审查和环境预检完成；正式压测未获确认，未开始。**

本轮未改变业务实现、生产配置或依赖，未部署、未登录真实用户、未读取用户数据库，未发起压力请求。新文件目前只保留本地，未提交推送。

## 1. 本轮验收结果

| 项目 | 结果 | 依据/限制 |
| --- | --- | --- |
| 当前 main | `145a5c1dfd188f0f0c9f6c7e71e587d7b5c8ba74` | GitHub只读API、local HEAD一致 |
| 生产代码 | `be63a02161aebcc5cd91fc8f2663ee75ab71752a` | VPS git rev-parse；不是最新main |
| 生产运行模式 | active，4 worker，IF_SHARED_RUNTIME=1 | 进程及白名单环境只读核实；四worker均加载uvloop/httptools |
| 服务环境 | Linux 6.8.0-134、Python3.12.3、4逻辑CPU、约16GiB | 实际采样见preflight.json；CPU型号/存储/cgroup隔离配额仍需测试机验收 |
| 依赖 | FastAPI0.115.6、Uvicorn0.34.0、uvloop0.23.0、httptools0.8.0 | 实际包元数据，psutil未安装；无需为本次预检安装 |
| 资源快照 | 可用内存约13.7GiB，服务memory.current约435MiB，低load | 瞬时值，不是压测资源占用或CPU余量证明 |
| 旧版schema兼容 | 静态审查未发现基础schema文件差异 | **不是迁移可安全执行的证明**；必须在合成库副本做启动/迁移/接口合同检查 |
| 正式开测门槛 | 未通过 | 独立发压端、隔离服务、合成fixture、原始样本导出和锁等待测量尚未就绪 |

生产默认SQLite配置仅从源码推断：busy_timeout=10000ms、cache_size=-32000KiB、mmap上限256MiB、synchronous=FULL，认证库始终FULL。本轮未打开生产用户数据库，**不声称逐连接PRAGMA已实测**。

## 2. 历史数据审查

已阅读 `benchmarks/results/2026-10-03/` 和四个HTTP/连接诊断脚本；另检查deepseek_reasoning_benchmark.py定位。后者会真实调用模型，**不执行、不纳入本次HTTP基准**。

历史数据可用于寻找实验问题，不足以直接支持正式简历容量结论：

- before-backend/after-final-backend：同机、同授权用户、各约8秒，bootstrap15VU为107.1→356.5RPS、P95为181→161ms；无三次重复、统一fixture哈希或缓存状态证明，且使用真实用户。新版health15VU反而944→887.6RPS，bootstrap5VU P95变差。不能择优引用“整体3.33倍”。
- client-pool-vps：单池190.9RPS/P95 3389ms，六池703.1RPS/P95 620ms；池分配墙钟5.047→2.862s，发压CPU接近单核满载。它支持**发压工具瓶颈诊断**，不支持纯服务器容量上限。诊断脚本多池总连接配置预算也不同，虽然总VU保持150，必须避免过度归因。
- corrected-ramp-vps：50/100/150VU为1342.6/1019.4/824.7RPS；发压端仍接近单核。不是服务最大吞吐。
- connection-probe及Windows TLS：公网TCP建连秒级长尾、握手重传；第二网络控制变量未完成。不得将其归因为nginx64连接硬限制。
- curl协议不同、SSH隧道Too many open files、初轮样本部分重叠、未预热及采样短，全部保留为限制；不能只挑最好一轮。
- TLS文件有逐请求阶段耗时，但HTTP性能文件主要是汇总，无请求级时序。无法事后计算稳态窗口或审核排队效应。

## 3. 现有工具审查：必须先补的合同

**本轮只记录缺口，不修改脚本或业务。**

1. hammer/mixed将2xx及3xx/304都算成功，登录重定向可被误报成功；正式三个API必须200+JSON schema正确，401/403/3xx/错误正文都算失败。baseline304分支目前硬传errors=0，需更正后才能用于验收。
2. run_stage是闭环且计入在途收尾；decompose按目标duration算RPS却等待在途请求结束。正式分离稳定测量窗口、请求发出/完成时间及drain，不混用分母。
3. 无固定到达率、无原始请求CSV/JSONL、无预热剔除、无三重复编排；mixed所有VU从同一计数起点走相同序列，需固定seed的独立用户/请求分配。
4. pool sharding改善发压端但不能消除单进程上限；已有CPU比例仅部分场景采集。必须逐发压进程/核记录CPU和调度延迟。
5. 缺DB锁等待、缓存命中和worker资源对应时序；不能把SQL耗时叫锁等待，也不能把没记录叫零等待。
6. 默认public target与高并发诊断不适合作为安全正式入口；未来runner要显式允许测试域/地址、禁止默认生产目标、先做合成fixture标记和目标SHA验证。
7. login失败截取响应正文/命令行password存在泄露风险；未来仅私有环境或交互读取凭据、输出固定错误类别，结束注销；原始样本不存Cookie或Authorization。

## 4. A/B/C 主对照

| 组 | SHA | worker | IF_SHARED_RUNTIME | 主对照解释 |
| --- | --- | ---: | --- | --- |
| A | `2b01df993ed382618bb2169babaf387160b5ee97` | 1 | 旧版无该机制 | 最近优化前基线，不是整个项目初版 |
| B | `145a5c1dfd188f0f0c9f6c7e71e587d7b5c8ba74` | 1 | 1 | 启用新版协调/缓存，仅保持单worker |
| C | 同B | 4 | 1 | B→C主要比较worker数量变化 |

B必须显式IF_SHARED_RUNTIME=1，否则B缓存关闭、C缓存开启，不能将B→C收益仅归因worker。B/C其他环境完全一致；A没有的新机制是A→B的整体处理变量。

三组统一Linux、CPU配额4核、内存与存储、Python3.12.3、冻结依赖清单、Uvicorn0.34.0，明确 --loop uvloop --http httptools，不把事件循环差异混进worker归因。先兼容检查；若旧版不能在此依赖环境启动，不能强行降级生产，而报告A不可比或拆成独立“历史完整栈”次级实验，明确依赖混杂。

**旧版已有WAL及sqlite.connect(timeout=10)**。主对照不能证明WAL从无到有或新增等待策略的独立效果。A→B是缓存/调优/协调整体效果；B→C是启用协调时多worker的增量。若要测WAL本身，另提隔离因子实验并获确认，不能伪装成这三组的结论。

## 5. 隔离、数据及兼容性

推荐独立Linux测试目标与独立Linux发压端，同地域/低RTT私有链路。不得拿现生产VPS四核直接高压，因为还运行其他服务；即使端口不同仍争CPU/磁盘。若只能使用当前VPS，必须先获具体资源窗口批准，实施本项目限额，且不得声明“独享4核”。本轮不创建云机、不安装工具、不改变防火墙。

仅新建合成数据：固定seed，20个普通用户、各100个题目进度条目及预登记学习事件规模、固定设置/复习日期；另单用户热点副实验。先检查表结构合法，不把“100题”当“100条真实提交”。用户名如bench_u001；假密码/凭据从私有运行环境取，不入库公开仓库。无真实AI key、Cookie、聊天、个人笔记、力扣数据；禁止外部模型/力扣调用，使用正常未配置AI状态，并验证bootstrap仍正常缓存（未配置与异常unavailable分支不能混淆）。

每次run从**同一合成学习库/认证库/AI配置库快照**恢复到该组独立目录，记录fixture manifest、表行数和SHA256。不得从生产data备份复制真实用户库。应用有固定PROJECT_ROOT/data路径；必须完整独立checkout/运行目录或容器卷隔离，不能只改一个DB环境变量就以为所有库已隔离。runtime锁目录、metrics、日志、索引及user目录均独立；不加载生产EnvironmentFile。

静态schema文件虽未变，connect初始化仍会执行migration/backfill。A先在副本启动并记录前后sqlite_master/schema与row-count、migration日志、integrity_check/foreign_key_check，再验证三接口schema和确定性内容。A若更改或无法读取统一fixture，终止A正式实验；采用版本各自建库+相同逻辑数据/规范化API输出校验的安全替代，报告物理快照不再完全相同，或仅报告B/C。

统一课程内容与搜索索引字节/hash、用户role、daily module参数、业务日期和保持率。不要跨北京时间午夜运行对照；跨日则作废重跑，不改主机时钟。登录在预热前做一次/每用户，三组会话数量、年龄、TTL统一；登录不计API测量。认证last_seen/renewal可能写auth.db，日志/metrics也写库，**只读GET不代表零写入**，统一保留这些开销并记录。库大小/页数基于副本，未触碰生产数据。

## 6. 接口与响应口径

- bootstrap：200，dashboard/daily/settings/capabilities结构有效，合成数据摘要相同；规范化去掉合法动态时间/运行元数据，但保留业务值。不得通过裁剪响应或禁用功能换成绩。
- daily：200，固定module或全模块口径，due/计划相关内容与fixture一致；原始样本只存响应大小/schema-pass/摘要，不存正文。
- search：200，items/count/has_more合法。固定查询集：命中、零命中、短词、较长词，及固定seed权重；索引hash相同。只测“线程池”不能代表搜索能力。
- mixed主场景：bootstrap40%、daily40%、search20%；用户均匀分配，固定seed，另单用户热点明确标注。所有版本相同响应口径、gzip/HTTP1.1/keepalive/超时（建议5s）和连接预算；完整API200与HTML304不能混合成一个成绩。
- health只作发压端校准参照，不计业务成绩；不把本轮当作LLM推理、SSE/TTFT或AI token吞吐基准。

## 7. 缓存冷热与同负载实验

主场景是**自然TTL下的热稳态**：完整重启测试组清进程缓存；恢复fixture；低速预热至少60秒，再测120秒，drain单列30秒、冷却30秒。四worker均收到预热请求需要证据（仅测试包装加worker标识，三组一律同样包装）；无法证明时标记预热覆盖不充分，不能偷偷延长某一组直到最好成绩。

冷场景单独：每次干净重启后的首批请求/首30秒，三次重复，报告首次请求及warming曲线，不跟热稳态样本合并。这只是应用进程冷缓存，**不是OS磁盘冷缓存**；不执行全主机drop_caches。bootstrap TTL3秒、session TTL30秒保留默认，自然过期必须出现在120秒窗口。不要在每个请求前人为失效从而代表真实“冷缓存”。

固定到达率比较是主指标：预探索5/10/20/40/80RPS，每档30秒，低速预热；探索不作为最终数字。根据最弱组无错误且符合SLO的范围选择至少两个共同负载点，确认后固定（例如低负载与约最弱组容量60%的点）。同arrival rate、同请求组成下比较P50/P95/P99/失败率。生成器记录计划发出时间、实际发出时间及schedule delay，避免闭环coordinated omission。虚拟用户阶梯另报5/10/25/50/100VU闭环探索，不将其等同恒定到达率。

容量实验：独立测最大可持续成功RPS，预登记error<=1%、各接口P95<=500ms且生成器未饱和，若500ms不符产品SLO需在开测前修改，而非看完结果再调。拟测120秒窗口、至少3次通过；到达率不足、样本不足、网络异常则不公布最大值，改称“达到X负载且满足SLO”。停止条件为测试目标CPU>90%持续10秒、错误>1%持续10秒、P95>2s、生成器任一核>70%或schedule-delay P95>10ms（安全阈值可在隔离校准后确认），所有中止也保存。

至少三次独立重复，主组顺序Latin-square：ABC、BCA、CAB；每次恢复fixture/重启/预热/同参数，seed提前登记。缓存冷实验也三次。按接口、用户模型、缓存状态分别报告三轮全部值、median/min/max、配对变化；有条件扩至5轮估计置信区间，不用3轮伪造高精度置信结论。不能平均各轮P95代替合并原始样本分位数；重复之间的中位P95和全样本P95分开命名。

最小核心矩阵为3组×3重复×4场景×2共同到达率=72个稳态窗口；仅120秒采样约2.4小时，另有预热/重启/冷却、探索和正确性验收。预计正式执行半天至一天，不是十分钟能完成。

## 8. 发压端校准与资源指标

开测前独立发压端至少能维持目标最高到达率2倍对校准目标的正确请求，验证结果不是客户端瓶颈；监控每核CPU/事件循环lag、连接等待、FD、errors与NIC带宽。同一负载将发压进程数量翻倍而总请求率不变，RPS与P95变化应在预登记10%内，否则增加生成器资源并重新校准。分池不等于独立发压端，先前隧道不适用容量测量。

主应用比较直达隔离应用相同协议路径；另有完整nginx/TLS路径副实验，三组相同网络和gzip，不能A直连B代理。记录DNS/TCP/TLS/TTFB/full-body而非只总时间；公网测试单列，未稳定的Windows外网不能作主发压端。

服务端1秒采样：每worker与总CPU、RSS/PSS、cgroup memory.current、thread/FD、上下文切换、I/O、磁盘延迟/利用率、CPU steal、宿主load；PSS/cgroup优于简单相加RSS，后者会重复共享页。原始资源时序对齐run_id/request_id/UTC timestamp。只采集测试项目进程；不公开其他服务信息。

## 9. 数据库锁等待与一致性：性能之外的必验门

只读主场景不足以证明写锁改善。另设**仅合成库**的受控writer：保持确定数量与时长的事务（如BEGIN IMMEDIATE持锁100ms，1次/秒），读流量保持同负载；记录提交、BUSY/LOCKED、读成功与陈旧读。该场景不可与主只读成绩合并。

标准sqlite3目前没有直接导出的busy-handler累计等待。必须明确区分：连接初始化/SQL总耗时是等待上界代理，不是精确锁等待；BUSY错误数不能替代等待时长。本轮锁等待数据为**未测/不可用，不是0**。

正式前选定可审计方法：隔离运行包装Connection操作、记录statement_id、起止、错误码，不记SQL正文；配合可选SQLite底层busy处理采样或受控持锁时间轴，若无法获得精确累计wait，字段保留null、报告operation-latency proxy并限制结论。诊断包装三组同样启用，完整请求主成绩另以未包装版本验证开销；不得修改生产实现或关闭锁来提高数字。

一致性用独立正确性suite，先执行才做容量：跨worker logout/disable生效、学习写后bootstrap/daily摘要更新、TTL内不返回旧数据、同用户sync任务复用/不同模式409、worker死亡回收、AI任务恢复不误取消活跃worker、模型槽全局并发限制。全部使用mock外部提供者与合成数据；mock不进入HTTP性能主场景。至少100轮可重复状态操作，逐轮记录assert与可见性延迟；以请求落到不同PID为证据，不能只在一个worker上自证一致性。调度/在途已开始请求与写后新请求分别定义，不要求已经开始的请求倒退撤销。对长期保持旧快照的次数容忍为0。

## 10. 原始产物与审计合同

未来每个run目录：manifest.json、requests.jsonl、requests.csv、resources.csv、db_operations.jsonl、correctness.jsonl、summary.json、stderr.txt（脱敏）与report.md。记录SHA、dirty=false、依赖freeze、OS/CPU/配额/磁盘、fixture/index hash、seed、组/重复/场景/缓存、参数和停止原因。原始文件生成SHA256清单，汇总脚本版本一并保存。

请求行字段：run_id/repeat/group/endpoint/query_case/synthetic_user_alias/request_id、scheduled_at/started_at/finished_at、phase、status、error_category、schema_pass、latency_ms、schedule_delay_ms、bytes、worker_alias。UTC ISO用于关联，单调时钟计算耗时。Cookie、密码、真实用户名/IP、正文和私有运维路径不入公开产物；token及精确用户数据不哈希后冒充匿名。

失败也保留，延迟分位数成功请求与全请求分别报告；report标明超时是右删失数据，不能把timeout秒数当实际完成延迟。SLO同时看失败率；错误不能丢弃后只展示成功P95。只在schema正确的200计success_rps，offer/start/complete/drop/timeout各计数独立。

Markdown报告包含三组每轮全部结果、共同负载延迟、SLO通过负载、资源瓶颈、正确性失败、缓存状态与局限。汇总公式固定；不挑最好一次、不倒推调整SLO、不只公布有利接口。报告提交/推送另按用户确认执行。

## 11. 当前最多三条简历结论的验收口径

**本轮没有新的正式量化结论，旧数据不升级为严格A/B/C简历证据。** 后续最多产出以下三类，只有达到门槛才填数字：

1. 性能：同合成数据、同到达率、热稳态三重复，A→B或B→C成功RPS/延迟变化；引用manifest+requests+summary，边界为指定接口/4核测试环境，不外推日活。
2. 一致性：跨4worker的N轮写后读/撤权测试0次陈旧读取与可见性延迟分位数；引用correctness.jsonl，边界为测试定义的新请求，不冒充强事务隔离或多主机支持。
3. 工程诊断：量化生成器池CPU开销并校准后验证特定负载；引用校准样本/资源时序，不能把客户端优化表述为服务吞吐提升。

## 12. 需用户确认后推进

- 允许准备/使用哪台独立Linux目标和发压端？优先专用测试环境；不给当前生产全机加压。
- 是否接受上述合成fixture、B共享运行时开启、接口200合同、三重复/固定到达率与预计半天至一天窗口？
- 同意后先实现测试runner/导出/fixture并单测，再做隔离兼容性和低负载校准，出开测门禁结果；只有门禁通过才按批准范围正式跑矩阵。若旧版不兼容或锁等待不可精测，先报告并调整，不强行运行。

验收结论：**方案与只读预检通过；正式性能测试仍为待确认、环境未就绪。**
