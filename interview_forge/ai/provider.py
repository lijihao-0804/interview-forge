"""Provider-side content and usage normalization for AI streaming.

The facade re-exports these helpers so existing provider/test hooks remain
valid while the streaming implementation has one focused home.
"""
from __future__ import annotations

import time
from typing import Any, Mapping

from interview_forge.ai.models import StreamEnvelope

def _content_text(value: Any) -> str:
    """Extract answer text only; reasoning blocks are intentionally excluded."""
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, Mapping) and str(item.get("type", "text")) in {"text", "output_text"}:
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _usage_from(value: Any) -> dict[str, int]:
    """Normalize LangChain/OpenAI/DeepSeek usage names without inventing values."""
    sources: list[Mapping[str, Any]] = []
    for candidate in (
        getattr(value, "usage_metadata", None),
        getattr(value, "response_metadata", None),
        getattr(value, "additional_kwargs", None),
    ):
        if isinstance(candidate, Mapping):
            sources.append(candidate)
            nested = candidate.get("token_usage") or candidate.get("usage")
            if isinstance(nested, Mapping):
                sources.append(nested)
    aliases = {
        "input_tokens": ("input_tokens", "prompt_tokens"),
        "output_tokens": ("output_tokens", "completion_tokens"),
        "reasoning_tokens": ("reasoning_tokens",),
    }
    result: dict[str, int] = {}
    for target, names in aliases.items():
        for source in sources:
            value_found = next((source.get(name) for name in names if source.get(name) is not None), None)
            if isinstance(value_found, (int, float)) and value_found >= 0:
                result[target] = int(value_found)
                break
            details = source.get("output_token_details") or source.get("completion_tokens_details")
            if target == "reasoning_tokens" and isinstance(details, Mapping):
                reasoning = details.get("reasoning") or details.get("reasoning_tokens")
                if isinstance(reasoning, (int, float)) and reasoning >= 0:
                    result[target] = int(reasoning)
                    break
        if target in result:
            continue
    return result



def _stream_deepseek_once(model: Any, messages: list[Any]) -> tuple[StreamEnvelope, dict[str, Any]]:
    """Consume a DeepSeek stream fully while retaining only final answer content."""
    started = time.perf_counter()
    first_chunk_at: float | None = None
    reasoning_started_at: float | None = None
    reasoning_finished_at: float | None = None
    content_started_at: float | None = None
    last_content_at: float | None = None
    chunks = 0
    reasoning_chunks = 0
    content_chunks = 0
    content_parts: list[str] = []
    usage: dict[str, int] = {}
    for chunk in model.stream(messages):
        chunks += 1
        now = time.perf_counter()
        if first_chunk_at is None:
            first_chunk_at = now
        answer_text = _content_text(getattr(chunk, "content", ""))
        additional = getattr(chunk, "additional_kwargs", None)
        reasoning = additional.get("reasoning_content") if isinstance(additional, Mapping) else None
        if reasoning:
            reasoning_chunks += 1
            if reasoning_started_at is None:
                reasoning_started_at = now
        if answer_text:
            content_chunks += 1
            if content_started_at is None:
                content_started_at = now
                if reasoning_started_at is not None:
                    reasoning_finished_at = now
            last_content_at = now
            content_parts.append(answer_text)
        current_usage = _usage_from(chunk)
        if current_usage:
            usage.update(current_usage)
    ended = time.perf_counter()
    if reasoning_started_at is not None and reasoning_finished_at is None:
        reasoning_finished_at = ended
    transport_ttft_ms = (
        round((first_chunk_at - started) * 1000, 2) if first_chunk_at is not None else None
    )
    time_to_first_content_ms = (
        round((content_started_at - started) * 1000, 2) if content_started_at is not None else None
    )
    unattributed_pre_content_ms = (
        round(max(0.0, time_to_first_content_ms - transport_ttft_ms), 2)
        if time_to_first_content_ms is not None and transport_ttft_ms is not None else None
    )
    reasoning_ms = (
        round((reasoning_finished_at - reasoning_started_at) * 1000, 2)
        if reasoning_started_at is not None and reasoning_finished_at is not None else None
    )
    time_to_reasoning_start_ms = (
        round((reasoning_started_at - started) * 1000, 2) if reasoning_started_at is not None else None
    )
    content_generation_ms = (
        round(max(0.0, (last_content_at - content_started_at) * 1000), 2)
        if content_started_at is not None and last_content_at is not None else None
    )
    metrics: dict[str, Any] = {
        # Legacy fields remain queryable, now with an explicit definition.
        "ttft_ms": time_to_first_content_ms,
        "ttft_definition": "time_to_first_content_token",
        "generation_ms": content_generation_ms,
        "generation_definition": "first_to_last_content_chunk",
        "transport_ttft_ms": transport_ttft_ms,
        "time_to_reasoning_start_ms": time_to_reasoning_start_ms,
        "reasoning_ms": reasoning_ms,
        "reasoning_visibility": (
            "stream_content" if reasoning_started_at is not None
            else "usage_only_not_exposed_by_langchain" if usage.get("reasoning_tokens") is not None
            else "unavailable"
        ),
        "unattributed_pre_content_ms": unattributed_pre_content_ms,
        "time_to_first_content_token_ms": time_to_first_content_ms,
        "content_generation_ms": content_generation_ms,
        "model_total_ms": round((ended - started) * 1000, 2),
        "chunk_count": chunks,
        "reasoning_chunk_count": reasoning_chunks,
        "content_chunk_count": content_chunks,
        "usage_status": "available" if usage else "unavailable",
        **usage,
    }
    output_tokens = usage.get("output_tokens")
    reasoning_tokens = usage.get("reasoning_tokens")
    content_tokens: int | None = None
    if output_tokens is not None and reasoning_tokens is not None and output_tokens >= reasoning_tokens:
        # The SDK reports reasoning as completion-token details nested under
        # output/completion usage, so the remainder is visible answer content.
        content_tokens = output_tokens - reasoning_tokens
        metrics["content_tokens"] = content_tokens
        metrics["output_tokens_definition"] = "completion_total_including_reasoning"
    else:
        metrics["output_tokens_definition"] = "provider_reported_unconfirmed"
    if output_tokens is not None and content_generation_ms is not None and content_generation_ms > 0:
        metrics["throughput_tokens_per_sec"] = round(output_tokens / (content_generation_ms / 1000), 3)
        metrics["throughput_definition"] = "legacy_output_tokens_per_content_generation_second"
    else:
        metrics["throughput_tokens_per_sec"] = None
        metrics["throughput_definition"] = "legacy_output_tokens_per_content_generation_second"
    if reasoning_tokens is not None and reasoning_ms is not None and reasoning_ms > 0:
        metrics["reasoning_tokens_per_sec"] = round(reasoning_tokens / (reasoning_ms / 1000), 3)
    else:
        metrics["reasoning_tokens_per_sec"] = None
    if content_tokens is not None and content_generation_ms is not None and content_generation_ms > 0:
        metrics["content_tokens_per_sec"] = round(content_tokens / (content_generation_ms / 1000), 3)
    else:
        metrics["content_tokens_per_sec"] = None
    return StreamEnvelope("".join(content_parts), usage), metrics


