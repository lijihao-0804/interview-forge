# 数据字典与分期采集指南

版本为 expansion-1.0，本期编制日期为 2026-11-18。岗位的实际采集时间保存在每条记录的 observed 字段。

## 下载与二次分析

| 文件 | 用途 |
|---|---|
| [完整语料](data/corpus.ndjson.gz) | 一行一个去重岗位发布记录。含原文、职责、资格、来源、证据和合并时遇到的其他来源。|
| [详细 JD 子集](data/detailed.ndjson.gz) | 有独立资格段、职责及资格分别至少 100 字符、资格提及至少两项词典技术。中英文长度口径会影响入选，供阅读筛选。|
| [SQLite](data/jobs.sqlite) | job 主表，scope/major/skill 多对多关联表，term 字典。可查询岗位方向、专业、地区、不同来源与技术交集。|
| [全部雇主名称](data/employers.csv) | 雇主及各方向记录量、来源披露人数与性质。|
| [分方向技术统计](data/skills-by-scope.csv) | 含零命中词的长表，有岗位和雇主两种权重。|
| [轻量岗位索引](data/catalog.json) 与 [技术词表](data/terms.json) | 前端筛选、再可视化。索引中的 part 相对于 data/。|
| [去重记录](data/dedup.json) 与 [本期元数据](data/release.json) | 合并依据、数据与规则版本。|
| [来源覆盖与缺口](data/coverage.json)、[校招门户逐站清单](data/campus-board-coverage.json)、[国际招聘板逐站清单](data/global-board-coverage.json) 与 [分期登记](data/periods.json) | 搜索渠道、无匹配或无法读取的站点、实际留存口径、历史日期。|

## 统计时的三个分母

研究方向支持多选，同一职位可以同时属于 AI 与电子信息。统计岗位先按 id 去重，统计雇主按 company 去重。company 是按数据可核对的集团、雇主或招聘门户名称，hiring_unit 保留具体招聘单位或原刊名，不能把二者相加作为独立公司数。

技术频率只用本筛选中 eligible 为真的独立资格段。tech 是去重后的资格技术 ID，duty_tech 来自职责。国际招聘板的 description 是职责证据摘句，完整工作说明以 full_text 为准。technology_evidence 记录术语 ID、起始位置与左闭右开的终止位置，偏移按 Python Unicode 码点计算。必备、至少一种、优先、加分等关系仍需看原句。

专业证据位于 major_evidence。专业简称和研究生学科保留各自粒度，学生入口是另一字段。专业证据和学历须指向同一招聘子方向才能用于个人投递判断。规模使用来源人数区间；同一名称若在不同公告披露不同人数，各条均保留原值。ownership 包含高校名片、雇主页面与已核验的集团归属，具体来源保存在原始采集文件或 source_metadata，跨来源用词可能不同。

## 历史存档与来源

两份封存的上游包提供既有互联网 JD 和通信专题采集。两个包的重复记录按原始 ID 连接专业证据。新增的牛客、雇主招聘门户、雇主校招站、国际 ATS 以及国家大学生就业服务平台采集都保留原始响应。国家大学生就业服务平台的部分搜索在第六页要求登录，按可公开取得的页留档。独立源采集器存有原始请求 URL、成功、未匹配或失败日志。保留记录在 source_id、url、observed、archive 等字段指向来源。

同源正式招聘系统通过各自岗位编号识别记录；独立编号有可能使用相同模板。聚合平台镜像另核对逐岗链接、同雇主/同职位/同地点的相同正文，归并结果写入 occurrences。数据集的雇主名采用有限的可核对别名，没有注册号的主体保留招聘名。跨平台改写、异名或无法确认的重复可能仍在。分析来源不等量、用人单位覆盖不等概率、岗位下架和工作地点限制时需保留这些字段。

## 如何留存下一期

1. 复制本地“采集与复算工作包”到新的日期目录，保留上期原始文件与两个封存上游目录。按四个 collect 目录的 README 或采集器参数拉取公开数据；使用新的空输出目录。仅重做解析时直接读取已存响应。
2. 保留逐条原始 ID、雇主主体、地点、资格/职责、完整正文、获取日期和响应路径，并记录入口、分页上限、失败和下线状态。collect_ncss/collect.py 的 --output 指向新的空目录；交给统一构建时将该次目录置于输入根的 collect_ncss/period_01，日期由实际时间戳决定。
3. 主要构建使用 Python。需要 requests、bs4、lxml（网页采集），markdown（生成报告），playwright（浏览器验收）。在工作包根目录运行下面命令，将输出路径放在一个新目录。V4 与 COMM 指向介绍中的两份上游解压目录。所有目录可放在本地，无需生产数据库。

```text
python -B tools/build.py --input-root . --main-baseline "V4" --communication-baseline "COMM" --snapshot YYYY-MM-DD --output "OUT"
python -B tools/archive.py metadata --output "OUT"
python -B tools/report.py --output "OUT"
python -B tools/guide.py --output "OUT"
python -B tools/verify.py --output "OUT" --qa "QA"
python -B tools/browser.py --output "OUT" --qa "QA"
```

4. 归档语料、SHA256、来源覆盖、规则/词典和验收报告，冻结新的发布包。工具保留 source_id 和原文，后续修改筛选或词典时可对历史输入重新处理。网页页首的日期由 release.json 决定。
5. 两个真实日期的来源采集齐备之后，使用 compare.py 比较。传入前后期 **data 目录**。它检查规则/词典哈希和原始观察日期，排除从旧包沿用的记录。只报告共同渠道与雇主、同源同雇主同岗位 ID 两种口径。没有再次出现的岗位状态仍待核。只有一期可用时不计算涨跌。

```text
python -B tools/compare.py PREVIOUS/data NEXT/data --scope AI应用与智能体开发 --out change.csv
```

## 网站接入

将前端文件夹整体挂在静态目录，建议入口 /research/market/。从 /research/jobs/ 和 /research/communications/ 的研究结论或筛选入口链接本版，可用 scope 查询参数直接打开相应方向。前端通过相对 URL 按需加载详情分片。mjs 按 JavaScript MIME 提供；原始 gzip 为下载文件，避免附加重复的 Content-Encoding。归档复算工作包包含未脱敏的原始公开页面和采集过程文件，供资料维护者本地保管；网站只需部署前端包。
