"""AI coach generation and provider-call orchestration.

The runtime-facing wrappers below resolve through the facade at call time.  This
keeps the historical ai_coach patch points working while the implementation
lives in this focused module.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any
from urllib.parse import urlparse

from interview_forge.ai.config import AIConfig
from interview_forge.ai.errors import AIServiceError
from interview_forge.ai.models import StreamEnvelope
from interview_forge.ai.prompts import (
    MAX_ACTIONS, MAX_DATA_GAPS, MAX_MODEL_OUTPUT_CHARS, MAX_RESULT_CHARS,
    MAX_STRENGTHS, MAX_SUPPORT_REFS, MAX_WEAKNESSES, PROMPT_VERSION,
    OUTPUT_CONTRACT, SYSTEM_PROMPT, LLM_CONTEXT_VERSION,
)
from interview_forge.ai.provider import _content_text, _stream_deepseek_once, _usage_from
from interview_forge.ai.validation import (
    _InvalidAIOutput, _bounded_string_list, _bounded_text, _plain_model_value,
    _pydantic_schema, build_rule_fallback, validate_insight_payload,
)
from interview_forge.ai.context_projection import _context_json, _model_projection_debug


def _runtime():
    from interview_forge.ai import ai_coach
    return ai_coach


def _dependencies_available():
    return _runtime()._dependencies_available()


def load_ai_config():
    return _runtime().load_ai_config()


def model_key(config=None):
    return _runtime().model_key(config)


def debug_ai_event(event, **fields):
    return _runtime().debug_ai_event(event, **fields)


def _make_chat_model(config: AIConfig, *, thinking_mode: str | None = None):
    return _runtime()._make_chat_model(config, thinking_mode=thinking_mode)


_StreamEnvelope = StreamEnvelope

def _normalize_unstructured_payload(payload: Any) -> Any:
    """Safely cap minor DeepSeek JSON overflows without inventing content."""
    plain = _plain_model_value(payload)
    if not isinstance(plain, Mapping):
        return plain
    normalized: dict[str, Any] = {
        "summary": _bounded_text(plain.get("summary"), 600),
        "strengths": _bounded_string_list(plain.get("strengths"), MAX_STRENGTHS, 120),
        "weaknesses": [],
        "actions": [],
        "confidence": plain.get("confidence"),
        "data_gaps": _bounded_string_list(plain.get("data_gaps"), MAX_DATA_GAPS, 160),
    }
    for item in list(plain.get("weaknesses") or [])[:MAX_WEAKNESSES]:
        if isinstance(item, Mapping):
            normalized["weaknesses"].append({
                "id": _bounded_text(item.get("id"), 64),
                "title": _bounded_text(item.get("title"), 120),
                "explanation": _bounded_text(item.get("explanation"), 500),
                "support_refs": list(item.get("support_refs") or [])[:MAX_SUPPORT_REFS],
            })
    for item in list(plain.get("actions") or [])[:MAX_ACTIONS]:
        if isinstance(item, Mapping):
            normalized["actions"].append({
                "title": _bounded_text(item.get("title"), 120),
                "description": _bounded_text(item.get("description"), 600),
                "support_refs": list(item.get("support_refs") or [])[:MAX_SUPPORT_REFS],
                "weakness_id": _bounded_text(item.get("weakness_id"), 64),
                "basis": _bounded_text(item.get("basis"), 16),
                "confidence": _bounded_text(item.get("confidence"), 16),
            })
    return normalized


def _messages(context_json: str, repair: bool = False) -> list[Any]:
    human = (
        f"{OUTPUT_CONTRACT}\n\n下面是本次唯一可用的 LLMContext v2 资料：\n"
        f"<llm-context-v2>{context_json}</llm-context-v2>"
    )
    if repair:
        human = (
            "上一轮输出没有通过服务端结构与证据校验。请丢弃上一轮输出，重新根据同一份"
            " LLMContext v2 只返回符合契约的 JSON。不要解释修复过程。\n\n" + human
        )
    return [("system", SYSTEM_PROMPT), ("human", human)]


def _make_chat_model_impl(config: AIConfig, *, thinking_mode: str | None = None) -> Any:
    # All provider-specific construction is kept in this single function.
    if thinking_mode not in {None, "enabled", "disabled"}:
        raise ValueError("thinking_mode must be enabled, disabled, or None")
    try:
        from langchain_openai import ChatOpenAI
    except (ImportError, ModuleNotFoundError) as exc:
        raise AIServiceError("not_configured", "AI 分析依赖尚未安装。") from exc
    kwargs: dict[str, Any] = {
        "model": config.model,
        "api_key": config.api_key,
        "timeout": config.request_timeout_seconds,
        "max_retries": 0,
    }
    if config.base_url:
        kwargs["base_url"] = config.base_url
    if config.wire_api == "responses":
        kwargs["use_responses_api"] = True
        kwargs["store"] = False
        kwargs["output_version"] = "responses/v1"
    if config.actor_authorization:
        kwargs["default_headers"] = {
            "x-openai-actor-authorization": config.actor_authorization,
        }
    if config.reasoning_effort in {"low", "medium", "high"}:
        kwargs["reasoning_effort"] = config.reasoning_effort
    effective_thinking_mode = thinking_mode
    if effective_thinking_mode is None and config.thinking_enabled:
        effective_thinking_mode = "enabled"
    if effective_thinking_mode is not None:
        kwargs["extra_body"] = {"thinking": {"type": effective_thinking_mode}}
    if not _uses_native_structured_output(config):
        # ChatOpenAI maps this to stream_options.include_usage when supported.
        kwargs["stream_usage"] = True
    try:
        return ChatOpenAI(**kwargs)
    except Exception as exc:
        raise AIServiceError("not_configured", "AI 服务配置不可用。") from exc


def _uses_native_structured_output(config: AIConfig) -> bool:
    """DeepSeek currently rejects response_format; keep it for OpenAI-compatible peers."""
    try:
        hostname = (urlparse(config.base_url).hostname or "").lower()
    except ValueError:
        hostname = ""
    return hostname not in {"api.deepseek.com", "api.deepseek.cn"}


def _invoke_once(
    model: Any,
    messages: list[Any],
    *,
    native_structured_output: bool = True,
) -> Any:
    """Use structured output first, with a single raw ChatModel fallback."""
    if not native_structured_output:
        return model.invoke(messages)
    structured = None
    try:
        structured = model.with_structured_output(_pydantic_schema())
    except AIServiceError:
        raise
    except Exception:
        structured = None
    target = structured or model
    return target.invoke(messages)


def _request_config_summary(
    config: AIConfig,
    *,
    native_structured: bool,
    thinking_mode: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Return a stable, credential-free request configuration fingerprint."""
    if thinking_mode not in {None, "enabled", "disabled"}:
        raise ValueError("thinking_mode must be enabled, disabled, or None")
    effective_thinking_mode = thinking_mode
    if effective_thinking_mode is None:
        effective_thinking_mode = "enabled" if config.thinking_enabled else "unspecified"
    summary: dict[str, Any] = {
        "model_key": model_key(config),
        "stream": not native_structured,
        "temperature": None,
        "top_p": None,
        "max_tokens": None,
        "reasoning_enabled": effective_thinking_mode == "enabled",
        "thinking_mode": effective_thinking_mode,
        "reasoning_effort": config.reasoning_effort or None,
        "reasoning_budget": None,
        "response_format": "native_structured" if native_structured else "plain_json",
        "prompt_template_version": PROMPT_VERSION,
    }
    serialized = json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return summary, hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _extract_json_payload(value: Any) -> Any:
    if hasattr(value, "content"):
        value = getattr(value, "content")
    plain = _plain_model_value(value)
    if isinstance(plain, Mapping):
        return plain
    if isinstance(plain, list):
        parts = []
        for item in plain:
            if isinstance(item, Mapping) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                parts.append(str(item))
        text = "".join(parts)
    else:
        text = plain if isinstance(plain, str) else str(plain)
    if len(text) > MAX_MODEL_OUTPUT_CHARS:
        raise _InvalidAIOutput("model output too long")
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _InvalidAIOutput("model output is not JSON") from exc


def _classify_provider_exception(exc: BaseException) -> AIServiceError:
    status_code = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    name = type(exc).__name__.lower()
    if isinstance(exc, TimeoutError) or "timeout" in name:
        return AIServiceError("timeout", "AI 分析响应超时，请稍后重试。")
    if status_code == 429 or "ratelimit" in name or "rate_limit" in name:
        return AIServiceError("rate_limited", "AI 服务当前请求较多，请稍后重试。", status=HTTPStatus.TOO_MANY_REQUESTS)
    if isinstance(status_code, int) and status_code >= 500:
        return AIServiceError("provider_error", "AI 服务暂时不可用，请稍后重试。")
    if isinstance(status_code, int) and status_code in {401, 403}:
        return AIServiceError("not_configured", "AI 服务配置不可用。")
    return AIServiceError("provider_error", "AI 分析暂时失败，请稍后重试。")


def _safe_raw_log(value: Any) -> Any:
    """Prevent a provider echo from putting backend machine IDs in debug JSONL."""
    try:
        serialized = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        serialized = str(value)
    if any(token in serialized for token in ("evidence:", "signal:", "metric:")):
        return {"redacted": True, "reason": "internal_id_pattern"}
    return value


def _debug_content_metadata(value: Any) -> dict[str, Any]:
    """Return correlation metadata without retaining the supplied content."""
    if not os.environ.get("AI_DEBUG_LOG_PATH", "").strip():
        return {"chars": 0, "sha256": ""}
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
    except (TypeError, ValueError):
        serialized = str(value)
    return {
        "chars": len(serialized),
        "sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
    }


def generate_ai_insight(
    context: Mapping[str, Any],
    config: AIConfig | None = None,
    *,
    debug_id: str = "",
    before_model_request: Any = None,
) -> dict[str, Any]:
    """Call one LangChain ChatModel, then at most one controlled repair call."""
    config = config or load_ai_config()
    fallback = build_rule_fallback(context)
    if not config.enabled:
        raise AIServiceError("disabled", "AI 分析暂未启用。", fallback=fallback)
    if not config.configured or not _dependencies_available():
        raise AIServiceError("not_configured", "AI 分析尚未完成配置。", fallback=fallback)
    try:
        model_started = time.perf_counter()
        model = _make_chat_model(config)
        context_json = _context_json(context)
        projection_debug = _model_projection_debug(context, context_json, config)
        debug_ai_event(
            "model_prepared",
            task_id=debug_id,
            elapsed_ms=round((time.perf_counter() - model_started) * 1000, 2),
            context_chars=len(context_json),
            final_context_chars=projection_debug["final_context_chars"],
            estimated_tokens=projection_debug["estimated_tokens"],
            included_sections=projection_debug["included_sections"],
            prompt_hash=projection_debug["prompt_hash"],
            context_hash=projection_debug["context_hash"],
            model_key=projection_debug["model_key"],
            llm_context_version=projection_debug["llm_context_version"],
            sections_not_sent=projection_debug["sections_not_sent"],
            native_structured_output=_uses_native_structured_output(config),
        )
        calls = 0
        request_id = debug_id or uuid.uuid4().hex
        last_invalid: BaseException | None = None
        for repair in (False, True):
            if repair and calls >= 2:
                break
            calls += 1
            try:
                call_started = time.perf_counter()
                attempt = calls
                native_structured = _uses_native_structured_output(config)
                request_config, request_config_hash = _request_config_summary(
                    config, native_structured=native_structured
                )
                if calls == 1 and callable(before_model_request):
                    before_model_request()
                debug_ai_event(
                    "model_request_started", task_id=debug_id, request_id=request_id,
                    attempt=attempt, repair=repair, streaming=not native_structured,
                    request_config=request_config, request_config_hash=request_config_hash,
                )
                if native_structured:
                    raw = _invoke_once(model, _messages(context_json, repair=repair), native_structured_output=True)
                    elapsed = round((time.perf_counter() - call_started) * 1000, 2)
                    usage = _usage_from(raw)
                    timing = {
                        "ttft_ms": elapsed, "ttft_definition": "non_streaming_full_response_time",
                        "generation_ms": None, "generation_definition": "unavailable_non_streaming",
                        "transport_ttft_ms": None, "time_to_reasoning_start_ms": None, "reasoning_ms": None,
                        "reasoning_visibility": "unavailable_non_streaming", "unattributed_pre_content_ms": None,
                        "time_to_first_content_token_ms": None, "content_generation_ms": None,
                        "model_total_ms": elapsed, "chunk_count": 1,
                        "reasoning_chunk_count": 0, "content_chunk_count": 1,
                        "usage_status": "available" if usage else "unavailable", **usage,
                    }
                else:
                    raw, timing = _stream_deepseek_once(model, _messages(context_json, repair=repair))
                debug_ai_event(
                    "model_stream_first_chunk", task_id=debug_id, request_id=request_id,
                    attempt=attempt, repair=repair,
                    transport_ttft_ms=timing.get("transport_ttft_ms"),
                )
                if timing.get("reasoning_ms") is not None:
                    debug_ai_event(
                        "model_reasoning_started", task_id=debug_id, request_id=request_id,
                        attempt=attempt, repair=repair,
                        time_to_reasoning_start_ms=timing.get("time_to_reasoning_start_ms"),
                    )
                    debug_ai_event(
                        "model_reasoning_finished", task_id=debug_id, request_id=request_id,
                        attempt=attempt, repair=repair, reasoning_ms=timing.get("reasoning_ms"),
                    )
                debug_ai_event(
                    "model_first_content_token", task_id=debug_id, request_id=request_id,
                    attempt=attempt, repair=repair,
                    time_to_first_content_token_ms=timing.get("time_to_first_content_token_ms"),
                )
                debug_ai_event(
                    "model_first_token", task_id=debug_id, request_id=request_id,
                    attempt=attempt, repair=repair, ttft_ms=timing["ttft_ms"],
                    ttft_definition=timing["ttft_definition"],
                )
                debug_ai_event(
                    "model_last_token", task_id=debug_id, request_id=request_id,
                    attempt=attempt, repair=repair, generation_ms=timing["generation_ms"],
                    generation_definition=timing["generation_definition"],
                    content_generation_ms=timing.get("content_generation_ms"),
                    chunk_count=timing["chunk_count"],
                )
                raw_plain = raw.content if isinstance(raw, _StreamEnvelope) else _plain_model_value(raw)
                raw_metadata = _debug_content_metadata(raw_plain)
                debug_ai_event(
                    "model_response",
                    task_id=debug_id,
                    request_id=request_id,
                    attempt=attempt,
                    call=calls,
                    repair=repair,
                    elapsed_ms=timing["model_total_ms"],
                    model_total_ms=timing["model_total_ms"],
                    ttft_ms=timing["ttft_ms"],
                    ttft_definition=timing["ttft_definition"],
                    generation_ms=timing["generation_ms"],
                    generation_definition=timing["generation_definition"],
                    transport_ttft_ms=timing.get("transport_ttft_ms"),
                    time_to_reasoning_start_ms=timing.get("time_to_reasoning_start_ms"),
                    reasoning_ms=timing.get("reasoning_ms"),
                    reasoning_visibility=timing.get("reasoning_visibility"),
                    unattributed_pre_content_ms=timing.get("unattributed_pre_content_ms"),
                    time_to_first_content_token_ms=timing.get("time_to_first_content_token_ms"),
                    content_generation_ms=timing.get("content_generation_ms"),
                    chunk_count=timing["chunk_count"],
                    reasoning_chunk_count=timing.get("reasoning_chunk_count", 0),
                    content_chunk_count=timing.get("content_chunk_count", 0),
                    usage={key: timing[key] for key in ("input_tokens", "output_tokens", "reasoning_tokens", "content_tokens") if key in timing},
                    usage_status=timing["usage_status"],
                    throughput_tokens_per_sec=timing.get("throughput_tokens_per_sec"),
                    throughput_definition=timing.get("throughput_definition"),
                    reasoning_tokens_per_sec=timing.get("reasoning_tokens_per_sec"),
                    content_tokens_per_sec=timing.get("content_tokens_per_sec"),
                    output_tokens_definition=timing.get("output_tokens_definition"),
                    request_config_hash=request_config_hash,
                    raw_output_chars=raw_metadata["chars"],
                    raw_output_sha256=raw_metadata["sha256"],
                )
                parse_started = time.perf_counter()
                payload = _extract_json_payload(raw)
                if not _uses_native_structured_output(config):
                    payload = _normalize_unstructured_payload(payload)
                debug_ai_event(
                    "model_response_parsed", task_id=debug_id, request_id=request_id,
                    attempt=attempt, repair=repair,
                    elapsed_ms=round((time.perf_counter() - parse_started) * 1000, 2),
                )
                validation_started = time.perf_counter()
                result = validate_insight_payload(payload, context)
                result_metadata = _debug_content_metadata(result)
                debug_ai_event(
                    "validation_succeeded",
                    task_id=debug_id,
                    request_id=request_id,
                    attempt=attempt,
                    repair=repair,
                    call=calls,
                    elapsed_ms=round((time.perf_counter() - validation_started) * 1000, 2),
                    result_chars=result_metadata["chars"],
                    result_sha256=result_metadata["sha256"],
                )
                return result
            except _InvalidAIOutput as exc:
                debug_ai_event(
                    "validation_failed",
                    task_id=debug_id,
                    request_id=request_id,
                    attempt=calls,
                    call=calls,
                    repair=repair,
                    error_type=type(exc).__name__,
                )
                last_invalid = exc
                if not repair:
                    continue
                raise AIServiceError("invalid_output", "AI 返回结果无法通过本地校验。", fallback=fallback) from exc
            except AIServiceError:
                raise
            except Exception as exc:
                debug_ai_event(
                    "model_failed",
                    task_id=debug_id,
                    request_id=request_id,
                    attempt=calls,
                    call=calls,
                    repair=repair,
                    elapsed_ms=round((time.perf_counter() - call_started) * 1000, 2),
                    error_type=type(exc).__name__,
                    status=getattr(exc, "status_code", None),
                )
                raise _classify_provider_exception(exc) from exc
        raise AIServiceError("invalid_output", "AI 返回结果无法通过本地校验。", fallback=fallback) from last_invalid
    except AIServiceError as exc:
        if exc.fallback is None:
            exc.fallback = fallback
        raise
    except Exception as exc:
        classified = _classify_provider_exception(exc)
        classified.fallback = fallback
        raise classified from exc
