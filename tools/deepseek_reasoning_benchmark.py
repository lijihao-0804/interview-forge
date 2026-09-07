"""One-shot, fixed-context DeepSeek reasoning A/B benchmark.

This operational harness intentionally performs exactly ten top-level model
calls in ABABABABAB order. It never repairs an invalid response and never
changes process environment or the running web service.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import statistics
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import ai_coach  # noqa: E402
from tools import study_server as server  # noqa: E402
from tools.context_compiler import compile_learning_context  # noqa: E402
from tools.learning_analytics import build_learning_analytics  # noqa: E402


METRICS = (
    "transport_ttft_ms",
    "time_to_first_content_token_ms",
    "unattributed_pre_content_ms",
    "content_generation_ms",
    "model_total_ms",
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "content_tokens",
    "content_tokens_per_sec",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def percentile_nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def summarize_numbers(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {name: None for name in ("min", "median", "mean", "p90", "max")}
    return {
        "min": round(min(values), 3),
        "median": round(statistics.median(values), 3),
        "mean": round(statistics.fmean(values), 3),
        "p90": round(float(percentile_nearest_rank(values, 0.9)), 3),
        "max": round(max(values), 3),
    }


def aggregate_group(samples: list[Mapping[str, Any]]) -> dict[str, Any]:
    completed = len(samples)
    valid = sum(bool(item.get("validation", {}).get("succeeded")) for item in samples)
    failure_categories: dict[str, int] = {}
    for item in samples:
        category = item.get("validation", {}).get("failure_category")
        if category:
            failure_categories[str(category)] = failure_categories.get(str(category), 0) + 1
    return {
        "sample_count": completed,
        "validation_success_rate": round(valid / completed, 4) if completed else None,
        "failure_categories": failure_categories,
        "metrics": {
            metric: summarize_numbers([
                float(item["timing"][metric])
                for item in samples
                if isinstance(item.get("timing", {}).get(metric), (int, float))
            ])
            for metric in METRICS
        },
    }


def aggregate_quality(samples: list[Mapping[str, Any]]) -> dict[str, Any]:
    qualities = [item.get("quality") for item in samples if isinstance(item.get("quality"), Mapping) and item.get("quality")]
    themes = ("review_backlog", "completion", "activity", "wrong_answers", "data_quality")
    count_names = ("strengths", "weaknesses", "actions", "data_gaps")
    titles: dict[str, int] = {}
    for quality in qualities:
        for title in [*quality.get("weakness_titles", []), *quality.get("action_titles", [])]:
            normalized = _normalized_text(title)
            if normalized:
                titles[normalized] = titles.get(normalized, 0) + 1
    return {
        "analyzable_samples": len(qualities),
        "mean_item_counts": {
            name: round(statistics.fmean([
                float(item.get("item_counts", {}).get(name, 0)) for item in qualities
            ]), 3) if qualities else None
            for name in count_names
        },
        "theme_sample_coverage": {
            theme: round(sum(bool(item.get("theme_coverage", {}).get(theme)) for item in qualities) / len(qualities), 4)
            if qualities else None
            for theme in themes
        },
        "support_ref_valid_rate": round(
            sum(item.get("support_refs", {}).get("valid", 0) for item in qualities)
            / sum(item.get("support_refs", {}).get("total", 0) for item in qualities), 4
        ) if sum(item.get("support_refs", {}).get("total", 0) for item in qualities) else None,
        "action_required_fields_complete_rate": round(
            sum(item.get("action_required_fields_complete", 0) for item in qualities)
            / sum(item.get("item_counts", {}).get("actions", 0) for item in qualities), 4
        ) if sum(item.get("item_counts", {}).get("actions", 0) for item in qualities) else None,
        "exact_title_duplicates_total": sum(item.get("exact_title_duplicates", 0) for item in qualities),
        "raw_output_chars": summarize_numbers([
            float(item.get("raw_output_chars", 0)) for item in qualities
        ]),
        "most_frequent_normalized_titles": sorted(titles.items(), key=lambda item: (-item[1], item[0]))[:8],
    }


def _normalized_text(value: Any) -> str:
    return "".join(str(value or "").lower().split())


def quality_summary(payload: Mapping[str, Any], available_refs: set[str], raw_chars: int) -> dict[str, Any]:
    weaknesses = payload.get("weaknesses") if isinstance(payload.get("weaknesses"), list) else []
    actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    strengths = payload.get("strengths") if isinstance(payload.get("strengths"), list) else []
    data_gaps = payload.get("data_gaps") if isinstance(payload.get("data_gaps"), list) else []
    titles = [str(item.get("title", "")) for item in weaknesses if isinstance(item, Mapping)]
    action_titles = [str(item.get("title", "")) for item in actions if isinstance(item, Mapping)]
    combined = " ".join([str(payload.get("summary", "")), *titles, *action_titles])
    themes = {
        "review_backlog": any(word in combined for word in ("复习", "逾期", "积压")),
        "completion": any(word in combined for word in ("完成", "进度", "轮次")),
        "activity": any(word in combined for word in ("活跃", "连续", "学习天数")),
        "wrong_answers": any(word in combined for word in ("错题", "未通过", "WA", "错误")),
        "data_quality": any(word in combined for word in ("数据", "缺失", "样本", "覆盖")),
    }
    support_refs = [
        str(ref)
        for section in (weaknesses, actions)
        for item in section
        if isinstance(item, Mapping)
        for ref in (item.get("support_refs") or [])
    ]
    valid_refs = sum(ref in available_refs for ref in support_refs)
    complete_actions = 0
    for item in actions:
        if not isinstance(item, Mapping):
            continue
        required = all(item.get(key) for key in ("title", "description", "basis", "confidence"))
        support_ok = item.get("basis") == "heuristic" or bool(item.get("support_refs"))
        complete_actions += bool(required and support_ok)
    normalized_titles = [_normalized_text(item) for item in [*titles, *action_titles] if item]
    duplicate_count = len(normalized_titles) - len(set(normalized_titles))
    return {
        "item_counts": {
            "strengths": len(strengths), "weaknesses": len(weaknesses),
            "actions": len(actions), "data_gaps": len(data_gaps),
        },
        "weakness_titles": titles,
        "action_titles": action_titles,
        "theme_coverage": themes,
        "support_refs": {
            "total": len(support_refs), "valid": valid_refs,
            "valid_rate": round(valid_refs / len(support_refs), 4) if support_refs else None,
        },
        "action_required_fields_complete": complete_actions,
        "action_required_fields_complete_rate": round(complete_actions / len(actions), 4) if actions else None,
        "exact_title_duplicates": duplicate_count,
        "raw_output_chars": raw_chars,
    }


def _failure_category(exc: BaseException) -> str:
    message = str(exc).lower()
    if "not json" in message:
        return "json_parse"
    if "support" in message or "reference" in message or "unknown ref" in message:
        return "support_refs"
    if "too long" in message or "bounds" in message:
        return "bounds"
    if "schema" in message or "field" in message or "expected" in message:
        return "schema"
    return "validation_other"


def analyze_existing(path: Path, output_dir: Path) -> Path:
    """Derive comparable quality/usage facts without making a model call."""
    original = json.loads(path.read_text(encoding="utf-8"))
    context, context_json, context_hash = freeze_context()
    source_context_hash = str(original.get("frozen_context", {}).get("hash", ""))
    available_refs = set(context.get("trace_map", {}))
    samples = copy.deepcopy(original.get("samples", []))
    for sample in samples:
        timing = sample.setdefault("timing", {})
        if sample.get("group") == "B" and timing.get("output_tokens") is not None:
            # DeepSeek's documented disabled mode has no reasoning stream. In
            # this controlled arm, all provider-reported output is content.
            timing["reasoning_tokens"] = 0
            timing["content_tokens"] = timing["output_tokens"]
            generation_ms = timing.get("content_generation_ms")
            timing["content_tokens_per_sec"] = (
                round(timing["content_tokens"] / (generation_ms / 1000), 3)
                if isinstance(generation_ms, (int, float)) and generation_ms > 0 else None
            )
            timing["content_tokens_derivation"] = "output_tokens; thinking explicitly disabled"
        raw = sample.get("raw_output")
        try:
            extracted = ai_coach._extract_json_payload(raw)
            if isinstance(extracted, Mapping):
                sample["quality"] = quality_summary(extracted, available_refs, len(raw) if isinstance(raw, str) else 0)
            try:
                payload = ai_coach._normalize_unstructured_payload(extracted)
                ai_coach.validate_insight_payload(payload, context)
                sample["validation"] = {"succeeded": True, "failure_category": None}
            except ai_coach._InvalidAIOutput as exc:
                sample["validation"] = {
                    "succeeded": False, "failure_category": _failure_category(exc),
                    "error_type": type(exc).__name__,
                }
        except ai_coach._InvalidAIOutput as exc:
            sample["validation"] = {
                "succeeded": False, "failure_category": _failure_category(exc),
                "error_type": type(exc).__name__,
            }
    groups = {name: [item for item in samples if item.get("group") == name] for name in ("A", "B")}
    analysis = {
        "analysis_version": "deepseek-reasoning-ab-analysis-v1",
        "source_artifact": path.name,
        "benchmark_id": original.get("benchmark_id"),
        "no_additional_model_calls": True,
        "frozen_context_reverified": {
            "source_hash": source_context_hash,
            "source_chars": original.get("frozen_context", {}).get("chars"),
            "all_source_samples_match": original.get("frozen_context", {}).get("all_samples_match"),
            "current_recompile_hash": context_hash,
            "current_recompile_chars": len(context_json),
            "exact_recompile_matches": context_hash == source_context_hash,
            "exact_recompile_note": "as_of is time-dependent; source hash remains the proof shared by all ten samples",
        },
        "samples": samples,
        "groups": {
            name: {**aggregate_group(items), "quality": aggregate_quality(items)}
            for name, items in groups.items()
        },
    }
    output_path = output_dir / f"{path.stem}.analysis-v2.json"
    if output_path.exists():
        raise RuntimeError("analysis artifact already exists; refusing to overwrite")
    output_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _select_real_learning_db() -> Path:
    candidates = []
    for path in server.USERS_DIR.glob("*/hot100-study.db"):
        try:
            import sqlite3
            with sqlite3.connect(path) as connection:
                count = int(connection.execute("SELECT COUNT(*) FROM submissions").fetchone()[0])
            candidates.append((count, path))
        except Exception:
            continue
    if not candidates:
        raise RuntimeError("no existing learning database available")
    return max(candidates, key=lambda item: item[0])[1]


def freeze_context() -> tuple[dict[str, Any], str, str]:
    db_path = _select_real_learning_db()
    analytics = build_learning_analytics(
        db_path,
        server.PROBLEM_BY_ID,
        server.load_library_manifest(),
        allowed_db_root=server.USERS_DIR,
    )
    full_context = compile_learning_context(analytics, "learning_diagnosis", budget_tier="small")
    frozen_context = copy.deepcopy(full_context)
    llm_context_json = ai_coach._context_json(frozen_context)
    return frozen_context, llm_context_json, sha256_text(llm_context_json)


def run_slot(
    *, benchmark_id: str, slot: int, group: str, context: Mapping[str, Any],
    context_json: str, context_hash: str, config: ai_coach.AIConfig,
) -> dict[str, Any]:
    thinking_mode = "enabled" if group == "A" else "disabled"
    native = ai_coach._uses_native_structured_output(config)
    if native:
        raise RuntimeError("benchmark requires the DeepSeek streaming path")
    request_config, config_hash = ai_coach._request_config_summary(
        config, native_structured=False, thinking_mode=thinking_mode
    )
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    event_base = {
        "benchmark_id": benchmark_id, "slot": slot, "group": group, "attempt": 1,
        "context_hash": context_hash, "context_chars": len(context_json),
        "request_config": request_config, "request_config_hash": config_hash,
    }
    ai_coach.debug_ai_event("benchmark_slot_started", task_id=benchmark_id, **event_base)
    sample: dict[str, Any] = {**event_base, "started_at": started_at}
    raw_text = ""
    try:
        model = ai_coach._make_chat_model(config, thinking_mode=thinking_mode)
        raw, timing = ai_coach._stream_deepseek_once(model, ai_coach._messages(context_json, repair=False))
        raw_text = raw.content
        sample["timing"] = timing
        try:
            payload = ai_coach._extract_json_payload(raw)
            payload = ai_coach._normalize_unstructured_payload(payload)
            validated = ai_coach.validate_insight_payload(payload, context)
            public_payload = {key: value for key, value in validated.items() if not key.startswith("_")}
            sample["validation"] = {"succeeded": True, "failure_category": None}
            sample["quality"] = quality_summary(payload, set(context.get("trace_map", {})), len(raw_text))
            sample["validated_output"] = public_payload
        except ai_coach._InvalidAIOutput as exc:
            sample["validation"] = {
                "succeeded": False, "failure_category": _failure_category(exc),
                "error_type": type(exc).__name__,
            }
            sample["quality"] = {}
        sample["raw_output"] = ai_coach._safe_raw_log(raw_text)
    except Exception as exc:
        sample.setdefault("timing", {})
        sample["validation"] = {
            "succeeded": False, "failure_category": "provider_error",
            "error_type": type(exc).__name__,
        }
    ai_coach.debug_ai_event(
        "benchmark_slot_finished", task_id=benchmark_id,
        **event_base, timing=sample.get("timing", {}), validation=sample["validation"],
        quality=sample.get("quality", {}),
    )
    return sample


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".maintenance")
    parser.add_argument("--analyze-existing", type=Path)
    args = parser.parse_args()
    if args.analyze_existing:
        output_path = analyze_existing(args.analyze_existing, args.output_dir)
        print(json.dumps({"analysis_artifact": str(output_path), "model_calls": 0}, ensure_ascii=False))
        return 0
    config = ai_coach.load_ai_config()
    if not config.configured or not config.enabled:
        raise RuntimeError("current AI configuration is not ready")
    if config.model != "deepseek-v4-flash" or not config.thinking_enabled or config.reasoning_effort != "high":
        raise RuntimeError("current configuration does not match benchmark A contract")

    initial_summary, initial_hash = ai_coach._request_config_summary(config, native_structured=False)
    frozen_context, context_json, context_hash = freeze_context()
    if context_json != ai_coach._context_json(frozen_context):
        raise RuntimeError("frozen context is not deterministic")
    benchmark_id = f"ds-reasoning-ab-{uuid.uuid4().hex[:12]}"
    samples = []
    for slot in range(1, 11):
        group = "A" if slot % 2 else "B"
        samples.append(run_slot(
            benchmark_id=benchmark_id, slot=slot, group=group, context=frozen_context,
            context_json=context_json, context_hash=context_hash, config=config,
        ))

    final_config = ai_coach.load_ai_config()
    final_summary, final_hash = ai_coach._request_config_summary(final_config, native_structured=False)
    groups = {name: [item for item in samples if item["group"] == name] for name in ("A", "B")}
    result = {
        "benchmark_version": "deepseek-reasoning-ab-v1",
        "benchmark_id": benchmark_id,
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "call_budget": {"planned": 10, "executed": len(samples), "repair_calls": 0},
        "order": "ABABABABAB",
        "p90_method": "nearest-rank; ceil(0.90*n), therefore max when n=5",
        "frozen_context": {
            "llm_context_version": ai_coach.LLM_CONTEXT_VERSION,
            "hash": context_hash, "chars": len(context_json),
            "all_samples_match": all(item["context_hash"] == context_hash for item in samples),
        },
        "configs": {
            "A": samples[0]["request_config"], "A_hash": samples[0]["request_config_hash"],
            "B": samples[1]["request_config"], "B_hash": samples[1]["request_config_hash"],
            "only_intended_difference": "thinking_mode enabled -> disabled",
        },
        "default_config_unchanged": {
            "unchanged": initial_hash == final_hash and initial_summary == final_summary,
            "before_hash": initial_hash, "after_hash": final_hash,
        },
        "samples": samples,
        "groups": {name: aggregate_group(items) for name, items in groups.items()},
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"deepseek-reasoning-ab-{benchmark_id}.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    ai_coach.debug_ai_event(
        "benchmark_completed", task_id=benchmark_id, benchmark_id=benchmark_id,
        call_budget=result["call_budget"], frozen_context=result["frozen_context"],
        configs=result["configs"], default_config_unchanged=result["default_config_unchanged"],
        groups=result["groups"], artifact_name=output_path.name,
    )
    print(json.dumps({
        "benchmark_id": benchmark_id, "artifact": str(output_path),
        "context_hash": context_hash, "context_chars": len(context_json),
        "executed": len(samples), "default_config_unchanged": result["default_config_unchanged"]["unchanged"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
