"""Analytics protocol, rule configuration, catalog normalization, and time models.

This module is data/rule infrastructure only; it does not open databases or
assemble the final analytics snapshot.
"""
from __future__ import annotations

import hashlib
import json
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

__all__ = [
    name for name in globals()
    if name not in {
        "hashlib", "json", "date", "datetime", "timedelta", "Path",
        "Any", "Mapping", "ZoneInfo", "ZoneInfoNotFoundError", "__all__",
    }
]

