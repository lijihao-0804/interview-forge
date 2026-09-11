"""Append-only, metadata-only AI diagnostics."""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


_AI_DEBUG_LOCK = threading.Lock()
_AI_DEBUG_CONTENT_FIELDS = frozenset({
    "context", "context_preview", "raw_output", "result", "user_request", "profile",
    "prompt", "messages", "content", "summary", "strengths", "weaknesses", "actions",
    "data_gaps", "facts", "signals", "evidence", "trace_map", "title", "label",
    "labels", "support_labels", "topic_details",
})


def debug_ai_event(event: str, *, task_id: str = "", **fields: Any) -> None:
    """Write opt-in metadata-only JSONL diagnostics."""
    target = os.environ.get("AI_DEBUG_LOG_PATH", "").strip()
    if not target:
        return
    safe_fields = {
        key: value for key, value in fields.items()
        if key not in _AI_DEBUG_CONTENT_FIELDS
    }
    record = {
        "at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "event": event,
        "task_id": task_id,
        **safe_fields,
    }
    try:
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str)
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        with _AI_DEBUG_LOCK, path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except (OSError, TypeError, ValueError):
        pass
