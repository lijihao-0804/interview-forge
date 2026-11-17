# Employment Data Bundle v3 schema

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
