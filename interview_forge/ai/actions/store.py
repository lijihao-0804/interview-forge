"""SQLite state machine for one user's pending assistant actions."""
from __future__ import annotations

import json
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from interview_forge.core.runtime import server_runtime


class ActionRequestError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "action_error") -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def _now() -> str:
    return str(server_runtime.now_iso())


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _expired(value: str, now: str | None = None) -> bool:
    try:
        return _parse_time(value) <= _parse_time(now or _now())
    except (TypeError, ValueError, OverflowError):
        return True


def _payload(row: Any) -> dict[str, Any]:
    result_meta = json.loads(str(row["result_meta_json"] or "{}"))
    return {
        "action_id": str(row["id"]),
        "session_id": str(row["session_id"]),
        "turn_id": str(row["turn_id"]),
        "user_message_id": row["user_message_id"],
        "tool_name": str(row["tool_name"]),
        "arguments": json.loads(str(row["arguments_json"])),
        "status": str(row["status"]),
        "confirmation_text": str(row["confirmation_text"]),
        "created_at": str(row["created_at"]),
        "expires_at": str(row["expires_at"]),
        "decided_at": row["decided_at"],
        "completed_at": row["completed_at"],
        "error_code": row["error_code"],
        "result_meta": result_meta if isinstance(result_meta, Mapping) else {},
    }


class ActionRequestStore:
    def create(
        self,
        *,
        user_db: Path | str,
        session_id: str,
        turn_id: str,
        user_message_id: int,
        tool_name: str,
        arguments: Mapping[str, Any],
        confirmation_text: str,
        ttl_seconds: int = 600,
    ) -> dict[str, Any]:
        created = _now()
        expires = (_parse_time(created) + timedelta(seconds=max(60, ttl_seconds))).isoformat(timespec="seconds")
        action_id = uuid.uuid4().hex
        with closing(server_runtime.connect(Path(user_db))) as connection:
            connection.execute(
                """INSERT INTO chat_action_requests(
                    id, session_id, turn_id, user_message_id, tool_name, arguments_json,
                    status, confirmation_text, created_at, expires_at, result_meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, '{}')""",
                (
                    action_id, session_id, turn_id, user_message_id, tool_name,
                    json.dumps(dict(arguments), ensure_ascii=False, separators=(",", ":")),
                    confirmation_text[:240], created, expires,
                ),
            )
            connection.commit()
        return {
            "action_id": action_id, "session_id": session_id, "turn_id": turn_id,
            "user_message_id": user_message_id, "tool_name": tool_name,
            "arguments": dict(arguments), "status": "pending",
            "confirmation_text": confirmation_text[:240], "created_at": created,
            "expires_at": expires,
        }

    def get(self, *, user_db: Path | str, action_id: str) -> dict[str, Any] | None:
        with closing(server_runtime.connect(Path(user_db))) as connection:
            row = connection.execute(
                "SELECT * FROM chat_action_requests WHERE id = ?", (str(action_id),)
            ).fetchone()
        return _payload(row) if row is not None else None

    def list_pending(self, *, user_db: Path | str, session_id: str) -> list[dict[str, Any]]:
        with closing(server_runtime.connect(Path(user_db))) as connection:
            rows = connection.execute(
                "SELECT * FROM chat_action_requests WHERE session_id = ? AND status = 'pending' ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = _payload(row)
            if _expired(item["expires_at"]):
                self.expire(user_db=user_db, action_id=item["action_id"])
            else:
                result.append(item)
        return result

    def claim_pending(self, *, user_db: Path | str, action_id: str) -> dict[str, Any] | None:
        now = _now()
        with closing(server_runtime.connect(Path(user_db))) as connection:
            cursor = connection.execute(
                """UPDATE chat_action_requests
                   SET status = 'executing', decided_at = ?
                   WHERE id = ? AND status = 'pending' AND expires_at > ?""",
                (now, str(action_id), now),
            )
            if cursor.rowcount:
                connection.commit()
                row = connection.execute(
                    "SELECT * FROM chat_action_requests WHERE id = ?", (str(action_id),)
                ).fetchone()
                payload = _payload(row) if row is not None else None
                if payload is not None:
                    payload["_claimed"] = True
                return payload

            row = connection.execute(
                "SELECT * FROM chat_action_requests WHERE id = ?", (str(action_id),)
            ).fetchone()
            if row is None:
                return None
            if str(row["status"]) == "pending" and _expired(str(row["expires_at"]), now):
                connection.execute(
                    "UPDATE chat_action_requests SET status = 'expired', decided_at = ? WHERE id = ? AND status = 'pending'",
                    (now, str(action_id)),
                )
                connection.commit()
            row = connection.execute(
                "SELECT * FROM chat_action_requests WHERE id = ?", (str(action_id),)
            ).fetchone()
        payload = _payload(row) if row is not None else None
        if payload is not None:
            payload["_claimed"] = False
        return payload

    def cancel(self, *, user_db: Path | str, action_id: str) -> dict[str, Any] | None:
        now = _now()
        with closing(server_runtime.connect(Path(user_db))) as connection:
            row = connection.execute(
                "SELECT * FROM chat_action_requests WHERE id = ?", (str(action_id),)
            ).fetchone()
            if row is None:
                return None
            if str(row["status"]) == "pending" and _expired(str(row["expires_at"]), now):
                connection.execute(
                    "UPDATE chat_action_requests SET status = 'expired', decided_at = ? WHERE id = ? AND status = 'pending'",
                    (now, str(action_id)),
                )
            else:
                connection.execute(
                    "UPDATE chat_action_requests SET status = 'cancelled', decided_at = ? WHERE id = ? AND status = 'pending'",
                    (now, str(action_id)),
                )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM chat_action_requests WHERE id = ?", (str(action_id),)
            ).fetchone()
        return _payload(row) if row is not None else None

    def complete(
        self,
        *,
        user_db: Path | str,
        action_id: str,
        status: str,
        error_code: str | None,
        result_meta: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        if status not in {"succeeded", "failed"}:
            raise ValueError("invalid action completion status")
        now = _now()
        with closing(server_runtime.connect(Path(user_db))) as connection:
            connection.execute(
                """UPDATE chat_action_requests
                   SET status = ?, completed_at = ?, error_code = ?, result_meta_json = ?
                   WHERE id = ? AND status = 'executing'""",
                (
                    status, now, error_code,
                    json.dumps(dict(result_meta), ensure_ascii=False, separators=(",", ":"))[:4000],
                    str(action_id),
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM chat_action_requests WHERE id = ?", (str(action_id),)
            ).fetchone()
        return _payload(row) if row is not None else None

    def expire(self, *, user_db: Path | str, action_id: str) -> bool:
        with closing(server_runtime.connect(Path(user_db))) as connection:
            cursor = connection.execute(
                "UPDATE chat_action_requests SET status = 'expired', decided_at = ? WHERE id = ? AND status = 'pending'",
                (_now(), str(action_id)),
            )
            connection.commit()
            return cursor.rowcount > 0


__all__ = ["ActionRequestError", "ActionRequestStore"]
