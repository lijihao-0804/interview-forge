"""Per-user SQLite persistence for active and superseded memories."""
from __future__ import annotations

import json
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from interview_forge.core.runtime import server_runtime

from .contracts import MemoryCandidate, MemoryItem


def _now() -> str:
    return str(server_runtime.now_iso())


def _item(row: Any) -> MemoryItem:
    return MemoryItem(
        id=str(row["id"]), kind=str(row["kind"]), canonical_key=str(row["canonical_key"]),
        value=json.loads(str(row["value_json"])), display_text=str(row["display_text"]),
        source_type=str(row["source_type"]), source_session_id=row["source_session_id"],
        source_message_id=int(row["source_message_id"]) if row["source_message_id"] is not None else None,
        confidence=float(row["confidence"]), importance=int(row["importance"]),
        valid_from=row["valid_from"], valid_to=row["valid_to"], status=str(row["status"]),
        created_at=str(row["created_at"]), updated_at=str(row["updated_at"]),
    )


class MemoryStore:
    def list_active(self, *, user_db: Path | str) -> list[MemoryItem]:
        with closing(server_runtime.connect(Path(user_db))) as connection:
            rows = connection.execute(
                "SELECT * FROM user_memories WHERE status = 'active' ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        return [_item(row) for row in rows]

    def save_candidate(
        self,
        *, user_db: Path | str,
        candidate: MemoryCandidate,
        source_session_id: str,
        source_message_id: int,
    ) -> MemoryItem | None:
        now = _now()
        with closing(server_runtime.connect(Path(user_db))) as connection:
            if candidate.operation == "forget":
                connection.execute(
                    "DELETE FROM user_memories WHERE kind = ? AND canonical_key = ?",
                    (candidate.kind, candidate.canonical_key),
                )
                connection.commit()
                return None
            old = connection.execute(
                "SELECT id FROM user_memories WHERE kind = ? AND canonical_key = ? AND status = 'active'",
                (candidate.kind, candidate.canonical_key),
            ).fetchone()
            old_id = str(old["id"]) if old is not None else None
            if old_id:
                connection.execute(
                    "UPDATE user_memories SET status = 'superseded', updated_at = ? WHERE id = ?",
                    (now, old_id),
                )
            memory_id = uuid.uuid4().hex
            source_type = "explicit" if candidate.explicit else "inferred"
            connection.execute(
                """INSERT INTO user_memories(
                    id, kind, canonical_key, value_json, display_text, source_type,
                    source_session_id, source_message_id, confidence, importance,
                    valid_from, valid_to, status, supersedes_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'active', ?, ?, ?)""",
                (
                    memory_id, candidate.kind, candidate.canonical_key,
                    json.dumps(dict(candidate.value), ensure_ascii=False, separators=(",", ":")),
                    candidate.display_text[:240], source_type, source_session_id,
                    source_message_id, float(candidate.confidence), int(candidate.importance),
                    now, old_id, now, now,
                ),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM user_memories WHERE id = ?", (memory_id,)).fetchone()
        return _item(row) if row is not None else None

    def delete(self, *, user_db: Path | str, memory_id: str) -> bool:
        with closing(server_runtime.connect(Path(user_db))) as connection:
            cursor = connection.execute("DELETE FROM user_memories WHERE id = ?", (str(memory_id),))
            connection.commit()
            return cursor.rowcount > 0


__all__ = ["MemoryStore"]
