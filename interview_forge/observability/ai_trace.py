"""Metadata-only AI trace recorder.

The existing chat/tool/action tables remain the source of truth for their
respective domains.  This table only records timing, status and usage data;
no prompt, response, memory, context, arguments or result body is accepted.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
from typing import Any

from interview_forge.core.runtime import server_runtime


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) and value >= 0 else None


class TraceRecorder:
    def __init__(
        self,
        *,
        user_db: Path | str,
        trace_id: str,
        session_id: str = "",
        request_id: str = "",
        provider: str = "",
        model: str = "",
        provider_id: str | None = None,
        provider_name: str = "",
        business_key: str = "",
        reasoning_mode: str = "",
        reasoning_effort: str | None = None,
        config_source: str = "env",
    ) -> None:
        self.user_db = Path(user_db)
        self.trace_id = str(trace_id)[:128]
        self.session_id = str(session_id)[:128]
        self.request_id = str(request_id)[:128]
        self.provider = str(provider)[:64]
        self.model = str(model)[:128]
        self.provider_id = str(provider_id or "")[:96]
        self.provider_name = str(provider_name)[:96]
        self.business_key = str(business_key)[:64]
        self.reasoning_mode = str(reasoning_mode)[:24]
        self.reasoning_effort = str(reasoning_effort or "")[:24]
        self.config_source = str(config_source)[:16]

    def record(
        self,
        *,
        event_type: str,
        name: str,
        status: str,
        round_index: int | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        duration_ms: int | float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        error_code: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        try:
            safe_metadata = {
                str(key): value for key, value in (metadata or {}).items()
                if str(key) in {
                    "estimated", "tool_calls_count", "tool_names", "tooling_unavailable", "ttft_ms",
                    "requested_business", "fallback", "fallback_reason",
                    "fallback_provider", "fallback_model",
                }
            }
            safe_metadata.update({
                "provider_id": self.provider_id or None,
                "provider_name": self.provider_name or None,
                "business_key": self.business_key or None,
                "reasoning_mode": self.reasoning_mode or None,
                "reasoning_effort": self.reasoning_effort or None,
                "config_source": self.config_source,
            })
            with closing(server_runtime.connect(self.user_db)) as connection:
                connection.execute(
                    """INSERT INTO ai_trace_events(
                       trace_id, session_id, request_id, event_type, name, status,
                       provider, model, round_index, started_at, finished_at,
                       duration_ms, input_tokens, output_tokens, reasoning_tokens,
                       error_code, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        self.trace_id, self.session_id or None, self.request_id or None,
                        str(event_type)[:32], str(name)[:96], str(status)[:32],
                        self.provider or None, self.model or None,
                        int(round_index) if round_index is not None else None,
                        started_at, finished_at,
                        int(duration_ms) if duration_ms is not None else None,
                        _int(input_tokens), _int(output_tokens), _int(reasoning_tokens),
                        str(error_code)[:64] if error_code else None,
                        json.dumps(safe_metadata, ensure_ascii=False, separators=(",", ":")),
                    ),
                )
                connection.commit()
        except Exception:
            # Telemetry must never change the user-visible AI path.
            return

    def record_llm_round(
        self, *, round_index: int, status: str, duration_ms: int | float,
        usage: dict[str, Any] | None = None, error_code: str | None = None,
        started_at: str | None = None, finished_at: str | None = None,
    ) -> None:
        usage = usage or {}
        self.record(
            event_type="llm", name="model_round", status=status,
            round_index=round_index, started_at=started_at or utc_now_iso(),
            finished_at=finished_at or utc_now_iso(),
            duration_ms=duration_ms, input_tokens=_int(usage.get("input_tokens")),
            output_tokens=_int(usage.get("output_tokens")),
            reasoning_tokens=_int(usage.get("reasoning_tokens")), error_code=error_code,
        )

    def record_chat(
        self, *, status: str, duration_ms: int | float,
        usage: dict[str, Any] | None = None, error_code: str | None = None,
        started_at: str | None = None, finished_at: str | None = None,
        ttft_ms: int | float | None = None,
    ) -> None:
        usage = usage or {}
        metadata = dict(usage)
        if isinstance(ttft_ms, (int, float)) and ttft_ms >= 0:
            metadata["ttft_ms"] = round(float(ttft_ms), 2)
        self.record(
            event_type="chat", name="chat_turn", status=status,
            started_at=started_at or utc_now_iso(),
            finished_at=finished_at or utc_now_iso(), duration_ms=duration_ms,
            input_tokens=_int(usage.get("input_tokens")),
            output_tokens=_int(usage.get("output_tokens")),
            reasoning_tokens=_int(usage.get("reasoning_tokens")), error_code=error_code,
            metadata=metadata,
        )


__all__ = ["TraceRecorder", "utc_now_iso"]
