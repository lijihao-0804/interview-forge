# 重建与再采集命令

本包的 maintained_sources 是可移交的离线工作台，不依赖 E盘原路径。包内上游输入只包含本专题选出的既有大厂记录；要扩大既有语料的召回范围，需换成封存v4的完整上游数据。此限制在 INPUT_SCOPE.json 中记录。

在本数据包目录运行（Python 3.10+ 标准库即可，无需安装依赖）：

```powershell
E:\python\python.exe -B maintained_sources/scripts/build_topic.py --topic-root maintained_sources --upstream maintained_sources/upstream --output rebuilt
E:\python\python.exe -B maintained_sources/scripts/build_report.py --topic-root maintained_sources --upstream maintained_sources/upstream --output rebuilt
E:\python\python.exe -B maintained_sources/scripts/verify_major_rules.py --topic-root maintained_sources --upstream maintained_sources/upstream --output rebuilt
```

工具路径可换成其他机器的python。输出写入 rebuilt，不覆盖封存交接包。元数据、完整文本、分片与报告均从冻结输入重建。

联通全量公开池再次采集示例（使用新的日期输出目录，已存在则拒绝覆盖）：

```powershell
E:\python\python.exe -B maintained_sources/scripts/collect_unicom_public.py --output snapshots/2026-12-18/unicom_105347 --campaign 105347
```

这只执行本期已验证的匿名公开API配方；将来页面迁移需先普通浏览器核验新的公开入口。遇HTTP限制/非JSON/登录要求则停止，不尝试签名、解密或绕过。每页原始响应和请求参数留档，末尾核对total/行数/唯一官方ID；直播列表在采集中变动造成总数不一致时不要把结果当完整快照。

规范化记录必须保留 id、source_job_id、company、parent_group、title、url、description、requirements、full_text、major_raw、major_evidence_scope、degree_raw、city/city_tags、student_status、batch、application_deadline、retrieved_at、source_archive 和来源类型。逐岗JD用job_specific；表中专业按table_row；批次共享条件用batch_shared，禁止给所有岗位强行套专业准入。

山东联通按jobNumber与主池交叉去重；缺jobNumber保留站点定位ID及其稳定性说明。烽火/中兴使用正常渲染的详情和官方UUID，不将仅岗位列表当作完整JD。央国企学校公告需要保留雇主发布主体、原文/表格对应行和截止时间。原采集器位于 maintained_sources/campus_bulk 与 soe_sources；这些历史采集脚本有本机路径，迁移时修改其输入输出参数，不应直接盲跑。

每期再生成规则/词表/提取器文件哈希与source-archive-manifest。专业/技术规则变更后同规则重算两期，再比较共同渠道、职业、城市与集团的提及率。

## 下期与真实跨期比较

新期规范化记录与来源文件放入新的工作台，使用 --as-of 指定实际整理日期，输出到新的目录，不覆盖本期。来源retrieved_at继续逐岗保留。

```powershell
E:\python\python.exe -B maintained_sources/scripts/build_topic.py --topic-root next_sources --upstream next_sources/upstream --output snapshots/2026-12-18 --as-of 2026-12-18
E:\python\python.exe -B maintained_sources/scripts/compare_periods.py snapshots/2026-11-18 snapshots/2026-12-18 --output comparisons/20261118_20261218.json
```

比较器只接受两个真实且日期有先后的期间，校验专业规则代码、版本、字典和提取器哈希一致。分别输出全样本、共同集团×渠道、共同官方岗位ID三种口径。表格/批次定位ID不作为已核验官方ID配对；消失ID只称“观测缺失”，不认定关闭。可加 --city 北京、--track 软件与系统开发；默认限A/B学生完整资格JD，--include-nonstudents才纳入职业参考社招。

## SQLite与统计例子

数据库 data/communications.sqlite 使用TEXT保存官方ID，避免长ID精度丢失。jobs含全文及专业、学生、来源字段；cities为多值地点；terms为970项词典；job_technologies分qualification/duty；technology_evidence保留Unicode码点偏移。FTS5可用时另建jobs_fts。

```sql
-- 学生A/B池：按集团、职业统计完整资格JD，不混入批次公告
SELECT parent_group,career_track,COUNT(*) AS qualification_jobs
FROM jobs
WHERE student_confirmed=1 AND tier IN ('A','B') AND skill_eligible=1
GROUP BY parent_group,career_track ORDER BY qualification_jobs DESC;

-- 北京学生A/B完整JD里，各技术提及了多少条岗位；多城市先用EXISTS防止重复
SELECT t.label,COUNT(DISTINCT j.id) AS mentions
FROM jobs j JOIN job_technologies x ON x.job_id=j.id
JOIN terms t ON t.id=x.term_id
WHERE j.student_confirmed=1 AND j.tier IN ('A','B') AND j.skill_eligible=1
AND x.field='qualification'
AND EXISTS(SELECT 1 FROM cities c WHERE c.job_id=j.id AND c.city='北京')
GROUP BY t.id ORDER BY mentions DESC;
```

完整详细度子集为 data/detailed-jds.ndjson.gz，是corpus的派生筛选，不能再次相加计数。专业候选CSV的字段用于投递筛选，技术聚合CSV包含零值，适合后续长期比较。

比较器还会要求新期记录有晚于旧期整理日的真实source_snapshot；只更改--as-of会被拒绝。保留在新语料库中的旧期记录会列入stale排除计数，不自动当作新期重新观察。比较时同时核对届别/批次与来源覆盖，不能把未重采或未进入筛选条件解释成岗位关闭。
