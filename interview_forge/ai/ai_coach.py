"""Optional, bounded LangChain integration for the first AI coach feature.

The module deliberately has no eager third-party imports.  The regular site can
therefore start with no AI packages installed and with ``AI_ENABLED=0``.  The
only supported model path in this phase is a LangChain ChatModel backed by an
OpenAI-compatible endpoint.  Database helpers in this file operate on the
already authenticated user's learning database; no auth database access is
performed here.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import sqlite3
import threading
import time
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from interview_forge.ai.config import (
    AIConfig,
    _beta_allows,
    _dependencies_available,
    _env_bool,
    _env_float,
    _env_int,
    load_ai_config as _load_ai_config,
    model_key as _config_model_key,
)
from interview_forge.ai.errors import AIServiceError
from interview_forge.ai.models import StreamEnvelope
from interview_forge.ai.provider import _content_text, _stream_deepseek_once, _usage_from
from interview_forge.ai.feedback import submit_ai_feedback
from interview_forge.ai.quota import (
    AI_DAILY_LIMIT,
    AI_QUOTA_TIMEZONE,
    _consume_ai_quota,
    _now_iso,
    _open_ai_db,
    _quota_window,
    _reserve_ai_quota,
    _release_ai_quota_reservation,
    _today_iso,
    _validated_daily_limit,
    get_ai_quota,
    reset_ai_quota,
)
from interview_forge.db.ai_schema import AI_DB_SCHEMA, ensure_ai_schema
from interview_forge.ai.telemetry import (
    _AI_DEBUG_CONTENT_FIELDS,
    _AI_DEBUG_LOCK,
    debug_ai_event,
)
from interview_forge.ai.prompts import (
    AI_TASK_STATUSES,
    CONTEXT_SCHEMA_VERSION,
    LLM_CONTEXT_VERSION,
    MAX_ACTIONS,
    MAX_CONTEXT_PREVIEW_CHARS,
    MAX_DATA_GAPS,
    MAX_MODEL_OUTPUT_CHARS,
    MAX_RECENT_TASKS,
    MAX_RESULT_CHARS,
    MAX_STRENGTHS,
    MAX_SUPPORT_REFS,
    MAX_TASK_ROWS,
    MAX_WEAKNESSES,
    OUTPUT_CONTRACT,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
)

AI_TASK_ID_RE = re.compile(r"^[0-9a-f]{32}$")
EVIDENCE_ID_RE = re.compile(r"^evidence:[A-Za-z0-9_.:-]{1,400}$")
SUPPORT_REF_RE = re.compile(r"^[pmcx][A-Za-z0-9]{1,16}$")


_StreamEnvelope = StreamEnvelope


from interview_forge.ai.validation import (
    _InvalidAIOutput,
    _json_load,
    _bounded_text,
    _bounded_string_list,
    _plain_model_value,
    _pydantic_schema,
    _pydantic_validate,
    _resolve_support_trace,
    validate_insight_payload,
    _signal_label,
    build_rule_fallback,
)


def load_ai_config() -> AIConfig:
    """Read AI configuration only from the current process environment."""
    return _load_ai_config(AI_DAILY_LIMIT)


def model_key(config: AIConfig | None = None) -> str:
    """Return a non-sensitive, stable model identifier for task deduplication."""
    return _config_model_key(
        config,
        daily_limit=AI_DAILY_LIMIT,
        loader=lambda _daily_limit: load_ai_config(),
    )


def ai_capability(username: str, role: str, daily_limit: int | None = None) -> dict[str, Any]:
    """Return capability state without exposing key, endpoint or raw model name."""
    config = load_ai_config()
    enabled = config.enabled
    configured = config.configured
    allowed = role == "admin" or _beta_allows(config.beta_users, username)
    dependencies = _dependencies_available() if enabled and configured else False
    effective_limit = None if role == "admin" else _validated_daily_limit(daily_limit)
    if role != "admin" and effective_limit == 0:
        status, message = "quota_disabled", "管理员已暂停当前账号的一键 AI 分析。"
    elif not enabled:
        status, message = "disabled", "AI 分析暂未启用，当前仍可使用规则分析。"
    elif not configured or not dependencies:
        status, message = "not_configured", "AI 分析尚未完成配置，当前仍可使用规则分析。"
    elif not allowed:
        status, message = "not_allowed", "AI 分析正在小范围开放，当前账号暂未加入体验范围。"
    else:
        status, message = "ready", "可以开始一次 AI 学习情况分析。"
    # When AI is configured, beta membership controls visibility.  When AI is
    # off or incomplete, showing the deterministic fallback card is useful and
    # does not grant model access; this state is still decided server-side.
    visible = not (enabled and configured and dependencies and not allowed)
    return {
        "visible": visible,
        "enabled": enabled,
        "configured": configured and dependencies,
        "allowed": allowed,
        "can_analyze": status == "ready" and allowed,
        "status": status,
        "message": message,
        "fallback_available": True,
        "daily_limit": effective_limit,
    }


from interview_forge.ai.context_projection import (
    _prune_empty,
    _compact_fact_for_case,
    _semantic_coverage,
    _build_llm_context,
    _context_json,
    _model_projection_debug,
)



from interview_forge.ai.generation import (
    _make_chat_model_impl,
    _messages,
    _uses_native_structured_output,
    _invoke_once,
    _request_config_summary,
    _extract_json_payload,
    _classify_provider_exception,
    _safe_raw_log,
    _debug_content_metadata,
    _normalize_unstructured_payload,
    generate_ai_insight,
)
_make_chat_model = _make_chat_model_impl

# Persistent task workers remain owned by the facade until their lifecycle
# extraction; these are process singletons and must not be duplicated.
from interview_forge.ai.tasks import (
    _AI_QUEUE,
    _AI_WORKERS,
    _AI_WORKER_LOCK,
    _AI_RUNTIME_LOCK,
    _AI_ACTIVE_TASKS,
    _AI_PROCESS_ID,
    _AI_CALL_CONDITION,
    _AI_CALL_ACTIVE,
    _ai_call_slot,
    _worker_loop,
    _ensure_workers,
    recover_ai_tasks,
    _parse_json_column,
    _support_labels,
    _legacy_evidence_labels,
    _replace_public_refs,
    _public_insight,
    _public_context,
    _public_task,
    _public_history_task,
    _finish_task_failure,
    _run_persisted_task,
    _prune_tasks,
    create_ai_task,
    get_ai_task,
    get_recent_ai_tasks,
    cancel_ai_task,
    reset_ai_runtime_for_tests,
)
