# 直接在交接包内运行

在本包根目录打开终端。分析、核验和分期注册工具只需Python标准库；联网采集器的可选依赖另列在source_project/requirements-optional.txt。

```powershell
python tools/serve.py --port 8765
python tools/verify_data.py
python tools/verify_technology.py
python tools/verify_lexicon.py --extractor tools/technology_enrich.py --dictionary data/technology/technology_dictionary_v4.json --output reports/lexicon-verification.json
python tools/snapshot_registry.py self-test
python tools/technology_report.py --catalog data/catalog.json --technology-index data/technology-index.json --snapshot 2026-11-17 --output-dir reports/recomputed-atomic
```

复用冻结词典在已保存原文上重新提取，输出到新工作目录：

```powershell
python tools/technology_enrich.py `
  --input data/corpus.ndjson.gz `
  --dictionary data/technology/technology_dictionary_v4.json `
  --snapshot-date 2026-11-17 `
  --output-dir derived/reextracted-2026-11-17 `
  --analysis-dir derived/reextracted-2026-11-17/analysis
```

新一期请替换input与真实snapshot-date。输入不变、同版规则的重提取属于处理复核，不产生新观测期。不要把输出目录设为历史snapshots。上面的核验/重算命令可能生成报告或派生产物；重新封包时应同步文件清单和哈希。

本版真实快照已经登记在data/snapshot-registry.json，无需再注册2026-11-17；重复日期会被拒绝。下一期先在独立工作目录完成采集、解析、技术提取和审阅，再登记：

```powershell
python tools/snapshot_registry.py register `
  --registry data/snapshot-registry.json `
  --snapshot-date 2026-12-17 `
  --source-corpus monthly_runs/2026-12-17/corpus.ndjson.gz `
  --city-catalog monthly_runs/2026-12-17/catalog.json `
  --technology-index monthly_runs/2026-12-17/technology-index.json `
  --metadata monthly_runs/2026-12-17/snapshot_metadata.json
```

上面的2026-12-17是命令示例，不是已经存在的真实快照。metadata契约见snapshot-contract.json，现有完整范围说明可参考baseline-metadata.json，不能只改日期照抄其公司覆盖、采集时间和失败情况。

真实第二期登记成功后，比较某公司、城市和方向：

```powershell
python tools/snapshot_registry.py compare `
  --registry data/snapshot-registry.json `
  --from 2026-11-17 --to 2026-12-17 `
  --company 百度 --city 北京 --direction 'AI Infra' `
  --output data/comparisons/2026-11-17_to_2026-12-17_baidu_beijing_infra.json
```

不传company/city/direction即比较全部采集范围；三个选项都可重复。城市精确匹配冻结标签，方向为标题/职能/方向字段子串。结果分别记录整体、共同公司和共同岗位的提及率与百分点差，以及同岗资格技术新增/移除；详见MAINTENANCE.md。

词典升级时，使用已归档原文重提取历史各期，并在data/derivations/<处理版本>/registry.json建立独立派生登记簿。保留原始日期与原manifest/corpus哈希，不能把处理日期当新市场观测。原始登记簿与快照不覆盖。

每个已发布处理版本的**完整词典文件与提取代码**另外冻结在`data/processing_versions/`，登记簿为`data/processing-registry.json`。新增规则版本时先执行下列命令；已登记版本拒绝覆盖。旧期次索引中的dictionary/extractor哈希可以在这里找到对应文件。

```powershell
python tools/archive_processing_version.py --dictionary 新版词典.json --extractor 新版提取器.py --registry data/processing-registry.json
```

网站更新时同步重建catalog及详情、词典索引和gzip镜像、分析结果、审读结论文案与manifest哈希。不要只替换目录却沿用旧日期/统计文字。前端仅展示登记记录，完整性校验由维护工具完成。
