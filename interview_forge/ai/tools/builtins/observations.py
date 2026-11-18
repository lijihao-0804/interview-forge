"""Immutable, bounded observations of two specific learning reads in one chat."""
from __future__ import annotations

import hashlib
import sqlite3
import time
from contextlib import closing
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from interview_forge.ai.token_counting import canonical_json
from interview_forge.ai.tools.contracts import ToolExecutionContext, ToolResult
from interview_forge.core.runtime import server_runtime

SESSION_LIMIT = 32
ACCOUNT_LIMIT = 128
MAX_AGE = 30 * 86400
MAX_BYTES = 12_000
PAGE_CHARS = 480
SOURCE_TOOLS = {"get_problem_progress", "get_acm_examples"}
_FIELDS = {
    "get_problem_progress": {"found", "problem_id", "problem"},
    "problem": {"problem_id", "title", "catalog", "rounds", "mark", "submits", "ac_submits",
                "last_status", "last_activity_at", "last_submitted_at", "next_due", "native_acm"},
    "native_acm": {"problem_key", "attempts", "status", "latest_language", "latest_submitted_at_utc", "latest_verdict"},
    "get_acm_examples": {"found", "problem_id", "title", "contract", "checker", "examples", "total", "next_index"},
    "checker": {"mode", "abs_tol", "rel_tol"},
    "examples": {"index", "name", "source", "source_url", "input", "expected", "input_truncated", "expected_truncated"},
}


def _allowed_fields(data, group: str) -> bool:
    if not isinstance(data, dict) or not data.keys() <= _FIELDS[group]:
        return False
    for key, value in data.items():
        if key == "examples":
            if not isinstance(value, list) or not all(_allowed_fields(item, key) for item in value):
                return False
        elif key in _FIELDS:
            if not _allowed_fields(value, key):
                return False
        elif value is not None and type(value) not in (bool, int, float, str):
            return False
    return True


def save_observation(context, name, pid, data, observation_id):
    if name not in SOURCE_TOOLS or not _allowed_fields(data, name):
        return {"status": "unsupported_fields"}
    payload = canonical_json(data)
    encoded = payload.encode("utf-8")
    if len(encoded) > MAX_BYTES:
        return {"status": "size_limit"}
    now = int(time.time())
    try:
        with closing(server_runtime.connect(context.user_db)) as db, db:
            written = db.execute("""INSERT INTO chat_learning_observations
                (id, session_id, user_message_id, source_tool, problem_id, created_at, data_json, sha256)
                SELECT ?, session_id, id, ?, ?, ?, ?, ? FROM chat_messages
                WHERE id=? AND session_id=? AND role='user'""", (observation_id, name, pid, now,
                    payload, hashlib.sha256(encoded).hexdigest(), context.user_message_id, context.session_id))
            if not written.rowcount:
                return {"status": "source_unavailable"}
            db.execute("DELETE FROM chat_learning_observations WHERE created_at <= ?", (now - MAX_AGE,))
            db.execute("""DELETE FROM chat_learning_observations WHERE sequence IN (
                SELECT sequence FROM chat_learning_observations WHERE session_id=?
                ORDER BY sequence DESC LIMIT -1 OFFSET ?)""", (context.session_id, SESSION_LIMIT))
            db.execute("""DELETE FROM chat_learning_observations WHERE sequence IN (
                SELECT sequence FROM chat_learning_observations ORDER BY sequence DESC LIMIT -1 OFFSET ?)""",
                (ACCOUNT_LIMIT,))
    except (sqlite3.Error, OSError):
        return {"status": "storage_unavailable"}
    return {"id": observation_id}


class RecallLearningObservationArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observation_id: str | None = Field(default=None, pattern="^[0-9a-f]{32}$")
    source_tool: Literal["get_problem_progress", "get_acm_examples"] | None = None
    problem_id: int | None = Field(default=None, gt=0, le=2**63 - 1)
    offset: int = Field(default=0, ge=0, le=MAX_BYTES)

    @model_validator(mode="after")
    def lookup(self):
        if self.observation_id:
            if self.source_tool is not None or self.problem_id is not None:
                raise ValueError("精确引用仅需 observation_id")
        elif self.source_tool is None or self.problem_id is None or self.offset:
            raise ValueError("按题号和来源查询最近一次历史观察，翻页需使用 observation_id")
        return self


def recall_learning_observation(context: ToolExecutionContext, args: RecallLearningObservationArgs) -> ToolResult:
    params = [context.session_id, context.user_message_id, int(time.time()) - MAX_AGE]
    clause = "id=?" if args.observation_id else "source_tool=? AND problem_id=?"
    params.extend([args.observation_id] if args.observation_id else [args.source_tool, args.problem_id])
    with closing(server_runtime.connect(context.user_db)) as db:
        rows = db.execute(f"""SELECT * FROM chat_learning_observations WHERE session_id=?
            AND user_message_id < ? AND created_at > ? AND {clause}
            ORDER BY sequence DESC LIMIT 2""", params).fetchall()
    if not rows:
        return ToolResult({"found": False, "reason": "missing_or_expired",
            "retention_days": MAX_AGE // 86400, "session_limit": SESSION_LIMIT, "account_limit": ACCOUNT_LIMIT})
    row = rows[0]
    payload = row["data_json"]
    if hashlib.sha256(payload.encode("utf-8")).hexdigest() != row["sha256"]:
        return ToolResult({"found": False, "reason": "integrity_failed"})
    if args.offset >= len(payload):
        return ToolResult({"found": False, "reason": "offset_out_of_range", "total_chars": len(payload)})
    end = min(len(payload), args.offset + PAGE_CHARS)
    result = {"found": True, "source_tool": row["source_tool"], "problem_id": row["problem_id"],
              "observation_id": row["id"], "user_message_id": row["user_message_id"], "recorded_at_unix": row["created_at"],
              "sha256": row["sha256"], "offset": args.offset, "next_offset": end if end < len(payload) else None,
              "total_chars": len(payload), "excerpt": payload[args.offset:end]}
    if len(rows) > 1:
        result["previous_observation_id"] = rows[1]["id"]
    return ToolResult(result, "已读取本会话当时的工具结果")
