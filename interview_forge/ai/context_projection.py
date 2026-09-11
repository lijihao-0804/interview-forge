"""LLMContext v2 projection and model-preparation observability helpers.

The functions here intentionally depend on the facade only at call time for
legacy patch points such as _messages and model_key.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from interview_forge.ai.prompts import (
    CONTEXT_SCHEMA_VERSION,
    LLM_CONTEXT_VERSION,
    MAX_CONTEXT_PREVIEW_CHARS,
)


def _runtime():
    from interview_forge.ai import ai_coach
    return ai_coach


def _messages(context_json: str, repair: bool = False):
    return _runtime()._messages(context_json, repair=repair)


def model_key(config=None):
    return _runtime().model_key(config)

def _prune_empty(value: Any) -> Any:
    """Recursively remove empty transport noise while preserving zero and false."""
    if isinstance(value, Mapping):
        result = {str(k): _prune_empty(v) for k, v in value.items()}
        return {k: v for k, v in result.items() if v not in (None, "", [], {})}
    if isinstance(value, (list, tuple)):
        result = [_prune_empty(item) for item in value]
        return [item for item in result if item not in (None, "", [], {})]
    return value


def _compact_fact_for_case(case: Mapping[str, Any], trace: Mapping[str, Any]) -> dict[str, Any]:
    fact = trace.get("semantic_fact", {})
    fact = fact if isinstance(fact, Mapping) else {}
    case_type = str(case.get("case_type", ""))
    common = {"problem_id", "module_id", "content_id", "title", "module_title", "category", "difficulty"}
    dynamic = {
        "due_overdue": {"due", "overdue", "overdue_days", "next_due_date", "content_due_date", "problem_round_count", "content_round_count", "last_activity_at"},
        "repeat_wa": {"wa_count", "submit_count", "ever_ac", "last_wa_at", "last_activity_at"},
        "wa_after_ac": {"wa_after_ac_count", "wa_after_latest_ac_count", "last_ac_at", "last_wa_at", "last_submission_status"},
        "view_without_ac": {"view_count", "view_days", "ever_ac", "last_activity_at"},
        "stalled_module": {"module_completion_ratio", "module_due_count", "module_overdue_count", "module_last_activity_at"},
    }.get(case_type, {"last_activity_at"})
    result = {"ref": str(case.get("ref")), "case_type": case_type}
    for key in sorted(common | dynamic):
        if key in fact:
            result[key] = fact[key]
    if not result.get("title") and trace.get("label"):
        result["title"] = str(trace.get("label"))[:160]
    return _prune_empty(result)


def _semantic_coverage(digest: Mapping[str, Any]) -> dict[str, Any]:
    coverage = digest.get("coverage", {})
    coverage = coverage if isinstance(coverage, Mapping) else {}
    source = coverage.get("source_data_missing", {})
    source = source if isinstance(source, Mapping) else {}
    omitted = coverage.get("context_budget_omitted", {})
    omitted = omitted if isinstance(omitted, Mapping) else {}
    source_missing = bool(source.get("tables") or source.get("schema_incompatible"))
    details_sampled = any(isinstance(v, (int, float)) and v > 0 for v in omitted.values())
    return {
        "source_missing": source_missing,
        "source_missing_note": "部分源数据不可用，结论覆盖受限。" if source_missing else "",
        "representative_cases_only": True,
        "details_sampled": details_sampled,
        "context_budget_omitted": details_sampled,
    }


def _build_llm_context(context: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(context, Mapping) or context.get("context_schema_version") != CONTEXT_SCHEMA_VERSION:
        raise ValueError("上下文协议不正确")
    if context.get("task") != "learning_diagnosis":
        raise ValueError("当前模型投影只支持学习诊断")
    digest = context.get("diagnostic_digest", {})
    digest = digest if isinstance(digest, Mapping) else {}
    trace_map = context.get("trace_map", {})
    trace_map = trace_map if isinstance(trace_map, Mapping) else {}
    cases = [item for item in digest.get("representative_cases", []) if isinstance(item, Mapping)]
    compact_facts = [
        _compact_fact_for_case(case, trace_map[str(case.get("ref"))])
        for case in cases
        if str(case.get("ref")) in trace_map and isinstance(trace_map[str(case.get("ref"))], Mapping)
    ]
    clean_cases = [
        {key: item.get(key) for key in ("ref", "case_type", "severity", "title")}
        for item in cases
        if str(item.get("ref")) in {str(fact.get("ref")) for fact in compact_facts}
    ]
    fact_refs = {str(fact.get("ref")) for fact in compact_facts}
    anomalies: list[dict[str, Any]] = []
    for item in digest.get("anomalies", []) if isinstance(digest.get("anomalies"), list) else []:
        if not isinstance(item, Mapping):
            continue
        clean = dict(item)
        clean["example_refs"] = [
            str(ref) for ref in item.get("example_refs", []) if str(ref) in fact_refs
        ][:3]
        anomalies.append(_prune_empty(clean))
    quality_notes = digest.get("data_quality_notes", [])
    quality = {"status": "attention", "notes": quality_notes} if quality_notes else {"status": "ok"}
    result = {
        "llm_context_version": LLM_CONTEXT_VERSION,
        "task": "learning_diagnosis",
        "as_of": context.get("data_as_of"),
        "diagnostic_digest": {
            "overview": digest.get("overview"),
            "review_backlog": digest.get("review_backlog"),
            "overdue_distribution": digest.get("overdue_distribution"),
            "round_distribution": digest.get("round_distribution"),
            "representative_cases": clean_cases,
        },
        "compact_facts": compact_facts,
        "anomalies": anomalies,
        "coverage": _semantic_coverage(digest),
        "data_quality": quality,
        "profile": context.get("profile"),
        "user_request": context.get("user_request"),
    }
    return _prune_empty(result)


def _context_json(context: Mapping[str, Any]) -> str:
    serialized = json.dumps(_build_llm_context(context), ensure_ascii=False, separators=(",", ":"))
    forbidden = ("evidence:", "signal:", "metric:", '"trace_map"', '"selection_reasons"', '"rule_version"')
    if any(token in serialized for token in forbidden):
        raise ValueError("模型上下文包含内部追溯字段")
    if len(serialized) > MAX_CONTEXT_PREVIEW_CHARS:
        raise ValueError("上下文超出允许范围")
    return serialized


def _model_projection_debug(context: Mapping[str, Any], context_json: str, config: AIConfig) -> dict[str, Any]:
    """Return non-sensitive observability fields for the final model projection."""
    included: dict[str, int] = {}
    projection = json.loads(context_json)
    for key in ("diagnostic_digest", "compact_facts", "anomalies", "coverage", "data_quality", "profile", "user_request"):
        value = projection.get(key)
        if isinstance(value, (list, tuple, dict)):
            included[key] = len(value)
        elif value not in (None, ""):
            included[key] = 1
        else:
            included[key] = 0
    model_context_hash = hashlib.sha256(context_json.encode("utf-8")).hexdigest()
    first_messages = _messages(context_json, repair=False)
    prompt_material = json.dumps(
        [{"role": role, "content": content} for role, content in first_messages],
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return {
        "final_context_chars": len(context_json),
        "estimated_tokens": max(1, (len(context_json) + 3) // 4),
        "included_sections": included,
        "prompt_hash": hashlib.sha256(prompt_material.encode("utf-8")).hexdigest(),
        "context_hash": model_context_hash,
        "model_key": model_key(config),
        "llm_context_version": LLM_CONTEXT_VERSION,
        "sections_not_sent": ["summary", "facts", "signals", "evidence", "selection_reasons", "trace_map", "omitted", "meta"],
    }

