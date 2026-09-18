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


_RESULT_META_MAX_CHARS = 4000


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str))


def _bound_result_value(value: Any, budget: int, *, depth: int = 0) -> Any:
    """Bound metadata before serialization; never cut a JSON string blindly."""
    if budget <= 32 or depth >= 4:
        return "[内容已省略]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= budget:
            return value
        return value[: max(0, budget - 20)] + "…[内容已省略]"
    if isinstance(value, Mapping):
        bounded: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)[:80]
            bounded[key] = _bound_result_value(raw_value, max(64, budget // 2), depth=depth + 1)
            if _json_size(bounded) > budget:
                bounded.pop(key, None)
                break
        if not bounded and value:
            return {"truncated": True}
        return bounded
    if isinstance(value, (list, tuple)):
        bounded_list: list[Any] = []
        for raw_value in value:
            candidate = _bound_result_value(raw_value, max(64, budget // 2), depth=depth + 1)
            bounded_list.append(candidate)
            if _json_size(bounded_list) > budget:
                bounded_list.pop()
                break
        return bounded_list
    return str(value)[: max(0, budget - 20)] + "…[内容已省略]"


def _bounded_result_meta(value: Mapping[str, Any]) -> dict[str, Any]:
    bounded = _bound_result_value(dict(value), _RESULT_META_MAX_CHARS)
    if isinstance(bounded, Mapping) and _json_size(bounded) <= _RESULT_META_MAX_CHARS:
        return dict(bounded)
    return {"truncated": True, "message": "结果过大，详细内容已省略。"}


def _decode_result_meta(value: Any) -> dict[str, Any]:
    try:
        decoded = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"truncated": True, "message": "结果元数据损坏，详细内容已省略。"}
    return dict(decoded) if isinstance(decoded, Mapping) else {}


def _payload(row: Any) -> dict[str, Any]:
    result_meta = _decode_result_meta(row["result_meta_json"])
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
        arguments_json = json.dumps(
            dict(arguments), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        with closing(server_runtime.connect(Path(user_db))) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT * FROM chat_action_requests
                   WHERE session_id = ? AND turn_id = ? AND tool_name = ?
                     AND arguments_json = ? AND status = 'pending'
                   ORDER BY created_at ASC LIMIT 1""",
                (session_id, turn_id, tool_name, arguments_json),
            ).fetchone()
            if existing is not None:
                connection.commit()
                payload = _payload(existing)
                payload["_deduplicated"] = True
                return payload
            connection.execute(
                """INSERT INTO chat_action_requests(
                    id, session_id, turn_id, user_message_id, tool_name, arguments_json,
                    status, confirmation_text, created_at, expires_at, result_meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, '{}')""",
                (
                    action_id, session_id, turn_id, user_message_id, tool_name,
                    arguments_json, confirmation_text[:240], created, expires,
                ),
            )
            connection.commit()
        payload = {
            "action_id": action_id, "session_id": session_id, "turn_id": turn_id,
            "user_message_id": user_message_id, "tool_name": tool_name,
            "arguments": dict(arguments), "status": "pending",
            "confirmation_text": confirmation_text[:240], "created_at": created,
            "expires_at": expires,
        }
        payload["_deduplicated"] = False
        return payload

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

    def list_recent(
        self, *, user_db: Path | str, session_id: str, limit: int = 4
    ) -> list[dict[str, Any]]:
        """Return a small, server-owned view of recent completed action rows.

        The store still returns its normal internal payload to trusted callers;
        the chat context provider deliberately projects it without arguments,
        IDs, or result bodies before it reaches the model.
        """
        bounded_limit = min(max(int(limit), 1), 10)
        with closing(server_runtime.connect(Path(user_db))) as connection:
            rows = connection.execute(
                """SELECT * FROM chat_action_requests
                   WHERE session_id = ?
                     AND status IN ('executing', 'succeeded', 'failed', 'cancelled')
                   ORDER BY COALESCE(completed_at, decided_at, created_at) DESC, id DESC
                   LIMIT ?""",
                (session_id, bounded_limit),
            ).fetchall()
        return [_payload(row) for row in rows]

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
            existing = connection.execute(
                "SELECT result_meta_json FROM chat_action_requests WHERE id = ?",
                (str(action_id),),
            ).fetchone()
            merged_meta = _decode_result_meta(existing["result_meta_json"]) if existing else {}
            merged_meta.update(dict(result_meta))
            connection.execute(
                """UPDATE chat_action_requests
                   SET status = ?, completed_at = ?, error_code = ?, result_meta_json = ?
                   WHERE id = ? AND status = 'executing'""",
                (
                    status, now, error_code,
                    json.dumps(
                        _bounded_result_meta(merged_meta),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    str(action_id),
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM chat_action_requests WHERE id = ?", (str(action_id),)
            ).fetchone()
        return _payload(row) if row is not None else None

    def update_background_result(
        self,
        *,
        user_db: Path | str,
        action_id: str,
        background: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """Persist the final result of a task started by a confirmed action.

        Action confirmation and background work have different lifecycles.  A
        confirmed action may be marked as accepted before its worker finishes;
        keep the existing action status for compatibility, but merge a safe
        background result so later chat context can distinguish accepted,
        running, completed, partial, and failed work.
        """
        with closing(server_runtime.connect(Path(user_db))) as connection:
            row = connection.execute(
                "SELECT result_meta_json FROM chat_action_requests WHERE id = ?",
                (str(action_id),),
            ).fetchone()
            if row is None:
                return None
            merged_meta = _decode_result_meta(row["result_meta_json"])
            merged_meta["background"] = dict(background)
            connection.execute(
                """UPDATE chat_action_requests
                   SET result_meta_json = ?
                   WHERE id = ? AND status IN ('executing', 'succeeded', 'failed')""",
                (
                    json.dumps(
                        _bounded_result_meta(merged_meta),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    str(action_id),
                ),
            )
            connection.commit()
            updated = connection.execute(
                "SELECT * FROM chat_action_requests WHERE id = ?", (str(action_id),)
            ).fetchone()
        return _payload(updated) if updated is not None else None

    def expire(self, *, user_db: Path | str, action_id: str) -> bool:
        with closing(server_runtime.connect(Path(user_db))) as connection:
            cursor = connection.execute(
                "UPDATE chat_action_requests SET status = 'expired', decided_at = ? WHERE id = ? AND status = 'pending'",
                (_now(), str(action_id)),
            )
            connection.commit()
            return cursor.rowcount > 0


__all__ = ["ActionRequestError", "ActionRequestStore"]
