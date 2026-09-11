"""Deterministic, bounded context compilation for ``analytics-v1``.

This module is intentionally independent from the HTTP server and from any
model SDK.  It treats the analytics snapshot as an untrusted read model and
constructs a much smaller, positive allow-list of learning facts.  The
compiler never copies an analytics object wholesale and never performs a
write.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any


from interview_forge.analytics.context_models import *


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _serialize(value: Any) -> str:
    """Serialize conservatively for the hard budget check."""

    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _hash_value(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _clean_text(value: str) -> str:
    # JSON can legally contain escaped lone surrogates.  Replace those before
    # an HTTP response or a UTF-8 file consumer can encounter an encoding
    # error; normal Chinese, emoji, and other Unicode characters are kept.
    return value.encode("utf-8", "replace").decode("utf-8")


def _text(
    value: Any,
    limit: int,
    stats: dict[str, int] | None = None,
    *,
    default: str = "",
) -> str:
    if not isinstance(value, str):
        return default
    cleaned = _clean_text(value)
    if len(cleaned) > limit:
        if stats is not None:
            stats["analytics_text_truncated_chars"] = (
                stats.get("analytics_text_truncated_chars", 0) + len(cleaned) - limit
            )
        return cleaned[:limit]
    return cleaned


def _user_text(value: Any) -> tuple[str, int]:
    if value is None:
        return "", 0
    if not isinstance(value, str):
        raise ContextCompilerError("user_request must be text")
    cleaned = _clean_text(value)
    if len(cleaned) <= MAX_USER_REQUEST_CHARS:
        return cleaned, 0
    return cleaned[:MAX_USER_REQUEST_CHARS], len(cleaned) - MAX_USER_REQUEST_CHARS


def _safe_int(value: Any, *, minimum: int | None = None, maximum: int = 10**12) -> int | None:
    if isinstance(value, bool):
        return None
    number: int | None = None
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"[+-]?\d{1,13}", value.strip()):
        try:
            number = int(value.strip())
        except ValueError:
            return None
    if number is None or abs(number) > maximum:
        return None
    if minimum is not None and number < minimum:
        return None
    return number


def _safe_count(value: Any) -> int | None:
    return _safe_int(value, minimum=0)


def _safe_ratio(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)) or float(value) < 0 or float(value) > 1:
        return None
    return round(float(value), 3)


def _safe_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _safe_code(value: Any, limit: int = 80) -> str:
    if not isinstance(value, str):
        return ""
    value = _clean_text(value)
    if len(value) > limit or not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
        return ""
    return value


def _bounded_text_list(
    value: Any,
    *,
    max_items: int,
    item_limit: int,
    stats: dict[str, int],
    allowed: set[str] | None = None,
) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[str] = []
    for raw in value[:max_items]:
        item = _text(raw, item_limit, stats)
        if not item:
            continue
        if allowed is not None and item not in allowed:
            continue
        if item not in result:
            result.append(item)
    return result


def _safe_id(value: Any, *, prefix: str | None = None, limit: int = 160) -> str:
    if not isinstance(value, str):
        return ""
    value = _clean_text(value)
    if len(value) > limit or "/" in value or "\\" in value:
        return ""
    if prefix is not None and not value.startswith(prefix):
        return ""
    if prefix is None and not _ID_RE.fullmatch(value):
        return ""
    if prefix is not None and not re.fullmatch(
        re.escape(prefix) + r"[A-Za-z0-9_.:-]+", value
    ):
        return ""
    return value


def _safe_reference_id(value: Any, *, prefix: str, limit: int) -> str:
    """Keep a stage-1 ID, while accepting opaque test/read-model IDs safely."""

    strict = _safe_id(value, prefix=prefix, limit=limit)
    if strict:
        return strict
    if not isinstance(value, str):
        return ""
    value = _clean_text(value)
    if len(value) > limit or "/" in value or "\\" in value:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
        return ""
    return value


def _safe_count_map(value: Any, keys: tuple[str, ...]) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for key in keys:
        number = _safe_count(value.get(key))
        if number is not None:
            result[key] = number
    return result


def _safe_metric_ids(value: Any, allowed_keys: set[str]) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for key in sorted(allowed_keys):
        raw = value.get(key)
        metric_id = _safe_reference_id(raw, prefix="metric:", limit=256)
        if metric_id:
            result[key] = metric_id
    return result


def _safe_time(value: Any, stats: dict[str, int]) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    text = _text(value, 64, stats)
    if not text:
        return None
    iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(iso_text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return text


def _safe_date(value: Any, stats: dict[str, int]) -> str | None:
    text = _text(value, 32, stats)
    if not text:
        return None
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except (TypeError, ValueError, OverflowError):
        return None
    return text


def _safe_module_id(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        return ""
    value = _clean_text(value)
    if "/" in value or "\\" in value or not re.fullmatch(
        r"[A-Za-z0-9_.:-]+", value
    ):
        return ""
    return value


def _safe_content_id(value: Any) -> str:
    return _safe_module_id(value)


def _safe_problem_fact(raw: Any, stats: dict[str, int]) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    problem_id = _safe_int(raw.get("problem_id"), minimum=1, maximum=10**9)
    if problem_id is None:
        return None
    fact: dict[str, Any] = {
        "fact_type": "problem_state",
        "entity_type": "problem",
        "problem_id": problem_id,
        "title": _text(raw.get("title"), 160, stats),
        "category": _text(raw.get("category"), 80, stats),
        "difficulty": _text(raw.get("difficulty"), 40, stats),
        "skill_ids": _bounded_text_list(
            raw.get("skill_ids"),
            max_items=4,
            item_limit=80,
            stats=stats,
        ),
        "view_count": _safe_count_map(raw.get("view_count"), ("all", "30d")),
        "view_days": _safe_count_map(raw.get("view_days"), ("all", "30d")),
        "submit_count": _safe_count_map(raw.get("submit_count"), ("all", "30d")),
        "ac_count": _safe_count_map(raw.get("ac_count"), ("all", "30d")),
        "wa_count": _safe_count_map(raw.get("wa_count"), ("all", "30d")),
        "wa_after_ac_count": _safe_count_map(raw.get("wa_after_ac_count"), ("30d",)),
        "source_distribution": {},
        "metric_ids": _safe_metric_ids(raw.get("metric_ids"), _PROBLEM_METRIC_KEYS),
    }
    scalar_counts = (
        "ac_day_count",
        "problem_round_count",
        "wa_after_latest_ac_count",
        "overdue_days",
    )
    for key in scalar_counts:
        value = _safe_count(raw.get(key))
        if value is not None:
            fact[key] = value
    ever_ac = _safe_bool(raw.get("ever_ac"))
    if ever_ac is not None:
        fact["ever_ac"] = ever_ac
    for key in ("due", "overdue", "mark_conflict"):
        value = _safe_bool(raw.get(key))
        if value is not None:
            fact[key] = value
    for key in ("last_submission_status",):
        value = raw.get(key)
        if isinstance(value, str) and value in _ALLOWED_STATUS:
            fact[key] = value
    for key in (
        "last_submitted_at",
        "last_ac_at",
        "last_wa_at",
        "last_activity_at",
    ):
        value = _safe_time(raw.get(key), stats)
        if value is not None:
            fact[key] = value
    next_due_date = _safe_date(raw.get("next_due_date"), stats)
    if next_due_date:
        fact["next_due_date"] = next_due_date
    pass_rate = _safe_ratio(raw.get("pass_rate"))
    if pass_rate is not None:
        fact["pass_rate"] = pass_rate
    mark = raw.get("mark")
    if isinstance(mark, str) and mark in _ALLOWED_MARKS:
        fact["mark"] = mark
    fact["mark_conflict_types"] = _bounded_text_list(
        raw.get("mark_conflict_types"),
        max_items=2,
        item_limit=80,
        stats=stats,
        allowed={"mastered_vs_wa_after_ac"},
    )
    confidence = raw.get("confidence")
    if isinstance(confidence, str) and confidence in _ALLOWED_CONFIDENCE:
        fact["confidence"] = confidence
    confidence_reason = _text(raw.get("confidence_reason"), 180, stats)
    if confidence_reason:
        fact["confidence_reason"] = confidence_reason
    distribution = raw.get("source_distribution")
    if isinstance(distribution, Mapping):
        for key in sorted(_ALLOWED_SOURCE_BUCKETS):
            value = _safe_count(distribution.get(key))
            if value is not None:
                fact["source_distribution"][key] = value
    return fact


def _safe_content_fact(
    raw: Any,
    parent_module_id: str,
    parent_module_title: str,
    stats: dict[str, int],
) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    content_id = _safe_content_id(raw.get("content_id"))
    if not content_id or not parent_module_id:
        return None
    fact: dict[str, Any] = {
        "fact_type": "content_state",
        "entity_type": "content",
        "content_id": content_id,
        "module_id": parent_module_id,
        "module_title": parent_module_title,
        "title": _text(raw.get("title"), 160, stats),
        "skill_ids": _bounded_text_list(
            raw.get("skill_ids"),
            max_items=2,
            item_limit=80,
            stats=stats,
        ),
        "view_count": _safe_count(raw.get("view_count")) or 0,
        "view_days": _safe_count(raw.get("view_days")) or 0,
        "content_round_count": _safe_count(raw.get("content_round_count")) or 0,
        "metric_ids": _safe_metric_ids(raw.get("metric_ids"), _CONTENT_METRIC_KEYS),
    }
    for key in ("started", "completed", "due", "overdue"):
        value = _safe_bool(raw.get(key))
        if value is not None:
            fact[key] = value
    for key in ("overdue_days",):
        value = _safe_count(raw.get(key))
        if value is not None:
            fact[key] = value
    for key in ("last_activity_at", "last_completed_at"):
        value = _safe_time(raw.get(key), stats)
        if value is not None:
            fact[key] = value
    for key in ("content_due_date", "next_due_date"):
        value = _safe_date(raw.get(key), stats)
        if value:
            fact[key] = value
    mark = raw.get("mark")
    if isinstance(mark, str) and mark in _ALLOWED_MARKS:
        fact["mark"] = mark
    confidence = raw.get("confidence")
    if isinstance(confidence, str) and confidence in _ALLOWED_CONFIDENCE:
        fact["confidence"] = confidence
    confidence_reason = _text(raw.get("confidence_reason"), 180, stats)
    if confidence_reason:
        fact["confidence_reason"] = confidence_reason
    return fact


def _safe_module_fact(
    raw: Any,
    stats: dict[str, int],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not isinstance(raw, Mapping):
        return None, []
    module_id = _safe_module_id(raw.get("module_id"))
    if not module_id:
        return None, []
    module_title = _text(raw.get("title"), 160, stats)
    fact: dict[str, Any] = {
        "fact_type": "module_state",
        "entity_type": "module",
        "module_id": module_id,
        "title": module_title,
        "skill_ids": _bounded_text_list(
            raw.get("skill_ids"),
            max_items=2,
            item_limit=80,
            stats=stats,
        ),
        "metric_ids": _safe_metric_ids(raw.get("metric_ids"), _MODULE_METRIC_KEYS),
    }
    for key in (
        "module_total_contents",
        "module_started_contents",
        "module_completed_contents",
        "module_due_count",
        "module_overdue_count",
    ):
        value = _safe_count(raw.get(key))
        if value is not None:
            fact[key] = value
    ratio = _safe_ratio(raw.get("module_completion_ratio"))
    if ratio is not None:
        fact["module_completion_ratio"] = ratio
    last_activity = _safe_time(raw.get("module_last_activity_at"), stats)
    if last_activity is not None:
        fact["module_last_activity_at"] = last_activity
    confidence = raw.get("confidence")
    if confidence in _ALLOWED_CONFIDENCE:
        fact["confidence"] = confidence
    confidence_reason = _text(raw.get("confidence_reason"), 180, stats)
    if confidence_reason:
        fact["confidence_reason"] = confidence_reason

    content_facts: list[dict[str, Any]] = []
    raw_contents = raw.get("content_metrics")
    if not isinstance(raw_contents, (list, tuple)):
        # analytics-v1 exposes ``contents`` as a readable compatibility alias;
        # accept it without opening a second, broader field surface.
        raw_contents = raw.get("contents")
    if not isinstance(raw_contents, (list, tuple)):
        raw_contents = []
    for content_raw in raw_contents:
        content = _safe_content_fact(content_raw, module_id, module_title, stats)
        if content is not None:
            content_facts.append(content)
    return fact, content_facts


def _dedupe(items: list[dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
    ordered = sorted(
        items,
        key=lambda item: _canonical_json({key_name: item.get(key_name), "item": item}),
    )
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in ordered:
        key = _canonical_json(item.get(key_name))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _safe_evidence_facts(
    raw: Any,
    fact_type: str,
    stats: dict[str, int],
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {}
    allowed_by_type = {
        "reason_codes": {"reason_codes"},
        "recent_wa_without_ac": {
            "problem_id",
            "wa_count_30d",
            "ever_ac",
            "event_ids",
            "omitted_event_ids",
        },
        "wa_after_latest_ac": {
            "problem_id",
            "wa_after_latest_ac_count",
            "wa_after_latest_ac_count_30d",
            "latest_ac_at",
            "event_ids",
            "omitted_event_ids",
        },
        "views_without_ac": {
            "problem_id",
            "view_count_30d",
            "view_days_30d",
            "ever_ac",
            "event_ids",
            "omitted_event_ids",
        },
        "problem_due_date": {
            "problem_id",
            "next_due_date",
            "overdue_days",
            "round_count",
            "event_ids",
            "omitted_event_ids",
        },
        "content_due_date": {
            "content_id",
            "module_id",
            "next_due_date",
            "overdue_days",
            "round_count",
            "event_ids",
            "omitted_event_ids",
        },
        "stalled_module": {
            "module_id",
            "completed_contents",
            "total_contents",
            "inactive_days",
            "last_activity_at",
            "event_ids",
            "omitted_event_ids",
        },
    }
    allowed = allowed_by_type.get(fact_type, set())
    result: dict[str, Any] = {}
    for key in sorted(allowed):
        value = raw.get(key)
        if key == "reason_codes":
            result[key] = _bounded_text_list(
                value,
                max_items=8,
                item_limit=80,
                stats=stats,
                allowed=_ALLOWED_QUALITY_CODES,
            )
        elif key == "event_ids":
            if isinstance(value, (list, tuple)):
                event_ids = [
                    number
                    for number in (_safe_int(item, minimum=0, maximum=10**9) for item in value[:32])
                    if number is not None
                ]
                result[key] = event_ids
        elif key == "omitted_event_ids":
            number = _safe_count(value)
            if number is not None:
                result[key] = number
        elif key in {"problem_id", "wa_count_30d", "wa_after_latest_ac_count", "wa_after_latest_ac_count_30d", "view_count_30d", "view_days_30d", "overdue_days", "round_count", "completed_contents", "total_contents", "inactive_days"}:
            number = _safe_int(value, minimum=0, maximum=10**12)
            if number is not None:
                result[key] = number
        elif key == "ever_ac":
            boolean = _safe_bool(value)
            if boolean is not None:
                result[key] = boolean
        elif key in {"next_due_date"}:
            text = _safe_date(value, stats)
            if text:
                result[key] = text
        elif key in {"latest_ac_at", "last_activity_at"}:
            text = _safe_time(value, stats)
            if text:
                result[key] = text
        elif key in {"content_id", "module_id"}:
            identifier = _safe_module_id(value)
            if identifier:
                result[key] = identifier
    return result


def _safe_evidence(raw: Any, stats: dict[str, int]) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    evidence_id = _safe_reference_id(
        raw.get("evidence_id"), prefix="evidence:", limit=420
    )
    source_table = raw.get("source_table")
    fact_type = raw.get("fact_type")
    if (
        not evidence_id
        or not isinstance(source_table, str)
        or not isinstance(fact_type, str)
        or source_table not in _ALLOWED_EVIDENCE_TABLES
        or fact_type not in _ALLOWED_EVIDENCE_TYPES
    ):
        return None
    entity_type = raw.get("entity_type")
    if entity_type not in _ALLOWED_SIGNAL_ENTITY_TYPES:
        return None
    entity_id = raw.get("entity_id")
    if isinstance(entity_id, int) and not isinstance(entity_id, bool):
        entity_id_text = str(entity_id)
    elif isinstance(entity_id, str):
        entity_id_text = _clean_text(entity_id)
    else:
        return None
    if len(entity_id_text) > 160 or "/" in entity_id_text or "\\" in entity_id_text:
        return None
    sample_count = _safe_count(raw.get("sample_count"))
    as_of = _safe_time(raw.get("as_of"), stats)
    result = {
        "evidence_id": evidence_id,
        "source_table": source_table,
        "fact_type": fact_type,
        "entity_type": entity_type,
        "entity_id": entity_id_text,
        "sample_count": sample_count if sample_count is not None else 0,
        "as_of": as_of,
        "facts": _safe_evidence_facts(raw.get("facts"), fact_type, stats),
    }
    return result


def _safe_signal(
    raw: Any,
    evidence_by_id: Mapping[str, dict[str, Any]],
    stats: dict[str, int],
) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    signal_id = _safe_reference_id(
        raw.get("signal_id"), prefix="signal:", limit=340
    )
    signal_type = raw.get("signal_type")
    entity_type = raw.get("entity_type")
    if (
        not signal_id
        or not isinstance(signal_type, str)
        or not isinstance(entity_type, str)
        or signal_type not in _ALLOWED_SIGNAL_TYPES
        or entity_type not in _ALLOWED_SIGNAL_ENTITY_TYPES
    ):
        return None
    entity_id_raw = raw.get("entity_id")
    if isinstance(entity_id_raw, int) and not isinstance(entity_id_raw, bool):
        entity_id = str(entity_id_raw)
    elif isinstance(entity_id_raw, str):
        entity_id = _clean_text(entity_id_raw)
    else:
        return None
    if len(entity_id) > 160 or "/" in entity_id or "\\" in entity_id:
        return None
    severity = raw.get("severity")
    confidence = raw.get("confidence")
    if (
        not isinstance(severity, str)
        or not isinstance(confidence, str)
        or severity not in _SEVERITY_RANK
        or confidence not in _ALLOWED_CONFIDENCE
    ):
        return None
    raw_evidence_ids = raw.get("evidence_ids")
    if not isinstance(raw_evidence_ids, (list, tuple)) or not raw_evidence_ids:
        return None
    evidence_ids: list[str] = []
    for item in raw_evidence_ids:
        evidence_id = _safe_reference_id(item, prefix="evidence:", limit=420)
        if not evidence_id or evidence_id not in evidence_by_id:
            # A signal with only part of its evidence is not useful context.
            return None
        if evidence_id not in evidence_ids:
            evidence_ids.append(evidence_id)
    metric_ids: list[str] = []
    raw_metric_ids = raw.get("metric_ids")
    if isinstance(raw_metric_ids, (list, tuple)):
        for item in raw_metric_ids[:32]:
            metric_id = _safe_reference_id(item, prefix="metric:", limit=256)
            if metric_id and metric_id not in metric_ids:
                metric_ids.append(metric_id)
    rule_version = _text(raw.get("rule_version"), 128, stats)
    if rule_version and not re.fullmatch(r"rules-v\d+(?:-[0-9a-f]{12})?", rule_version):
        rule_version = ""
    reason_code = _safe_code(raw.get("reason_code"), 96)
    if reason_code not in _ALLOWED_REASON_CODES:
        return None
    signal: dict[str, Any] = {
        "signal_id": signal_id,
        "rule_version": rule_version,
        "signal_type": signal_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "severity": severity,
        "confidence": confidence,
        "window": _safe_code(raw.get("window"), 32),
        "window_end": _safe_date(raw.get("window_end"), stats),
        "reason_code": reason_code,
        "reason_codes": _bounded_text_list(
            raw.get("reason_codes"),
            max_items=8,
            item_limit=80,
            stats=stats,
            allowed=_ALLOWED_QUALITY_CODES,
        ),
        "metric_ids": sorted(metric_ids),
        "evidence_ids": sorted(evidence_ids),
    }
    if entity_type == "problem":
        problem_id = _safe_int(entity_id, minimum=1, maximum=10**9)
        if problem_id is None:
            return None
        signal["problem_id"] = problem_id
    elif entity_type == "content":
        content_id = _safe_content_id(raw.get("content_id"))
        module_id = _safe_module_id(raw.get("module_id"))
        if content_id:
            signal["content_id"] = content_id
        if module_id:
            signal["module_id"] = module_id
    return signal


def _safe_summary(
    raw: Any,
    fields: tuple[str, ...],
    stats: dict[str, int],
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {"snapshot_available": False}
    result: dict[str, Any] = {"snapshot_available": True}
    count_fields = {
        "completed_problem_count",
        "curriculum_round",
        "current_streak_days",
        "today_problem_round_actions",
        "today_content_round_actions",
        "due_problem_count",
        "overdue_problem_count",
        "due_content_count",
        "overdue_content_count",
        "total_submissions",
        "total_ac",
        "total_wa",
        "problem_catalog_count",
        "module_count",
        "content_catalog_count",
    }
    ratio_fields = {"problem_completion_ratio", "pass_rate"}
    for key in fields:
        value = raw.get(key)
        if key in count_fields:
            number = _safe_count(value)
            if number is not None:
                result[key] = number
        elif key in ratio_fields:
            ratio = _safe_ratio(value)
            if ratio is not None:
                result[key] = ratio
        elif key == "active_days" and isinstance(value, Mapping):
            active: dict[str, int] = {}
            for window in ("7d", "14d", "30d"):
                number = _safe_count(value.get(window))
                if number is not None:
                    active[window] = number
            result[key] = active
        elif key == "submission_source_distribution" and isinstance(value, Mapping):
            distribution: dict[str, int] = {}
            for source in sorted(_ALLOWED_SOURCE_BUCKETS):
                number = _safe_count(value.get(source))
                if number is not None:
                    distribution[source] = number
            result[key] = distribution
        elif key == "last_learning_at":
            timestamp = _safe_time(value, stats)
            result[key] = timestamp
    return result


def _safe_data_quality(
    analytics: Mapping[str, Any],
    stats: dict[str, int],
) -> dict[str, Any]:
    raw = analytics.get("data_quality")
    raw = raw if isinstance(raw, Mapping) else {}
    schema_version = _text(analytics.get("schema_version"), 48, stats)
    rule_version = _text(analytics.get("rule_version"), 96, stats)
    result: dict[str, Any] = {
        "source_schema_version": (
            schema_version if re.fullmatch(r"analytics-v\d+", schema_version) else None
        ),
        "source_rule_version": (
            rule_version
            if re.fullmatch(r"rules-v\d+(?:-[0-9a-f]{12})?", rule_version)
            else None
        ),
        "read_only": True,
        "source_read_only": raw.get("read_only") is not False,
        "compiler": {
            "deterministic": True,
            "model_calls": 0,
            "writes_triggered": 0,
        },
    }
    for key in _QUALITY_COUNT_KEYS:
        number = _safe_count(raw.get(key))
        if number is not None:
            result[key] = number
    result["source_reason_codes"] = _bounded_text_list(
        raw.get("reason_codes"),
        max_items=16,
        item_limit=80,
        stats=stats,
        allowed=_ALLOWED_QUALITY_CODES,
    )
    result["source_missing_tables"] = _bounded_text_list(
        raw.get("missing_tables"),
        max_items=8,
        item_limit=40,
        stats=stats,
        allowed=set(_QUALITY_TABLES),
    )
    row_counts: dict[str, int] = {}
    raw_counts = raw.get("table_row_counts")
    if isinstance(raw_counts, Mapping):
        for table in _QUALITY_TABLES:
            number = _safe_count(raw_counts.get(table))
            if number is not None:
                row_counts[table] = number
    result["source_table_row_counts"] = row_counts
    raw_rule_config = raw.get("rule_config")
    if isinstance(raw_rule_config, Mapping):
        rule_config: dict[str, int] = {}
        relearn_days = _safe_count(raw_rule_config.get("relearn_overdue_days"))
        if relearn_days is not None:
            rule_config["relearn_overdue_days"] = relearn_days
        if rule_config:
            result["rule_config"] = rule_config
    incompatible = _safe_bool(raw.get("schema_incompatible"))
    if incompatible is not None:
        result["source_schema_incompatible"] = incompatible
    return result


from interview_forge.analytics.diagnosis import (
    _time_score,
    _time_date,
    _days_before,
    _fact_id,
    _entity_key,
    _fact_num,
    _fact_has_learning_activity,
    _diagnostic_fact_key,
    _diagnostic_signal_key,
    _diagnostic_signal_overdue_days,
    _diagnostic_signal_sort_key,
    _select_diagnosis_signals,
    _diagnostic_review_facts,
    _diagnostic_overdue_distribution,
    _diagnostic_round_distribution,
    _diagnostic_fact_titles,
    _diagnostic_ref,
    _build_trace_map,
    _diagnostic_representative_cases,
    _diagnostic_anomalies,
    _build_diagnostic_digest,
)



from interview_forge.analytics.selection import _SelectionBuilder


def _normalize_profile(
    profile: Any,
) -> tuple[dict[str, Any], dict[str, int]]:
    if profile is None:
        return {}, {
            "profile_unknown_fields": 0,
            "profile_invalid_fields": 0,
            "profile_truncated_chars": 0,
        }
    if not isinstance(profile, Mapping):
        raise ContextCompilerError("profile must be an object")
    result: dict[str, Any] = {}
    stats = {
        "profile_unknown_fields": 0,
        "profile_invalid_fields": 0,
        "profile_truncated_chars": 0,
    }
    for key, value in profile.items():
        if not isinstance(key, str) or key not in {
            "learning_goal",
            "available_minutes",
            "preferred_language",
        }:
            stats["profile_unknown_fields"] += 1
            continue
        if key == "available_minutes":
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
                or value > 24 * 60
            ):
                stats["profile_invalid_fields"] += 1
                continue
            result[key] = value
            continue
        if not isinstance(value, str):
            stats["profile_invalid_fields"] += 1
            continue
        cleaned = _clean_text(value)
        limit = PROFILE_TEXT_LIMITS[key]
        if len(cleaned) > limit:
            stats["profile_truncated_chars"] += len(cleaned) - limit
            cleaned = cleaned[:limit]
        if cleaned:
            result[key] = cleaned
    return result, stats


def _normalize_task(task: Any) -> str:
    if not isinstance(task, str):
        raise ContextCompilerError("task is invalid")
    task = task.strip()
    if task not in TASKS:
        raise ContextCompilerError("task is invalid")
    return task


def _normalize_budget(task: str, budget_tier: Any) -> str:
    if budget_tier is None:
        return TASK_DEFAULT_BUDGET[task]
    if not isinstance(budget_tier, str) or budget_tier.strip() not in BUDGET_TIERS:
        raise ContextCompilerError("budget_tier is invalid")
    return budget_tier.strip()


def _normalize_target_problem_id(value: Any) -> int:
    target = _safe_int(value, minimum=1, maximum=10**9)
    if target is None:
        raise ContextCompilerError("target_problem_id is invalid")
    return target


def _evidence_references(
    signals: list[dict[str, Any]],
    evidence_by_id: Mapping[str, dict[str, Any]],
) -> set[str]:
    return {
        evidence_id
        for signal in signals
        for evidence_id in signal.get("evidence_ids", [])
        if evidence_id in evidence_by_id
    }


def compile_learning_context(
    analytics: Mapping[str, Any],
    task: str,
    user_request: str = "",
    target_problem_id: Any = None,
    profile: Mapping[str, Any] | None = None,
    budget_tier: str | None = None,
) -> dict[str, Any]:
    """Compile a bounded ``context-v1`` object from one analytics snapshot.

    The function accepts only a previously computed analytics mapping.  It
    does not open a database, call a model, interpret user instructions, or
    perform a write.  ``problem_review`` requires a valid target that exists
    in the supplied snapshot; ``learning_route`` is a reserved unavailable
    protocol and never returns course candidates.
    """

    if not isinstance(analytics, Mapping):
        raise ContextCompilerError("analytics snapshot is invalid")
    normalized_task = _normalize_task(task)
    tier = _normalize_budget(normalized_task, budget_tier)
    request, request_omitted = _user_text(user_request)
    normalized_profile, profile_stats = _normalize_profile(profile)
    stats: dict[str, int] = {
        "analytics_text_truncated_chars": 0,
        **profile_stats,
    }
    data_as_of = _safe_time(analytics.get("data_as_of"), stats)
    data_quality = _safe_data_quality(analytics, stats)

    raw_summary = analytics.get("summary")
    raw_problem_metrics = analytics.get("problem_metrics")
    raw_module_metrics = analytics.get("module_metrics")
    raw_signals = analytics.get("signals")
    raw_evidence = analytics.get("evidence")

    problem_facts = _dedupe(
        [
            fact
            for raw in (raw_problem_metrics if isinstance(raw_problem_metrics, (list, tuple)) else [])
            if (fact := _safe_problem_fact(raw, stats)) is not None
        ],
        "problem_id",
    )
    module_facts: list[dict[str, Any]] = []
    content_facts: list[dict[str, Any]] = []
    for raw in (raw_module_metrics if isinstance(raw_module_metrics, (list, tuple)) else []):
        module, contents = _safe_module_fact(raw, stats)
        if module is not None:
            module_facts.append(module)
            content_facts.extend(contents)
    module_facts = _dedupe(module_facts, "module_id")
    content_facts = _dedupe(content_facts, "content_id")

    evidence_by_id: dict[str, dict[str, Any]] = {}
    for raw in (raw_evidence if isinstance(raw_evidence, (list, tuple)) else []):
        evidence = _safe_evidence(raw, stats)
        if evidence is not None:
            evidence_by_id.setdefault(evidence["evidence_id"], evidence)

    all_signals: list[dict[str, Any]] = []
    for raw in (raw_signals if isinstance(raw_signals, (list, tuple)) else []):
        signal = _safe_signal(raw, evidence_by_id, stats)
        if signal is not None:
            all_signals.append(signal)
    all_signals = _dedupe(all_signals, "signal_id")

    normalized_target_problem_id: int | None = None
    target_fact: dict[str, Any] | None = None
    diagnosis_selection_stats: dict[str, Any] = {}
    diagnostic_digest: dict[str, Any] | None = None
    diagnostic_all_signals: list[dict[str, Any]] = []
    diagnostic_candidate_facts: list[dict[str, Any]] = []
    if normalized_task == "problem_review":
        normalized_target_problem_id = _normalize_target_problem_id(target_problem_id)
        target_fact = next(
            (
                item
                for item in problem_facts
                if item.get("problem_id") == normalized_target_problem_id
            ),
            None,
        )
        if target_fact is None:
            raise ContextCompilerError("target_problem_id is invalid")

    if normalized_task == "learning_diagnosis":
        summary = _safe_summary(
            raw_summary,
            (
                "completed_problem_count",
                "problem_completion_ratio",
                "curriculum_round",
                "active_days",
                "current_streak_days",
                "today_problem_round_actions",
                "today_content_round_actions",
                "due_problem_count",
                "overdue_problem_count",
                "due_content_count",
                "overdue_content_count",
                "last_learning_at",
                "total_submissions",
                "total_ac",
                "total_wa",
                "pass_rate",
                "problem_catalog_count",
                "module_count",
                "content_catalog_count",
            ),
            stats,
        )
        diagnostic_all_signals = list(all_signals)
        anomaly_keys = {
            (str(item.get("entity_type")), str(item.get("entity_id")))
            for item in _diagnostic_anomalies(problem_facts, data_as_of, all_signals)
        }
        selected_signals, diagnosis_selection_stats = _select_diagnosis_signals(
            all_signals,
            evidence_by_id,
            int(BUDGET_TIERS[tier]["max_items"]["signals"]),
            priority_keys=anomaly_keys,
        )
        strategy = "diagnosis:digest_then_diverse_signal_sampling"
        signal_rank = _DIAGNOSIS_SIGNAL_RANK
        all_candidate_facts = [
            fact
            for fact in problem_facts + module_facts + content_facts
            if _fact_has_learning_activity(fact)
        ]
        selected_signal_entity_keys = {
            (str(signal.get("entity_type")), str(signal.get("entity_id")))
            for signal in selected_signals
        }
        candidate_facts = [
            fact
            for fact in all_candidate_facts
            if _diagnostic_fact_key(fact) in selected_signal_entity_keys
        ]
        if not candidate_facts:
            candidate_facts = all_candidate_facts[:3]
        candidate_facts = sorted(
            candidate_facts,
            key=lambda fact: (
                -max(
                    [
                        signal_rank.get(
                            signal.get("signal_type"), 0
                        )
                        for signal in selected_signals
                        if signal.get("entity_type") == fact.get("entity_type")
                        and str(signal.get("entity_id"))
                        in {
                            str(fact.get("problem_id")),
                            str(fact.get("module_id")),
                            str(fact.get("content_id")),
                        }
                    ]
                    or [0]
                ),
                -_fact_num(fact, "wa_count", "30d"),
                -_fact_num(fact, "wa_after_latest_ac_count"),
                -_fact_num(fact, "overdue_days"),
                -_time_score(
                    fact.get("last_activity_at")
                    or fact.get("module_last_activity_at")
                ),
                _fact_id(fact),
            ),
        )
        diagnostic_candidate_facts = all_candidate_facts
        fact_reason = "diagnosis_risk_or_anomaly"
        signal_reason = "diagnosis_signal_priority"
    elif normalized_task == "today_plan":
        summary = _safe_summary(
            raw_summary,
            (
                "active_days",
                "current_streak_days",
                "today_problem_round_actions",
                "today_content_round_actions",
                "due_problem_count",
                "overdue_problem_count",
                "due_content_count",
                "overdue_content_count",
                "completed_problem_count",
                "problem_completion_ratio",
                "total_submissions",
                "pass_rate",
                "last_learning_at",
            ),
            stats,
        )
        selected_signals = all_signals
        strategy = "today_plan:due_urgency_then_actionability_then_stable_id"
        signal_rank = _TODAY_SIGNAL_RANK
        related_signal_types: dict[tuple[str, str], set[str]] = {}
        for signal in selected_signals:
            related_signal_types.setdefault(
                (str(signal.get("entity_type")), str(signal.get("entity_id"))),
                set(),
            ).add(str(signal.get("signal_type")))
        due_problem_or_content = [
            fact
            for fact in problem_facts + content_facts
            if fact.get("due") is True
            or fact.get("mark") == "weak"
            or bool(
                related_signal_types.get(
                    (
                        str(fact.get("entity_type")),
                        str(fact.get("problem_id", fact.get("content_id"))),
                    ),
                    set(),
                )
            )
            or (
                fact.get("entity_type") == "problem"
                and fact.get("ever_ac") is False
            )
        ]
        candidate_facts = due_problem_or_content + [
            fact
            for fact in module_facts
            if _fact_num(fact, "module_due_count") > 0
            or _fact_num(fact, "module_overdue_count") > 0
            or _fact_num(fact, "module_completed_contents") > 0
        ]
        seen_fact_ids: set[str] = set()
        ranked_today_facts = sorted(
            candidate_facts,
            key=lambda item: (
                -(1 if item.get("due") is True else 0),
                -_fact_num(item, "overdue_days"),
                -(1 if item.get("mark") == "weak" else 0),
                -max(
                    [
                        signal_rank.get(signal_type, 0)
                        for signal_type in related_signal_types.get(
                            (
                                str(item.get("entity_type")),
                                str(item.get("problem_id", item.get("content_id"))),
                            ),
                            set(),
                        )
                    ]
                    or [0]
                ),
                _time_score(item.get("last_activity_at")),
                _fact_id(item),
            ),
        )
        candidate_facts = []
        for fact in ranked_today_facts:
            fact_id = _fact_id(fact)
            if fact_id in seen_fact_ids:
                continue
            seen_fact_ids.add(fact_id)
            candidate_facts.append(fact)
        fact_reason = "today_due_or_review_action"
        signal_reason = "today_actionable_priority"
    elif normalized_task == "problem_review":
        assert target_fact is not None
        summary = {
            "scope": "target_problem",
            "target_problem_id": normalized_target_problem_id,
            "target_title": target_fact.get("title", ""),
            "target_available": True,
        }
        selected_signals = [
            signal
            for signal in all_signals
            if signal.get("entity_type") == "problem"
            and str(signal.get("entity_id")) == str(normalized_target_problem_id)
        ]
        strategy = "problem_review:target_only_then_recent_evidence"
        signal_rank = {key: 1 for key in _ALLOWED_SIGNAL_TYPES}
        candidate_facts = [target_fact]
        fact_reason = "target_problem_scope"
        signal_reason = "target_problem_evidence"
    else:
        summary = {
            "availability": "unavailable",
            "course_retrieval": "unavailable",
            "reason_code": "no_course_retrieval",
        }
        selected_signals = []
        strategy = "learning_route:reserved_no_course_retrieval"
        signal_rank = {}
        candidate_facts = []
        fact_reason = "reserved_protocol"
        signal_reason = "reserved_protocol"

    selected_signals = sorted(
        selected_signals,
        key=lambda signal: (
            -signal_rank.get(str(signal.get("signal_type")), 0),
            -_SEVERITY_RANK.get(str(signal.get("severity")), 0),
            -_CONFIDENCE_RANK.get(str(signal.get("confidence")), 0),
            _entity_key(signal.get("entity_type"), signal.get("entity_id")),
            str(signal.get("signal_id")),
        ),
    )
    if normalized_task == "today_plan":
        evidence_overdue: dict[str, int] = {}
        for signal in selected_signals:
            for evidence_id in signal.get("evidence_ids", []):
                evidence_overdue[evidence_id] = max(
                    evidence_overdue.get(evidence_id, 0),
                    _fact_num(evidence_by_id.get(evidence_id, {}).get("facts", {}), "overdue_days"),
                )
        selected_signals = sorted(
            selected_signals,
            key=lambda signal: (
                -(
                    1
                    if signal.get("signal_type") == "due_overdue"
                    else 0
                ),
                -max(
                    [evidence_overdue.get(evidence_id, 0) for evidence_id in signal.get("evidence_ids", [])]
                    or [0]
                ),
                -signal_rank.get(str(signal.get("signal_type")), 0),
                -_SEVERITY_RANK.get(str(signal.get("severity")), 0),
                _entity_key(signal.get("entity_type"), signal.get("entity_id")),
                str(signal.get("signal_id")),
            ),
        )

    if normalized_task == "learning_diagnosis":
        diagnostic_digest = _build_diagnostic_digest(
            summary,
            problem_facts,
            content_facts,
            diagnostic_all_signals,
            selected_signals,
            evidence_by_id,
            data_quality,
            data_as_of,
        )

    count_facts = (
        diagnostic_candidate_facts
        if normalized_task == "learning_diagnosis"
        else candidate_facts
    )
    count_signals = (
        diagnostic_all_signals
        if normalized_task == "learning_diagnosis"
        else selected_signals
    )
    relevant_evidence_ids = _evidence_references(count_signals, evidence_by_id)
    candidate_counts = {
        "facts": len(count_facts),
        "problem_facts": sum(1 for item in count_facts if item.get("entity_type") == "problem"),
        "module_facts": sum(1 for item in count_facts if item.get("entity_type") == "module"),
        "content_facts": sum(1 for item in count_facts if item.get("entity_type") == "content"),
        "signals": len(count_signals),
        "evidence": len(relevant_evidence_ids),
        "selection_reasons": len(count_facts) + len(count_signals),
    }
    if normalized_task == "learning_route":
        candidate_counts["selection_reasons"] = 1
    input_omitted = {
        "user_request_chars": request_omitted,
        "profile_unknown_fields": profile_stats["profile_unknown_fields"],
        "profile_invalid_fields": profile_stats["profile_invalid_fields"],
        "profile_truncated_chars": profile_stats["profile_truncated_chars"],
    }
    builder = _SelectionBuilder(
        task=normalized_task,
        tier=tier,
        user_request=request,
        profile=normalized_profile,
        summary=summary,
        data_quality=data_quality,
        data_as_of=data_as_of,
        strategy=strategy,
        input_omitted=input_omitted,
        analytics_text_truncated_chars=stats["analytics_text_truncated_chars"],
        candidate_counts=candidate_counts,
        diagnostic_digest=diagnostic_digest,
        diagnostic_problem_facts=(
            problem_facts if normalized_task == "learning_diagnosis" else None
        ),
        diagnostic_content_facts=(
            content_facts if normalized_task == "learning_diagnosis" else None
        ),
        diagnostic_all_signals=(
            diagnostic_all_signals if normalized_task == "learning_diagnosis" else None
        ),
        diagnostic_data_as_of=(
            data_as_of if normalized_task == "learning_diagnosis" else None
        ),
    )
    if diagnosis_selection_stats:
        builder.meta["diagnosis_signal_selection"] = diagnosis_selection_stats
    if normalized_target_problem_id is not None:
        builder.meta["target_problem_id"] = normalized_target_problem_id

    if normalized_task == "learning_route":
        builder.add_protocol_reason()
    else:
        if normalized_task in {"learning_diagnosis", "today_plan"}:
            for rank, signal in enumerate(selected_signals, 1):
                builder.try_add_signal(
                    signal,
                    evidence_by_id,
                    reason_code=signal_reason,
                    rank=rank,
                )
        if normalized_task == "problem_review":
            assert target_fact is not None
            if not builder.try_add_fact(
                target_fact,
                reason_code=fact_reason,
                rank=1,
                mandatory=True,
            ):
                builder.force_add_fact(target_fact, reason_code=fact_reason, rank=1)
            for rank, signal in enumerate(selected_signals, 1):
                builder.try_add_signal(
                    signal,
                    evidence_by_id,
                    reason_code=signal_reason,
                    rank=rank,
                )
        else:
            for rank, fact in enumerate(candidate_facts, 1):
                builder.try_add_fact(
                    fact,
                    reason_code=fact_reason,
                    rank=rank,
                )

    return builder.finalize()


__all__ = [
    "BUDGET_TIERS",
    "COMPILER_VERSION",
    "CONTEXT_SCHEMA_VERSION",
    "ContextCompilerError",
    "MAX_USER_REQUEST_CHARS",
    "TASKS",
    "compile_learning_context",
]
