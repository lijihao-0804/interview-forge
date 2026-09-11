"""Deterministic diagnosis selection, digest, and trace helpers.

This module owns the diagnosis-specific aggregation rules while the compiler
facade keeps the public compilation entrypoint and protocol assembly.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from interview_forge.analytics.context_models import *


def _runtime():
    from interview_forge.analytics import context_compiler
    return context_compiler


def _safe_count(value):
    return _runtime()._safe_count(value)

def _time_score(value: Any) -> float:
    if not isinstance(value, str) or not value:
        return 0.0
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            # Never ask the host OS for a timezone when ranking malformed
            # legacy values.  A naive value is already only a deterministic
            # lexical tie-breaker here.
            return float(parsed.toordinal() * 86400 + parsed.hour * 3600 + parsed.minute * 60 + parsed.second)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError, OSError):
        return 0.0


def _time_date(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed.date().isoformat()


def _days_before(as_of: str | None, value: Any) -> int | None:
    if not as_of:
        return None
    as_of_date = _time_date(as_of)
    value_date = _time_date(value)
    if as_of_date is None or value_date is None:
        return None
    try:
        return (
            datetime.fromisoformat(as_of_date).date()
            - datetime.fromisoformat(value_date).date()
        ).days
    except (TypeError, ValueError, OverflowError):
        return None
def _fact_id(fact: Mapping[str, Any]) -> str:
    entity_type = str(fact.get("entity_type", ""))
    if entity_type == "problem":
        return f"problem:{fact.get('problem_id')}"
    if entity_type == "module":
        return f"module:{fact.get('module_id')}"
    return f"content:{fact.get('content_id')}"


def _entity_key(entity_type: Any, entity_id: Any) -> tuple[int, str]:
    ranks = {"problem": 0, "content": 1, "module": 2, "dataset": 3}
    return ranks.get(str(entity_type), 9), str(entity_id)


def _fact_num(fact: Mapping[str, Any], key: str, nested: str | None = None) -> int:
    value = fact.get(key)
    if nested is not None and isinstance(value, Mapping):
        value = value.get(nested)
    return _safe_count(value) or 0


def _fact_has_learning_activity(fact: Mapping[str, Any]) -> bool:
    """Exclude catalog-only zero rows from a diagnosis context."""

    entity_type = fact.get("entity_type")
    if entity_type == "problem":
        return any(
            (
                _fact_num(fact, "view_count", "all"),
                _fact_num(fact, "submit_count", "all"),
                _fact_num(fact, "ac_count", "all"),
                _fact_num(fact, "wa_count", "all"),
            )
        ) or fact.get("mark") in _ALLOWED_MARKS or fact.get("due") is True
    if entity_type == "module":
        return any(
            (
                _fact_num(fact, "module_started_contents"),
                _fact_num(fact, "module_completed_contents"),
                _fact_num(fact, "module_due_count"),
                _fact_num(fact, "module_overdue_count"),
            )
        )
    if entity_type == "content":
        return any(
            (
                _fact_num(fact, "view_count"),
                _fact_num(fact, "content_round_count"),
            )
        ) or fact.get("started") is True or fact.get("due") is True
    return False


def _diagnostic_fact_key(fact: Mapping[str, Any]) -> tuple[str, str]:
    entity_type = str(fact.get("entity_type", ""))
    if entity_type == "problem":
        return entity_type, str(fact.get("problem_id", ""))
    if entity_type == "module":
        return entity_type, str(fact.get("module_id", ""))
    return entity_type, str(fact.get("content_id", ""))


def _diagnostic_signal_key(signal: Mapping[str, Any]) -> tuple[str, str]:
    return str(signal.get("entity_type", "")), str(signal.get("entity_id", ""))


def _diagnostic_signal_overdue_days(
    signal: Mapping[str, Any], evidence_by_id: Mapping[str, Mapping[str, Any]]
) -> int:
    days: list[int] = []
    for evidence_id in signal.get("evidence_ids", []):
        evidence = evidence_by_id.get(str(evidence_id), {})
        facts = evidence.get("facts", {}) if isinstance(evidence, Mapping) else {}
        value = _safe_count(facts.get("overdue_days")) if isinstance(facts, Mapping) else None
        if value is not None:
            days.append(value)
    return max(days or [0])


def _diagnostic_signal_sort_key(
    signal: Mapping[str, Any], evidence_by_id: Mapping[str, Mapping[str, Any]]
) -> tuple[Any, ...]:
    return (
        -_DIAGNOSIS_SIGNAL_RANK.get(str(signal.get("signal_type")), 0),
        -_SEVERITY_RANK.get(str(signal.get("severity")), 0),
        -_diagnostic_signal_overdue_days(signal, evidence_by_id),
        -_CONFIDENCE_RANK.get(str(signal.get("confidence")), 0),
        _entity_key(signal.get("entity_type"), signal.get("entity_id")),
        str(signal.get("signal_id")),
    )


def _select_diagnosis_signals(
    signals: list[dict[str, Any]],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    limit: int,
    priority_keys: set[tuple[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select diagnosis signals by type before applying the atomic builder.

    A due signal is useful as a count/distribution, but a long due queue must
    not crowd out WA, view, module, or data-quality signals.  The first pass
    takes one best item per type; the second pass fills remaining slots while
    keeping due items near a 40% cap whenever another type exists.
    """

    priority_keys = priority_keys or set()

    def selection_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            0 if _diagnostic_signal_key(item) in priority_keys else 1,
            *_diagnostic_signal_sort_key(item, evidence_by_id),
        )

    ordered = sorted(signals, key=selection_key)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for signal in ordered:
        grouped.setdefault(str(signal.get("signal_type")), []).append(signal)
    type_order = sorted(
        grouped,
        key=lambda signal_type: _diagnostic_signal_sort_key(
            grouped[signal_type][0], evidence_by_id
        ),
    )
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for signal_type in type_order:
        if len(selected) >= limit:
            break
        signal = grouped[signal_type][0]
        selected.append(signal)
        selected_ids.add(str(signal.get("signal_id")))

    due_present = "due_overdue" in grouped
    other_type_present = len(grouped) > 1
    due_cap = max(1, int(limit * _DIAGNOSIS_SIGNAL_DUE_CAP_RATIO))
    if due_present and not other_type_present:
        # Even a due-only snapshot keeps only a few representative rows; the
        # digest carries the complete queue distribution.
        due_cap = min(limit, 3)
    due_selected = sum(1 for item in selected if item.get("signal_type") == "due_overdue")
    for signal in ordered:
        if len(selected) >= limit:
            break
        signal_id = str(signal.get("signal_id"))
        if signal_id in selected_ids:
            continue
        if (
            signal.get("signal_type") == "due_overdue"
            and due_selected >= due_cap
        ):
            continue
        selected.append(signal)
        selected_ids.add(signal_id)
        if signal.get("signal_type") == "due_overdue":
            due_selected += 1

    stats = {
        "candidate_signals": len(signals),
        "candidate_signal_types": type_order,
        "selected_signal_types": [str(item.get("signal_type")) for item in selected],
        "due_overdue_cap": due_cap if due_present else None,
        "due_overdue_selected": due_selected,
        "diversity_applied": bool(other_type_present and due_present),
    }
    return selected, stats


def _diagnostic_review_facts(
    problem_facts: list[dict[str, Any]], content_facts: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]], list[dict[str, Any]]]:
    problem_due = [item for item in problem_facts if item.get("due") is True]
    content_due = [item for item in content_facts if item.get("due") is True]
    # Hot100 content rows can mirror problem rows.  Use the problem read model
    # as the canonical review queue when it is populated, and expose the
    # content scope separately instead of double-counting the same backlog.
    if problem_due:
        return problem_due, "problem_metrics", problem_due, content_due
    return content_due, "content_metrics", problem_due, content_due


def _diagnostic_overdue_distribution(
    review_facts: list[dict[str, Any]], data_as_of: str | None
) -> dict[str, int]:
    result = {key: 0 for key in _DIAGNOSIS_DUE_BUCKETS}
    result["unclassified"] = 0
    for fact in review_facts:
        days = _safe_count(fact.get("overdue_days"))
        if days is None:
            due_date = fact.get("next_due_date") or fact.get("content_due_date")
            if data_as_of and _time_date(due_date) == _time_date(data_as_of):
                result["due_today"] += 1
            else:
                result["unclassified"] += 1
        elif days > 90:
            result[">90d"] += 1
        elif days == 90:
            result["90d"] += 1
        elif days >= 60:
            result["60-89d"] += 1
        elif days >= 30:
            result["30-59d"] += 1
        elif days >= 8:
            result["8-29d"] += 1
        elif days >= 1:
            result["1-7d"] += 1
        else:
            result["due_today"] += 1
    return result


def _diagnostic_round_distribution(problem_facts: list[dict[str, Any]]) -> dict[str, int]:
    result = {
        "round_0": 0,
        "round_1": 0,
        "round_2": 0,
        "round_3_plus": 0,
        "unknown": 0,
    }
    for fact in problem_facts:
        if "problem_round_count" not in fact:
            result["unknown"] += 1
            continue
        rounds = _safe_count(fact.get("problem_round_count"))
        if rounds is None:
            result["unknown"] += 1
        elif rounds == 0:
            result["round_0"] += 1
        elif rounds == 1:
            result["round_1"] += 1
        elif rounds == 2:
            result["round_2"] += 1
        else:
            result["round_3_plus"] += 1
    return result


def _diagnostic_fact_titles(
    facts: list[dict[str, Any]],
) -> dict[tuple[str, str], str]:
    return {
        _diagnostic_fact_key(fact): str(fact.get("title", ""))[:160]
        for fact in facts
        if isinstance(fact.get("title"), str) and fact.get("title")
    }


def _diagnostic_ref(entity_type: Any, entity_id: Any) -> str:
    """Return a stable compact reference that never embeds internal metric IDs."""
    kind = str(entity_type)
    raw = str(entity_id)
    prefix = {"problem": "p", "module": "m", "content": "c"}.get(kind, "x")
    if kind == "problem" and re.fullmatch(r"[0-9]{1,8}", raw):
        return f"{prefix}{raw}"
    return f"{prefix}{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:8]}"


def _build_trace_map(
    signals: list[dict[str, Any]],
    facts: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build the bounded backend-only bridge from compact refs to real trace IDs."""
    fact_by_key = {_diagnostic_fact_key(item): item for item in facts}
    result: dict[str, dict[str, Any]] = {}
    for signal in signals:
        if len(result) >= _TRACE_MAP_MAX_ENTRIES:
            break
        key = _diagnostic_signal_key(signal)
        ref = _diagnostic_ref(*key)
        fact = fact_by_key.get(key, {})
        entry = result.setdefault(
            ref,
            {
                "entity_type": key[0],
                "entity_id": key[1],
                "label": str(fact.get("title") or fact.get("module_title") or key[1])[:160],
                "signal_ids": [],
                "evidence_ids": [],
                "metric_ids": [],
                "semantic_fact": {
                    str(name): fact[name]
                    for name in (
                        "problem_id", "module_id", "content_id", "title", "module_title",
                        "category", "difficulty", "view_count", "view_days", "submit_count",
                        "ac_count", "wa_count", "wa_after_ac_count", "wa_after_latest_ac_count",
                        "problem_round_count", "content_round_count", "ever_ac",
                        "last_submission_status", "last_activity_at", "last_ac_at", "last_wa_at",
                        "due", "overdue", "overdue_days", "next_due_date", "content_due_date",
                        "module_completion_ratio", "module_due_count", "module_overdue_count",
                        "module_last_activity_at",
                    )
                    if name in fact and fact[name] not in (None, "", [], {})
                },
            },
        )
        for field, values in (
            ("signal_ids", [signal.get("signal_id")]),
            ("evidence_ids", signal.get("evidence_ids", [])),
            ("metric_ids", signal.get("metric_ids", [])),
        ):
            for value in values:
                text = str(value or "")
                if text and text not in entry[field] and len(entry[field]) < _TRACE_MAP_MAX_IDS_PER_KIND:
                    entry[field].append(text)
        fact_metric_ids = fact.get("metric_ids", {}) if isinstance(fact, Mapping) else {}
        values = fact_metric_ids.values() if isinstance(fact_metric_ids, Mapping) else fact_metric_ids
        if isinstance(values, (list, tuple, set)) or type(values).__name__ == "dict_values":
            for value in values:
                text = str(value or "")
                if text and text not in entry["metric_ids"] and len(entry["metric_ids"]) < _TRACE_MAP_MAX_IDS_PER_KIND:
                    entry["metric_ids"].append(text)
    return result


def _diagnostic_representative_cases(
    signals: list[dict[str, Any]],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    facts: list[dict[str, Any]],
    trace_map: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    titles = _diagnostic_fact_titles(facts)
    ordered = sorted(signals, key=lambda item: _diagnostic_signal_sort_key(item, evidence_by_id))
    selected: list[dict[str, Any]] = []
    seen_types: set[str] = set()
    for signal in ordered:
        signal_type = str(signal.get("signal_type"))
        if signal_type in seen_types:
            continue
        selected.append(signal)
        seen_types.add(signal_type)
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        for signal in ordered:
            if signal in selected:
                continue
            selected.append(signal)
            if len(selected) >= limit:
                break
    cases: list[dict[str, Any]] = []
    for signal in selected:
        ref = _diagnostic_ref(signal.get("entity_type"), signal.get("entity_id"))
        if trace_map is not None and ref not in trace_map:
            continue
        case = {
            "ref": ref,
            "case_type": str(signal.get("signal_type")),
            "entity_type": str(signal.get("entity_type")),
            "severity": str(signal.get("severity")),
        }
        title = titles.get(_diagnostic_signal_key(signal))
        if title:
            case["title"] = title
        cases.append(case)
    return cases


def _diagnostic_anomalies(
    problem_facts: list[dict[str, Any]],
    data_as_of: str | None,
    selected_signals: list[dict[str, Any]],
    trace_map: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not data_as_of:
        return []
    selected_entities: set[tuple[str, str]] = set()
    for signal in selected_signals:
        selected_entities.add(_diagnostic_signal_key(signal))
    candidates: list[tuple[tuple[Any, ...], str]] = []
    total_count = 0
    for fact in problem_facts:
        if fact.get("due") is not True:
            continue
        activity_age = _days_before(data_as_of, fact.get("last_activity_at"))
        due_age = _days_before(data_as_of, fact.get("next_due_date"))
        if activity_age is None or activity_age < 0 or activity_age > 7:
            continue
        if due_age is None or due_age < 0:
            continue
        problem_id = str(fact.get("problem_id"))
        total_count += 1
        ref = _diagnostic_ref("problem", problem_id)
        if ("problem", problem_id) in selected_entities and (trace_map is None or ref in trace_map):
            candidates.append(((activity_age, -(_safe_count(fact.get("overdue_days")) or 0), problem_id), ref))
    candidates.sort(key=lambda item: item[0])
    if not candidates:
        return []
    return [{
        "type": "recent_activity_with_stale_review_state",
        "count": total_count,
        "example_refs": [item[1] for item in candidates[:3]],
        "observation": "部分代表题目近期存在学习活动，但完成或复习到期状态尚未刷新。",
        "possible_explanations": [
            "近期活动可能是查看或未通过提交，没有形成新的完成记录。",
            "复习日期可能依据另一类完成事件计算，或存在正常的同步时间差。",
        ],
    }]


def _build_diagnostic_digest(
    summary: Mapping[str, Any],
    problem_facts: list[dict[str, Any]],
    content_facts: list[dict[str, Any]],
    all_signals: list[dict[str, Any]],
    selected_signals: list[dict[str, Any]],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    data_quality: Mapping[str, Any],
    data_as_of: str | None,
) -> dict[str, Any]:
    review_facts, review_scope, problem_due, content_due = _diagnostic_review_facts(
        problem_facts, content_facts
    )
    overdue = _diagnostic_overdue_distribution(review_facts, data_as_of)
    rule_config = data_quality.get("rule_config", {})
    relearn_days = (
        _safe_count(rule_config.get("relearn_overdue_days"))
        if isinstance(rule_config, Mapping)
        else None
    )
    if relearn_days is not None:
        relearn_total = sum(
            1
            for fact in review_facts
            if (_safe_count(fact.get("overdue_days")) or 0) >= relearn_days
        )
        relearn_basis = f"overdue_days>={relearn_days}"
    else:
        review_keys = {_diagnostic_fact_key(fact) for fact in review_facts}
        relearn_total = len(
            {
                _diagnostic_signal_key(signal)
                for signal in all_signals
                if signal.get("signal_type") == "due_overdue"
                and signal.get("severity") == "relearn"
                and _diagnostic_signal_key(signal) in review_keys
            }
        )
        relearn_basis = "analytics_signal_severity_relearn"

    active_days = summary.get("active_days") if isinstance(summary, Mapping) else {}
    active_days = active_days if isinstance(active_days, Mapping) else {}
    overview: dict[str, Any] = {}
    completed = _safe_count(summary.get("completed_problem_count"))
    total = _safe_count(summary.get("problem_catalog_count"))
    if completed is not None:
        overview["completed"] = completed
    if total is not None:
        overview["total"] = total
    for key, source_key in (
        ("completion_ratio", "problem_completion_ratio"),
        ("curriculum_round", "curriculum_round"),
        ("pass_rate", "pass_rate"),
        ("streak", "current_streak_days"),
        ("last_learning_at", "last_learning_at"),
    ):
        value = summary.get(source_key)
        if value is not None:
            overview[key] = value
    for days in (7, 14, 30):
        value = _safe_count(active_days.get(f"{days}d"))
        if value is not None:
            overview[f"active_days_{days}"] = value

    source_missing = list(data_quality.get("source_missing_tables", []))
    source_schema_incompatible = data_quality.get("source_schema_incompatible") is True
    quality_notes: list[dict[str, Any]] = []
    ignored_hot100 = _safe_count(data_quality.get("ignored_hot100_content_event_count"))
    if ignored_hot100:
        quality_notes.append(
            {
                "code": "ignored_hot100_content_event_count",
                "count": ignored_hot100,
                "meaning": "Hot100 内容完成由题目提交记录代表；这是已知统计语义提示，不是学习优势，也不等同于数据故障。",
            }
        )
    digest = {
        "version": _DIAGNOSTIC_DIGEST_VERSION,
        "overview": overview,
        "review_backlog": {
            "scope": review_scope,
            "due_total": len(review_facts),
            "overdue_total": sum(
                1
                for fact in review_facts
                if fact.get("overdue") is True
                or (_safe_count(fact.get("overdue_days")) or 0) > 0
            ),
            "relearn_total": relearn_total,
            "relearn_basis": relearn_basis,
            "problem_due_total": len(problem_due),
            "content_due_total": len(content_due),
        },
        "overdue_distribution": overdue,
        "round_distribution": _diagnostic_round_distribution(problem_facts),
        "representative_cases": _diagnostic_representative_cases(
            selected_signals, evidence_by_id, problem_facts + content_facts
        ),
        "anomalies": _diagnostic_anomalies(problem_facts, data_as_of, selected_signals),
        "coverage": {
            "source_data_missing": {
                "tables": source_missing,
                "schema_incompatible": source_schema_incompatible,
            },
            "context_budget_omitted": {},
        },
        "data_quality_notes": quality_notes,
    }
    return digest

