# 就业数据快照维护与跨期比较 v4

**在本交接包直接运行，请先读 [包内命令](maintenance/PACKAGE_COMMANDS.md)。** 本文保留上游研究目录的采集路径示例；包内对应工具是`tools/snapshot_registry.py`，登记簿是`data/snapshot-registry.json`，历史目录是`data/snapshots/`。采集器参考代码位于`maintenance/source_project/analysis/`，应复制到新一期独立工作目录后使用。

本指南供后续维护者在独立工作副本中更新公开招聘岗位样本。当前提供的是 **2026-11-17 已完成快照的基线登记**；登记动作发生在 2026-11-18，不代表 2026-11-18 又进行了一轮采集。现有真实基线只有一期，因此它只提供单期统计，不能称为趋势。

## 交付文件与接口

维护工具只依赖 Python 标准库，可在研究目录的 `analysis/` 下运行，也可复制到另一个项目的 `tools/` 后运行。所有输入路径由命令参数传入，不依赖固定工作区绝对路径。

| 文件 | 用途 |
|---|---|
| `longitudinal/registry.json` | 不可覆盖登记簿；按快照日期索引 manifest、summary、原始语料和可选词典索引，记录相对路径与 SHA256。 |
| `longitudinal/snapshots/YYYY-MM-DD/manifest.json` | 日期、来源范围、解析器/词典版本、完整度、失败、公司计数、原始语料哈希和归档文件清单。 |
| `longitudinal/snapshots/YYYY-MM-DD/summary.json` | 前端可读的单期汇总；`trend_available=false`。跨期结果另由 `compare` 生成。 |
| `longitudinal/snapshots/YYYY-MM-DD/corpus.ndjson.gz` | 从输入语料逐字节复制的 gzip，若输入为 plain NDJSON 则用确定性 gzip 压缩；原文和原始 source ID 随行保留。 |
| `longitudinal/snapshots/YYYY-MM-DD/technology-index.json` | 可选，原样归档的原子 technology requirement 索引。 |
| `longitudinal/snapshots/YYYY-MM-DD/city-tags.json` | 可选，只冻结 `job id → city_tags[]` 映射，不复制 44 MB 全量 catalog。 |
| `analysis/snapshot_contract_v4.json` | 元数据、登记簿、manifest、summary、compare 报告的字段契约。 |

注册器拒绝重复日期、重复/空岗位 ID、technology index 与 corpus ID 集合不相等、合成 fixture、哈希不匹配和 archive 路径越界。已注册快照不会被替换；比较报告也默认不可覆盖。登记簿只在新增日期成功后原子更新。

维护/分析工具读取快照前核验 manifest/corpus/summary 哈希。前端可读取 `registry.json` 的 `snapshots[YYYY-MM-DD]` 映射展示登记信息；当前前端并未承诺在浏览器运行时校验这些哈希。当前 registry 的相对路径以 `longitudinal/` 为根。前端可以按自身路径约定生成 `data/snapshot-registry.json` 适配副本；不要把适配副本中的路径当作原始证据。

## 当前真实基线

基线来自交接包 `data/corpus.ndjson.gz`，并保持其压缩字节不变。v3 manifest 记录 28,344 条岗位、28,268 条有正文、28,144 条有独立资格文本、20 家公司、37 条人工审读；取数时间为 2026-11-17 20:40:32 至 22:15:13（Asia/Shanghai）。登记器将这些统计重新从语料扫描并校验。

覆盖不是统一口径的全站清点：公司采用的招聘入口、职位类型、页面分页、关键词、地区和详情开放范围各有差别。全部来源不代表中国互联网市场总体或完整 vacancy census。公开页面列出的岗位也不等于确认招聘人数或实际剩余 HC。缺少行、详情失败、未知地点和未出现的职位均保留为未知/未观察状态，不能当作 0 或已关闭。

已知范围边界包括：

- 拼多多样本有 36 条校园职位正文和 16 条社招“热招/最新”列表元数据；社招主列表显示 0，16 条没有完整详情，详情受官网 anti-content 限制。本次不会构造或绕过该参数。
- 网易社会招聘接口采集过程中总量变化：曾观察到 2,652 条/266 页，随后复核为 2,648 条/265 页；第 266 页为空。按实际捕获、唯一 ID 和后续校园入口分别留痕，不声称静态零遗漏。
- 字节跳动按官网显示研发、产品、运营页码并对多个查询按职位 ID 去重；官网分页有上限和跨查询重复，唯一职位总数不等于招聘全站完整度。
- 百度、科大讯飞、腾讯、京东、硬件、外企等渠道的总数与取数范围按对应 audit 记录解释；不同范围的公司数不能作市场份额分母。
- 硬件第一次探测的华为/荣耀公开接口路径错误，后续正式 audit 已使用修正路径；Apple 初始详情请求有超时并做了恢复尝试。历史失败仍在 audit 引用中，不把失败尝试计作额外岗位。

基线 package manifest、采集 audit 和源代码文件的 SHA256 作为 `snapshot_baseline_v4.json` 的来源证据。source 路径只作为 provenance 文本，不是文件链接。`city_tags` 不在该包的 NDJSON 行内；它由 v3 catalog 从每条来源 `city` 字段应用明确中英文别名表产生。注册时传 `--city-catalog`，只按岗位 `id` 抽取并冻结为 `city-tags.json`。后续 compare 精确匹配冻结标签，不从正文、国家/地区字段或未来会变的 catalog 重新推断城市。

## 冻结采集器的使用边界

交接包 `maintenance/source_project/` 是 2026-11-17 的采集代码参考快照。它按 `Path(__file__).resolve().parents[1]` 定位项目根，故需保留 `source_project/analysis/` 结构。`source-manifest.json` 列出文件哈希；可选依赖在 `requirements-optional.txt`。其中没有凭据、浏览器个人配置或 cookie。父目录根的 `MAINTENANCE.md` 也记录了参考包边界。

这些代码不是“所有网站都能一键重抓”的承诺。招聘页面和接口可能变化，分页、详情、字段语义需要每期重新验证；历史补抓脚本也依赖之前生成的 evidence。先读入口函数、对应 `*_audit.json` 和 endpoint 注释，再以匿名访问做一页/一岗探测，确认真实官网 UI 路径、响应结构、报告总量和详情链接。对于只在正常匿名公开页面可见的数据，按页面限速。遇到登录、验证码、签名、anti-content/访问限制即停在公开范围并记失败，不绕过、不重建签名。

采集器内可核对的当前公开入口例子：

| 公司/渠道 | 参考脚本及当前代码中的公开路径 | 注意 |
|---|---|---|
| 腾讯 | `collect_tencent.py`：官方 `Query` 分页、`ByPostId` 详情 | 初始公开列表有 2,121 行，按中国范围取 1,855 条详情；接口字段 `IsValid` 不等同实际 HC。 |
| 字节跳动 | `collect_bytedance_expanded.py`：`jobs.bytedance.com`，`/api/v1/search/job/posts` | 查询及分页行数/唯一 ID 分开检查；有官方分页上限及跨页重复。 |
| 百度 | `collect_software_employers.py`：`talent.baidu.com/httservice/getPostListNew` | SOCIAL、GRADUATE、INTERN 类型分别记录报告量、页数和详情数。 |
| 拼多多 | 同上：`careers.pddglobalhr.com/api/careers/api/recruit/position/list` 与 `/detail`；社招公开 `latest_list` | 当前仅“最新/热招”区域；正文访问失败或要求 anti-content 就记录受限。 |
| 科大讯飞 | 同上：`iflytek.zhiye.com/api/Jobad/GetJobAdPageList` | 类别 ID 来自公开招聘页面，逐期校验，不把旧 ID 当永远有效。 |
| 网易 | 同上：`hr.163.com/api/hr163/position/queryPage`；校招以官网当前 navigation 项目驱动 `/api/campuspc/position/getJobList` | 不固定使用历史 projectId；保存当期官网当前导航和返回总量。 |
| 华为/小米/荣耀 | `collect_hardware_employers.py`：官网公开招聘页使用的职位列表接口；华为 `getJobPage`、小米 `searchJobPage`、荣耀 `listPosition`/`listPositionDetail` | 详情 URL 和页面路径以 audit 记载为准；旧失败路径不重复当成当前端点。 |
| Amazon/Google/Workday/Qualcomm 等 | `collect_foreign_v2.py`：Amazon Jobs JSON、Google Careers public results、Workday `/wday/cxs/{tenant}/{site}/jobs`、Qualcomm public position search/detail | 各站国家筛选与地域口径不一致；保留原始地区和未知，不用公司所在国家补缺。 |

以上路径只是被冻结代码中的线索。运行前必须从目标站点当前公开前端确认仍可匿名访问和分页真实含义。不要仅因裸请求失败就认定站点不可采；也不要对抗验证码或访问控制。

## 月度采集执行流程

1. 创建新的日期工作副本，不在已登记的快照、历史采集目录或前端交接包内直接跑 collector。将 `maintenance/source_project/` 完整复制到 `monthly_runs/YYYY-MM-DD/source_project/`，保持 `analysis/` 目录结构；每次独立运行，防止 `evidence/`、`archives/` 和 audit 被旧任务覆盖。
2. 使用项目现有 Python 环境或隔离环境安装可选依赖。先执行 `python .\analysis\collect_software_employers.py --help`、相关 collector 的 `--help`（如支持），查看该期目标公司和代码写出位置。不要把可选包安装到全局环境。
3. 逐站确认公开列表页、列表 API、详情页、报告 total、page size、实际 page count。记下 `access_time`/时区、列表原始行数、跨页重复、唯一 `source_job_id` 数、详情成功/部分/列表-only 数、未知/失效字段、失败页、限制和重试过程。访问失败不写成 0 个岗位。
4. 只采集官网公开、匿名可见内容。详情页拒绝访问时保留列表事实和阻碍；不改签名、不使用他人账号、不向招聘者发消息。正常低频请求；检查页面返回量/分页数变化后再续采，避免重复请求全部历史页。
5. 每家公司在本轮工作目录里落盘原始公开响应/列表页和详情响应到 `archives/`（JSONL 或逐页 JSON），同时保存公司 audit。保留所有岗位原文、职责、资格、bonus 原始段、源岗位 ID、类别原值、地点原值、经验/学历原值及日期字段。原始响应与标准化正文分开保存；对原始响应和每个正文算 SHA256。
6. 对每站实际验证后再运行对应 integration/normalizer。岗位去重键是 `(company, source_job_id)`；不按标题或全文去重，不跨公司合并。缺 source ID、重复身份键和身份变更单列审查。类别/技能/方向是派生字段，与来源原字段并存。
7. 整合后核对每家公司：官网 total vs 采到列表行 vs 去重 ID，页码覆盖，详情状态，正文/独立资格分母，失败与异常、更新时间跨度、未知地理、原文 hash 数、HC 限制。任何一项未对齐都在 metadata 中标 `partial` 或 `unknown` 并给理由，不自动标 `complete=true`。
8. 审阅代表性记录和原始 JSON archive：抽查列表与详情 ID 一致；确认岗位正文没被公司宣传 footer、bonus、重复段落等误解析；检查原始字段没有被派生分类覆盖。按独立职位审读，不按公司名气或篇幅选岗位。
9. 生成新的 corpus NDJSON 或 gzip NDJSON，写明 `snapshot_date` 是真实访问日期（Asia/Shanghai）、parser/dictionary/extractor 版本、范围/完整度、公司表、失败、source corpus hash、上游 audit 的 hash 引用。使用唯一新日期 register；日期重复会被拒绝。

推荐的隔离副本 PowerShell 形式（用实际目标路径替换变量；该命令示例不会自动运行所有站点）：

```powershell
$py = 'E:\python\python.exe'
$run = 'E:\monthly_runs\2026-12-17\source_project'
Push-Location $run
& $py .\analysis\collect_software_employers.py --companies baidu iflytek pdd netease
& $py .\analysis\collect_tencent.py
& $py .\analysis\collect_bytedance_expanded.py --headless
& $py .\analysis\collect_hardware_employers.py
& $py .\analysis\collect_foreign_v2.py
Pop-Location
```

上面只示范入口名。某个脚本若路径或参数已变，先检查当前源码和 `--help`，对独立站点单独执行；不要因某一站失败而跳过其余站点。社招/校招、地区、职位类型和公开入口要分别记录。对于 Apple 恢复、历史补抓和 `integrate_v2.py` 等有依赖的脚本，先读对应 job spec 与入口代码并在新工作副本中准备输入，不能把它们当成独立重抓器。

## 登记真实基线/新一期

先整理 metadata JSON，字段示例见 `snapshot_contract_v4.json`。`parser_version` 必须是明确、稳定、可审计的版本字符串；推荐将解析脚本版本和其 SHA256 一并写入 `parser_provenance`。`scope` 需列采集入口、职位类型、区域/关键词/page范围；`collection_completeness` 按公司写 partial/unknown 与解释。不能只用当前行数反推全站完整。

以当前研究包为例，在项目根运行；真实基线日期仍是 2026-11-17：

```powershell
$py = 'E:\python\python.exe'
& $py .\analysis\snapshot_registry_v4.py register `
  --registry .\longitudinal\registry.json `
  --snapshot-date 2026-11-17 `
  --source-corpus .\前端交接包_就业数据台\data\corpus.ndjson.gz `
  --city-catalog .\前端交接包_就业数据台\data\catalog.json `
  --technology-index .\前端交接包_就业数据台\data\technology-index.json `
  --metadata .\analysis\snapshot_baseline_v4.json
```

基线注册须使用已检查版本的 technology index；若本期无该文件，省略 `--technology-index`，summary 会明确写 legacy skill fallback。不要手工创建 2026-11-18 快照来“凑”第二期。首次注册成功后，registry/manifest/summary、corpus 和附加索引都以相对 `longitudinal/` 路径引用，哈希作为读取前校验。

后续新一期示例（命令行路径需指向本次整理好的文件）：

```powershell
& $py .\analysis\snapshot_registry_v4.py register `
  --registry .\longitudinal\registry.json `
  --snapshot-date 2026-12-17 `
  --source-corpus .\monthly_runs\2026-12-17\corpus.ndjson.gz `
  --city-catalog .\monthly_runs\2026-12-17\catalog.json `
  --technology-index .\monthly_runs\2026-12-17\technology-index.json `
  --metadata .\monthly_runs\2026-12-17\snapshot_metadata.json
```

若输入是 plain NDJSON，注册器会压为 `.gz` 归档，并分别记录 source/archived hash；gzip 输入原样复制，hash 完全相同。metadata 的 `expected_counts` 若设置，会和语料重新扫描计数核对。注册报错时不要删除或改写已有快照来重试；检查未完成的新 staging、路径和输入 hash，修正 metadata 后用未注册的新日期/独立 registry 重新执行。

## 同期范围和词典更新的派生版本

不可覆盖 registry 按采集日期登记，不能用同一 registry 同日覆盖同一 snapshot。若之后升级技术词典/解析器，需要在已归档每一期原文上重新解析，并创建独立派生 registry，例如 `longitudinal/derivations/tech-v2/registry.json`。该 registry 记录相同原始 `snapshot_date`，但使用新语料派生结果、明确新 parser/dictionary version，并在 metadata 的 `derived_from_snapshot`/`upstream_provenance` 写原 snapshot 日期、原 manifest SHA、原 corpus SHA 和派生规则哈希。此操作是“同一期历史语料的重新提取”，不是新一期采集。

派生时从原 registry 校验 manifest/corpus hash 后读取 `snapshots/YYYY-MM-DD/corpus.ndjson.gz`，保留原文和 `(company, source_job_id)`；城市标签如要保持原期口径，传原快照冻结的 `city-tags.json` 给 `--city-catalog`，注册器支持该 `by_job_id` 格式。不要从未来 catalog 重算历史 city tags。派生索引/语料只写入新 derivation registry 的归档目录，原注册簿保持不变。

如果比较报告因 parser/dictionary/extractor 版本或 dictionary/rule SHA 不一致而拒绝，应分别对两期已归档原文运行同一版 parser/technology extractor，再在同一派生 registry 注册；不要仅改版本字符串绕过 gate。Technology index 的 `jobs` key 集合必须与该期 corpus 的 `id` 集合完全一致；requirement/duty/fulltext 各项以去重 term ID 数组表示。

## 跨期比较与字段解释

```powershell
& $py .\analysis\snapshot_registry_v4.py compare `
  --registry .\longitudinal\registry.json `
  --from 2026-11-17 --to 2026-12-17 `
  --company 百度 --city 北京 --direction '数据平台' `
  --output .\longitudinal\comparisons\2026-11-17_to_2026-12-17_baidu_beijing_data.json
```

`--company`、`--city`、`--direction` 都可重复。公司按 company 精确匹配；城市按快照自己的冻结 `city_tags` 精确匹配（无标签时只用来源 `city` 原字段精确匹配）；方向在 `title_direction`、`job_family`、`title` 上做不区分大小写的子串匹配。过滤条件会写进报告；新增/未重现只在这个 selected scope 内解释。

职位匹配键是 `(company, source_job_id)`。缺少身份字段不进入新增/未重现/共同职位分母；一个截面内若同键重复，则该键两期都排除并报告歧义。报告包含：

- `newly_observed_in_selected_scope`：本期筛选范围观察到而上期未观察到的岗位。
- `not_reappeared_in_selected_scope`：上期存在但本期筛选快照未再出现的岗位；这不表示招聘关闭或下架。
- `common_matched_jobs`：共同公司+source ID 职位 cohort，含正文 hash 和独立 qualification hash 前后值、资格变化标记、technology requirement term 增删。
- `populations.full_sample`：两期各自筛选的全样本；`n` 会受详情/资格覆盖变化影响。
- `populations.common_companies`：只留两期都出现的公司，但职位构成和分母仍可变化。
- `populations.common_matched_jobs.skills`：固定共同职位中两期都存在可读资格技能向量的职位数 `n`；对每个技术 term 报告前后 `q`、`q/n` 和百分点差。缺失/解析失败资格文本不进 `n`，不会被算作“未提到技能”。

默认用两期同版本 `technology-index.json` 的 `jobs[id].requirement` 原子标签。登记时索引岗位 ID 集必须与语料 `id` 集完全一致；索引若带 `snapshot_date` 或 `source_corpus_sha256`，必须匹配该期日期和输入语料原始字节 hash（NDJSON 转 gzip 前）。metadata 应给出 technology extractor version、dictionary source SHA 和 extractor 源码 SHA；若 index 自带 extractor/rules/dictionary/parser fingerprint，也一起记录并核对。词典版本、term清单、声明的 hash/version 必须一致；不一致时拒绝比较，要求同规则重新提取。若两期缺少兼容 technology index，只能在 parser 一致且 legacy skill dictionary version+SHA 完全相同时走旧 `skills_in_requirement` fallback，报告会显式标出 fallback。技能被提及不代表它是硬门槛，也不代表岗位录用条件已经确认。

全文 hash 变化和 qualification 段 hash 变化分别统计。公司统一 footer 变化可让全文 hash 改变，但资格段不变；逐岗位明细分别记录全文 hash 与资格段 hash，不重复展开长正文。原始正文仍在压缩语料中。

scope/completeness 元数据不同会在报告中标记，且影响解释。共同公司不代表两期的采集入口和职位类型相同。报告不能由招聘数推断 HC；未观察职位不等于已下架。每个 compare 输出使用新文件名；只有明确需要替换分析报告时才传 `--replace-report`，该参数不会修改 snapshot。

## 月度复核清单

- 快照日期对应真实访问日期；访问时区、时间范围、每站范围和过滤条件齐全。
- collector、解析器、skill/technology dictionary、extractor 的版本和代码/规则 hash 可回溯。
- 每家网站的 reported total、抓到行数、unique ID、分页和正文数并列；缺页/限流/验证码记为未知或失败，不作零。
- 正文 `text_sha256` 与 requirements 原文分开；bonus 与来源层级保留；新旧职位以 `(company, source_job_id)` 对齐。
- 注册前原始 corpus/audit/catalog/technology index SHA256 已复核，已存在日期没有被覆盖。
- 查看 compare 的 scope drift、资格覆盖、技能 n/q、共同公司和共同职位分母；优先解释共同职位百分点，再解释全样本变化。
- 抽查每家公司数个职位的官网 URL、源 ID、岗位标题、分类原值、经验/学历原值、资格正文和来源详情状态。
- 仅报告页面可见信息，不声称已确认在招 HC、薪资预算或招聘者反馈。

## 本工具的自动化验证

```powershell
E:\python\python.exe .\analysis\snapshot_registry_v4.py self-test
```

自测仅在临时目录生成合成两期语料，不调用网络、不写真实 registry；覆盖 gzip/纯文本 NDJSON 归档、城市/方向过滤、同岗位匹配、footer-only 全文变化、资格变化、technology term 增删、技能 n/q 与百分点、索引 ID/date/source-hash gate、词典不匹配和单期不可比较。
