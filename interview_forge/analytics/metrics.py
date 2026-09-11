"""Metric, signal, evidence, and snapshot-id builders for analytics.

These helpers are pure over already-read rows.  Runtime lookup keeps the
learning_analytics facade's constants and monkeypatch points authoritative.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


def _runtime():
    from interview_forge.analytics import learning_analytics
    return learning_analytics


def _short_hash(value, length=16):
    return _runtime()._short_hash(value, length=length)


def _canonical_json(value):
    return _runtime()._canonical_json(value)


def _safe_int(value, default=None):
    return _runtime()._safe_int(value, default)


def _safe_text(value, default=""):
    return _runtime()._safe_text(value, default)


def _parse_record_time(value, business_tz):
    return _runtime()._parse_record_time(value, business_tz)


def _event_key(event):
    return _runtime()._event_key(event)

def _source_dict(values: Mapping[str, int]) -> dict[str, int]:
    """Return a bounded source histogram with one stable fallback bucket."""
    merged: defaultdict[str, int] = defaultdict(int)
    for key, value in values.items():
        source = str(key)
        bucket = source if source in _runtime().ALLOWED_SUBMISSION_SOURCES else "other"
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
    return f"metric:{_runtime().SCHEMA_VERSION}:{entity_type}:{entity_id}:{metric_name}:{window}"


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
    skill_id = _runtime().CATEGORY_SKILL_IDS.get(category)
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
        "schema_version": _runtime().SCHEMA_VERSION,
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
