"""Durable request admission, replay and crash recovery in one account's SQLite DB."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import uuid
from contextlib import closing
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any

from interview_forge.ai.errors import AIServiceError
from interview_forge.ai.quota import charge_chat_quota
from interview_forge.ai.token_counting import canonical_json
from interview_forge.core.runtime import server_runtime
from interview_forge.runtime.shared import FileLock

DEFAULT_SESSION_TITLE = "新会话"
_ACTIVE_SESSIONS: dict[tuple[str, str], FileLock] = {}
_ACTIVE_SESSIONS_LOCK = threading.Lock()


def claim_chat_session(db_path: Path, session_id: str) -> bool:
    # Both the serving worker and the maintenance process need the OS lease,
    # including when the web launcher is configured for only one worker.
    key = (str(db_path.resolve()), session_id)
    with _ACTIVE_SESSIONS_LOCK:
        if key in _ACTIVE_SESSIONS:
            return False
        lease = FileLock("chat-session", canonical_json(key))
        if not lease.acquire():
            return False
        _ACTIVE_SESSIONS[key] = lease
        return True


def release_chat_session(db_path: Path, session_id: str) -> None:
    key = (str(db_path.resolve()), session_id)
    with _ACTIVE_SESSIONS_LOCK:
        lease = _ACTIVE_SESSIONS.pop(key, None)
        if lease is not None:
            lease.release()


def validate_request_id(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value):
        raise ValueError("client_request_id 须为 1 至 128 位字母、数字或 . _ : -")
    return value


def payload_hash(message: str, page_context: dict | None) -> str:
    return hashlib.sha256(canonical_json({"message": message, "page_context": page_context}).encode()).hexdigest()


def read_request(db_path: Path, session_id: str, key: str) -> sqlite3.Row | None:
    with closing(server_runtime.connect(db_path)) as conn:
        return conn.execute(
            "SELECT * FROM chat_request_ledger WHERE session_id = ? AND client_request_id = ?",
            (session_id, key),
        ).fetchone()


def public_status(row: sqlite3.Row) -> dict:
    status = row["status"]
    result = {
        "status": "in_progress" if status in {"reserved", "started"} else status,
        "message_id": row["turn_id"] if row["user_message_id"] is not None else None,
    }
    if status == "interrupted":
        result.update(error_category="chat_request_interrupted", memory_changed=bool(row["has_memory_effect"]),
                      action_recorded=bool(row["has_action_effect"]))
    return result


def check_identity(row: sqlite3.Row, fingerprint: str) -> None:
    if row["payload_hash"] != fingerprint:
        raise AIServiceError("idempotency_conflict", "同一请求标识不能用于不同的消息或页面上下文。",
                             status=HTTPStatus.CONFLICT)


def replay(db_path: Path, row: sqlite3.Row) -> list[dict]:
    result = json.loads(row["result_json"])
    with closing(server_runtime.connect(db_path)) as conn:
        user = conn.execute("SELECT created_at FROM chat_messages WHERE id=? AND session_id=? AND role='user'",
                            (row["user_message_id"], row["session_id"])).fetchone()
        frames = [{"event": "message.start", "data": {"message_id": row["turn_id"], "created_at": user[0]}}]
        frames.extend(result["confirmations"])
        if row["assistant_message_id"] is not None:
            assistant = conn.execute("SELECT content FROM chat_messages WHERE id=? AND session_id=? AND role='assistant'",
                                     (row["assistant_message_id"], row["session_id"])).fetchone()
            content = result.get("leading", "") + assistant[0] + result.get("trailing", "")
            frames.append({"event": "message.delta", "data": {"delta": content}})
        elif "whitespace" in result:
            frames.append({"event": "message.delta", "data": {"delta": result["whitespace"]}})
        frames.append({"event": "message.done", "data": result["done"]})
        return frames


@dataclass(frozen=True)
class RequestAttempt:
    session_id: str
    client_request_id: str
    turn_id: str

    @classmethod
    def new(cls, session_id: str, key: str | None) -> RequestAttempt:
        # '~' is outside the accepted alphabet. Keyless clients can never
        # collide with, or address, a server-generated legacy reservation.
        return cls(session_id, key if key is not None else "~" + uuid.uuid4().hex, uuid.uuid4().hex)

    def reserve(self, db_path: Path, fingerprint: str, role: str) -> None:
        """Caller holds this session's lease. Charge and reservation commit together."""
        with closing(server_runtime.connect(db_path)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            receipt = charge_chat_quota(conn, role)
            now = server_runtime.now_iso()
            cursor = conn.execute(
                """INSERT INTO chat_request_ledger(session_id, client_request_id, payload_hash, turn_id,
                       status, quota_state, quota_day, created_at, updated_at)
                   VALUES(?,?,?,?,'reserved',?,?,?,?)
                   ON CONFLICT(session_id, client_request_id) DO UPDATE SET
                       turn_id=excluded.turn_id, status='reserved', quota_state=excluded.quota_state,
                       quota_day=excluded.quota_day, user_message_id=NULL, assistant_message_id=NULL,
                       has_memory_effect=0, has_action_effect=0, result_json=NULL,
                       attempt_count=attempt_count+1, updated_at=excluded.updated_at
                   WHERE status='retryable' AND payload_hash=excluded.payload_hash""",
                (self.session_id, self.client_request_id, fingerprint, self.turn_id,
                 "charged" if receipt else "exempt", receipt["day_key"] if receipt else None, now, now),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("chat reservation no longer eligible")
            conn.commit()

    def _advance(self, conn: sqlite3.Connection, fields: str, values: tuple, *, expected: str) -> None:
        # Each provider attempt has a new turn_id. A late callback from a
        # cancelled to_thread task cannot commit data into a newer attempt.
        cursor = conn.execute(
            f"UPDATE chat_request_ledger SET {fields}, updated_at=? "
            "WHERE session_id=? AND client_request_id=? AND turn_id=? AND status=?",
            (*values, server_runtime.now_iso(), self.session_id, self.client_request_id, self.turn_id, expected),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("stale chat request attempt")

    def record_start(self, conn: sqlite3.Connection, user_message_id: int) -> None:
        self._advance(conn, "status='started', user_message_id=?", (user_message_id,), expected="reserved")

    def record_memory(self, conn: sqlite3.Connection) -> None:
        self._advance(conn, "has_memory_effect=1", (), expected="started")

    def record_action(self, conn: sqlite3.Connection) -> None:
        self._advance(conn, "has_action_effect=1", (), expected="started")

    def complete(self, conn: sqlite3.Connection, assistant_id: int | None,
                 done: dict, confirmations: list[dict], stream_text: str) -> None:
        receipt = {"done": done, "confirmations": confirmations}
        # History stores a trimmed reply. Preserve the wire text without
        # copying every answer into the ledger as well.
        if stream_text and stream_text != stream_text.strip():
            if assistant_id is None:
                receipt["whitespace"] = stream_text
            else:
                receipt["leading"] = stream_text[:len(stream_text) - len(stream_text.lstrip())]
                receipt["trailing"] = stream_text[len(stream_text.rstrip()):]
        result = json.dumps(receipt, ensure_ascii=False, separators=(",", ":"))
        self._advance(conn, "status='completed', assistant_message_id=?, result_json=?",
                      (assistant_id, result), expected="started")


def delete_failed_user(conn: sqlite3.Connection, session_id: str, message_id: int) -> None:
    deleted = conn.execute("DELETE FROM chat_messages WHERE id=? AND session_id=? AND role='user'",
                           (message_id, session_id))
    if deleted.rowcount:
        last = conn.execute("SELECT created_at FROM chat_messages WHERE session_id=? ORDER BY id DESC LIMIT 1",
                            (session_id,)).fetchone()
        if last is None:
            conn.execute("UPDATE chat_sessions SET title=?, updated_at=created_at WHERE id=?",
                         (DEFAULT_SESSION_TITLE, session_id))
        else:
            conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (last[0], session_id))


def _settle(conn: sqlite3.Connection, row: sqlite3.Row, counts: dict, *, dry_run: bool,
            keep_started_charge: bool = False) -> None:
    counts[row["status"]] += 1
    has_effect = bool(row["has_memory_effect"] or row["has_action_effect"])
    status = "interrupted" if has_effect else "retryable"
    counts[status] += 1
    refund = (not has_effect and row["quota_state"] == "charged"
              and not (keep_started_charge and row["status"] == "started"))
    counts["refunded"] += int(refund)
    if dry_run:
        return
    now = server_runtime.now_iso()
    if refund:
        debit = conn.execute("UPDATE ai_chat_daily_quota SET used=used-1, updated_at=? WHERE day_key=? AND used>0",
                             (now, row["quota_day"]))
        if debit.rowcount != 1:
            raise RuntimeError("chat quota reservation has no matching debit")
    user_id = row["user_message_id"]
    if user_id is not None and not has_effect:
        delete_failed_user(conn, row["session_id"], user_id)
        user_id = None
    conn.execute(
        """UPDATE chat_request_ledger SET status=?, user_message_id=?, quota_state=?, updated_at=?
           WHERE session_id=? AND client_request_id=? AND turn_id=?""",
        (status, user_id, "refunded" if refund else row["quota_state"], now,
         row["session_id"], row["client_request_id"], row["turn_id"]),
    )


def reconcile_owned_session(db_path: Path, session_id: str, *, dry_run: bool = False,
                            closing_attempt: RequestAttempt | None = None) -> dict:
    """Caller owns the OS lease. Never settle a different attempt from a response finalizer."""
    counts = dict.fromkeys(("busy", "reserved", "started", "retryable", "interrupted", "refunded"), 0)
    with closing(server_runtime.connect(db_path)) as conn:
        conn.execute("BEGIN" if dry_run else "BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM chat_request_ledger WHERE session_id=? AND status IN ('reserved','started')",
            (session_id,),
        ).fetchone()
        if row is not None and (closing_attempt is None or closing_attempt.turn_id == row["turn_id"]):
            legacy_close = closing_attempt is not None and closing_attempt.client_request_id.startswith("~")
            _settle(conn, row, counts, dry_run=dry_run, keep_started_charge=legacy_close)
        conn.commit()
    return counts


def reconcile_session(db_path: Path, session_id: str, *, dry_run: bool = False) -> dict:
    """For a status read or a maintenance sweep. Live workers always win."""
    if not claim_chat_session(db_path, session_id):
        return {"busy": 1, "reserved": 0, "started": 0, "retryable": 0, "interrupted": 0, "refunded": 0}
    try:
        return reconcile_owned_session(db_path, session_id, dry_run=dry_run)
    finally:
        release_chat_session(db_path, session_id)
