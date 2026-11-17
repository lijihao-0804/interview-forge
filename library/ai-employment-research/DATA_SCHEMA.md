# Employment Data Bundle v4 schema

This package is an offline export of the 2026-11-17 Asia/Shanghai snapshot. It is independent of the workspace’s v2 evidence and report files.

## Package layout

```text
前端交接包_就业数据台/
├── DATA_SCHEMA.md
└── data/
    ├── catalog.json
    ├── details/<company>_<batch>.json
    ├── corpus.ndjson.gz
    ├── sources.json
    └── manifest.json
```

`catalog.json` has a `jobs` array with compact metadata and no job-description text. Each row’s `detail_shard` is relative to `data/`. A detail shard is an object keyed by job `id`; a job’s full record is stored at `shard[id]`.

## Catalog fields

| Field | Meaning |
|---|---|
| `id` | Stable unique record ID in the exported dataset. |
| `company`, `company_group` | Company name and the explicit group label `中国企业` or `外企`. |
| `source_job_id`, `job_code_raw` | Original employer/source ID and original or extracted job code. |
| `title`, `job_family`, `title_direction` | Original title and existing role-family/direction classification. |
| `city` | Source location text as stored upstream; it may contain several locations or non-city text. |
| `city_tags` | Ordered, deduplicated city matches from the embedded Chinese/English alias map. Multiple matches are retained. Unmatched text, province-only locations, “global”, remote, and unknown values are not guessed into a city. |
| `geography` | Existing geography classification; it is not recalculated from `city_tags`. |
| `experience`, `degree_raw`, `education_mentions` | Existing experience text, raw degree field, and extracted education mentions. Raw “unknown/not stated” values remain as recorded. |
| `skills_in_requirement` | Skill terms found in requirement text. A mention does not imply a mandatory hiring threshold. |
| `ai_signal` | Existing AI signal label, not a new classification. |
| `summary` | Existing summary sentence(s). Full body remains in the detail shard. |
| `clarity_score`, `clarity_candidate` | Rule-based clarity screening fields, not job value, compensation, or hiring probability. |
| `reviewed_clarity`, `review_reason` | Whether a record received the separate manual clarity review, and the retained reason when available. Only the reviewed subset is manual. |
| `body_chars`, `requirements_available` | Existing body size and independent-requirements availability flag. The manifest’s independent-requirements denominator counts rows where this flag is true. |
| `archive_status`, `record_kind`, `requirements_parse_status` | Existing body/archive, record, and requirement parsing statuses; see the source values for exact categories. |
| `url`, `url_kind`, `source_type` | Official source URL, existing URL kind, and collection source type. URLs are source links; local archive paths are not included. |
| `retrieved_at`, `posted_date` | Retrieved timestamp and source publication date string; they are not interchangeable. |
| `text_sha256` | SHA-256 of the normalized `full_text` string in UTF-8. Empty source text retains its empty/missing value. |
| `detail_shard` | Package-relative lookup path under `data/details/`. |

## Detail fields

Each detail object retains `description`, `requirements`, `requirements_analysis`, `full_text`, and `bonus_source` exactly as exported from v2, including blank strings and the existing `requirements_parse_status` marker. `source_url_resolution` explains how the source URL maps to a job when available. `text_sha256` hashes `full_text`; a missing or unarchived body is not synthesized.

## Reading one detail shard

```python
import json
from pathlib import Path

package = Path("前端交接包_就业数据台")
data_dir = package / "data"
catalog = json.loads((data_dir / "catalog.json").read_text(encoding="utf-8"))
row = catalog["jobs"][0]
shard = json.loads((data_dir / row["detail_shard"]).read_text(encoding="utf-8"))
detail = shard[row["id"]]
print(detail["description"], detail["requirements"])
```

## Reading the gzip NDJSON corpus

`corpus.ndjson.gz` keeps all standardized v2 fields and adds `detail_shard`. It omits the local `archive_html` and `archive_json` paths. `source_file` remains only as upstream provenance text and must not be treated as a clickable package path.

```python
import gzip
import json

with gzip.open("前端交接包_就业数据台/data/corpus.ndjson.gz", "rt", encoding="utf-8") as stream:
    for line in stream:
        row = json.loads(line)
        if row.get("requirements_available"):
            analyze(row)
```

## Interpretation limits

- `skills_in_requirement` records mentions. Distinguish required, preferred, optional, and contextual language by reading the original `requirements` and `requirements_analysis` text.
- `requirements_available` is the upstream independent-requirement flag; a non-empty combined body alone does not make it true.
- Multiple `city_tags` reflect multiple explicit location mentions. An empty list means no city alias was confidently matched, not that the job is remote.
- Publicly visible job pages and source headcount fields do not confirm remaining hiring capacity (HC).
- `clarity_candidate` is a rule screen; `reviewed_clarity` identifies the smaller manually reviewed set.
- `manifest.json` file paths are relative to the package root. `detail_shard` paths are relative to the `data/` directory. The manifest inventories payload files but excludes its own self-referential hash.

## 前端高级分析扩展

目录额外提供 `posttraining_duty_signal`（836条）、`posttraining_requirement_signal`（923条）和`posttraining_candidate`（1257条）三个布尔特征，来源为上游v2逐岗正文线索清单。职责或资格词命中的纯并集为1254，候选1257还合入3条仅由严格标题入列的记录。它们是生成式语境下的词线索，不认定岗位主责，不可相加为HC。全文与重算输入仍可从details/corpus获得。

固定研究结论与高级JSON分析排除2条已识别招聘池，职位分母为28342、要求分母28142；前端默认保留全部28344记录/28144可用要求，可勾选“排除已识别招聘池”对齐。四个目标方向的分母不受这2条影响。

城市标签用于检索与覆盖计数，不是标准地理编码；原始地点仍保留，极少数地名别名/行政后缀可能分列。多地标签不应相加为去重岗位数。

## 原子技术扩展与原文证据

`data/technology-index.json` 与目录按 `id` 精确一一关联，不改写 `skills_in_requirement` 的旧含义。顶层 `dictionary_version` 标识冻结词典；`terms` 含 `id/name/category/aliases`；`jobs[id]` 的 `requirement/duty/fulltext` 是去重的技术ID数组。不同技术独立计数，别名归一到同一ID。读取时先通过terms把ID映射为展示名称，不应把原子ID当旧技能标签。

资格段提及率的分母严格取 `requirements_available == true`，即使全文存在也不能替代这个标记。职责和全文以已存正文为分母；字段提及不能自动解释成必备。显式优先字段、资格中的“或/至少一种”、否定上下文需读原文证据。

`data/technology/` 保存提取器产出的词典、证据引用与候选队列。证据位置相对于其声明的源字段，不能拿全文offset去切资格段；重新格式化文本后应重提取证据。未审核候选不进入正式技术索引。

索引另含`snapshot_date`、`source_corpus_sha256`、`dictionary_sha256`、`extractor_version/extractor_sha256`和`parser_version`。源语料哈希绑定实际输入文件字节；词典哈希为UTF-8、sort_keys、无多余空格的规范JSON SHA256，独立文件字节哈希另见manifest。提取代码hash同时锁定词典guard的实现。分期注册核对日期、语料绑定和岗位ID集合，比较时要求规则身份一致；两期的原文语料hash自然可以不同。

证据为`technology_evidence_v4.ndjson.gz`，按岗位保存`field/offset_start/offset_end_exclusive/matched_alias/snippet`。偏移是Python Unicode code point索引，左闭右开；JavaScript需要先用`Array.from(text)`转为字符数组再按这些偏移切分，不能直接用UTF-16字符串slice。每个词在每字段最多保存前两个命中片段，并另记该字段总出现次数，完整原文不截断。索引统计按岗位是否提及去重，不按出现次数累加。

## 分期、处理版本与可比性

`data/snapshot-registry.json`登记真实观测期；每期的manifest/summary/corpus和技术索引位于`data/snapshots/<snapshot_id>/`并有SHA256。注册不可覆盖，不可把今日重新计算包装成今日新增采集。

每期保留采集日期、来源与范围、公司、完成度和失败、解析器及词典版本。`retrieved_at`、官网`posted_date`和处理时间分别保留。岗位跨期使用公司与原始source_job_id匹配；首次看到不是首次发布，未重现不是下架，原文哈希变化也不必然代表任职技能变化。

`data/processing-registry.json`按词典版本登记完整处理文件，`data/processing_versions/<version>/`冻结词典与提取脚本，文件SHA与规范词典SHA均保留。当前`data/technology/`是便于使用的索引/证据副本；未来更新它时，已登记的历史处理版本仍须保留。

跨期工具会输出整体、共同公司、共同职位的技术提及数、可用资格分母和百分点差，并保留同岗技术新增/移除。词典版本不同禁止直接比较；应使用同一版本重提取历史原文，再登记可比较的处理产物。具体命令和范围限制见`MAINTENANCE.md`。

原子技术总表与默认比较使用全部记录口径，包含已标记的2条毕业生招聘池；原子统计JSON另列具体职位口径。高级研究原有结论排除这2条，不能混用分母。需要调整记录类型、城市规则或解析范围时，用明确范围的派生登记簿保存新产物并保留原始归档。
