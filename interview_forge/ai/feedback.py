"""Persistence for feedback on a stored AI insight."""
from __future__ import annotations

import re
from contextlib import closing
from http import HTTPStatus
from pathlib import Path
from typing import Any

from interview_forge.ai.errors import AIServiceError
from interview_forge.ai.quota import _now_iso, _open_ai_db

AI_TASK_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def submit_ai_feedback(db_path: Path, insight_id: str, helpful: bool) -> dict[str, Any]:
    if not AI_TASK_ID_RE.fullmatch(insight_id) or not isinstance(helpful, bool):
        raise ValueError("反馈参数不正确")
    with closing(_open_ai_db(db_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT insight_id FROM ai_insights WHERE insight_id = ?", (insight_id,)
        ).fetchone()
        if row is None:
            connection.execute("ROLLBACK")
            raise AIServiceError("cancelled", "分析结果不存在或已过期。", status=HTTPStatus.NOT_FOUND)
        connection.execute(
            "UPDATE ai_insights SET helpful = ?, feedback_at = ? WHERE insight_id = ?",
            (1 if helpful else 0, _now_iso(), insight_id),
        )
        connection.execute("COMMIT")
    return {"insight_id": insight_id, "helpful": helpful}
