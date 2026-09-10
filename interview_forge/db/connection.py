"""Learning-database connection and one-time schema initialization.

This is the existing study database plumbing extracted from the HTTP server.
The server supplies its business timezone and AI schema initializer so import
timing, migration order, and the single process-wide schema state stay intact.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Callable

from interview_forge.ai.ai_coach import ensure_ai_schema as _default_ensure_ai_schema
from interview_forge.core.paths import DB_PATH
from interview_forge.db.schema import SCHEMA


_SCHEMA_DONE: set[str] = set()
_SCHEMA_LOCK = threading.Lock()


def _prepare_legacy_study_events_schema(connection: sqlite3.Connection) -> None:
    """Add the current ``action`` column to the pre-AC event schema."""
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'study_events'"
    ).fetchone()
    if table is None:
        return
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(study_events)")}
    if "action" in columns or "event_type" not in columns:
        return
    connection.execute("ALTER TABLE study_events ADD COLUMN action TEXT NOT NULL DEFAULT 'view'")
    connection.execute(
        "UPDATE study_events SET action = CASE WHEN event_type = 'complete' THEN 'complete' ELSE 'view' END"
    )


def _legacy_business_date(
    timestamp: object,
    fallback: object = "",
    business_tz: tzinfo | None = None,
) -> str:
    """Normalize a historical event timestamp to the business date."""
    if business_tz is None:
        business_tz = timezone(timedelta(hours=8), "Asia/Shanghai")
    try:
        parsed = datetime.fromisoformat(str(timestamp))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=business_tz)
        return parsed.astimezone(business_tz).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return str(fallback or "")[:10]


def _legacy_submission_timestamp(
    timestamp: object,
    study_date: str,
    business_tz: tzinfo | None = None,
) -> str:
    """Return a valid aware timestamp for a migrated AC submission."""
    if business_tz is None:
        business_tz = timezone(timedelta(hours=8), "Asia/Shanghai")
    try:
        parsed = datetime.fromisoformat(str(timestamp))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=business_tz)
        return parsed.astimezone(business_tz).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError):
        return f"{study_date}T00:00:00+08:00"


def _backfill_legacy_completes(
    connection: sqlite3.Connection,
    business_tz: tzinfo | None = None,
) -> None:
    """Idempotently mirror historical complete events into AC submissions."""
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(study_events)")}
    if not {"problem_id", "studied_at"}.issubset(columns):
        return
    if "action" in columns:
        kind_sql = "action"
    elif "event_type" in columns:
        kind_sql = "event_type"
    else:
        return
    date_sql = "study_date" if "study_date" in columns else "NULL"
    events = connection.execute(
        f"SELECT problem_id, studied_at, {date_sql} AS study_date, {kind_sql} AS event_kind "
        "FROM study_events WHERE " + kind_sql + " = 'complete' ORDER BY rowid"
    ).fetchall()
    if not events:
        return
    existing_dates = {
        (int(row["problem_id"]), _legacy_business_date(row["submitted_at"], business_tz=business_tz))
        for row in connection.execute(
            "SELECT problem_id, submitted_at FROM submissions WHERE status = 'ac'"
        )
    }
    migrated: set[tuple[int, str]] = set()
    for row in events:
        problem_id = int(row["problem_id"])
        study_date = _legacy_business_date(row["studied_at"], row["study_date"], business_tz)
        if not study_date:
            continue
        key = (problem_id, study_date)
        if key in existing_dates or key in migrated:
            continue
        connection.execute(
            """INSERT INTO submissions(
                   problem_id, status, lang, runtime_ms, memory_kb, submitted_at, source
               ) VALUES (?, 'ac', '', NULL, NULL, ?, 'manual')""",
            (
                problem_id,
                _legacy_submission_timestamp(row["studied_at"], study_date, business_tz),
            ),
        )
        migrated.add(key)
    if migrated:
        connection.commit()


def connect(
    db_path: Path = DB_PATH,
    *,
    business_tz: tzinfo | None = None,
    ensure_ai_schema: Callable[[sqlite3.Connection], None] = _default_ensure_ai_schema,
) -> sqlite3.Connection:
    """Open a learning database and initialize its schema exactly once per path."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    schema_key = str(db_path)
    if schema_key not in _SCHEMA_DONE:
        with _SCHEMA_LOCK:
            if schema_key not in _SCHEMA_DONE:
                connection.execute("PRAGMA journal_mode = WAL")
                _prepare_legacy_study_events_schema(connection)
                connection.executescript(SCHEMA)
                ensure_ai_schema(connection)
                try:
                    connection.execute("ALTER TABLE submissions ADD COLUMN lc_id INTEGER")
                except sqlite3.OperationalError:
                    pass
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_submissions_lc ON submissions(lc_id) WHERE lc_id IS NOT NULL"
                )
                _backfill_legacy_completes(connection, business_tz)
                _SCHEMA_DONE.add(schema_key)
    return connection
