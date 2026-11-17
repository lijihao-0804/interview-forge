#!/usr/bin/env python3
"""Immutable job-snapshot registration and cohort-aware comparison (v4).

This script uses only the Python standard library. Snapshot artifacts are stored
under the directory containing --registry; source files are read-only inputs.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - supported Python versions include zoneinfo
    ZoneInfo = None  # type: ignore[assignment]


REGISTRY_SCHEMA = "employment-snapshot-registry-v4"
MANIFEST_SCHEMA = "employment-snapshot-manifest-v4"
COMPARE_SCHEMA = "employment-snapshot-comparison-v4"
CONTRACT_VERSION = "4.0.0"


def now_iso() -> str:
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
        except Exception:
            pass
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def write_json(path: Path, value: Any) -> bytes:
    data = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.write_bytes(data)
    return data


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def file_is_gzip(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(2) == b"\x1f\x8b"


def archive_corpus(source: Path, target: Path) -> tuple[str, str]:
    """Write an immutable .gz archive; return source and archived encodings."""
    if file_is_gzip(source):
        shutil.copyfile(source, target)
        return "gzip_ndjson", sha256_file(target)
    with source.open("rb") as in_stream, target.open("wb") as raw_out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_out, mtime=0) as gzip_out:
            shutil.copyfileobj(in_stream, gzip_out, length=1024 * 1024)
    return "ndjson_gzipped_for_archive", sha256_file(target)


def require_date(text: str) -> str:
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"snapshot date must be YYYY-MM-DD: {text}") from exc
    return text


def safe_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"artifact path must stay inside longitudinal root: {path}") from exc


def resolve_inside(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"registered path escapes longitudinal root: {relative}") from exc
    return candidate


def iter_corpus(path: Path) -> Iterable[dict[str, Any]]:
    opener = gzip.open if file_is_gzip(path) else open
    with opener(path, "rt", encoding="utf-8") as stream:  # type: ignore[arg-type]
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid corpus JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"corpus line {line_number} must be a JSON object")
            yield row


def get_identity(row: dict[str, Any]) -> tuple[str, str] | None:
    company = str(row.get("company") or "").strip()
    source_id = str(row.get("source_job_id") or "").strip()
    if not company or not source_id:
        return None
    return company, source_id


def text_hash(row: dict[str, Any]) -> tuple[str | None, str]:
    if isinstance(row.get("_text_hash"), str) and row.get("_text_hash"):
        return str(row["_text_hash"]), str(row.get("_text_hash_source") or "computed_at_registration")
    existing = row.get("text_sha256")
    if isinstance(existing, str) and existing.strip():
        return existing.strip().lower(), "text_sha256"
    body = row.get("full_text") or row.get("description")
    if isinstance(body, str) and body:
        return sha256_bytes(body.encode("utf-8")), "computed_full_text"
    return None, "unavailable"


def qualification_hash(row: dict[str, Any]) -> tuple[str | None, str]:
    if isinstance(row.get("_qualification_hash"), str) and row.get("_qualification_hash"):
        return str(row["_qualification_hash"]), str(row.get("_qualification_hash_source") or "requirements")
    raw = row.get("requirements")
    field = "requirements"
    if raw is None or raw == "":
        raw = row.get("requirements_analysis")
        field = "requirements_analysis_fallback"
    if raw is None or raw == "":
        return None, "unavailable"
    data = raw.encode("utf-8") if isinstance(raw, str) else canonical_bytes(raw)
    return sha256_bytes(data), field


def scan_corpus(path: Path, city_tags_by_id: dict[str, list[str]] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    counts: Counter[str] = Counter()
    companies: Counter[str] = Counter()
    source_types: Counter[str] = Counter()
    archive_statuses: Counter[str] = Counter()
    parse_statuses: Counter[str] = Counter()
    retrieval_dates: list[str] = []
    identities: Counter[tuple[str, str]] = Counter()
    summarized: list[dict[str, Any]] = []
    observed_ids: set[str] = set()
    for row in iter_corpus(path):
        counts["records"] += 1
        company = str(row.get("company") or "未知").strip() or "未知"
        companies[company] += 1
        source_types[str(row.get("source_type") or "未知")] += 1
        archive_statuses[str(row.get("archive_status") or "未知")] += 1
        parse_statuses[str(row.get("requirements_parse_status") or "未知")] += 1
        if get_identity(row) is None:
            counts["missing_company_or_source_id"] += 1
        else:
            identities[get_identity(row)] += 1  # type: ignore[index]
        body = row.get("full_text") or row.get("description")
        if isinstance(body, str) and body.strip():
            counts["body_count"] += 1
        if row.get("requirements_available") is True:
            counts["requirements_available_count"] += 1
        raw_time = row.get("retrieved_at")
        if isinstance(raw_time, str) and raw_time:
            retrieval_dates.append(raw_time)
        digest, digest_source = text_hash(row)
        qualification_digest, qualification_source = qualification_hash(row)
        record_id = str(row.get("id") or "")
        if record_id:
            observed_ids.add(record_id)
        row_city_tags = row.get("city_tags")
        if not isinstance(row_city_tags, list) and city_tags_by_id is not None:
            row_city_tags = city_tags_by_id.get(record_id, [])
        if isinstance(row_city_tags, list) and row_city_tags:
            counts["city_tagged_records"] += 1
        summarized.append({
            "company": company,
            "source_job_id": str(row.get("source_job_id") or "").strip(),
            "id": record_id,
            "title": str(row.get("title") or ""),
            "title_direction": str(row.get("title_direction") or ""),
            "job_family": str(row.get("job_family") or ""),
            "city": row.get("city"),
            "city_tags": row_city_tags,
            "geography": row.get("geography"),
            "_text_hash": digest,
            "_text_hash_source": digest_source,
            "_qualification_hash": qualification_digest,
            "_qualification_hash_source": qualification_source,
            "requirements_available": row.get("requirements_available"),
            "requirements_parse_status": row.get("requirements_parse_status"),
            "skills_in_requirement": row.get("skills_in_requirement"),
        })
    if city_tags_by_id is not None:
        absent_city_tags = observed_ids - set(city_tags_by_id)
        extra_city_tags = set(city_tags_by_id) - observed_ids
        if absent_city_tags or extra_city_tags:
            raise ValueError(f"city catalog identity mismatch: missing={len(absent_city_tags)}, extra={len(extra_city_tags)}")
        counts["city_tag_catalog_id_count"] = len(city_tags_by_id)
    counts["unique_company_source_ids"] = sum(1 for _, n in identities.items() if n == 1)
    counts["duplicate_company_source_id_keys"] = sum(1 for _, n in identities.items() if n > 1)
    counts["duplicate_rows_over_unique_keys"] = sum(n - 1 for n in identities.values() if n > 1)
    stats = {
        "counts": dict(counts),
        "company_counts": dict(sorted(companies.items())),
        "source_type_counts": dict(sorted(source_types.items())),
        "archive_status_counts": dict(sorted(archive_statuses.items())),
        "requirements_parse_status_counts": dict(sorted(parse_statuses.items())),
        "retrieved_at_min": min(retrieval_dates) if retrieval_dates else None,
        "retrieved_at_max": max(retrieval_dates) if retrieval_dates else None,
    }
    return stats, summarized


def load_city_catalog(path: Path) -> tuple[dict[str, list[str]], dict[str, Any]]:
    value = read_json(path)
    mapping: dict[str, list[str]] = {}
    jobs = value.get("jobs") if isinstance(value, dict) else None
    archived = value.get("by_job_id") if isinstance(value, dict) else None
    if isinstance(jobs, list):
        for row in jobs:
            if not isinstance(row, dict) or not row.get("id"):
                raise ValueError("each city catalog row requires id")
            ident = str(row["id"])
            if ident in mapping:
                raise ValueError(f"duplicate id in city catalog: {ident}")
            tags = row.get("city_tags", [])
            if not isinstance(tags, list):
                raise ValueError(f"city_tags must be an array for catalog id {ident}")
            mapping[ident] = [str(tag) for tag in tags if tag is not None and str(tag).strip()]
        source_format = "v3_catalog_jobs"
        derivation = "Copied from the v3 catalog city_tags field, originally computed only from the source city field using its embedded alias map."
        origin_catalog_sha256 = sha256_file(path)
    elif isinstance(archived, dict):
        for ident, tags in archived.items():
            if not isinstance(tags, list):
                raise ValueError(f"city_tags must be an array for archived id {ident}")
            mapping[str(ident)] = [str(tag) for tag in tags if tag is not None and str(tag).strip()]
        source_format = "frozen_city_tags_by_job_id"
        derivation = str(value.get("derivation") or "Reused frozen city_tags mapping from an earlier snapshot; not recomputed.")
        origin_catalog_sha256 = str(value.get("source_catalog_sha256") or "") or None
    else:
        raise ValueError("city catalog must be v3 jobs[] or frozen city-tags.json by_job_id{}")
    return mapping, {"record_count": len(mapping), "input_sha256": sha256_file(path),
                     "origin_catalog_sha256": origin_catalog_sha256,
                     "bytes": path.stat().st_size, "source_format": source_format,
                     "derivation": derivation}


def validate_technology_index(index: Any) -> dict[str, Any]:
    if not isinstance(index, dict):
        raise ValueError("technology index must be a JSON object")
    version = index.get("dictionary_version")
    terms = index.get("terms")
    jobs = index.get("jobs")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("technology index requires dictionary_version")
    if not isinstance(terms, list) or not isinstance(jobs, dict):
        raise ValueError("technology index requires terms[] and jobs{}")
    term_ids: set[str] = set()
    for term in terms:
        if not isinstance(term, dict) or not term.get("id") or not term.get("name"):
            raise ValueError("each technology term needs id and name")
        ident = str(term["id"])
        if ident in term_ids:
            raise ValueError(f"duplicate technology term id: {ident}")
        term_ids.add(ident)
    checked_jobs = 0
    for job_id, entry in jobs.items():
        if not isinstance(entry, dict):
            raise ValueError(f"technology jobs[{job_id!r}] must be an object")
        for facet in ("requirement", "duty", "fulltext"):
            values = entry.get(facet, [])
            if not isinstance(values, list):
                raise ValueError(f"technology jobs[{job_id!r}].{facet} must be an array")
            normalized_values = [str(value) for value in values]
            if len(normalized_values) != len(set(normalized_values)):
                raise ValueError(f"technology jobs[{job_id!r}].{facet} contains duplicate term IDs")
            unknown = set(normalized_values) - term_ids
            if unknown:
                raise ValueError(f"unknown technology term ids for job {job_id}: {sorted(unknown)[:5]}")
        checked_jobs += 1
    declared_rule_hashes: dict[str, str] = {}
    for field in ("dictionary_sha256", "rules_sha256", "extractor_sha256", "parser_sha256"):
        value = index.get(field)
        if value is not None:
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
                raise ValueError(f"technology index {field} must be a 64-character SHA256 when provided")
            declared_rule_hashes[field] = value.lower()
    index_snapshot_date = index.get("snapshot_date")
    if index_snapshot_date is not None:
        require_date(str(index_snapshot_date))
    index_source_hash = index.get("source_corpus_sha256")
    if index_source_hash is not None and (not isinstance(index_source_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", index_source_hash)):
        raise ValueError("technology index source_corpus_sha256 must be a 64-character SHA256 when provided")
    return {
        "dictionary_version": version,
        "term_count": len(terms),
        "job_entry_count": checked_jobs,
        "terms_sha256": sha256_bytes(canonical_bytes(terms)),
        "declared_rule_hashes": declared_rule_hashes,
        "extractor_version": index.get("extractor_version"),
        "index_parser_version": index.get("parser_version"),
        "snapshot_date": index_snapshot_date,
        "source_corpus_sha256": index_source_hash.lower() if isinstance(index_source_hash, str) else None,
    }


def technology_fingerprint(index: dict[str, Any], metadata: dict[str, Any], *, require_extractor: bool = True) -> dict[str, Any]:
    """Combine index-declared provenance with snapshot metadata provenance."""
    result = validate_technology_index(index)
    index_version = result["extractor_version"]
    metadata_version = metadata.get("technology_extractor_version")
    if index_version and metadata_version and index_version != metadata_version:
        raise ValueError("technology extractor_version in index and metadata disagree")
    extractor_version = index_version or metadata_version
    rule_hashes = dict(result["declared_rule_hashes"])
    metadata_hash_fields = {
        "technology_dictionary_sha256": "dictionary_sha256",
        "technology_rules_sha256": "rules_sha256",
        "technology_extractor_sha256": "extractor_sha256",
        "technology_parser_sha256": "parser_sha256",
    }
    for metadata_field, index_field in metadata_hash_fields.items():
        metadata_hash = metadata.get(metadata_field)
        if metadata_hash is None:
            continue
        if not isinstance(metadata_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", metadata_hash):
            raise ValueError(f"metadata {metadata_field} must be a 64-character SHA256")
        metadata_hash = metadata_hash.lower()
        if rule_hashes.get(index_field) and rule_hashes[index_field] != metadata_hash:
            raise ValueError(f"technology {index_field} in index and metadata disagree")
        rule_hashes[index_field] = metadata_hash
    if not extractor_version and rule_hashes.get("extractor_sha256"):
        extractor_version = "sha256:" + rule_hashes["extractor_sha256"]
    if require_extractor and not extractor_version:
        raise ValueError("technology index requires extractor_version or metadata technology_extractor_version/SHA256")
    index_parser = result["index_parser_version"]
    metadata_parser = metadata.get("technology_index_parser_version")
    if index_parser and metadata_parser and index_parser != metadata_parser:
        raise ValueError("technology index parser_version in index and metadata disagree")
    return {
        **result,
        "declared_rule_hashes": rule_hashes,
        "extractor_version": extractor_version,
        "index_parser_version": index_parser or metadata_parser,
    }


def verify_technology_source(index: dict[str, Any], snapshot_date: str, source_corpus_sha256: str) -> None:
    index_date = index.get("snapshot_date")
    if index_date is not None and index_date != snapshot_date:
        raise ValueError(f"technology index snapshot_date mismatch: expected {snapshot_date}, got {index_date}")
    index_corpus_hash = index.get("source_corpus_sha256")
    if index_corpus_hash is not None and str(index_corpus_hash).lower() != source_corpus_sha256.lower():
        raise ValueError("technology index source_corpus_sha256 does not match the input corpus hash")


def verify_technology_job_ids(rows: list[dict[str, Any]], index: dict[str, Any]) -> None:
    corpus_ids = [str(row.get("id") or "") for row in rows]
    if any(not ident for ident in corpus_ids) or len(corpus_ids) != len(set(corpus_ids)):
        raise ValueError("technology index requires unique, non-empty corpus job id values")
    corpus_id_set = set(corpus_ids)
    technology_id_set = {str(key) for key in index["jobs"]}
    missing_index = corpus_id_set - technology_id_set
    extra_index = technology_id_set - corpus_id_set
    if missing_index or extra_index:
        raise ValueError(f"technology index job IDs must exactly match corpus IDs: missing={len(missing_index)}, extra={len(extra_index)}")


def registry_initial() -> dict[str, Any]:
    return {
        "schema_version": REGISTRY_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "generated_at": now_iso(),
        "snapshot_count": 0,
        "snapshots": {},
        "notes": [
            "Snapshots are immutable after registration; a registered date cannot be overwritten.",
            "A prior job absent from a later observed scope is not evidence that the job was closed.",
        ],
    }


def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return registry_initial()
    value = read_json(path)
    if not isinstance(value, dict) or value.get("schema_version") != REGISTRY_SCHEMA:
        raise ValueError(f"unsupported snapshot registry schema at {path}")
    if not isinstance(value.get("snapshots"), dict):
        raise ValueError("registry snapshots must be an object keyed by YYYY-MM-DD")
    return value


def skill_vector_for(row: dict[str, Any], index: dict[str, Any] | None, strategy: str) -> set[str] | None:
    if strategy == "technology_requirement":
        if index is None or row.get("requirements_available") is not True:
            return None
        entry = index.get("jobs", {}).get(str(row.get("id") or ""))
        if not isinstance(entry, dict) or not isinstance(entry.get("requirement"), list):
            return None
        return {str(value) for value in entry["requirement"]}
    if row.get("requirements_available") is not True:
        return None
    skills = row.get("skills_in_requirement")
    if not isinstance(skills, list):
        return None
    return {str(value) for value in skills if value is not None and str(value)}


def term_names(index: dict[str, Any] | None, strategy: str, rows: Iterable[dict[str, Any]]) -> dict[str, str]:
    if strategy == "technology_requirement" and index is not None:
        return {str(term["id"]): str(term["name"]) for term in index["terms"]}
    values = {str(skill) for row in rows for skill in (row.get("skills_in_requirement") or [])}
    return {value: value for value in values}


def vector_rates(
    rows: list[dict[str, Any]], index: dict[str, Any] | None, strategy: str,
    names: dict[str, str],
) -> dict[str, Any]:
    n = 0
    qs: Counter[str] = Counter()
    for row in rows:
        vector = skill_vector_for(row, index, strategy)
        if vector is None:
            continue
        n += 1
        qs.update(vector)
    skills = []
    for ident in sorted(names, key=lambda x: (names[x].casefold(), x)):
        q = qs.get(ident, 0)
        skills.append({"id": ident, "name": names[ident], "n": n, "q": q,
                       "prevalence": q / n if n else None})
    return {"n": n, "skills": skills}


def row_matches(row: dict[str, Any], companies: list[str], cities: list[str], directions: list[str]) -> bool:
    if companies and str(row.get("company") or "").casefold() not in {x.casefold() for x in companies}:
        return False
    if cities:
        raw_tags = row.get("city_tags")
        if isinstance(raw_tags, list):
            observed_cities = {str(tag).strip().casefold() for tag in raw_tags if str(tag).strip()}
        else:
            # Older corpora may lack city_tags. Fall back only to the source city
            # field; do not mine geography or job body text for city mentions.
            raw_city = row.get("city")
            values = raw_city if isinstance(raw_city, list) else re.split(r"[;,，、/|]+", str(raw_city or ""))
            observed_cities = {str(value).strip().casefold() for value in values if str(value).strip()}
        if not any(term.casefold() in observed_cities for term in cities):
            return False
    if directions:
        direction_text = " ".join(str(row.get(field) or "") for field in ("title_direction", "job_family", "title")).casefold()
        if not any(term.casefold() in direction_text for term in directions):
            return False
    return True


def stable_scope_signature(value: Any) -> Any:
    """Drop capture-time fields while retaining source/channel/filter changes."""
    volatile = {"observed_at_min", "observed_at_max", "retrieved_at_min", "retrieved_at_max",
                "captured_at", "collected_at", "access_time", "snapshot_date", "last_run_access_time"}
    if isinstance(value, dict):
        return {key: stable_scope_signature(item) for key, item in value.items() if key not in volatile}
    if isinstance(value, list):
        return [stable_scope_signature(item) for item in value]
    return value


def index_identity(rows: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], dict[str, Any]], set[tuple[str, str]], int]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    missing = 0
    for row in rows:
        key = get_identity(row)
        if key is None:
            missing += 1
            continue
        grouped[key].append(row)
    ambiguous = {key for key, values in grouped.items() if len(values) > 1}
    unique = {key: values[0] for key, values in grouped.items() if len(values) == 1}
    return unique, ambiguous, missing


def id_card(row: dict[str, Any]) -> dict[str, Any]:
    text_digest, digest_source = text_hash(row)
    return {
        "company": row.get("company"),
        "source_job_id": row.get("source_job_id"),
        "id": row.get("id"),
        "title": row.get("title"),
        "city": row.get("city"),
        "title_direction": row.get("title_direction"),
        "job_family": row.get("job_family"),
        "text_sha256": text_digest,
        "text_hash_source": digest_source,
    }


def compare_snapshots(
    before_meta: dict[str, Any], before_rows: list[dict[str, Any]], before_index: dict[str, Any] | None,
    after_meta: dict[str, Any], after_rows: list[dict[str, Any]], after_index: dict[str, Any] | None,
    *, companies: list[str] | None = None, cities: list[str] | None = None,
    directions: list[str] | None = None,
) -> dict[str, Any]:
    before_date, after_date = before_meta["snapshot_date"], after_meta["snapshot_date"]
    if before_date == after_date:
        raise ValueError("cannot compare a snapshot with itself; one real period is baseline only")
    if before_date > after_date:
        raise ValueError("compare dates must be chronological: --from earlier than --to")
    parser_before = before_meta.get("parser_version")
    parser_after = after_meta.get("parser_version")
    if not parser_before or parser_before != parser_after:
        raise ValueError("parser_version differs or is missing; re-extract both periods with one parser version")

    if before_index is not None and after_index is not None:
        b_tax = technology_fingerprint(before_index, before_meta)
        a_tax = technology_fingerprint(after_index, after_meta)
        if b_tax["dictionary_version"] != a_tax["dictionary_version"] or b_tax["terms_sha256"] != a_tax["terms_sha256"]:
            raise ValueError("technology dictionary mismatch; re-extract both periods using the same dictionary_version and terms")
        if b_tax["declared_rule_hashes"] != a_tax["declared_rule_hashes"]:
            raise ValueError("technology rule/dictionary hash mismatch; re-extract both periods using the same rule hashes")
        if b_tax["extractor_version"] != a_tax["extractor_version"] or b_tax["index_parser_version"] != a_tax["index_parser_version"]:
            raise ValueError("technology extractor/parser version mismatch; re-extract both periods with one version")
        strategy = "technology_requirement"
        dictionary_version = b_tax["dictionary_version"]
        before_skill_index, after_skill_index = before_index, after_index
    else:
        bver = before_meta.get("legacy_skill_dictionary_version")
        aver = after_meta.get("legacy_skill_dictionary_version")
        bhash = before_meta.get("legacy_skill_dictionary_sha256")
        ahash = after_meta.get("legacy_skill_dictionary_sha256")
        if not bver or bver != aver or not bhash or bhash != ahash:
            raise ValueError("legacy skills dictionary mismatch or missing; re-extract both periods using one dictionary")
        strategy = "legacy_skills_in_requirement_fallback"
        dictionary_version = bver
        before_skill_index = after_skill_index = None

    company_filters = list(companies or [])
    city_filters = list(cities or [])
    direction_filters = list(directions or [])
    before_selected = [r for r in before_rows if row_matches(r, company_filters, city_filters, direction_filters)]
    after_selected = [r for r in after_rows if row_matches(r, company_filters, city_filters, direction_filters)]
    bmap, bdup, bmissing = index_identity(before_selected)
    amap, adup, amissing = index_identity(after_selected)
    ambiguous = bdup | adup
    before_keys, after_keys = set(bmap) - ambiguous, set(amap) - ambiguous
    common_keys = sorted(before_keys & after_keys)
    newly_observed_keys = sorted(after_keys - before_keys)
    not_reappeared_keys = sorted(before_keys - after_keys)
    common_companies = sorted({key[0] for key in before_keys} & {key[0] for key in after_keys})
    before_common_company_rows = [r for r in before_selected if str(r.get("company") or "") in common_companies]
    after_common_company_rows = [r for r in after_selected if str(r.get("company") or "") in common_companies]
    before_common_rows = [bmap[key] for key in common_keys]
    after_common_rows = [amap[key] for key in common_keys]

    names = term_names(before_skill_index, strategy, before_selected)
    if strategy == "technology_requirement":
        names.update(term_names(after_skill_index, strategy, after_selected))
    else:
        names.update(term_names(None, strategy, after_selected))

    full_before_rates = vector_rates(before_selected, before_skill_index, strategy, names)
    full_after_rates = vector_rates(after_selected, after_skill_index, strategy, names)
    company_before_rates = vector_rates(before_common_company_rows, before_skill_index, strategy, names)
    company_after_rates = vector_rates(after_common_company_rows, after_skill_index, strategy, names)

    paired_vectors: list[tuple[dict[str, Any], dict[str, Any], set[str], set[str]]] = []
    for key in common_keys:
        br, ar = bmap[key], amap[key]
        bv = skill_vector_for(br, before_skill_index, strategy)
        av = skill_vector_for(ar, after_skill_index, strategy)
        if bv is not None and av is not None:
            paired_vectors.append((br, ar, bv, av))
    common_n = len(paired_vectors)
    before_q: Counter[str] = Counter()
    after_q: Counter[str] = Counter()
    for _, _, bv, av in paired_vectors:
        before_q.update(bv)
        after_q.update(av)
    common_skill_metrics = []
    for ident in sorted(names, key=lambda x: (names[x].casefold(), x)):
        bq, aq = before_q.get(ident, 0), after_q.get(ident, 0)
        brate = bq / common_n if common_n else None
        arate = aq / common_n if common_n else None
        common_skill_metrics.append({
            "id": ident, "name": names[ident], "n": common_n,
            "q_before": bq, "q_after": aq,
            "rate_before": brate, "rate_after": arate,
            "change_percentage_points": (arate - brate) * 100 if common_n else None,
        })

    changed_jobs: list[dict[str, Any]] = []
    text_changed_count = 0
    qualification_changed_count = 0
    for key in common_keys:
        br, ar = bmap[key], amap[key]
        bh, bsrc = text_hash(br)
        ah, asrc = text_hash(ar)
        text_changed = bh is not None and ah is not None and bh != ah
        if text_changed:
            text_changed_count += 1
        bqh, bqsrc = qualification_hash(br)
        aqh, aqsrc = qualification_hash(ar)
        qualification_changed = bqh is not None and aqh is not None and bqh != aqh
        if qualification_changed:
            qualification_changed_count += 1
        bv = skill_vector_for(br, before_skill_index, strategy)
        av = skill_vector_for(ar, after_skill_index, strategy)
        added = sorted(av - bv) if bv is not None and av is not None else []
        removed = sorted(bv - av) if bv is not None and av is not None else []
        changed_jobs.append({
            "company": key[0], "source_job_id": key[1],
            "id_before": br.get("id"), "id_after": ar.get("id"),
            "title_before": br.get("title"), "title_after": ar.get("title"),
            "text_changed": text_changed if bh is not None and ah is not None else None,
            "text_sha256_before": bh, "text_sha256_after": ah,
            "text_hash_source_before": bsrc, "text_hash_source_after": asrc,
            "qualification_changed": qualification_changed if bqh is not None and aqh is not None else None,
            "qualification_sha256_before": bqh, "qualification_sha256_after": aqh,
            "qualification_hash_source_before": bqsrc, "qualification_hash_source_after": aqsrc,
            "requirement_terms_added": added, "requirement_terms_removed": removed,
            "requirement_terms_comparable": bv is not None and av is not None,
        })

    before_company_counts = Counter(str(r.get("company") or "未知") for r in before_selected)
    after_company_counts = Counter(str(r.get("company") or "未知") for r in after_selected)
    common_company_counts = [
        {"company": company,
         "records_before": sum(1 for r in before_common_company_rows if r.get("company") == company),
         "records_after": sum(1 for r in after_common_company_rows if r.get("company") == company),
         "matched_jobs": sum(1 for key in common_keys if key[0] == company)}
        for company in common_companies
    ]

    def rates_as_map(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {entry["id"]: entry for entry in value["skills"]}

    full_b, full_a = rates_as_map(full_before_rates), rates_as_map(full_after_rates)
    comp_b, comp_a = rates_as_map(company_before_rates), rates_as_map(company_after_rates)
    all_term_ids = sorted(names, key=lambda x: (names[x].casefold(), x))

    def cohort_rate_series(bmap_rates: dict[str, dict[str, Any]], amap_rates: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        values = []
        for ident in all_term_ids:
            bentry, aentry = bmap_rates.get(ident), amap_rates.get(ident)
            bq = int((bentry or {}).get("q", 0)); bn = int((bentry or {}).get("n", 0))
            aq = int((aentry or {}).get("q", 0)); an = int((aentry or {}).get("n", 0))
            brate = bq / bn if bn else None
            arate = aq / an if an else None
            values.append({"id": ident, "name": names[ident],
                           "n_before": bn, "q_before": bq, "rate_before": brate,
                           "n_after": an, "q_after": aq, "rate_after": arate,
                           "change_percentage_points": (arate - brate) * 100 if brate is not None and arate is not None else None})
        return values

    before_scope = before_meta.get("scope", {})
    after_scope = after_meta.get("scope", {})
    before_company_scope = sorted(str(x) for x in before_meta.get("company_scope", []))
    after_company_scope = sorted(str(x) for x in after_meta.get("company_scope", []))
    scope_changed = (canonical_bytes(stable_scope_signature(before_scope)) != canonical_bytes(stable_scope_signature(after_scope))
                     or before_company_scope != after_company_scope)
    before_completeness = before_meta.get("collection_completeness", {})
    after_completeness = after_meta.get("collection_completeness", {})
    limitations = [
        "未在本次快照出现只表示当前采集范围未观察到；不能据此推断岗位已下架。",
        "技能 n/q 的共同职位序列使用两期都具备资格段技能向量的共同职位；未能解析的资格文本不进入 n，也不记作无技能。",
        "全样本和共同公司序列的职位构成会变动，应结合固定共同职位序列解释百分点。",
    ]
    if scope_changed:
        limitations.append("两期 scope 元数据不同；全样本/共同公司指标受范围变化影响。")
    if before_completeness != after_completeness:
        limitations.append("两期采集完整度或失败摘要不同；缺页和访问失败不按零岗位处理。")
    if ambiguous:
        limitations.append("重复 company+source_job_id 键在本次匹配中排除，避免误配。")

    return {
        "schema_version": COMPARE_SCHEMA,
        "generated_at": now_iso(),
        "from_snapshot": {"snapshot_date": before_date, "manifest_sha256": before_meta.get("manifest_sha256")},
        "to_snapshot": {"snapshot_date": after_date, "manifest_sha256": after_meta.get("manifest_sha256")},
        "synthetic_fixture": bool(before_meta.get("synthetic_fixture") or after_meta.get("synthetic_fixture")),
        "filters": {"company_exact": company_filters, "city_tags_exact": city_filters,
                    "direction_contains": direction_filters},
        "matching_key": ["company", "source_job_id"],
        "parser_version": parser_before,
        "skill_method": {"name": strategy, "dictionary_version": dictionary_version,
                         "technology_terms_sha256": (technology_fingerprint(before_skill_index, before_meta)["terms_sha256"]
                                                      if strategy == "technology_requirement" and before_skill_index else None),
                         "technology_rule_hashes": (technology_fingerprint(before_skill_index, before_meta)["declared_rule_hashes"]
                                                    if strategy == "technology_requirement" and before_skill_index else None),
                         "technology_extractor_version": (technology_fingerprint(before_skill_index, before_meta)["extractor_version"]
                                                          if strategy == "technology_requirement" and before_skill_index else None),
                         "technology_index_parser_version": (technology_fingerprint(before_skill_index, before_meta)["index_parser_version"]
                                                              if strategy == "technology_requirement" and before_skill_index else None)},
        "scope": {
            "changed": scope_changed,
            "company_scope_from": before_company_scope,
            "company_scope_to": after_company_scope,
            "from": before_scope,
            "to": after_scope,
            "collection_completeness_from": before_completeness,
            "collection_completeness_to": after_completeness,
        },
        "populations": {
            "full_sample": {
                "records_before": len(before_selected), "records_after": len(after_selected),
                "company_counts_before": dict(sorted(before_company_counts.items())),
                "company_counts_after": dict(sorted(after_company_counts.items())),
                "skills_before": full_before_rates, "skills_after": full_after_rates,
                "skill_prevalence_comparison": cohort_rate_series(full_b, full_a),
                "interpretation": "两个截面的各自筛选全集；n 可随正文覆盖率变化。",
            },
            "common_companies": {
                "companies": common_companies,
                "company_counts": common_company_counts,
                "records_before": len(before_common_company_rows), "records_after": len(after_common_company_rows),
                "skills_before": company_before_rates, "skills_after": company_after_rates,
                "skill_prevalence_comparison": cohort_rate_series(comp_b, comp_a),
                "interpretation": "仅限两期都有记录的公司，但职位构成和 n 仍会变化。",
            },
            "common_matched_jobs": {
                "matched_job_count": len(common_keys),
                "companies": common_companies,
                "companies_count": len(common_companies),
                "skills": common_skill_metrics,
                "skill_denominator_n": common_n,
                "interpretation": "按 company+source_job_id 匹配；技能 n 固定为两期资格技能向量都可用的共同职位数。",
            },
        },
        "job_changes": {
            "newly_observed_in_selected_scope_count": len(newly_observed_keys),
            "newly_observed_in_selected_scope": [id_card(amap[key]) for key in newly_observed_keys],
            "not_reappeared_in_selected_scope_count": len(not_reappeared_keys),
            "not_reappeared_in_selected_scope": [id_card(bmap[key]) for key in not_reappeared_keys],
            "common_count": len(common_keys),
            "full_text_changed_count": text_changed_count,
            "qualification_segment_changed_count": qualification_changed_count,
            "matched_job_changes": changed_jobs,
            "ambiguous_identity_key_count": len(ambiguous),
            "ambiguous_identity_keys": [{"company": k[0], "source_job_id": k[1]} for k in sorted(ambiguous)],
            "missing_identity_rows_before": bmissing,
            "missing_identity_rows_after": amissing,
        },
        "limitations": limitations,
    }


def create_snapshot_summary(manifest: dict[str, Any], rows: list[dict[str, Any]], technology: dict[str, Any] | None) -> dict[str, Any]:
    if technology is not None:
        index = technology
        taxonomy = technology_fingerprint(index, manifest)
        strategy = "technology_requirement"
        names = term_names(index, strategy, rows)
        rates = vector_rates(rows, index, strategy, names)
    else:
        index = None
        strategy = "legacy_skills_in_requirement_fallback"
        names = term_names(None, strategy, rows)
        rates = vector_rates(rows, None, strategy, names)
    company_counts = manifest["corpus_stats"]["company_counts"]
    return {
        "schema_version": "employment-snapshot-summary-v4",
        "snapshot_date": manifest["snapshot_date"],
        "registered_at": manifest["registered_at"],
        "is_baseline": manifest["is_baseline"],
        "synthetic_fixture": False,
        "summary_scope": "single_snapshot",
        "registered_period_count_at_creation": manifest["registered_period_count_at_creation"],
        "trend_available": False,
        "trend_note": "本summary只描述这一期，不含跨期趋势；跨期结果由compare命令单独生成。",
        "scope": manifest["scope"],
        "collection_completeness": manifest["collection_completeness"],
        "counts": manifest["corpus_stats"]["counts"],
        "company_count": len(company_counts),
        "company_counts": company_counts,
        "companies": sorted(company_counts),
        "source_type_counts": manifest["corpus_stats"]["source_type_counts"],
        "archive_status_counts": manifest["corpus_stats"]["archive_status_counts"],
        "requirements_parse_status_counts": manifest["corpus_stats"]["requirements_parse_status_counts"],
        "city_tags_source": manifest.get("city_tags_source"),
        "skill_baseline": {
            "method": strategy,
            "dictionary_version": (taxonomy["dictionary_version"] if technology is not None else manifest.get("legacy_skill_dictionary_version")),
            "n": rates["n"],
            "skills": rates["skills"],
            "note": "需求文本未归档或无法拆分的岗位不进入 n；技能提及不等于硬性门槛。",
        },
        "files": manifest["files"],
    }


def register(args: argparse.Namespace) -> dict[str, Any]:
    registry_path = Path(args.registry).resolve()
    registry_root = registry_path.parent
    registry_root.mkdir(parents=True, exist_ok=True)
    date = require_date(args.snapshot_date)
    source = Path(args.source_corpus).resolve()
    metadata_path = Path(args.metadata).resolve()
    metadata = read_json(metadata_path)
    if not isinstance(metadata, dict):
        raise ValueError("snapshot metadata must be a JSON object")
    if metadata.get("snapshot_date") != date:
        raise ValueError("--snapshot-date does not match metadata.snapshot_date")
    if metadata.get("synthetic_fixture") is True:
        raise ValueError("synthetic fixtures are forbidden from the real snapshot registry")
    parser_version = metadata.get("parser_version")
    if not isinstance(parser_version, str) or not parser_version.strip():
        raise ValueError("metadata requires parser_version")
    if not isinstance(metadata.get("scope"), dict) or not isinstance(metadata.get("collection_completeness"), dict):
        raise ValueError("metadata requires scope and collection_completeness objects")
    legacy_version = metadata.get("legacy_skill_dictionary_version")
    legacy_hash = metadata.get("legacy_skill_dictionary_sha256")
    if legacy_version and (not isinstance(legacy_hash, str) or len(legacy_hash) != 64):
        raise ValueError("legacy_skill_dictionary_version requires a SHA256")
    if not source.is_file():
        raise FileNotFoundError(f"source corpus not found: {source}")
    source_hash = sha256_file(source)
    expected_corpus_hash = metadata.get("source_corpus_sha256")
    if expected_corpus_hash and source_hash != expected_corpus_hash:
        raise ValueError(f"source corpus hash mismatch: expected {expected_corpus_hash}, got {source_hash}")

    city_catalog_path = Path(args.city_catalog).resolve() if args.city_catalog else None
    city_tags_by_id: dict[str, list[str]] | None = None
    city_catalog_stats: dict[str, Any] | None = None
    if city_catalog_path is not None:
        city_tags_by_id, city_catalog_stats = load_city_catalog(city_catalog_path)
        expected_city_hash = metadata.get("city_catalog_sha256")
        if expected_city_hash and city_catalog_stats["input_sha256"] != expected_city_hash:
            raise ValueError(f"city catalog hash mismatch: expected {expected_city_hash}, got {city_catalog_stats['input_sha256']}")

    technology_path = Path(args.technology_index).resolve() if args.technology_index else None
    technology: dict[str, Any] | None = None
    technology_stats: dict[str, Any] | None = None
    if technology_path is not None:
        technology = read_json(technology_path)
        technology_stats = technology_fingerprint(technology, metadata)
        verify_technology_source(technology, date, source_hash)

    stats, rows = scan_corpus(source, city_tags_by_id)
    if technology is not None:
        verify_technology_job_ids(rows, technology)
    declared_counts = metadata.get("expected_counts", {})
    for field, actual_key in (("record_count", "records"), ("body_count", "body_count"),
                              ("requirements_available_count", "requirements_available_count")):
        expected = declared_counts.get(field) if isinstance(declared_counts, dict) else None
        actual = stats["counts"].get(actual_key, 0)
        if expected is not None and expected != actual:
            raise ValueError(f"metadata expected_counts.{field}={expected}, corpus has {actual}")

    lock_path = registry_root / ".snapshot-registry-v4.lock"
    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"another registry operation holds {lock_path}; inspect before removing a stale lock") from exc
    os.close(lock_fd)
    stage: Path | None = None
    try:
        registry = load_registry(registry_path)
        if date in registry["snapshots"]:
            raise FileExistsError(f"snapshot {date} is already registered; snapshots cannot be overwritten")
        snapshot_parent = (registry_root / args.archive_subdir).resolve()
        safe_relative(snapshot_parent, registry_root)
        snapshot_parent.mkdir(parents=True, exist_ok=True)
        final_dir = snapshot_parent / date
        if final_dir.exists():
            raise FileExistsError(f"snapshot archive already exists: {final_dir}; refusing overwrite")
        stage = Path(tempfile.mkdtemp(prefix=f".staging-{date}-", dir=snapshot_parent))
        corpus_target = stage / "corpus.ndjson.gz"
        corpus_encoding, archived_corpus_hash = archive_corpus(source, corpus_target)
        if file_is_gzip(source) and archived_corpus_hash != source_hash:
            raise IOError("gzip corpus archive copy did not preserve source SHA256")
        files: dict[str, Any] = {
            "corpus": {"path": "corpus.ndjson.gz", "bytes": corpus_target.stat().st_size,
                       "sha256": archived_corpus_hash, "source_sha256": source_hash,
                       "source_encoding": corpus_encoding}
        }
        if technology_path is not None and technology is not None:
            target = stage / "technology-index.json"
            shutil.copyfile(technology_path, target)
            technology_file_hash = sha256_file(target)
            files["technology_index"] = {
                "path": "technology-index.json", "bytes": target.stat().st_size,
                "sha256": technology_file_hash,
                "dictionary_version": technology_stats["dictionary_version"],
                "terms_sha256": technology_stats["terms_sha256"],
                "term_count": technology_stats["term_count"],
                "job_entry_count": technology_stats["job_entry_count"],
                "declared_rule_hashes": technology_stats["declared_rule_hashes"],
                "extractor_version": technology_stats["extractor_version"],
                "index_parser_version": technology_stats["index_parser_version"],
            }
        city_tags_info = None
        if city_tags_by_id is not None and city_catalog_stats is not None:
            city_archive = {
                "schema_version": "employment-city-tags-v1",
                "source_catalog_sha256": city_catalog_stats["origin_catalog_sha256"],
                "source_mapping_input_sha256": city_catalog_stats["input_sha256"],
                "source_catalog_record_count": city_catalog_stats["record_count"],
                "source_catalog_format": city_catalog_stats["source_format"],
                "derivation": city_catalog_stats["derivation"],
                "by_job_id": city_tags_by_id,
            }
            city_bytes = json.dumps(city_archive, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
            (stage / "city-tags.json").write_bytes(city_bytes)
            city_tags_info = {
                "path": "city-tags.json", "bytes": len(city_bytes), "sha256": sha256_bytes(city_bytes),
                "source_catalog_sha256": city_catalog_stats["origin_catalog_sha256"],
                "source_mapping_input_sha256": city_catalog_stats["input_sha256"],
                "source_catalog_record_count": city_catalog_stats["record_count"],
                "source_catalog_format": city_catalog_stats["source_format"],
                "derivation": city_catalog_stats["derivation"],
            }
            files["city_tags"] = city_tags_info
        counts = stats["counts"]
        source_provenance = metadata.get("upstream_provenance", {})
        manifest = {
            "schema_version": MANIFEST_SCHEMA,
            "contract_version": CONTRACT_VERSION,
            "snapshot_date": date,
            "timezone": metadata.get("timezone", "Asia/Shanghai"),
            "registered_at": now_iso(),
            "is_baseline": len(registry["snapshots"]) == 0,
            "registered_period_count_at_creation": len(registry["snapshots"]) + 1,
            "synthetic_fixture": False,
            "parser_version": parser_version,
            "legacy_skill_dictionary_version": legacy_version,
            "legacy_skill_dictionary_sha256": legacy_hash,
            "technology_dictionary_version": technology_stats["dictionary_version"] if technology_stats else None,
            "technology_terms_sha256": technology_stats["terms_sha256"] if technology_stats else None,
            "technology_declared_rule_hashes": technology_stats["declared_rule_hashes"] if technology_stats else None,
            "technology_dictionary_sha256": (technology_stats["declared_rule_hashes"].get("dictionary_sha256") if technology_stats else None),
            "technology_rules_sha256": (technology_stats["declared_rule_hashes"].get("rules_sha256") if technology_stats else None),
            "technology_extractor_version": technology_stats["extractor_version"] if technology_stats else None,
            "technology_extractor_sha256": (technology_stats["declared_rule_hashes"].get("extractor_sha256") if technology_stats else None),
            "technology_parser_sha256": (technology_stats["declared_rule_hashes"].get("parser_sha256") if technology_stats else None),
            "technology_index_parser_version": technology_stats["index_parser_version"] if technology_stats else None,
            "technology_index_snapshot_date": technology_stats["snapshot_date"] if technology_stats else None,
            "technology_index_source_corpus_sha256": technology_stats["source_corpus_sha256"] if technology_stats else None,
            "city_tags_source": ({"method": ("v3 catalog city_tags copied to city-tags.json" if city_catalog_stats["source_format"] == "v3_catalog_jobs" else "previous frozen city_tags mapping reused without recomputation"),
                                  "source_catalog_sha256": city_catalog_stats["origin_catalog_sha256"],
                                  "source_mapping_input_sha256": city_catalog_stats["input_sha256"],
                                  "source_catalog_record_count": city_catalog_stats["record_count"],
                                  "source_catalog_format": city_catalog_stats["source_format"],
                                  "derivation": city_catalog_stats["derivation"],
                                  "source_name": metadata.get("city_catalog_source_name", city_catalog_path.name if city_catalog_path else "catalog.json"),
                                  "source_path_is_linkable": False}
                                 if city_catalog_stats else None),
            "scope": metadata["scope"],
            "collection_completeness": metadata["collection_completeness"],
            "failures": metadata.get("failures", []),
            "company_scope": metadata.get("company_scope", sorted(stats["company_counts"])),
            "upstream_provenance": source_provenance,
            "registration_metadata": {"source_name": metadata_path.name,
                                      "sha256": sha256_file(metadata_path),
                                      "path_is_linkable": False},
            "source_corpus": {"sha256": source_hash, "bytes": source.stat().st_size,
                              "source_encoding": corpus_encoding, "source_path_is_linkable": False},
            "corpus_stats": stats,
            "files": files,
        }
        summary = create_snapshot_summary(manifest, rows, technology)
        summary_bytes = write_json(stage / "summary.json", summary)
        files["summary"] = {"path": "summary.json", "bytes": len(summary_bytes), "sha256": sha256_bytes(summary_bytes)}
        manifest["files"] = files
        manifest_bytes = write_json(stage / "manifest.json", manifest)
        manifest_hash = sha256_bytes(manifest_bytes)
        archived_corpus_bytes = corpus_target.stat().st_size

        os.rename(stage, final_dir)
        stage = None
        entry = {
            "snapshot_date": date,
            "synthetic_fixture": False,
            "is_baseline": manifest["is_baseline"],
            "manifest": {"path": safe_relative(final_dir / "manifest.json", registry_root), "sha256": manifest_hash},
            "summary": {"path": safe_relative(final_dir / "summary.json", registry_root),
                        "sha256": files["summary"]["sha256"]},
            "corpus": {"path": safe_relative(final_dir / "corpus.ndjson.gz", registry_root),
                       "sha256": archived_corpus_hash, "bytes": archived_corpus_bytes,
                       "source_sha256": source_hash, "source_encoding": corpus_encoding},
            "technology_index": ({"path": safe_relative(final_dir / "technology-index.json", registry_root),
                                  "sha256": files["technology_index"]["sha256"],
                                  "dictionary_version": technology_stats["dictionary_version"],
                                  "terms_sha256": technology_stats["terms_sha256"],
                                  "declared_rule_hashes": technology_stats["declared_rule_hashes"],
                                  "extractor_version": technology_stats["extractor_version"],
                                  "extractor_sha256": technology_stats["declared_rule_hashes"].get("extractor_sha256"),
                                  "index_parser_version": technology_stats["index_parser_version"],
                                  "snapshot_date": technology_stats["snapshot_date"],
                                  "source_corpus_sha256": technology_stats["source_corpus_sha256"]}
                                 if technology_stats else None),
            "city_tags": ({"path": safe_relative(final_dir / "city-tags.json", registry_root),
                           "sha256": city_tags_info["sha256"],
                           "source_catalog_sha256": city_catalog_stats["origin_catalog_sha256"],
                           "source_mapping_input_sha256": city_catalog_stats["input_sha256"]}
                          if city_tags_info and city_catalog_stats else None),
            "record_count": counts.get("records", 0),
            "company_count": len(stats["company_counts"]),
            "parser_version": parser_version,
            "technology_dictionary_version": technology_stats["dictionary_version"] if technology_stats else None,
            "legacy_skill_dictionary_version": legacy_version,
        }
        registry["snapshots"][date] = entry
        registry["snapshot_count"] = len(registry["snapshots"])
        registry["generated_at"] = now_iso()
        payload = json.dumps(registry, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        temp_registry = registry_root / f".registry-{os.getpid()}-{date}.tmp"
        with temp_registry.open("xb") as stream:
            stream.write(payload)
        os.replace(temp_registry, registry_path)
        return {"registry": str(registry_path), "snapshot_date": date,
                "manifest": str(final_dir / "manifest.json"), "summary": str(final_dir / "summary.json"),
                "source_corpus_sha256": source_hash, "archived_corpus_sha256": archived_corpus_hash,
                "record_count": counts.get("records", 0),
                "technology_dictionary_version": technology_stats["dictionary_version"] if technology_stats else None}
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def load_registered_snapshot(registry_path: Path, registry: dict[str, Any], date: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    entry = registry["snapshots"].get(date)
    if not isinstance(entry, dict):
        raise KeyError(f"snapshot date not found in registry: {date}")
    if entry.get("synthetic_fixture") is True:
        raise ValueError("synthetic fixture cannot be loaded through the real snapshot registry")
    root = registry_path.parent.resolve()
    manifest_path = resolve_inside(root, entry["manifest"]["path"])
    actual_manifest_hash = sha256_file(manifest_path)
    if actual_manifest_hash != entry["manifest"].get("sha256"):
        raise ValueError(f"manifest SHA256 mismatch for {date}")
    manifest = read_json(manifest_path)
    if manifest.get("snapshot_date") != date or manifest.get("synthetic_fixture") is True:
        raise ValueError(f"snapshot manifest identity mismatch for {date}")
    summary_ref = entry.get("summary")
    if not isinstance(summary_ref, dict):
        raise ValueError(f"summary reference missing for {date}")
    summary_path = resolve_inside(root, summary_ref["path"])
    if sha256_file(summary_path) != summary_ref.get("sha256"):
        raise ValueError(f"summary SHA256 mismatch for {date}")
    manifest_summary = manifest.get("files", {}).get("summary", {})
    if manifest_summary.get("sha256") != summary_ref.get("sha256"):
        raise ValueError(f"summary registry/manifest hash mismatch for {date}")
    corpus_info = manifest.get("files", {}).get("corpus")
    if not isinstance(corpus_info, dict):
        raise ValueError(f"corpus file missing from manifest for {date}")
    corpus_path = resolve_inside(manifest_path.parent, corpus_info["path"])
    registered_corpus_path = resolve_inside(root, entry.get("corpus", {}).get("path", ""))
    if registered_corpus_path != corpus_path:
        raise ValueError(f"corpus registry/manifest path mismatch for {date}")
    corpus_hash = sha256_file(corpus_path)
    if corpus_hash != corpus_info.get("sha256") or corpus_hash != entry.get("corpus", {}).get("sha256"):
        raise ValueError(f"corpus SHA256 mismatch for {date}")
    city_tags_by_id = None
    city_info = manifest.get("files", {}).get("city_tags")
    if city_info:
        city_path = resolve_inside(manifest_path.parent, city_info["path"])
        if sha256_file(city_path) != city_info.get("sha256"):
            raise ValueError(f"city-tags SHA256 mismatch for {date}")
        city_archive = read_json(city_path)
        if city_archive.get("schema_version") != "employment-city-tags-v1" or not isinstance(city_archive.get("by_job_id"), dict):
            raise ValueError(f"city-tags archive schema mismatch for {date}")
        city_tags_by_id = city_archive["by_job_id"]
    _, rows = scan_corpus(corpus_path, city_tags_by_id)
    technology: dict[str, Any] | None = None
    tech_info = manifest.get("files", {}).get("technology_index")
    registered_tech = entry.get("technology_index")
    if tech_info:
        tech_path = resolve_inside(manifest_path.parent, tech_info["path"])
        if not isinstance(registered_tech, dict) or resolve_inside(root, registered_tech.get("path", "")) != tech_path:
            raise ValueError(f"technology index registry/manifest path mismatch for {date}")
        if sha256_file(tech_path) != tech_info.get("sha256"):
            raise ValueError(f"technology index SHA256 mismatch for {date}")
        technology = read_json(tech_path)
        validate_technology_index(technology)
        verify_technology_source(technology, date, manifest.get("source_corpus", {}).get("sha256", ""))
    elif registered_tech is not None:
        raise ValueError(f"technology index registry/manifest presence mismatch for {date}")
    if tech_info and registered_tech.get("sha256") != tech_info.get("sha256"):
        raise ValueError(f"technology index registry/manifest hash mismatch for {date}")
    city_info = manifest.get("files", {}).get("city_tags")
    registered_city = entry.get("city_tags")
    if city_info:
        city_path = resolve_inside(manifest_path.parent, city_info["path"])
        if not isinstance(registered_city, dict) or resolve_inside(root, registered_city.get("path", "")) != city_path:
            raise ValueError(f"city-tags registry/manifest path mismatch for {date}")
        if registered_city.get("sha256") != city_info.get("sha256"):
            raise ValueError(f"city-tags registry/manifest hash mismatch for {date}")
    elif registered_city is not None:
        raise ValueError(f"city-tags registry/manifest presence mismatch for {date}")
    meta = dict(manifest)
    meta["manifest_sha256"] = actual_manifest_hash
    return meta, rows, technology


def compare_command(args: argparse.Namespace) -> dict[str, Any]:
    registry_path = Path(args.registry).resolve()
    registry = load_registry(registry_path)
    before_date, after_date = require_date(args.from_date), require_date(args.to_date)
    before_meta, before_rows, before_index = load_registered_snapshot(registry_path, registry, before_date)
    after_meta, after_rows, after_index = load_registered_snapshot(registry_path, registry, after_date)
    report = compare_snapshots(before_meta, before_rows, before_index,
                               after_meta, after_rows, after_index,
                               companies=args.company, cities=args.city, directions=args.direction)
    output = Path(args.output).resolve() if args.output else None
    if output:
        # Reports are confined to the longitudinal directory too.
        safe_relative(output, registry_path.parent)
        if output.exists() and not args.replace_report:
            raise FileExistsError(f"report exists; use --replace-report to replace a comparison report: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_name(output.name + f".{os.getpid()}.tmp")
        with temp.open("xb") as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
        os.replace(temp, output)
        report["report_path"] = safe_relative(output, registry_path.parent)
    return report


def synthetic_self_test() -> dict[str, Any]:
    """Run two temporary synthetic periods; never writes to a real registry."""
    terms = [
        {"id": "py", "name": "Python", "category": "lang", "aliases": ["Python"]},
        {"id": "sql", "name": "SQL", "category": "data", "aliases": ["SQL"]},
    ]
    def job(company: str, source_id: str, ident: str, city: str, direction: str,
            body: str, req: str, sha_suffix: str) -> dict[str, Any]:
        return {"company": company, "source_job_id": source_id, "id": ident,
                "title": f"{direction} Engineer", "title_direction": direction,
                "job_family": direction, "city": city, "city_tags": [city], "full_text": body,
                "text_sha256": sha256_bytes((body + sha_suffix).encode()),
                "requirements": req, "requirements_available": True,
                "skills_in_requirement": ["Python"] if "Python" in req else (["SQL"] if "SQL" in req else [])}
    before_rows = [
        job("Acme", "1", "a1", "北京", "backend", "old footer A", "Need Python", "A"),
        job("Acme", "2", "a2", "北京", "backend", "stable", "Need SQL", "B"),
        job("Acme", "10", "a10", "深圳", "frontend", "gone", "Need SQL", "C"),
        job("Beta", "9", "b9", "北京", "backend", "other company", "Need Python", "D"),
    ]
    after_rows = [
        job("Acme", "1", "a1", "北京", "backend", "new footer B", "Need Python", "E"),
        job("Acme", "2", "a2", "北京", "backend", "stable", "Need SQL and Python", "F"),
        job("Acme", "3", "a3", "深圳", "backend", "new role", "Need Python", "G"),
    ]
    before_index = {"dictionary_version": "fixture-tech-v1", "terms": terms,
                    "jobs": {"a1": {"requirement": ["py"], "duty": [], "fulltext": []},
                             "a2": {"requirement": ["sql"], "duty": [], "fulltext": []},
                             "a10": {"requirement": ["sql"], "duty": [], "fulltext": []},
                             "b9": {"requirement": ["py"], "duty": [], "fulltext": []}}}
    after_index = {"dictionary_version": "fixture-tech-v1", "terms": terms,
                   "jobs": {"a1": {"requirement": ["py"], "duty": [], "fulltext": []},
                            "a2": {"requirement": ["sql", "py"], "duty": [], "fulltext": []},
                            "a3": {"requirement": ["py"], "duty": [], "fulltext": []}}}
    before_source_hash = sha256_bytes("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in before_rows).encode("utf-8"))
    after_source_hash = sha256_bytes("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in after_rows).encode("utf-8"))
    before_index.update({"snapshot_date": "2026-01-01", "source_corpus_sha256": before_source_hash})
    after_index.update({"snapshot_date": "2026-02-01", "source_corpus_sha256": after_source_hash})
    verify_technology_job_ids(before_rows, before_index)
    verify_technology_source(before_index, "2026-01-01", before_source_hash)
    try:
        verify_technology_job_ids(before_rows, {**before_index, "jobs": {**before_index["jobs"], "extra": {"requirement": [], "duty": [], "fulltext": []}}})
    except ValueError as exc:
        if "exactly match" not in str(exc):
            raise
    else:
        raise AssertionError("technology index job-ID mismatch should be rejected")
    try:
        verify_technology_source(before_index, "2026-02-01", before_source_hash)
    except ValueError as exc:
        if "snapshot_date mismatch" not in str(exc):
            raise
    else:
        raise AssertionError("technology index snapshot date mismatch should be rejected")
    try:
        verify_technology_source(before_index, "2026-01-01", "f" * 64)
    except ValueError as exc:
        if "source_corpus_sha256" not in str(exc):
            raise
    else:
        raise AssertionError("technology index source corpus mismatch should be rejected")
    metadata = lambda date: {"snapshot_date": date, "parser_version": "fixture-parser-v1",
                             "technology_extractor_version": "fixture-extractor-v1",
                             "technology_extractor_sha256": "0" * 64,
                             "scope": {"companies": ["Acme", "Beta"]},
                             "collection_completeness": {"fixture": True},
                             "synthetic_fixture": True}
    # Exercise the same gzip NDJSON reader shape inside a temporary fixture directory.
    with tempfile.TemporaryDirectory(prefix="snapshot-v4-fixture-") as tmp:
        fixture = Path(tmp)
        for name, rows in (("before", before_rows), ("after", after_rows)):
            with gzip.open(fixture / f"{name}.ndjson.gz", "wt", encoding="utf-8") as stream:
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            loaded = list(iter_corpus(fixture / f"{name}.ndjson.gz"))
            if len(loaded) != len(rows):
                raise AssertionError("fixture gzip row count mismatch")
        plain_path = fixture / "plain.ndjson"
        plain_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in before_rows), encoding="utf-8")
        plain_archive = fixture / "plain-archived.ndjson.gz"
        encoding, archived_hash = archive_corpus(plain_path, plain_archive)
        if encoding != "ndjson_gzipped_for_archive" or sha256_file(plain_archive) != archived_hash:
            raise AssertionError("plain NDJSON archive metadata/hash failed")
        with gzip.open(plain_archive, "rt", encoding="utf-8") as stream:
            if sum(1 for line in stream if line.strip()) != len(before_rows):
                raise AssertionError("plain NDJSON gzip archive row count failed")
    report = compare_snapshots(metadata("2026-01-01"), before_rows, before_index,
                               metadata("2026-02-01"), after_rows, after_index,
                               companies=["Acme"], cities=["北京"], directions=["backend"])
    changes = report["job_changes"]
    if (changes["common_count"] != 2 or changes["newly_observed_in_selected_scope_count"] != 0
            or changes["not_reappeared_in_selected_scope_count"] != 0):
        raise AssertionError("city/direction filters or matched identity counts failed")
    matched = {(x["company"], x["source_job_id"]): x for x in changes["matched_job_changes"]}
    if not matched[("Acme", "1")]["text_changed"] or matched[("Acme", "1")]["qualification_changed"]:
        raise AssertionError("footer-only full text change must not mark qualification changed")
    if matched[("Acme", "2")]["requirement_terms_added"] != ["py"]:
        raise AssertionError("requirement term additions failed")
    py_metric = next(x for x in report["populations"]["common_matched_jobs"]["skills"] if x["id"] == "py")
    if py_metric["n"] != 2 or py_metric["q_before"] != 1 or py_metric["q_after"] != 2 or py_metric["change_percentage_points"] != 50.0:
        raise AssertionError("common-cohort n/q percentage-point result failed")
    mismatch = dict(after_index)
    mismatch["dictionary_version"] = "fixture-tech-v2"
    try:
        compare_snapshots(metadata("2026-01-01"), before_rows, before_index,
                          metadata("2026-02-01"), after_rows, mismatch)
    except ValueError as exc:
        if "dictionary mismatch" not in str(exc):
            raise
    else:
        raise AssertionError("technology dictionary mismatch should be rejected")
    try:
        compare_snapshots(metadata("2026-01-01"), before_rows, before_index,
                          metadata("2026-01-01"), before_rows, before_index)
    except ValueError as exc:
        if "itself" not in str(exc):
            raise
    else:
        raise AssertionError("single-period comparison should be rejected")
    return {"status": "PASS", "synthetic_fixture": True,
            "real_registry_writes": 0, "matched_jobs": 2,
            "technology_added_term_case": "Acme/2 added Python (py)",
            "footer_only_change_case": "full_text changed, qualification hash unchanged",
            "skill_case": "Python n=2, q=1→2, +50.0 percentage points",
            "plain_ndjson_archive": "gzip output and row count verified",
            "technology_id_date_and_source_hash_mismatch": "rejected",
            "dictionary_mismatch": "rejected", "same_period": "rejected"}


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("register", help="register a real, immutable snapshot")
    reg.add_argument("--registry", required=True, help="longitudinal/registry.json")
    reg.add_argument("--source-corpus", required=True, help="source NDJSON or gzip NDJSON corpus")
    reg.add_argument("--metadata", required=True, help="snapshot metadata JSON with scope and completeness")
    reg.add_argument("--snapshot-date", required=True, help="observed snapshot date, YYYY-MM-DD")
    reg.add_argument("--technology-index", help="optional technology-index.json with requirement term IDs")
    reg.add_argument("--city-catalog", help="optional v3 catalog.json or frozen city-tags.json; freeze only id→city_tags mapping")
    reg.add_argument("--archive-subdir", default="snapshots", help="archive directory relative to registry parent")
    reg.set_defaults(func=register)
    cmp = sub.add_parser("compare", help="compare two real registered snapshots")
    cmp.add_argument("--registry", required=True)
    cmp.add_argument("--from", dest="from_date", required=True)
    cmp.add_argument("--to", dest="to_date", required=True)
    cmp.add_argument("--company", action="append", default=[], help="exact company filter; repeatable")
    cmp.add_argument("--city", action="append", default=[], help="exact city_tags filter (legacy fallback: exact source city value); repeatable")
    cmp.add_argument("--direction", action="append", default=[], help="substring filter over title_direction/job_family/title; repeatable")
    cmp.add_argument("--output", help="comparison JSON under the longitudinal root")
    cmp.add_argument("--replace-report", action="store_true", help="allow replacing an existing comparison report only")
    cmp.set_defaults(func=compare_command)
    test = sub.add_parser("self-test", help="run isolated synthetic two-period checks; no real registry writes")
    test.set_defaults(func=lambda _args: synthetic_self_test())
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
