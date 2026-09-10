"""Deterministic, read-only learning analytics for InterviewForge.

This module deliberately does not import the web server, the authentication
database, an LLM SDK, or any optional dependency.  It reads only the learning
tables from the database supplied by the caller and returns JSON-compatible
plain Python values.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCHEMA_VERSION = "analytics-v1"
RULE_VERSION = "rules-v1"
ANALYTICS_DB_TIMEOUT_SECONDS = 0.25
ANALYTICS_BUSY_TIMEOUT_MS = 250


class AnalyticsUnavailableError(RuntimeError):
    """Transient analytics read failure suitable for an HTTP 503 response."""

    retryable = True

    def __init__(self, message: str = "learning analytics is temporarily unavailable"):
        super().__init__(message)
        self.status_code = 503

# These are intentionally ordinary dictionaries.  A caller may copy and
# override them for a controlled experiment without changing the module's
# defaults or the meaning of an existing rule_version.
DEFAULT_RULE_CONFIG: dict[str, Any] = {
    "rule_version": RULE_VERSION,
    "repeat_wa_min": 3,
    "wa_after_ac_high_min_30d": 2,
    "view_without_ac_min_views_30d": 3,
    "view_without_ac_min_days_30d": 2,
    "stalled_module_days": 14,
    "stalled_module_high_days": 30,
    "relearn_overdue_days": 60,
    "due_medium_max_days": 7,
    "too_few_attempts": 3,
    "mixed_source_window_seconds": 300,
    "curriculum_round_threshold": 90,
}

DEFAULT_LIMITS: dict[str, int] = {
    "max_signals": 500,
    "max_evidence": 500,
    "max_problem_metrics": 1000,
    "max_module_metrics": 1000,
    "max_content_metrics": 5000,
    "max_evidence_event_ids": 10,
}

PROBLEM_REVIEW_INTERVALS = (1, 3, 7, 15, 30, 60)
CONTENT_REVIEW_INTERVALS = (3, 7, 15, 30, 60, 90)

# The names and IDs are the phase-0 coarse mapping.  Unknown catalog
# categories are intentionally left unmapped; the analyzer must not guess.
CATEGORY_SKILL_IDS: dict[str, str] = {
    "哈希表": "algo.hash-table",
    "双指针": "algo.two-pointers",
    "滑动窗口": "algo.sliding-window",
    "子串": "algo.substring",
    "普通数组": "algo.array",
    "矩阵": "algo.matrix",
    "链表": "algo.linked-list",
    "二叉树": "algo.binary-tree",
    "图论": "algo.graph",
    "回溯": "algo.backtracking",
    "二分查找": "algo.binary-search",
    "栈": "algo.stack",
    "堆": "algo.heap",
    "贪心": "algo.greedy",
    "动态规划": "algo.dynamic-programming",
    "多维动态规划": "algo.multidimensional-dp",
    "技巧": "algo.techniques",
}

ALLOWED_SUBMISSION_SOURCES = {"manual", "bookmarklet", "extension", "sync"}
ALLOWED_STATUSES = {"ac", "wa"}


def _json_default(value: Any) -> Any:
    """Return a safe representation for snapshot hashing only."""

    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    return str(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _short_hash(value: Any, length: int = 16) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()[:length]


def _safe_int(value: Any, default: int | None = None) -> int | None:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _merge_config(
    defaults: Mapping[str, Any], overrides: Mapping[str, Any] | None, *, name: str
) -> dict[str, Any]:
    result = dict(defaults)
    if overrides is None:
        return result
    if not isinstance(overrides, Mapping):
        raise TypeError(f"{name} must be a mapping")
    for key, value in overrides.items():
        if key not in result:
            raise ValueError(f"unknown {name} key: {key}")
        result[key] = value
    return result


def _normalize_rule_config(rule_config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Accept the flat public config and a small, explicit nested alias."""

    if rule_config is None:
        return dict(DEFAULT_RULE_CONFIG)
    if not isinstance(rule_config, Mapping):
        raise TypeError("rule_config must be a mapping")
    flattened: dict[str, Any] = {}
    for key, value in rule_config.items():
        if isinstance(value, Mapping) and key in {
            "repeat_wa",
            "wa_after_ac",
            "view_without_ac",
            "stalled_module",
            "data_insufficient",
        }:
            aliases = {
                ("repeat_wa", "min_wa"): "repeat_wa_min",
                ("wa_after_ac", "high_min_30d"): "wa_after_ac_high_min_30d",
                ("view_without_ac", "min_views_30d"): "view_without_ac_min_views_30d",
                ("view_without_ac", "min_days_30d"): "view_without_ac_min_days_30d",
                ("stalled_module", "days"): "stalled_module_days",
                ("stalled_module", "high_days"): "stalled_module_high_days",
                ("data_insufficient", "min_attempts"): "too_few_attempts",
            }
            for nested_key, nested_value in value.items():
                flattened[aliases.get((key, nested_key), nested_key)] = nested_value
        else:
            flattened[key] = value
    normalized = _merge_config(DEFAULT_RULE_CONFIG, flattened, name="rule_config")
    rule_version = _safe_text(normalized.get("rule_version")).strip()
    if not rule_version:
        raise ValueError("rule_config.rule_version cannot be empty")
    normalized["rule_version"] = rule_version
    rule_spec = {
        key: normalized[key]
        for key in sorted(normalized)
        if key != "rule_version"
    }
    default_rule_spec = {
        key: DEFAULT_RULE_CONFIG[key]
        for key in sorted(DEFAULT_RULE_CONFIG)
        if key != "rule_version"
    }
    if rule_spec != default_rule_spec:
        # The semantic rule specification, rather than a caller-supplied label,
        # determines the effective version.  This makes equivalent overrides
        # stable and prevents a threshold change from reusing old signal IDs.
        normalized["rule_version"] = (
            f"{rule_version}-{_short_hash(rule_spec, length=12)}"
        )
    return normalized


def _normalize_limits(limits: Mapping[str, Any] | None) -> dict[str, int]:
    merged = _merge_config(DEFAULT_LIMITS, limits, name="limits")
    normalized: dict[str, int] = {}
    for key, value in merged.items():
        number = _safe_int(value)
        if number is None or number < 0:
            raise ValueError(f"limits.{key} must be a non-negative integer")
        normalized[key] = number
    return normalized


def _resolve_as_of(as_of: Any, business_tz: ZoneInfo) -> datetime:
    if as_of is None:
        return datetime.now(business_tz).replace(microsecond=0)
    if isinstance(as_of, datetime):
        value = as_of
    elif isinstance(as_of, date):
        value = datetime.combine(as_of, datetime.min.time())
    elif isinstance(as_of, str):
        text = as_of.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            value = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("as_of must be an ISO date or datetime") from exc
    else:
        raise TypeError("as_of must be an ISO date, datetime, or ISO string")
    if value.tzinfo is None:
        value = value.replace(tzinfo=business_tz)
    return value.astimezone(business_tz)


def _parse_record_time(value: Any, business_tz: ZoneInfo) -> datetime | None:
    """Parse a stored timestamp without consulting the host OS timezone.

    Stored learning timestamps are required to carry an explicit offset.  A
    naive timestamp is therefore treated as invalid instead of silently
    inheriting a machine-specific timezone.
    """

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(business_tz)


def _event_key(event: Mapping[str, Any]) -> tuple[datetime, int]:
    return (event["dt"], _safe_int(event.get("id"), 0) or 0)


def _date_in_window(event_date: date, as_of_date: date, days: int) -> bool:
    return as_of_date - timedelta(days=days - 1) <= event_date <= as_of_date


def _interval(round_no: int, *, content: bool) -> int:
    intervals = CONTENT_REVIEW_INTERVALS if content else PROBLEM_REVIEW_INTERVALS
    index = min(max(int(round_no) - 1, 0), len(intervals) - 1)
    return intervals[index]


def _due_date(completed_at: datetime, round_no: int, *, content: bool) -> date:
    return completed_at.date() + timedelta(days=_interval(round_no, content=content))


def _normalize_problem_catalog(problem_catalog: Any) -> dict[int, dict[str, str]]:
    if isinstance(problem_catalog, Mapping):
        entries = list(problem_catalog.items())
    else:
        try:
            entries = [(None, item) for item in problem_catalog]
        except TypeError as exc:
            raise TypeError("problem_catalog must be a mapping or iterable") from exc

    result: dict[int, dict[str, str]] = {}
    for key, raw in entries:
        if not isinstance(raw, Mapping):
            raise ValueError("each problem catalog entry must be a mapping")
        pid = _safe_int(raw.get("id", key))
        if pid is None or pid < 0:
            raise ValueError("problem catalog entries need an integer id")
        if pid in result:
            raise ValueError(f"duplicate problem id: {pid}")
        result[pid] = {
            "title": _safe_text(raw.get("title")),
            "category": _safe_text(raw.get("category")),
            "difficulty": _safe_text(raw.get("difficulty")),
        }
    return dict(sorted(result.items()))


def _normalize_manifest(manifest: Any) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(manifest, Mapping):
        raise TypeError("manifest must be a mapping")
    raw_modules = manifest.get("modules", [])
    if raw_modules is None:
        raw_modules = []
    if not isinstance(raw_modules, (list, tuple)):
        raise ValueError("manifest.modules must be a list")

    modules: list[dict[str, Any]] = []
    content_index: dict[str, dict[str, Any]] = {}
    module_ids: set[str] = set()
    for raw_module in raw_modules:
        if not isinstance(raw_module, Mapping):
            raise ValueError("each manifest module must be a mapping")
        module_id = _safe_text(raw_module.get("id")).strip()
        if not module_id:
            raise ValueError("manifest module id cannot be empty")
        if module_id in module_ids:
            raise ValueError(f"duplicate module id: {module_id}")
        module_ids.add(module_id)
        raw_chapters = raw_module.get("chapters", [])
        if raw_chapters is None:
            raw_chapters = []
        if not isinstance(raw_chapters, (list, tuple)):
            raise ValueError(f"manifest chapters for {module_id} must be a list")

        chapters: list[dict[str, str]] = []
        for raw_chapter in raw_chapters:
            if not isinstance(raw_chapter, Mapping):
                raise ValueError(f"manifest chapter in {module_id} must be a mapping")
            content_id = _safe_text(raw_chapter.get("id")).strip()
            if not content_id:
                raise ValueError(f"manifest chapter in {module_id} has no id")
            if content_id in content_index:
                previous = content_index[content_id]["module_id"]
                raise ValueError(
                    f"duplicate content_id {content_id!r} in modules {previous!r} and {module_id!r}"
                )
            chapter = {
                "id": content_id,
                "title": _safe_text(raw_chapter.get("title")),
                "url": _safe_text(raw_chapter.get("url")),
            }
            chapters.append(chapter)
            content_index[content_id] = {
                "content_id": content_id,
                "module_id": module_id,
                "module_title": _safe_text(raw_module.get("title")),
                "title": chapter["title"],
            }
        modules.append(
            {
                "id": module_id,
                "title": _safe_text(raw_module.get("title")),
                "chapters": chapters,
            }
        )
    modules.sort(key=lambda item: item["id"])
    return modules, content_index


READ_TABLE_SCHEMAS: dict[str, dict[str, Any]] = {
    "study_events": {
        "core": ("id", "problem_id", "action", "studied_at"),
        "optional": {
            "study_date": "NULL",
            "round_no": "NULL",
            "source": "'learning-site'",
        },
    },
    "submissions": {
        "core": ("id", "problem_id", "status", "submitted_at"),
        "optional": {
            "lang": "''",
            "runtime_ms": "NULL",
            "memory_kb": "NULL",
            "source": "'manual'",
            "lc_id": "NULL",
        },
    },
    "content_events": {
        "core": ("id", "module_id", "content_id", "action", "studied_at"),
        "optional": {
            "study_date": "NULL",
            "round_no": "NULL",
        },
    },
    "marks": {
        "core": ("target_type", "target_id", "mark"),
        "optional": {"updated_at": "NULL"},
    },
}


def _is_lock_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "locked" in message or "busy" in message


def _raise_if_lock_error(exc: sqlite3.OperationalError) -> None:
    if _is_lock_error(exc):
        raise AnalyticsUnavailableError(
            "learning analytics database is locked; retry the read"
        ) from exc


def _resolve_db_path(db_path: Any, allowed_db_root: Any | None) -> Any:
    """Resolve and constrain a database path without weakening read-only mode."""

    if allowed_db_root is None:
        return db_path
    if isinstance(db_path, str) and db_path == ":memory:":
        raise ValueError(":memory: is not allowed with allowed_db_root")
    try:
        root_input = Path(allowed_db_root)
        db_input = Path(db_path)
    except TypeError as exc:
        raise TypeError("db_path and allowed_db_root must be path-like") from exc
    if ".." in db_input.parts:
        raise ValueError("db_path must not contain a parent traversal component")
    root = root_input.resolve()
    if not root.is_dir():
        raise ValueError("allowed_db_root must point to a directory")
    resolved_db = db_input.resolve()
    try:
        resolved_db.relative_to(root)
    except ValueError as exc:
        raise ValueError("db_path must resolve inside allowed_db_root") from exc
    return resolved_db


def _open_read_only(db_path: Any) -> sqlite3.Connection | None:
    """Open an existing SQLite file with short, query-only read settings."""

    connection: sqlite3.Connection | None = None
    try:
        if isinstance(db_path, str) and db_path == ":memory:":
            connection = sqlite3.connect(
                db_path,
                timeout=ANALYTICS_DB_TIMEOUT_SECONDS,
            )
        else:
            path = Path(db_path)
            if not path.exists():
                return None
            if not path.is_file():
                raise ValueError("db_path must point to an SQLite file")
            # Open in SQLite's URI mode=ro first, then keep query_only enabled
            # as a second guard.  This prevents an accidental schema/table
            # mutation even if this module is reused by a caller with a
            # writable file.
            connection = sqlite3.connect(
                path.resolve().as_uri() + "?mode=ro",
                uri=True,
                timeout=ANALYTICS_DB_TIMEOUT_SECONDS,
            )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {ANALYTICS_BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA query_only = ON")
        return connection
    except sqlite3.OperationalError as exc:
        if connection is not None:
            connection.close()
        _raise_if_lock_error(exc)
        raise


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    try:
        return (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            is not None
        )
    except sqlite3.OperationalError as exc:
        _raise_if_lock_error(exc)
        raise


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
    except sqlite3.OperationalError as exc:
        _raise_if_lock_error(exc)
        raise


def _quoted_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _read_compatible_rows(
    connection: sqlite3.Connection | None,
    table: str,
    quality: dict[str, Any],
) -> list[sqlite3.Row]:
    if connection is None:
        quality["missing_tables"].append(table)
        return []
    schema = READ_TABLE_SCHEMAS[table]
    if not _table_exists(connection, table):
        quality["missing_tables"].append(table)
        return []
    columns = _table_columns(connection, table)
    missing_core = [name for name in schema["core"] if name not in columns]
    if missing_core:
        quality["schema_incompatible_details"][table] = {
            "missing_core_columns": missing_core,
        }
        return []
    select_parts = [_quoted_identifier(name) for name in schema["core"]]
    for name, default_sql in schema["optional"].items():
        if name in columns:
            select_parts.append(_quoted_identifier(name))
        else:
            select_parts.append(f"{default_sql} AS {_quoted_identifier(name)}")
    try:
        return connection.execute(
            f"SELECT {', '.join(select_parts)} FROM {_quoted_identifier(table)}"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        _raise_if_lock_error(exc)
        raise


def _source_dict(values: Mapping[str, int]) -> dict[str, int]:
    """Return a bounded source histogram with one stable fallback bucket."""
    merged: defaultdict[str, int] = defaultdict(int)
    for key, value in values.items():
        source = str(key)
        bucket = source if source in ALLOWED_SUBMISSION_SOURCES else "other"
        merged[bucket] += int(value)
    return {key: merged[key] for key in sorted(merged)}


def _metric(
    *,
    metric_id: str,
    value: Any,
    unit: str,
    window: str,
    data_as_of: str,
    source: list[str] | tuple[str, ...],
    sample_count: int,
    confidence: str,
    confidence_reason: str,
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "value": value,
        "unit": unit,
        "window": window,
        "as_of": data_as_of,
        "source": sorted({str(item) for item in source}),
        "sample_count": int(sample_count),
        "confidence": confidence,
        "confidence_reason": confidence_reason,
    }


def _metric_id(entity_type: str, entity_id: Any, metric_name: str, window: str) -> str:
    return f"metric:{SCHEMA_VERSION}:{entity_type}:{entity_id}:{metric_name}:{window}"


def _add_metric(
    records: list[dict[str, Any]],
    ids: dict[str, str],
    *,
    entity_type: str,
    entity_id: Any,
    name: str,
    window: str,
    value: Any,
    unit: str,
    data_as_of: str,
    source: list[str] | tuple[str, ...],
    sample_count: int,
    confidence: str,
    confidence_reason: str,
) -> str:
    identifier = _metric_id(entity_type, entity_id, name, window)
    records.append(
        _metric(
            metric_id=identifier,
            value=value,
            unit=unit,
            window=window,
            data_as_of=data_as_of,
            source=source,
            sample_count=sample_count,
            confidence=confidence,
            confidence_reason=confidence_reason,
        )
    )
    ids[f"{name}.{window}"] = identifier
    return identifier


def _confidence(
    sample_count: int,
    *,
    quality_issue: bool = False,
    zero_reason: str = "no matching records",
    direct_reason: str = "directly counted from valid learning records",
) -> tuple[str, str]:
    if sample_count <= 0:
        return "insufficient", zero_reason
    if quality_issue:
        return "medium", "direct fact with timestamp or source-quality caveat"
    return "high", direct_reason


def _problem_skills(category: str) -> list[str]:
    skill_id = CATEGORY_SKILL_IDS.get(category)
    return [skill_id] if skill_id is not None else []


def _record_event(
    row: Mapping[str, Any],
    *,
    event_time_key: str,
    business_tz: ZoneInfo,
) -> dict[str, Any] | None:
    parsed = _parse_record_time(row[event_time_key], business_tz)
    if parsed is None:
        return None
    return {
        "id": _safe_int(row.get("id"), 0) or 0,
        "dt": parsed,
        "raw_time": _safe_text(row[event_time_key]),
        "row": dict(row),
    }


def _as_of_string(value: datetime) -> str:
    return value.isoformat()


def _signal_id(
    rule_version: str, signal_type: str, entity_type: str, entity_id: Any, window_end: str
) -> str:
    return f"signal:{rule_version}:{signal_type}:{entity_type}:{entity_id}:{window_end}"


def _evidence_id(snapshot_hash: str, source_table: str, fact: Mapping[str, Any]) -> str:
    return f"evidence:{snapshot_hash}:{source_table}:{_short_hash(fact)}"


def _event_ids(events: list[Mapping[str, Any]], limit: int) -> tuple[list[int], int]:
    ordered = sorted(events, key=_event_key, reverse=True)
    ids = [_safe_int(event.get("id"), 0) or 0 for event in ordered[:limit]]
    return ids, max(0, len(ordered) - len(ids))


def _due_severity(overdue_days: int, rules: Mapping[str, Any]) -> str:
    if overdue_days <= 0:
        return "low"
    if overdue_days <= int(rules["due_medium_max_days"]):
        return "medium"
    if overdue_days <= int(rules["relearn_overdue_days"]):
        return "high"
    return "relearn"


def _build_snapshot_hash(
    *,
    catalog: Mapping[int, Mapping[str, str]],
    modules: list[Mapping[str, Any]],
    raw_rows: Mapping[str, list[Mapping[str, Any]]],
    data_as_of: str,
    timezone_name: str,
    rules: Mapping[str, Any],
) -> str:
    normalized_modules = [
        {
            "id": module["id"],
            "chapters": [chapter["id"] for chapter in module.get("chapters", [])],
        }
        for module in modules
    ]
    normalized_catalog = [
        {"id": pid, **dict(catalog[pid])} for pid in sorted(catalog)
    ]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "rule_version": rules["rule_version"],
        "rules": dict(rules),
        "data_as_of": data_as_of,
        "timezone": timezone_name,
        "catalog": normalized_catalog,
        "modules": normalized_modules,
        "rows": {
            key: sorted(
                (dict(row) for row in rows),
                key=_canonical_json,
            )
            for key, rows in sorted(raw_rows.items())
        },
    }
    return _short_hash(payload, length=16)


def build_learning_analytics(
    db_path: Any,
    problem_catalog: Any,
    manifest: Mapping[str, Any],
    *,
    allowed_db_root: Any | None = None,
    as_of: Any = None,
    timezone_name: str = "Asia/Shanghai",
    rule_config: Mapping[str, Any] | None = None,
    limits: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic analytics-v1 snapshot from one learning DB.

    ``db_path`` must already be the current user's learning database path.  It
    is never used to infer a username, and this function never opens the
    account database or the credentials table.  The database is opened with
    SQLite's ``query_only`` setting and only SELECT statements are issued.

    Invalid event timestamps are counted and skipped from time-based facts;
    missing tables and an empty database return a normal, data-insufficient
    response rather than an exception.  A manifest with duplicate content IDs
    is a contract error and raises ``ValueError`` before analysis begins.  If
    ``allowed_db_root`` is supplied, the resolved database path must remain
    inside that resolved directory.
    """

    try:
        business_tz = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown timezone: {timezone_name}") from exc
    rules = _normalize_rule_config(rule_config)
    output_limits = _normalize_limits(limits)
    catalog = _normalize_problem_catalog(problem_catalog)
    modules, content_index = _normalize_manifest(manifest)
    as_of_dt = _resolve_as_of(as_of, business_tz)
    data_as_of = _as_of_string(as_of_dt)
    as_of_date = as_of_dt.date()

    quality: dict[str, Any] = {
        "invalid_timestamp_count": 0,
        "invalid_timestamp_by_table": {
            "study_events": 0,
            "submissions": 0,
            "content_events": 0,
            "marks": 0,
        },
        "future_event_count": 0,
        "future_event_by_table": {
            "study_events": 0,
            "submissions": 0,
            "content_events": 0,
        },
        "unknown_problem_count": 0,
        "unknown_content_count": 0,
        "orphan_content_count": 0,
        "legacy_complete_ignored_count": 0,
        "ignored_hot100_content_event_count": 0,
        "mixed_source_possible_duplicate_count": 0,
        "duplicate_lc_id_count": 0,
        "duplicate_sync_lc_id_count": 0,
        "invalid_status_count": 0,
        "invalid_source_count": 0,
        "other_source_count": 0,
        "unknown_mark_target_count": 0,
        "missing_tables": [],
        "schema_incompatible": False,
        "schema_incompatible_details": {},
        "table_row_counts": {},
        "omitted": {
            "signals": 0,
            "evidence": 0,
            "problem_metrics": 0,
            "module_metrics": 0,
            "content_metrics": 0,
            "evidence_event_ids": 0,
        },
        "limits": dict(output_limits),
        "read_only": True,
    }

    raw_rows: dict[str, list[Mapping[str, Any]]] = {}
    resolved_db_path = _resolve_db_path(db_path, allowed_db_root)
    connection = _open_read_only(resolved_db_path)
    try:
        raw_rows["study_events"] = [
            dict(row)
            for row in _read_compatible_rows(
                connection,
                "study_events",
                quality,
            )
        ]
        raw_rows["submissions"] = [
            dict(row)
            for row in _read_compatible_rows(
                connection,
                "submissions",
                quality,
            )
        ]
        raw_rows["content_events"] = [
            dict(row)
            for row in _read_compatible_rows(
                connection,
                "content_events",
                quality,
            )
        ]
        raw_rows["marks"] = [
            dict(row)
            for row in _read_compatible_rows(
                connection,
                "marks",
                quality,
            )
        ]
    finally:
        if connection is not None:
            connection.close()

    for table_name, rows in raw_rows.items():
        quality["table_row_counts"][table_name] = len(rows)
    quality["missing_tables"] = sorted(set(quality["missing_tables"]))

    if quality["schema_incompatible_details"]:
        quality["schema_incompatible"] = True
        quality["reason_codes"] = ["schema_incompatible"]
        quality["rule_config"] = dict(rules)
        quality["schema_incompatible_message"] = (
            "one or more learning tables are missing required core columns"
        )
        result = {
            "schema_version": SCHEMA_VERSION,
            "rule_version": str(rules["rule_version"]),
            "data_as_of": data_as_of,
            "timezone": timezone_name,
            "summary": {"metric_ids": {}, "metrics": []},
            "problem_metrics": [],
            "module_metrics": [],
            "signals": [],
            "evidence": [],
            "data_quality": quality,
        }
        json.dumps(result, ensure_ascii=False, sort_keys=True)
        return result

    valid_study_events: list[dict[str, Any]] = []
    problem_views: dict[int, list[dict[str, Any]]] = defaultdict(list)
    all_learning_events: list[dict[str, Any]] = []

    for raw in raw_rows["study_events"]:
        pid = _safe_int(raw.get("problem_id"))
        parsed = _record_event(raw, event_time_key="studied_at", business_tz=business_tz)
        if parsed is None:
            quality["invalid_timestamp_count"] += 1
            quality["invalid_timestamp_by_table"]["study_events"] += 1
            continue
        if parsed["dt"] > as_of_dt:
            quality["future_event_count"] += 1
            quality["future_event_by_table"]["study_events"] += 1
            continue
        if pid is None or pid not in catalog:
            quality["unknown_problem_count"] += 1
            continue
        action = _safe_text(raw.get("action")).lower()
        if action not in {"view", "complete"}:
            quality.setdefault("invalid_event_action_count", 0)
            quality["invalid_event_action_count"] += 1
            continue
        parsed["problem_id"] = pid
        parsed["action"] = action
        valid_study_events.append(parsed)
        all_learning_events.append(parsed)
        if action == "view":
            problem_views[pid].append(parsed)
        else:
            # This is retained as a historical learning event, but never as a
            # Hot100 round.  AC submissions are the only Hot100 round source.
            quality["legacy_complete_ignored_count"] += 1

    submissions_by_problem: dict[int, list[dict[str, Any]]] = defaultdict(list)
    valid_submissions: list[dict[str, Any]] = []
    lc_ids: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sync_lc_ids: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_pairs: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for raw in raw_rows["submissions"]:
        pid = _safe_int(raw.get("problem_id"))
        parsed = _record_event(raw, event_time_key="submitted_at", business_tz=business_tz)
        if parsed is None:
            quality["invalid_timestamp_count"] += 1
            quality["invalid_timestamp_by_table"]["submissions"] += 1
            continue
        if parsed["dt"] > as_of_dt:
            quality["future_event_count"] += 1
            quality["future_event_by_table"]["submissions"] += 1
            continue
        if pid is None or pid not in catalog:
            quality["unknown_problem_count"] += 1
            continue
        status = _safe_text(raw.get("status")).lower()
        if status not in ALLOWED_STATUSES:
            quality["invalid_status_count"] += 1
            continue
        raw_source = _safe_text(raw.get("source"), "unknown").strip() or "unknown"
        source = raw_source
        if source not in ALLOWED_SUBMISSION_SOURCES:
            quality["invalid_source_count"] += 1
            quality["other_source_count"] += 1
            source = "other"
        parsed.update({"problem_id": pid, "status": status, "source": source})
        valid_submissions.append(parsed)
        submissions_by_problem[pid].append(parsed)
        source_pairs[pid][source] += 1
        lc_id = _safe_text(raw.get("lc_id")).strip()
        if lc_id:
            lc_ids[lc_id].append(parsed)
            if source == "sync":
                sync_lc_ids[lc_id].append(parsed)
        all_learning_events.append(parsed)

    quality["duplicate_lc_id_count"] = sum(
        max(0, len(events) - 1) for events in lc_ids.values()
    )
    quality["duplicate_sync_lc_id_count"] = sum(
        max(0, len(events) - 1) for events in sync_lc_ids.values()
    )

    content_events_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    content_views_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    content_completes_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for raw in raw_rows["content_events"]:
        content_id = _safe_text(raw.get("content_id")).strip()
        module_id = _safe_text(raw.get("module_id")).strip()
        parsed = _record_event(raw, event_time_key="studied_at", business_tz=business_tz)
        if parsed is None:
            quality["invalid_timestamp_count"] += 1
            quality["invalid_timestamp_by_table"]["content_events"] += 1
            continue
        if parsed["dt"] > as_of_dt:
            quality["future_event_count"] += 1
            quality["future_event_by_table"]["content_events"] += 1
            continue
        metadata = content_index.get(content_id)
        if metadata is None or metadata["module_id"] != module_id:
            quality["unknown_content_count"] += 1
            quality["orphan_content_count"] += 1
            continue
        action = _safe_text(raw.get("action")).lower()
        if action not in {"view", "complete"}:
            quality.setdefault("invalid_event_action_count", 0)
            quality["invalid_event_action_count"] += 1
            continue
        parsed.update({"content_id": content_id, "module_id": module_id, "action": action})
        if module_id == "hot100":
            # The manifest may contain old mirrored events; current Hot100
            # progress is derived exclusively from submissions below.
            quality["ignored_hot100_content_event_count"] += 1
            continue
        content_events_by_id[content_id].append(parsed)
        if action == "view":
            content_views_by_id[content_id].append(parsed)
        else:
            content_completes_by_id[content_id].append(parsed)
        all_learning_events.append(parsed)

    marks: dict[tuple[str, str], str] = {}
    for raw in raw_rows["marks"]:
        updated_at_value = raw.get("updated_at")
        updated_at = (
            _parse_record_time(updated_at_value, business_tz)
            if updated_at_value is not None
            else None
        )
        if updated_at_value is not None and updated_at is None:
            quality["invalid_timestamp_count"] += 1
            quality["invalid_timestamp_by_table"]["marks"] += 1
        target_type = _safe_text(raw.get("target_type")).strip()
        target_id = _safe_text(raw.get("target_id")).strip()
        is_known = (
            target_type == "problem"
            and (_safe_int(target_id) in catalog if _safe_int(target_id) is not None else False)
        ) or (target_type == "content" and target_id in content_index)
        if not is_known:
            quality["unknown_mark_target_count"] += 1
            continue
        mark = _safe_text(raw.get("mark")).strip()
        if mark in {"mastered", "reviewing", "weak"}:
            marks[(target_type, target_id)] = mark

    # A manual/bookmarklet and a sync record close in time can describe one
    # real-world submission.  They remain separate facts in v1.  Use a
    # sorted sliding window: a large all-manual history must not become an
    # O(n^2) comparison merely because it has many rows.
    mixed_window = int(rules["mixed_source_window_seconds"])
    mixed_pair_count = 0
    mixed_problem_ids: set[int] = set()
    for pid, rows in submissions_by_problem.items():
        by_status: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_status[row["status"]].append(row)
        for status_rows in by_status.values():
            sync_rows = sorted(
                (row for row in status_rows if row["source"] == "sync"),
                key=_event_key,
            )
            other_rows = sorted(
                (row for row in status_rows if row["source"] != "sync"),
                key=_event_key,
            )
            if not sync_rows or not other_rows:
                continue
            left = 0
            right = 0
            for sync_row in sync_rows:
                lower = sync_row["dt"] - timedelta(seconds=mixed_window)
                upper = sync_row["dt"] + timedelta(seconds=mixed_window)
                while left < len(other_rows) and other_rows[left]["dt"] < lower:
                    left += 1
                if right < left:
                    right = left
                while right < len(other_rows) and other_rows[right]["dt"] <= upper:
                    right += 1
                if right > left:
                    mixed_pair_count += right - left
                    mixed_problem_ids.add(pid)
    quality["mixed_source_possible_duplicate_count"] = mixed_pair_count

    raw_rows_for_hash = {
        name: rows for name, rows in raw_rows.items() if name != "credentials"
    }
    snapshot_hash = _build_snapshot_hash(
        catalog=catalog,
        modules=modules,
        raw_rows=raw_rows_for_hash,
        data_as_of=data_as_of,
        timezone_name=timezone_name,
        rules=rules,
    )

    # Build per-problem facts and metric records.
    problem_states: dict[int, dict[str, Any]] = {}
    problem_metrics: list[dict[str, Any]] = []
    unmapped_problem_count = 0
    for pid, metadata in catalog.items():
        submissions = sorted(submissions_by_problem.get(pid, []), key=_event_key)
        views = sorted(problem_views.get(pid, []), key=_event_key)
        views_30d = [
            event for event in views if _date_in_window(event["dt"].date(), as_of_date, 30)
        ]
        view_days_30d = len({event["dt"].date() for event in views_30d})
        ac_events = [event for event in submissions if event["status"] == "ac"]
        wa_events = [event for event in submissions if event["status"] == "wa"]
        ac_events_desc = sorted(ac_events, key=_event_key, reverse=True)
        wa_events_desc = sorted(wa_events, key=_event_key, reverse=True)
        latest_submission = max(submissions, key=_event_key) if submissions else None
        latest_ac = ac_events_desc[0] if ac_events_desc else None
        latest_wa = wa_events_desc[0] if wa_events_desc else None
        ac_dates = {event["dt"].date() for event in ac_events}
        ac_30d = [
            event for event in ac_events if _date_in_window(event["dt"].date(), as_of_date, 30)
        ]
        wa_30d = [
            event for event in wa_events if _date_in_window(event["dt"].date(), as_of_date, 30)
        ]
        submit_30d = [
            event
            for event in submissions
            if _date_in_window(event["dt"].date(), as_of_date, 30)
        ]
        wa_after_latest_ac = (
            [event for event in wa_events if event["dt"] > latest_ac["dt"]]
            if latest_ac
            else []
        )
        wa_after_latest_ac_30d = [
            event
            for event in wa_after_latest_ac
            if _date_in_window(event["dt"].date(), as_of_date, 30)
        ]
        latest_activity = max(
            [*submissions, *views], key=_event_key
        ) if (submissions or views) else None
        mark = marks.get(("problem", str(pid)))
        skill_ids = _problem_skills(metadata["category"])
        if not skill_ids:
            unmapped_problem_count += 1
        entity_quality_issue = pid in mixed_problem_ids
        confidence, confidence_reason = _confidence(
            len(submissions) + len(views),
            quality_issue=entity_quality_issue,
            zero_reason="no valid submission or view records",
        )
        pass_rate = round(len(ac_events) / len(submissions), 3) if submissions else None
        due_date = (
            _due_date(latest_ac["dt"], len(ac_dates), content=False)
            if latest_ac
            else None
        )
        overdue_days = max(0, (as_of_date - due_date).days) if due_date else 0
        due = bool(due_date and due_date <= as_of_date)
        overdue = bool(due_date and due_date < as_of_date)
        mark_conflict = bool(mark == "mastered" and wa_after_latest_ac)

        records: list[dict[str, Any]] = []
        ids: dict[str, str] = {}
        sources_for_submissions = ["submissions"]
        views_sources = ["study_events"]
        _add_metric(
            records,
            ids,
            entity_type="problem",
            entity_id=pid,
            name="view_count",
            window="all",
            value=len(views),
            unit="views",
            data_as_of=data_as_of,
            source=views_sources,
            sample_count=len(views),
            confidence=_confidence(len(views), zero_reason="no valid view records")[0],
            confidence_reason=_confidence(len(views), zero_reason="no valid view records")[1],
        )
        for name, value in (("view_count", len(views_30d)), ("view_days", view_days_30d)):
            view_confidence, view_reason = _confidence(
                len(views_30d),
                zero_reason="no valid view records in the 30-day window",
            )
            _add_metric(
                records,
                ids,
                entity_type="problem",
                entity_id=pid,
                name=name,
                window="30d",
                value=value,
                unit="views" if name == "view_count" else "days",
                data_as_of=data_as_of,
                source=views_sources,
                sample_count=len(views_30d),
                confidence=view_confidence,
                confidence_reason=view_reason,
            )
        _add_metric(
            records,
            ids,
            entity_type="problem",
            entity_id=pid,
            name="view_days",
            window="all",
            value=len({event["dt"].date() for event in views}),
            unit="days",
            data_as_of=data_as_of,
            source=views_sources,
            sample_count=len(views),
            confidence=_confidence(len(views), zero_reason="no valid view records")[0],
            confidence_reason=_confidence(len(views), zero_reason="no valid view records")[1],
        )
        for name, window, value, sample in (
            ("submit_count", "all", len(submissions), len(submissions)),
            ("submit_count", "30d", len(submit_30d), len(submit_30d)),
            ("ac_count", "all", len(ac_events), len(submissions)),
            ("ac_count", "30d", len(ac_30d), len(ac_30d)),
            ("wa_count", "all", len(wa_events), len(submissions)),
            ("wa_count", "30d", len(wa_30d), len(wa_30d)),
        ):
            metric_confidence, metric_reason = _confidence(
                sample,
                quality_issue=entity_quality_issue,
                zero_reason="no valid submission records",
            )
            _add_metric(
                records,
                ids,
                entity_type="problem",
                entity_id=pid,
                name=name,
                window=window,
                value=value,
                unit="submissions",
                data_as_of=data_as_of,
                source=sources_for_submissions,
                sample_count=sample,
                confidence=metric_confidence,
                confidence_reason=metric_reason,
            )
        for name, value, unit, sample, zero_reason in (
            ("ac_day_count", len(ac_dates), "rounds", len(ac_events), "no valid AC records"),
            ("ever_ac", bool(ac_events), "boolean", len(ac_events), "no valid AC records"),
            ("pass_rate", pass_rate, "ratio", len(submissions), "no valid submission records"),
            (
                "wa_after_latest_ac_count",
                len(wa_after_latest_ac),
                "submissions",
                len(wa_after_latest_ac),
                "no WA after the latest AC",
            ),
            (
                "wa_after_ac_count",
                len(wa_after_latest_ac_30d),
                "submissions",
                len(wa_after_latest_ac_30d),
                "no recent WA after the latest AC",
            ),
        ):
            metric_confidence, metric_reason = _confidence(
                sample,
                quality_issue=entity_quality_issue,
                zero_reason=zero_reason,
            )
            _add_metric(
                records,
                ids,
                entity_type="problem",
                entity_id=pid,
                name=name,
                window="all" if name != "wa_after_ac_count" else "30d",
                value=value,
                unit=unit,
                data_as_of=data_as_of,
                source=sources_for_submissions,
                sample_count=sample,
                confidence=metric_confidence,
                confidence_reason=metric_reason,
            )
        for name, value, unit, sample, zero_reason in (
            ("next_due_date", due_date.isoformat() if due_date else None, "date", len(ac_events), "not completed"),
            ("due", due, "boolean", len(ac_events), "not completed"),
            ("overdue", overdue, "boolean", len(ac_events), "not completed"),
            ("overdue_days", overdue_days if due_date else None, "days", len(ac_events), "not completed"),
            (
                "last_submission_status",
                latest_submission["status"] if latest_submission else None,
                "status",
                len(submissions),
                "no valid submission records",
            ),
        ):
            metric_confidence, metric_reason = _confidence(
                sample,
                quality_issue=entity_quality_issue,
                zero_reason=zero_reason,
            )
            _add_metric(
                records,
                ids,
                entity_type="problem",
                entity_id=pid,
                name=name,
                window="all",
                value=value,
                unit=unit,
                data_as_of=data_as_of,
                source=sources_for_submissions,
                sample_count=sample,
                confidence=metric_confidence,
                confidence_reason=metric_reason,
            )

        for name, value, sample, zero_reason in (
            (
                "last_submitted_at",
                latest_submission["raw_time"] if latest_submission else None,
                len(submissions),
                "no valid submission records",
            ),
            (
                "last_ac_at",
                latest_ac["raw_time"] if latest_ac else None,
                len(ac_events),
                "no valid AC records",
            ),
            (
                "last_wa_at",
                latest_wa["raw_time"] if latest_wa else None,
                len(wa_events),
                "no valid WA records",
            ),
            (
                "last_activity_at",
                latest_activity["raw_time"] if latest_activity else None,
                len(submissions) + len(views),
                "no valid submission or view records",
            ),
        ):
            metric_confidence, metric_reason = _confidence(
                sample,
                quality_issue=entity_quality_issue,
                zero_reason=zero_reason,
            )
            _add_metric(
                records,
                ids,
                entity_type="problem",
                entity_id=pid,
                name=name,
                window="all",
                value=value,
                unit="timestamp",
                data_as_of=data_as_of,
                source=(
                    ["submissions"]
                    if name != "last_activity_at"
                    else ["study_events", "submissions"]
                ),
                sample_count=sample,
                confidence=metric_confidence,
                confidence_reason=metric_reason,
            )

        problem_state = {
            "problem_id": pid,
            "submissions": submissions,
            "views": views,
            "ac_events": ac_events,
            "wa_events": wa_events,
            "ac_30d": ac_30d,
            "wa_30d": wa_30d,
            "submit_30d": submit_30d,
            "wa_after_latest_ac": wa_after_latest_ac,
            "wa_after_latest_ac_30d": wa_after_latest_ac_30d,
            "views_30d": views_30d,
            "view_days_30d": view_days_30d,
            "latest_ac": latest_ac,
            "latest_submission": latest_submission,
            "latest_activity": latest_activity,
            "ac_dates": ac_dates,
            "due_date": due_date,
            "overdue_days": overdue_days,
            "due": due,
            "overdue": overdue,
            "mark": mark,
            "mark_conflict": mark_conflict,
            "skill_ids": skill_ids,
            "metric_ids": ids,
            "entity_quality_issue": entity_quality_issue,
        }
        problem_states[pid] = problem_state
        problem_metrics.append(
            {
                "entity_type": "problem",
                "problem_id": pid,
                "title": metadata["title"],
                "category": metadata["category"],
                "difficulty": metadata["difficulty"],
                "skill_ids": skill_ids,
                "view_count": {"all": len(views), "30d": len(views_30d)},
                "view_days": {
                    "all": len({event["dt"].date() for event in views}),
                    "30d": view_days_30d,
                },
                "submit_count": {"all": len(submissions), "30d": len(submit_30d)},
                "ac_count": {"all": len(ac_events), "30d": len(ac_30d)},
                "wa_count": {"all": len(wa_events), "30d": len(wa_30d)},
                "ac_day_count": len(ac_dates),
                "problem_round_count": len(ac_dates),
                "ever_ac": bool(ac_events),
                "last_submission_status": latest_submission["status"] if latest_submission else None,
                "last_submitted_at": latest_submission["raw_time"] if latest_submission else None,
                "last_ac_at": latest_ac["raw_time"] if latest_ac else None,
                "last_wa_at": latest_wa["raw_time"] if latest_wa else None,
                "wa_after_latest_ac_count": len(wa_after_latest_ac),
                "wa_after_ac_count": {"30d": len(wa_after_latest_ac_30d)},
                "pass_rate": pass_rate,
                "source_distribution": _source_dict(source_pairs.get(pid, {})),
                "mark": mark,
                "mark_conflict": mark_conflict,
                "mark_conflict_types": ["mastered_vs_wa_after_ac"] if mark_conflict else [],
                "last_activity_at": latest_activity["raw_time"] if latest_activity else None,
                "next_due_date": due_date.isoformat() if due_date else None,
                "due": due,
                "overdue": overdue,
                "overdue_days": overdue_days if due_date else None,
                "confidence": confidence,
                "confidence_reason": confidence_reason,
                "metric_ids": dict(sorted(ids.items())),
                "metrics": sorted(records, key=lambda record: record["metric_id"]),
            }
        )

    # Build current manifest chapter facts.  Hot100 chapters deliberately use
    # AC-derived state, while all other chapters use content_events.
    content_states: dict[str, dict[str, Any]] = {}
    all_content_metrics: list[dict[str, Any]] = []
    for module in modules:
        for chapter in module["chapters"]:
            content_id = chapter["id"]
            module_id = module["id"]
            is_hot100 = module_id == "hot100"
            content_views = sorted(content_views_by_id.get(content_id, []), key=_event_key)
            content_completes = sorted(content_completes_by_id.get(content_id, []), key=_event_key)
            hot_problem_id: int | None = None
            if is_hot100 and content_id.startswith("hot100:"):
                hot_problem_id = _safe_int(content_id.split(":", 1)[1])
            hot_state = problem_states.get(hot_problem_id) if hot_problem_id is not None else None
            if is_hot100 and hot_state is not None:
                rounds = len(hot_state["ac_dates"])
                started = rounds > 0
                completed = rounds > 0
                last_completed = hot_state["latest_ac"]
                hot_activity = [*hot_state["views"], *hot_state["ac_events"]]
                last_activity = max(hot_activity, key=_event_key, default=None)
                content_views = sorted(hot_state["views"], key=_event_key)
                sources = ["study_events", "submissions"]
                sample_count = len(hot_activity)
            else:
                rounds = len(content_completes)
                started = bool(content_views or content_completes)
                completed = rounds > 0
                last_completed = max(content_completes, key=_event_key) if content_completes else None
                all_activity = [*content_views, *content_completes]
                last_activity = max(all_activity, key=_event_key) if all_activity else None
                sources = ["content_events"]
                sample_count = len(all_activity)
            due_date = (
                _due_date(last_completed["dt"], rounds, content=True)
                if last_completed and rounds > 0
                else None
            )
            overdue_days = max(0, (as_of_date - due_date).days) if due_date else 0
            due = bool(due_date and due_date <= as_of_date)
            overdue = bool(due_date and due_date < as_of_date)
            mark = marks.get(("content", content_id))
            confidence, confidence_reason = _confidence(
                sample_count,
                zero_reason="no valid chapter activity",
            )
            records = []
            ids = {}
            _add_metric(
                records,
                ids,
                entity_type="content",
                entity_id=content_id,
                name="content_round_count",
                window="all",
                value=rounds,
                unit="rounds",
                data_as_of=data_as_of,
                source=sources,
                sample_count=sample_count,
                confidence=confidence,
                confidence_reason=confidence_reason,
            )
            for name, value, unit in (
                ("started", started, "boolean"),
                ("completed", completed, "boolean"),
                ("content_due_date", due_date.isoformat() if due_date else None, "date"),
                ("next_due_date", due_date.isoformat() if due_date else None, "date"),
                ("due", due, "boolean"),
                ("overdue", overdue, "boolean"),
                ("overdue_days", overdue_days if due_date else None, "days"),
            ):
                _add_metric(
                    records,
                    ids,
                    entity_type="content",
                    entity_id=content_id,
                    name=name,
                    window="all",
                    value=value,
                    unit=unit,
                    data_as_of=data_as_of,
                    source=sources,
                    sample_count=sample_count,
                    confidence=confidence,
                    confidence_reason=confidence_reason,
                )
            for name, value, sample, zero_reason in (
                (
                    "last_activity_at",
                    last_activity["raw_time"] if last_activity else None,
                    sample_count,
                    "no valid chapter activity",
                ),
                (
                    "last_completed_at",
                    last_completed["raw_time"] if last_completed else None,
                    rounds,
                    "not completed",
                ),
            ):
                metric_confidence, metric_reason = _confidence(
                    sample,
                    zero_reason=zero_reason,
                )
                _add_metric(
                    records,
                    ids,
                    entity_type="content",
                    entity_id=content_id,
                    name=name,
                    window="all",
                    value=value,
                    unit="timestamp",
                    data_as_of=data_as_of,
                    source=sources,
                    sample_count=sample,
                    confidence=metric_confidence,
                    confidence_reason=metric_reason,
                )
            state = {
                "content_id": content_id,
                "module_id": module_id,
                "module_title": module["title"],
                "title": chapter["title"],
                "views": content_views,
                "completes": content_completes,
                "rounds": rounds,
                "started": started,
                "completed": completed,
                "last_completed": last_completed,
                "last_activity": last_activity,
                "due_date": due_date,
                "due": due,
                "overdue": overdue,
                "overdue_days": overdue_days,
                "mark": mark,
                "metric_ids": ids,
                "is_hot100": is_hot100,
                "sample_count": sample_count,
            }
            content_states[content_id] = state
            all_content_metrics.append(
                {
                    "entity_type": "content",
                    "content_id": content_id,
                    "module_id": module_id,
                    "module_title": module["title"],
                    "title": chapter["title"],
                    "skill_ids": [f"module.{module_id}"],
                    "view_count": len(content_views),
                    "view_days": len({event["dt"].date() for event in content_views}),
                    "content_round_count": rounds,
                    "started": started,
                    "completed": completed,
                    "last_activity_at": last_activity["raw_time"] if last_activity else None,
                    "last_completed_at": last_completed["raw_time"] if last_completed else None,
                    "mark": mark,
                    "content_due_date": due_date.isoformat() if due_date else None,
                    "next_due_date": due_date.isoformat() if due_date else None,
                    "due": due,
                    "overdue": overdue,
                    "overdue_days": overdue_days if due_date else None,
                    "confidence": confidence,
                    "confidence_reason": confidence_reason,
                    "metric_ids": dict(sorted(ids.items())),
                    "metrics": sorted(records, key=lambda record: record["metric_id"]),
                }
            )

    all_content_metrics.sort(key=lambda item: (item["module_id"], item["content_id"]))
    if len(all_content_metrics) > output_limits["max_content_metrics"]:
        quality["omitted"]["content_metrics"] = (
            len(all_content_metrics) - output_limits["max_content_metrics"]
        )
    output_content_metrics = all_content_metrics[: output_limits["max_content_metrics"]]
    output_content_ids = {item["content_id"] for item in output_content_metrics}

    module_metrics: list[dict[str, Any]] = []
    module_states: dict[str, dict[str, Any]] = {}
    for module in modules:
        module_id = module["id"]
        states = [
            content_states[chapter["id"]]
            for chapter in module["chapters"]
            if chapter["id"] in content_states
        ]
        total = len(states)
        started_count = sum(1 for state in states if state["started"])
        completed_count = sum(1 for state in states if state["completed"])
        due_count = sum(1 for state in states if state["due"])
        overdue_count = sum(1 for state in states if state["overdue"])
        last_activity = max(
            (state["last_activity"] for state in states if state["last_activity"] is not None),
            key=_event_key,
            default=None,
        )
        module_quality_issue = False
        confidence, confidence_reason = _confidence(
            sum(state["sample_count"] for state in states),
            zero_reason="no valid activity in current module",
        )
        records = []
        ids = {}
        for name, value, unit, sample in (
            ("module_total_contents", total, "contents", total),
            ("module_started_contents", started_count, "contents", started_count),
            ("module_completed_contents", completed_count, "contents", completed_count),
            (
                "module_completion_ratio",
                round(completed_count / total, 3) if total else None,
                "ratio",
                total,
            ),
            ("module_due_count", due_count, "contents", due_count),
            ("module_overdue_count", overdue_count, "contents", overdue_count),
            (
                "module_last_activity_at",
                last_activity["raw_time"] if last_activity else None,
                "timestamp",
                sum(state["sample_count"] for state in states),
            ),
        ):
            metric_confidence, metric_reason = _confidence(
                sample,
                quality_issue=module_quality_issue,
                zero_reason="no matching current module records",
            )
            _add_metric(
                records,
                ids,
                entity_type="module",
                entity_id=module_id,
                name=name,
                window="all",
                value=value,
                unit=unit,
                data_as_of=data_as_of,
                source=(
                    ["study_events", "submissions"]
                    if module_id == "hot100"
                    else ["content_events"]
                ),
                sample_count=sample,
                confidence=metric_confidence,
                confidence_reason=metric_reason,
            )
        module_content_output = [
            item for item in output_content_metrics if item["module_id"] == module_id
        ]
        module_state = {
            "module_id": module_id,
            "total": total,
            "started": started_count,
            "completed": completed_count,
            "due": due_count,
            "overdue": overdue_count,
            "last_activity": last_activity,
            "metric_ids": ids,
            "states": states,
        }
        module_states[module_id] = module_state
        module_metrics.append(
            {
                "entity_type": "module",
                "module_id": module_id,
                "title": module["title"],
                "skill_ids": [f"module.{module_id}"],
                "module_total_contents": total,
                "module_started_contents": started_count,
                "module_completed_contents": completed_count,
                "module_completion_ratio": round(completed_count / total, 3) if total else None,
                "module_due_count": due_count,
                "module_overdue_count": overdue_count,
                "module_last_activity_at": last_activity["raw_time"] if last_activity else None,
                "confidence": confidence,
                "confidence_reason": confidence_reason,
                "metric_ids": dict(sorted(ids.items())),
                "metrics": sorted(records, key=lambda record: record["metric_id"]),
                "content_metrics": module_content_output,
                # ``contents`` is a readable alias retained for service-layer
                # consumers that use the library terminology.
                "contents": module_content_output,
            }
        )

    problem_metrics.sort(key=lambda item: item["problem_id"])
    if len(problem_metrics) > output_limits["max_problem_metrics"]:
        quality["omitted"]["problem_metrics"] = (
            len(problem_metrics) - output_limits["max_problem_metrics"]
        )
    problem_metrics = problem_metrics[: output_limits["max_problem_metrics"]]
    output_problem_ids = {item["problem_id"] for item in problem_metrics}

    module_metrics.sort(key=lambda item: item["module_id"])
    if len(module_metrics) > output_limits["max_module_metrics"]:
        quality["omitted"]["module_metrics"] = (
            len(module_metrics) - output_limits["max_module_metrics"]
        )
    module_metrics = module_metrics[: output_limits["max_module_metrics"]]
    output_module_ids = {item["module_id"] for item in module_metrics}
    # Content metrics are exposed only inside their parent module.  Recompute
    # this set after the module cap so content signals cannot point into a
    # module that was itself omitted.
    output_content_ids = {
        content["content_id"]
        for module in module_metrics
        for content in module["content_metrics"]
    }

    # Summary facts and their metric records.
    completed_problem_ids = {pid for pid, state in problem_states.items() if state["ac_events"]}
    total_problems = len(catalog)
    completed_problem_count = len(completed_problem_ids)
    # Phase-0 treats a genuinely empty learning snapshot as an unknown ratio;
    # once there is at least one valid learning fact, zero completed problems
    # is a measured 0.0 rather than missing data.
    problem_completion_ratio = (
        round(completed_problem_count / total_problems, 3)
        if total_problems and all_learning_events
        else None
    )
    per_problem_rounds = [len(state["ac_dates"]) for state in problem_states.values()]
    curriculum_round = 0
    threshold = int(rules["curriculum_round_threshold"])
    current_round = 1
    while True:
        reached = sum(1 for rounds in per_problem_rounds if rounds >= current_round)
        if current_round == 1:
            ok = reached >= threshold
        else:
            ok = completed_problem_count > 0 and reached * 2 > completed_problem_count
        if not ok:
            break
        curriculum_round = current_round
        current_round += 1

    active_dates: set[date] = set()
    for event in valid_study_events:
        if event["action"] == "view":
            active_dates.add(event["dt"].date())
    for event in valid_submissions:
        active_dates.add(event["dt"].date())
    for events in content_events_by_id.values():
        for event in events:
            active_dates.add(event["dt"].date())

    active_days = {
        f"{days}d": sum(
            1
            for active_date in active_dates
            if _date_in_window(active_date, as_of_date, days)
        )
        for days in (7, 14, 30)
    }
    streak_cursor = as_of_date
    if streak_cursor not in active_dates:
        streak_cursor -= timedelta(days=1)
    current_streak = 0
    while streak_cursor in active_dates:
        current_streak += 1
        streak_cursor -= timedelta(days=1)

    today_problem_round_actions = len(
        {
            event["problem_id"]
            for event in valid_submissions
            if event["status"] == "ac" and event["dt"].date() == as_of_date
        }
    )
    today_content_round_actions = sum(
        1
        for events in content_events_by_id.values()
        for event in events
        if event["action"] == "complete" and event["dt"].date() == as_of_date
    )
    due_problem_count = sum(1 for state in problem_states.values() if state["due"])
    overdue_problem_count = sum(1 for state in problem_states.values() if state["overdue"])
    due_content_count = sum(1 for state in content_states.values() if state["due"])
    overdue_content_count = sum(1 for state in content_states.values() if state["overdue"])
    last_learning_event = max(all_learning_events, key=_event_key, default=None)
    total_ac = sum(1 for event in valid_submissions if event["status"] == "ac")
    total_wa = sum(1 for event in valid_submissions if event["status"] == "wa")
    total_submissions = len(valid_submissions)
    total_pass_rate = round(total_ac / total_submissions, 3) if total_submissions else None
    total_sources: defaultdict[str, int] = defaultdict(int)
    for event in valid_submissions:
        total_sources[event["source"]] += 1

    summary_values: dict[str, Any] = {
        "completed_problem_count": completed_problem_count,
        "problem_completion_ratio": problem_completion_ratio,
        "curriculum_round": curriculum_round,
        "active_days": active_days,
        "current_streak_days": current_streak,
        "today_problem_round_actions": today_problem_round_actions,
        "today_content_round_actions": today_content_round_actions,
        "due_problem_count": due_problem_count,
        "overdue_problem_count": overdue_problem_count,
        "due_content_count": due_content_count,
        "overdue_content_count": overdue_content_count,
        "last_learning_at": last_learning_event["raw_time"] if last_learning_event else None,
        "total_submissions": total_submissions,
        "total_ac": total_ac,
        "total_wa": total_wa,
        "pass_rate": total_pass_rate,
        "problem_catalog_count": total_problems,
        "module_count": len(modules),
        "content_catalog_count": len(content_index),
        "submission_source_distribution": _source_dict(total_sources),
    }
    summary_records: list[dict[str, Any]] = []
    summary_ids: dict[str, str] = {}
    summary_metric_specs = [
        ("completed_problem_count", completed_problem_count, "problems", completed_problem_count, ["submissions"]),
        (
            "problem_completion_ratio",
            problem_completion_ratio,
            "ratio",
            len(all_learning_events),
            ["submissions", "manifest"],
        ),
        ("curriculum_round", curriculum_round, "rounds", completed_problem_count, ["submissions"]),
        ("current_streak_days", current_streak, "days", len(active_dates), ["study_events", "submissions", "content_events"]),
        ("today_problem_round_actions", today_problem_round_actions, "problems", today_problem_round_actions, ["submissions"]),
        ("today_content_round_actions", today_content_round_actions, "rounds", today_content_round_actions, ["content_events"]),
        ("due_problem_count", due_problem_count, "problems", due_problem_count, ["submissions"]),
        ("overdue_problem_count", overdue_problem_count, "problems", overdue_problem_count, ["submissions"]),
        ("due_content_count", due_content_count, "contents", due_content_count, ["content_events", "submissions"]),
        ("overdue_content_count", overdue_content_count, "contents", overdue_content_count, ["content_events", "submissions"]),
        ("total_submissions", total_submissions, "submissions", total_submissions, ["submissions"]),
        ("total_ac", total_ac, "submissions", total_ac, ["submissions"]),
        ("total_wa", total_wa, "submissions", total_wa, ["submissions"]),
        ("pass_rate", total_pass_rate, "ratio", total_submissions, ["submissions"]),
        ("last_learning_at", summary_values["last_learning_at"], "timestamp", len(all_learning_events), ["study_events", "submissions", "content_events"]),
    ]
    for name, value, unit, sample, source in summary_metric_specs:
        metric_confidence, metric_reason = _confidence(
            sample,
            zero_reason="no valid records for this fact",
        )
        _add_metric(
            summary_records,
            summary_ids,
            entity_type="summary",
            entity_id="all",
            name=name,
            window="all",
            value=value,
            unit=unit,
            data_as_of=data_as_of,
            source=source,
            sample_count=sample,
            confidence=metric_confidence,
            confidence_reason=metric_reason,
        )
    for days in (7, 14, 30):
        name = "active_days"
        value = active_days[f"{days}d"]
        metric_confidence, metric_reason = _confidence(
            len(active_dates),
            zero_reason="no valid active dates",
        )
        _add_metric(
            summary_records,
            summary_ids,
            entity_type="summary",
            entity_id="all",
            name=name,
            window=f"{days}d",
            value=value,
            unit="days",
            data_as_of=data_as_of,
            source=["study_events", "submissions", "content_events"],
            sample_count=value,
            confidence=metric_confidence,
            confidence_reason=metric_reason,
        )
    summary = dict(summary_values)
    summary["metric_ids"] = dict(sorted(summary_ids.items()))
    summary["metrics"] = sorted(summary_records, key=lambda record: record["metric_id"])

    available_metric_ids = {
        metric["metric_id"] for metric in summary["metrics"]
    }
    available_metric_ids.update(
        metric["metric_id"]
        for item in problem_metrics
        for metric in item["metrics"]
    )
    available_metric_ids.update(
        metric["metric_id"]
        for item in module_metrics
        for metric in item["metrics"]
    )
    available_metric_ids.update(
        metric["metric_id"]
        for item in module_metrics
        for content in item["content_metrics"]
        for metric in content["metrics"]
    )

    # Rule candidates are assembled first, then bounded.  Every emitted signal
    # receives an evidence record during the same pass, so no dangling refs can
    # be produced by the list limits.
    signal_candidates: list[dict[str, Any]] = []

    def add_candidate(
        *,
        signal_type: str,
        entity_type: str,
        entity_id: Any,
        severity: str,
        confidence: str,
        window: str,
        reason_code: str,
        metric_ids: list[str],
        source_table: str,
        fact_type: str,
        fact: Mapping[str, Any],
        events: list[Mapping[str, Any]] | None = None,
        reason_codes: list[str] | None = None,
        extra_entity_fields: Mapping[str, Any] | None = None,
    ) -> None:
        if entity_type == "problem" and _safe_int(entity_id) not in output_problem_ids:
            quality["omitted"]["signals"] += 1
            return
        if entity_type == "module" and str(entity_id) not in output_module_ids:
            quality["omitted"]["signals"] += 1
            return
        if entity_type == "content" and str(entity_id) not in output_content_ids:
            quality["omitted"]["signals"] += 1
            return
        normalized_metric_ids = sorted(set(metric_ids))
        if not normalized_metric_ids or not set(normalized_metric_ids).issubset(
            available_metric_ids
        ):
            quality["omitted"]["signals"] += 1
            return
        signal_candidates.append(
            {
                "signal_type": signal_type,
                "entity_type": entity_type,
                "entity_id": str(entity_id),
                "severity": severity,
                "confidence": confidence,
                "window": window,
                "reason_code": reason_code,
                "metric_ids": normalized_metric_ids,
                "source_table": source_table,
                "fact_type": fact_type,
                "fact": dict(fact),
                "events": list(events or []),
                "reason_codes": sorted(set(reason_codes or [])),
                "extra_entity_fields": dict(extra_entity_fields or {}),
            }
        )

    # Keep data_insufficient first so it is never crowded out by a large
    # number of due items.
    insufficient_reason_codes: list[str] = []
    warning_codes: list[str] = []
    recognized_learning_count = len(all_learning_events)
    if recognized_learning_count == 0:
        insufficient_reason_codes.append("no_learning_data")
    if total_submissions == 0:
        insufficient_reason_codes.append("no_submission_data")
    elif total_submissions < int(rules["too_few_attempts"]):
        insufficient_reason_codes.append("too_few_attempts")
    if unmapped_problem_count > 0:
        warning_codes.append("skill_unmapped")
    if quality["invalid_timestamp_count"] > 0:
        warning_codes.append("invalid_timestamps")
    if quality["mixed_source_possible_duplicate_count"] > 0:
        warning_codes.append("mixed_source_possible_duplicate")
    if quality["invalid_source_count"] > 0:
        warning_codes.append("invalid_sources")
    if quality["duplicate_lc_id_count"] > 0:
        warning_codes.append("duplicate_lc_id")
    if insufficient_reason_codes:
        add_candidate(
            signal_type="data_insufficient",
            entity_type="dataset",
            entity_id="all",
            severity="informational",
            confidence="insufficient",
            window="all",
            reason_code="data_insufficient",
            metric_ids=[
                summary_ids["total_submissions.all"],
                summary_ids["completed_problem_count.all"],
            ],
            source_table="data_quality",
            fact_type="reason_codes",
            fact={"reason_codes": sorted(set(insufficient_reason_codes))},
            reason_codes=insufficient_reason_codes,
        )

    for pid in sorted(problem_states):
        state = problem_states[pid]
        ids = state["metric_ids"]
        if (
            len(state["wa_30d"]) >= int(rules["repeat_wa_min"])
            and not state["ac_events"]
        ):
            add_candidate(
                signal_type="repeat_wa",
                entity_type="problem",
                entity_id=pid,
                severity="high",
                confidence="medium" if state["entity_quality_issue"] else "high",
                window="30d",
                reason_code="repeat_wa_without_ac",
                metric_ids=[ids["wa_count.30d"], ids["ever_ac.all"]],
                source_table="submissions",
                fact_type="recent_wa_without_ac",
                fact={
                    "problem_id": pid,
                    "wa_count_30d": len(state["wa_30d"]),
                    "ever_ac": False,
                },
                events=state["wa_30d"],
            )
        if state["ac_events"] and state["wa_after_latest_ac"]:
            severity = (
                "high"
                if len(state["wa_after_latest_ac_30d"])
                >= int(rules["wa_after_ac_high_min_30d"])
                else "medium"
            )
            add_candidate(
                signal_type="wa_after_ac",
                entity_type="problem",
                entity_id=pid,
                severity=severity,
                confidence="medium" if state["entity_quality_issue"] else "high",
                window="all",
                reason_code="wa_after_latest_ac",
                metric_ids=[
                    ids["wa_after_latest_ac_count.all"],
                    ids["wa_after_ac_count.30d"],
                    ids["last_submission_status.all"],
                ],
                source_table="submissions",
                fact_type="wa_after_latest_ac",
                fact={
                    "problem_id": pid,
                    "wa_after_latest_ac_count": len(state["wa_after_latest_ac"]),
                    "wa_after_latest_ac_count_30d": len(state["wa_after_latest_ac_30d"]),
                    "latest_ac_at": state["latest_ac"]["raw_time"] if state["latest_ac"] else None,
                },
                events=state["wa_after_latest_ac"],
            )
        if (
            len(state["views_30d"]) >= int(rules["view_without_ac_min_views_30d"])
            and state["view_days_30d"]
            >= int(rules["view_without_ac_min_days_30d"])
            and not state["ac_events"]
        ):
            recent_views = [
                event
                for event in state["views"]
                if _date_in_window(event["dt"].date(), as_of_date, 30)
            ]
            add_candidate(
                signal_type="view_without_ac",
                entity_type="problem",
                entity_id=pid,
                severity="medium",
                confidence="high",
                window="30d",
                reason_code="repeated_views_without_ac",
                metric_ids=[ids["view_count.30d"], ids["view_days.30d"], ids["ever_ac.all"]],
                source_table="study_events",
                fact_type="views_without_ac",
                fact={
                    "problem_id": pid,
                    "view_count_30d": len(recent_views),
                    "view_days_30d": len({event["dt"].date() for event in recent_views}),
                    "ever_ac": False,
                },
                events=recent_views,
            )
        if state["due"]:
            add_candidate(
                signal_type="due_overdue",
                entity_type="problem",
                entity_id=pid,
                severity=_due_severity(state["overdue_days"], rules),
                confidence="high" if not state["entity_quality_issue"] else "medium",
                window="as_of",
                reason_code="problem_due_or_overdue",
                metric_ids=[ids["next_due_date.all"], ids["overdue_days.all"]],
                source_table="submissions",
                fact_type="problem_due_date",
                fact={
                    "problem_id": pid,
                    "next_due_date": state["due_date"].isoformat() if state["due_date"] else None,
                    "overdue_days": state["overdue_days"],
                    "round_count": len(state["ac_dates"]),
                },
                events=state["ac_events"],
            )

    for content_id in sorted(content_states):
        state = content_states[content_id]
        if not state["due"]:
            continue
        # A capped chapter list must not leave a due signal pointing at a
        # metric record that was omitted from the response.
        if content_id not in output_content_ids:
            quality["omitted"]["signals"] += 1
            continue
        ids = state["metric_ids"]
        completion_events = (
            state["completes"]
            if not state["is_hot100"]
            else problem_states.get(
                _safe_int(content_id.split(":", 1)[1]) if ":" in content_id else -1,
                {},
            ).get("ac_events", [])
        )
        add_candidate(
            signal_type="due_overdue",
            entity_type="content",
            entity_id=content_id,
            severity=_due_severity(state["overdue_days"], rules),
            confidence="high",
            window="as_of",
            reason_code="content_due_or_overdue",
            metric_ids=[ids["next_due_date.all"], ids["overdue_days.all"]],
            source_table="submissions" if state["is_hot100"] else "content_events",
            fact_type="content_due_date",
            fact={
                "content_id": content_id,
                "module_id": state["module_id"],
                "next_due_date": state["due_date"].isoformat() if state["due_date"] else None,
                "overdue_days": state["overdue_days"],
                "round_count": state["rounds"],
            },
            events=completion_events,
            extra_entity_fields={"content_id": content_id, "module_id": state["module_id"]},
        )

    for module_id in sorted(module_states):
        state = module_states[module_id]
        if (
            state["completed"] <= 0
            or state["completed"] >= state["total"]
            or state["last_activity"] is None
        ):
            continue
        inactive_days = (as_of_date - state["last_activity"]["dt"].date()).days
        if inactive_days < int(rules["stalled_module_days"]):
            continue
        module_metric_ids = state["metric_ids"]
        add_candidate(
            signal_type="stalled_module",
            entity_type="module",
            entity_id=module_id,
            severity=(
                "high"
                if inactive_days >= int(rules["stalled_module_high_days"])
                else "medium"
            ),
            confidence="high",
            window="as_of",
            reason_code="partial_module_without_recent_activity",
            metric_ids=[
                module_metric_ids["module_completed_contents.all"],
                module_metric_ids["module_total_contents.all"],
                module_metric_ids["module_last_activity_at.all"],
            ],
            source_table="content_events" if module_id != "hot100" else "submissions",
            fact_type="stalled_module",
            fact={
                "module_id": module_id,
                "completed_contents": state["completed"],
                "total_contents": state["total"],
                "inactive_days": inactive_days,
                "last_activity_at": state["last_activity"]["raw_time"],
            },
            events=[state["last_activity"]],
        )

    # Signal and evidence caps are applied together.  Evidence event IDs are
    # also capped and their omission count is retained in data_quality.
    signals: list[dict[str, Any]] = []
    evidence_by_id: dict[str, dict[str, Any]] = {}
    max_signals = output_limits["max_signals"]
    max_evidence = output_limits["max_evidence"]
    max_event_ids = output_limits["max_evidence_event_ids"]
    for candidate in signal_candidates:
        if len(signals) >= max_signals:
            quality["omitted"]["signals"] += 1
            continue
        event_ids, omitted_event_ids = _event_ids(candidate["events"], max_event_ids)
        if omitted_event_ids:
            quality["omitted"]["evidence_event_ids"] += omitted_event_ids
        fact = dict(candidate["fact"])
        fact["event_ids"] = event_ids
        fact["omitted_event_ids"] = omitted_event_ids
        evidence_identifier = _evidence_id(snapshot_hash, candidate["source_table"], fact)
        if evidence_identifier not in evidence_by_id:
            if len(evidence_by_id) >= max_evidence:
                quality["omitted"]["signals"] += 1
                quality["omitted"]["evidence"] += 1
                continue
            evidence_by_id[evidence_identifier] = {
                "evidence_id": evidence_identifier,
                "source_table": candidate["source_table"],
                "fact_type": candidate["fact_type"],
                "entity_type": candidate["entity_type"],
                "entity_id": candidate["entity_id"],
                "sample_count": len(candidate["events"]),
                "as_of": data_as_of,
                "facts": fact,
            }
        signal_identifier = _signal_id(
            str(rules["rule_version"]),
            candidate["signal_type"],
            candidate["entity_type"],
            candidate["entity_id"],
            as_of_date.isoformat(),
        )
        signal = {
            "signal_id": signal_identifier,
            "rule_version": str(rules["rule_version"]),
            "signal_type": candidate["signal_type"],
            "entity_type": candidate["entity_type"],
            "entity_id": candidate["entity_id"],
            "severity": candidate["severity"],
            "confidence": candidate["confidence"],
            "window": candidate["window"],
            "window_end": as_of_date.isoformat(),
            "reason_code": candidate["reason_code"],
            "reason_codes": candidate["reason_codes"],
            "metric_ids": candidate["metric_ids"],
            "evidence_ids": [evidence_identifier],
        }
        signal.update(candidate["extra_entity_fields"])
        if candidate["entity_type"] == "problem":
            signal["problem_id"] = _safe_int(candidate["entity_id"])
        signals.append(signal)

    signals.sort(key=lambda item: item["signal_id"])
    evidence = [evidence_by_id[key] for key in sorted(evidence_by_id)]
    quality["reason_codes"] = sorted(
        set(insufficient_reason_codes) | set(warning_codes)
    )
    quality["insufficient_reason_codes"] = sorted(set(insufficient_reason_codes))
    quality["warning_codes"] = sorted(set(warning_codes))
    quality["rule_config"] = dict(rules)
    quality["unmapped_problem_count"] = unmapped_problem_count
    quality["valid_learning_event_count"] = recognized_learning_count
    quality["valid_submission_count"] = len(valid_submissions)
    quality["snapshot_hash"] = snapshot_hash
    quality["signal_count"] = len(signals)
    quality["evidence_count"] = len(evidence)
    quality["problem_metric_count"] = len(problem_metrics)
    quality["module_metric_count"] = len(module_metrics)
    quality["content_metric_count"] = len(output_content_metrics)

    result = {
        "schema_version": SCHEMA_VERSION,
        "rule_version": str(rules["rule_version"]),
        "data_as_of": data_as_of,
        "timezone": timezone_name,
        "summary": summary,
        "problem_metrics": sorted(problem_metrics, key=lambda item: item["problem_id"]),
        "module_metrics": sorted(module_metrics, key=lambda item: item["module_id"]),
        "signals": signals,
        "evidence": evidence,
        "data_quality": quality,
    }
    # Keep accidental non-JSON values from leaking out when this function is
    # called with unusual catalog/manifest objects.
    json.dumps(result, ensure_ascii=False, sort_keys=True)
    return result


__all__ = [
    "AnalyticsUnavailableError",
    "CATEGORY_SKILL_IDS",
    "CONTENT_REVIEW_INTERVALS",
    "DEFAULT_LIMITS",
    "DEFAULT_RULE_CONFIG",
    "PROBLEM_REVIEW_INTERVALS",
    "RULE_VERSION",
    "SCHEMA_VERSION",
    "build_learning_analytics",
]
