"""Bounded chat context assembly and incremental rolling summaries."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any

from interview_forge.ai.chat.prompts import CHAT_SYSTEM_PROMPT
from interview_forge.ai.chat.token_budget import (
    ChatTokenBudget,
    DEFAULT_CHAT_TOKEN_BUDGET,
    DEFAULT_TOKEN_ESTIMATOR,
    TokenEstimator,
    trim_text_to_tokens,
)
from interview_forge.core.runtime import server_runtime


SUMMARY_PREFIX = "这是当前会话的滚动摘要，仅用于短期上下文，不是长期 Memory。\n"


def _row_message(row: Mapping[str, Any]) -> dict[str, str]:
    return {"role": str(row["role"]), "content": str(row["content"])}


def _collapse(value: str) -> str:
    return " ".join(str(value or "").split())


class ContextBuilder:
    """Build ``system → summary → recent → current`` messages for one DB."""

    def __init__(
        self,
        *,
        estimator: TokenEstimator | None = None,
        budget: ChatTokenBudget = DEFAULT_CHAT_TOKEN_BUDGET,
        system_prompt: str = CHAT_SYSTEM_PROMPT,
        contextual_system: str = "",
    ) -> None:
        self.estimator = estimator or DEFAULT_TOKEN_ESTIMATOR
        self.budget = budget
        self.system_prompt = system_prompt
        self.contextual_system = contextual_system.strip()
        self.last_build: dict[str, Any] = {}

    def _load(
        self, *, user_db: Path | str, session_id: str
    ) -> tuple[list[sqlite3.Row], sqlite3.Row | None]:
        with closing(server_runtime.connect(Path(user_db))) as connection:
            rows = connection.execute(
                "SELECT id, role, content, created_at FROM chat_messages "
                "WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
            summary = connection.execute(
                "SELECT session_id, summary, through_message_id, updated_at "
                "FROM chat_session_summaries WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return rows, summary

    def _save_summary(
        self,
        *,
        user_db: Path | str,
        session_id: str,
        summary: str,
        through_message_id: int,
    ) -> None:
        timestamp = str(server_runtime.now_iso())
        with closing(server_runtime.connect(Path(user_db))) as connection:
            connection.execute(
                """INSERT INTO chat_session_summaries(
                       session_id, summary, through_message_id, updated_at
                   ) VALUES (?, ?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                       summary = excluded.summary,
                       through_message_id = excluded.through_message_id,
                       updated_at = excluded.updated_at""",
                (session_id, summary, through_message_id, timestamp),
            )
            connection.commit()

    def _select_recent(self, rows: Sequence[sqlite3.Row]) -> list[sqlite3.Row]:
        selected: list[sqlite3.Row] = []
        used = 0
        for row in reversed(rows):
            message = _row_message(row)
            cost = self.estimator.estimate_messages([message])
            if selected and used + cost > self.budget.recent_tokens:
                break
            if not selected and cost > self.budget.recent_tokens:
                clipped = trim_text_to_tokens(
                    message["content"],
                    max(1, self.budget.recent_tokens - self.budget.message_overhead_tokens),
                    self.estimator,
                )
                # SQLite rows are immutable; the clipped message is carried by
                # a small mapping in the final assembly instead.
                selected.append({"id": int(row["id"]), "role": message["role"], "content": clipped})  # type: ignore[list-item]
                break
            selected.insert(0, row)
            used += cost
        return selected

    def _summary_for(
        self,
        *,
        existing: str,
        new_rows: Sequence[sqlite3.Row],
    ) -> str:
        existing_text = existing.strip()
        prefix = SUMMARY_PREFIX.strip()
        if existing_text.startswith(prefix):
            existing_text = existing_text[len(prefix):].lstrip()
        lines: list[str] = []
        # Keep the first and newest complete turns from the newly aged batch.
        # The existing summary already carries older stable material, while
        # this preserves both an early goal and the latest incremental outcome.
        selected_rows = list(new_rows)
        if len(selected_rows) > 4:
            selected_rows = selected_rows[:2] + selected_rows[-2:]
        for row in selected_rows:
            role = "目标/问题" if str(row["role"]) == "user" else "结论/建议"
            content = _collapse(str(row["content"]))
            if content:
                if len(content) > 360:
                    content = content[:357].rstrip() + "..."
                lines.append(f"{role}：{content}")
        if not lines and not existing_text:
            return ""
        new_text = "\n".join(lines)
        new_budget = max(1, self.budget.summary_tokens // 2)
        new_part = trim_text_to_tokens(new_text, new_budget, self.estimator)
        prefix_cost = self.estimator.estimate_text(SUMMARY_PREFIX)
        new_cost = self.estimator.estimate_text(new_part)
        old_budget = max(1, self.budget.summary_tokens - prefix_cost - new_cost)
        old_part = trim_text_to_tokens(existing_text, old_budget, self.estimator)
        body = SUMMARY_PREFIX + old_part
        if new_part:
            body += "\n" + new_part
        return trim_text_to_tokens(body, self.budget.summary_tokens, self.estimator)

    def build(
        self,
        *,
        session_id: str,
        current_message: str,
        user_db: Path | str,
    ) -> list[dict[str, str]]:
        """Return ordered, bounded messages with the current request exactly once."""
        rows, summary_row = self._load(user_db=user_db, session_id=session_id)
        # The service persists the current user turn before building.  Remove
        # all equal user rows so the request is re-added exactly once at the end.
        history = [
            row for row in rows
            if not (str(row["role"]) == "user" and str(row["content"]) == current_message)
        ]
        recent = self._select_recent(history)
        recent_ids = {int(row["id"]) for row in recent}
        cutoff_id = min(recent_ids) if recent_ids else (int(history[-1]["id"]) + 1 if history else 0)
        through = int(summary_row["through_message_id"] or 0) if summary_row is not None else 0
        new_summary_rows = [
            row for row in history
            if int(row["id"]) > through and int(row["id"]) < cutoff_id and int(row["id"]) not in recent_ids
        ]
        summary_text = str(summary_row["summary"]) if summary_row is not None else ""
        if new_summary_rows:
            summary_text = self._summary_for(existing=summary_text, new_rows=new_summary_rows)
            self._save_summary(
                user_db=user_db,
                session_id=session_id,
                summary=summary_text,
                through_message_id=int(new_summary_rows[-1]["id"]),
            )

        system_content = trim_text_to_tokens(
            self.system_prompt + (("\n\n" + self.contextual_system) if self.contextual_system else ""),
            self.budget.system_tokens,
            self.estimator,
        )
        result: list[dict[str, str]] = [{"role": "system", "content": system_content}]
        if summary_text:
            result.append({"role": "system", "content": trim_text_to_tokens(summary_text, self.budget.summary_tokens, self.estimator)})
        result.extend(_row_message(row) for row in recent)
        result.append({
            "role": "user",
            "content": trim_text_to_tokens(current_message, self.budget.current_tokens, self.estimator),
        })
        self.last_build = {
            "summary_present": bool(summary_text),
            "summary_through_message_id": int(new_summary_rows[-1]["id"]) if new_summary_rows else through,
            "recent_message_count": len(recent),
            "recent_message_ids": sorted(recent_ids),
            "estimated_prompt_tokens": self.estimator.estimate_messages(result),
            "estimator": getattr(self.estimator, "name", type(self.estimator).__name__),
            "budget": {
                "summary_tokens": self.budget.summary_tokens,
                "recent_tokens": self.budget.recent_tokens,
                "system_tokens": self.budget.system_tokens,
                "current_tokens": self.budget.current_tokens,
                "output_tokens": self.budget.output_tokens,
            },
        }
        return result


__all__ = ["ContextBuilder", "SUMMARY_PREFIX"]
