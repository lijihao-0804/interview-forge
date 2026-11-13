"""Account-local view of the context decisions for one assistant turn."""
from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path

from interview_forge.core.runtime import server_runtime

_BLOCKS = {"learning", "memory", "memory_persistence", "recent_actions", "current_page", "legacy_context"}
_MODES = {"independent", "followup", "related", "ambiguous", "recall"}
_SELECTION_COUNTS = ("history_message_count", "history_selected_count", "history_archived_count", "recent_message_count")
_ROUND_COUNTS = ("original_prompt_tokens", "admitted_prompt_tokens", "reserved_output_tokens", "context_window",
                 "omitted_exchange_count", "masked_tool_result_count", "tool_result_tokens_saved", "budget_rejected_tool_result_count")


def _counts(data: dict, names: tuple[str, ...]) -> dict:
    return {name: value for name in names if type(value := data.get(name)) is int and value >= 0}


def turn_context(user_db: Path, session_id: str, turn_id: str) -> dict | None:
    # The database is resolved by the authenticated route. The trace index
    # makes this read proportional to one turn, irrespective of chat length.
    with closing(server_runtime.connect(user_db)) as conn:
        rows = conn.execute(
            """SELECT name, round_index, status, metadata_json, input_tokens
               FROM ai_trace_events WHERE trace_id = ? AND session_id = ?
               AND ((event_type = 'context' AND name IN ('context_selection','request_admission'))
                 OR (event_type = 'llm' AND name = 'model_round')) ORDER BY id""",
            (turn_id, session_id),
        ).fetchall()
    if not rows:
        return None
    summary: dict = {}
    rounds: dict[int, dict] = {}
    for row in rows:
        try:
            meta = json.loads(row["metadata_json"] or "{}")
        except (ValueError, TypeError):
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        if row["name"] == "context_selection":
            summary = _counts(meta, _SELECTION_COUNTS)
            summary["summary_present"] = meta.get("summary_present") is True
            mode = meta.get("history_mode")
            if isinstance(mode, str) and mode in _MODES:
                summary["history_mode"] = mode
            for name in ("context_blocks", "context_blocks_shortened", "context_blocks_rejected", "context_blocks_irrelevant"):
                items = meta.get(name)
                if isinstance(items, list):
                    summary[name] = [x for x in items if isinstance(x, str) and x in _BLOCKS]
            continue
        idx = row["round_index"]
        if type(idx) is not int or idx < 1:
            continue
        item = rounds.setdefault(idx, {"round": idx})
        if row["name"] == "request_admission":
            item.update(_counts(meta, _ROUND_COUNTS))
            item["admitted"] = row["status"] == "success"
        elif type(row["input_tokens"]) is int and row["input_tokens"] >= 0:
            item["provider_input_tokens"] = row["input_tokens"]
    return {"preparation": summary, "rounds": [rounds[k] for k in sorted(rounds)]}
