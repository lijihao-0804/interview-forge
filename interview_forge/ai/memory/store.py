"""Per-user SQLite persistence for active and superseded memories."""
from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any

from interview_forge.core.runtime import server_runtime

from .contracts import MemoryCandidate, MemoryItem

if TYPE_CHECKING:
    from interview_forge.ai.chat.request_ledger import RequestAttempt


def _now() -> str:
    return str(server_runtime.now_iso())


class MemorySourceSuperseded(ValueError):
    """A newer message or user deletion already decided this memory."""


def _key_digest(kind: str, key: str) -> bytes:
    return sha256((kind + "\0" + key).encode("utf-8")).digest()


def _record_forget(connection, digest: bytes, source_id: int) -> None:
    connection.execute(
        """INSERT INTO memory_forget_watermarks(key_digest, source_message_id) VALUES (?, ?)
           ON CONFLICT(key_digest) DO UPDATE SET
               source_message_id = MAX(source_message_id, excluded.source_message_id)""",
        (digest, source_id),
    )


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
        attempt: RequestAttempt | None = None,
    ) -> MemoryItem | None:
        return self.save_candidates(
            user_db=user_db, candidates=[candidate], source_session_id=source_session_id,
            source_message_id=source_message_id, attempt=attempt,
        )[0]

    def save_candidates(
        self, *, user_db: Path | str, candidates: Sequence[MemoryCandidate],
        source_session_id: str, source_message_id: int, attempt: RequestAttempt | None = None,
    ) -> list[MemoryItem | None]:
        """Commit the facts and ledger effects of one extraction together."""
        now = _now()
        with closing(server_runtime.connect(Path(user_db))) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            return [
                self._apply_candidate(connection, candidate, source_session_id, source_message_id, now, attempt)
                for candidate in candidates
            ]

    @staticmethod
    def _apply_candidate(connection, candidate: MemoryCandidate, source_session_id: str,
                         source_message_id: int, now: str, attempt: RequestAttempt | None) -> MemoryItem | None:
        key = (candidate.kind, candidate.canonical_key)
        digest = _key_digest(*key)
        latest = connection.execute(
            """SELECT MAX(source_message_id) FROM (
                   SELECT source_message_id FROM user_memories WHERE kind=? AND canonical_key=?
                   UNION ALL SELECT source_message_id FROM memory_forget_watermarks WHERE key_digest=?
               )""", (*key, digest),
        ).fetchone()[0]
        if latest is not None and source_message_id <= latest:
            if candidate.explicit:
                raise MemorySourceSuperseded("memory source already processed or superseded")
            return None
        if attempt is not None:
            attempt.record_memory(connection)
        if candidate.operation == "forget":
            connection.execute(
                "DELETE FROM user_memories WHERE kind = ? AND canonical_key = ?",
                key,
            )
            _record_forget(connection, digest, source_message_id)
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
        row = connection.execute("SELECT * FROM user_memories WHERE id = ?", (memory_id,)).fetchone()
        return _item(row)

    def delete(self, *, user_db: Path | str, memory_id: str) -> bool:
        with closing(server_runtime.connect(Path(user_db))) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT kind, canonical_key, source_message_id, status FROM user_memories WHERE id=?",
                (str(memory_id),),
            ).fetchone()
            if row is not None and row["status"] == "active":
                # AUTOINCREMENT's high-water mark also covers deleted chat sessions
                # whose already-dispatched extractors might still finish.
                latest = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='chat_messages'").fetchone()
                cutoff = max(int(latest[0]) if latest else 0, int(row["source_message_id"] or 0))
                _record_forget(connection, _key_digest(row["kind"], row["canonical_key"]), cutoff)
            cursor = connection.execute("DELETE FROM user_memories WHERE id = ?", (str(memory_id),))
            connection.commit()
            return cursor.rowcount > 0


__all__ = ["MemorySourceSuperseded", "MemoryStore"]
