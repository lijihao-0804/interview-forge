"""AI coach output normalization and deterministic fallback.

This module owns the provider-independent output contract.  The facade re-exports
its historical helpers so existing imports and test patch points remain stable.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from interview_forge.ai.errors import AIServiceError
from interview_forge.ai.prompts import (
    MAX_ACTIONS, MAX_CONTEXT_PREVIEW_CHARS, MAX_DATA_GAPS, MAX_RESULT_CHARS,
    MAX_STRENGTHS, MAX_SUPPORT_REFS, MAX_WEAKNESSES,
)
from interview_forge.ai.prompts import LLM_CONTEXT_VERSION

SUPPORT_REF_RE = re.compile(r"^[pmcx][A-Za-z0-9]{1,16}$")

class _InvalidAIOutput(ValueError):
    """Internal marker for the one permitted repair attempt."""


def _json_load(value: Any, default: Any) -> Any:
    if not isinstance(value, str) or len(value) > MAX_CONTEXT_PREVIEW_CHARS + MAX_RESULT_CHARS:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _bounded_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        raise _InvalidAIOutput("string expected")
    value = value.replace("\x00", "").strip()
    if len(value) > limit:
        raise _InvalidAIOutput("text too long")
    return value


def _bounded_string_list(value: Any, limit_count: int, item_limit: int) -> list[str]:
    if not isinstance(value, list) or len(value) > limit_count:
        raise _InvalidAIOutput("list bounds")
    return [_bounded_text(item, item_limit) for item in value]


def _plain_model_value(value: Any) -> Any:
    # LangChain's raw fallback returns an AIMessage.  Prefer its content over
    # model_dump(), whose envelope contains provider metadata and is not the
    # JSON object we need to validate.
    if hasattr(value, "content") and not isinstance(value, (str, bytes, Mapping, list, tuple)):
        return _plain_model_value(value.content)
    if isinstance(value, Mapping):
        return {str(key): _plain_model_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_model_value(item) for item in value]
    if hasattr(value, "model_dump"):
        return _plain_model_value(value.model_dump())
    if hasattr(value, "dict") and callable(value.dict):
        try:
            return _plain_model_value(value.dict())
        except Exception:
            pass
    return value


def _pydantic_schema() -> Any:
    """Build the optional Pydantic schema lazily for structured model output."""
    try:
        from pydantic import BaseModel, ConfigDict, Field
    except (ImportError, ModuleNotFoundError) as exc:
        raise AIServiceError("not_configured", "AI 分析依赖尚未安装。") from exc

    class _Strict(BaseModel):
        if hasattr(BaseModel, "model_validate"):
            model_config = ConfigDict(extra="forbid")
        else:  # Pydantic v1 compatibility for a controlled local upgrade.
            class Config:
                extra = "forbid"

    class _Weakness(_Strict):
        id: str = ""
        title: str
        explanation: str
        support_refs: list[str] = Field(default_factory=list)

    class _Action(_Strict):
        title: str
        description: str
        support_refs: list[str] = Field(default_factory=list)
        weakness_id: str = ""
        basis: str
        confidence: str

    class _Insight(_Strict):
        summary: str
        strengths: list[str] = Field(default_factory=list)
        weaknesses: list[_Weakness] = Field(default_factory=list)
        actions: list[_Action] = Field(default_factory=list)
        confidence: str
        data_gaps: list[str] = Field(default_factory=list)

    return _Insight


def _pydantic_validate(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Use Pydantic when installed, while keeping startup dependency-free."""
    _Insight = _pydantic_schema()

    try:
        if hasattr(_Insight, "model_validate"):
            model = _Insight.model_validate(dict(payload))
            result = model.model_dump()
        else:
            model = _Insight.parse_obj(dict(payload))
            result = model.dict()
    except Exception as exc:
        raise _InvalidAIOutput("schema validation failed") from exc
    return result


def _resolve_support_trace(
    result: Mapping[str, Any], trace_map: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Resolve model refs to bounded internal IDs; this object is never public."""
    refs: list[str] = []
    for section in ("weaknesses", "actions"):
        for item in result.get(section, []) if isinstance(result.get(section), list) else []:
            if isinstance(item, Mapping):
                for ref in item.get("support_refs", []):
                    text = str(ref)
                    if text not in refs:
                        refs.append(text)
    resolved: dict[str, dict[str, Any]] = {}
    for ref in refs[:12]:
        entry = trace_map.get(ref)
        if not isinstance(entry, Mapping):
            continue
        resolved[ref] = {
            "label": str(entry.get("label", ""))[:160],
            "signal_ids": list(entry.get("signal_ids") or [])[:6],
            "evidence_ids": list(entry.get("evidence_ids") or [])[:6],
            "metric_ids": list(entry.get("metric_ids") or [])[:6],
        }
    return resolved


def validate_insight_payload(payload: Any, context: Mapping[str, Any]) -> dict[str, Any]:
    """Validate schema, bounds and compact-reference closure before persistence."""
    plain = _plain_model_value(payload)
    if not isinstance(plain, Mapping):
        raise _InvalidAIOutput("object expected")
    allowed = {"summary", "strengths", "weaknesses", "actions", "confidence", "data_gaps"}
    if set(plain) != allowed:
        raise _InvalidAIOutput("unexpected output fields")
    # The actual production path uses Pydantic.  The explicit set/type checks
    # below remain necessary because structured-output providers can still
    # return a dict after their own schema handling.
    validated = _pydantic_validate(plain)
    if not isinstance(validated, Mapping):
        raise _InvalidAIOutput("validated object expected")

    result: dict[str, Any] = {
        "summary": _bounded_text(validated.get("summary"), 600),
        "strengths": _bounded_string_list(validated.get("strengths"), MAX_STRENGTHS, 120),
        "weaknesses": [],
        "actions": [],
        "confidence": validated.get("confidence"),
        "data_gaps": _bounded_string_list(validated.get("data_gaps"), MAX_DATA_GAPS, 160),
    }
    if result["confidence"] not in {"low", "medium", "high"}:
        raise _InvalidAIOutput("confidence invalid")
    trace_map = context.get("trace_map", {}) if isinstance(context, Mapping) else {}
    if not isinstance(trace_map, Mapping):
        trace_map = {}
    available_refs = {str(ref) for ref in trace_map if SUPPORT_REF_RE.fullmatch(str(ref))}
    weaknesses = validated.get("weaknesses")
    if not isinstance(weaknesses, list) or len(weaknesses) > MAX_WEAKNESSES:
        raise _InvalidAIOutput("weakness bounds")
    weakness_ids: set[str] = set()
    for index, item in enumerate(weaknesses, 1):
        if not isinstance(item, Mapping):
            raise _InvalidAIOutput("weakness object expected")
        weakness_id = _bounded_text(item.get("id") or f"weakness-{index}", 64)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", weakness_id) or weakness_id in weakness_ids:
            raise _InvalidAIOutput("weakness id invalid")
        weakness_ids.add(weakness_id)
        refs = item.get("support_refs")
        if not isinstance(refs, list) or not refs or len(refs) > MAX_SUPPORT_REFS:
            raise _InvalidAIOutput("weakness support required")
        clean_refs: list[str] = []
        for ref in refs:
            ref_text = _bounded_text(ref, 24)
            if not SUPPORT_REF_RE.fullmatch(ref_text) or ref_text not in available_refs:
                raise _InvalidAIOutput("support ref invalid")
            if ref_text not in clean_refs:
                clean_refs.append(ref_text)
        result["weaknesses"].append({
            "id": weakness_id,
            "title": _bounded_text(item.get("title"), 120),
            "explanation": _bounded_text(item.get("explanation"), 500),
            "support_refs": clean_refs,
        })
    actions = validated.get("actions")
    if not isinstance(actions, list) or len(actions) > MAX_ACTIONS:
        raise _InvalidAIOutput("action bounds")
    for item in actions:
        if not isinstance(item, Mapping):
            raise _InvalidAIOutput("action object expected")
        refs = item.get("support_refs")
        if not isinstance(refs, list) or len(refs) > MAX_SUPPORT_REFS:
            raise _InvalidAIOutput("action support invalid")
        clean_refs: list[str] = []
        for ref in refs:
            ref_text = _bounded_text(ref, 24)
            if not SUPPORT_REF_RE.fullmatch(ref_text) or ref_text not in available_refs:
                raise _InvalidAIOutput("action support invalid")
            if ref_text not in clean_refs:
                clean_refs.append(ref_text)
        weakness_id = _bounded_text(item.get("weakness_id") or "", 64)
        if weakness_id and weakness_id not in weakness_ids:
            raise _InvalidAIOutput("action weakness invalid")
        basis = _bounded_text(item.get("basis"), 16)
        if basis not in {"data", "heuristic"}:
            raise _InvalidAIOutput("action basis invalid")
        action_confidence = _bounded_text(item.get("confidence"), 16)
        if action_confidence not in {"low", "medium", "high"}:
            raise _InvalidAIOutput("action confidence invalid")
        if basis == "data" and not clean_refs:
            raise _InvalidAIOutput("data action needs support")
        result["actions"].append({
            "title": _bounded_text(item.get("title"), 120),
            "description": _bounded_text(item.get("description"), 600),
            "support_refs": clean_refs,
            "weakness_id": weakness_id,
            "basis": basis,
            "confidence": action_confidence,
        })
    result["_support_trace"] = _resolve_support_trace(result, trace_map)
    if len(json.dumps(result, ensure_ascii=False, separators=(",", ":"))) > MAX_RESULT_CHARS:
        raise _InvalidAIOutput("result too long")
    return result


def _signal_label(signal_type: Any) -> str:
    return {
        "repeat_wa": "同一题多次未通过",
        "wa_after_ac": "通过后再次出现未通过",
        "view_without_ac": "浏览较多但还没有通过记录",
        "due_overdue": "复习已经到期或逾期",
        "stalled_module": "学习模块推进停滞",
        "data_insufficient": "当前数据不足以形成强结论",
    }.get(str(signal_type), "学习记录显示需要关注的信号")


def build_rule_fallback(context: Mapping[str, Any]) -> dict[str, Any]:
    """Create a deterministic result with the same display shape as AI output."""
    summary = context.get("summary", {}) if isinstance(context, Mapping) else {}
    if not isinstance(summary, Mapping):
        summary = {}
    completed = summary.get("completed_problem_count")
    active_days = summary.get("active_days")
    total_ac = summary.get("total_ac")
    total_wa = summary.get("total_wa")
    parts: list[str] = []
    if isinstance(completed, int):
        parts.append(f"已完成 {completed} 道题的学习记录")
    if isinstance(active_days, int):
        parts.append(f"近窗口内有 {active_days} 天学习活动")
    if isinstance(total_ac, int) and isinstance(total_wa, int):
        parts.append(f"提交记录中通过 {total_ac} 次、未通过 {total_wa} 次")
    result: dict[str, Any] = {
        "summary": "规则分析：" + ("；".join(parts) if parts else "当前学习数据较少，建议继续记录学习行为。"),
        "strengths": [],
        "weaknesses": [],
        "actions": [],
        "confidence": "medium" if parts else "low",
        "data_gaps": [],
    }
    signals = context.get("signals", []) if isinstance(context, Mapping) else []
    if not isinstance(signals, list):
        signals = []
    for index, signal in enumerate(signals[:MAX_WEAKNESSES], 1):
        if not isinstance(signal, Mapping):
            continue
        trace_map = context.get("trace_map", {}) if isinstance(context, Mapping) else {}
        refs = [
            str(ref)
            for ref, entry in trace_map.items()
            if isinstance(entry, Mapping)
            and str(entry.get("entity_type")) == str(signal.get("entity_type"))
            and str(entry.get("entity_id")) == str(signal.get("entity_id"))
            and SUPPORT_REF_RE.fullmatch(str(ref))
        ][:MAX_SUPPORT_REFS]
        if not refs:
            continue
        label = _signal_label(signal.get("signal_type"))
        result["weaknesses"].append({
            "id": f"weakness-{index}",
            "title": label,
            "explanation": f"确定性规则检测到：{label}。建议结合依据逐项复盘，不把这条信号当作最终能力判断。",
            "support_refs": refs,
        })
        result["actions"].append({
            "title": "优先复盘这组记录",
            "description": "查看相关题目的错误原因，完成一次独立重做后再记录结果。",
            "support_refs": refs,
            "weakness_id": f"weakness-{index}",
            "basis": "data",
            "confidence": str(signal.get("confidence", "medium"))
            if str(signal.get("confidence", "medium")) in {"low", "medium", "high"}
            else "medium",
        })
    if not result["weaknesses"]:
        result["strengths"].append("当前没有检测到需要立即处理的高优先级规则信号。")
    quality = context.get("data_quality", {}) if isinstance(context, Mapping) else {}
    if isinstance(quality, Mapping):
        if quality.get("status") not in (None, "ok", "complete"):
            result["data_gaps"].append("学习数据覆盖有限，以上结论只适合做当前阶段的参考。")
        omitted = quality.get("omitted")
        if isinstance(omitted, Mapping) and any(int(value or 0) > 0 for value in omitted.values() if isinstance(value, (int, float))):
            result["data_gaps"].append("上下文已按预算裁剪，未列出的历史记录没有参与本次分析。")
    trace_map = context.get("trace_map", {}) if isinstance(context, Mapping) else {}
    result["_support_trace"] = _resolve_support_trace(result, trace_map if isinstance(trace_map, Mapping) else {})
    return {"source": "rules-v2", "message": "当前展示确定性规则分析，AI 恢复后可重新生成解释。", "result": result}
